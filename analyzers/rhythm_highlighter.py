# analyzers/rhythm_highlighter.py – RHYTHM HIGHLIGHTER (BASE GOLPE) v2025-09-06
# VU alto = énfasis rítmico fuerte (picos claramente más altos que el promedio) + densidad suficiente.
import numpy as np
import logging
from scipy.signal import find_peaks as scipy_find_peaks
from base_module import BaseModule
from module_card import ModuleCard
from rhythm_tools import mono, env_onset, find_peaks

# Constantes matemáticas documentadas
EPS = 1e-12
MAD_TO_SIGMA = 1.4826  # Factor para convertir MAD (Median Absolute Deviation) a desviación estándar
MIN_ENV_SIZE = 5       # Mínimo tamaño de envelope para procesamiento válido
SILENCE_GATE_RMS = 2e-4  # Umbral RMS para gate de silencio
SILENCE_DECAY_TAU = 0.18  # Constante de tiempo para decay en silencio (segundos)

# Rangos de parámetros - OPTIMIZADO
SENS_RANGE = (1.4, 4.0)      # Sensibilidad de picos (×σ)
WIN_RANGE = (1.2, 4.0)       # Ventana temporal (segundos)
DENS_RANGE = (1.0, 8.0)      # Densidad objetivo (onsets/s)
RATIO_RANGE = (1.05, 3.5)    # Ratio de acento objetivo
SMOOTH_RANGE = (0.0, 0.95)   # Suavizado visual
HOLD_RANGE = (50.0, 400.0)   # Hold time (ms) - OPTIMIZADO

# Umbrales para LED
LED_THRESHOLD_ON = 0.60
LED_THRESHOLD_OFF = 0.50
HOLD_OFF_MULTIPLIER = 1.5

# Umbrales para estado ON
ON_THRESHOLD_TOLERANCE = 1e-6

def _norm01(v):
    """Normaliza un valor a rango [0,1], admitiendo entrada 0-100."""
    if v is None: 
        return 0.0
    try:
        v = float(v)
        if v > 1.5: 
            v *= 0.01  # convierte 0..100 → 0..1
        return float(np.clip(v, 0.0, 1.0))
    except (ValueError, TypeError):
        return 0.0

def _norm_match(m):
    """Normaliza valor de match, admitiendo diferentes escalas."""
    try: 
        m = float(50.0 if m is None else m)
    except (ValueError, TypeError): 
        m = 50.0
    
    if 0.0 <= m < 1.0: 
        m *= 100.0
    elif m == 1.0:     
        m = 1.0
    return float(np.clip(m, 0.0, 100.0))

def _mad(a):
    """Calcula Median Absolute Deviation de forma robusta."""
    if len(a) == 0: 
        return 0.0
    try:
        med = np.median(a)
        return float(np.median(np.abs(a - med)) + EPS)
    except Exception:
        return 0.0

def _safe_divide(numerator, denominator, default=0.0):
    """División segura con valor por defecto."""
    try:
        if abs(denominator) < EPS:
            return default
        return float(numerator / denominator)
    except (ValueError, TypeError, ZeroDivisionError):
        return default

