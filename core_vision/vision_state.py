"""
VisionState PRO - Phase 6.10
Thread-safe state management para Vision System
Almacena: FPS, haze, DJ zones, artist tracking, flags ON/OFF
Note: camera_index DEPRECATED (USB removed in Phase 6.10)
"""
import threading
import time
from typing import Optional, Dict, Any


class VisionState:
    """
    Estado thread-safe del Vision System PRO.

    Responsabilidades:
    - Mantener estado de FPS
    - Haze level, baseline, contraste, estado
    - DJ zone actual, estado del módulo
    - Artist tracking: zona actual (1-8)
    - Flags ON/OFF de cada módulo
    - Cámara activa
    - Módulo general ON/OFF
    """

    def __init__(self):
        """Inicializa el estado con valores por defecto."""
        self.lock = threading.RLock()

        # Estado del sistema
        self.system_enabled = False
        self.camera_index = 0
        self.fps = 0.0
        self.last_frame_time = None

        # Estado Haze
        self.haze_enabled = True
        self.haze_level = 0.0
        self.haze_baseline = 0.0
        self.haze_contrast = 0.0
        self.haze_state = "LOW"  # LOW, MEDIUM, HIGH
        self.haze_status = "READY"  # READY, SHOOTING, COOLDOWN
        self.haze_cooldown_until = 0.0
        self.haze_last_fire = 0.0

        # Estado DJ Detector
        self.dj_enabled = False
        self.dj_active_zone = None  # 1-5 o None
        self.dj_state = "disabled"  # disabled, idle, active
        self.dj_last_seen = None
        self.dj_zones_count = 1

        # Estado Artist Tracker
        self.tracking_enabled = False
        self.tracking_zone = None  # 1-8 o None
        self.tracking_state = "disabled"  # disabled, idle, tracking
        self.tracking_last_seen = None

    # ===== GETTERS THREAD-SAFE =====

    def get_fps(self) -> float:
        """Obtiene FPS actual."""
        with self.lock:
            return self.fps

    def get_camera_index(self) -> int:
        """Obtiene índice de cámara activa."""
        with self.lock:
            return self.camera_index

    def is_system_enabled(self) -> bool:
        """Verifica si el sistema está habilitado."""
        with self.lock:
            return self.system_enabled

    # ----- HAZE -----

    def get_haze_state(self) -> Dict[str, Any]:
        """Obtiene estado completo de haze."""
        with self.lock:
            return {
                "enabled": self.haze_enabled,
                "level": self.haze_level,
                "baseline": self.haze_baseline,
                "contrast": self.haze_contrast,
                "state": self.haze_state,
                "status": self.haze_status,
                "cooldown_remaining": max(0, self.haze_cooldown_until - time.time()),
                "last_fire": self.haze_last_fire,
            }

    def update_haze(
        self,
        level: Optional[float] = None,
        baseline: Optional[float] = None,
        contrast: Optional[float] = None,
        state: Optional[str] = None,
    ):
        """Actualiza estado de haze."""
        with self.lock:
            if level is not None:
                self.haze_level = level
            if baseline is not None:
                self.haze_baseline = baseline
            if contrast is not None:
                self.haze_contrast = contrast
            if state is not None:
                self.haze_state = state

    def set_haze_status(self, status: str):
        """Establece estado de haze (READY/SHOOTING/COOLDOWN)."""
        with self.lock:
            self.haze_status = status

    def set_haze_cooldown(self, duration_seconds: float):
        """Establece cooldown de haze."""
        with self.lock:
            self.haze_cooldown_until = time.time() + duration_seconds
            self.haze_status = "COOLDOWN"

    def set_haze_fire(self):
        """Marca que se disparó haze."""
        with self.lock:
            self.haze_last_fire = time.time()
            self.haze_status = "SHOOTING"

    def is_haze_ready(self) -> bool:
        """Verifica si haze está listo para disparar."""
        with self.lock:
            if not self.haze_enabled:
                return False
            if time.time() < self.haze_cooldown_until:
                return False
            return self.haze_status == "READY"

    # ----- DJ DETECTOR -----

    def get_dj_state(self) -> Dict[str, Any]:
        """Obtiene estado completo de DJ detector."""
        with self.lock:
            return {
                "enabled": self.dj_enabled,
                "active_zone": self.dj_active_zone,
                "state": self.dj_state,
                "last_seen": self.dj_last_seen,
                "zones_count": self.dj_zones_count,
            }

    def update_dj(self, zone: Optional[int] = None, state: Optional[str] = None):
        """Actualiza estado de DJ detector."""
        with self.lock:
            if zone is not None:
                self.dj_active_zone = zone
                self.dj_last_seen = time.time()
            if state is not None:
                self.dj_state = state

    def set_dj_zones_count(self, count: int):
        """Establece cantidad de zonas DJ (1-5)."""
        with self.lock:
            self.dj_zones_count = max(1, min(5, count))

    # ----- ARTIST TRACKER -----

    def get_tracking_state(self) -> Dict[str, Any]:
        """Obtiene estado completo de artist tracker."""
        with self.lock:
            return {
                "enabled": self.tracking_enabled,
                "zone": self.tracking_zone,
                "state": self.tracking_state,
                "last_seen": self.tracking_last_seen,
            }

    def update_tracking(self, zone: Optional[int] = None, state: Optional[str] = None):
        """Actualiza estado de artist tracker."""
        with self.lock:
            if zone is not None:
                self.tracking_zone = zone
                self.tracking_last_seen = time.time()
            if state is not None:
                self.tracking_state = state

    # ===== SETTERS THREAD-SAFE =====

    def set_system_enabled(self, enabled: bool):
        """Habilita/deshabilita el sistema completo."""
        with self.lock:
            self.system_enabled = enabled

    def set_camera_index(self, index: int):
        """Establece índice de cámara."""
        with self.lock:
            self.camera_index = index

    def set_fps(self, fps: float):
        """Actualiza FPS."""
        with self.lock:
            self.fps = fps
            self.last_frame_time = time.time()

    def set_haze_enabled(self, enabled: bool):
        """Habilita/deshabilita detector de haze."""
        with self.lock:
            self.haze_enabled = enabled

    def set_dj_enabled(self, enabled: bool):
        """Habilita/deshabilita detector de DJ."""
        with self.lock:
            self.dj_enabled = enabled
            if not enabled:
                self.dj_state = "disabled"

    def set_tracking_enabled(self, enabled: bool):
        """Habilita/deshabilita artist tracker."""
        with self.lock:
            self.tracking_enabled = enabled
            if not enabled:
                self.tracking_state = "disabled"

    # ===== ESTADO COMPLETO =====

    def to_dict(self) -> Dict[str, Any]:
        """
        Serializa el estado completo a diccionario.

        Returns:
            dict: Estado completo del sistema
        """
        with self.lock:
            return {
                "system": {
                    "enabled": self.system_enabled,
                    "camera_index": self.camera_index,
                    "fps": self.fps,
                    "last_frame_time": self.last_frame_time,
                },
                "haze": {
                    "enabled": self.haze_enabled,
                    "level": self.haze_level,
                    "baseline": self.haze_baseline,
                    "contrast": self.haze_contrast,
                    "state": self.haze_state,
                    "status": self.haze_status,
                    "cooldown_remaining": max(0, self.haze_cooldown_until - time.time()),
                    "last_fire": self.haze_last_fire,
                },
                "dj": {
                    "enabled": self.dj_enabled,
                    "active_zone": self.dj_active_zone,
                    "state": self.dj_state,
                    "last_seen": self.dj_last_seen,
                    "zones_count": self.dj_zones_count,
                },
                "tracking": {
                    "enabled": self.tracking_enabled,
                    "zone": self.tracking_zone,
                    "state": self.tracking_state,
                    "last_seen": self.tracking_last_seen,
                }
            }

    def reset(self):
        """Resetea el estado a valores iniciales."""
        with self.lock:
            self.fps = 0.0
            self.haze_level = 0.0
            self.haze_baseline = 0.0
            self.haze_contrast = 0.0
            self.haze_state = "LOW"
            self.haze_status = "READY"
            self.haze_cooldown_until = 0.0
            self.dj_active_zone = None
            self.dj_state = "disabled" if not self.dj_enabled else "idle"
            self.tracking_zone = None
            self.tracking_state = "disabled" if not self.tracking_enabled else "idle"
