# core/system_bridge.py
"""
SystemBridge v6.8 - Calendar → System Bridge (Hard Governance)

Punto ÚNICO de gobierno entre el calendario y el sistema.
Cuando el calendario cambia de modo, el SystemBridge aplica
los módulos activos de calendar_rules.py a todos los componentes.

PRINCIPIO FUNDAMENTAL:
El calendario GOBIERNA los módulos directamente.
El calendario decide SI ESTÁN ACTIVOS O NO.

V6.8 FIX (Hard Governance):
- Teardown explícito en transiciones: log de módulos enable/disable
- ZZZ state (apagado) cuando no hay bloque activo
- Transición A→B muestra qué módulos se apagan/encienden
- Log format: [SystemBridge] disable: x, y / enable: z

V6.7 FIX:
- Calendar GOVERNS modules directly (not permission gate)
- When calendar ALLOWS → module ON (ignores user preference)
- When calendar DISALLOWS → module OFF (forced)
- persist=False ensures user preferences in config are preserved

FUENTE DE VERDAD ÚNICA: core/calendar/calendar_rules.py

MÓDULOS CANÓNICOS (los únicos que existen):
- audio_engine:    Motor 911 completo (base_golpe, bajada, ataque, brake)
- vision_haze:     Familia de cues de haze
- vision_dj:       Familia de cues DJ
- vision_artista:  Familia de cues artista
- tracking_cam:    Tracking por cámaras
- dj_detection:    Detección de DJ
- cues_clima:      Familia de cues clima (clima_1 a clima_4)
- system_idle:     Sistema en standby (apagado lógico)

NO HACE:
- Ejecutar cues directamente
- Disparar escenas
- Manejar "energy levels"
- Manejar "disabled states"
"""

from typing import Optional, Dict, Any, List, TYPE_CHECKING
from datetime import datetime

from .calendar.calendar_rules import (
    get_permissions,
    normalize_mode,
    merge_permissions_with_actions,
    get_action_permissions,
    CANONICAL_MODES,
    CALENDAR_RULES,
    ACTION_RULES,
    CANONICAL_MODULES,
)

# Importar mapa canónico de cues para CLIMA
from .cues import (
    FAMILIA_CLIMA,
    CLIMA_CUE_MAP,
    FamilyManager,
)

if TYPE_CHECKING:
    from cue_engine import CueEngine


