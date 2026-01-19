# analyzers/pattern_lock.py – PATTERN LOCK (AUTO-LOCK, sin grabar) v2025-08-27r1
# Compatible con ModuleCard SIN add_toggle (usa slider 0/1 "auto" como fallback).
import numpy as np

# --- UI bridge seguro ---
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

# ---------- helpers ----------
def _mono(x):
    x = np.asarray(x)
    return x.astype(np.float32, copy=False) if x.ndim == 1 else x.mean(axis=1).astype(np.float32, copy=False)

def _norm01(v):
    if v is None: return 0.0
    v = float(v)
    if v > 1.5: v *= 0.01  # 0..100 → 0..1
    return float(np.clip(v, 0.0, 1.0))

def _norm_match(m):
    try: m = float(50.0 if m is None else m)
    except: m = 50.0
    if 0.0 <= m < 1.0: m *= 100.0
    elif m == 1.0:     m = 1.0
    return float(np.clip(m, 0.0, 100.0))

def _resample_to(v: np.ndarray, L: int) -> np.ndarray:
    v = np.asarray(v, dtype=np.float32).ravel()
    if v.size == 0: return np.zeros(L, dtype=np.float32)
    if v.size == L: return v.copy()
    xp = np.linspace(0.0, 1.0, v.size, dtype=np.float32)
    xq = np.linspace(0.0, 1.0, L,      dtype=np.float32)
    return np.interp(xq, xp, v).astype(np.float32)

def _env20ms(x: np.ndarray, sr: int) -> np.ndarray:
    win = max(1, int(0.020 * sr))
    c = np.cumsum(np.insert(np.abs(x), 0, 0.0))
    sm = (c[win:] - c[:-win]) / float(win)
    return sm.astype(np.float32)

def _znorm(v: np.ndarray) -> np.ndarray:
    v = v.astype(np.float32, copy=False)
    v = v - float(np.mean(v))
    n = float(np.linalg.norm(v)) + EPS
    return v / n

def _xcorr_circ_max(a: np.ndarray, b: np.ndarray) -> float:
    L = int(len(a))
    nfft = 1
    while nfft < L: nfft <<= 1
    A = np.fft.rfft(a, nfft)
    B = np.fft.rfft(b, nfft)
    corr = np.fft.irfft(A * np.conj(B), nfft)[:L]
    return float(np.clip(np.max(corr), -1.0, 1.0))

def _sim_with_warp(ref_vec: np.ndarray, cur_vec: np.ndarray, warp_pct: float) -> float:
    L = len(ref_vec)
    w = float(np.clip(warp_pct, 0.0, 0.20))
    scales = [1.0 - w, 1.0 - 0.5*w, 1.0, 1.0 + 0.5*w, 1.0 + w]
    best = -1.0
    for s in scales:
        Ls = max(8, int(round(L * s)))
        c = _resample_to(cur_vec, Ls)
        c = _resample_to(c, L)
        c = _znorm(c)
        sim = _xcorr_circ_max(ref_vec, c)
        if sim > best: best = sim
    return float(best)

