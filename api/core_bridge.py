"""
Core Bridge - Acceso directo a instancias reales del CORE.

Este módulo es el ÚNICO punto de lectura del estado real del sistema.
NO genera estado propio, NO inventa datos, SOLO lee del core vivo.

Si el core no está inicializado → devuelve None/offline.
"""
import time
from datetime import datetime
from typing import Dict, Any, Optional
from services.app_state import AppState


def _get_app_state() -> Optional[AppState]:
    """Obtiene AppState si está inicializado, sino None."""
    try:
        inst = AppState.get_instance()
        if inst.is_initialized():
            return inst
        return inst  # Degraded pero existe
    except RuntimeError:
        return None


def _get_calendar_manager():
    """
    Obtiene CalendarManager desde múltiples rutas.
    1. Singleton global del módulo calendar
    2. Desde AppState.calendar_manager
    3. Desde AppState.main_window.calendar_manager
    """
    # Ruta 1: Singleton global
    try:
        from core.calendar import get_calendar_manager
        cm = get_calendar_manager()
        if cm:
            return cm
    except ImportError:
        pass

    # Ruta 2: Desde AppState
    app_state = _get_app_state()
    if app_state:
        cm = getattr(app_state, 'calendar_manager', None)
        if cm:
            return cm

        # Ruta 3: Desde main_window
        main_window = getattr(app_state, 'main_window', None)
        if main_window:
            cm = getattr(main_window, 'calendar_manager', None)
            if cm:
                return cm

    return None


def get_full_snapshot() -> Dict[str, Any]:
    """
    Snapshot COMPLETO del estado real del CORE.

    Retorna EXACTAMENTE:
    - state: str (BAJADA, BASE_GOLPE, ATAQUE, BRAKE)
    - energy: str (BAJA, MEDIA, ALTA)
    - audio: {running, device, silence, clipping, level}
    - avolites: {connected, ip, port, latency_ms}
    - cameras: [{name, online, fps}]
    - calendar: {day, time, current_mode, next_mode, remaining, override_active}
    - system: {cpu, ram}
    - ts: timestamp

    Si algo no está disponible → null/offline, NUNCA inventar.
    """
    now = datetime.now()
    ts = int(time.time())

    app_state = _get_app_state()

    # ====== STATE & ENERGY (LO MÁS IMPORTANTE) ======
    state = None
    energy = None

    if app_state and app_state.state_manager:
        try:
            state = app_state.state_manager.get_state()
            energy = app_state.state_manager.get_energy()
        except Exception as e:
            print(f"[CORE_BRIDGE] StateManager error: {e}")

    # ====== AUDIO ======
    audio = {
        "running": False,
        "device": None,
        "silence": True,
        "clipping": False,
        "level": 0.0
    }

    if app_state and app_state.audio_engine:
        try:
            eng = app_state.audio_engine
            audio["running"] = getattr(eng, 'is_running', False)
            audio["device"] = getattr(eng, 'device_name', None)

            # Nivel desde audio_monitor si existe
            if app_state.audio_monitor:
                level = getattr(app_state.audio_monitor, 'current_level', 0.0)
                if level:
                    audio["level"] = round(level, 3)
                    audio["silence"] = level < 0.001
                    audio["clipping"] = level > 0.95
            else:
                # Intentar desde engine.get_status()
                try:
                    status = eng.get_status()
                    rms = status.get("rms_db", -60)
                    # Convertir dB a nivel lineal aproximado
                    if rms > -60:
                        level = 10 ** (rms / 20)
                        audio["level"] = round(level, 3)
                        audio["silence"] = rms < -50
                        audio["clipping"] = rms > -3
                except:
                    pass
        except Exception as e:
            print(f"[CORE_BRIDGE] AudioEngine error: {e}")

    # ====== AVOLITES ======
    avolites = {
        "connected": False,
        "ip": "",
        "port": 4430,
        "latency_ms": None
    }

    if app_state and app_state.avolites:
        try:
            status = app_state.avolites.get_status()
            avolites["connected"] = status.get("is_connected", False)
            avolites["ip"] = status.get("console_ip", "")
            avolites["port"] = status.get("console_port", 4430)

            latency = status.get("latency_ms")
            if latency is not None:
                avolites["latency_ms"] = int(latency)
        except Exception as e:
            print(f"[CORE_BRIDGE] Avolites error: {e}")

    # ====== CAMERAS (VISION) ======
    cameras = []
    camera_types = ["haze", "people", "tracking"]

    if app_state and app_state.vision_manager:
        try:
            vm = app_state.vision_manager

            for cam_type in camera_types:
                cam_info = {
                    "name": cam_type,
                    "online": False,
                    "fps": 0,
                    "ip": ""
                }

                # Buscar handler
                handler = getattr(vm, f"{cam_type}_handler", None)
                if handler:
                    cam_info["online"] = getattr(handler, 'is_running', False)
                    cam_info["ip"] = getattr(handler, 'camera_ip', "") or ""
                    cam_info["fps"] = getattr(handler, 'current_fps', 0) or 0

                cameras.append(cam_info)
        except Exception as e:
            print(f"[CORE_BRIDGE] Vision error: {e}")
    else:
        # Sin vision manager - todas offline
        for cam_type in camera_types:
            cameras.append({
                "name": cam_type,
                "online": False,
                "fps": 0,
                "ip": ""
            })

    # ====== CALENDAR ======
    days_es = {
        "monday": "lunes", "tuesday": "martes", "wednesday": "miércoles",
        "thursday": "jueves", "friday": "viernes", "saturday": "sábado", "sunday": "domingo"
    }

    calendar = {
        "day": days_es.get(now.strftime("%A").lower(), now.strftime("%A").lower()),
        "time": now.strftime("%H:%M:%S"),
        "current_mode": None,
        "next_mode": None,
        "time_remaining_s": -1,
        "time_to_next_s": -1,
        "override_active": False,
        "auto": True,
        "source": None
    }

    cm = _get_calendar_manager()
    if cm:
        try:
            state_data = cm.get_state()
            calendar["current_mode"] = state_data.get("current_mode")
            calendar["next_mode"] = state_data.get("next_mode")
            calendar["override_active"] = state_data.get("is_override", False)
            calendar["auto"] = state_data.get("auto_mode_enabled", True)
            calendar["source"] = state_data.get("source")

            # Tiempo restante
            if state_data.get("time_remaining_s"):
                calendar["time_remaining_s"] = state_data["time_remaining_s"]

            if state_data.get("time_to_next_s"):
                calendar["time_to_next_s"] = state_data["time_to_next_s"]

            # Si hay next_change_at, calcular tiempo
            if state_data.get("next_change_at"):
                try:
                    next_dt = datetime.fromisoformat(state_data["next_change_at"])
                    calendar["time_to_next_s"] = max(0, int((next_dt - now).total_seconds()))
                except:
                    pass

        except Exception as e:
            print(f"[CORE_BRIDGE] Calendar error: {e}")

    # ====== SYSTEM RESOURCES ======
    system = {
        "cpu": 0,
        "ram": 0,
        "gpu": 0,
        "temp": 0
    }

    try:
        import psutil
        system["cpu"] = int(psutil.cpu_percent(interval=None))
        system["ram"] = int(psutil.virtual_memory().percent)
    except:
        pass

    # ====== SNAPSHOT FINAL ======
    return {
        "ts": ts,
        "state": state,
        "energy": energy,
        "audio": audio,
        "avolites": avolites,
        "cameras": cameras,
        "calendar": calendar,
        "system": system
    }


