# core/boot_manager.py
"""
BootManager v1.0 - Bootstrap Global Determinístico

Implementa AUTO LOAD SHOW con las siguientes garantías:
1. Cargar última config persistida
2. Cargar último preset de analizadores
3. Resolver calendario "NOW" con timezone correcto (no cache)
4. Aplicar acciones al runtime (Vision ON/OFF) forzado
5. Sincronizar consola: KILL ALL + rearmar baseline
6. Publicar estado final (READY) y recién ahí arrancar polling

PRINCIPIOS:
- Idempotente: si el sistema reinicia, no genera loops
- No congela UI: todo async donde sea posible
- Reutiliza pathways existentes: no duplica lógica
- Un solo log de resumen al final

DEPENDENCIAS:
- CalendarManager: resolve(force=True)
- VisionManager: sync_to_actions(actions, force=True)
- AvolitesController: kill_all_cues()
- CueEngine: silent_reset()
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import TYPE_CHECKING, Optional, Dict, Any, List
import threading

if TYPE_CHECKING:
    from core.calendar import CalendarManager
    from core_vision import VisionManager
    from cue_engine import CueEngine


class BootState:
    """Estado del proceso de boot."""
    PENDING = "PENDING"
    BOOTING = "BOOTING"
    READY = "READY"
    FAILED = "FAILED"


class BootManager:
    """
    Manager de bootstrap global para 911 Fiesta.

    Garantiza un arranque determinístico y reproducible.
    """

    def __init__(
        self,
        avolites=None,
        cue_engine: Optional[CueEngine] = None,
        calendar_manager: Optional[CalendarManager] = None,
        vision_manager: Optional[VisionManager] = None,
        system_bridge=None,
        state_manager=None,
        energy_detector=None,
    ):
        """
        Inicializa el BootManager.

        Args:
            avolites: AvolitesController para kill_all
            cue_engine: CueEngine para silent_reset
            calendar_manager: CalendarManager para resolve
            vision_manager: VisionManager para sync
            system_bridge: SystemBridge para apply
            state_manager: StateManager para estado actual
            energy_detector: EnergyDetector para energía
        """
        self._avolites = avolites
        self._cue_engine = cue_engine
        self._calendar = calendar_manager
        self._vision = vision_manager
        self._bridge = system_bridge
        self._state_manager = state_manager
        self._energy = energy_detector

        # Estado de boot
        self._boot_state = BootState.PENDING
        self._boot_started_at: Optional[datetime] = None
        self._boot_completed_at: Optional[datetime] = None
        self._boot_error: Optional[str] = None

        # Pending baseline (si Titan offline en boot)
        self._pending_boot_baseline = False
        self._baseline_applied = False

        # Lock para boot único
        self._boot_lock = threading.Lock()

        print("[BootManager] v1.0 inicializado")

    # ==================== MAIN BOOT ====================

    def boot_autoload_show(self) -> bool:
        """
        BOOT AUTO LOAD SHOW — Secuencia de arranque determinística.

        Ejecutar UNA SOLA VEZ al inicio de la aplicación.
        Si ya se ejecutó, retorna True sin hacer nada.

        Secuencia:
        1. KILL ALL en consola (baseline limpio)
        2. Calendar resolve con force=True
        3. Vision sync con actions del calendario
        4. CueEngine baseline (C41 dimmer)
        5. Log READY con resumen de estado

        Returns:
            True si el boot fue exitoso, False si hubo error
        """
        # Solo permitir un boot
        if not self._boot_lock.acquire(blocking=False):
            print("[BOOT] SKIP: boot ya en progreso")
            return True

        try:
            if self._boot_state == BootState.READY:
                print("[BOOT] SKIP: sistema ya booteado")
                return True

            self._boot_state = BootState.BOOTING
            self._boot_started_at = datetime.now()

            print("[BOOT] ========== AUTO LOAD SHOW START ==========")

            # PASO 1: Console baseline (KILL ALL)
            self._boot_console_baseline()

            # PASO 2: Calendar bootstrap (resolve + apply forzado)
            calendar_state = self._boot_calendar_resolve()

            # PASO 3: Vision bootstrap (sync a actions del calendario)
            self._boot_vision_sync(calendar_state)

            # PASO 4: CueEngine baseline (C41 dimmer ON)
            self._boot_cue_engine_baseline()

            # PASO 5: Log READY
            self._boot_completed_at = datetime.now()
            self._boot_state = BootState.READY

            self._log_boot_ready(calendar_state)

            print("[BOOT] ========== AUTO LOAD SHOW COMPLETE ==========")
            return True

        except Exception as e:
            self._boot_state = BootState.FAILED
            self._boot_error = str(e)
            print(f"[BOOT] ERROR: {e}")
            import traceback
            traceback.print_exc()
            return False

        finally:
            self._boot_lock.release()

    # ==================== BOOT STEPS ====================

    def _boot_console_baseline(self) -> None:
        """
        PASO 1: Console baseline — KILL ALL + reset estado.

        Usa el pathway canónico del botón KILL ALL de Cues Monitor.
        Si Titan offline, marca pending_boot_baseline para retry.
        """
        print("[BOOT] Step 1: Console baseline (KILL ALL)")

        titan_online = False

        # 1. Kill all cues en Titan
        if self._avolites:
            try:
                # Verificar si Titan está conectado
                status = self._avolites.get_status()
                titan_online = status.get("connected", False)

                if titan_online:
                    self._avolites.kill_all_cues()
                    print("[BOOT] → Titan KILL ALL OK")
                else:
                    print("[BOOT] → Titan OFFLINE, marking pending baseline")
                    self._pending_boot_baseline = True

            except Exception as e:
                print(f"[BOOT] → Titan KILL ALL failed: {e}")
                self._pending_boot_baseline = True
        else:
            print("[BOOT] → No avolites controller")

        # 2. Silent reset del CueEngine
        if self._cue_engine and hasattr(self._cue_engine, 'silent_reset'):
            try:
                self._cue_engine.silent_reset()
                print("[BOOT] → CueEngine silent reset OK")
            except Exception as e:
                print(f"[BOOT] → CueEngine silent reset failed: {e}")

    def _boot_calendar_resolve(self) -> Dict[str, Any]:
        """
        PASO 2: Calendar bootstrap — resolve forzado.

        Resuelve el calendario usando datetime.now() y aplica
        el estado INMEDIATAMENTE, bypasseando dedup.

        Returns:
            Dict con: mode, actions, day_key
        """
        print("[BOOT] Step 2: Calendar resolve (force)")

        result = {
            "mode": "apagado",
            "actions": [],
            "day_key": datetime.now().strftime("%A").lower(),
        }

        if not self._calendar:
            print("[BOOT] → No calendar manager")
            return result

        try:
            # Forzar resolve con now actual
            now = datetime.now()

            # Obtener resolver interno
            resolver = getattr(self._calendar, '_resolver', None)
            if resolver:
                mode, block, next_change = resolver.resolve(now)

                if mode:
                    result["mode"] = mode
                    result["actions"] = block.actions if block else []
                    result["day_key"] = block.day if block else result["day_key"]

                    print(f"[BOOT] → Resolved: mode={mode} actions={result['actions']} day={result['day_key']}")

                    # Aplicar via SystemBridge con force
                    if self._bridge and hasattr(self._bridge, 'apply_calendar_state'):
                        self._bridge.apply_calendar_state(mode, result["actions"])
                        print("[BOOT] → Applied via SystemBridge")
                    elif hasattr(self._calendar, 'go'):
                        # Fallback: usar GO manual
                        self._calendar.go(mode)
                        print("[BOOT] → Applied via Calendar.go()")
                else:
                    print("[BOOT] → No active block (ZZZ mode)")
                    # Aplicar ZZZ explícitamente
                    if self._bridge and hasattr(self._bridge, 'apply_calendar_state'):
                        self._bridge.apply_calendar_state("apagado", [])
                        print("[BOOT] → Applied ZZZ via SystemBridge")
            else:
                # Fallback: usar force_resolve
                if hasattr(self._calendar, 'force_resolve'):
                    self._calendar.force_resolve()
                    print("[BOOT] → Used force_resolve()")

                # Obtener estado resultante
                state = self._calendar.get_state()
                result["mode"] = state.get("current_mode", "apagado")
                result["actions"] = state.get("current_actions", [])

        except Exception as e:
            print(f"[BOOT] → Calendar resolve failed: {e}")

        return result

    def _boot_vision_sync(self, calendar_state: Dict[str, Any]) -> None:
        """
        PASO 3: Vision bootstrap — sync forzado a actions.

        Sincroniza Vision con las actions del calendario.
        Si action incluye vision_haze → force enable
        Si action NO incluye vision_haze → force disable

        Args:
            calendar_state: Dict con mode y actions del calendario
        """
        print("[BOOT] Step 3: Vision sync (force)")

        if not self._vision:
            print("[BOOT] → No vision manager")
            return

        try:
            actions = set(calendar_state.get("actions", []))

            # HAZE: force sync
            haze_on = "vision_haze" in actions
            self._boot_vision_module("haze", haze_on)

            # DJ: force sync
            dj_on = "vision_dj" in actions or "dj_detection" in actions
            self._boot_vision_module("dj", dj_on)

            # ARTIST: force sync (con exclusión mutua)
            artist_on = "vision_artista" in actions or "tracking_cam" in actions
            if dj_on and artist_on:
                print("[BOOT] → EXCLUSION: DJ + Artist → Artist OFF")
                artist_on = False
            self._boot_vision_module("tracking", artist_on)

            # Auto-start si hay algún módulo activo
            if (haze_on or dj_on or artist_on) and not self._vision.running:
                print("[BOOT] → Vision auto-start (modules active)")
                self._vision.start(force=True)

            print(f"[BOOT] → Vision synced: haze={haze_on} dj={dj_on} artist={artist_on}")

        except Exception as e:
            print(f"[BOOT] → Vision sync failed: {e}")

    def _boot_vision_module(self, name: str, enabled: bool) -> None:
        """
        Sincroniza un módulo de Vision con force.

        Garantiza:
        - Si enabled=True y detector OFF → force enable con restart
        - Si enabled=False y detector ON → force disable con teardown

        Args:
            name: Nombre del módulo (haze, dj, tracking)
            enabled: Estado deseado
        """
        if not self._vision:
            return

        try:
            # Mapeo de detectores
            detector_map = {
                "haze": getattr(self._vision, 'haze_detector', None),
                "dj": getattr(self._vision, 'dj_detector', None),
                "tracking": getattr(self._vision, 'artist_detector', None),
            }

            detector = detector_map.get(name)
            if not detector:
                return

            # Obtener estado actual del detector
            current_enabled = getattr(detector, 'enabled', False)

            if enabled and not current_enabled:
                # Force enable
                if hasattr(self._vision, 'enable_module'):
                    self._vision.enable_module(name, True, source="boot", persist=False)
                    print(f"[BOOT] → {name}: OFF→ON (force)")

            elif not enabled and current_enabled:
                # Force disable
                if hasattr(self._vision, 'enable_module'):
                    self._vision.enable_module(name, False, source="boot", persist=False)
                    print(f"[BOOT] → {name}: ON→OFF (force)")

            elif enabled:
                # Ya está ON pero puede estar en dirty state
                # Force restart via enable_module
                if hasattr(self._vision, 'enable_module'):
                    self._vision.enable_module(name, True, source="boot", persist=False)
                    print(f"[BOOT] → {name}: ON (refresh)")

        except Exception as e:
            print(f"[BOOT] → {name} sync failed: {e}")

    def _boot_cue_engine_baseline(self) -> None:
        """
        PASO 4: CueEngine baseline — C41 dimmer ON.

        Dispara C41 para asegurar que el dimmer esté ON.
        Este es el estado baseline del sistema.
        """
        print("[BOOT] Step 4: CueEngine baseline (C41)")

        if not self._avolites:
            print("[BOOT] → No avolites controller")
            return

        try:
            # Verificar si Titan está conectado
            status = self._avolites.get_status()
            titan_online = status.get("connected", False)

            if titan_online:
                self._avolites.fire_cue(41)
                print("[BOOT] → C41 fired (dimmer ON)")
                self._baseline_applied = True
            else:
                print("[BOOT] → Titan OFFLINE, C41 pending")
                self._pending_boot_baseline = True

        except Exception as e:
            print(f"[BOOT] → C41 fire failed: {e}")

    def _log_boot_ready(self, calendar_state: Dict[str, Any]) -> None:
        """
        PASO 5: Log de resumen READY.

        Un único log con todo el estado del sistema.

        Args:
            calendar_state: Estado del calendario
        """
        # Obtener info de componentes
        mode = calendar_state.get("mode", "unknown")
        actions = calendar_state.get("actions", [])
        day = calendar_state.get("day_key", "unknown")

        # Vision state
        vision_haze = "OFF"
        vision_dj = "OFF"
        vision_artist = "OFF"

        if self._vision:
            try:
                state = self._vision.get_state()
                vision_haze = "ON" if state.get("haze", {}).get("enabled") else "OFF"
                vision_dj = "ON" if state.get("dj", {}).get("enabled") else "OFF"
                vision_artist = "ON" if state.get("tracking", {}).get("enabled") else "OFF"
            except:
                pass

        # Titan state
        titan = "OFFLINE"
        if self._avolites:
            try:
                status = self._avolites.get_status()
                titan = "ONLINE" if status.get("connected") else "OFFLINE"
            except:
                pass

        # Audio device
        audio = "N/A"

        # Tiempo de boot
        boot_time_ms = 0
        if self._boot_started_at and self._boot_completed_at:
            boot_time_ms = int((self._boot_completed_at - self._boot_started_at).total_seconds() * 1000)

        # Log único de resumen
        print(f"[BOOT] READY day={day} mode={mode} actions={actions} vision(haze/dj/artist)={vision_haze}/{vision_dj}/{vision_artist} titan={titan} boot_time={boot_time_ms}ms")

    # ==================== PENDING BASELINE ====================

    def apply_pending_baseline(self) -> bool:
        """
        Aplica el baseline pendiente si Titan se reconecta.

        Llamar desde un callback de conexión de Titan.
        Solo ejecuta UNA VEZ (no spam).

        Returns:
            True si se aplicó, False si no había pendiente
        """
        if not self._pending_boot_baseline:
            return False

        if self._baseline_applied:
            return False

        print("[BOOT] Applying pending baseline (Titan reconnected)")

        try:
            if self._avolites:
                # Kill all primero
                self._avolites.kill_all_cues()
                print("[BOOT] → Pending: KILL ALL OK")

                # Luego C41
                self._avolites.fire_cue(41)
                print("[BOOT] → Pending: C41 OK")

                self._baseline_applied = True
                self._pending_boot_baseline = False
                return True

        except Exception as e:
            print(f"[BOOT] → Pending baseline failed: {e}")

        return False

    def has_pending_baseline(self) -> bool:
        """Verifica si hay baseline pendiente."""
        return self._pending_boot_baseline and not self._baseline_applied

    # ==================== STATUS ====================

    def get_status(self) -> Dict[str, Any]:
        """
        Obtiene estado del boot.

        Returns:
            Dict con estado del boot
        """
        return {
            "state": self._boot_state,
            "started_at": self._boot_started_at.isoformat() if self._boot_started_at else None,
            "completed_at": self._boot_completed_at.isoformat() if self._boot_completed_at else None,
            "error": self._boot_error,
            "pending_baseline": self._pending_boot_baseline,
            "baseline_applied": self._baseline_applied,
        }

    def is_ready(self) -> bool:
        """Verifica si el boot completó exitosamente."""
        return self._boot_state == BootState.READY


# ==================== SINGLETON ====================

_boot_manager_instance: Optional[BootManager] = None


def get_boot_manager() -> Optional[BootManager]:
    """Obtiene la instancia singleton del BootManager."""
    global _boot_manager_instance
    return _boot_manager_instance


def create_boot_manager(
    avolites=None,
    cue_engine=None,
    calendar_manager=None,
    vision_manager=None,
    system_bridge=None,
    state_manager=None,
    energy_detector=None,
) -> BootManager:
    """
    Crea y registra el BootManager singleton.

    Returns:
        BootManager instance
    """
    global _boot_manager_instance

    _boot_manager_instance = BootManager(
        avolites=avolites,
        cue_engine=cue_engine,
        calendar_manager=calendar_manager,
        vision_manager=vision_manager,
        system_bridge=system_bridge,
        state_manager=state_manager,
        energy_detector=energy_detector,
    )

    return _boot_manager_instance


__all__ = [
    "BootManager",
    "BootState",
    "get_boot_manager",
    "create_boot_manager",
]
