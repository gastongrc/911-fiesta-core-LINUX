# analyzers/ramp_up.py — PRE ATAQUE: RAMP UP v2025-08-27
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
    if v > 1.5: v *= 0.01      # 0..100 → 0..1
    return float(np.clip(v, 0.0, 1.0))

def _norm_match(m):
    try: m = float(50.0 if m is None else m)
    except: m = 50.0
    if 0.0 <= m <= 1.0: m *= 100.0
    return float(np.clip(m, 0.0, 100.0))

class RampUp:
    name = "RAMP UP"

    def __init__(self):
        self.card = ModuleCard(self.name)
        # Detección de onsets
        self.card.add_slider("thr_x",   "Sens (×σ)",       1.4, 4.0, 2.2)
        self.card.add_slider("refrac",  "Refractario (ms)", 50.0, 200.0, 110.0)
        # Ventanas
        self.card.add_slider("win_short","Vent corta (s)", 1.0, 3.0, 1.4)
        self.card.add_slider("win_long", "Vent larga (s)", 2.5, 6.0, 3.5)
        # Criterio de aceleración
        self.card.add_slider("acc_req", "Aceleración req", 0.05, 0.50, 0.18)  # cuánto más chica debe ser IOI_short vs IOI_long (relativo)
        # Visual
        self.card.add_slider("smooth",  "Suavizado",       0.0, 0.95, 0.60)
        self.card.add_slider("hold",    "Hold ON (ms)",    80.0, 600.0, 220.0)
        self.card.add_led("up", "Up")

        self._t = 0.0
        self._events = deque()
        self._vu = 0.0
        self._on = False
        self._ton = 0.0
        self._toff = 0.0

    def _novelty_peaks(self, x, sr, kx=2.0, refr_ms=110.0):
        # envolvente MA 10ms → derivada positiva → umbral robusto
        win = max(1, int(0.010 * sr))
        env = np.abs(x)
        env = np.convolve(env, np.ones(win, dtype=np.float32)/win, mode="same")
        dpos = np.maximum(np.diff(env, prepend=env[0]), 0.0)
        thr = float(np.median(dpos) + kx * 1.4826 * _mad(dpos))
        cand = np.where(dpos > thr)[0]
        if cand.size == 0: return np.array([], dtype=np.int32)
        # refractario + máximo local ±2
        refr = int((refr_ms/1000.0)*sr)
        keep = []
        last = -10**9
        for i in cand:
            if i - last >= refr:
                i0 = max(0, i-2); i1 = min(dpos.size, i+3)
                if dpos[i] == np.max(dpos[i0:i1]):
                    keep.append(i); last = i
        return np.array(keep, dtype=np.int32)

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
        wS      = float(np.clip(self.card.get_value("win_short"), 1.0, 3.0))
        wL      = float(np.clip(self.card.get_value("win_long"),  2.0, 6.0))
        acc_req = float(np.clip(self.card.get_value("acc_req"), 0.02, 1.0))
        smooth  = float(np.clip(self.card.get_value("smooth"), 0.0, 0.95))

        # Onsets del bloque → eventos absolutos
        idx = self._novelty_peaks(x, sr, kx=thr_x, refr_ms=refr_ms)
        if idx.size:
            t0 = self._t - n/sr
            for i in idx:
                self._events.append(t0 + i/ sr)

        # Mantener solo ventana larga
        while self._events and (self._t - self._events[0]) > wL:
            self._events.popleft()

        # Si no hay suficientes, caer
        if len(self._events) < 4:
            a = np.exp(-dt / 0.20); self._vu *= a
            return self._render(float(np.clip(self._vu, 0.0, 1.0)), dt)

        ev = np.fromiter(self._events, dtype=np.float32)

        # IOIs por ventana
        def med_ioi_in(last_s):
            i0 = np.searchsorted(ev, self._t - last_s)
            seg = ev[i0:]
            if seg.size < 3: return 0.0, 0    # insuficiente
            ioi = np.diff(seg)
            return float(np.median(ioi)), ioi.size

        medS, nS = med_ioi_in(wS)
        medL, nL = med_ioi_in(wL)

        if medS <= 0.0 or medL <= 0.0 or nS < 2 or nL < 2:
            v_raw = 0.0; densS = 0.0
        else:
            # densidad y aceleración
            densS = float(nS / max(1e-6, wS))
            ratio = float((medL - medS) / medL)  # cuánto se achicó IOI (positivo = acelera)
            # normalizar: ratio >= acc_req → 1
            v_acc = float(np.clip(ratio / max(1e-6, acc_req), 0.0, 1.0))
            # pedir algo de densidad mínima para que sea PRE-ATAQUE real
            v_den = float(np.clip(densS / 3.0, 0.0, 1.0))  # 3/s ~ buen build
            v_raw = float(np.clip(0.6*v_acc + 0.4*v_den, 0.0, 1.0))

        # Suavizado
        tau_ms = 80.0 + (600.0 - 80.0) * (smooth**2)
        a = np.exp(-dt / (tau_ms/1000.0))
        self._vu = (1.0 - a)*v_raw + a*self._vu
        v = float(np.clip(self._vu, 0.0, 1.0))

        try:
            self.card.set_status(f"IOI_S={medS*1000:.0f}ms IOI_L={medL*1000:.0f}ms | densS={densS:.2f}/s | v={v:.2f}")
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
        self.card.set_led("up", self._on)

        # MATCH universal
        lo, hi = self.card.get_thresholds()
        lo = _norm01(lo); hi = _norm01(hi)
        if hi < lo: lo, hi = hi, lo
        mreq = _norm_match(self.card.get_match())
        self.card.set_on((lo <= v <= hi) and ((v*100.0) >= mreq - 1e-6))
