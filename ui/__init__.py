"""
UI Package - 911 Fiesta Vision System PRO
REFACTOR A2: 3 tabs independientes (Haze, DJ, Artist)
Zone Editor PRO: LayeredZoneEditor profesional tipo Resolume
"""
from .vision_haze_tab import VisionHazeTab
from .vision_dj_tab import VisionDJTab
from .vision_artist_tab import VisionArtistTab
from .vision_config_widget import VisionConfigWidget
from .layered_zone_editor import LayeredZoneEditor

__all__ = [
    "VisionHazeTab",
    "VisionDJTab",
    "VisionArtistTab",
    "VisionConfigWidget",
    "LayeredZoneEditor"
]
