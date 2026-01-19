# analyzers/percussive_build.py — PRE ATAQUE: PERCUSSIVE BUILD v2025-08-27
import numpy as np
from collections import deque

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

class PercussiveBuild:
    name = "PERCUSSIVE BUILD"

    def __init__(self):
        self.card = ModuleCard(self.name)
        # Onsets
        self.card.add_slider("thr_x",   "Sens (×σ)",         1.4, 4.0, 2.2)
        self.card.add_slider("refrac",  "Refractario (ms)",  50.0, 200.0, 110.0)
        # Ventanas
        self.card.add_slider("win_short","Vent corta (s)",   0.8, 2.0, 1.0)
        self.card.add_slider("win_long", "Vent larga (s)",   2.0, 5.0, 3.0)
        # Ganancias
        self.card.add_slider("gain_d",  "Peso densidad",     0.2, 1.0, 0.5)
        self.card.add_slider("gain_e",  "Peso energía",      0.2, 1.0, 0.5)
        # Visual
        self.card.add_slider("smooth",  "Suavizado",         0.0, 0.95, 0.60)
        self.card.add_slider("hold",    "Hold ON (ms)",      80.0, 600.0, 220.0)
        self.card.add_led("build", "Build")

        self._t = 0.0
        self._events = deque()
        self._vu = 0.0
        self._on = False
        self._ton = 0.0
        self._toff = 0.0

        # energía per banda (EMA)
        self._ema_low = 0.0
        self._ema_hi  = 0.0

    def _novelty_peaks(self, x, sr, kx=2.0, refr_ms=110.0):
        win = max(1, int(0.010 * sr))
        env = np.abs(x)
        env = np.convolve(env, np.ones(win, dtype=np.float32)/win, mode="same")
        dpos = np.maximum(np.diff(env, prepend=env[0]), 0.0)
        thr = float(np.median(dpos) + kx * 1.4826 * _mad(dpos))
        cand = np.where(dpos > thr)[0]
        if cand.size == 0: return np.array([], dtype=np.int32)
        refr = int((refr_ms/1000.0)*sr)
        keep = []
        last = -10**9
        for i in cand:
            if i - last >= refr:
                i0 = max(0, i-2); i1 = min(dpos.size, i+3)
                if dpos[i] == np.max(dpos[i0:i1]):
                    keep.append(i); last = i
        return np.array(keep, dtype=np.int32)

    def _bands_energy(self, x, sr):
        # FFT rápida para medir low (40–200 Hz) + hi (2–8 kHz)
        n = len(x)
        nfft = 1
        while nfft < n: nfft <<= 1
        X = np.fft.rfft(x, nfft)
        mag2 = (X.real*X.real + X.imag*X.imag) + 1e-20
        freqs = np.fft.rfftfreq(nfft, 1.0/sr)
        def band(f0,f1):
            i0 = int(np.searchsorted(freqs, f0))
            i1 = int(np.searchsorted(freqs, f1))
            i1 = max(i1, i0+1)
            return float(np.sum(mag2[i0:i1]))
        low = band(40.0, 200.0)
        hi  = band(2000.0, 8000.0)
        return low, hi

    def process(self, block, sr):
        if block is None or sr is None or sr <= 0: return
        x = _mono(block); n = len(x)
        if n == 0: return
        dt = n / float(sr); self._t += dt

        # Gate silencio
        rms = float(np.sqrt(np.mean(x*x)) + EPS)
        if rms < 2e-4:
            a = np.exp(-dt / 0.18); self._vu *= a
            return self._render(float(np.clip(self._vu, 0.0, 1.0)), dt)

        # Sliders
        thr_x   = float(np.clip(self.card.get_value("thr_x"), 1.4, 4.0))
        refr_ms = float(np.clip(self.card.get_value("refrac"), 50.0, 300.0))
        wS      = float(np.clip(self.card.get_value("win_short"), 0.6, 2.5))
        wL      = float(np.clip(self.card.get_value("win_long"),  1.5, 6.0))
        gD      = float(np.clip(self.card.get_value("gain_d"), 0.1, 2.0))
        gE      = float(np.clip(self.card.get_value("gain_e"), 0.1, 2.0))
        smooth  = float(np.clip(self.card.get_value("smooth"), 0.0, 0.95))

        # Onsets → eventos
        idx = self._novelty_peaks(x, sr, kx=thr_x, refr_ms=refr_ms)
        if idx.size:
            t0 = self._t - n/sr
            for i in idx:
                self._events.append(t0 + i/ sr)
        while self._events and (self._t - self._events[0]) > wL:
            self._events.popleft()
        ev = np.fromiter(self._events, dtype=np.float32) if self._events else np.array([], dtype=np.float32)

        # Densidad corto vs largo
        def dens_in(last_s):
            if ev.size == 0: return 0.0
            i0 = np.searchsorted(ev, self._t - last_s)
            return float(max(0, ev[i0:].size - 1)) / max(1e-6, last_s)
        dS = dens_in(wS); dL = dens_in(wL)
        v_d = float(np.clip((dS - dL) / max(0.5, dL + 1e-6), 0.0, 1.0))

        # Energía percutiva (EMA) corto vs largo
        low, hi = self._bands_energy(x, sr)
        # Acumular EMA con dos constantes distintas (simula corta vs larga)
        aS = np.exp(-dt / 0.25)   # ~250 ms
        aL = np.exp(-dt / 1.20)   # ~1.2 s
        self._ema_low  = (1.0 - aL)*low + aL*self._ema_low
        ema_low_long = self._ema_low
        ema_low_short = (1.0 - aS)*low + aS*ema_low_long

        self._ema_hi   = (1.0 - aL)*hi + aL*self._ema_hi
        ema_hi_long = self._ema_hi
        ema_hi_short = (1.0 - aS)*hi + aS*ema_hi_long

        # ratio corto/largo (crecimiento)
        r_low = float(np.clip((ema_low_short + 1e-9)/(ema_low_long + 1e-9), 0.0, 3.0))
        r_hi  = float(np.clip((ema_hi_short  + 1e-9)/(ema_hi_long  + 1e-9), 0.0, 3.0))
        v_e = float(np.clip(0.5*(r_low - 1.0) + 0.5*(r_hi - 1.0), 0.0, 1.0))

        v_raw = float(np.clip(gD*v_d + gE*v_e, 0.0, 1.0))

        # Suavizado
        tau_ms = 80.0 + (600.0 - 80.0) * (smooth**2)
        a = np.exp(-dt / (tau_ms/1000.0))
        self._vu = (1.0 - a)*v_raw + a*self._vu
        v = float(np.clip(self._vu, 0.0, 1.0))

        try:
            self.card.set_status(f"dS={dS:.2f}/s dL={dL:.2f}/s | rL={r_low:.2f} rH={r_hi:.2f} | v={v:.2f}")
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
        self.card.set_led("build", self._on)

        lo, hi = self.card.get_thresholds()
        lo = _norm01(lo); hi = _norm01(hi)
        if hi < lo: lo, hi = hi, lo
        mreq = _norm_match(self.card.get_match())
        self.card.set_on((lo <= v <= hi) and ((v*100.0) >= mreq - 1e-6))
