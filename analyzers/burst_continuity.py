# analyzers/burst_continuity.py — ATAQUE: BURST CONTINUITY (calibrado según análisis real)
# v2025-09-07-calibrated: optimizado para detectar ráfagas sostenidas con características del análisis

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

class BurstContinuity:
    name = "BURST CONTINUITY"

    def __init__(self):
        from module_card import ModuleCard
        self.card = ModuleCard(self.name)
        # Detección calibrada según análisis (eventos cada ~3s en tu ejemplo)
        self.card.add_slider("thr_x",     "Sens (×σ)",            1.8, 3.5, 2.4)  # Más específico: era 1.4-4.0, 2.2
        self.card.add_slider("refrac",    "Refractario (ms)",     100.0, 180.0, 140.0)  # Calibrado: era 40-120, 70
        # Racha/continuidad calibrada para ataques sostenidos
        self.card.add_slider("gap_ms",    "Hueco máx (ms)",       200.0, 400.0, 300.0)  # Más permisivo: era 80-220, 150
        self.card.add_slider("run_req",   "Racha req (s)",        1.50, 4.00, 2.50)  # Más largo: era 0.40-1.50, 0.80
        self.card.add_slider("win_s",     "Ventana (s)",          2.0,  6.0,  3.5)  # Más largo: era 0.6-2.0, 1.0
        # Compuertas calibradas para continuidad
        self.card.add_slider("flux_on",    "Flux p/permitir",      0.06, 0.25, 0.12)  # Moderado: era 0.02-0.30, 0.10
        self.card.add_slider("hi_ratio_min","%Agudos mín (rel)",   0.25, 0.55, 0.35)  # Calibrado: era 0.10-0.60, 0.30
        self.card.add_slider("env_min",    "Env RMS mín (×1e-3)",  1.00, 4.00, 2.00)  # Calibrado: era 0.10-3.00, 1.50
        self.card.add_slider("low_veto",   "Veto low ratio",       0.40, 0.75, 0.58)  # Calibrado: era 0.40-0.90, 0.55
        # Anti-genérico calibrado para ataques reales
        self.card.add_slider("trem_req",   "Tremolo req (pico/banda)", 1.5, 2.8, 2.0)  # Menos estricto: era 1.2-3.0, 2.0
        self.card.add_slider("cv_max",     "IOI CV máx",           0.20, 0.50, 0.35)  # Sin cambio: era 0.15-0.60, 0.35
        self.card.add_slider("min_ev",     "Eventos mín",          4.0,  12.0, 6.0)  # Menos estricto: era 3.0-20.0, 8.0
        # Crest factor para validación
        self.card.add_slider("crest_min",  "Crest mín (dB)",       9.0,  15.0, 10.5)  # NUEVO: según análisis 10.4-11.5
        # Visual
        self.card.add_slider("smooth",    "Suavizado",            0.0,  0.80, 0.30)  # Moderado: era 0.25
        self.card.add_slider("hold",      "Hold ON (ms)",         200.0, 800.0, 400.0)  # Más largo: era 80-600, 200
        self.card.add_led("burst", "Burst")

        self._vu = 0.0; self._on=False; self._ton=0.0; self._toff=0.0
        # Filtros calibrados para continuity (2.5-8 kHz, rango intermedio)
        self._lp2k5 = 0.0  # CALIBRADO: 2.5kHz (entre snare y hi-hat)
        self._lp200 = 0.0
        self._last_mag_hi = None
        self._events = deque()
        self._t = 0.0
        # Buffer de envolvente hi (200 Hz) para tremolo
        self._env_sr = 200.0
        self._env_buf = np.zeros(0, dtype=np.float32)
        self._env_max = int(6.0 * self._env_sr)  # Hasta 6s para continuidad

    def _lp1(self, x, sr, fc, state_attr):
        a = 1.0 - np.exp(-2.0*np.pi*fc/float(sr))
        y = np.empty_like(x, dtype=np.float32); s = getattr(self, state_attr)
        for i, xi in enumerate(x):
            s = s + a*(xi - s); y[i] = s
        setattr(self, state_attr, float(s)); return y

    def _hi_flux(self, band_hi, sr):
        """Flux calibrado para continuidad: 2.5-8 kHz."""
        n = len(band_hi); nfft = 1
        while nfft < n: nfft <<= 1
        H = np.fft.rfft(band_hi, nfft)
        mag = np.abs(H) + 1e-12
        f   = np.fft.rfftfreq(nfft, 1.0/sr)
        # CALIBRADO: 2.5-8 kHz para continuidad (rango intermedio)
        mask = (f >= 2500.0) & (f <= 8000.0)
        M = mag[mask]
        if self._last_mag_hi is None or self._last_mag_hi.shape != M.shape:
            flux = 0.0
        else:
            D = M - self._last_mag_hi; D[D < 0] = 0.0
            flux = float(np.sum(D) / (np.sum(M) + 1e-9))
            flux = float(np.clip(flux, 0.0, 1.0))
        self._last_mag_hi = M
        return flux

    def _novelty_peaks(self, sig, sr, kx, refr_ms):
        """Detección de picos calibrada para continuidad."""
        # Envelope calibrado para attack time promedio (12ms)
        win = max(1, int(0.012 * sr))  # Calibrado según análisis
        env = np.abs(sig)
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

    def _tremolo_ratio(self, env_d, f_lo, f_hi):
        """Tremolo calibrado para continuidad: menos estricto que otros módulos."""
        seg = env_d.astype(np.float32)
        if seg.size < 80: return 0.0  # Menos estricto: era 60
        seg -= float(np.mean(seg))
        nfft = 1
        while nfft < seg.size: nfft <<= 1
        E = np.fft.rfft(seg, nfft)
        P = (E.real*E.real + E.imag*E.imag) + 1e-20
        freqs = np.fft.rfftfreq(nfft, 1.0/self._env_sr)
        # Bandas calibradas para continuidad (más amplio)
        band_fast = (freqs >= f_lo) & (freqs <= f_hi)
        band_slow = (freqs >= 0.5) & (freqs <= 4.0)  # Más amplio: era 1-5 Hz
        if not np.any(band_fast) or not np.any(band_slow): return 0.0
        peak = float(np.max(P[band_fast])); base = float(np.mean(P[band_slow])) + 1e-9
        return float(np.clip(peak/base, 0.0, 15.0))  # Más rango: era 10.0

    def process(self, block, sr):
        if block is None or sr is None or sr <= 0: return
        x = _mono(block); n=len(x)
        if n == 0: return
        dt = n/float(sr); self._t += dt

        # Gate de silencio
        rms = float(np.sqrt(np.mean(x*x)) + 1e-12)
        if rms < 2e-4:
            self._last_mag_hi = None
            self._events.clear()
            self._env_buf = np.zeros(0, dtype=np.float32)
            self._vu = 0.0; self._on=False; self._ton=0.0; self._toff=0.0
            try: self.card.set_status("silencio")
            except: pass
            self.card.set_value(0.0); self.card.set_led("burst", False); self.card.set_on(False)
            return

        # Bandas calibradas: hi = x - LP2.5k ; low = LP200(x)
        lp2k5 = self._lp1(x, sr, 2500.0, "_lp2k5")  # CALIBRADO: 2.5kHz para continuidad
        lp200 = self._lp1(x, sr, 200.0,  "_lp200")
        hi  = x - lp2k5  # Contenido > 2.5kHz
        low = lp200

        rms_hi  = float(np.sqrt(np.mean(hi*hi)) + 1e-12)
        rms_low = float(np.sqrt(np.mean(low*low)) + 1e-12)
        hi_ratio  = float(np.clip(rms_hi / rms, 0.0, 1.0))
        low_ratio = float(np.clip(rms_low / rms, 0.0, 1.0))

        # Flux en HI calibrado
        flux_hi  = self._hi_flux(hi, sr)

        # Compuertas calibradas
        flux_on = float(np.clip(self.card.get_value("flux_on"), 0.04, 0.30))
        hi_req  = float(np.clip(self.card.get_value("hi_ratio_min"), 0.20, 0.65))
        raw_env = float(self.card.get_value("env_min"))
        env_min = raw_env*1e-3 if raw_env > 0.02 else raw_env
        env_min = float(np.clip(env_min, 5e-4, 8e-3))
        low_veto= float(np.clip(self.card.get_value("low_veto"), 0.35, 0.80))
        crest_min = float(np.clip(self.card.get_value("crest_min"), 8.0, 18.0))

        # Envolvente HI calibrada (10 ms) y buffer decimado
        win_env = max(1, int(0.010 * sr))
        env_hi = np.convolve(np.abs(hi), np.ones(win_env, dtype=np.float32)/win_env, mode="same")
        env_rms= float(np.sqrt(np.mean(env_hi*env_hi)) + 1e-12)
        step = max(1, int(round(sr / self._env_sr)))
        env_d = env_hi[::step].astype(np.float32)
        if env_d.size:
            self._env_buf = np.concatenate((self._env_buf, env_d))
            if self._env_buf.size > self._env_max:
                self._env_buf = self._env_buf[-self._env_max:]

        # Validación de crest factor calibrada
        if hi.size > 0:
            hi_peak = float(np.max(np.abs(hi)))
            hi_rms_local = float(np.sqrt(np.mean(hi*hi)) + 1e-12)
            crest_factor_db = 20 * np.log10(hi_peak / hi_rms_local + 1e-12)
            crest_ok = (crest_factor_db >= crest_min)
        else:
            crest_ok = False
            crest_factor_db = 0.0

        # Gating principal calibrado
        allow = (hi_ratio >= hi_req) and (flux_hi >= flux_on) and (env_rms >= env_min) and (low_ratio <= low_veto) and crest_ok

        # Sliders de continuidad calibrados
        gap_ms = float(np.clip(self.card.get_value("gap_ms"),  150.0, 500.0))
        refr   = float(np.clip(self.card.get_value("refrac"),  100.0, 200.0))
        win_s  = float(np.clip(self.card.get_value("win_s"),    2.0,  8.0))
        run_req= float(np.clip(self.card.get_value("run_req"),  1.0,  5.0))
        trem_req=float(np.clip(self.card.get_value("trem_req"), 1.3,  3.0))
        cv_max = float(np.clip(self.card.get_value("cv_max"),   0.15, 0.60))
        min_ev = int(np.clip(self.card.get_value("min_ev"),     4.0,  15.0))
        smooth = float(np.clip(self.card.get_value("smooth"),   0.0,  0.85))
        aS = np.exp(-dt / ((120.0 + (600.0-120.0)*(smooth**2))/1000.0))  # Más lento para continuidad

        # Eventos en hi (si hay permiso)
        if allow:
            pk = self._novelty_peaks(hi, sr, kx=float(np.clip(self.card.get_value("thr_x"),1.6,4.0)), refr_ms=refr)
            if pk.size:
                t0 = self._t - n/sr
                for i in pk:
                    self._events.append(t0 + i/sr)
        else:
            # Drenado más suave para continuidad
            tcut = self._t - min(0.5, win_s*0.3)  # Más conservador
            while self._events and self._events[0] < tcut:
                self._events.popleft()

        # Mantener ventana calibrada
        while self._events and (self._t - self._events[0]) > win_s:
            self._events.popleft()

        # Métricas de ráfaga calibradas
        v_raw = 0.0; run_len = 0.0; ioi_med=0.0; ioi_cv=0.0; trem=0.0
        if len(self._events) >= 2:
            ev = np.fromiter(self._events, dtype=np.float32)
            ioi = np.diff(ev)
            if ioi.size:
                ioi_med = float(np.median(ioi))
                ioi_cv  = float((np.std(ioi) / (np.mean(ioi)+1e-9)))
                gap_s = gap_ms/1000.0
                spans = []
                cur = 0.0
                for d in ioi:
                    cur += d
                    if d > gap_s:
                        spans.append(cur); cur = 0.0
                spans.append(cur)
                run_len = float(np.max(spans)) if spans else 0.0

        # Tremolo calibrado para continuidad
        need = int(max(100, round(win_s * self._env_sr)))  # Más muestras para continuidad
        if self._env_buf.size >= need:
            seg = self._env_buf[-need:]
            trem = self._tremolo_ratio(seg, 4.0, 12.0)  # Calibrado: 4-12 Hz

        # Condiciones de ATAQUE calibradas (menos estrictas para continuidad)
        fast   = (0.05 <= ioi_med <= 0.25) if ioi_med > 0 else False  # Más rango: era 0.03-0.12
        stable = (ioi_cv <= cv_max) if ioi_med > 0 else False
        enough = (len(self._events) >= min_ev) and (run_len >= 0.7*run_req)  # Menos estricto
        tremok = (trem >= trem_req)

        if allow and fast and stable and enough and tremok:
            # Score calibrado para continuidad
            v_speed = float(np.clip((0.20 - ioi_med) / (0.20 - 0.05), 0.0, 1.0))  # Rango ampliado
            v_run   = float(np.clip(run_len / max(0.5, run_req), 0.0, 1.0))
            v_trem  = float(np.clip((trem - 1.0) / (trem_req - 1.0 + 1e-6), 0.0, 1.0))
            v_cont  = float(np.clip(len(self._events) / max(1.0, min_ev * 1.5), 0.0, 1.0))  # Nuevo: continuidad
            # Pesos calibrados para continuidad (más peso a run y eventos)
            v_raw   = float(np.clip(0.40*v_run + 0.25*v_cont + 0.20*v_trem + 0.15*v_speed, 0.0, 1.0))
        else:
            v_raw = 0.0

        self._vu = (1.0 - aS)*v_raw + aS*self._vu
        v = float(np.clip(self._vu, 0.0, 1.0))
        try:
            self.card.set_status(
                f"allow={allow} | hi%={hi_ratio:.2f} | low%={low_ratio:.2f} | fluxHi={flux_hi:.2f} "
                f"| env={env_rms:.2e} | crest={crest_factor_db:.1f}dB>={crest_min:.1f} | N={len(self._events)} "
                f"run={run_len:.2f}s | ioiMed={ioi_med*1000:.0f}ms cv={ioi_cv:.2f} fast={fast} stab={stable} "
                f"| trem={trem:.2f}>=req{trem_req:.2f} ok={enough} v={v:.2f}"
            )
        except: pass
        self._render(v, dt)

    def _render(self, v, dt):
        self.card.set_value(v)
        hold_on  = float(np.clip(self.card.get_value("hold"), 200.0, 800.0))/1000.0
        hold_off = 1.6*hold_on  # Más largo para continuidad
        # Umbrales calibrados para continuidad (moderadamente exigente)
        thr_on, thr_off = 0.65, 0.55  # Moderado: más permisivo que sharpness pero más que roll básico
        if v >= thr_on:
            self._ton += dt; self._toff = 0.0
            if self._ton >= hold_on: self._on = True
        elif v <= thr_off:
            self._toff += dt; self._ton = 0.0
            if self._toff >= hold_off: self._on = False
        self.card.set_led("burst", self._on)

        lo, hi = self.card.get_thresholds()
        lo = _norm01(lo); hi = _norm01(hi)
        if hi < lo: lo, hi = hi, lo
        mreq = _norm_match(self.card.get_match())
        self.card.set_on((lo <= v <= hi) and ((v*100.0) >= mreq - 1e-6))