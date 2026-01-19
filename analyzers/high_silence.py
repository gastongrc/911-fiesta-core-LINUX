from base_module import BaseModule
from module_card import ModuleCard
from dsp_utils import band_energy
import numpy as np
import logging

# Configurar logging para el módulo
logger = logging.getLogger(__name__)

# Constantes
EPS = 1e-12
MIN_FREQUENCY = 20.0
MAX_TAU_MS = 600.0
MIN_TAU_MS = 80.0
DEFAULT_MATCH = 50.0

def _norm01(v):
    """Normaliza valor a rango 0..1, admite tanto 0..1 como 0..100"""
    if v is None: 
        return 0.0
    
    try:
        v = float(v)
        # Si el valor es mayor a 1.5, asumimos que está en escala 0..100
        if v > 1.5: 
            v *= 0.01   
        return float(np.clip(v, 0.0, 1.0))
    except (ValueError, TypeError):
        logger.warning(f"No se pudo convertir valor {v} a float, usando 0.0")
        return 0.0

def _norm_match(m):
    """
    Normaliza valor de match: 0..1 o 0..100 → 0..100
    Incluye el caso m==1.0 → 100%
    """
    try:
        m = float(DEFAULT_MATCH if m is None else m)
    except (ValueError, TypeError):
        logger.warning(f"Valor de match inválido: {m}, usando {DEFAULT_MATCH}")
        m = DEFAULT_MATCH
    
    # Si está en rango 0..1, convertir a 0..100
    if 0.0 <= m <= 1.0:
        m *= 100.0
    
    return float(np.clip(m, 0.0, 100.0))

def _validate_frequency_range(lo, hi, nyquist):
    """
    Valida y corrige el rango de frecuencias
    
    Args:
        lo: Frecuencia baja
        hi: Frecuencia alta  
        nyquist: Frecuencia de Nyquist
        
    Returns:
        tuple: (lo_corregida, hi_corregida)
    """
    # Aplicar límites físicos
    hi = min(max(2000.0, hi), nyquist * 0.95)
    lo = min(max(MIN_FREQUENCY, lo), hi - 200.0)
    
    return lo, hi

