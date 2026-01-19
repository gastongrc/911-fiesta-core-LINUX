"""
Camera People Sensor - Phase 6.6
Detección de personas en zonas definidas
"""
import logging
import cv2
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
import threading
import time

logger = logging.getLogger(__name__)


class CameraPeopleSensor:
    """
    Sensor para detección de personas en zonas específicas
    """

    def __init__(self):
        self.zones = {}  # camera_id -> [zone_dict, ...]
        self.detections = {}  # camera_id -> detection_data
        self.lock = threading.RLock()

        # Configuración del detector HOG (Histogram of Oriented Gradients)
        self.hog = cv2.HOGDescriptor()
        self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

        self.frame_count = 0
        self.last_detection_time = {}

        logger.info("CameraPeopleSensor initialized")

    def set_zones(self, camera_id: str, zones: List[Dict[str, Any]]):
        """
        Define zonas de detección para una cámara
        zones: lista de dicts con {id, name, points: [[x,y], ...], enabled}
        """
        with self.lock:
            self.zones[camera_id] = zones
            logger.info(f"Zones set for camera {camera_id}: {len(zones)} zones")

    def get_zones(self, camera_id: str) -> List[Dict[str, Any]]:
        """Retorna las zonas definidas para una cámara"""
        with self.lock:
            return self.zones.get(camera_id, []).copy()

    def process_frame(self, frame: np.ndarray, camera_id: str):
        """Procesa un frame y detecta personas en las zonas definidas"""
        try:
            with self.lock:
                zones = self.zones.get(camera_id, [])
                if not zones:
                    return

                # Detectar personas usando HOG
                people, weights = self.hog.detectMultiScale(
                    frame,
                    winStride=(8, 8),
                    padding=(4, 4),
                    scale=1.05
                )

                # Verificar qué personas están en qué zonas
                zone_detections = []
                for zone in zones:
                    if not zone.get('enabled', True):
                        continue

                    people_in_zone = 0
                    zone_points = np.array(zone['points'], dtype=np.int32)

                    for (x, y, w, h) in people:
                        # Centro de la detección
                        cx, cy = x + w // 2, y + h // 2
                        # Verificar si está dentro de la zona
                        if cv2.pointPolygonTest(zone_points, (cx, cy), False) >= 0:
                            people_in_zone += 1

                    zone_detections.append({
                        'zone_id': zone.get('id'),
                        'zone_name': zone.get('name'),
                        'people_count': people_in_zone
                    })

                # Guardar resultados
                self.detections[camera_id] = {
                    'timestamp': time.time(),
                    'total_people': len(people),
                    'zones': zone_detections,
                    'raw_detections': [(int(x), int(y), int(w), int(h)) for (x, y, w, h) in people]
                }

                self.frame_count += 1
                self.last_detection_time[camera_id] = time.time()

        except Exception as e:
            logger.error(f"Error processing frame for camera {camera_id}: {e}", exc_info=True)

    def get_detections(self, camera_id: str) -> Optional[Dict[str, Any]]:
        """Retorna las últimas detecciones para una cámara"""
        with self.lock:
            return self.detections.get(camera_id, {}).copy()

    def get_annotated_frame(self, frame: np.ndarray, camera_id: str) -> np.ndarray:
        """Retorna un frame con anotaciones de detecciones y zonas"""
        annotated = frame.copy()

        with self.lock:
            # Dibujar zonas
            zones = self.zones.get(camera_id, [])
            for zone in zones:
                if not zone.get('enabled', True):
                    continue

                points = np.array(zone['points'], dtype=np.int32)
                cv2.polylines(annotated, [points], True, (0, 255, 0), 2)

                # Label de la zona
                if len(points) > 0:
                    cv2.putText(
                        annotated,
                        zone.get('name', 'Zone'),
                        tuple(points[0]),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (0, 255, 0),
                        1
                    )

            # Dibujar detecciones
            detection_data = self.detections.get(camera_id)
            if detection_data:
                for (x, y, w, h) in detection_data.get('raw_detections', []):
                    cv2.rectangle(annotated, (x, y), (x + w, y + h), (255, 0, 0), 2)

        return annotated

    def get_stats(self) -> Dict[str, Any]:
        """Retorna estadísticas del sensor"""
        with self.lock:
            return {
                'frame_count': self.frame_count,
                'cameras': list(self.zones.keys()),
                'total_zones': sum(len(z) for z in self.zones.values()),
                'last_detection_times': self.last_detection_time.copy()
            }