class SystemBridge:
    """
    Puente único entre CalendarManager y el sistema.

    Uso:
        system_bridge = get_system_bridge()
        calendar_manager = CalendarManager(system_bridge=system_bridge)

        # Conectar componentes:
        system_bridge.connect_vision_manager(vision_manager)
        system_bridge.connect_audio_engine(audio_engine)

    CalendarManager llama apply_calendar_state() cuando cambia el estado.
    El bridge activa/desactiva módulos según calendar_rules.py.
    """

    def __init__(self):
        """Inicializa el SystemBridge."""
        # Referencias a componentes (set via connect_*)
        self._vision_manager = None
        self._audio_engine = None
        self._audio_callback = None  # Legacy: audio processor callback
        self._cue_engine = None  # Legacy: CueEngine reference
        self._avolites = None  # Avolites controller for FamilyManager

        # FamilyManager para cues ON/OFF por familia (C60-C82)
        self._family_manager: Optional[FamilyManager] = None

        # Estado actual aplicado
        self._current_mode: str = "apagado"
        self._current_actions: List[str] = []
        self._current_modules: Dict[str, bool] = {}
        self._last_applied_at: Optional[datetime] = None

        # Modo simulador (no ejecuta acciones reales)
        self._simulator_mode: bool = False

        # Logging
        self._log_changes: bool = True

        print("[SystemBridge] v6.7 - Calendar GOVERNS modules directly")

    # ==================== CONEXIONES ====================

    def connect_vision_manager(self, vision_manager) -> None:
        """Conecta el VisionManager para control de visión."""
        self._vision_manager = vision_manager
        print("[SystemBridge] VisionManager connected")

        # Wire FamilyManager to VisionManager if available
        if self._family_manager and hasattr(vision_manager, 'set_family_manager'):
            vision_manager.set_family_manager(self._family_manager)
            print("[SystemBridge] FamilyManager wired to VisionManager detectors")

        if self._current_mode:
            self._sync_vision()

    def connect_audio_engine(self, audio_engine) -> None:
        """Conecta el AudioEngine para control de audio."""
        self._audio_engine = audio_engine
        print("[SystemBridge] AudioEngine connected")
        if self._current_mode:
            self._sync_audio()

    # ==================== LEGACY COMPATIBILITY ====================

    def connect_cue_engine(self, cue_engine) -> None:
        """Conecta CueEngine para control de estados por calendario."""
        self._cue_engine = cue_engine
        print("[SystemBridge] CueEngine connected")

        # Obtener referencia a Avolites desde CueEngine
        if hasattr(cue_engine, 'av') and cue_engine.av:
            self.connect_avolites(cue_engine.av)

        # ✅ FIX: Sincronizar usando _apply_modules (respeta modo boliche)
        # NO usar set_disabled_states directo que ignora el modo actual
        if self._current_modules:
            self._apply_modules(self._current_modules)

    def connect_avolites(self, avolites) -> None:
        """Conecta Avolites controller para FamilyManager."""
        self._avolites = avolites
        self._family_manager = FamilyManager(avolites)
        print("[SystemBridge] Avolites + FamilyManager connected")

        # Wire CueEngine to FamilyManager for unified pipeline
        if self._cue_engine and hasattr(self._family_manager, 'set_cue_engine'):
            self._family_manager.set_cue_engine(self._cue_engine)
            print("[SystemBridge] FamilyManager wired to CueEngine (unified pipeline)")

        # Wire FamilyManager to VisionManager if already connected
        if self._vision_manager and hasattr(self._vision_manager, 'set_family_manager'):
            self._vision_manager.set_family_manager(self._family_manager)
            print("[SystemBridge] FamilyManager wired to VisionManager detectors")

    def connect_audio_processor(self, callback) -> None:
        """Legacy: Conecta callback para habilitar/deshabilitar audio."""
        self._audio_callback = callback
        print("[SystemBridge] Audio processor connected (legacy)")
        if self._current_mode:
            self._sync_audio()

    # ==================== API PÚBLICA ====================

    def apply_calendar_state(self, base_mode: str, actions: Optional[List[str]] = None) -> None:
        """
        Aplica el estado del calendario: base_mode + actions.

        ÚNICO punto de entrada. CalendarManager debe llamar este método
        UNA VEZ por cambio de estado.

        V6.8: Teardown explícito - log de módulos que se desactivan.

        Args:
            base_mode: Modo canónico (ej: "boliche_desarrollo")
            actions: Acciones paralelas activas (ej: ["vision_dj"])
        """
        actions = actions or []

        # Obtener módulos activos desde la fuente de verdad
        base_modules = get_permissions(base_mode)
        modules = merge_permissions_with_actions(base_modules, actions)

        # Log canónico
        if self._log_changes:
            actions_str = f" + {actions}" if actions else ""
            print(f"[SystemBridge] applying: {base_mode}{actions_str}")

        # V6.8: Log de transición (teardown explícito)
        if self._log_changes and self._current_modules:
            old_active = {m for m, v in self._current_modules.items() if v}
            new_active = {m for m, v in modules.items() if v}

            # Módulos que se desactivan
            turning_off = old_active - new_active
            if turning_off:
                print(f"[SystemBridge] disable: {', '.join(sorted(turning_off))}")

            # Módulos que se activan
            turning_on = new_active - old_active
            if turning_on:
                print(f"[SystemBridge] enable: {', '.join(sorted(turning_on))}")

        # ✅ FIX: Guardar estado ANTES de _apply_modules para que el gating use el modo correcto
        self._current_mode = normalize_mode(base_mode)
        self._current_actions = actions.copy()
        self._current_modules = modules.copy()
        self._last_applied_at = datetime.now()

        # Aplicar módulos (ahora _current_mode ya tiene el valor correcto)
        self._apply_modules(modules)

        # Log resumen
        if self._log_changes:
            active = [m for m, v in modules.items() if v]
            if active:
                print(f"[SystemBridge] active: {', '.join(active)}")
            else:
                print("[SystemBridge] active: (none) - ZZZ state")

    def _apply_modules(self, modules: Dict[str, bool]) -> None:
        """Aplica los módulos activos a los componentes conectados."""
        if self._simulator_mode:
            print(f"[SystemBridge] [SIM] modules: {modules}")
            return

        # Audio Engine
        audio_on = modules.get("audio_engine", False)

        # ✅ Log diagnóstico mínimo
        print(f"[SystemBridge] _apply_modules mode={self._current_mode} audio={audio_on}")

        if self._audio_engine and hasattr(self._audio_engine, 'set_enabled'):
            self._audio_engine.set_enabled(audio_on)
        # Legacy audio callback
        if self._audio_callback:
            try:
                self._audio_callback(audio_on)
            except Exception:
                pass

        # CueEngine gating: Controlar qué estados musicales están permitidos
        if self._cue_engine and hasattr(self._cue_engine, 'set_disabled_states'):
            if not audio_on:
                # Audio deshabilitado: bloquear todos los estados
                self._cue_engine.set_disabled_states(["ALL"])
            elif self._current_mode in ("boliche_inicio", "boliche_fin"):
                # Audio suave: BAJADA + BASE_GOLPE + MOVIMIENTO permitidos (sin ATAQUE, BRAKE)
                disabled = ["ATAQUE", "BRAKE"]
                self._cue_engine.set_disabled_states(disabled)
                print(f"[SystemBridge] GATING boliche -> disabled={disabled}")
            else:
                # Audio completo: todos los estados permitidos
                self._cue_engine.set_disabled_states([])

        # Vision Manager - cada módulo de visión
        if self._vision_manager:
            vm = self._vision_manager

            if hasattr(vm, 'enable_module'):
                # V6.7 FIX: Calendar GOVERNS modules directly
                # - Calendar ALLOWS → module ON (calendar overrides user preference)
                # - Calendar DISALLOWS → module OFF (forced)
                # persist=False ensures user preferences in config are preserved

                # HAZE: Calendar governs directly
                haze_allowed = modules.get("vision_haze", False)
                vm.enable_module("haze", haze_allowed, source="calendar", persist=False)
                print(f"[CALENDAR] haze={'ON' if haze_allowed else 'OFF'} ({'allowed' if haze_allowed else 'disallowed'})")

                # DJ: Calendar governs directly (vision_dj OR dj_detection)
                dj_allowed = modules.get("vision_dj", False) or modules.get("dj_detection", False)
                vm.enable_module("dj", dj_allowed, source="calendar", persist=False)
                print(f"[CALENDAR] dj={'ON' if dj_allowed else 'OFF'} ({'allowed' if dj_allowed else 'disallowed'})")

                # ARTIST/TRACKING: Calendar governs directly (vision_artista OR tracking_cam)
                tracking_allowed = modules.get("vision_artista", False) or modules.get("tracking_cam", False)
                vm.enable_module("tracking", tracking_allowed, source="calendar", persist=False)
                print(f"[CALENDAR] artist={'ON' if tracking_allowed else 'OFF'} ({'allowed' if tracking_allowed else 'disallowed'})")

            if hasattr(vm, 'set_calendar_mode'):
                vm.set_calendar_mode(self._map_to_vision_mode(self._current_mode))

        # ==================== CUES CLIMA (C60-C63) ====================
        # Si cues_clima está activo, activar el cue correspondiente al modo
        self._apply_clima_cues(modules.get("cues_clima", False))

    def _sync_vision(self) -> None:
        """Sincroniza VisionManager con el estado actual."""
        if self._current_modules:
            self._apply_modules(self._current_modules)

    def _sync_audio(self) -> None:
        """Sincroniza AudioEngine con el estado actual."""
        if self._current_modules:
            audio_on = self._current_modules.get("audio_engine", False)
            # New API
            if self._audio_engine and hasattr(self._audio_engine, 'set_enabled'):
                self._audio_engine.set_enabled(audio_on)
            # Legacy callback
            if self._audio_callback:
                try:
                    self._audio_callback(audio_on)
                except Exception:
                    pass

    def _map_to_vision_mode(self, canonical_mode: str) -> str:
        """Mapea modo canónico a modo de VisionManager."""
        mode_map = {
            "clima_1": "CLIMA",
            "clima_2": "CLIMA",
            "clima_3": "CLIMA",
            "clima_4": "CLIMA",
            "teatro": "TEATRO",
            "artista": "ARTISTA",
            "boliche_inicio": "BOLICHE",
            "boliche_desarrollo": "BOLICHE",
            "boliche_fin": "BOLICHE",
            "apagado": "OFF",
        }
        return mode_map.get(canonical_mode, "OFF")

    def _apply_clima_cues(self, cues_clima_active: bool) -> None:
        """
        Aplica cues de CLIMA (C60-C63) según el modo actual.

        Si cues_clima está activo Y estamos en un modo clima_x:
        - Activa el cue correspondiente (C60-C63)
        - Desactiva los demás cues de la familia

        Si cues_clima está inactivo:
        - Desactiva todos los cues de la familia CLIMA
        """
        if not self._family_manager:
            return  # Sin FamilyManager, no hay nada que hacer

        if cues_clima_active and self._current_mode in CLIMA_CUE_MAP:
            # Modo clima activo: activar cue correspondiente
            self._family_manager.activate_state(FAMILIA_CLIMA, self._current_mode)
        else:
            # Fuera de modo clima o clima deshabilitado: todo OFF
            self._family_manager.deactivate_family(FAMILIA_CLIMA)

    # ==================== GETTERS ====================

    def get_current_mode(self) -> str:
        """Obtiene el modo actual."""
        return self._current_mode

    def get_current_actions(self) -> List[str]:
        """Obtiene las acciones activas."""
        return self._current_actions.copy()

    def get_current_modules(self) -> Dict[str, bool]:
        """Obtiene los módulos activos."""
        return self._current_modules.copy()

    def is_module_active(self, module: str) -> bool:
        """Verifica si un módulo está activo."""
        return self._current_modules.get(module, False)

    def is_idle(self) -> bool:
        """Verifica si el sistema está en idle."""
        return self._current_modules.get("system_idle", False)

    def get_family_manager(self) -> Optional[FamilyManager]:
        """Obtiene el FamilyManager para consultas de cues activos."""
        return self._family_manager

    # ==================== CONFIGURACIÓN ====================

    def set_simulator_mode(self, enabled: bool) -> None:
        """Activa/desactiva el modo simulador."""
        self._simulator_mode = enabled
        print(f"[SystemBridge] simulator: {'ON' if enabled else 'OFF'}")

    def set_logging(self, enabled: bool) -> None:
        """Activa/desactiva el logging."""
        self._log_changes = enabled

    def force_apply(self, base_mode: Optional[str] = None, actions: Optional[List[str]] = None) -> None:
        """Fuerza reaplicación de estado."""
        mode = base_mode or self._current_mode or "apagado"
        acts = actions if actions is not None else self._current_actions
        if self._log_changes:
            print(f"[SystemBridge] force apply: {mode}")
        self.apply_calendar_state(mode, acts)

    # ==================== DEBUG ====================

    def get_status(self) -> Dict[str, Any]:
        """Obtiene el estado completo para debugging."""
        return {
            "mode": self._current_mode,
            "actions": self._current_actions.copy(),
            "modules": self._current_modules.copy(),
            "active_modules": [m for m, v in self._current_modules.items() if v],
            "last_applied": self._last_applied_at.isoformat() if self._last_applied_at else None,
            "simulator": self._simulator_mode,
            "connections": {
                "vision_manager": self._vision_manager is not None,
                "audio_engine": self._audio_engine is not None,
            }
        }


# ==================== SINGLETON ====================

_bridge_instance: Optional[SystemBridge] = None


def get_system_bridge() -> SystemBridge:
    """Obtiene la instancia singleton del SystemBridge."""
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = SystemBridge()
    return _bridge_instance


def reset_system_bridge() -> None:
    """Resetea la instancia singleton (para testing)."""
    global _bridge_instance
    _bridge_instance = None
