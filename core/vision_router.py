"""
Vision Router - Phase 6.6
Coordina el flujo de datos entre cámaras y sensores especializados
"""
import logging
from typing import Dict, List, Optional, Any
import threading
import time

logger = logging.getLogger(__name__)


class VisionRouter:
    """
    Enruta frames de cámaras a sensores especializados
    """

    def __init__(self):
        self.cameras = {}
        self.sensors = {}
        self.routes = {}  # camera_id -> [sensor_id, ...]
        self.lock = threading.RLock()
        self.running = False
        self._thread = None

        logger.info("VisionRouter initialized")

    def register_camera(self, camera_id: str, camera):
        """Registra una cámara en el router"""
        with self.lock:
            self.cameras[camera_id] = camera
            if camera_id not in self.routes:
                self.routes[camera_id] = []
            logger.info(f"Camera registered: {camera_id}")

    def register_sensor(self, sensor_id: str, sensor):
        """Registra un sensor en el router"""
        with self.lock:
            self.sensors[sensor_id] = sensor
            logger.info(f"Sensor registered: {sensor_id}")

    def add_route(self, camera_id: str, sensor_id: str):
        """Crea una ruta desde una cámara a un sensor"""
        with self.lock:
            if camera_id not in self.routes:
                self.routes[camera_id] = []
            if sensor_id not in self.routes[camera_id]:
                self.routes[camera_id].append(sensor_id)
                logger.info(f"Route added: {camera_id} -> {sensor_id}")

    def remove_route(self, camera_id: str, sensor_id: str):
        """Elimina una ruta"""
        with self.lock:
            if camera_id in self.routes and sensor_id in self.routes[camera_id]:
                self.routes[camera_id].remove(sensor_id)
                logger.info(f"Route removed: {camera_id} -> {sensor_id}")

    def start(self):
        """Inicia el router"""
        if self.running:
            logger.warning("VisionRouter already running")
            return

        self.running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("VisionRouter started")

    def stop(self):
        """Detiene el router"""
        self.running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        logger.info("VisionRouter stopped")

    def _run(self):
        """Loop principal del router"""
        while self.running:
            try:
                self._process_frame()
                time.sleep(0.033)  # ~30 FPS
            except Exception as e:
                logger.error(f"Error in router loop: {e}", exc_info=True)

    def _process_frame(self):
        """Procesa un frame de cada cámara y lo envía a sus sensores"""
        with self.lock:
            for camera_id, camera in self.cameras.items():
                if not camera.is_active():
                    continue

                frame = camera.get_frame()
                if frame is None:
                    continue

                # Enviar frame a sensores registrados
                for sensor_id in self.routes.get(camera_id, []):
                    sensor = self.sensors.get(sensor_id)
                    if sensor and hasattr(sensor, 'process_frame'):
                        try:
                            sensor.process_frame(frame, camera_id)
                        except Exception as e:
                            logger.error(f"Error processing frame in sensor {sensor_id}: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Retorna el estado del router"""
        with self.lock:
            return {
                'running': self.running,
                'cameras': list(self.cameras.keys()),
                'sensors': list(self.sensors.keys()),
                'routes': self.routes.copy()
            }
