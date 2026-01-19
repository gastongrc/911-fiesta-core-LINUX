# analyzers/rhythm_void.py — BRAKE: RHYTHM VOID (optimized for sensitivity) v2025-09-08
import numpy as np
from collections import deque

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

class RhythmVoid:
    name = "RHYTHM VOID"

    def __init__(self):
        from module_card import ModuleCard
        self.card = ModuleCard(self.name)
        # Onsets más sensibles
        self.card.add_slider("thr_x",    "Sens (×σ)",         1.0, 3.5, 1.8)  # Más sensible por defecto
        self.card.add_slider("refrac",   "Refractario (ms)",  40.0, 200.0, 80.0)  # Menor refractario
        # Criterio de vacío más permisivo
        self.card.add_slider("void_s",   "Vacío req (s)",     0.5, 2.5, 1.2)  # Menos tiempo requerido
        self.card.add_slider("flux_max", "Flux máx",          0.01, 0.20, 0.05)  # Más sensible al flux
        # Nuevos controles
        self.card.add_slider("rms_thr",  "Umbral RMS",        0.001, 0.01, 0.003)  # Control de silencio
        self.card.add_slider("energy_w", "Peso Energía",      0.0, 1.0, 0.4)  # Peso del criterio energético
        # Visual
        self.card.add_slider("smooth",   "Suavizado",         0.0, 0.90, 0.45)  # Menos suavizado
        self.card.add_slider("hold",     "Hold ON (ms)",      80.0, 1200.0, 400.0)  # Menos hold
        self.card.add_led("void", "Void")
        self.card.add_slider("thr_on",  "Thr ON",   0.30, 0.90, 0.55)
        self.card.add_slider("thr_off", "Thr OFF",  0.20, 0.85, 0.45)

        self._t = 0.0
        self._last_pk_t = -1e9
        self._vu = 0.0
        self._on=False; self._ton=0.0; self._toff=0.0
        self._last_mag = None
        # Nuevos estados
        self._rms_history = deque(maxlen=20)  # Histórico de RMS para comparar
        self._energy_drop = 0.0  # Factor de caída energética

    def _novelty_peaks(self, x, sr, kx=1.8, refr_ms=80.0):
        win = max(1, int(0.008 * sr))  # Ventana más pequeña
        env = np.abs(x)
        env = np.convolve(env, np.ones(win, dtype=np.float32)/win, mode="same")
        dpos = np.maximum(np.diff(env, prepend=env[0]), 0.0)
        thr = float(np.median(dpos) + kx * 1.4826 * _mad(dpos))
        cand = np.where(dpos > thr)[0]
        if cand.size == 0: return np.array([], dtype=np.int32)
        refr = int((refr_ms/1000.0)*sr)
        keep = []; last=-10**9
        for i in cand:
            if i - last >= refr:
                i0 = max(0, i-2); i1 = min(dpos.size, i+3)
                if dpos[i] == np.max(dpos[i0:i1]):
                    keep.append(i); last=i
        return np.array(keep, dtype=np.int32)

    def process(self, block, sr):
        if block is None or sr is None or sr <= 0: return
        x = _mono(block); n=len(x)
        if n==0: return
        dt = n/float(sr); self._t += dt

        # Análisis energético mejorado
        rms = float(np.sqrt(np.mean(x*x)) + EPS)
        self._rms_history.append(rms)
        
        # Sliders
        thr_x  = float(np.clip(self.card.get_value("thr_x"), 1.0, 4.0))
        refr   = float(np.clip(self.card.get_value("refrac"), 40.0, 250.0))
        void_s = float(np.clip(self.card.get_value("void_s"), 0.3, 3.0))
        flux_m = float(np.clip(self.card.get_value("flux_max"), 0.005, 0.3))
        rms_thr = float(np.clip(self.card.get_value("rms_thr"), 0.0005, 0.02))
        energy_w = float(np.clip(self.card.get_value("energy_w"), 0.0, 1.0))
        smooth = float(np.clip(self.card.get_value("smooth"), 0.0, 0.95))

        # Detección de silencio absoluto
        is_silent = (rms < rms_thr)
        
        # Cálculo de caída energética
        if len(self._rms_history) >= 5:
            recent_avg = np.mean(list(self._rms_history)[-3:])  # Últimos 3
            older_avg = np.mean(list(self._rms_history)[-8:-3])  # Anteriores 5
            if older_avg > rms_thr * 2:  # Solo si había energía antes
                self._energy_drop = float(np.clip(1.0 - (recent_avg / (older_avg + 1e-9)), 0.0, 1.0))
            else:
                self._energy_drop = 0.0
        else:
            self._energy_drop = 0.0

        # Evitar void instantáneo al inicio
        if self._t <= dt + 1e-6 and self._last_pk_t < -1e8:
            self._last_pk_t = self._t

        # Picos (más permisivo en silencio)
        if not is_silent or rms > rms_thr * 0.5:  # Detectar incluso con poca señal
            pk = self._novelty_peaks(x, sr, kx=thr_x, refr_ms=refr)
            if pk.size:
                self._last_pk_t = self._t

        # Spectral flux
        if is_silent:
            flux = 0.0
        else:
            nfft = 1
            while nfft < n: nfft <<= 1
            X = np.fft.rfft(x, nfft)
            mag = np.abs(X) + 1e-12
            if self._last_mag is None or self._last_mag.shape != mag.shape:
                flux = 0.0
            else:
                diff = mag - self._last_mag
                diff[diff < 0] = 0.0
                flux = float(np.sum(diff) / (np.sum(mag) + 1e-9))
                flux = float(np.clip(flux, 0.0, 1.0))
            self._last_mag = mag

        since = self._t - self._last_pk_t

        # NUEVA MÉTRICA: Más agresiva y con múltiples criterios
        # 1. Criterio temporal (más permisivo)
        v_time = float(np.clip((since - void_s*0.7) / max(0.1, void_s), 0.0, 1.0))
        
        # 2. Criterio espectral (más sensible)
        v_flux = float(np.clip((flux_m - flux) / max(1e-6, flux_m), 0.0, 1.0))
        
        # 3. Criterio energético (NUEVO)
        v_energy = 0.0
        if is_silent:
            v_energy = 1.0  # Silencio absoluto = máximo void
        elif self._energy_drop > 0.3:  # Caída significativa
            v_energy = self._energy_drop * 1.2  # Amplificar la caída
            
        # 4. Combinación más agresiva (OR lógico parcial en lugar de AND)
        if is_silent:
            v_raw = 1.0  # Silencio = void inmediato
        elif since >= void_s * 0.5:  # Reducir tiempo mínimo
            # Usar el MÁXIMO de los criterios en lugar del promedio
            v_temporal_flux = max(v_time * 0.7, v_flux * 0.8)
            v_raw = float(np.clip(
                max(v_temporal_flux, v_energy * energy_w) + 
                min(v_time * 0.3, v_flux * 0.2), 0.0, 1.0))
        else:
            v_raw = float(np.clip(v_energy * energy_w * 0.5, 0.0, 1.0))

        # Suavizado menos agresivo
        tau_ms = 80.0 + (600.0 - 80.0)*(smooth**2)
        aV = np.exp(-dt / (tau_ms/1000.0))
        self._vu = (1.0 - aV)*v_raw + aV*self._vu
        v = float(np.clip(self._vu, 0.0, 1.0))

        try:
            self.card.set_status(f"since={since:.2f}s | flux={flux:.3f} | drop={self._energy_drop:.2f} | v={v:.2f}")
        except: pass

        self._render(v, dt)

    def _render(self, v, dt):
        self.card.set_value(v)
        hold_on  = float(np.clip(self.card.get_value("hold"), 80.0, 1500.0))/1000.0
        hold_off = max(0.25, 1.1*hold_on)  # simétrico con los otros para evitar "serrucho"
        thr_on  = float(np.clip(self.card.get_value("thr_on"),  0.10, 0.99))
        thr_off = float(np.clip(self.card.get_value("thr_off"), 0.05, thr_on))
        
        if v >= thr_on:
            self._ton += dt; self._toff = 0.0
            if self._ton >= hold_on: self._on = True
        elif v <= thr_off:
            self._toff += dt; self._ton = 0.0
            if self._toff >= hold_off: self._on = False
        self.card.set_led("void", self._on)

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
            "since_last_pk": float(self._t - self._last_pk_t),
            "energy_drop": float(self._energy_drop)
        }