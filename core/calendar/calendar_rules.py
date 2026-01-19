# core/calendar/calendar_rules.py
"""
CalendarRules v6.4 - Contrato canónico de módulos por modo.

El calendario NO ejecuta nada. Solo indica qué módulos están activos.
Todo lo que no esté listado como True → OFF.

MÓDULOS (única lista real):
- audio_engine:    Motor 911 completo (base_golpe, bajada, ataque, brake)
- vision_haze:     Familia de cues de haze
- vision_dj:       Familia de cues DJ
- vision_artista:  Familia de cues artista
- tracking_cam:    Tracking por cámaras
- dj_detection:    Detección de DJ
- cues_clima:      Familia de cues clima (clima_1 a clima_4)
- system_idle:     Sistema en standby (apagado lógico)

MODOS SEMÁNTICOS:
Los modos son etiquetas de contexto/UX. La lógica real la definen los módulos.
"""

from typing import Dict, Any, List, Optional


# ==================== MÓDULOS CANÓNICOS ====================
# Única lista de módulos que el calendario puede controlar

CANONICAL_MODULES = [
    "audio_engine",
    "vision_haze",
    "vision_dj",
    "vision_artista",
    "tracking_cam",
    "dj_detection",
    "cues_clima",
    "system_idle",
]


# ==================== MODOS CANÓNICOS ====================

CANONICAL_MODES = [
    "clima_1",
    "clima_2",
    "clima_3",
    "clima_4",
    "teatro",
    "artista",
    "boliche_inicio",
    "boliche_desarrollo",
    "boliche_fin",
    "apagado",
]


# ==================== REGLAS POR MODO ====================
# Cada modo declara TODOS los módulos (True/False)

CALENDAR_RULES: Dict[str, Dict[str, bool]] = {

    # ================== CLIMAS ==================
    # Solo cues_clima activo

    "clima_1": {
        "audio_engine": False,
        "vision_haze": False,
        "vision_dj": False,
        "vision_artista": False,
        "tracking_cam": False,
        "dj_detection": False,
        "cues_clima": True,
        "system_idle": False,
    },

    "clima_2": {
        "audio_engine": False,
        "vision_haze": False,
        "vision_dj": False,
        "vision_artista": False,
        "tracking_cam": False,
        "dj_detection": False,
        "cues_clima": True,
        "system_idle": False,
    },

    "clima_3": {
        "audio_engine": False,
        "vision_haze": False,
        "vision_dj": False,
        "vision_artista": False,
        "tracking_cam": False,
        "dj_detection": False,
        "cues_clima": True,
        "system_idle": False,
    },

    "clima_4": {
        "audio_engine": False,
        "vision_haze": False,
        "vision_dj": False,
        "vision_artista": False,
        "tracking_cam": False,
        "dj_detection": False,
        "cues_clima": True,
        "system_idle": False,
    },

    # ================== TEATRO ==================
    # Tracking de artista, detección DJ, visión artista

    "teatro": {
        "audio_engine": False,
        "vision_haze": False,
        "vision_dj": False,
        "vision_artista": True,
        "tracking_cam": True,
        "dj_detection": True,
        "cues_clima": False,
        "system_idle": False,
    },

    # ================== ARTISTA ==================
    # Similar a teatro, enfocado en artista

    "artista": {
        "audio_engine": False,
        "vision_haze": False,
        "vision_dj": False,
        "vision_artista": True,
        "tracking_cam": True,
        "dj_detection": False,
        "cues_clima": False,
        "system_idle": False,
    },

    # ================== BOLICHE ==================

    # boliche_inicio: Audio suave (solo bajada + basegolpe via state gating)
    "boliche_inicio": {
        "audio_engine": True,
        "vision_haze": False,
        "vision_dj": False,
        "vision_artista": False,
        "tracking_cam": False,
        "dj_detection": False,
        "cues_clima": False,
        "system_idle": False,
    },

    # boliche_desarrollo: Audio completo + haze + DJ
    "boliche_desarrollo": {
        "audio_engine": True,
        "vision_haze": True,
        "vision_dj": True,
        "vision_artista": False,
        "tracking_cam": False,
        "dj_detection": False,
        "cues_clima": False,
        "system_idle": False,
    },

    # boliche_fin: Audio suave (solo bajada + basegolpe via state gating)
    "boliche_fin": {
        "audio_engine": True,
        "vision_haze": False,
        "vision_dj": False,
        "vision_artista": False,
        "tracking_cam": False,
        "dj_detection": False,
        "cues_clima": False,
        "system_idle": False,
    },

    # ================== APAGADO ==================
    # Solo system_idle activo

    "apagado": {
        "audio_engine": False,
        "vision_haze": False,
        "vision_dj": False,
        "vision_artista": False,
        "tracking_cam": False,
        "dj_detection": False,
        "cues_clima": False,
        "system_idle": True,
    },
}


