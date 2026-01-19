# analyzers/soft_peaks.py - SoftPeaks (transitorios MUY suaves)
# v2025-09-04: VU invertido (silencio/ausencia=100%), LED y ON/OFF ajustados
# v2025-10-02-OPTIMIZED: smooth default 0.5 → 0.60

import numpy as np
from collections import deque
from module_card import ModuleCard
from dsp_utils import mono

EPS = 1e-12
MIN_WINDOW_SAMPLES = 5
HISTORY_TIME_SECONDS = 2.5

class SoftPeaks:
    name = "SOFT PEAKS"

    def __init__(self):
        self.card = ModuleCard(self.name)
        # UI
        self.card.add_slider("sens",   "Sensibilidad",        0.2,  2.0, 0.9)
        self.card.add_slider("attack", "Ventana (ms)",          6,   40, 12)
        self.card.add_slider("kl",     "K bajo",               0.5,  2.0, 0.9)
        self.card.add_slider("kh",     "K alto",               1.2,  3.0, 1.8)
        # CORRECCIÓN: smooth default 0.5 → 0.60
        self.card.add_slider("smooth", "Suavizado",           0.0,  0.95, 0.60)
        self.card.add_slider("sil_db", "Gate silencio (dB)",  40.0, 70.0, 60.0)

        self.card.add_led("soft", "Transitorios leves")

        # Estado
        self._vu = 0.0
        self._p95_hist = deque()
        self._sr_cache = None
        self._debug_counter = 0

    @staticmethod
    def _rms_env(x: np.ndarray, sr: int, ms: float) -> np.ndarray:
        """Calcula envolvente RMS con ventana deslizante."""
        n = max(MIN_WINDOW_SAMPLES, int(sr * (ms / 1000.0)))
        if n % 2 == 0:
            n += 1
        
        s2 = x.astype(np.float32) ** 2
        w = np.ones(n, dtype=np.float32) / float(n)
        return np.sqrt(np.convolve(s2, w, mode="same") + EPS)

    @staticmethod
    def _normalize_01(v):
        """Normaliza valor a rango [0,1] con manejo robusto."""
        if v is None:
            return 0.0
        
        v = float(v)
        if v > 1.5:
            v *= 0.01
        return float(np.clip(v, 0.0, 1.0))

    @staticmethod
    def _normalize_match(val):
        """Normaliza valor de match con logica mejorada para 0..1 vs 0..100."""
        if val is None:
            return 50.0
        
        m = float(val)
        
        if 0.0 <= m < 1.0:
            m *= 100.0
        elif m == 1.0:
            m = 100.0
            
        return float(np.clip(m, 0.0, 100.0))

    def _update_history_size(self, sr: int):
        """Actualiza el tamano de la historia basado en el sample rate actual."""
        if self._sr_cache != sr:
            callback_rate_estimate = sr / 512
            new_maxlen = max(20, int(HISTORY_TIME_SECONDS * callback_rate_estimate))
            
            old_data = list(self._p95_hist) if self._p95_hist else []
            self._p95_hist = deque(old_data[-new_maxlen:], maxlen=new_maxlen)
            self._sr_cache = sr

    def _validate_parameters(self):
        """Valida y corrige parametros fuera de rango."""
        sens = float(np.clip(self.card.get_value("sens"), 0.1, 3.0))
        attack = float(np.clip(self.card.get_value("attack"), 4.0, 60.0))
        kl = float(np.clip(self.card.get_value("kl"), 0.1, 4.0))
        kh = float(np.clip(self.card.get_value("kh"), 0.1, 4.0))
        smooth = float(np.clip(self.card.get_value("smooth"), 0.0, 0.95))
        sil_db = float(np.clip(self.card.get_value("sil_db"), 20.0, 80.0))
        
        return sens, attack, kl, kh, smooth, sil_db

    def process(self, block, sr):
        """Procesa un bloque de audio para detectar transitorios suaves."""
        if block is None or sr is None or sr <= 0:
            return
            
        x = mono(block).astype(np.float32)
        n = x.size
        if n == 0:
            return
            
        dt = n / float(sr)
        
        self._update_history_size(sr)
        sens, attack_ms, kl, kh, smooth, sil_db = self._validate_parameters()

        # Gate de silencio
        rms = float(np.sqrt(np.mean(x * x)) + EPS)
        dbfs = 20.0 * np.log10(rms + EPS)
        
        if dbfs < -sil_db:
            self._vu *= np.exp(-dt / 0.18)
            inv_v = 1.0 - float(np.clip(self._vu, 0.0, 1.0))
            self._update_ui(inv_v)
            return

        # Envolventes rapida vs lenta
        env_f = self._rms_env(x, sr, attack_ms)
        env_s = self._rms_env(x, sr, max(16.0, attack_ms * 4.0))

        inc = env_f - env_s
        rel = np.maximum(0.0, inc) / (env_s + EPS)

        # Metrica del bloque
        t95 = float(np.percentile(rel, 95))
        tmax = float(np.max(rel))
        dens = float(np.mean(rel > 0.0))

        # Umbral adaptativo con historia
        self._p95_hist.append(t95)
        
        if len(self._p95_hist) >= 20:
            hist = np.array(self._p95_hist, dtype=np.float32)
            med = float(np.median(hist))
            mad = float(np.median(np.abs(hist - med))) + EPS
        else:
            med = float(np.median(rel))
            mad = float(np.median(np.abs(rel - med))) + EPS

        sigma = 1.4826 * mad
        baseline = med + sigma * (sens * kl)
        top = med + sigma * max(1.0, sens * kh)

        if sigma < EPS:
            baseline = med * 0.9
            top = med * 1.6 + EPS
            
        if top <= baseline:
            top = baseline + EPS

        # Map a VU [0..1]
        v_raw = float(np.clip((t95 - baseline) / (top - baseline), 0.0, 1.0))

        # Penalizacion por golpes fuertes
        if tmax > top * 1.5:
            v_raw *= 0.8

        # Adaptacion a densidad
        if dens < 0.03:
            v_raw *= 1.35
        elif dens > 0.25:
            v_raw *= 0.85
            
        v_raw = float(np.clip(v_raw, 0.0, 1.0))

        # Suavizado unificado (tau 80..600 ms)
        tau_ms = 80.0 + (600.0 - 80.0) * (smooth ** 2)
        alpha = np.exp(-dt / (tau_ms / 1000.0))
        self._vu = (1.0 - alpha) * v_raw + alpha * self._vu
        v = float(np.clip(self._vu, 0.0, 1.0))

        # INVERTIR VU PARA BAJADA
        inv_v = 1.0 - v

        self._update_ui(inv_v)

        # Debug
        self._debug_counter += 1
        if (self._debug_counter % 400) == 0:
            self._debug_counter = 0
            try:
                status = (f"inv_v={inv_v:.3f} | p95={t95:.4g} med={med:.4g} "
                         f"sigma={sigma:.4g} dens={dens:.2f} | {dbfs:.1f} dBFS")
                self.card.set_status(status)
            except (AttributeError, ValueError):
                pass

    def _update_ui(self, inv_v):
        """Actualiza la interfaz de usuario con el valor invertido."""
        self.card.set_value(inv_v)
        self.card.set_led("soft", inv_v > 0.75)

        # ON/OFF universal (MATCH + Min/Max) sobre el VU invertido
        lo, hi = self.card.get_thresholds()
        lo = self._normalize_01(lo)
        hi = self._normalize_01(hi)
        
        if hi < lo:
            lo, hi = hi, lo
            
        mreq = self._normalize_match(self.card.get_match())
        is_in_range = lo <= inv_v <= hi
        meets_match = (inv_v * 100.0) >= (mreq - EPS)
        
        self.card.set_on(is_in_range and meets_match)