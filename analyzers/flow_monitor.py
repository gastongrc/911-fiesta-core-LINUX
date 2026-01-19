# analyzers/flow_monitor.py - FLOW MONITOR (BASE GOLPE, sesgo percutivo) v2025-09-06
"""
Flow Monitor: Detecta patrones rítmicos y densidad de onsets para evaluar flujo musical.
Optimizado para contenido percusivo con análisis robusto de novedad y continuidad.
"""

import numpy as np
import logging
from typing import Optional, Tuple, Union

# Verificar dependencias personalizadas
try:
    from base_module import BaseModule
    from module_card import ModuleCard
    from rhythm_tools import mono, env_onset, find_peaks, gaps_ms
except ImportError as e:
    raise ImportError(f"Required module not found: {e}. Please ensure all dependencies are installed.")

# Configurar logging
logger = logging.getLogger(__name__)

class Constants:
    """Constantes del sistema con nombres descriptivos."""
    EPS = 1e-12
    SILENCE_THRESHOLD = 2e-4  # ~-74 dBFS
    MAD_SCALE_FACTOR = 1.4826  # Factor robusto para MAD (Median Absolute Deviation)
    VU_DECAY_TIME_S = 0.18     # Tiempo de decaimiento del VU meter
    MIN_SAMPLE_RATE = 8000     # Sample rate mínimo válido
    MAX_SAMPLE_RATE = 192000   # Sample rate máximo válido
    MIN_BLOCK_SIZE = 64        # Tamaño mínimo de bloque para FFT
    
    # Rangos de parámetros
    SENS_RANGE = (1.4, 4.0)
    DENS_TGT_RANGE = (1.0, 8.0)
    GAP_MS_RANGE = (250.0, 1200.0)
    WIN_S_RANGE = (2.0, 5.0)
    SMOOTH_RANGE = (0.0, 0.80)
    HOLD_RANGE = (50.0, 400.0)
    
    # Umbrales para LED
    LED_ON_THRESHOLD = 0.60
    LED_OFF_THRESHOLD = 0.50


def _norm01(v: Union[float, int, None]) -> float:
    """Normaliza valor a rango [0, 1] manejando formatos 0-1, 0-100."""
    if v is None:
        return 0.0
    try:
        v = float(v)
        if v > 1.5:  # Asume formato 0-100
            v *= 0.01
        return float(np.clip(v, 0.0, 1.0))
    except (ValueError, TypeError) as e:
        logger.debug(f"Error normalizing value {v}: {e}")
        return 0.0


def _norm_match(m: Union[float, int, None]) -> float:
    """Normaliza match value a rango [0, 100]."""
    try:
        m = float(50.0 if m is None else m)
    except (ValueError, TypeError):
        logger.debug(f"Invalid match value {m}, using default 50.0")
        m = 50.0
    
    if 0.0 <= m < 1.0:
        m *= 100.0
    elif m == 1.0:
        m = 1.0
    
    return float(np.clip(m, 0.0, 100.0))


def _read_units(card: 'ModuleCard', key: str, lo: float, hi: float) -> float:
    """
    Lee valor de slider aceptando formatos: 0-1, 0-100, o unidades directas.
    Retorna valor en unidades especificadas por [lo, hi].
    """
    try:
        v = float(card.get_value(key))
    except (ValueError, TypeError, AttributeError) as e:
        logger.debug(f"Error reading slider '{key}': {e}, using default")
        return (lo + hi) * 0.5
    
    if 0.0 <= v <= 1.0:  # Formato normalizado
        return lo + (hi - lo) * v
    elif 1.5 < v <= 100.0:  # Formato porcentaje
        normalized = np.clip(v, 0.0, 100.0) / 100.0
        return lo + (hi - lo) * normalized
    else:  # Unidades directas
        return float(np.clip(v, lo, hi))


def _mad(a: np.ndarray) -> float:
    """Calcula Median Absolute Deviation de forma robusta."""
    if len(a) == 0:
        return 0.0
    try:
        med = np.median(a)
        return float(np.median(np.abs(a - med)) + Constants.EPS)
    except Exception as e:
        logger.debug(f"Error calculating MAD: {e}")
        return Constants.EPS


