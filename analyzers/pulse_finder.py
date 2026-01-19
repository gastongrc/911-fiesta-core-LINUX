# analyzers/pulse_finder.py — PULSE FINDER (BASE GOLPE) v2025-09-06 MINIMAL MOD
# VU alto = pulso/periodicidad fuerte CONSTANTE (electrónica, reggaeton)
import numpy as np
from collections import deque

# --- UI bridge ---
try:
    from module_card import ModuleCard
except Exception:
    class ModuleCard:
        def __init__(self, *a, **k): pass
        def add_slider(self, *a, **k): pass
        def add_led(self, *a, **k): pass
        def set_value(self, *a, **k): pass
        def set_led(self, *a, **k): pass
        def set_on(self, *a, **k): pass
        def set_status(self, *a, **k): pass
        def get_value(self, *a, **k): return 0
        def get_thresholds(self): return (0.0, 1.0)
        def get_match(self): return 50.0

# -------- helpers --------
def _mono(x):
    x = np.asarray(x)
    return x.astype(np.float32, copy=False) if x.ndim == 1 else x.mean(axis=1).astype(np.float32, copy=False)

def _mad(a):
    m = np.median(a); return float(np.median(np.abs(a - m)) + 1e-12)

def _norm01(v):
    if v is None: return 0.0
    v = float(v)
    if v > 1.5: v *= 0.01   # 0..100 → 0..1
    return float(np.clip(v, 0.0, 1.0))

def _norm_match(m):
    try: m = float(50.0 if m is None else m)
    except: m = 50.0
    if 0.0 <= m < 1.0: m *= 100.0
    elif m == 1.0:     m = 1.0
    return float(np.clip(m, 0.0, 100.0))

