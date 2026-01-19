# analyzers/no_hits.py – BAJADA: ausencia de transitorios (calma)
# v2025-09-05-calibrated (HPF + env rápida + refrac real + match/threshold norm)
# v2025-10-02-OPTIMIZED: smooth default 0.25 → 0.40

import numpy as np

EPS = 1e-12

def _mono(x):
    x = np.asarray(x)
    return x.astype(np.float32, copy=False) if x.ndim == 1 else x.mean(axis=1).astype(np.float32, copy=False)

def _mad(a):
    if len(a) == 0: return 0.0
    m = np.median(a)
    return float(np.median(np.abs(a - m)) + 1e-12)

def _norm01(v):
    if v is None: return 0.0
    v = float(v)
    if v > 1.5: v *= 0.01
    return float(np.clip(v, 0.0, 1.0))

def _norm_match(m):
    try: m = float(50.0 if m is None else m)
    except: m = 50.0
    if 0.0 <= m <= 1.0: m *= 100.0
    return float(np.clip(m, 0.0, 100.0))

class NoHits:
    name = "NO HITS"

    def __init__(self):
        from module_card import ModuleCard
        self.card = ModuleCard(self.name)

        # Perillas calibradas
        self.card.add_slider("sens",    "Sensibilidad (×MAD)",  0.3,  2.0, 0.8)
        self.card.add_slider("refrac",  "Refractario (ms)",    20.0, 100.0, 40.0)
        self.card.add_slider("snr",     "Umbral silencio (dB)", 6.0, 24.0, 12.0)
        # CORRECCIÓN: smooth default 0.25 → 0.40
        self.card.add_slider("smooth",  "Suavizado",            0.0,  0.95, 0.40)
        try: 
            self.card.add_led("calm", "Calma")
        except Exception as e:
            print(f"Warning: No se pudo añadir LED 'calm': {e}")

        # Estados internos
        self._vu = 0.0
        self._lp120 = 0.0
        self._last_hit_time = -1.0
        
        # Buffer circular para análisis temporal más estable
        self._history_size = 10
        self._hits_history = np.zeros(self._history_size, dtype=np.float32)
        self._history_idx = 0

    def _lp1(self, x, sr, fc, state_name):
        """Filtro pasa-bajos de primer orden"""
        a = 1.0 - np.exp(-2.0*np.pi*fc/float(sr))
        y = np.empty_like(x, dtype=np.float32)
        s = getattr(self, state_name)
        for i, xi in enumerate(x):
            s = s + a*(xi - s)
            y[i] = s
        setattr(self, state_name, float(s))
        return y

    def _env_rms(self, x, sr, win_ms):
        """Envolvente RMS más robusta que valor absoluto medio"""
        w = max(1, int((win_ms/1000.0)*sr))
        if w <= 1: 
            return np.sqrt(x*x + EPS)
        
        x_sq = x * x
        k = np.ones(w, dtype=np.float32) / float(w)
        rms_sq = np.convolve(x_sq, k, mode="same")
        return np.sqrt(np.maximum(rms_sq, EPS))

    def _novelty_pos(self, env):
        """Derivada positiva (novedad)"""
        d = np.diff(env, prepend=env[0])
        return np.maximum(d, 0.0).astype(np.float32)

    def _apply_refrac_real(self, peaks, sr, refr_ms):
        """Refractario real: suprime picos cercanos temporalmente"""
        if len(peaks) == 0:
            return peaks
            
        refr_samples = int((refr_ms / 1000.0) * sr)
        if refr_samples <= 1:
            return peaks
            
        peak_indices = np.where(peaks > 0)[0]
        if len(peak_indices) == 0:
            return peaks
        
        suppressed = np.zeros_like(peaks)
        last_peak = -refr_samples - 1
        
        for idx in peak_indices:
            if idx - last_peak >= refr_samples:
                suppressed[idx] = peaks[idx]
                last_peak = idx
                
        return suppressed

    def _update_hits_history(self, hits_per_s):
        """Actualiza historial circular de hits para suavizado temporal"""
        self._hits_history[self._history_idx] = hits_per_s
        self._history_idx = (self._history_idx + 1) % self._history_size
        return float(np.mean(self._hits_history))

    def process(self, block, sr):
        if block is None or sr is None or sr <= 0: 
            return
            
        x = _mono(block)
        n = len(x)
        if n == 0: 
            return
            
        dt = n/float(sr)

        # Gate silencio por dBFS
        rms = float(np.sqrt(np.mean(x*x)) + EPS)
        lvl_db = 20.0 * np.log10(rms + EPS)
        snr_db = float(np.clip(self.card.get_value("snr"), 0.0, 60.0))
        
        if lvl_db < -snr_db:
            v_raw = 1.0
            status = f"silencio: {lvl_db:.1f} dBFS < -{snr_db:.1f} dB"
        else:
            # Detección de transitorios calibrada
            lp120 = self._lp1(x, sr, 120.0, "_lp120")
            hp = x - lp120
            env = self._env_rms(hp, sr, win_ms=6.0)
            d = self._novelty_pos(env)
            refr_ms = float(np.clip(self.card.get_value("refrac"), 10.0, 200.0))
            
            sens = float(np.clip(self.card.get_value("sens"), 0.1, 3.0))
            med = float(np.median(d))
            mad = _mad(d)
            thr = float(med + sens * 1.4826 * mad)

            peaks = (d > thr).astype(np.float32) * d
            peaks_refrac = self._apply_refrac_real(peaks, sr, refr_ms)
            
            hits = int(np.count_nonzero(peaks_refrac > 0))
            hits_per_s_raw = hits / max(dt, 1e-6)
            hits_per_s = self._update_hits_history(hits_per_s_raw)

            HREF = 1.5
            tnorm = float(np.clip(hits_per_s / HREF, 0.0, 1.2))
            v_raw = float(np.clip(1.0 - tnorm, 0.0, 1.0))

            status = f"lvl={lvl_db:.1f}dB | hits={hits_per_s:.2f}/s (raw:{hits_per_s_raw:.2f}) | thr={thr:.2e} | calma={v_raw:.2f}"

        # Suavizado visual mejorado
        smooth = float(np.clip(self.card.get_value("smooth"), 0.0, 0.95))
        tau_ms = 60.0 + (800.0 - 60.0) * (smooth ** 1.5)
        a = np.exp(-dt / (tau_ms / 1000.0))
        self._vu = (1.0 - a) * v_raw + a * self._vu
        v = float(np.clip(self._vu, 0.0, 1.0))

        # UI
        try: 
            self.card.set_status(status)
        except Exception as e:
            print(f"Warning: No se pudo actualizar status: {e}")

        self.card.set_value(v)
        
        try: 
            self.card.set_led("calm", v >= 0.5)
        except Exception as e:
            print(f"Warning: No se pudo actualizar LED: {e}")

        # MATCH + thresholds normalizados
        lo, hi = self.card.get_thresholds()
        lo = _norm01(lo)
        hi = _norm01(hi)
        if hi < lo: 
            lo, hi = hi, lo
        mreq = _norm_match(self.card.get_match())

        self.card.set_on((lo <= v <= hi) and ((v*100.0) >= mreq - 0.1))