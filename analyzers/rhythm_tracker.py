# analyzers/rhythm_tracker.py — RHYTHM TRACKER (IMPROVED) v2025-09-06
# Versión mejorada con mejor gestión de estado, optimización de memoria y configurabilidad
import numpy as np
import threading
import time
from typing import Optional, Tuple, Dict, Any

try:
    from module_card import ModuleCard
except Exception:
    class ModuleCard:
        def __init__(self, *a, **k): pass
        def add_slider(self, *a, **k): pass
        def add_led(self, *a, **k): pass
        def set_value(self, *a, **k): pass
        def set_led(self, *a, **k): pass
        def set_status(self, *a, **k): pass
        def set_on(self, *a, **k): pass
        def get_value(self, *a, **k): return 0
        def get_thresholds(self): return (0.0, 1.0)
        def get_match(self): return 50.0

# -------- Constantes mejoradas --------
class Config:
    MIN_SAMPLE_RATE = 8000
    MAX_SAMPLE_RATE = 192000
    TARGET_ANALYSIS_RATE = 100.0  # Hz para análisis temporal
    MAX_ANALYSIS_DURATION = 6.0   # segundos máximos para análisis
    MIN_SILENCE_DURATION = 0.1    # segundos mínimos antes de declarar silencio
    MAX_SILENCE_DURATION = 10.0   # segundos máximos de silencio continuo
    STATE_RESET_GAP = 0.5         # segundos de gap para reset de estado
    NOISE_FLOOR_ALPHA = 0.001     # velocidad de adaptación del piso de ruido
    
    # Rangos de BPM válidos
    MIN_BPM = 30.0
    MAX_BPM = 240.0
    
    # Parámetros de filtro
    LP_CUTOFF_HZ = 250.0
    NOVELTY_HARMONICS = [1.0, 0.5, 1/3, 0.25]  # Pesos para armónicos

# -------- Funciones helper mejoradas --------
def _mono(x: np.ndarray) -> np.ndarray:
    """Convierte a mono con validación de entrada"""
    x = np.asarray(x, dtype=np.float32)
    if x.ndim == 0:
        return np.array([float(x)], dtype=np.float32)
    elif x.ndim == 1:
        return x
    elif x.ndim == 2:
        return x.mean(axis=1 if x.shape[1] > x.shape[0] else 0).astype(np.float32)
    else:
        raise ValueError(f"Audio con {x.ndim} dimensiones no soportado")

def _mad(a: np.ndarray) -> float:
    """Median Absolute Deviation robusto"""
    if len(a) == 0:
        return 0.0
    a_clean = a[np.isfinite(a)]
    if len(a_clean) == 0:
        return 0.0
    m = np.median(a_clean)
    return float(np.median(np.abs(a_clean - m)) + 1e-12)

def _norm01(v: Optional[float]) -> float:
    """Normalización 0-1 con mejor manejo de casos edge"""
    if v is None or not np.isfinite(v):
        return 0.0
    v = float(v)
    if v > 1.5:  # Asumir 0-100 scale
        v *= 0.01
    return float(np.clip(v, 0.0, 1.0))

def _norm_match(m: Optional[float]) -> float:
    """Normalización de match percentage"""
    try:
        m = float(50.0 if m is None else m)
    except (TypeError, ValueError):
        m = 50.0
    
    if 0.0 <= m < 1.0:
        m *= 100.0
    elif m == 1.0:
        m = 100.0
    return float(np.clip(m, 0.0, 100.0))

def _read_slider_pct(card: ModuleCard, key: str) -> float:
    """Lee slider que puede venir 0..1 o 0..100. Devuelve [0..1]."""
    try:
        v = float(card.get_value(key))
    except (TypeError, ValueError):
        return 0.0
    
    if v > 1.5:
        v *= 0.01
    return float(np.clip(v, 0.0, 1.0))

