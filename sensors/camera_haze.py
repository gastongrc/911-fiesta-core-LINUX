"""
Camera Haze Sensor - Phase 6.6
Detección de humo/neblina en zonas definidas
"""
import logging
import cv2
import numpy as np
from typing import List, Dict, Any, Optional
import threading
import time

logger = logging.getLogger(__name__)


class CameraHazeSensor:
    """
    Sensor para detección de humo/neblina mediante análisis de contraste
    """

    def __init__(self):
        self.zones = {}  # camera_id -> [zone_dict, ...]
        self.detections = {}  # camera_id -> detection_data
        self.lock = threading.RLock()

        self.frame_count = 0
        self.last_detection_time = {}

        # Configuración de detección
        self.contrast_threshold = 30  # Umbral de contraste para detectar neblina
        self.brightness_threshold = 150  # Umbral de brillo

        logger.info("CameraHazeSensor initialized")

    def set_zones(self, camera_id: str, zones: List[Dict[str, Any]]):
        """
        Define zonas de detección para una cámara
        zones: lista de dicts con {id, name, points: [[x,y], ...], enabled, sensitivity}
        """
        with self.lock:
            self.zones[camera_id] = zones
            logger.info(f"Haze zones set for camera {camera_id}: {len(zones)} zones")

    def get_zones(self, camera_id: str) -> List[Dict[str, Any]]:
        """Retorna las zonas definidas para una cámara"""
        with self.lock:
            return self.zones.get(camera_id, []).copy()

    def process_frame(self, frame: np.ndarray, camera_id: str):
        """Procesa un frame y detecta humo/neblina en las zonas definidas"""
        try:
            with self.lock:
                zones = self.zones.get(camera_id, [])
                if not zones:
                    return

                # Convertir a escala de grises
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

                zone_detections = []
                for zone in zones:
                    if not zone.get('enabled', True):
                        continue

                    # Crear máscara para la zona
                    mask = np.zeros(gray.shape, dtype=np.uint8)
                    points = np.array(zone['points'], dtype=np.int32)
                    cv2.fillPoly(mask, [points], 255)

                    # Extraer región de la zona
                    zone_region = cv2.bitwise_and(gray, gray, mask=mask)

                    # Calcular métricas
                    pixels = zone_region[mask > 0]
                    if len(pixels) == 0:
                        continue

                    mean_brightness = np.mean(pixels)
                    std_contrast = np.std(pixels)

                    # Detectar humo (baja contraste + alta luminosidad)
                    sensitivity = zone.get('sensitivity', 1.0)
                    haze_detected = (
                        std_contrast < self.contrast_threshold * sensitivity and
                        mean_brightness > self.brightness_threshold
                    )

                    haze_level = 0
                    if haze_detected:
                        # Nivel de humo (0-100)
                        haze_level = min(100, int((1 - std_contrast / 100) * 100))

                    zone_detections.append({
                        'zone_id': zone.get('id'),
                        'zone_name': zone.get('name'),
                        'haze_detected': haze_detected,
                        'haze_level': haze_level,
                        'brightness': float(mean_brightness),
                        'contrast': float(std_contrast)
                    })

                # Guardar resultados
                self.detections[camera_id] = {
                    'timestamp': time.time(),
                    'zones': zone_detections
                }

                self.frame_count += 1
                self.last_detection_time[camera_id] = time.time()

        except Exception as e:
            logger.error(f"Error processing haze frame for camera {camera_id}: {e}", exc_info=True)

    def get_detections(self, camera_id: str) -> Optional[Dict[str, Any]]:
        """Retorna las últimas detecciones para una cámara"""
        with self.lock:
            return self.detections.get(camera_id, {}).copy()

    def get_annotated_frame(self, frame: np.ndarray, camera_id: str) -> np.ndarray:
        """Retorna un frame con anotaciones de zonas y niveles de humo"""
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
                haze_detected = result.get('haze_detected', False)
                color = (0, 0, 255) if haze_detected else (0, 255, 0)

                cv2.polylines(annotated, [points], True, color, 2)

                # Label con nivel de humo
                if len(points) > 0:
                    label = zone.get('name', 'Zone')
                    if haze_detected:
                        haze_level = result.get('haze_level', 0)
                        label += f" | Haze: {haze_level}%"

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

    def set_thresholds(self, contrast: Optional[int] = None, brightness: Optional[int] = None):
        """Ajusta los umbrales de detección"""
        if contrast is not None:
            self.contrast_threshold = contrast
        if brightness is not None:
            self.brightness_threshold = brightness
        logger.info(f"Thresholds updated: contrast={self.contrast_threshold}, brightness={self.brightness_threshold}")
