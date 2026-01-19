# core/calendar/__init__.py
"""
Calendar Core v6.4 - Sistema de Gobierno Contextual Completo

El calendario es la otra mitad de la inteligencia del sistema:
- La musical decide QUE hacer
- El calendario decide CUANDO y SI hacerlo

MODOS CANONICOS:
- clima_1, clima_2, clima_3, clima_4: Niveles de ambiente
- teatro: Modo espectáculo/teatro
- artista: Modo con artista en escena
- boliche_inicio, boliche_desarrollo, boliche_fin: Fases de fiesta
- apagado: Sistema completamente deshabilitado

Componentes:
- CalendarManager: Gestor principal con GO, override, alertas
- CalendarState: Estado del calendario con timeline y permisos
- CalendarResolver: Resolucion de horarios desde calendar.json
- CalendarRules: Permisos por clima

Uso basico:
    from core.calendar import CalendarManager, OverrideType

    calendar = CalendarManager()

    # Leer estado
    state = calendar.get_state()
    permissions = calendar.get_permissions()

    # GO manual
    calendar.go("boliche_fin")

    # GO con delay de 5 minutos
    calendar.go("artista", delay_minutes=5)

    # Override temporal de 30 minutos
    calendar.set_override("artista", OverrideType.TEMPORARY, 30)

    # Verificar permisos
    if calendar.is_permitted("audio"):
        pass  # El sistema puede usar audio reactivo

    # Verificar si un estado de CueEngine esta permitido
    if calendar.is_state_allowed("ATAQUE"):
        pass  # El estado ATAQUE esta permitido
"""

from .calendar_manager import (
    CalendarManager,
    OverrideType,
    OverrideState,
    UpcomingAlert,
    PendingGo
)
from .calendar_state import (
    CalendarState,
    CalendarSource,
    ScheduleBlock,
    PermissionState,
    OverrideInfo
)
from .calendar_resolver import CalendarResolver
from .calendar_rules import (
    get_permissions,
    get_available_climates,
    is_permission_enabled,
    normalize_mode,
    get_energy_level,
    get_disabled_states,
    is_state_allowed,
    CALENDAR_RULES,
    CANONICAL_MODES,
    MODE_ALIASES
)

# ==================== GLOBAL CALENDAR MANAGER INSTANCE ====================

_calendar_manager_instance: CalendarManager = None


def set_calendar_manager(calendar_manager: CalendarManager) -> None:
    """
    Establece la instancia global del CalendarManager.

    Esto permite que otros módulos accedan al calendario sin
    necesidad de pasar la referencia explícitamente.

    Args:
        calendar_manager: Instancia de CalendarManager
    """
    global _calendar_manager_instance
    _calendar_manager_instance = calendar_manager
    print("[Calendar] CalendarManager global establecido")


def get_calendar_manager() -> CalendarManager:
    """
    Obtiene la instancia global del CalendarManager.

    Returns:
        CalendarManager: Instancia global o None si no está establecida
    """
    return _calendar_manager_instance


__all__ = [
    # Manager principal
    "CalendarManager",

    # Override
    "OverrideType",
    "OverrideState",
    "UpcomingAlert",
    "PendingGo",

    # Estado
    "CalendarState",
    "CalendarSource",
    "ScheduleBlock",
    "PermissionState",
    "OverrideInfo",

    # Resolver
    "CalendarResolver",

    # Reglas
    "get_permissions",
    "get_available_climates",
    "is_permission_enabled",
    "normalize_mode",
    "get_energy_level",
    "get_disabled_states",
    "is_state_allowed",
    "CALENDAR_RULES",
    "CANONICAL_MODES",
    "MODE_ALIASES",

    # Global instance
    "set_calendar_manager",
    "get_calendar_manager",
]