def _read_slider_units(card: ModuleCard, key: str, lo: float, hi: float) -> float:
    """
    Lee slider robusto que puede venir: en unidades [lo..hi], o 0..1, o 0..100.
    Devuelve en unidades [lo..hi].
    """
    try:
        v = float(card.get_value(key))
    except (TypeError, ValueError):
        return (lo + hi) * 0.5
    
    # Si parece porcentaje normalized → mapear
    if 0.0 <= v <= 1.0:
        return lo + (hi - lo) * v
    # Si parece porcentaje 0-100 → mapear
    elif 1.0 < v <= 100.0:
        return lo + (hi - lo) * (np.clip(v, 0.0, 100.0) / 100.0)
    # Si está en rango razonable para las unidades, usar directo
    elif lo <= v <= hi:
        return float(v)
    # Si está fuera de rango, clampear
    else:
        return float(np.clip(v, lo, hi))

def _db_to_linear(db: float) -> float:
    """Convierte dB a escala lineal"""
    return 10.0 ** (db / 20.0)

class RhythmTracker:
    name = "RHYTHM TRACKER"

    def __init__(self):
        self.card = ModuleCard(self.name)
        
        # Sliders mejorados con más control
        self.card.add_slider("thr_x", "Umbral onsets (×σ)", 1.4, 4.0, 2.2)
        self.card.add_slider("win_s", "Ventana análisis (s)", 1.5, 6.0, 3.0)
        self.card.add_slider("drift", "Drift permitido (%)", 1.0, 12.0, 6.0)
        self.card.add_slider("hold", "Hold ON (ms)", 80.0, 600.0, 200.0)
        self.card.add_slider("smooth", "Suavizado", 0.0, 0.95, 0.60)
        
        # Nuevos sliders para mejor control
        self.card.add_slider("silence_thr", "Umbral silencio (dB)", -80, -40, -60)
        self.card.add_slider("novelty_env", "Ventana novedad (ms)", 4, 20, 8)
        self.card.add_slider("thr_on", "Umbral ON", 0.3, 0.8, 0.60)
        self.card.add_slider("thr_off", "Umbral OFF", 0.2, 0.7, 0.50)
        
        self.card.add_led("lock", "Tempo estable")
        self.card.add_led("silence", "Silencio detectado")

        # Estado interno protegido
        self._process_lock = threading.RLock()
        self._reset_state()
        
        # Estadísticas para debugging
        self._stats = {
            'rms': 0.0,
            'strength': 0.0,
            'bpm_stability': 0.0,
            'filter_state': 0.0,
            'samples_processed': 0
        }

    def _reset_state(self):
        """Reinicia todo el estado interno"""
        self._vu = 0.0
        self._lp_state = 0.0
        self._bpm_ref = 0.0
        self._bpm_ema = 0.0
        self._on = False
        self._ton = 0.0
        self._toff = 0.0
        self._last_process_time = time.time()
        self._noise_floor = 1e-6
        self._silence_duration = 0.0
        self._current_rms = 0.0
        self._last_strength = 0.0

    def _adaptive_downsample_rate(self, sr: float) -> int:
        """Calcula downsampling rate adaptativo para consistencia temporal"""
        # Mantener ~100Hz de resolución temporal mínima
        ds = max(1, int(sr / Config.TARGET_ANALYSIS_RATE))
        # Cap máximo a 20ms para evitar perder resolución temporal
        max_ds = int(0.020 * sr)
        return min(ds, max_ds)

    def _detect_audio_gap(self) -> bool:
        """Detecta si hay un gap significativo en el procesamiento"""
        current_time = time.time()
        gap = current_time - self._last_process_time
        self._last_process_time = current_time
        return gap > Config.STATE_RESET_GAP

    def _update_noise_floor(self, rms: float):
        """Actualiza estimación adaptativa del piso de ruido"""
        if rms > 0:
            self._noise_floor = (
                (1.0 - Config.NOISE_FLOOR_ALPHA) * self._noise_floor + 
                Config.NOISE_FLOOR_ALPHA * rms
            )

    def _silence_detection(self, rms: float, dt: float) -> bool:
        """Detección de silencio mejorada con umbral adaptativo"""
        # Obtener umbral desde slider (dB)
        silence_db = _read_slider_units(self.card, "silence_thr", -80, -40)
        silence_threshold = _db_to_linear(silence_db)
        
        # Umbral adaptativo basado en piso de ruido
        adaptive_threshold = max(silence_threshold, self._noise_floor * 2.0)
        
        is_silent = rms < adaptive_threshold
        
        if is_silent:
            self._silence_duration += dt
        else:
            self._silence_duration = 0.0
            
        # Solo declarar silencio después de duración mínima
        return (is_silent and 
                self._silence_duration >= Config.MIN_SILENCE_DURATION and
                self._silence_duration <= Config.MAX_SILENCE_DURATION)

    def _lp1(self, x: np.ndarray, sr: float, fc: float = None) -> np.ndarray:
        """Filtro LP de 1er orden con gestión mejorada de estado"""
        if fc is None:
            fc = Config.LP_CUTOFF_HZ
            
        # Detectar gaps y reiniciar estado si es necesario
        if self._detect_audio_gap() and len(x) > 0:
            self._lp_state = float(x[0])

        alpha = 1.0 - np.exp(-2.0 * np.pi * fc / float(sr))
        y = np.empty_like(x, dtype=np.float32)
        
        state = self._lp_state
        for i, xi in enumerate(x):
            state = state + alpha * (xi - state)
            y[i] = state
            
        self._lp_state = float(state)
        return y

    def _novelty(self, sig: np.ndarray, sr: float) -> np.ndarray:
        """Función de novedad mejorada con parámetros configurables"""
        # Obtener ventana desde slider
        ms_env = _read_slider_units(self.card, "novelty_env", 4, 20)
        win = max(1, int((ms_env / 1000.0) * sr))
        
        # Envelope con validación
        env = np.abs(sig)
        if len(env) == 0:
            return np.array([], dtype=np.float32)
            
        # Convolución eficiente
        kernel = np.ones(win, dtype=np.float32) / win
        if len(env) >= len(kernel):
            env = np.convolve(env, kernel, mode="same")
        
        # Diferencia positiva (novedad)
        nov = np.maximum(np.diff(env, prepend=env[0] if len(env) > 0 else 0.0), 0.0)
        
        # Umbral adaptativo robusto
        if len(nov) > 0:
            thr = float(np.median(nov) + 2.2 * 1.4826 * _mad(nov))
            nov = nov - thr
            nov[nov < 0.0] = 0.0
            
        return nov.astype(np.float32)

    def _periodicity_and_bpm(self, nov: np.ndarray, sr: float, win_s: float) -> Tuple[float, float]:
        """Análisis de periodicidad optimizado con mejor gestión de memoria"""
        if len(nov) == 0:
            return 0.0, 0.0
            
        # Downsampling adaptativo
        ds = self._adaptive_downsample_rate(sr)
        y = nov[::ds].astype(np.float32, copy=False)

        # Limitar duración para gestión de memoria
        max_samples = int(Config.MAX_ANALYSIS_DURATION * sr / ds)
        if len(y) > max_samples:
            y = y[-max_samples:]

        # Ventana de análisis adaptativa
        W = max(int(round(max(2.2, win_s) * sr / ds)), 140)
        if len(y) > W:
            y = y[-W:]
            
        # Validaciones básicas
        energy = float(np.sum(y))
        if energy < 1e-7 or np.all(y == 0.0):
            return 0.0, 0.0

        # Remover DC
        y = y - float(np.mean(y))
        if np.all(y == 0.0):
            return 0.0, 0.0

        # FFT optimizada - potencia de 2 exacta
        nfft = 1 << (len(y) - 1).bit_length()
        nfft = min(nfft, 8192)  # Cap para evitar uso excesivo de memoria
        
        try:
            Y = np.fft.rfft(y, nfft)
            ac = np.fft.irfft(np.abs(Y)**2, nfft)[:len(y)]
            
            # Normalización robusta
            ac_max = ac[0]
            if ac_max <= 0:
                return 0.0, 0.0
            r = ac / float(ac_max)
            
        except (MemoryError, ValueError):
            return 0.0, 0.0

        # Rango de lags para BPM válidos
        min_period_s = 60.0 / Config.MAX_BPM
        max_period_s = 60.0 / Config.MIN_BPM
        
        L = max(2, int(round(min_period_s * sr / ds)))
        H = min(len(r) - 1, int(round(max_period_s * sr / ds)))
        
        if H <= L:
            return 0.0, 0.0

        # Encontrar pico principal
        k = int(np.argmax(r[L:H])) + L
        
        # Refuerzo armónico mejorado
        harmonic_strength = 0.0
        total_weight = 0.0
        
        for h, weight in enumerate(Config.NOVELTY_HARMONICS, 1):
            harmonic_idx = h * k
            if harmonic_idx < len(r):
                harmonic_strength += weight * r[harmonic_idx]
                total_weight += weight
                
        if total_weight > 0:
            harmonic_strength /= total_weight

        # Prominencia local
        local_start = max(L, k - 2)
        local_end = min(H, k + 3)
        if local_end > local_start:
            local_region = r[local_start:local_end]
            prominence = max(0.0, float(np.max(local_region) - np.mean(local_region)))
        else:
            prominence = 0.0

        # Strength combinado
        strength = float(np.clip(0.6 * harmonic_strength + 0.4 * prominence, 0.0, 1.0))

        # Calcular BPM
        period_s = (k * ds) / float(sr)
        bpm = 60.0 / max(1e-6, period_s)
        bpm = float(np.clip(bpm, Config.MIN_BPM, Config.MAX_BPM))

        return strength, bpm

    def _update_stats(self, **kwargs):
        """Actualiza estadísticas internas para debugging"""
        self._stats.update(kwargs)
        self._stats['samples_processed'] += kwargs.get('block_size', 0)

    def process(self, block: Optional[np.ndarray], sr: Optional[float]):
        """Procesamiento principal thread-safe"""
        with self._process_lock:
            try:
                self._process_internal(block, sr)
            except Exception as e:
                # Log error pero no crashear
                try:
                    self.card.set_status(f"Error: {str(e)[:50]}...")
                except:
                    pass

    def _process_internal(self, block: Optional[np.ndarray], sr: Optional[float]):
        """Lógica de procesamiento interno"""
        # Validaciones de entrada
        if block is None or sr is None or sr <= 0:
            return
            
        if not (Config.MIN_SAMPLE_RATE <= sr <= Config.MAX_SAMPLE_RATE):
            self.card.set_status(f"Sample rate {sr} fuera de rango válido")
            return

        try:
            x = _mono(block)
        except ValueError as e:
            self.card.set_status(f"Error en conversión mono: {e}")
            return
            
        n = len(x)
        if n == 0:
            return
            
        dt = n / float(sr)

        # RMS con validación
        x_clean = x[np.isfinite(x)]
        if len(x_clean) == 0:
            return
            
        rms = float(np.sqrt(np.mean(x_clean * x_clean)) + 1e-12)
        self._current_rms = rms
        self._update_noise_floor(rms)

        # Detección de silencio mejorada
        is_silent = self._silence_detection(rms, dt)
        self.card.set_led("silence", is_silent)
        
        if is_silent:
            # Decay suave durante silencio
            decay_rate = np.exp(-dt / 0.18)
            self._vu = float(decay_rate * self._vu)
            self._bpm_ema = float(0.9 * self._bpm_ema)
            
            try:
                self.card.set_status(f"Silencio — v≈{self._vu:.2f} (dur: {self._silence_duration:.1f}s)")
            except:
                pass
                
            self._update_stats(rms=rms, block_size=n)
            return self._render(float(np.clip(self._vu, 0.0, 1.0)), bpm_est=0.0, dt=dt)

        # Leer sliders con validación
        try:
            thr_x = _read_slider_units(self.card, "thr_x", 1.4, 4.0)
            win_s = _read_slider_units(self.card, "win_s", 1.5, 6.0)
            driftp = _read_slider_units(self.card, "drift", 1.0, 12.0) / 100.0
            hold_s = _read_slider_units(self.card, "hold", 80.0, 600.0) / 1000.0
            smooth = _read_slider_units(self.card, "smooth", 0.0, 0.95)
        except Exception:
            # Valores por defecto si hay error
            thr_x, win_s, driftp, hold_s, smooth = 2.2, 3.0, 0.06, 0.2, 0.6

        # Procesamiento de audio en dos bandas
        try:
            low = self._lp1(x_clean, sr)
            high = x_clean - low
            
            # Novedad en ambas bandas
            nov_low = self._novelty(low, sr)
            nov_high = self._novelty(high, sr)
            
            # Combinar con ponderación (bombo + resto)
            nov = nov_low + 0.9 * nov_high
            
        except Exception:
            # Fallback a procesamiento simple
            nov = self._novelty(x_clean, sr)

        # Análisis de periodicidad
        if len(nov) > 0:
            strength, bpm = self._periodicity_and_bpm(nov, sr, win_s)
        else:
            strength, bpm = 0.0, 0.0
            
        self._last_strength = strength

        # EMA de BPM (más robusto)
        if bpm > 0 and Config.MIN_BPM <= bpm <= Config.MAX_BPM:
            alpha_bpm = 0.25
            self._bpm_ema = (1.0 - alpha_bmp) * self._bpm_ema + alpha_bpm * bpm
        else:
            self._bpm_ema *= 0.9  # Decay si BPM inválido

        # Referencia auto-adaptativa
        if self._bpm_ema > 0.0 and self._bpm_ref <= 0.0:
            self._bmp_ref = self._bpm_ema
        elif self._bpm_ema > 0.0:
            self._bpm_ref = 0.98 * self._bpm_ref + 0.02 * self._bpm_ema

        # Penalización gaussiana por drift
        if self._bpm_ref > 0.0 and self._bpm_ema > 0.0:
            rel_drift = abs(self._bpm_ema - self._bpm_ref) / max(self._bmp_ref, 1e-6)
            sigma = max(1e-3, driftp)
            drift_penalty = float(np.exp(-0.5 * (rel_drift / sigma) ** 2))
        else:
            drift_penalty = 0.0

        # VU combinado
        v_raw = float(np.clip(strength * drift_penalty, 0.0, 1.0))

        # Suavizado visual mejorado
        tau_ms = 80.0 + (600.0 - 80.0) * (smooth ** 2)
        alpha_smooth = np.exp(-dt / (tau_ms / 1000.0))
        self._vu = (1.0 - alpha_smooth) * v_raw + alpha_smooth * self._vu
        v = float(np.clip(self._vu, 0.0, 1.0))

        # Actualizar estadísticas
        bmp_stability = abs(self._bpm_ema - self._bpm_ref) if self._bpm_ref > 0 else 0.0
        self._update_stats(
            rms=rms,
            strength=strength,
            bpm_stability=bmp_stability,
            filter_state=self._lp_state,
            block_size=n
        )

        # Status informativo con más detalles de debugging
        try:
            br = f"{self._bpm_ref:.1f}" if self._bpm_ref > 0 else "—"
            be = f"{self._bpm_ema:.1f}" if self._bpm_ema > 0 else "—"
            status_msg = (
                f"RMS:{rms:.1e} | str={strength:.2f} | pen={drift_penalty:.2f} | v={v:.2f} | "
                f"BPM est:{be} ref:{br} | silence:{self._silence_duration:.1f}s"
            )
            self.card.set_status(status_msg)
        except:
            pass

        self._render(v, bmp_est=self._bpm_ema, dt=dt, hold_s=hold_s)

    def _render(self, v: float, bmp_est: float = 0.0, dt: float = 0.02, hold_s: float = 0.20):
        """Renderizado de salida con umbrales configurables"""
        self.card.set_value(v)

        # Umbrales desde sliders
        try:
            thr_on = _read_slider_units(self.card, "thr_on", 0.3, 0.8)
            thr_off = _read_slider_units(self.card, "thr_off", 0.2, 0.7)
        except:
            thr_on, thr_off = 0.60, 0.50

        # Asegurar coherencia de umbrales
        if thr_off >= thr_on:
            thr_off = thr_on - 0.05

        # Histeresis con hold configurable
        hold_on = float(np.clip(hold_s, 0.05, 1.50))
        hold_off = 1.5 * hold_on

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

        self.card.set_led("lock", self._on)

        # ON universal (match/min/max normalizados)
        try:
            lo, hi = self.card.get_thresholds()
            lo = _norm01(lo)
            hi = _norm01(hi)
            if hi < lo:
                lo, hi = hi, lo
            mreq = _norm_match(self.card.get_match())
            is_on = (lo <= v <= hi) and ((v * 100.0) >= mreq - 1e-6)
            self.card.set_on(is_on)
        except:
            pass

    def get_debug_stats(self) -> Dict[str, Any]:
        """Retorna estadísticas para debugging"""
        with self._process_lock:
            return self._stats.copy()

    def reset(self):
        """Reset público del módulo"""
        with self._process_lock:
            self._reset_state()