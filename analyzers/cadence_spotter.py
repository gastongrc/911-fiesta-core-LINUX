# analyzers/cadence_spotter.py – CADENCE SPOTTER (robusto) v2025-09-06
import numpy as np
import logging
from base_module import BaseModule
from module_card import ModuleCard

# Verificar dependencias críticas
try:
    from rhythm_tools import mono, env_onset, find_peaks, gaps_ms
except ImportError as e:
    raise ImportError(f"rhythm_tools module required but not found: {e}")

# Constantes documentadas
EPS = 1e-12
SILENCE_THRESHOLD_RMS = 2e-4      # -74 dBFS gate threshold for silence detection
LOW_DENSITY_PENALTY = 0.8         # Penalty factor for sparse onset density
MIN_ONSETS_FOR_ANALYSIS = 3       # Minimum onsets needed for cadence analysis
ONSET_DENSITY_THRESHOLD = 1.0     # Onsets per second threshold
VISUAL_SMOOTHING_MIN_MS = 80.0     # Minimum visual smoothing time
VISUAL_SMOOTHING_MAX_MS = 400.0    # Maximum visual smoothing time - OPTIMIZADO
SILENCE_DECAY_TIME = 0.18          # Time constant for VU decay during silence
LED_THRESHOLD_ON = 0.60            # Threshold for LED activation
LED_THRESHOLD_OFF = 0.50           # Threshold for LED deactivation
LED_HOLD_MULTIPLIER = 1.5          # Hold off time multiplier

# Configurar logging
logger = logging.getLogger(__name__)

def _norm01(v):
    """Normaliza valor a rango [0.0, 1.0], manejando porcentajes."""
    if v is None: 
        return 0.0
    try:
        v = float(v)
        if v > 1.5: 
            v *= 0.01    # 0..100 → 0..1
        return float(np.clip(v, 0.0, 1.0))
    except (ValueError, TypeError):
        logger.debug(f"Invalid value for normalization: {v}, using 0.0")
        return 0.0

def _norm_match(m):
    """Normaliza valor de match a rango [0.0, 100.0]."""
    try: 
        m = float(50.0 if m is None else m)
    except (ValueError, TypeError):
        logger.debug(f"Invalid match value: {m}, using 50.0")
        m = 50.0
    
    if 0.0 <= m < 1.0: 
        m *= 100.0
    elif m == 1.0:     
        m = 1.0
    return float(np.clip(m, 0.0, 100.0))

def _read_units(card, key, lo, hi):
    """Lee slider en unidades [lo..hi] o porcentaje 0..1 / 0..100 y lo mapea a [lo..hi]."""
    try: 
        v = float(card.get_value(key))
    except (ValueError, TypeError, AttributeError):
        logger.debug(f"Failed to read {key} from card, using midpoint")
        v = (lo + hi) * 0.5
    
    if 0.0 <= v <= 1.0:             # 0..1 → unidades
        return lo + (hi - lo) * v
    if 1.5 < v <= 100.0:            # 0..100 → unidades
        return lo + (hi - lo) * (np.clip(v, 0.0, 100.0) / 100.0)
    return float(np.clip(v, lo, hi))  # ya en unidades

def _mad(a):
    """Calcula Median Absolute Deviation de un array."""
    if len(a) == 0: 
        return 0.0
    med = np.median(a)
    return float(np.median(np.abs(a - med)) + EPS)