class PercussiveBiasFilter:
    """Filtro ligero sin IIR - solo análisis temporal rápido"""
    
    def __init__(self, sr: float):
        self.sr = sr
    
    def calculate_bias(self, x: np.ndarray) -> float:
        """Aproximación rápida usando energía temporal"""
        if len(x) < 64:
            return 0.7
        
        try:
            # Energía en graves (downsample)
            low_energy = float(np.sqrt(np.mean(x[::4]**2)))
            
            # Energía en agudos (derivada)
            high_energy = float(np.sqrt(np.mean(np.diff(x)**2)))
            
            # Energía total
            total_energy = float(np.sqrt(np.mean(x**2)))
            
            if total_energy <= 0:
                return 0.7
            
            ratio = (low_energy + high_energy) / total_energy
            return float(np.clip(0.5 + 0.5 * ratio, 0.5, 1.0))
            
        except Exception:
            return 0.7


class FlowMonitor(BaseModule):
    """
    Monitor de flujo rítmico que analiza densidad de onsets y continuidad.
    
    Características:
    - Detección robusta de onsets usando umbral adaptativo
    - Análisis de densidad temporal configurable
    - Sesgo hacia contenido percusivo
    - Penalización por gaps largos en el flujo
    """
    
    name = "FLOW MONITOR"
    flag_name = "FLOW_MONITOR"  # V10: Flag para votación en BaseGolpe

    def __init__(self):
        super().__init__()
        self._initialize_card()
        self._initialize_state()
        self._percussive_filter = None
        self._last_sr = None

    def _initialize_card(self):
        """Inicializa la interfaz de usuario del módulo."""
        try:
            self.card = ModuleCard(self.name)
            
            # Parámetros de análisis
            self.card.add_slider("sens", "Sensibilidad (×σ)", 
                               Constants.SENS_RANGE[0], Constants.SENS_RANGE[1], 2.2)
            self.card.add_slider("dens_tgt", "Densidad obj (1/s)", 
                               Constants.DENS_TGT_RANGE[0], Constants.DENS_TGT_RANGE[1], 3.0)
            self.card.add_slider("gap_ms", "Gap máx (ms)", 
                               Constants.GAP_MS_RANGE[0], Constants.GAP_MS_RANGE[1], 450.0)
            self.card.add_slider("win_s", "Ventana (s)", 
                               Constants.WIN_S_RANGE[0], Constants.WIN_S_RANGE[1], 3.0)
            
            # Parámetros visuales - OPTIMIZADO
            self.card.add_slider("smooth", "Suavizado", 
                               Constants.SMOOTH_RANGE[0], Constants.SMOOTH_RANGE[1], 0.40)
            self.card.add_slider("hold", "Hold ON (ms)", 
                               Constants.HOLD_RANGE[0], Constants.HOLD_RANGE[1], 120.0)
            
            # Indicadores
            self.card.add_led("flow", "Flow")
            
        except Exception as e:
            logger.error(f"Error initializing module card: {e}")
            raise

    def _initialize_state(self):
        """Inicializa variables de estado del módulo."""
        self._vu = 0.0
        self._on = False
        self._ton = 0.0
        self._toff = 0.0

    def _validate_inputs(self, block, sr) -> bool:
        """Valida inputs del método process."""
        if block is None:
            logger.debug("Received None block")
            return False
        
        if sr is None or sr <= 0:
            logger.debug(f"Invalid sample rate: {sr}")
            return False
        
        if not (Constants.MIN_SAMPLE_RATE <= sr <= Constants.MAX_SAMPLE_RATE):
            logger.debug(f"Sample rate {sr} outside valid range")
            return False
        
        if not hasattr(self, 'card') or self.card is None:
            logger.error("Module not properly initialized")
            return False
        
        return True

    def _setup_percussive_filter(self, sr: float):
        """Configura filtro percusivo si es necesario."""
        if self._last_sr != sr:
            try:
                self._percussive_filter = PercussiveBiasFilter(sr)
                self._last_sr = sr
            except Exception as e:
                logger.error(f"Error setting up percussive filter: {e}")
                self._percussive_filter = None

    def _apply_vu_decay(self, dt: float):
        """Aplica decaimiento exponencial al VU meter."""
        decay_factor = np.exp(-dt / Constants.VU_DECAY_TIME_S)
        self._vu = float(decay_factor * self._vu)

    def _detect_onsets(self, x: np.ndarray, sr: float) -> Tuple[np.ndarray, float, float]:
        """
        Detecta onsets usando umbral adaptativo robusto.
        
        Returns:
            - indices de picos detectados
            - densidad de onsets (onsets/s)
            - gap máximo en ms
        """
        try:
            env, hop = env_onset(x)
            if env.size < 3:
                return np.array([], dtype=np.int32), 0.0, 0.0
            
            # Calcular novedad (diferencia positiva)
            nov = np.maximum(np.diff(env, prepend=env[0]), 0.0)
            
            # Umbral adaptativo usando MAD robusto
            sens = _read_units(self.card, "sens", *Constants.SENS_RANGE)
            median_nov = np.median(nov)
            mad_nov = _mad(nov)
            threshold = float(median_nov + sens * Constants.MAD_SCALE_FACTOR * mad_nov)
            
            # Encontrar candidatos
            candidates = np.where(nov > threshold)[0]
            
            if candidates.size < 3:
                return candidates.astype(np.int32), 0.0, 0.0
            
            # Filtrar máximos locales (evitar mesetas)
            peaks = []
            for i in candidates:
                window_start = max(0, i - 2)
                window_end = min(nov.size, i + 3)
                if nov[i] == np.max(nov[window_start:window_end]):
                    peaks.append(i)
            
            peaks = np.array(peaks, dtype=np.int32)
            
            # Calcular densidad en ventana reciente
            win_s = _read_units(self.card, "win_s", *Constants.WIN_S_RANGE)
            hop_s = hop / float(sr)
            win_frames = int(max(1, round(win_s / max(hop_s, Constants.EPS))))
            
            win_start = max(0, env.size - win_frames)
            recent_peaks = peaks[(peaks >= win_start) & (peaks < env.size)]
            
            density = float(recent_peaks.size) / max(Constants.EPS, win_frames * hop_s)
            
            # Calcular gap máximo
            if recent_peaks.size >= 2:
                gaps_frames = np.diff(recent_peaks)
                max_gap_ms = float(np.max(gaps_frames) * hop_s * 1000.0)
            else:
                max_gap_ms = win_s * 1000.0  # Sin onsets = gap completo
            
            return peaks, density, max_gap_ms
            
        except Exception as e:
            logger.error(f"Error in onset detection: {e}")
            return np.array([], dtype=np.int32), 0.0, 0.0

    def _calculate_flow_metric(self, density: float, max_gap_ms: float, 
                             percussive_bias: float) -> float:
        """Calcula métrica de flujo combinando densidad, gaps y sesgo percusivo."""
        try:
            # Componente de densidad
            dens_tgt = _read_units(self.card, "dens_tgt", *Constants.DENS_TGT_RANGE)
            density_score = float(np.clip(density / max(0.5, dens_tgt), 0.0, 1.0))
            
            # Penalización por gaps largos
            gap_max = _read_units(self.card, "gap_ms", *Constants.GAP_MS_RANGE)
            if gap_max <= 1.0:
                gap_score = 0.0
            else:
                gap_ratio = max_gap_ms / gap_max
                gap_score = float(np.clip(1.0 - (gap_ratio - 1.0), 0.0, 1.0))
            
            # Métrica combinada
            flow_value = density_score * gap_score * percussive_bias
            return float(np.clip(flow_value, 0.0, 1.0))
            
        except Exception as e:
            logger.error(f"Error calculating flow metric: {e}")
            return 0.0

    def _update_visual_smoothing(self, raw_value: float, dt: float):
        """Aplica suavizado visual configurable."""
        try:
            smooth = _read_units(self.card, "smooth", *Constants.SMOOTH_RANGE)
            tau_ms = 80.0 + (400.0 - 80.0) * (smooth ** 2)
            decay_factor = np.exp(-dt / (tau_ms / 1000.0))
            
            self._vu = (1.0 - decay_factor) * raw_value + decay_factor * self._vu
            self._vu = float(np.clip(self._vu, 0.0, 1.0))
            
        except Exception as e:
            logger.error(f"Error in visual smoothing: {e}")
            self._vu = raw_value

    def _update_status(self, density: float, max_gap_ms: float, 
                      percussive_bias: float, flow_value: float):
        """Actualiza status del módulo con información de debug."""
        try:
            dens_tgt = _read_units(self.card, "dens_tgt", *Constants.DENS_TGT_RANGE)
            gap_max = _read_units(self.card, "gap_ms", *Constants.GAP_MS_RANGE)
            
            status = (f"dens={density:.2f}/s tgt={dens_tgt:.1f} | "
                     f"maxGap={max_gap_ms:.0f}ms (≤{gap_max:.0f}) | "
                     f"perc={percussive_bias:.2f} | v={flow_value:.2f}")
            
            self.card.set_status(status)
            
        except Exception as e:
            logger.debug(f"Error updating status: {e}")

    def process(self, block, sr):
        """
        Procesa bloque de audio para detectar flujo rítmico.
        
        Args:
            block: Array de audio (mono/estéreo)
            sr: Sample rate en Hz
        """
        # Validaciones tempranas
        if not self._validate_inputs(block, sr):
            return
        
        try:
            # Convertir a mono
            x = mono(block).astype(np.float32, copy=False)
            if len(x) == 0:
                return
            
            dt = len(x) / float(sr)
            
            # Gate de silencio
            rms = float(np.sqrt(np.mean(x * x)) + Constants.EPS)
            if rms < Constants.SILENCE_THRESHOLD:
                self._apply_vu_decay(dt)
                return self._render(self._vu, dt)
            
            # Configurar filtro percusivo
            self._setup_percussive_filter(sr)
            
            # Análisis de onsets
            peaks, density, max_gap_ms = self._detect_onsets(x, sr)
            
            # Sesgo percusivo
            if self._percussive_filter:
                percussive_bias = self._percussive_filter.calculate_bias(x)
            else:
                percussive_bias = 0.7  # Valor conservador como fallback
            
            # Calcular métrica de flujo
            raw_flow = self._calculate_flow_metric(density, max_gap_ms, percussive_bias)
            
            # Aplicar suavizado visual
            self._update_visual_smoothing(raw_flow, dt)
            
            # Actualizar status para debug
            self._update_status(density, max_gap_ms, percussive_bias, self._vu)
            
            # Renderizar resultado
            self._render(self._vu, dt)
            
        except Exception as e:
            logger.error(f"Error processing audio block: {e}")
            # En caso de error, aplicar decay y continuar
            self._apply_vu_decay(dt if 'dt' in locals() else 0.02)
            self._render(self._vu, dt if 'dt' in locals() else 0.02)

    def _render(self, value: float, dt: float = 0.02):
        """Renderiza valor final y actualiza LED con histéresis."""
        try:
            # Actualizar valor principal
            self.card.set_value(value)
            
            # LED con histéresis y hold
            hold_on_ms = _read_units(self.card, "hold", *Constants.HOLD_RANGE)
            hold_on_s = float(np.clip(hold_on_ms / 1000.0, 0.05, 1.50))
            hold_off_s = 1.5 * hold_on_s
            
            # Lógica de histéresis
            if value >= Constants.LED_ON_THRESHOLD:
                self._ton += dt
                self._toff = 0.0
                if self._ton >= hold_on_s:
                    self._on = True
            elif value <= Constants.LED_OFF_THRESHOLD:
                self._toff += dt
                self._ton = 0.0
                if self._toff >= hold_off_s:
                    self._on = False
            
            self.card.set_led("flow", self._on)
            
            # Estado ON universal (thresholds y match)
            lo, hi = self.card.get_thresholds()
            lo = _norm01(lo)
            hi = _norm01(hi)
            if hi < lo:
                lo, hi = hi, lo
            
            match_required = _norm_match(self.card.get_match())
            
            in_range = lo <= value <= hi
            meets_match = (value * 100.0) >= (match_required - Constants.EPS)
            
            self.card.set_on(in_range and meets_match)
            
        except Exception as e:
            logger.error(f"Error in render: {e}")

    def reset(self):
        """Resetea el estado del módulo."""
        self._initialize_state()
        self._percussive_filter = None
        self._last_sr = None