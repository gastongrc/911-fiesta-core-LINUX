# Deep Listener – BAJADA (VU = CALMA) v2025-08-25-fix-OPTIMIZED
# - Corrige bombo constante activando actividad (crest del envelope).
# - Suavizado exponencial por tau en ms (a = exp(-dt/tau)) => mucho más visible.
# OPTIMIZACIONES v2025-10-02:
# - FFT reducida a 512 (línea ~101)
# - Buffer size reducido a la mitad (línea ~85-90)
# - AGC history: 600→200 (línea ~165)
# - Envelope history: 64→32 (línea ~167)
# - Smoothing default: 0.60→0.70 (línea ~60)
# - Eliminada variable mid_voice innecesaria (línea ~231-250)

from __future__ import annotations
import math, re
from collections import deque
import numpy as np

try:
    from module_card import ModuleCard
except Exception:
    class ModuleCard:
        def __init__(self, title=""): self._vals={}
        def add_slider(self, *a, **k): pass
        def add_led(self, *a, **k): pass
        def set_led(self, *a, **k): pass
        def get(self, k): return self._vals.get(k, 0.0)
        def set_value(self, *a, **k): pass
        def set_estado(self, *a, **k): pass
        def set_status_text(self, *a, **k): pass

__all__ = ["DeepListener"]
DEBUG_TEXT = False

def _clip01(v): return float(max(0.0, min(1.0, float(v))))
_num_re = re.compile(r"[-+]?\d+(?:[.,]\d+)?")

def _parse_num(val, default=None):
    try:
        if isinstance(val, (int, float)): return float(val)
        if isinstance(val, str):
            m = _num_re.search(val)
            if not m: return default
            return float(m.group(0).replace(',', '.'))
    except Exception:
        pass
    return default

def _mono(x):
    if x is None: return None
    x = np.asarray(x)
    return x.astype(np.float32) if x.ndim == 1 else x.mean(axis=1).astype(np.float32)

def _hann(n): return np.hanning(n).astype(np.float32)

def _ema(prev, cur, a):
    # a=coef de 0..1 sobre el PREV. a alto => más lento (si a = exp(-dt/tau)).
    return (1.0 - a) * float(cur) + a * float(prev)