class HighSilence(BaseModule):
    """
    Módulo que detecta silencio en frecuencias agudas.
    
    Analiza la energía relativa en una banda de frecuencias altas
    y determina si hay "silencio" (poca energía) en esas frecuencias.
    """
    
    name = "HIGH SILENCE"

    def __init__(self):
        super().__init__()
        self._setup_ui()
        self._init_state()

    def _setup_ui(self):
        """Configura la interfaz de usuario del módulo"""
        self.card = ModuleCard(self.name)
        self.card.add_slider("lo", "Agudos LO (Hz)", 4000, 8000, 5000)
        self.card.add_slider("hi", "Agudos HI (Hz)", 9000, 16000, 12000)
        # Suavizado: 0..0.95 → τ 80..600 ms (↑ = más suave)
        self.card.add_slider("smooth", "Suavizado", 0.00, 0.95, 0.25)
        self.card.add_led("hs", "Agudos silenciosos")
        self.card.add_slider("hold", "Hold ON (ms)", 80.0, 1500.0, 400.0)
        self.card.add_slider("thr_on",  "Thr ON",   0.30, 0.90, 0.55)
        self.card.add_slider("thr_off", "Thr OFF",  0.20, 0.85, 0.48)

    def _init_state(self):
        """Inicializa el estado interno del módulo"""
        self._vu = 0.0
        self._dbg = 0
        self._last_lo = None
        self._last_hi = None
        self._on = False
        self._ton = 0.0
        self._toff = 0.0

    def _calculate_smoothing_coefficient(self, smooth_param, dt):
        """
        Calcula el coeficiente de suavizado exponencial
        
        Args:
            smooth_param: Parámetro de suavizado (0..0.95)
            dt: Delta de tiempo del bloque actual
            
        Returns:
            float: Coeficiente alpha para filtro exponencial
        """
        smooth = float(np.clip(smooth_param, 0.0, 0.95))
        # Mapeo cuadrático para más control fino en valores bajos
        tau_ms = MIN_TAU_MS + (MAX_TAU_MS - MIN_TAU_MS) * (smooth ** 2)
        alpha = np.exp(-dt / (tau_ms / 1000.0))
        return alpha

    def _calculate_silence_metric(self, rel_energy):
        """
        Calcula la métrica de silencio basada en energía relativa
        
        Args:
            rel_energy: Energía relativa en la banda (0..1)
            
        Returns:
            float: Métrica de silencio (0..1, donde 1 = más silencio)
        """
        # Pocos agudos => VU alto (más silencio detectado)
        v_raw = 1.0 - float(rel_energy) * 4.0
        return float(np.clip(v_raw, 0.0, 1.0))

    def _update_debug_info(self, lo, hi, rel_energy, v):
        """Actualiza información de debug periódicamente"""
        self._dbg += 1
        if (self._dbg % 120) == 0:  # Cada ~2.5 segundos a 48kHz
            try:
                status_msg = f"{lo:.0f}-{hi:.0f} Hz | rel={rel_energy:.2f} | v={v:.2f}"
                self.card.set_status(status_msg)
                
                # Log cambios en parámetros de frecuencia
                if self._last_lo != lo or self._last_hi != hi:
                    logger.debug(f"Rango de frecuencias actualizado: {lo:.0f}-{hi:.0f} Hz")
                    self._last_lo, self._last_hi = lo, hi
                    
            except Exception as e:
                logger.error(f"Error actualizando debug info: {e}")

    def process(self, block, sr):
        """
        Procesa un bloque de audio para detectar silencio en agudos
        
        Args:
            block: Bloque de audio (numpy array)
            sr: Frecuencia de muestreo
        """
        # Validaciones de entrada
        if block is None or sr is None or sr <= 0:
            logger.warning("Bloque o sample rate inválido")
            return
            
        n = len(block) if hasattr(block, "__len__") else 0
        if n == 0:
            logger.warning("Bloque de audio vacío")
            return
            
        dt = n / float(sr)

        try:
            # Obtener y validar parámetros de frecuencia
            lo = float(self.card.get_value("lo"))
            hi = float(self.card.get_value("hi"))
            nyquist = 0.5 * float(sr)
            
            lo, hi = _validate_frequency_range(lo, hi, nyquist)

            # Calcular energía en la banda de frecuencias
            # band_energy retorna: (E_band, E_total, rel_band) 
            # donde rel_band ~ 0..1 es la energía relativa en la banda
            _, _, rel_energy = band_energy(block, sr, lo, hi)
            
            # Calcular métrica de silencio
            v_raw = self._calculate_silence_metric(rel_energy)

            # Aplicar suavizado temporal
            smooth_param = self.card.get_value("smooth")
            alpha = self._calculate_smoothing_coefficient(smooth_param, dt)
            
            self._vu = (1.0 - alpha) * v_raw + alpha * self._vu
            v = float(np.clip(self._vu, 0.0, 1.0))

            # Actualizar interfaz
            self._render(v, dt)
            
            # Debug
            self._update_debug_info(lo, hi, rel_energy, v)
            
        except Exception as e:
            logger.error(f"Error procesando bloque de audio: {e}")
            # En caso de error, mantener estado anterior sin crash

    def _apply_threshold_matching(self, v):
        """
        Aplica la lógica de matching con umbrales mín/máx
        
        Args:
            v: Valor actual de la métrica (0..1)
        """
        try:
            # Obtener umbrales y normalizar
            lo_threshold, hi_threshold = self.card.get_thresholds()
            lo_threshold = _norm01(lo_threshold)
            hi_threshold = _norm01(hi_threshold)
            
            # Asegurar orden correcto
            if hi_threshold < lo_threshold:
                lo_threshold, hi_threshold = hi_threshold, lo_threshold
            
            # Obtener valor de match requerido
            match_required = _norm_match(self.card.get_match())
            
            # Aplicar lógica: valor debe estar en rango Y superar el match
            eps = 1e-6
            in_range = (lo_threshold - eps) <= v <= (hi_threshold + eps)
            meets_match = (v * 100.0 + eps) >= match_required
            
            self.card.set_on(in_range and meets_match)
            
        except Exception as e:
            logger.error(f"Error en threshold matching: {e}")
            self.card.set_on(False)

    def _render(self, v, dt):
        """Actualiza VU, LED con histeresis y match status."""
        self.card.set_value(v)
        hold_on  = float(np.clip(self.card.get_value("hold"), 80.0, 1500.0))/1000.0
        hold_off = max(0.25, 1.1*hold_on)
        thr_on  = float(np.clip(self.card.get_value("thr_on"),  0.10, 0.99))
        thr_off = float(np.clip(self.card.get_value("thr_off"), 0.05, thr_on))
        if v >= thr_on:
            self._ton += dt; self._toff = 0.0
            if self._ton >= hold_on: self._on = True
        elif v <= thr_off:
            self._toff += dt; self._ton = 0.0
            if self._toff >= hold_off: self._on = False
        self.card.set_led("hs", self._on)
        self._apply_threshold_matching(v)

    def reset(self):
        """Reinicia el estado del módulo"""
        self._init_state()
        logger.info("Módulo HighSilence reiniciado")

    # === API de integración/debug ===
    def get_current_value(self):
        return float(np.clip(self._vu, 0.0, 1.0))
    
    def debug_dict(self):
        return {
            "name": self.name,
            "vu": float(np.clip(self._vu,0.0,1.0)),
            "on": bool(self._on)
        }