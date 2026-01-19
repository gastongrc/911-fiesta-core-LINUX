# core/cues/cue_map.py
"""
Cue Map v6.4 - Canonical Continuous Cue Assignments C60-C82

SINGLE SOURCE OF TRUTH para asignación de cues.
Ningún número mágico suelto - todo lee de aquí.

MAPA CANÓNICO CONTINUO:
┌────────────┬─────────┬───────────────────────┐
│ FAMILIA    │ RANGO   │ ESTADOS               │
├────────────┼─────────┼───────────────────────┤
│ CLIMA      │ C60-C63 │ clima_1..clima_4      │
│ HAZE       │ C64-C66 │ LOW, MID, HIGH        │
│ DJ         │ C67-C71 │ dj_1..dj_5            │
│ ARTIST     │ C72-C79 │ T1..T8                │
│ TRACKING   │ C80-C82 │ idle, follow, focus   │
└────────────┴─────────┴───────────────────────┘

USO:
    from core.cues import CUE_CLIMA_1, CLIMA_CUE_MAP, get_cue_for_state

SEMÁNTICA ON/OFF:
    - Una sola cue activa por familia a la vez
    - Al cambiar estado: kill previos, fire nuevo
    - Al deshabilitar familia: kill todos
"""

from typing import Dict, List, Optional, Tuple

# =============================================================================
# FAMILIA CLIMA (C60-C63)
# =============================================================================

CUE_CLIMA_1 = 60
CUE_CLIMA_2 = 61
CUE_CLIMA_3 = 62
CUE_CLIMA_4 = 63

FAMILIA_CLIMA = "CLIMA"

CLIMA_STATES = ["clima_1", "clima_2", "clima_3", "clima_4"]

CLIMA_CUE_MAP: Dict[str, int] = {
    "clima_1": CUE_CLIMA_1,
    "clima_2": CUE_CLIMA_2,
    "clima_3": CUE_CLIMA_3,
    "clima_4": CUE_CLIMA_4,
}

CLIMA_CUE_LIST = [CUE_CLIMA_1, CUE_CLIMA_2, CUE_CLIMA_3, CUE_CLIMA_4]


# =============================================================================
# FAMILIA HAZE (C64-C66)
# =============================================================================

CUE_HAZE_LOW = 64
CUE_HAZE_MID = 65
CUE_HAZE_HIGH = 66

FAMILIA_HAZE = "HAZE"

HAZE_STATES = ["LOW", "MID", "HIGH"]

HAZE_CUE_MAP: Dict[str, int] = {
    "LOW": CUE_HAZE_LOW,
    "MID": CUE_HAZE_MID,
    "MEDIUM": CUE_HAZE_MID,  # Alias para compatibilidad
    "HIGH": CUE_HAZE_HIGH,
}

HAZE_CUE_LIST = [CUE_HAZE_LOW, CUE_HAZE_MID, CUE_HAZE_HIGH]


# =============================================================================
# FAMILIA DJ (C67-C71)
# =============================================================================

CUE_DJ_1 = 67
CUE_DJ_2 = 68
CUE_DJ_3 = 69
CUE_DJ_4 = 70
CUE_DJ_5 = 71

FAMILIA_DJ = "DJ"

DJ_STATES = ["dj_1", "dj_2", "dj_3", "dj_4", "dj_5"]

DJ_CUE_MAP: Dict[str, int] = {
    "dj_1": CUE_DJ_1,
    "dj_2": CUE_DJ_2,
    "dj_3": CUE_DJ_3,
    "dj_4": CUE_DJ_4,
    "dj_5": CUE_DJ_5,
    # Alias numéricos para detectores que usan ints
    1: CUE_DJ_1,
    2: CUE_DJ_2,
    3: CUE_DJ_3,
    4: CUE_DJ_4,
    5: CUE_DJ_5,
}

DJ_CUE_LIST = [CUE_DJ_1, CUE_DJ_2, CUE_DJ_3, CUE_DJ_4, CUE_DJ_5]


# =============================================================================
# FAMILIA ARTIST (C72-C79)
# =============================================================================

CUE_ARTIST_T1 = 72
CUE_ARTIST_T2 = 73
CUE_ARTIST_T3 = 74
CUE_ARTIST_T4 = 75
CUE_ARTIST_T5 = 76
CUE_ARTIST_T6 = 77
CUE_ARTIST_T7 = 78
CUE_ARTIST_T8 = 79

FAMILIA_ARTIST = "ARTIST"

ARTIST_STATES = ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"]

ARTIST_CUE_MAP: Dict[str, int] = {
    "T1": CUE_ARTIST_T1,
    "T2": CUE_ARTIST_T2,
    "T3": CUE_ARTIST_T3,
    "T4": CUE_ARTIST_T4,
    "T5": CUE_ARTIST_T5,
    "T6": CUE_ARTIST_T6,
    "T7": CUE_ARTIST_T7,
    "T8": CUE_ARTIST_T8,
    # Alias numéricos para detectores que usan ints (1-8)
    1: CUE_ARTIST_T1,
    2: CUE_ARTIST_T2,
    3: CUE_ARTIST_T3,
    4: CUE_ARTIST_T4,
    5: CUE_ARTIST_T5,
    6: CUE_ARTIST_T6,
    7: CUE_ARTIST_T7,
    8: CUE_ARTIST_T8,
}

