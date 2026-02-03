"""
Status Router - Sistema status endpoint + SSE para Control Room V7
"""
import time
import asyncio
import json
from datetime import datetime
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from api.models import (
    SystemStatus, AudioEngineStatus, AvolitesStatus, CueEngineStatus,
    UnifiedStatus, AudioHealthStatus, AvolitesHealthStatus,
    CameraStatus, SystemResourcesStatus, CalendarStatusBrief
)
from api.dependencies import get_app_state
from services.app_state import AppState

router = APIRouter()


# ==================== LEGACY STATUS (mantener compatibilidad) ====================

@router.get("/status", response_model=SystemStatus)
async def get_system_status(
    app_state: AppState = Depends(get_app_state)
):
    """
    Obtener estado completo del sistema (legacy).
    """
    state = "BAJADA"
    energy = "BAJA"
    state_locked = False
    brake_active = False

    if app_state.state_manager:
        try:
            state = app_state.state_manager.get_state()
            energy = app_state.state_manager.get_energy()
            state_locked = getattr(app_state.state_manager, 'state_locked', False)
            brake_active = getattr(app_state.state_manager, 'brake_active', False)
        except Exception:
            pass

    audio_status = AudioEngineStatus(
        device=None,
        samplerate=44100,
        channels=2,
        running=False,
        buffer_size=None
    )

    if app_state.audio_engine:
        try:
            audio_status = AudioEngineStatus(
                device=getattr(app_state.audio_engine, 'device_name', None),
                samplerate=getattr(app_state.audio_engine, 'samplerate', 44100),
                channels=2,
                running=getattr(app_state.audio_engine, 'is_running', False),
                buffer_size=None
            )
        except Exception:
            pass

    avolites_status = AvolitesStatus(
        connection_state="NOT_READY",
        is_connected=False,
        console_ip="",
        console_port=4430,
        last_error=None,
        active_cues_count=0
    )

    if app_state.avolites:
        try:
            status = app_state.avolites.get_status()
            active_cues = getattr(app_state.avolites, '_active_cues', set())

            avolites_status = AvolitesStatus(
                connection_state=status.get("connection_state", "NOT_READY"),
                is_connected=status.get("is_connected", False),
                console_ip=status.get("console_ip", ""),
                console_port=status.get("console_port", 4430),
                last_error=status.get("last_error"),
                active_cues_count=len(active_cues) if isinstance(active_cues, set) else 0
            )
        except Exception:
            pass

    cue_engine_status = CueEngineStatus(
        modules_active=0,
        total_updates=0,
        last_state="",
        running=False
    )

    if app_state.cue_engine:
        try:
            status = app_state.cue_engine.get_status()
            cue_engine_status = CueEngineStatus(
                modules_active=status.get("modules_active", 0),
                total_updates=status.get("total_updates", 0),
                last_state=status.get("last_state", ""),
                running=status.get("running", False)
            )
        except Exception:
            pass

    return SystemStatus(
        state=state,
        energy=energy,
        state_locked=state_locked,
        brake_active=brake_active,
        uptime_seconds=app_state.get_uptime(),
        version=app_state.version,
        audio=audio_status,
        avolites=avolites_status,
        cue_engine=cue_engine_status
    )


# ==================== UNIFIED STATUS V7 ====================