class CadenceSpotter(BaseModule):
    """
    Detector de cadencia rítmica usando análisis de onsets y MAD.

    Detecta patrones rítmicos regulares analizando la dispersión temporal
    de los onsets musicales usando Median Absolute Deviation (MAD).
    """

    name = "CADENCE SPOTTER"
    flag_name = "CADENCE_SPOTTER"  # V11: Flag para votación en BaseGolpe

    def __init__(self):
        super().__init__()
        self.card = ModuleCard(self.name)
        
        # Configuración de sliders - OPTIMIZADO
        self.card.add_slider("thr",     "Umbral pico",     0.05, 0.90, 0.35)
        self.card.add_slider("tol_ms",  "Tolerancia (ms)",  5.0, 120.0, 35.0)
        self.card.add_slider("smooth",  "Suavizado",        0.0,  0.90, 0.40)
        self.card.add_slider("hold",    "Hold ON (ms)",     50.0, 400.0, 100.0)
        self.card.add_slider("threshold", "Umbral ON",      0.0, 1.0, 0.55)
        self.card.add_led("ok", "Cadencia")

        # Estado interno
        self._vu = 0.0          # VU meter value
        self._on = False        # LED state
        self._ton = 0.0         # Time above threshold
        self._toff = 0.0        # Time below threshold
        self.detected = False   # V11: Flag para votación en BaseGolpe

        logger.info(f"{self.name} initialized successfully")

    def process(self, block, sr):
        """Procesa un bloque de audio para detectar cadencia rítmica."""
        if block is None or sr is None or sr <= 0: 
            return
            
        try:
            x = mono(block).astype(np.float32, copy=False)
        except Exception as e:
            logger.error(f"Failed to convert audio to mono: {e}")
            return
            
        n = len(x)
        if n == 0: 
            return
            
        dt = n / float(sr)

        # Gate de silencio – BASE GOLPE: VU→0
        rms = float(np.sqrt(np.mean(x*x)) + EPS)
        if rms < SILENCE_THRESHOLD_RMS:
            a = np.exp(-dt / SILENCE_DECAY_TIME)
            self._vu = float(a * self._vu)
            return self._render(float(np.clip(self._vu, 0.0, 1.0)), dt)

        # Leer parámetros de sliders (responden en vivo)
        thr     = _norm01(self.card.get_value("thr"))
        tol_ms  = _read_units(self.card, "tol_ms", 5.0, 120.0)
        smooth  = _read_units(self.card, "smooth", 0.0, 0.90)

        # Análisis de cadencia
        v_raw = self._analyze_cadence(x, sr, thr, tol_ms)

        # Suavizado visual (80..400 ms según slider) - OPTIMIZADO
        tau_ms = VISUAL_SMOOTHING_MIN_MS + (VISUAL_SMOOTHING_MAX_MS - VISUAL_SMOOTHING_MIN_MS) * (smooth ** 2)
        a = np.exp(-dt / (tau_ms/1000.0))
        self._vu = (1.0 - a) * v_raw + a * self._vu
        v = float(np.clip(self._vu, 0.0, 1.0))

        # Actualizar status informativo
        self._update_status(v, tol_ms)
        self._render(v, dt)

    def _analyze_cadence(self, x, sr, thr, tol_ms):
        """Analiza la cadencia del audio usando detección de onsets y MAD."""
        try:
            # Envolvente de onsets → picos → gaps en ms
            env, hop = env_onset(x)
            pk = find_peaks(env, float(np.clip(thr, 0.0, 1.0)))
            g = gaps_ms(pk, hop, sr)  # array en ms
        except Exception as e:
            logger.error(f"Failed to analyze onsets: {e}")
            return 0.0

        # Métrica robusta de cadencia: MAD alrededor del mediano
        if g.size < MIN_ONSETS_FOR_ANALYSIS:
            logger.debug(f"Insufficient onsets for analysis: {g.size} < {MIN_ONSETS_FOR_ANALYSIS}")
            return 0.0

        # Calcular cadencia usando MAD
        med = float(np.median(g))
        mad = _mad(g)
        v_raw = float(np.clip(1.0 - (mad / max(1.0, tol_ms)), 0.0, 1.0))

        # Penalizar densidad baja de onsets (evitar voz/pads)
        n = len(x)
        dens = float(g.size) / max(1.0, (n / sr))  # onsets por segundo aproximados
        if dens < ONSET_DENSITY_THRESHOLD:
            logger.debug(f"Low onset density detected: {dens:.2f} < {ONSET_DENSITY_THRESHOLD}")
            v_raw *= LOW_DENSITY_PENALTY

        return v_raw

    def _update_status(self, v, tol_ms):
        """Actualiza el status informativo del módulo."""
        try:
            # Obtener información de onsets para el status
            status_msg = f"v={v:.2f} | tol={tol_ms:.0f}ms"
            self.card.set_status(status_msg)
        except Exception as e:
            logger.debug(f"Failed to update status: {e}")

    def _render(self, v, dt=0.02):
        """Renderiza la salida visual y determina el estado ON."""
        # Actualizar VU meter
        self.card.set_value(v)

        # LED con histéresis unificada (no parpadea)
        threshold = _norm01(self.card.get_value("threshold"))
        thr_on = max(threshold, LED_THRESHOLD_ON)
        thr_off = min(threshold * 0.9, LED_THRESHOLD_OFF)  # 10% de histéresis
        
        hold_on = float(np.clip(_read_units(self.card, "hold", 
                                          VISUAL_SMOOTHING_MIN_MS, 
                                          VISUAL_SMOOTHING_MAX_MS)/1000.0, 0.05, 1.50))
        hold_off = LED_HOLD_MULTIPLIER * hold_on
        
        if v >= thr_on:
            self._ton += dt
            self._toff = 0.0
            if self._ton >= hold_on: 
                self._on = True
        elif v <= thr_off:
            self._toff += dt
            self._ton = 0.0
            if self._toff >= hold_off: 
                self._on = False
                
        self.card.set_led("ok", self._on)
        self.detected = self._on  # V11: Flag para votación

        # Estado ON del módulo (sistema unificado)
        self.card.set_on(self._on)

    def get_debug_info(self):
        """Retorna información de debug del estado interno."""
        return {
            'vu_level': self._vu,
            'led_state': self._on,
            'time_above_threshold': self._ton,
            'time_below_threshold': self._toff
        }