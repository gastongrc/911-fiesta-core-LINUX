# core/cues/__init__.py
"""
Cue System v6.4 - Canonical Cue Map and Family Management

Single source of truth for cue assignments C60-C82.
All specialists and monitors read from this module.
"""

from .cue_map import (
    # Familia CLIMA
    CUE_CLIMA_1, CUE_CLIMA_2, CUE_CLIMA_3, CUE_CLIMA_4,
    FAMILIA_CLIMA, CLIMA_STATES, CLIMA_CUE_MAP,

    # Familia HAZE
    CUE_HAZE_LOW, CUE_HAZE_MID, CUE_HAZE_HIGH,
    FAMILIA_HAZE, HAZE_STATES, HAZE_CUE_MAP,

    # Familia DJ
    CUE_DJ_1, CUE_DJ_2, CUE_DJ_3, CUE_DJ_4, CUE_DJ_5,
    FAMILIA_DJ, DJ_STATES, DJ_CUE_MAP,

    # Familia ARTIST
    CUE_ARTIST_T1, CUE_ARTIST_T2, CUE_ARTIST_T3, CUE_ARTIST_T4,
    CUE_ARTIST_T5, CUE_ARTIST_T6, CUE_ARTIST_T7, CUE_ARTIST_T8,
    FAMILIA_ARTIST, ARTIST_STATES, ARTIST_CUE_MAP,

    # Familia TRACKING
    CUE_TRACKING_IDLE, CUE_TRACKING_FOLLOW, CUE_TRACKING_FOCUS,
    FAMILIA_TRACKING, TRACKING_STATES, TRACKING_CUE_MAP,

    # Mapas globales
    FAMILY_CUE_RANGES_EXTENDED,
    ALL_FAMILIES,
    get_family_cues,
    get_cue_for_state,
    get_state_for_cue,
)

from .family_manager import FamilyManager

__all__ = [
    # Constants
    "CUE_CLIMA_1", "CUE_CLIMA_2", "CUE_CLIMA_3", "CUE_CLIMA_4",
    "CUE_HAZE_LOW", "CUE_HAZE_MID", "CUE_HAZE_HIGH",
    "CUE_DJ_1", "CUE_DJ_2", "CUE_DJ_3", "CUE_DJ_4", "CUE_DJ_5",
    "CUE_ARTIST_T1", "CUE_ARTIST_T2", "CUE_ARTIST_T3", "CUE_ARTIST_T4",
    "CUE_ARTIST_T5", "CUE_ARTIST_T6", "CUE_ARTIST_T7", "CUE_ARTIST_T8",
    "CUE_TRACKING_IDLE", "CUE_TRACKING_FOLLOW", "CUE_TRACKING_FOCUS",

    # Familias
    "FAMILIA_CLIMA", "FAMILIA_HAZE", "FAMILIA_DJ", "FAMILIA_ARTIST", "FAMILIA_TRACKING",

    # Mapas
    "CLIMA_CUE_MAP", "HAZE_CUE_MAP", "DJ_CUE_MAP", "ARTIST_CUE_MAP", "TRACKING_CUE_MAP",
    "FAMILY_CUE_RANGES_EXTENDED", "ALL_FAMILIES",

    # Funciones
    "get_family_cues", "get_cue_for_state", "get_state_for_cue",

    # Manager
    "FamilyManager",
]