def _build_unified_status(app_state: AppState) -> dict:
    """
    Construye el payload unificado para Control Room V7.
    Nunca lanza excepción - siempre devuelve datos válidos.
    """
    now = datetime.now()

    # Audio Health
    audio = AudioHealthStatus(
        silence=False,
        clipping=False,
        level=0.0,
        device=None
    )

    if app_state.audio_engine:
        try:
            audio.device = getattr(app_state.audio_engine, 'device_name', None)
            # Obtener nivel RMS si hay audio_monitor
            if app_state.audio_monitor:
                level = getattr(app_state.audio_monitor, 'current_level', 0.0)
                audio.level = round(level, 3) if level else 0.0
                audio.silence = level < 0.001 if level else True
                audio.clipping = level > 0.95 if level else False
        except Exception:
            pass

    # Avolites Health
    avolites = AvolitesHealthStatus(
        connected=False,
        console_ip="",
        port=4430,
        latency_ms=None
    )

    if app_state.avolites:
        try:
            status = app_state.avolites.get_status()
            avolites.connected = status.get("is_connected", False)
            avolites.console_ip = status.get("console_ip", "")
            avolites.port = status.get("console_port", 4430)
            # Obtener latencia si está disponible
            latency = status.get("latency_ms")
            if latency is not None:
                avolites.latency_ms = int(latency)
        except Exception:
            pass

    # Cameras (Vision)
    cameras = []
    if app_state.vision_manager:
        try:
            # Intentar obtener estado de cámaras
            vm = app_state.vision_manager
            camera_types = ["haze", "people", "tracking"]
            for cam_type in camera_types:
                cam_info = CameraStatus(
                    name=cam_type,
                    ip="",
                    online=False,
                    fps=0
                )
                # Buscar handler de cámara
                handler = getattr(vm, f"{cam_type}_handler", None)
                if handler:
                    cam_info.online = getattr(handler, 'is_running', False)
                    cam_info.ip = getattr(handler, 'camera_ip', "") or ""
                    cam_info.fps = getattr(handler, 'current_fps', 0) or 0
                cameras.append(cam_info)
        except Exception:
            pass

    # System Resources
    system = SystemResourcesStatus(cpu=0, ram=0, gpu=0, temp=0)
    try:
        import psutil
        system.cpu = int(psutil.cpu_percent(interval=None))
        system.ram = int(psutil.virtual_memory().percent)
        # GPU y temp son opcionales
    except Exception:
        pass

    # Calendar
    calendar = CalendarStatusBrief(
        day=now.strftime("%A").lower(),
        time=now.strftime("%H:%M:%S"),
        current_mode="apagado",
        next_mode=None,
        time_remaining_s=-1,
        time_to_next_s=-1,
        override_active=False,
        auto=True
    )

    # Obtener CalendarManager desde app_state o main window
    calendar_manager = getattr(app_state, 'calendar_manager', None)
    if calendar_manager is None:
        # Intentar desde main_window
        main_window = getattr(app_state, 'main_window', None)
        if main_window:
            calendar_manager = getattr(main_window, 'calendar_manager', None)

    if calendar_manager:
        try:
            state = calendar_manager.get_state()
            calendar.current_mode = state.get("current_mode", "apagado")
            calendar.next_mode = state.get("next_mode")
            calendar.override_active = state.get("is_override", False)
            calendar.auto = state.get("auto_mode_enabled", True)

            # Tiempo restante
            if state.get("next_change_at"):
                try:
                    next_dt = datetime.fromisoformat(state["next_change_at"])
                    calendar.time_to_next_s = max(0, int((next_dt - now).total_seconds()))
                except:
                    pass

            # Progreso del bloque actual
            progress = state.get("progress", 0)
            if progress > 0:
                # Estimar tiempo restante del bloque
                block = state.get("active_block")
                if block:
                    try:
                        total_seconds = (datetime.strptime(block["to_time"], "%H:%M") -
                                        datetime.strptime(block["from_time"], "%H:%M")).total_seconds()
                        calendar.time_remaining_s = int(total_seconds * (1 - progress))
                    except:
                        pass
        except Exception as e:
            print(f"[WEB][STATUS] Calendar error: {e}")

    # Día en español
    days_es = {
        "monday": "lunes", "tuesday": "martes", "wednesday": "miércoles",
        "thursday": "jueves", "friday": "viernes", "saturday": "sábado", "sunday": "domingo"
    }
    calendar.day = days_es.get(now.strftime("%A").lower(), now.strftime("%A").lower())

    return UnifiedStatus(
        ts=int(time.time()),
        audio=audio,
        avolites=avolites,
        cameras=cameras,
        system=system,
        calendar=calendar
    ).model_dump()


@router.get("/status/unified")
async def get_unified_status(
    app_state: AppState = Depends(get_app_state)
):
    """
    GET /api/v1/status/unified

    Estado unificado para Control Room V7.
    Un solo endpoint con todo lo que la web necesita.
    Nunca devuelve 500 - siempre datos válidos (null/false si falla algo).
    """
    print("[WEB][STATUS] unified status requested")
    return _build_unified_status(app_state)


# ==================== SSE STREAM ====================

async def _status_event_generator(app_state: AppState):
    """
    Generador de eventos SSE para tiempo real.
    Emite el mismo payload que /status/unified cada 500ms.
    """
    print("[WEB][SSE] stream started")
    try:
        while True:
            try:
                data = _build_unified_status(app_state)
                yield f"data: {json.dumps(data)}\n\n"
            except Exception as e:
                # Emitir error como evento pero no romper stream
                error_data = {"error": str(e), "ts": int(time.time())}
                yield f"data: {json.dumps(error_data)}\n\n"

            await asyncio.sleep(0.5)  # 500ms = 2 updates/segundo
    except asyncio.CancelledError:
        print("[WEB][SSE] stream cancelled")
        raise
    finally:
        print("[WEB][SSE] stream ended")


@router.get("/stream")
async def status_stream(
    app_state: AppState = Depends(get_app_state)
):
    """
    GET /api/v1/stream

    Server-Sent Events (SSE) para tiempo real.
    Emite el mismo payload que /status/unified cada 500ms.

    Uso en cliente:
        const es = new EventSource('/api/v1/stream');
        es.onmessage = (e) => { const data = JSON.parse(e.data); ... };
    """
    return StreamingResponse(
        _status_event_generator(app_state),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Para nginx
        }
    )
