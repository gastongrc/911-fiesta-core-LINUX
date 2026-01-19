"""
Smart Camera - Phase 6.6
Wrapper inteligente sobre OpenCV para captura de video
"""
import logging
import cv2
import numpy as np
import threading
import time
from typing import Optional, Tuple, Dict, Any

logger = logging.getLogger(__name__)


class SmartCamera:
    """
    Cámara inteligente con buffer y manejo automático de errores
    """

    def __init__(self, device_id: int, resolution: Tuple[int, int] = (640, 480), fps: int = 30):
        self.device_id = device_id
        self.resolution = resolution
        self.fps = fps

        self.cap = None
        self.frame = None
        self.active = False
        self.lock = threading.RLock()
        self._thread = None

        self.frame_count = 0
        self.error_count = 0
        self.last_frame_time = 0

        logger.info(f"SmartCamera created for device {device_id}")

    def start(self) -> bool:
        """Inicia la captura de video"""
        if self.active:
            logger.warning(f"Camera {self.device_id} already active")
            return True

        try:
            self.cap = cv2.VideoCapture(self.device_id)
            if not self.cap.isOpened():
                logger.error(f"Failed to open camera {self.device_id}")
                return False

            # Configurar resolución y FPS
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolution[0])
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])
            self.cap.set(cv2.CAP_PROP_FPS, self.fps)

            self.active = True
            self._thread = threading.Thread(target=self._capture_loop, daemon=True)
            self._thread.start()

            logger.info(f"Camera {self.device_id} started")
            return True

        except Exception as e:
            logger.error(f"Error starting camera {self.device_id}: {e}")
            self.active = False
            return False

    def stop(self):
        """Detiene la captura de video"""
        self.active = False

        if self._thread:
            self._thread.join(timeout=2.0)

        if self.cap:
            self.cap.release()
            self.cap = None

        logger.info(f"Camera {self.device_id} stopped")

    def release(self):
        """Alias para stop() - compatibilidad con OpenCV"""
        self.stop()

    def _capture_loop(self):
        """Loop de captura en thread separado"""
        while self.active:
            try:
                if self.cap and self.cap.isOpened():
                    ret, frame = self.cap.read()
                    if ret:
                        with self.lock:
                            self.frame = frame
                            self.frame_count += 1
                            self.last_frame_time = time.time()
                    else:
                        self.error_count += 1
                        logger.warning(f"Failed to read frame from camera {self.device_id}")
                        time.sleep(0.1)
                else:
                    logger.error(f"Camera {self.device_id} not opened")
                    break

            except Exception as e:
                self.error_count += 1
                logger.error(f"Error in capture loop for camera {self.device_id}: {e}")
                time.sleep(0.1)

    def get_frame(self) -> Optional[np.ndarray]:
        """Obtiene el último frame capturado"""
        with self.lock:
            return self.frame.copy() if self.frame is not None else None

    def is_active(self) -> bool:
        """Verifica si la cámara está activa"""
        return self.active

    def get_stats(self) -> Dict[str, Any]:
        """Retorna estadísticas de la cámara"""
        with self.lock:
            return {
                'device_id': self.device_id,
                'active': self.active,
                'frame_count': self.frame_count,
                'error_count': self.error_count,
                'last_frame_age': time.time() - self.last_frame_time if self.last_frame_time > 0 else None,
                'resolution': self.resolution,
                'fps': self.fps
            }

    def get_info(self) -> Dict[str, Any]:
        """Retorna información de la cámara"""
        info = {
            'device_id': self.device_id,
            'resolution': self.resolution,
            'fps': self.fps,
            'active': self.active
        }

        if self.cap and self.cap.isOpened():
            info['actual_width'] = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            info['actual_height'] = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            info['actual_fps'] = int(self.cap.get(cv2.CAP_PROP_FPS))

        return info