# ==================== ALIASES ====================

MODE_ALIASES: Dict[str, str] = {
    "off": "apagado",
    "OFF": "apagado",
    "boliche": "boliche_fin",
    "BOLICHE": "boliche_fin",
    "clima": "clima_1",
    "CLIMA": "clima_1",
    "CLIMA_1": "clima_1",
    "CLIMA_2": "clima_2",
    "CLIMA_3": "clima_3",
    "CLIMA_4": "clima_4",
    "TEATRO": "teatro",
    "ARTISTA": "artista",
    "ESCENA": "artista",
    "escena": "artista",
    "BOLICHE_INICIO": "boliche_inicio",
    "BOLICHE_DESARROLLO": "boliche_desarrollo",
    "BOLICHE_FIN": "boliche_fin",
}


# ==================== FUNCIONES ====================

def normalize_mode(mode: str) -> str:
    """Normaliza un nombre de modo al canónico."""
    mode_lower = mode.lower()
    if mode_lower in CANONICAL_MODES:
        return mode_lower
    if mode in MODE_ALIASES:
        return MODE_ALIASES[mode]
    print(f"[CalendarRules] WARN: Modo '{mode}' no reconocido, usando 'apagado'")
    return "apagado"


def get_permissions(mode: str) -> Dict[str, bool]:
    """Obtiene los módulos activos para un modo."""
    canonical = normalize_mode(mode)
    return CALENDAR_RULES[canonical].copy()


def get_available_climates() -> List[str]:
    """Retorna lista de modos canónicos."""
    return CANONICAL_MODES.copy()


def is_module_enabled(mode: str, module: str) -> bool:
    """Verifica si un módulo está activo en un modo."""
    perms = get_permissions(mode)
    return perms.get(module, False)


# ==================== COMPATIBILIDAD LEGACY ====================
# Funciones mantenidas para no romper imports existentes


def get_calendar_permissions(mode: str) -> Dict[str, bool]:
    """Alias de get_permissions() para compatibilidad."""
    return get_permissions(mode)

def get_energy_level(mode: str) -> Optional[str]:
    """Legacy: No hay niveles de energía. Retorna None."""
    return None


def get_disabled_states(mode: str) -> List[str]:
    """Legacy: No hay estados deshabilitados. Retorna lista vacía."""
    return []


def is_state_allowed(mode: str, state: str) -> bool:
    """Legacy: Todos los estados permitidos (la lógica está en otro lugar)."""
    return True


def is_permission_enabled(mode: str, permission: str) -> bool:
    """
    Returns True if the given permission/module is enabled for the given calendar mode.

    This is the contract function used by SystemBridge.
    """
    perms = get_permissions(mode)
    return perms.get(permission, False)


# ==================== ACCIONES (v6.4) ====================
# Las acciones SUMAN módulos, nunca restan

ACTION_RULES: Dict[str, Dict[str, Any]] = {
    "cues_clima": {
        "enables": {"cues_clima": True},
        "description": "Habilita familia de cues clima"
    },
    "vision_haze": {
        "enables": {"vision_haze": True},
        "description": "Habilita familia de cues haze"
    },
    "vision_dj": {
        "enables": {"vision_dj": True},
        "description": "Habilita familia de cues DJ"
    },
    "vision_artista": {
        "enables": {"vision_artista": True, "tracking_cam": True},
        "description": "Habilita tracking de artista"
    },
}


def get_action_permissions(action: str) -> Dict[str, bool]:
    """Obtiene los módulos que una acción habilita."""
    if action not in ACTION_RULES:
        return {}
    return ACTION_RULES[action].get("enables", {}).copy()


def merge_permissions_with_actions(base_permissions: Dict[str, bool], actions: List[str]) -> Dict[str, bool]:
    """
    Combina módulos del modo base con acciones.
    Las acciones SUMAN (True), nunca restan.
    """
    result = base_permissions.copy()
    for action in actions:
        action_perms = get_action_permissions(action)
        for module, enabled in action_perms.items():
            if enabled:
                result[module] = True
    return result