ARTIST_CUE_LIST = [
    CUE_ARTIST_T1, CUE_ARTIST_T2, CUE_ARTIST_T3, CUE_ARTIST_T4,
    CUE_ARTIST_T5, CUE_ARTIST_T6, CUE_ARTIST_T7, CUE_ARTIST_T8,
]


# =============================================================================
# FAMILIA TRACKING (C80-C82)
# =============================================================================

CUE_TRACKING_IDLE = 80
CUE_TRACKING_FOLLOW = 81
CUE_TRACKING_FOCUS = 82

FAMILIA_TRACKING = "TRACKING"

TRACKING_STATES = ["tracking_idle", "tracking_follow", "tracking_focus"]

TRACKING_CUE_MAP: Dict[str, int] = {
    "tracking_idle": CUE_TRACKING_IDLE,
    "tracking_follow": CUE_TRACKING_FOLLOW,
    "tracking_focus": CUE_TRACKING_FOCUS,
    "idle": CUE_TRACKING_IDLE,
    "follow": CUE_TRACKING_FOLLOW,
    "focus": CUE_TRACKING_FOCUS,
}

TRACKING_CUE_LIST = [CUE_TRACKING_IDLE, CUE_TRACKING_FOLLOW, CUE_TRACKING_FOCUS]


# =============================================================================
# MAPAS GLOBALES
# =============================================================================

ALL_FAMILIES = [FAMILIA_CLIMA, FAMILIA_HAZE, FAMILIA_DJ, FAMILIA_ARTIST, FAMILIA_TRACKING]

# Rango extendido de cues por familia (para CuesMonitor y kill_pool)
FAMILY_CUE_RANGES_EXTENDED: Dict[str, List[int]] = {
    FAMILIA_CLIMA: CLIMA_CUE_LIST,
    FAMILIA_HAZE: HAZE_CUE_LIST,
    FAMILIA_DJ: DJ_CUE_LIST,
    FAMILIA_ARTIST: ARTIST_CUE_LIST,
    FAMILIA_TRACKING: TRACKING_CUE_LIST,
}

# Mapa completo: familia → {estado → cue}
FAMILY_STATE_CUE_MAP: Dict[str, Dict] = {
    FAMILIA_CLIMA: CLIMA_CUE_MAP,
    FAMILIA_HAZE: HAZE_CUE_MAP,
    FAMILIA_DJ: DJ_CUE_MAP,
    FAMILIA_ARTIST: ARTIST_CUE_MAP,
    FAMILIA_TRACKING: TRACKING_CUE_MAP,
}

# Mapa inverso: cue → (familia, estado)
CUE_TO_FAMILY_STATE: Dict[int, Tuple[str, str]] = {}

# Construir mapa inverso
for _family, _state_map in [
    (FAMILIA_CLIMA, {"clima_1": 60, "clima_2": 61, "clima_3": 62, "clima_4": 63}),
    (FAMILIA_HAZE, {"LOW": 64, "MID": 65, "HIGH": 66}),
    (FAMILIA_DJ, {"dj_1": 67, "dj_2": 68, "dj_3": 69, "dj_4": 70, "dj_5": 71}),
    (FAMILIA_ARTIST, {"T1": 72, "T2": 73, "T3": 74, "T4": 75, "T5": 76, "T6": 77, "T7": 78, "T8": 79}),
    (FAMILIA_TRACKING, {"idle": 80, "follow": 81, "focus": 82}),
]:
    for _state, _cue in _state_map.items():
        CUE_TO_FAMILY_STATE[_cue] = (_family, _state)


# =============================================================================
# FUNCIONES DE LOOKUP
# =============================================================================

def get_family_cues(family: str) -> List[int]:
    """
    Obtiene la lista de cues de una familia.

    Args:
        family: Nombre de familia (CLIMA, HAZE, DJ, ARTIST, TRACKING)

    Returns:
        Lista de cue IDs de la familia
    """
    return FAMILY_CUE_RANGES_EXTENDED.get(family.upper(), [])


def get_cue_for_state(family: str, state) -> Optional[int]:
    """
    Obtiene el cue correspondiente a un estado en una familia.

    Args:
        family: Nombre de familia
        state: Estado (string o int según familia)

    Returns:
        Cue ID o None si no existe
    """
    family_map = FAMILY_STATE_CUE_MAP.get(family.upper())
    if not family_map:
        return None
    return family_map.get(state)


def get_state_for_cue(cue_id: int) -> Optional[Tuple[str, str]]:
    """
    Obtiene familia y estado para un cue dado.

    Args:
        cue_id: ID del cue

    Returns:
        Tupla (familia, estado) o None
    """
    return CUE_TO_FAMILY_STATE.get(cue_id)


def get_all_extended_cues() -> List[int]:
    """
    Obtiene la lista completa de cues extendidos (C60-C82).

    Returns:
        Lista ordenada de todos los cue IDs
    """
    return list(range(60, 83))