# ---------- módulo ----------
class PatternLock:
    name = "PATTERN LOCK"
    flag_name = "PATTERN_LOCK"  # V11: Flag para votación en BaseGolpe

    def __init__(self):
        self.card = ModuleCard(self.name)

        # UI: si no hay add_toggle, creo slider 0/1 "auto" (por defecto en 1 = auto-lock ON)
        add_tgl = getattr(self.card, "add_toggle", None)
        if callable(add_tgl):
            add_tgl("auto", "Auto-lock")
            self._auto_is_toggle = True
        else:
            self.card.add_slider("auto", "Auto-lock (0/1)", 0.0, 1.0, 1.0)
            self._auto_is_toggle = False

        self.card.add_slider("win_s",  "Ventana (s)",         0.8, 3.0, 1.6)
        self.card.add_slider("warp",   "Tolerancia warp (%)", 0.0, 12.0, 6.0)
        self.card.add_slider("cap",    "Umbral captura",      0.70, 0.95, 0.86)
        # OPTIMIZADO: hold y smooth
        self.card.add_slider("hold",   "Hold ON (ms)",        50.0, 400.0, 120.0)
        self.card.add_slider("smooth", "Suavizado",           0.0,  0.80, 0.35)
        self.card.add_led("lock", "Match")

        # estado de audio / template - OPTIMIZADO
        self._sr = 0
        self._cap_s = 5.0  # Reducido de 8.0 a 5.0
        self._buf = None
        self._widx = 0
        self._filled = 0
        self._vec_len = 64  # Reducido de 128 a 64

        self._ref = None
        self._prev_vec = None
        self._vu = 0.0

        # histeresis LED
        self._on = False
        self._ton = 0.0
        self._toff = 0.0
        self.detected = False  # V11: Flag para votación en BaseGolpe

    # ----- ring buffer -----
    def _ensure_buf(self, sr):
        if sr != self._sr or self._buf is None:
            self._sr = int(sr)
            cap = max(1, int(self._cap_s * self._sr))
            self._buf = np.zeros(cap, dtype=np.float32)
            self._widx = 0
            self._filled = 0

    def _write(self, x):
        if x.size == 0: return
        n = x.size; cap = self._buf.size
        i = 0
        while i < n:
            space = cap - self._widx
            k = min(space, n - i)
            self._buf[self._widx:self._widx+k] = x[i:i+k]
            self._widx = (self._widx + k) % cap
            self._filled = min(cap, self._filled + k)
            i += k

    def _recent(self, samples):
        samples = int(max(1, samples))
        take = min(samples, self._filled)
        if take <= 0: return np.zeros(0, dtype=np.float32)
        cap = self._buf.size
        start = (self._widx - take) % cap
        if start + take <= cap:
            return self._buf[start:start+take].copy()
        a = self._buf[start:]
        b = self._buf[:(start + take) % cap]
        return np.concatenate([a, b], axis=0)

    # ----- núcleo -----
    def process(self, block, sr):
        try:
            if block is None or sr is None or sr <= 0: return
            x = _mono(block); n = len(x)
            if n == 0: return
            self._ensure_buf(sr)
            self._write(x)
            dt = n / float(sr)

            # Gate de silencio → BASE GOLPE: VU hacia 0
            rms = float(np.sqrt(np.mean(x*x)) + EPS)
            if rms < 2e-4:
                a = np.exp(-dt / 0.18)
                self._vu = float(a * self._vu)
                self._prev_vec = None
                return self._render(float(np.clip(self._vu, 0.0, 1.0)), dt)

            # Leer controles (toggle o slider 0/1)
            v_auto = self.card.get_value("auto")
            auto = bool(v_auto) if isinstance(v_auto, (bool, int)) else (float(v_auto) > 0.5)

            win_s  = float(np.clip(self.card.get_value("win_s"), 0.8, 3.0))
            warp   = float(np.clip(self.card.get_value("warp"),  0.0, 12.0)) * 0.01
            cap_t  = float(np.clip(self.card.get_value("cap"),   0.70, 0.95))
            smooth = float(np.clip(self.card.get_value("smooth"), 0.0, 0.80))

            # Ventana actual → envolvente → vector normalizado
            Lsamp = max(1, int(win_s * sr))
            wav = self._recent(Lsamp)
            if wav.size < int(0.4 * sr):
                return  # aún no hay suficiente ventana

            env = _env20ms(wav, sr)
            cur = _znorm(_resample_to(env, self._vec_len))

            # -------- AUTO-LOCK ----------
            if auto:
                sim_prev = None
                if self._prev_vec is not None and len(self._prev_vec) == len(cur):
                    sim_prev = _sim_with_warp(self._prev_vec, cur, warp)
                self._prev_vec = cur

                if self._ref is None and (sim_prev is not None) and (sim_prev >= cap_t):
                    self._ref = cur.copy()

                if self._ref is not None and sim_prev is not None and sim_prev >= (cap_t - 0.08):
                    beta = 0.10
                    self._ref = _znorm((1.0 - beta)*self._ref + beta*cur)

            # -------- Similitud contra referencia ----------
            if self._ref is not None:
                sim = _sim_with_warp(self._ref, cur, warp)  # [-1..1]
                match01 = 0.5 * (sim + 1.0)                 # → [0..1]
                v_raw = float(np.clip(match01, 0.0, 1.0))
            else:
                v_raw = 0.0
                sim = 0.0

            # Suavizado visual (80..400 ms) - OPTIMIZADO
            tau_ms = 80.0 + (400.0 - 80.0) * (smooth ** 2)
            a_s = np.exp(-dt / (tau_ms/1000.0))
            self._vu = (1.0 - a_s) * v_raw + a_s * self._vu
            v = float(np.clip(self._vu, 0.0, 1.0))

            # Status
            try:
                have = self._ref is not None
                sp = f"{sim:.2f}" if have else "–"
                self.card.set_status(f"AUTO:{int(auto)} | win:{win_s:.1f}s | warp:{warp*100:.1f}% | cap:{cap_t:.2f} | sim:{sp} | v:{v:.2f}")
            except Exception:
                pass

            self._render(v, dt)

        except Exception:
            pass

    def _render(self, v, dt=0.02):
        self.card.set_value(v)

        # LED con histeresis y HOLD desde slider - OPTIMIZADO
        hold_on  = float(np.clip(self.card.get_value("hold"), 50.0, 400.0)) / 1000.0
        hold_off = 1.5 * hold_on
        thr_on, thr_off = 0.65, 0.55
        if v >= thr_on:
            self._ton += dt; self._toff = 0.0
            if self._ton >= hold_on: self._on = True
        elif v <= thr_off:
            self._toff += dt; self._ton = 0.0
            if self._toff >= hold_off: self._on = False
        self.card.set_led("lock", self._on)
        self.detected = self._on  # V11: Flag para votación

        # ON universal (MATCH/Min/Max normalizados)
        lo, hi = self.card.get_thresholds()
        lo = _norm01(lo); hi = _norm01(hi)
        if hi < lo: lo, hi = hi, lo
        mreq = _norm_match(self.card.get_match())
        self.card.set_on((lo <= v <= hi) and ((v * 100.0) >= mreq - EPS))