class DeepListener:
    """
    Detector de CALMA en graves (30–220 Hz).
    Actividad = máx(logística ΔdB, transiente grave, AGC) * gate_graves  (+ crest envelope)
    VU mostrado = CALMA = 1 - actividad.
    ON si Min ≤ VU ≤ Max y VU% ≥ Match.
    """
    def __init__(self, card: ModuleCard | None = None):
        print("[DeepListener] v2025-08-25-fix-OPTIMIZED (crest + tau_ms + performance)")
        self.name = "DEEP LISTENER"
        self.card = card if card is not None else ModuleCard(self.name)

        # Sliders (mismos + smooth re-mapeado a tau_ms)
        self._add_slider("f_lo",     "Fmin (Hz)",   20.0, 120.0,  30.0)
        self._add_slider("f_hi",     "Fmax (Hz)",   80.0, 220.0, 160.0)
        self._add_slider("sens_db",  "Sens (dB)",    1.0,  18.0,   7.0)
        self._add_slider("tau_db",   "Tau (dB)",     0.5,   8.0,   3.0)
        self._add_slider("snr_db",   "SNR (dB)",     0.0,  18.0,   3.0)
        self._add_slider("agc_mix",  "AGC mix",      0.0,   1.0,   0.40)
        # CAMBIO 1: Smoothing default 0.60 → 0.70
        self._add_slider("smooth",   "Suavizado",    0.0,  0.95,  0.70)
        self._add_slider("hold_ms",  "Hold (ms)",    0.0,  300.0,  80.0)

        # LED Calma
        self.card.add_led("calma", "Calma")
        self._calm_on_vu  = 0.70
        self._calm_off_vu = 0.50
        self._calm_state  = False

        # CAMBIO 2: FFT reducida 1024 → 512
        self._fft_n  = 512
        self._window = _hann(self._fft_n)
        self._last_sr = None
        
        # CAMBIO 3: Buffer circular reducido a la mitad
        self._buffer = np.zeros(self._fft_n, dtype=np.float32)
        self._buf_pos = 0
        self._buf_filled = False

        # estado
        self._vu = 1.0
        self.is_on = True
        self._hold_low_ms = 0.0
        self._ring = deque(maxlen=16384)
        
        # CAMBIO 4: AGC history reducido 600 → 200
        self._agc_hist = deque(maxlen=200)

        # CAMBIO 5: Envelope history reducido 64 → 32
        self._env_hist = deque(maxlen=32)
        
        # EMAs/transientes
        self._ema_fast = None
        self._ema_slow = None
        self.audio_engine = None
        self._dbg = 0

    # ---- UI helpers
    def _add_slider(self, key, label, vmin, vmax, vdef):
        try: self.card.add_slider(key, label, float(vmin), float(vmax), float(vdef))
        except: pass

    def _get(self, key, default):
        try:
            v = _parse_num(self.card.get(key), default)
            return float(default) if v is None else float(v)
        except: return float(default)

    def _read_pct01(self, key: str):
        try:
            v = _parse_num(self.card.get(key), None)
            if v is not None:
                return _clip01(v/100.0 if v > 1.0 else v)
        except: pass
        for attr in (f"get_{key}", f"{key}_value", f"value_{key}"):
            fn = getattr(self.card, attr, None)
            if callable(fn):
                v = _parse_num(fn(), None)
                if v is not None:
                    return _clip01(v/100.0 if v > 1.0 else v)
        gt = getattr(self.card, "get_thresholds", None)
        if callable(gt):
            try:
                t = gt()
                if isinstance(t, (list, tuple)) and len(t) >= 2:
                    idx = {"min":0, "max":1, "match":2}.get(key, None)
                    if idx is not None and idx < len(t):
                        v = _parse_num(t[idx], None)
                        if v is not None:
                            return _clip01(v/100.0 if v > 1.0 else v)
            except: pass
        return {"min":0.25, "max":0.95, "match":0.50}.get(key, 0.5)

    def _get_minmaxmatch(self):
        lo = self._read_pct01("min")
        hi = self._read_pct01("max")
        mm01 = self._read_pct01("match")
        return lo, hi, mm01 * 100.0

    def _set_on(self, on: bool):
        self.is_on = bool(on)
        for name in ("set_estado","set_onoff","set_on","set_active","set_state"):
            fn = getattr(self.card, name, None)
            if callable(fn):
                try: fn(bool(on)); return
                except: pass

    def _render(self, vu, on, dbg=None):
        self._vu = _clip01(vu)
        for m in ("set_value","set_vu"):
            fn = getattr(self.card, m, None)
            if callable(fn):
                try: fn(self._vu); break
                except: pass
        self._set_on(on)
        if DEBUG_TEXT and dbg:
            try: self.card.set_status_text(dbg)
            except: pass

    def _reset_filters(self):
        """Reset filtros cuando cambia sample rate"""
        self._ema_fast = None
        self._ema_slow = None
        self._agc_hist.clear()
        self._env_hist.clear()
        self._ring.clear()
        self._buf_pos = 0
        self._buf_filled = False

    def _update_buffer(self, x):
        """Buffer circular más eficiente que deque"""
        n_new = len(x)
        if n_new == 0:
            return None
            
        # Si el nuevo bloque es mayor que nuestro buffer, tomar solo el final
        if n_new >= self._fft_n:
            return x[-self._fft_n:].astype(np.float32)
            
        # Insertar en buffer circular
        end_pos = (self._buf_pos + n_new) % len(self._buffer)
        
        if end_pos > self._buf_pos:
            # No hay wrap-around
            self._buffer[self._buf_pos:end_pos] = x
        else:
            # Hay wrap-around
            first_chunk = len(self._buffer) - self._buf_pos
            self._buffer[self._buf_pos:] = x[:first_chunk]
            self._buffer[:end_pos] = x[first_chunk:]
            
        self._buf_pos = end_pos
        if not self._buf_filled and self._buf_pos >= self._fft_n:
            self._buf_filled = True
            
        if not self._buf_filled:
            return None
            
        # Extraer frame actual
        if self._buf_pos >= self._fft_n:
            start = self._buf_pos - self._fft_n
            return self._buffer[start:self._buf_pos].copy()
        else:
            # Wrap-around case
            n_from_end = self._fft_n - self._buf_pos
            frame = np.empty(self._fft_n, dtype=np.float32)
            frame[:n_from_end] = self._buffer[-n_from_end:]
            frame[n_from_end:] = self._buffer[:self._buf_pos]
            return frame

    # ---- integración
    def set_audio_engine(self, eng): self.audio_engine = eng
    def tick(self, *a, **k): pass

    def process(self, block, sr, *a, **k):
        x = _mono(np.asarray(block) if block is not None else None)
        if x is None or x.size == 0:
            self._render(self._vu, self.is_on); return

        # Validar sample rate
        sr = float(sr)
        if sr <= 0:
            self._render(self._vu, self.is_on); return
            
        if self._last_sr is not None and abs(sr - self._last_sr) > 0.1:
            self._reset_filters()
        self._last_sr = sr

        # FFT con buffer mejorado
        frame = self._update_buffer(x)
        if frame is None:
            self._render(self._vu, self.is_on); return

        w = self._window
        windowed = frame * w
        spec = np.fft.rfft(windowed, n=self._fft_n)
        
        # Normalización correcta para densidad espectral
        window_power = np.sum(w**2)
        mag2 = (spec.real**2 + spec.imag**2) / (sr * window_power + 1e-12)

        freqs = np.fft.rfftfreq(self._fft_n, d=1.0/sr)

        # Validar bandas de frecuencia
        f_lo = float(np.clip(self._get("f_lo", 30.0), 20.0, min(120.0, sr/2 - 10)))
        f_hi = float(np.clip(self._get("f_hi",160.0), 80.0, min(220.0, sr/2 - 10)))
        if f_lo >= f_hi: 
            f_lo, f_hi = min(f_lo, f_hi - 10), max(f_lo + 10, f_hi)

        def _sum_band(fa, fb):
            fa, fb = max(fa, freqs[1]), min(fb, freqs[-1])
            i0 = int(np.searchsorted(freqs, fa, side="left"))
            i1 = int(np.searchsorted(freqs, fb, side="right"))
            i0 = max(0, min(i0, mag2.size-1))
            i1 = max(i0+1, min(i1, mag2.size))
            if i0 >= i1:
                return 1e-18
            return float(np.sum(mag2[i0:i1]) + 1e-18)

        # CAMBIO 6: Simplificación - eliminar mid_voice innecesario
        band      = _sum_band(f_lo, f_hi)         # 30–220 Hz (config)
        low_total = _sum_band(20.0, 200.0)        # 20–200 Hz
        
        # Evitar división por cero
        ratio_graves = float(band / max(low_total, 1e-18))

        # Piso dinámico con más muestras para estadística confiable
        self._agc_hist.append(band)
        if len(self._agc_hist) >= 50:
            floor = float(np.percentile(self._agc_hist, 30)) + 1e-18
        else:
            floor = band + 1e-18
            
        delta_db = 10.0 * math.log10(max(band / floor, 1e-12))

        # Actividad por logística con validación
        sens = float(np.clip(self._get("sens_db", 7.0), 1.0, 18.0))
        tau_db = float(np.clip(self._get("tau_db", 3.0), 0.5, 8.0))
        z = (delta_db - sens) / max(tau_db, 0.1)
        act_log = 1.0 / (1.0 + math.exp(-np.clip(z, -20, 20)))

        # Transiente de graves: EMA rápido vs lento con inicialización
        a_fast, a_slow = 0.10, 0.95
        if self._ema_fast is None:
            self._ema_fast = band
            self._ema_slow = band
        else:
            self._ema_fast = _ema(self._ema_fast, band, a_fast)
            self._ema_slow = _ema(self._ema_slow, band, a_slow)
            
        rise = float(self._ema_fast / max(self._ema_slow, 1e-18) - 1.0)
        act_flux = _clip01(rise / 0.50)

        # Gate por ratio de graves
        gate_threshold_low = 0.15
        gate_threshold_high = 0.45
        gate_ratio = _clip01((ratio_graves - gate_threshold_low) / 
                            max(gate_threshold_high - gate_threshold_low, 0.01))

        # AGC p95 para normalizar niveles
        if len(self._agc_hist) >= 30:
            p95 = float(np.percentile(self._agc_hist, 95)) + 1e-18
        else:
            p95 = band + 1e-18
        act_agc = _clip01(band / p95)
        mix = _clip01(self._get("agc_mix", 0.40))

        # Crest del envelope para pateo constante
        self._env_hist.append(band)
        if len(self._env_hist) >= 8:
            mean_env = float(np.mean(self._env_hist)) + 1e-18
            p95_env = float(np.percentile(self._env_hist, 95)) + 1e-18
            crest_factor = 0.6
            crest = _clip01((p95_env / mean_env - 1.0) / crest_factor)
        else:
            crest = 0.0

        # Combinar con suma ponderada
        weights = [0.3, 0.25, 0.25, 0.2]
        actividad_base = (weights[0] * act_log + 
                         weights[1] * act_flux + 
                         weights[2] * mix * act_agc + 
                         weights[3] * crest)
        
        # Aplicar gate
        actividad = actividad_base * max(gate_ratio, 0.4)

        # Boost de golpe claro
        golpe_threshold_ratio = 0.35
        golpe_threshold_flux = 0.30
        if ratio_graves > golpe_threshold_ratio and act_flux > golpe_threshold_flux:
            actividad = max(actividad, 0.80)

        # CAMBIO 7: Protección de voz simplificada sin mid_voice
        # Usar solo ratio de graves como indicador
        if ratio_graves < 0.20:
            actividad *= 0.5

        # Gate por SNR
        snr = float(np.clip(self._get("snr_db", 3.0), 0.0, 18.0))
        if delta_db < snr:
            actividad *= 0.7

        # VU CALMA (invertido)
        vu_calma_raw = 1.0 - _clip01(actividad)

        # Suavizado real por tau_ms
        smooth = float(np.clip(self._get("smooth", 0.70), 0.0, 0.95))
        tau_ms = 20.0 + (600.0 - 20.0) * (smooth ** 2)
        dt_ms = 1000.0 * (len(x) / sr)
        a_tau = math.exp(-dt_ms / max(tau_ms, 1e-3))
        vu = _ema(self._vu, vu_calma_raw, a_tau)

        # Hold abajo (golpe = queda un cachito en 0)
        hold_ms = float(np.clip(self._get("hold_ms", 80.0), 0.0, 300.0))
        if vu < 0.10:
            self._hold_low_ms = hold_ms
        else:
            self._hold_low_ms = max(0.0, self._hold_low_ms - dt_ms)
        if self._hold_low_ms > 0.0:
            vu = min(vu, 0.10)

        # Thresholds & estado
        lo, hi, match = self._get_minmaxmatch()
        on = (lo <= vu <= hi) and ((vu * 100.0) >= match)

        # LED Calma (histéresis por VU alto)
        if not self._calm_state:
            self._calm_state = (vu > self._calm_on_vu)
        else:
            self._calm_state = not (vu < self._calm_off_vu)
        try:
            self.card.set_led("calma", bool(self._calm_state))
        except: pass

        dbg = None
        if DEBUG_TEXT:
            dbg = (f"VUcalma={vu:.2f} | crest={crest:.2f} | ΔdB={delta_db:+.1f} | "
                   f"ratioGraves={ratio_graves:.2f} | rise={rise:.2f} | "
                   f"act={actividad:.2f} | tau_ms={tau_ms:.0f}")
        self._render(vu, on, dbg)