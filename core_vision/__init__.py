"""
core_vision - Vision System PRO - Phase 9.0
Sistema completo de visión integrado con FamilyManager

V9 VISION DJ:
- VisionDJEngine: Multi-zone state machine with YOLO ROI-only detection
- YoloRoiDetector: YOLO-based person detection on ROI only (not full frame)
- Non-blocking cue firing via event queue

CUES CANÓNICOS:
Para constantes de cues, usar core.cues:
    from core.cues import CUE_HAZE_LOW, CUE_DJ_1, CUE_ARTIST_T1, etc.

Los detectores usan FamilyManager para activación exclusiva vía cue_map canónico.
"""
from .vision_manager import VisionManager
from .vision_state import VisionState
from .vision_config import VisionConfig
from .camera_haze import HazeDetector
from .dj_detector import DJDetector
from .vision_dj_engine import VisionDJEngine, ZoneConfig, ZoneState, EngineConfig
from .yolo_roi_detector import YoloRoiDetector, DetectorConfig
from .camera_tracking import ArtistTracker
from .camera_loop import CameraLoop

__all__ = [
    "VisionManager",
    "VisionState",
    "VisionConfig",
    "HazeDetector",
    "DJDetector",
    "VisionDJEngine",
    "ZoneConfig",
    "ZoneState",
    "EngineConfig",
    "YoloRoiDetector",
    "DetectorConfig",
    "ArtistTracker",
    "CameraLoop",
]

__version__ = "9.0.0"
__author__ = "911 Fiesta Team"
