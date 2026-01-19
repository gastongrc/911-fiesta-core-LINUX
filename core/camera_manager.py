"""
Camera Manager - Phase 6.6
Gestiona múltiples cámaras y sus configuraciones
"""
import logging
from typing import Dict, List, Optional, Any
import cv2
import threading

logger = logging.getLogger(__name__)


class CameraManager:
    """
    Administra el ciclo de vida de múltiples cámaras
    """

    def __init__(self):
        self.cameras = {}
        self.configs = {}
        self.lock = threading.RLock()

        logger.info("CameraManager initialized")

    def add_camera(self, camera_id: str, camera, config: Optional[Dict] = None):
        """Agrega una cámara al manager"""
        with self.lock:
            self.cameras[camera_id] = camera
            if config:
                self.configs[camera_id] = config
            logger.info(f"Camera added: {camera_id}")

    def remove_camera(self, camera_id: str):
        """Remueve una cámara del manager"""
        with self.lock:
            if camera_id in self.cameras:
                camera = self.cameras[camera_id]
                if hasattr(camera, 'release'):
                    camera.release()
                del self.cameras[camera_id]
                if camera_id in self.configs:
                    del self.configs[camera_id]
                logger.info(f"Camera removed: {camera_id}")

    def get_camera(self, camera_id: str):
        """Obtiene una cámara por su ID"""
        with self.lock:
            return self.cameras.get(camera_id)

    def get_all_cameras(self) -> Dict[str, Any]:
        """Retorna todas las cámaras"""
        with self.lock:
            return self.cameras.copy()

    def get_config(self, camera_id: str) -> Optional[Dict]:
        """Obtiene la configuración de una cámara"""
        with self.lock:
            return self.configs.get(camera_id)

    def update_config(self, camera_id: str, config: Dict):
        """Actualiza la configuración de una cámara"""
        with self.lock:
            if camera_id in self.cameras:
                self.configs[camera_id] = config
                logger.info(f"Config updated for camera: {camera_id}")
            else:
                logger.warning(f"Camera not found: {camera_id}")

    def list_available_devices(self) -> List[int]:
        """Lista dispositivos de video disponibles en el sistema"""
        available = []
        for i in range(10):  # Verificar primeros 10 índices
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                available.append(i)
                cap.release()
        return available

    def get_status(self) -> Dict[str, Any]:
        """Retorna el estado del manager"""
        with self.lock:
            status = {}
            for camera_id, camera in self.cameras.items():
                status[camera_id] = {
                    'active': camera.is_active() if hasattr(camera, 'is_active') else False,
                    'config': self.configs.get(camera_id, {})
                }
            return status

    def stop_all(self):
        """Detiene todas las cámaras"""
        with self.lock:
            for camera_id in list(self.cameras.keys()):
                self.remove_camera(camera_id)
            logger.info("All cameras stopped")