class PulseFinder:
    name = "PULSE FINDER"

    def __init__(self):
        self.card = ModuleCard(self.name)
        # Sliders (IGUALES AL ORIGINAL + 1 nuevo)
        self.card.add_slider("thr_x",   "Umbral onsets (×σ)",  1.4, 4.0, 2.0)    # Ligeramente más sensible
        self.card.add_slider("win_s",   "Ventana (s)",         1.5, 6.0, 2.5)    # Ventana más corta
        self.card.add_slider("refrac",  "Refractario (ms)",    60.0, 400.0, 120.0) # Más rápido
        self.card.add_slider("smooth",  "Suavizado",           0.0,  0.95, 0.50)   # Un poco menos
        self.card.add_slider("consistency", "Req. Consistencia", 0.0, 1.0, 0.6)   # NUEVO para patrón constante
        
        self.card.add_led("pulse", "Pulso detectado")
        self.card.add_led("constant", "Patrón constante") # NUEVO LED

        # estado (IGUAL AL ORIGINAL + consistencia)
        self._vu = 0.0
        self._t  = 0.0
        self._lp_state = 0.0
        self._on = False
        self._constant_pattern = False  # NUEVO
        self._ton = 0.0
        self._toff = 0.0
        self._last_bpm = 0.0
        
        # NUEVO: Para medir consistencia del patrón
        self._bpm_history = deque(maxlen=10)

    # LP 1er orden (IDÉNTICO AL ORIGINAL)
    def _lp1(self, x, sr, fc=250.0):
        a = 1.0 - np.exp(-2.0*np.pi*fc/float(sr))
        y = np.empty_like(x, dtype=np.float32)
        s = self._lp_state
        for i, xi in enumerate(x):
            s = s + a*(xi - s)
            y[i] = s
        self._lp_state = float(s)
        return y

    # IDÉNTICO AL ORIGINAL
    def _novelty(self, sig, sr, ms_env=8.0, k=2.0):
        win = max(1, int((ms_env/1000.0) * sr))
        env = np.abs(sig)
        env = np.convolve(env, np.ones(win, dtype=np.float32)/win, mode="same")
        nov = np.maximum(np.diff(env, prepend=env[0]), 0.0)
        thr = float(np.median(nov) + k * 1.4826 * _mad(nov))
        nov = nov - thr
        nov[nov < 0.0] = 0.0
        return nov

    # IDÉNTICO AL ORIGINAL
    def _periodicity(self, nov, sr, win_s):
        ds = max(1, int(0.010 * sr))
        y  = nov[::ds].astype(np.float32, copy=False)

        W = max(int(round(max(2.2, win_s) * sr / ds)), 140)
        if len(y) > W: y = y[-W:]
        if float(np.sum(y)) < 1e-7 or np.all(y == 0.0):
            return 0.0, 0.0

        y = y - float(np.mean(y))
        if np.all(y == 0.0):
            return 0.0, 0.0

        nfft = 1
        while nfft < 2*len(y): nfft <<= 1
        Y = np.fft.rfft(y, nfft)
        ac = np.fft.irfft(np.abs(Y)**2, nfft)[:len(y)]
        r  = ac / (float(ac[0]) + 1e-12)

        # MODIFICADO: Rango más enfocado en música electrónica (75-160 BPM)
        L = max(2, int(round(0.375 * sr / ds)))  # ~160 BPM
        H = min(len(r)-1, int(round(0.8 * sr / ds)))   # ~75 BPM
        if H <= L:
            return 0.0, 0.0

        k = int(np.argmax(r[L:H])) + L
        norm_h = 1.0 + 0.5 + (1/3) + 0.25
        s_h = r[k]
        if 2*k < len(r): s_h += 0.5  * r[2*k]
        if 3*k < len(r): s_h += (1/3) * r[3*k]
        if 4*k < len(r): s_h += 0.25 * r[4*k]
        s_h /= norm_h
        local = r[max(L, k-2):min(H, k+3)]
        prom  = max(0.0, float(np.max(local) - np.mean(local)))
        strength = float(np.clip(0.6*s_h + 0.4*prom, 0.0, 1.0))

        period_s = (k * ds) / float(sr)
        bpm = 60.0 / max(1e-6, period_s)
        return strength, bpm

    # NUEVO: Evalúa si el patrón es constante
    def _evaluate_constant_pattern(self, bpm, strength):
        # Agregar BPM al historial
        if 75 <= bpm <= 165:  # Solo BPMs válidos
            self._bpm_history.append(bpm)
        
        # Necesitamos al menos 5 mediciones para evaluar consistencia
        if len(self._bpm_history) < 5:
            return False, 0.0
        
        # Calcular variabilidad del BPM
        recent_bpms = list(self._bpm_history)
        bpm_std = np.std(recent_bpms)
        bpm_mean = np.mean(recent_bpms)
        
        # Coeficiente de variación (menor = más constante)
        cv = bpm_std / max(bpm_mean, 1.0)
        consistency_score = np.exp(-cv * 8.0)  # 0=variable, 1=constante
        
        # Verificar que está en rangos de música electrónica/reggaeton
        is_electronic_range = (
            (90 <= bpm_mean <= 110) or   # Reggaeton
            (120 <= bpm_mean <= 135) or  # House/EDM
            (140 <= bpm_mean <= 150)     # Trap
        )
        
        # Requiere consistencia + rango electrónico + fuerza mínima
        is_constant = (
            consistency_score > 0.7 and
            is_electronic_range and
            strength > 0.3
        )
        
        return is_constant, consistency_score

    # CASI IDÉNTICO AL ORIGINAL + validación de patrón constante
    def process(self, block, sr):
        try:
            if block is None or sr is None or sr <= 0: return
            x = _mono(block)
            n = len(x)
            if n == 0: return
            dt = n / float(sr); self._t += dt

            # Gate de silencio (IDÉNTICO)
            rms = float(np.sqrt(np.mean(x*x)) + 1e-12)
            if rms < 2e-4:
                a = np.exp(-dt / 0.18)
                self._vu = float(a * self._vu)
                v = float(np.clip(self._vu, 0.0, 1.0))
                return self._render(v, dt)

            # Sliders (IGUAL + nuevo consistency)
            thr_x  = float(np.clip(self.card.get_value("thr_x"), 1.4, 4.0))
            win_s  = float(np.clip(self.card.get_value("win_s"), 1.5, 6.0))
            smooth = float(np.clip(self.card.get_value("smooth"), 0.0, 0.95))
            consistency_req = float(np.clip(self.card.get_value("consistency"), 0.0, 1.0))

            # MODIFICADO: Priorizar más los graves (donde están los bombos)
            low  = self._lp1(x.astype(np.float32, copy=False), sr, fc=200.0)  # Más grave
            high = x - low
            nov = 1.5 * self._novelty(low,  sr, k=thr_x) + 0.7 * self._novelty(high, sr, k=thr_x)

            strength, bpm = self._periodicity(nov, sr, win_s)
            self._last_bpm = bpm

            # NUEVO: Evaluar si es patrón constante
            is_constant, consistency_score = self._evaluate_constant_pattern(bpm, strength)
            self._constant_pattern = is_constant
            
            # NUEVO: Aplicar filtro de consistencia
            if consistency_score < consistency_req:
                strength *= (consistency_score / max(consistency_req, 0.1))
            
            # NUEVO: Penalizar si no es música electrónica
            if not ((90 <= bpm <= 110) or (120 <= bpm <= 135) or (140 <= bpm <= 150)):
                strength *= 0.5  # Penalización por estar fuera de rangos objetivo

            # Suavizado (IDÉNTICO)
            tau_ms = 80.0 + (600.0 - 80.0) * (smooth ** 2)
            a = np.exp(-dt / (tau_ms/1000.0))
            self._vu = (1.0 - a) * strength + a * self._vu
            v = float(np.clip(self._vu, 0.0, 1.0))

            # Status mejorado
            try:
                genre = ("Reggaeton" if 90 <= bpm <= 110 else 
                        "House" if 120 <= bpm <= 135 else
                        "Trap" if 140 <= bpm <= 150 else "Otro")
                self.card.set_status(f"v={v:.2f} | {bpm:.0f}BPM | Cons={consistency_score:.2f} | {genre}")
            except Exception:
                pass

            self._render(v, dt)

        except Exception:
            pass

    # MODIFICADO: Umbrales más estrictos + LED de patrón constante
    def _render(self, v, dt=0.02):
        self.card.set_value(v)

        # Histeresis (SIMILAR AL ORIGINAL pero umbrales ajustados)
        hold_on  = float(np.clip(self.card.get_value("refrac"), 60.0, 800.0)) / 1000.0
        hold_off = 1.5 * hold_on
        
        # MODIFICADO: Umbrales más estrictos para golpe constante
        thr_on, thr_off = 0.45, 0.30  # Más accesibles que antes

        if v >= thr_on:
            self._ton += dt; self._toff = 0.0
            if self._ton >= hold_on: self._on = True
        elif v <= thr_off:
            self._toff += dt; self._ton = 0.0
            if self._toff >= hold_off: self._on = False

        # LEDs
        self.card.set_led("pulse", self._on)
        self.card.set_led("constant", self._constant_pattern)  # NUEVO LED

        # ON universal MODIFICADO: requiere patrón constante
        lo, hi = self.card.get_thresholds()
        lo = _norm01(lo); hi = _norm01(hi)
        if hi < lo: lo, hi = hi, lo
        mreq = _norm_match(self.card.get_match())
        
        # NUEVO: Solo se activa si detecta patrón constante
        meets_threshold = (lo <= v <= hi) and ((v * 100.0) >= mreq - 1e-6)
        self.card.set_on(meets_threshold and self._constant_pattern)