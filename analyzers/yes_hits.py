# analyzers/yes_hits.py — YES HITS (opuesto literal de NoHits)
import numpy as np
from base_module import BaseModule
from module_card import ModuleCard
from dsp_utils import mono, rms

class YesHits(BaseModule):
    name = "YES HITS"
    flag_name = "YES_HITS"  # V10: Flag para votación en BaseGolpe

    def __init__(self):
        super().__init__()
        self.card = ModuleCard(self.name)
        
        # Sliders de configuración OPTIMIZADOS para respuesta rápida
        self.card.add_slider("sens", "Sensibilidad", 0.1, 3.0, 1.2)      # Subido de 1.0 a 1.2
        self.card.add_slider("refrac", "Refractario (ms)", 5, 60, 15)    # Reducido de 5-80/30 a 5-60/15
        self.card.add_slider("smooth", "Suavizado", 0.05, 0.5, 0.18)     # Reducido de 0.25 a 0.18
        self.card.add_slider("snr", "SNR gate", 6, 24, 10)               # Reducido de 12 a 10
        self.card.add_slider("hold", "Hold golpe (ms)", 20, 300, 50)     # Reducido de 40-500/160 a 20-300/50
        self.card.add_slider("thresh", "Umbral golpe", 0.3, 0.9, 0.65)   # Reducido de 0.7 a 0.65
        self.card.add_led("golpe", "Golpe")
        
        # Estado interno
        self._ema = 0.0
        self._ts_hit = 0.0  # ms consecutivos con golpe
        self._last_hit_time = 0.0  # para período refractario
        self._prev_rms = 0.0  # para detección de cambios súbitos
        self.detected = False  # V10: Flag para votación
        
    def _detect_transient(self, x, sr):
        """Detección OPTIMIZADA de transitorios - más eficiente"""
        
        # 1. Métrica de derivada mejorada con menos cálculos
        d = np.diff(x, prepend=x[0])
        
        # ✅ Usar RMS en lugar de STD para evitar cálculo de media
        rms_signal = np.sqrt(np.mean(x**2))
        rms_derivative = np.sqrt(np.mean(d**2))
        
        # Evitar división por cero
        denominator = max(rms_signal, 1e-6)
        derivative_score = rms_derivative / denominator
        
        # 2. Detección de cambios súbitos en RMS
        current_rms = rms(x)
        if self._prev_rms > 0:
            rms_ratio = current_rms / max(self._prev_rms, 1e-6)
            # Normalizar ratio a [0, 1]: valores > 1 indican aumento súbito
            rms_score = np.clip((rms_ratio - 1.0) * 2.0, 0.0, 1.0)
        else:
            rms_score = 0.0
        self._prev_rms = current_rms
        
        # 3. High-frequency content OPTIMIZADO
        # Usar max absoluto en lugar de segunda derivada (más rápido)
        hf_score = np.max(np.abs(d)) / max(rms_signal, 1e-6)
        
        # ✅ Combinar métricas con pesos BALANCEADOS
        transient_score = (
            0.55 * derivative_score +  # Aumentado de 0.5 - más peso a cambios
            0.30 * rms_score +         # Mantener
            0.15 * hf_score            # Reducido de 0.2 - menos peso a HF
        )
        
        return np.clip(transient_score, 0.0, 2.0)  # Permitir valores > 1 para sensibilidad
    
    def _apply_refractory_period(self, hit_detected, block_duration_ms):
        """Aplica período refractario OPTIMIZADO"""
        refrac_ms = float(self.card.get_value("refrac"))
        
        # ✅ Simplificado: actualizar timer siempre
        self._last_hit_time = max(0.0, self._last_hit_time - block_duration_ms)
        
        # Solo permitir hit si no estamos en período refractario
        if hit_detected and self._last_hit_time <= 0:
            self._last_hit_time = refrac_ms
            return True
        
        return False
    
    def process(self, block, sr):
        if block is None or block.size == 0:
            return
            
        x = mono(block).astype(np.float32)
        block_duration_ms = (len(x) / float(sr)) * 1000.0
        
        # ✅ Gate por SNR optimizado - calcular umbral una sola vez
        if not hasattr(self, '_snr_threshold_cache'):
            self._snr_threshold_cache = {}
            self._snr_last_value = None
        
        snr_gate_db = float(self.card.get_value("snr"))
        
        # Cachear cálculo de umbral (costoso: 10**x)
        if snr_gate_db != self._snr_last_value:
            self._snr_threshold_cache = 10**(-snr_gate_db/20)
            self._snr_last_value = snr_gate_db
        
        current_rms = rms(x)
        
        if current_rms < self._snr_threshold_cache:
            transient_score = 0.0
        else:
            # Detección mejorada de transitorios
            transient_score = self._detect_transient(x, sr)
            
            # Aplicar sensibilidad
            sensitivity = float(self.card.get_value("sens"))
            transient_score *= sensitivity
        
        # ✅ Normalizar con safety check para valores extremos
        val = float(np.clip(transient_score, 0.0, 2.0))  # Permitir >1 temporalmente
        
        # Suavizado exponencial mejorado
        smooth_factor = float(self.card.get_value("smooth"))
        # Clamp smooth_factor para evitar inestabilidad
        smooth_factor = max(0.05, min(0.5, smooth_factor))
        
        self._ema = (1.0 - smooth_factor) * self._ema + smooth_factor * val
        # Normalizar DESPUÉS del smoothing
        smoothed_val = float(np.clip(self._ema, 0.0, 1.0))
        
        # Detección de golpe con umbral configurable
        hit_threshold = float(self.card.get_value("thresh"))
        hit_detected = smoothed_val >= hit_threshold
        
        # Aplicar período refractario
        hit_detected = self._apply_refractory_period(hit_detected, block_duration_ms)
        
        # Actualizar contador de hold
        if hit_detected:
            self._ts_hit += block_duration_ms
        else:
            self._ts_hit = 0.0
        
        # Activar LED si se mantiene el hit por suficiente tiempo
        hold_time_ms = float(self.card.get_value("hold"))
        self.detected = self._ts_hit >= hold_time_ms  # V10: Flag para votación
        self.card.set_led("golpe", self.detected)

        # Establecer valor del módulo
        self.card.set_value(smoothed_val)
        
        # Estado ON basado en thresholds y match
        lo, hi = self.card.get_thresholds()
        match = self.card.get_match()
        on = (lo <= smoothed_val <= hi) and (int(smoothed_val * 100) >= match)
        self.card.set_on(on)