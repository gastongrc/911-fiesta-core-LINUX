# analyzers/energy_cliff.py — BRAKE: ENERGY CLIFF v2025-08-27
import numpy as np

EPS = 1e-12

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
    if 0.0 <= m <= 1.0: m *= 100.0
    return float(np.clip(m, 0.0, 100.0))

class EnergyCliff:
    name = "ENERGY CLIFF"

    def __init__(self):
        from module_card import ModuleCard
        self.card = ModuleCard(self.name)
        # Ventanas de energía (EMA)
        self.card.add_slider("win_short", "Vent corta (s)",    0.08, 0.25, 0.12)
        self.card.add_slider("win_long",  "Vent larga (s)",    0.6,  2.0,  1.0)
        # Caída requerida
        self.card.add_slider("drop_db",   "Caída dB req",      6.0,  24.0, 12.0)
        # Confirmación (para freno real)
        self.card.add_slider("confirm_s", "Confirm (s)",       0.4,  2.5,  1.2)
        # Visual
        self.card.add_slider("smooth",    "Suavizado",         0.0,  0.95, 0.60)
        self.card.add_slider("hold",      "Hold ON (ms)",      100.0, 1200.0, 500.0)
        self.card.add_led("cliff", "Cliff")
        # Umbrales ajustables (BRAKE score local)
        self.card.add_slider("thr_on",  "Thr ON",   0.30, 0.90, 0.60)
        self.card.add_slider("thr_off", "Thr OFF",  0.20, 0.85, 0.50)

        # estado
        self._vu = 0.0
        self._on = False; self._ton = 0.0; self._toff = 0.0
        self._eS = 0.0  # EMA corta
        self._eL = 0.0  # EMA larga
        self._ok_time = 0.0  # acumula tiempo en que el drop cumple

    def process(self, block, sr):
        if block is None or sr is None or sr <= 0: return
        x = _mono(block); n = len(x)
        if n == 0: return
        dt = n/float(sr)

        # Gate silencio
        rms = float(np.sqrt(np.mean(x*x)) + EPS)
        if rms < 2e-4:
            a = np.exp(-dt/0.18); self._vu *= a
            self._ok_time = 0.0
            return self._render(float(np.clip(self._vu,0.0,1.0)), dt)

        # sliders
        wS = float(np.clip(self.card.get_value("win_short"), 0.05, 0.35))
        wL = float(np.clip(self.card.get_value("win_long"),  0.4,  3.0))
        drop_db_req = float(np.clip(self.card.get_value("drop_db"), 4.0, 30.0))
        confirm_s   = float(np.clip(self.card.get_value("confirm_s"), 0.2, 3.0))
        smooth      = float(np.clip(self.card.get_value("smooth"), 0.0, 0.95))

        # EMA de energía (RMS^2) en dos escalas
        e_inst = float(np.mean(x*x) + 1e-12)
        aS = np.exp(-dt / max(1e-3, wS))
        aL = np.exp(-dt / max(1e-3, wL))
        self._eS = (1.0 - aS)*e_inst + aS*self._eS
        self._eL = (1.0 - aL)*e_inst + aL*self._eL

        # dB drop (positiva si cayó)
        drop_db = 10.0 * np.log10((self._eL + 1e-18) / (self._eS + 1e-18))
        met = float(np.clip(drop_db / max(1e-6, drop_db_req), 0.0, 1.0))
        if drop_db >= drop_db_req:
            self._ok_time += dt
        else:
            self._ok_time = max(0.0, self._ok_time - 2*dt)  # se "descarga" rápido si dejó de cumplir

        # Vu crudo: mezcla de magnitud de drop + progreso de confirmación
        v_raw = float(np.clip(0.6*met + 0.4*np.clip(self._ok_time / max(0.1, confirm_s), 0.0, 1.0), 0.0, 1.0))

        # Suavizado visual
        tau_ms = 80.0 + (800.0 - 80.0)*(smooth**2)
        aV = np.exp(-dt / (tau_ms/1000.0))
        self._vu = (1.0 - aV)*v_raw + aV*self._vu
        v = float(np.clip(self._vu, 0.0, 1.0))

        try:
            self.card.set_status(f"drop={drop_db:.1f} dB | ok={self._ok_time:.2f}s | v={v:.2f}")
        except: pass

        self._render(v, dt)

    def _render(self, v, dt):
        self.card.set_value(v)
        # LED con histeresis/hold
        hold_on  = float(np.clip(self.card.get_value("hold"), 100.0, 2000.0))/1000.0
        hold_off = max(0.3, 1.2*hold_on)
        thr_on  = float(np.clip(self.card.get_value("thr_on"),  0.10, 0.99))
        thr_off = float(np.clip(self.card.get_value("thr_off"), 0.05, thr_on))
        if v >= thr_on:
            self._ton += dt; self._toff = 0.0
            if self._ton >= hold_on: self._on = True
        elif v <= thr_off:
            self._toff += dt; self._ton = 0.0
            if self._toff >= hold_off: self._on = False
        self.card.set_led("cliff", self._on)

        # MATCH universal (+ Min/Max)
        lo, hi = self.card.get_thresholds()
        lo = _norm01(lo); hi = _norm01(hi)
        if hi < lo: lo, hi = hi, lo
        mreq = _norm_match(self.card.get_match())
        self.card.set_on((lo <= v <= hi) and ((v*100.0) >= mreq - 1e-6))

    # === API de integración/debug ===
    def get_current_value(self):
        return float(np.clip(self._vu, 0.0, 1.0))
    
    def debug_dict(self):
        return {
            "name": self.name,
            "vu": float(np.clip(self._vu,0.0,1.0)),
            "on": bool(self._on),
            "ok_time": float(self._ok_time),
            "e_short": float(self._eS),
            "e_long": float(self._eL)
        }