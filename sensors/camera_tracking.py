"""
Camera Tracking Sensor - Phase 6.6
Seguimiento de movimiento en zonas definidas
"""
import logging
import cv2
import numpy as np
from typing import List, Dict, Any, Optional
import threading
import time

logger = logging.getLogger(__name__)


class CameraTrackingSensor:
    """
    Sensor para tracking de movimiento mediante optical flow
    """

    def __init__(self):
        self.zones = {}  # camera_id -> [zone_dict, ...]
        self.detections = {}  # camera_id -> detection_data
        self.lock = threading.RLock()

        self.previous_frames = {}  # camera_id -> prev_gray_frame
        self.frame_count = 0
        self.last_detection_time = {}

        # Parámetros de optical flow
        self.flow_params = dict(
            pyr_scale=0.5,
            levels=3,
            winsize=15,
            iterations=3,
            poly_n=5,
            poly_sigma=1.2,
            flags=0
        )

        logger.info("CameraTrackingSensor initialized")

    def set_zones(self, camera_id: str, zones: List[Dict[str, Any]]):
        """
        Define zonas de tracking para una cámara
        zones: lista de dicts con {id, name, points: [[x,y], ...], enabled, sensitivity}
        """
        with self.lock:
            self.zones[camera_id] = zones
            logger.info(f"Tracking zones set for camera {camera_id}: {len(zones)} zones")

    def get_zones(self, camera_id: str) -> List[Dict[str, Any]]:
        """Retorna las zonas definidas para una cámara"""
        with self.lock:
            return self.zones.get(camera_id, []).copy()

    def process_frame(self, frame: np.ndarray, camera_id: str):
        """Procesa un frame y detecta movimiento en las zonas definidas"""
        try:
            with self.lock:
                zones = self.zones.get(camera_id, [])
                if not zones:
                    return

                # Convertir a escala de grises
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

                # Obtener frame anterior
                prev_gray = self.previous_frames.get(camera_id)

                zone_detections = []

                if prev_gray is not None:
                    # Calcular optical flow
                    flow = cv2.calcOpticalFlowFarneback(
                        prev_gray, gray, None, **self.flow_params
                    )

                    # Calcular magnitud del movimiento
                    magnitude, angle = cv2.cartToPolar(flow[..., 0], flow[..., 1])

                    # Analizar cada zona
                    for zone in zones:
                        if not zone.get('enabled', True):
                            continue

                        # Crear máscara para la zona
                        mask = np.zeros(gray.shape, dtype=np.uint8)
                        points = np.array(zone['points'], dtype=np.int32)
                        cv2.fillPoly(mask, [points], 255)

                        # Extraer movimiento en la zona
                        zone_magnitude = magnitude[mask > 0]

                        if len(zone_magnitude) == 0:
                            continue

                        # Calcular métricas de movimiento
                        mean_motion = np.mean(zone_magnitude)
                        max_motion = np.max(zone_magnitude)

                        sensitivity = zone.get('sensitivity', 1.0)
                        motion_threshold = 2.0 / sensitivity

                        motion_detected = mean_motion > motion_threshold

                        # Nivel de movimiento (0-100)
                        motion_level = min(100, int((mean_motion / 10.0) * 100))

                        # Dirección predominante
                        zone_angles = angle[mask > 0]
                        mean_angle = np.mean(zone_angles)
                        direction = self._angle_to_direction(mean_angle)

                        zone_detections.append({
                            'zone_id': zone.get('id'),
                            'zone_name': zone.get('name'),
                            'motion_detected': motion_detected,
                            'motion_level': motion_level,
                            'mean_motion': float(mean_motion),
                            'max_motion': float(max_motion),
                            'direction': direction
                        })

                # Guardar resultados
                self.detections[camera_id] = {
                    'timestamp': time.time(),
                    'zones': zone_detections
                }

                # Guardar frame actual para próxima iteración
                self.previous_frames[camera_id] = gray.copy()

                self.frame_count += 1
                self.last_detection_time[camera_id] = time.time()

        except Exception as e:
            logger.error(f"Error processing tracking frame for camera {camera_id}: {e}", exc_info=True)

    def _angle_to_direction(self, angle_rad: float) -> str:
        """Convierte un ángulo en radianes a una dirección cardinal"""
        angle_deg = np.degrees(angle_rad)
        if angle_deg < 0:
            angle_deg += 360

        if 337.5 <= angle_deg or angle_deg < 22.5:
            return "E"
        elif 22.5 <= angle_deg < 67.5:
            return "NE"
        elif 67.5 <= angle_deg < 112.5:
            return "N"
        elif 112.5 <= angle_deg < 157.5:
            return "NW"
        elif 157.5 <= angle_deg < 202.5:
            return "W"
        elif 202.5 <= angle_deg < 247.5:
            return "SW"
        elif 247.5 <= angle_deg < 292.5:
            return "S"
        else:
            return "SE"

    def get_detections(self, camera_id: str) -> Optional[Dict[str, Any]]:
        """Retorna las últimas detecciones para una cámara"""
        with self.lock:
            return self.detections.get(camera_id, {}).copy()

    def get_annotated_frame(self, frame: np.ndarray, camera_id: str) -> np.ndarray:
        """Retorna un frame con anotaciones de zonas y movimiento"""
        annotated = frame.copy()

        with self.lock:
            # Dibujar zonas
            zones = self.zones.get(camera_id, [])
            detection_data = self.detections.get(camera_id, {})
            zone_results = {z['zone_id']: z for z in detection_data.get('zones', [])}

            for zone in zones:
                if not zone.get('enabled', True):
                    continue

                zone_id = zone.get('id')
                points = np.array(zone['points'], dtype=np.int32)

                # Color según detección
                result = zone_results.get(zone_id, {})
                motion_detected = result.get('motion_detected', False)
                color = (255, 165, 0) if motion_detected else (0, 255, 0)

                cv2.polylines(annotated, [points], True, color, 2)

                # Label con nivel de movimiento
                if len(points) > 0:
                    label = zone.get('name', 'Zone')
                    if motion_detected:
                        motion_level = result.get('motion_level', 0)
                        direction = result.get('direction', '?')
                        label += f" | Motion: {motion_level}% {direction}"

                    cv2.putText(
                        annotated,
                        label,
                        tuple(points[0]),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        color,
                        1
                    )

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
