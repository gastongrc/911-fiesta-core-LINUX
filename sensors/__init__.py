"""
Vision Sensors - Phase 6.6
Sensores especializados para procesamiento de video
"""
from .camera_people import CameraPeopleSensor
from .camera_haze import CameraHazeSensor
from .camera_tracking import CameraTrackingSensor
from .vision_diagnostics import VisionDiagnostics

__all__ = ['CameraPeopleSensor', 'CameraHazeSensor', 'CameraTrackingSensor', 'VisionDiagnostics']
