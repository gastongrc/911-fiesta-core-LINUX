"""
Haze Detector - Phase 6 REAL Core Integration
Detector de humo/neblina integrado al motor principal de 911 Fiesta
"""
import cv2
import numpy as np
import time


class HazeDetector:
    """
    Detector REAL de haze integrado al CORE.

    Responsabilidades:
    - Detectar presencia de humo/neblina en zonas configuradas
    - Calcular niveles de intensidad (0-100)
    - Generar triggers para cues cuando se detecta cambio de estado
    - Mantener estado persistente para StateManager

    Integración:
    - Se conecta con StateManager para reportar estado
    - Puede disparar cues específicos via CueEngine
    - Usa vision_config.json para configuración de zonas
    """

    def __init__(self, config):
        """
        Inicializa el detector de haze.

        Args:
            config (VisionConfig): Configuración de zonas y parámetros
        """
        self.config = config
        haze_config = config.get("haze")

        # Parámetros de configuración
        self.threshold = haze_config.get("threshold", 35)
        self.smooth_factor = haze_config.get("smooth_factor", 0.2)
        self.baseline_frames = haze_config.get("baseline_frames", 30)

        # ✅ VISION PRO v2: Nuevos parámetros de histéresis y smoothing
        self.alpha = haze_config.get("smooth_alpha", 0.25)
        self.entry_th = haze_config.get("entry_threshold", 0.40)
        self.exit_th = haze_config.get("exit_threshold", 0.30)
        self.lock_time = haze_config.get("lock_time", 0.25)

        # Estado interno
        self.baseline_contrast = None
        self.haze_level = 0.0
        self.haze_detected = False
        self.last_update = None

        # ✅ VISION PRO v2: Estado de haze con histéresis
        self._smooth_haze = 0.0
        self._lock = 0.0
        self.haze_state = "HAZE_LOW"  # Estados: HAZE_LOW, HAZE_HIGH, DISABLED_BY_MODE

        # Baseline learning
        self.baseline_samples = []
        self.frame_count = 0

        # Historial para suavizado temporal (EMA)
        self.contrast_history = []

    def process_frame(self, frame):
        """
        Procesa un frame de cámara para detectar haze.

        Args:
            frame: Frame de OpenCV (numpy array BGR)

        Returns:
            dict: Estado de detección {
                'detected': bool,
                'level': float (0-100),
                'contrast': float,
                'baseline': float
            }
        """
        if frame is None:
            return self.get_state()

        # 1. Conversión BGR → GRAY
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # 2. Calcular histograma
        hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
        hist = hist.flatten()

        # 3. RMS de luminancia (Root Mean Square)
        luminance_rms = np.sqrt(np.mean(gray.astype(np.float32) ** 2))

        # 4. Cálculo de contraste local (desviación estándar)
        # Phase 6.10: Use cv2.meanStdDev instead of np.std (thread-safe, no BLAS)
        _, stddev = cv2.meanStdDev(gray)
        contrast = float(stddev[0][0])

        # 5. Baseline dinámico (aprendizaje inicial)
        if self.baseline_contrast is None:
            # Fase de aprendizaje: acumular muestras
            self.baseline_samples.append(contrast)

            if len(self.baseline_samples) >= self.baseline_frames:
                # Establecer baseline como la media de las primeras N frames
                self.baseline_contrast = np.mean(self.baseline_samples)
                self.baseline_samples = []  # Liberar memoria
            else:
                # Todavía aprendiendo, no detectar haze
                self.last_update = time.time()
                return self.get_state()

        # 6. Suavizado temporal (EMA - Exponential Moving Average)
        if len(self.contrast_history) > 0:
            smoothed_contrast = (
                self.smooth_factor * contrast +
                (1 - self.smooth_factor) * self.contrast_history[-1]
            )
        else:
            smoothed_contrast = contrast

        self.contrast_history.append(smoothed_contrast)

        # Mantener solo últimas 100 muestras
        if len(self.contrast_history) > 100:
            self.contrast_history.pop(0)

        # 7. Cálculo de nivel de haze (0-100)
        # Haze = reducción de contraste respecto a baseline
        # Más haze → menos contraste → valor más alto

        if self.baseline_contrast > 0:
            # Porcentaje de reducción de contraste
            contrast_reduction = (
                (self.baseline_contrast - smoothed_contrast) /
                self.baseline_contrast
            )

            # Normalizar a 0-100
            # 0% reducción = 0 haze
            # 50% reducción = 100 haze
            raw_haze = np.clip(contrast_reduction * 200, 0, 100)
        else:
            raw_haze = 0.0

        # ✅ VISION PRO v2: Aplicar EMA smoothing al nivel de haze
        self._smooth_haze = (
            self.alpha * raw_haze +
            (1 - self.alpha) * self._smooth_haze
        )

        # Normalizar smooth_haze a rango 0-1 para comparar con thresholds
        normalized_haze = self._smooth_haze / 100.0

        # ✅ VISION PRO v2: Decrementar lock si está activo
        dt = 0.033  # Aproximadamente 30 FPS
        if self._lock > 0:
            self._lock -= dt

        # ✅ VISION PRO v2: Aplicar histéresis de entrada/salida con lock anti-parpadeo
        if normalized_haze >= self.entry_th:
            if self._lock <= 0:
                self._lock = self.lock_time
                self.haze_state = "HAZE_HIGH"
        elif normalized_haze <= self.exit_th:
            self.haze_state = "HAZE_LOW"

        # Mantener haze_level para compatibilidad
        self.haze_level = self._smooth_haze

        # 8. Detección booleana (threshold configurable)
        self.haze_detected = self.haze_level >= self.threshold

        # 9. Guardar timestamp
        self.last_update = time.time()
        self.frame_count += 1

        return self.get_state()

    def get_state(self):
        """
        Retorna el estado actual del detector.

        Returns:
            dict: Estado completo para integración con StateManager {
                'detected': bool,
                'level': float (0-100),
                'contrast': float,
                'baseline': float,
                'last_update': timestamp
            }
        """
        return {
            "detected": self.haze_detected,
            "level": float(self.haze_level),
            "contrast": float(self.contrast_history[-1]) if self.contrast_history else 0.0,
            "baseline": float(self.baseline_contrast) if self.baseline_contrast is not None else 0.0,
            "last_update": self.last_update,
            "frame_count": self.frame_count,
            "learning": self.baseline_contrast is None,
            "haze_state": self.haze_state,  # ✅ VISION PRO v2: Estado con histéresis
            "smooth_value": float(self._smooth_haze),  # ✅ Valor smoothed normalizado
            "lock_remaining": float(self._lock)  # ✅ Lock anti-parpadeo restante
        }

    def disable_by_mode(self):
        """
        ✅ VISION PRO v2 FIX: Desactiva el detector por modo calendario.
        Resetea estado a DISABLED_BY_MODE y limpia locks/smoothing.
        """
        self.haze_state = "DISABLED_BY_MODE"
        self._lock = 0.0
        self._smooth_haze = 0.0
        self.haze_level = 0.0
        self.haze_detected = False

