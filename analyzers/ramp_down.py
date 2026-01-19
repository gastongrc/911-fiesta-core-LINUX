# analyzers/ramp_down.py – RAMP DOWN (caída de nivel por segundo)
# v2025-09-02: fix match=1.0→100, smoothing por tau (80..600 ms), status
# v2025-09-05: Corrección completa - constantes, mejor manejo de errores, optimizaciones
# v2025-10-02-OPTIMIZED: smooth default 0.25 → 0.40

import numpy as np
from base_module import BaseModule
from module_card import ModuleCard
from dsp_utils import mono, rms

class RampDown(BaseModule):
    """
    Analizador que detecta caídas rápidas de nivel de audio.
    Mide la velocidad de caída en amplitud por segundo y la suaviza.
    """
    
    # Constantes del módulo
    SILENCE_THRESHOLD = 1e-4
    FAST_DECAY_TAU_SEC = 0.18
    MIN_DELTA_TIME = 1e-6
    LED_ACTIVATION_THRESHOLD = 0.20
    TAU_MIN_MS = 80.0
    TAU_MAX_MS = 600.0
    DEBUG_UPDATE_INTERVAL = 60
    DEFAULT_MATCH_VALUE = 50.0
    
    name = "RAMP DOWN"

    def __init__(self):
        super().__init__()
        self.card = ModuleCard(self.name)
        
        self._setup_controls()
        self._reset_state()

    def _setup_controls(self):
        """Configura los controles de la interfaz de usuario"""
        self.card.add_slider("vmin", "Vel. caída mín", 0.01, 0.25, 0.05)
        self.card.add_slider("vmax", "Vel. caída máx", 0.05, 0.80, 0.30)
        # CORRECCIÓN: smooth default 0.25 → 0.40
        self.card.add_slider("smooth", "Suavizado", 0.00, 0.95, 0.40)
        self.card.add_led("down", "Bajando")

    def _reset_state(self):
        """Reinicia el estado interno del módulo"""
        self._vu_level = 0.0
        self._last_level = None
        self._debug_counter = 0

    def process(self, block, sr):
        """Procesa un bloque de audio para detectar caídas de nivel"""
        if not self._validate_input(block, sr):
            return

        audio_mono = mono(block).astype(np.float32, copy=False)
        if audio_mono.size == 0:
            return

        current_level = float(rms(audio_mono))
        block_duration = audio_mono.size / float(sr)
        
        if self._last_level is None:
            self._last_level = current_level

        previous_level = self._last_level
        self._last_level = current_level

        if self._is_silence(current_level, previous_level):
            self._process_silence(block_duration)
            output_value = float(np.clip(self._vu_level, 0.0, 1.0))
            self._render(output_value, current_level, previous_level, 0.0, 0.0)
        else:
            self._process_signal(current_level, previous_level, block_duration)

    def _validate_input(self, block, sr):
        """Valida los parámetros de entrada"""
        return (block is not None and 
                sr is not None and 
                sr > 0 and 
                hasattr(block, 'size'))

    def _is_silence(self, current_level, previous_level):
        """Determina si los niveles actuales constituyen silencio"""
        return max(current_level, previous_level) < self.SILENCE_THRESHOLD

    def _process_silence(self, delta_time):
        """Procesa el caso de silencio con caída rápida del VU"""
        decay_factor = np.exp(-delta_time / self.FAST_DECAY_TAU_SEC)
        self._vu_level = float(decay_factor * self._vu_level)

    def _process_signal(self, current_level, previous_level, delta_time):
        """Procesa señal audible calculando caídas de nivel"""
        safe_delta_time = max(delta_time, self.MIN_DELTA_TIME)
        level_derivative = (current_level - previous_level) / safe_delta_time
        fall_rate = max(0.0, -level_derivative)

        raw_fall_value = self._calculate_raw_fall_value(fall_rate)
        smoothed_value = self._apply_smoothing(raw_fall_value, delta_time)
        
        output_value = float(np.clip(smoothed_value, 0.0, 1.0))
        self._render(output_value, current_level, previous_level, fall_rate, raw_fall_value)

    def _calculate_raw_fall_value(self, fall_rate):
        """Mapea la velocidad de caída a un valor 0-1 usando vmin/vmax"""
        vmin = float(self.card.get_value("vmin"))
        vmax = float(self.card.get_value("vmax"))
        
        if vmax < vmin:
            vmin, vmax = vmax, vmin
        
        range_size = max(1e-6, vmax - vmin)
        raw_value = (fall_rate - vmin) / range_size
        return float(np.clip(raw_value, 0.0, 1.0))

    def _apply_smoothing(self, raw_value, delta_time):
        """Aplica suavizado temporal usando filtro exponencial"""
        smooth_param = float(np.clip(self.card.get_value("smooth"), 0.0, 0.95))
        
        tau_ms = self.TAU_MIN_MS + (self.TAU_MAX_MS - self.TAU_MIN_MS) * (smooth_param ** 2)
        tau_seconds = tau_ms / 1000.0
        
        decay_factor = np.exp(-delta_time / tau_seconds)
        self._vu_level = (1.0 - decay_factor) * raw_value + decay_factor * self._vu_level
        
        return self._vu_level

    def _render(self, output_value, current_level, previous_level, fall_rate, raw_value):
        """Actualiza la interfaz de usuario y calcula el estado de match"""
        self.card.set_value(output_value)
        self.card.set_led("down", output_value > self.LED_ACTIVATION_THRESHOLD)

        self._update_match_status(output_value)
        self._update_debug_info(current_level, previous_level, fall_rate, raw_value, output_value)

    def _update_match_status(self, output_value):
        """Actualiza el estado de match basado en thresholds y valor de match"""
        threshold_low, threshold_high = self.card.get_thresholds()
        threshold_low = self._normalize_01(threshold_low)
        threshold_high = self._normalize_01(threshold_high)
        
        if threshold_high < threshold_low:
            threshold_low, threshold_high = threshold_high, threshold_low
        
        required_match = self._normalize_match(self.card.get_match())
        
        within_thresholds = threshold_low <= output_value <= threshold_high
        above_match = (output_value * 100.0) >= (required_match - 1e-6)
        
        self.card.set_on(within_thresholds and above_match)

    def _update_debug_info(self, current_level, previous_level, fall_rate, raw_value, output_value):
        """Actualiza información de debug de forma controlada"""
        self._debug_counter += 1
        
        if (self._debug_counter % self.DEBUG_UPDATE_INTERVAL) == 0:
            try:
                status_text = (f"lvl={current_level:.3f} prev={previous_level:.3f} | "
                             f"fall={fall_rate:.3f}/s | raw={raw_value:.2f} out={output_value:.2f}")
                self.card.set_status(status_text)
            except Exception as e:
                print(f"RampDown debug update failed: {e}")

    @staticmethod
    def _normalize_01(value):
        """Normaliza un valor al rango 0-1"""
        if value is None:
            return 0.0
        
        try:
            float_value = float(value)
        except (ValueError, TypeError):
            return 0.0
        
        if float_value > 1.5:
            float_value *= 0.01
        
        return float(np.clip(float_value, 0.0, 1.0))

    @staticmethod
    def _normalize_match(match_value):
        """Normaliza valor de match a rango 0-100"""
        if match_value is None:
            return RampDown.DEFAULT_MATCH_VALUE
        
        try:
            match_float = float(match_value)
        except (ValueError, TypeError):
            return RampDown.DEFAULT_MATCH_VALUE
        
        if 0.0 <= match_float <= 1.0:
            match_float *= 100.0
        
        return float(np.clip(match_float, 0.0, 100.0))

    def reset(self):
        """Método público para reiniciar el estado del módulo"""
        self._reset_state()

    def get_status(self):
        """Retorna información de estado del módulo para debugging"""
        return {
            'vu_level': self._vu_level,
            'last_level': self._last_level,
            'debug_counter': self._debug_counter,
            'name': self.name
        }