class RhythmHighlighter(BaseModule):
    """
    Analizador de énfasis rítmico que detecta patrones rítmicos fuertes.

    Combina densidad de onsets con contraste de amplitudes para determinar
    el nivel de énfasis rítmico en tiempo real.
    """

    name = "RHYTHM HIGHLIGHTER"
    flag_name = "RHYTHM_HIGHLIGHTER"  # V11: Flag para votación en BaseGolpe

    def __init__(self):
        super().__init__()
        self.card = ModuleCard(self.name)
        
        # Configuración de parámetros
        self._setup_parameters()
        
        # Estado interno
        self._reset_state()
        
        # Logger opcional
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    def _setup_parameters(self):
        """Configura todos los parámetros del módulo."""
        # Sensibilidad de picos (×σ) sobre la novedad
        self.card.add_slider("sens_x", "Sensibilidad (×σ)", *SENS_RANGE, 2.2)
        
        # Ventana temporal para medir énfasis
        self.card.add_slider("win_s", "Ventana (s)", *WIN_RANGE, 2.0)
        
        # Densidad objetivo (onsets/s) mínima para considerarlo rítmico
        self.card.add_slider("dens_tgt", "Densidad obj (1/s)", *DENS_RANGE, 2.5)
        
        # Acento objetivo (ratio = top25%/mediana) → 1.6–2.2 suele ir bien
        self.card.add_slider("ratio_ok", "Acento objetivo", 1.1, 3.0, 1.6)
        
        # Visual - OPTIMIZADO
        self.card.add_slider("smooth", "Suavizado", *SMOOTH_RANGE, 0.40)
        self.card.add_slider("hold", "Hold ON (ms)", *HOLD_RANGE, 120.0)
        
        # LED de estado
        self.card.add_led("hl", "Énfasis")

    def _reset_state(self):
        """Reinicia el estado interno del módulo."""
        self._vu = 0.0
        self._on = False
        self._ton = 0.0
        self._toff = 0.0
        self._last_error = None
        self.detected = False  # V11: Flag para votación en BaseGolpe

    def _validate_inputs(self, block, sr):
        """Valida las entradas del procesamiento."""
        if block is None:
            self.logger.debug("Block is None")
            return False
        
        if sr is None or sr <= 0:
            self.logger.debug(f"Invalid sample rate: {sr}")
            return False
            
        return True

    def _handle_invalid_input(self, dt=0.02):
        """Maneja entradas inválidas manteniendo estado consistente."""
        # Decay suave del VU meter
        a = np.exp(-dt / SILENCE_DECAY_TAU)
        self._vu = float(a * self._vu)
        self._render(float(np.clip(self._vu, 0.0, 1.0)), dt)

    def _handle_processing_error(self, error, dt=0.02):
        """Maneja errores durante el procesamiento."""
        if self._last_error != str(error):
            self.logger.error(f"Processing error: {error}")
            self._last_error = str(error)
        
        # Mantener estado estable durante errores
        self._handle_invalid_input(dt)

    def _get_parameters(self):
        """Obtiene y valida todos los parámetros."""
        try:
            return {
                'sens_x': float(np.clip(self.card.get_value("sens_x"), *SENS_RANGE)),
                'win_s': float(np.clip(self.card.get_value("win_s"), *WIN_RANGE)),
                'dens_tgt': float(np.clip(self.card.get_value("dens_tgt"), *DENS_RANGE)),
                'ratio_ok': float(np.clip(self.card.get_value("ratio_ok"), *RATIO_RANGE)),
                'smooth': float(np.clip(self.card.get_value("smooth"), *SMOOTH_RANGE)),
                'hold': float(np.clip(self.card.get_value("hold"), *HOLD_RANGE))
            }
        except Exception as e:
            self.logger.debug(f"Error getting parameters: {e}")
            # Valores por defecto seguros
            return {
                'sens_x': 2.2, 'win_s': 2.0, 'dens_tgt': 2.5,
                'ratio_ok': 1.6, 'smooth': 0.40, 'hold': 120.0
            }

    def _compute_novelty(self, x, sens_x):
        """Calcula la función de novedad y detecta picos - OPTIMIZADO"""
        try:
            env, hop = env_onset(x)
            
            if env.size < MIN_ENV_SIZE:
                return np.array([], dtype=np.int32), hop, np.array([])
            
            # Función de novedad
            nov = np.maximum(np.diff(env, prepend=env[0]), 0.0)
            
            # Umbral robusto usando MAD
            mad_val = _mad(nov)
            median_val = np.median(nov)
            threshold = float(median_val + sens_x * MAD_TO_SIGMA * mad_val)
            
            # ✅ OPTIMIZADO: Usar scipy.signal.find_peaks (vectorizado)
            peaks, _ = scipy_find_peaks(nov, height=threshold, distance=3)
            
            return peaks.astype(np.int32), hop, nov
            
        except Exception as e:
            self.logger.error(f"Error in novelty computation: {e}")
            return np.array([], dtype=np.int32), 1, np.array([])

    def _analyze_rhythm_window(self, peaks, nov, hop, sr, win_s):
        """Analiza la ventana temporal más reciente para métricas rítmicas."""
        try:
            hop_s = _safe_divide(hop, sr, 1e-3)  # segundos por hop
            take_hops = int(max(1, round(_safe_divide(win_s, hop_s, 1))))
            
            # Índice de inicio de la ventana
            env_size = len(nov) if len(nov) > 0 else take_hops
            i0 = max(0, env_size - take_hops)
            
            # Filtrar picos en la ventana actual
            if peaks.size > 0:
                window_peaks = peaks[peaks >= i0]
                window_duration = take_hops * hop_s
                
                if window_peaks.size >= 1:
                    density = _safe_divide(window_peaks.size, window_duration, 0.0)
                    amplitudes = nov[window_peaks] if len(nov) > max(window_peaks) else np.array([])
                else:
                    density = 0.0
                    amplitudes = np.array([])
            else:
                density = 0.0
                amplitudes = np.array([])
                
            return density, amplitudes
            
        except Exception as e:
            self.logger.error(f"Error in rhythm window analysis: {e}")
            return 0.0, np.array([])

    def _compute_emphasis_ratio(self, amplitudes):
        """Calcula la métrica de énfasis: ratio top25% / mediana."""
        if amplitudes.size < 3:
            return 0.0
        
        try:
            median_amp = float(np.median(amplitudes) + EPS)  # Evitar división por cero
            
            # Top 25% de las amplitudes
            k = max(1, int(np.ceil(0.25 * amplitudes.size)))
            sorted_amps = np.sort(amplitudes)
            top_quarter_mean = float(np.mean(sorted_amps[-k:]))
            
            ratio = _safe_divide(top_quarter_mean, median_amp, 0.0)
            return ratio
            
        except Exception as e:
            self.logger.error(f"Error computing emphasis ratio: {e}")
            return 0.0

    def _compute_rhythm_score(self, density, ratio, params):
        """Calcula el score final de énfasis rítmico."""
        try:
            # Normalizar densidad contra objetivo
            v_density = np.clip(_safe_divide(density, max(0.5, params['dens_tgt']), 0.0), 0.0, 1.0)
            
            # Normalizar ratio contra objetivo
            ratio_range = max(EPS, params['ratio_ok'] - 1.0)
            v_ratio = np.clip(_safe_divide(ratio - 1.0, ratio_range, 0.0), 0.0, 1.0)
            
            # Score combinado
            raw_score = float(v_density * v_ratio)
            return np.clip(raw_score, 0.0, 1.0)
            
        except Exception as e:
            self.logger.error(f"Error computing rhythm score: {e}")
            return 0.0

    def _apply_smoothing(self, raw_score, smooth_param, dt):
        """Aplica suavizado temporal al score."""
        try:
            # Mapeo cuadrático para control más intuitivo del suavizado
            tau_ms = 80.0 + (400.0 - 80.0) * (smooth_param ** 2)
            tau_s = tau_ms / 1000.0
            
            # Filtro exponencial
            alpha = np.exp(-dt / max(tau_s, EPS))
            self._vu = (1.0 - alpha) * raw_score + alpha * self._vu
            
            return float(np.clip(self._vu, 0.0, 1.0))
            
        except Exception as e:
            self.logger.error(f"Error in smoothing: {e}")
            return float(np.clip(raw_score, 0.0, 1.0))

    def _update_status(self, density, ratio, params, final_score):
        """Actualiza el status del módulo para debugging."""
        try:
            status_msg = (f"dens={density:.2f}/s tgt={params['dens_tgt']:.1f} | "
                         f"ratio={ratio:.2f} (ok={params['ratio_ok']:.2f}) | "
                         f"v={final_score:.2f}")
            self.card.set_status(status_msg)
        except Exception:
            pass  # No crítico si falla el status

    def process(self, block, sr):
        """Procesa un bloque de audio para detectar énfasis rítmico."""
        # Validación de entradas
        if not self._validate_inputs(block, sr):
            self._handle_invalid_input()
            return

        try:
            # Conversión a mono
            x = mono(block).astype(np.float32, copy=False)
            n = len(x)
            if n == 0:
                return
            
            dt = _safe_divide(n, sr, 0.02)

            # Gate de silencio (BASE GOLPE: en stop cae)
            rms = float(np.sqrt(np.mean(x * x)) + EPS)
            if rms < SILENCE_GATE_RMS:
                a = np.exp(-dt / SILENCE_DECAY_TAU)
                self._vu = float(a * self._vu)
                return self._render(float(np.clip(self._vu, 0.0, 1.0)), dt)

            # Obtener parámetros
            params = self._get_parameters()

            # Computar novedad y picos
            peaks, hop, novelty = self._compute_novelty(x, params['sens_x'])

            # Analizar ventana temporal
            density, amplitudes = self._analyze_rhythm_window(
                peaks, novelty, hop, sr, params['win_s']
            )

            # Calcular métrica de énfasis
            ratio = self._compute_emphasis_ratio(amplitudes)

            # Score final
            raw_score = self._compute_rhythm_score(density, ratio, params)

            # Aplicar suavizado
            final_score = self._apply_smoothing(raw_score, params['smooth'], dt)

            # Actualizar status
            self._update_status(density, ratio, params, final_score)

            # Renderizar resultado
            self._render(final_score, dt)

        except Exception as e:
            self._handle_processing_error(e, _safe_divide(len(block) if block is not None else 0, sr, 0.02))

    def _render(self, v, dt=0.02):
        """Renderiza el resultado final y actualiza controles."""
        try:
            # Actualizar VU meter
            self.card.set_value(float(np.clip(v, 0.0, 1.0)))

            # LED con histéresis + HOLD
            params = self._get_parameters()
            hold_on_s = params['hold'] / 1000.0  # ms a segundos
            hold_off_s = HOLD_OFF_MULTIPLIER * hold_on_s

            if v >= LED_THRESHOLD_ON:
                self._ton += dt
                self._toff = 0.0
                if self._ton >= hold_on_s:
                    self._on = True
            elif v <= LED_THRESHOLD_OFF:
                self._toff += dt
                self._ton = 0.0
                if self._toff >= hold_off_s:
                    self._on = False

            self.card.set_led("hl", self._on)
            self.detected = self._on  # V11: Flag para votación

            # Estado ON universal (MATCH/Min/Max normalizados)
            lo, hi = self.card.get_thresholds()
            lo = _norm01(lo)
            hi = _norm01(hi)
            
            if hi < lo:
                lo, hi = hi, lo
                
            match_req = _norm_match(self.card.get_match())
            
            # Verificar si está en rango y cumple match
            in_range = lo <= v <= hi
            meets_match = (v * 100.0) >= (match_req - ON_THRESHOLD_TOLERANCE)
            
            self.card.set_on(in_range and meets_match)

        except Exception as e:
            self.logger.error(f"Error in render: {e}")

    def reset(self):
        """Reinicia el estado del módulo."""
        self._reset_state()
        self.logger.debug("RhythmHighlighter state reset")

    def get_debug_info(self):
        """Retorna información de debug del estado interno."""
        return {
            'vu': self._vu,
            'led_on': self._on,
            'hold_times': {'on': self._ton, 'off': self._toff},
            'last_error': self._last_error
        }