# ==================== COMANDOS AL CORE ====================

def calendar_go(mode: str, delay_minutes: int = 0) -> Dict[str, Any]:
    """
    Ejecuta GO en el CalendarManager real.
    """
    cm = _get_calendar_manager()
    if not cm:
        return {"success": False, "error": "CalendarManager not available"}

    try:
        from core.calendar.calendar_state import CalendarSource
        success = cm.go(
            mode=mode,
            source=CalendarSource.MANUAL,
            delay_minutes=delay_minutes
        )
        return {"success": success, "mode": mode, "delay_minutes": delay_minutes}
    except Exception as e:
        return {"success": False, "error": str(e)}


def calendar_extend(minutes: int) -> Dict[str, Any]:
    """
    Extiende el bloque actual por N minutos.
    """
    cm = _get_calendar_manager()
    if not cm:
        return {"success": False, "error": "CalendarManager not available"}

    try:
        current_mode = cm.get_current_mode()
        from core.calendar.calendar_manager import OverrideType

        success = cm.set_override(
            mode=current_mode,
            override_type=OverrideType.TEMPORARY,
            duration_minutes=minutes,
            reason=f"Extend +{minutes}min"
        )
        return {"success": success, "mode": current_mode, "extended_minutes": minutes}
    except Exception as e:
        return {"success": False, "error": str(e)}


def calendar_override(mode: str, duration_minutes: int = 30, reason: str = "") -> Dict[str, Any]:
    """
    Activa override temporal.
    """
    cm = _get_calendar_manager()
    if not cm:
        return {"success": False, "error": "CalendarManager not available"}

    try:
        from core.calendar.calendar_manager import OverrideType

        success = cm.set_override(
            mode=mode,
            override_type=OverrideType.TEMPORARY,
            duration_minutes=duration_minutes,
            reason=reason or "Override desde web"
        )
        return {"success": success, "mode": mode, "duration_minutes": duration_minutes}
    except Exception as e:
        return {"success": False, "error": str(e)}


def calendar_stop_override() -> Dict[str, Any]:
    """
    Detiene el override activo.
    """
    cm = _get_calendar_manager()
    if not cm:
        return {"success": False, "error": "CalendarManager not available"}

    try:
        was_active = cm.is_override_active()
        cm.clear_override()
        return {"success": True, "was_active": was_active}
    except Exception as e:
        return {"success": False, "error": str(e)}
