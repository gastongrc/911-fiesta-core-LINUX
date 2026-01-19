# analyzers/wideband_blackout.py — BRAKE: WIDEBAND BLACKOUT v2025-08-27
import numpy as np

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

class WidebandBlackout:
    name = "WIDEBAND BLACKOUT"

    def __init__(self):
        from module_card import ModuleCard
        self.card = ModuleCard(self.name)
        self.card.add_slider("win_short","Vent corta (s)",   0.10, 0.40, 0.16)
        self.card.add_slider("win_long", "Vent larga (s)",   0.8,  3.0,  1.5)
        self.card.add_slider("ratio_max","Ratio máx (S/L)",  0.05, 0.40, 0.15)  # cuanto más bajo, más blackout
        self.card.add_slider("confirm_s","Confirm (s)",      0.6,  3.0,  1.6)
        self.card.add_slider("smooth",   "Suavizado",        0.0,  0.95, 0.60)
        self.card.add_slider("hold",     "Hold ON (ms)",     120.0, 1500.0, 600.0)
        self.card.add_led("black", "Blackout")
        self.card.add_slider("thr_on",  "Thr ON",   0.30, 0.90, 0.60)
        self.card.add_slider("thr_off", "Thr OFF",  0.20, 0.85, 0.50)

        # EMA por banda (short/long)
        self._eS = dict(low=0.0, mid=0.0, hi=0.0)
        self._eL = dict(low=0.0, mid=0.0, hi=0.0)
        self._vu = 0.0
        self._ok_time = 0.0
        self._on=False; self._ton=0.0; self._toff=0.0

    def _bands_energy(self, x, sr):
        n = len(x); nfft = 1
        while nfft < n: nfft <<= 1
        X = np.fft.rfft(x, nfft)
        mag2 = (X.real*X.real + X.imag*X.imag) + 1e-20
        f = np.fft.rfftfreq(nfft, 1.0/sr)
        def band(f0,f1):
            i0 = int(np.searchsorted(f, f0))
            i1 = int(np.searchsorted(f, f1)); i1 = max(i1, i0+1)
            return float(np.sum(mag2[i0:i1]))
        low = band(40.0, 200.0)
        mid = band(200.0, 2000.0)
        hi  = band(2000.0, 10000.0)
        return low, mid, hi

    def process(self, block, sr):
        if block is None or sr is None or sr <= 0: return
        x = _mono(block); n=len(x)
        if n==0: return
        dt = n/float(sr)

        # Gate silencio
        rms = float(np.sqrt(np.mean(x*x)) + EPS)
        if rms < 2e-4:
            a = np.exp(-dt/0.18); self._vu *= a
            self._ok_time = min(10.0, self._ok_time + dt)  # silencio favorece blackout
            return self._render(float(np.clip(self._vu, 0.0, 1.0)), dt)

        wS = float(np.clip(self.card.get_value("win_short"), 0.08, 0.5))
        wL = float(np.clip(self.card.get_value("win_long"),  0.6,  4.0))
        rMax = float(np.clip(self.card.get_value("ratio_max"), 0.02, 0.6))
        confirm_s = float(np.clip(self.card.get_value("confirm_s"), 0.4, 3.0))
        smooth = float(np.clip(self.card.get_value("smooth"), 0.0, 0.95))

        low, mid, hi = self._bands_energy(x, sr)

        aS = np.exp(-dt / max(1e-3, wS))
        aL = np.exp(-dt / max(1e-3, wL))
        for k, val in (("low",low),("mid",mid),("hi",hi)):
            self._eS[k] = (1.0 - aS)*val + aS*self._eS[k]
            self._eL[k] = (1.0 - aL)*val + aL*self._eL[k]

        rL = float(np.clip(self._eS["low"]/(self._eL["low"]+1e-18), 0.0, 1.5))
        rM = float(np.clip(self._eS["mid"]/(self._eL["mid"]+1e-18), 0.0, 1.5))
        rH = float(np.clip(self._eS["hi"] /(self._eL["hi"] +1e-18), 0.0, 1.5))

        ok_now = (rL <= rMax) and (rM <= rMax) and (rH <= rMax)
        if ok_now:
            self._ok_time = min(10.0, self._ok_time + dt)
        else:
            self._ok_time = max(0.0, self._ok_time - 2*dt)

        # v_raw: cuánto baja + cuánto se sostiene
        ratio = (rL + rM + rH) / 3.0
        v_drop = float(np.clip((rMax - ratio) / max(1e-6, rMax), 0.0, 1.0))
        v_hold = float(np.clip(self._ok_time / max(0.1, confirm_s), 0.0, 1.0))
        v_raw = float(np.clip(0.55*v_drop + 0.45*v_hold, 0.0, 1.0))

        # suavizado
        tau_ms = 120.0 + (900.0 - 120.0)*(smooth**2)
        aV = np.exp(-dt / (tau_ms/1000.0))
        self._vu = (1.0 - aV)*v_raw + aV*self._vu
        v = float(np.clip(self._vu, 0.0, 1.0))

        try:
            self.card.set_status(f"ratios L/M/H={rL:.2f}/{rM:.2f}/{rH:.2f} | ok={self._ok_time:.2f}s | v={v:.2f}")
        except: pass

        self._render(v, dt)

    def _render(self, v, dt):
        self.card.set_value(v)
        hold_on  = float(np.clip(self.card.get_value("hold"), 120.0, 2000.0))/1000.0
        hold_off = max(0.4, 1.3*hold_on)
        thr_on  = float(np.clip(self.card.get_value("thr_on"),  0.10, 0.99))
        thr_off = float(np.clip(self.card.get_value("thr_off"), 0.05, thr_on))
        if v >= thr_on:
            self._ton += dt; self._toff = 0.0
            if self._ton >= hold_on: self._on = True
        elif v <= thr_off:
            self._toff += dt; self._ton = 0.0
            if self._toff >= hold_off: self._on = False
        self.card.set_led("black", self._on)

        self._update_match_status(v)

    def _update_match_status(self, output_value):
        """Actualiza el estado de match basado en thresholds y valor de match"""
        # Obtener y normalizar thresholds
        threshold_low, threshold_high = self.card.get_thresholds()
        threshold_low = self._normalize_01(threshold_low)
        threshold_high = self._normalize_01(threshold_high)
        
        # Asegurar orden correcto
        if threshold_high < threshold_low:
            threshold_low, threshold_high = threshold_high, threshold_low
        
        # Obtener valor de match requerido
        required_match = self._normalize_match(self.card.get_match())
        
        # Calcular estado: dentro de thresholds Y por encima del match requerido
        within_thresholds = threshold_low <= output_value <= threshold_high
        
        # Para valores muy bajos de match (0-2%), usar tolerancia más generosa
        tolerance = 0.1 if required_match <= 2.0 else 1e-6
        above_match = (output_value * 100.0) >= (required_match - tolerance)
        
        self.card.set_on(within_thresholds and above_match)

    @staticmethod
    def _normalize_01(value):
        """Normaliza un valor al rango 0-1"""
        if value is None:
            return 0.0
        
        try:
            float_value = float(value)
        except (ValueError, TypeError):
            return 0.0
        
        # Convertir porcentajes (0-100) a 0-1 si es necesario
        if float_value > 1.5:
            float_value *= 0.01
        
        return float(np.clip(float_value, 0.0, 1.0))

    @staticmethod
    def _normalize_match(match_value):
        """
        Normaliza valor de match a rango 0-100
        Acepta tanto valores 0-1 como 0-100
        """
        if match_value is None:
            return 50.0  # Default value
        
        try:
            match_float = float(match_value)
        except (ValueError, TypeError):
            return 50.0
        
        # Convertir 0-1 a 0-100 si es necesario
        if 0.0 <= match_float <= 1.0:
            match_float *= 100.0
        
        return float(np.clip(match_float, 0.0, 100.0))

    # === API de integración/debug ===
    def get_current_value(self):
        return float(np.clip(self._vu, 0.0, 1.0))
    
    def debug_dict(self):
        return {
            "name": self.name,
            "vu": float(np.clip(self._vu,0.0,1.0)),
            "on": bool(self._on),
            "ok_time": float(self._ok_time),
            "ratios": "L/M/H",
            # Nota: ratios actuales se incluyen vía status string ya seteado
        }