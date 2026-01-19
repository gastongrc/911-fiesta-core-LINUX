"""
Core System - Phase 6.6
Includes Vision System, Titan Transport, Calendar, and System Bridge
"""
from .vision_router import VisionRouter
from .camera_manager import CameraManager
from .smart_camera import SmartCamera

# Titan Transport System
from .transport import (
    TitanTransport,
    TransportConfig,
    TitanQueue,
    QueueConfig,
    TitanStateSync,
    SyncConfig,
)

# System Bridge - Calendar → System governance
try:
    from .system_bridge import SystemBridge, get_system_bridge, reset_system_bridge
    SYSTEM_BRIDGE_AVAILABLE = True
except ImportError as e:
    SYSTEM_BRIDGE_AVAILABLE = False
    SystemBridge = None
    get_system_bridge = None
    reset_system_bridge = None
    print(f"[Core] SystemBridge no disponible: {e}")

__all__ = [
    # Vision
    'VisionRouter',
    'CameraManager',
    'SmartCamera',
    # Transport
    'TitanTransport',
    'TransportConfig',
    'TitanQueue',
    'QueueConfig',
    'TitanStateSync',
    'SyncConfig',
    # System Bridge
    'SystemBridge',
    'get_system_bridge',
    'reset_system_bridge',
    'SYSTEM_BRIDGE_AVAILABLE',
]
