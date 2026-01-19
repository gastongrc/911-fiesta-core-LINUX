# analyzers/hf_swell.py — PRE ATAQUE: HF SWELL v2025-08-27
import numpy as np

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
        def get_value(self, *a, **k): return 0.0
        def get_match(self): return 50.0
        def get_thresholds(self): return (0.0, 1.0)

EPS = 1e-12

def _mono(x):
    x = np.asarray(x)
    return x.astype(np.float32, copy=False) if x.ndim == 1 else x.mean(axis=1).astype(np.float32, copy=False)

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

class HFSwell:
    name = "HF SWELL"

    def __init__(self):
        self.card = ModuleCard(self.name)
        self.card.add_slider("win_s",   "Ventana (s)",        1.0, 4.0, 2.0)
        self.card.add_slider("ratio_ok","Crec. objetivo",     1.05, 3.0, 1.40)
        self.card.add_slider("smooth",  "Suavizado",          0.0, 0.95, 0.60)
        self.card.add_slider("hold",    "Hold ON (ms)",       80.0, 600.0, 220.0)
        self.card.add_led("swell", "Swell")

        self._vu = 0.0
        self._on = False
        self._ton = 0.0
        self._toff = 0.0

        # memorias espectrales (último frame y EMA corto/largo)
        self._last_mag = None
        self._ema_short = 0.0
        self._ema_long  = 0.0

    def _band_energy(self, mag2, freqs, f0, f1):
        i0 = int(np.searchsorted(freqs, f0))
        i1 = int(np.searchsorted(freqs, f1))
        i1 = max(i1, i0+1)
        return float(np.sum(mag2[i0:i1]))

    def process(self, block, sr):
        if block is None or sr is None or sr <= 0: return
        x = _mono(block); n = len(x)
        if n == 0: return
        dt = n / float(sr)

        # Gate silencio
        rms = float(np.sqrt(np.mean(x*x)) + EPS)
        if rms < 2e-4:
            a = np.exp(-dt / 0.18); self._vu *= a
            self._last_mag = None
            return self._render(float(np.clip(self._vu, 0.0, 1.0)), dt)

        # FFT
        nfft = 1
        while nfft < n: nfft <<= 1
        X = np.fft.rfft(x, nfft)
        mag = np.abs(X) + 1e-12
        mag2 = mag*mag
        freqs = np.fft.rfftfreq(nfft, 1.0/sr)

        # Spectral flux (agudos)
        if self._last_mag is None or self._last_mag.shape != mag.shape:
            flux = 0.0
        else:
            hi_mask = (freqs >= 2000.0) & (freqs <= 10000.0)
            diff = mag[hi_mask] - self._last_mag[hi_mask]
            diff[diff < 0] = 0.0
            flux = float(np.sum(diff) / (np.sum(mag[hi_mask]) + 1e-9))
            flux = float(np.clip(flux, 0.0, 1.0))
        self._last_mag = mag

        # Energía en banda alta (2–10 kHz) con EMA corto vs largo
        Ehi = self._band_energy(mag2, freqs, 2000.0, 10000.0)
        aS = np.exp(-dt / 0.25)
        aL = np.exp(-dt / 1.20)
        self._ema_short = (1.0 - aS)*Ehi + aS*self._ema_short
        self._ema_long  = (1.0 - aL)*Ehi + aL*self._ema_long

        ratio = float(np.clip((self._ema_short + 1e-9)/(self._ema_long + 1e-9), 0.0, 3.0))
        ratio_ok = float(np.clip(self.card.get_value("ratio_ok"), 1.01, 3.0))

        # Métrica: crecimiento de agudos (ratio) * flujo espectral
        v_raw = float(np.clip(((ratio - 1.0) / max(1e-6, ratio_ok - 1.0)) * flux, 0.0, 1.0))

        # Suavizado
        smooth = float(np.clip(self.card.get_value("smooth"), 0.0, 0.95))
        tau_ms = 80.0 + (600.0 - 80.0) * (smooth**2)
        a = np.exp(-dt / (tau_ms/1000.0))
        self._vu = (1.0 - a)*v_raw + a*self._vu
        v = float(np.clip(self._vu, 0.0, 1.0))

        try:
            self.card.set_status(f"ratio={ratio:.2f} flux={flux:.2f} v={v:.2f}")
        except Exception:
            pass

        self._render(v, dt)

    def _render(self, v, dt):
        self.card.set_value(v)
        hold_on  = float(np.clip(self.card.get_value("hold"), 80.0, 600.0))/1000.0
        hold_off = 1.5*hold_on
        thr_on, thr_off = 0.60, 0.50
        if v >= thr_on:
            self._ton += dt; self._toff = 0.0
            if self._ton >= hold_on: self._on = True
        elif v <= thr_off:
            self._toff += dt; self._ton = 0.0
            if self._toff >= hold_off: self._on = False
        self.card.set_led("swell", self._on)

        lo, hi = self.card.get_thresholds()
        lo = _norm01(lo); hi = _norm01(hi)
        if hi < lo: lo, hi = hi, lo
        mreq = _norm_match(self.card.get_match())
        self.card.set_on((lo <= v <= hi) and ((v*100.0) >= mreq - 1e-6))
