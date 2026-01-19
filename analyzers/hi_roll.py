# analyzers/hi_roll.py — ATAQUE: HI-ROLL (calibrado según análisis real)
# v2025-09-07-calibrated: ajustado para agudos en 4-12 kHz, crest 10.4-11.5dB, slope 1200-2200 dB/s

import numpy as np

EPS = 1e-12

def _mono(x):
    x = np.asarray(x)
    return x.astype(np.float32, copy=False) if x.ndim == 1 else x.mean(axis=1).astype(np.float32, copy=False)

def _norm01(v):
    if v is None: return 0.0
    v = float(v)
    if v > 1.5: v *= 0.01  # 0..100 -> 0..1
    return float(np.clip(v, 0.0, 1.0))

def _norm_match(m):
    try: m = float(50.0 if m is None else m)
    except: m = 50.0
    if 0.0 <= m <= 1.0: m *= 100.0
    return float(np.clip(m, 0.0, 100.0))

class HiRoll:
    name = "HI ROLL"

    def __init__(self):
        from module_card import ModuleCard
        self.card = ModuleCard(self.name)
        # Tremolo calibrado para hi-hat rolls específicos
        self.card.add_slider("win_s",      "Ventana (s)",          0.8,  2.0, 1.2)  # Más específico: era 0.6-2.5, 1.0
        self.card.add_slider("f_lo",       "F min (Hz)",           8.0, 12.0, 10.0)  # Ajustado: era 6.0-10.0, 6.5
        self.card.add_slider("f_hi",       "F max (Hz)",           15.0, 20.0, 17.0)  # Ajustado: era 10.0-18.0, 13.5
        self.card.add_slider("peak_ratio", "Pico/Media objetivo",  1.8,  3.0, 2.2)  # Más exigente: era 1.2-3.5, 1.6
        # Compuertas calibradas para hi-hat específico (4-12 kHz)
        self.card.add_slider("flux_on",     "Flux p/permitir",      0.08, 0.25, 0.12)  # Más estricto: era 0.02-0.30, 0.06
        self.card.add_slider("hi_ratio_min","%Agudos mín (rel)",    0.35, 0.65, 0.45)  # Muy estricto: era 0.10-0.60, 0.24
        self.card.add_slider("env_min",     "Env RMS mín (×1e-3)",  1.20, 4.00, 2.00)  # Ajustado: era 0.10-3.00, 1.00
        self.card.add_slider("low_veto",    "Veto low ratio",       0.35, 0.70, 0.50)  # Más estricto: era 0.40-0.90, 0.60
        # Visual
        self.card.add_slider("smooth",      "Suavizado",            0.0,  0.80, 0.20)  # Menos pegajoso: era 0.25
        self.card.add_slider("hold",        "Hold ON (ms)",         120.0, 400.0, 220.0)  # Ajustado: era 80-600, 200
        self.card.add_led("hi", "HiRoll")

        self._vu = 0.0; self._on=False; self._ton=0.0; self._toff=0.0
        # Filtros calibrados para hi-hat (más alto que snare)
        self._lp4k = 0.0   # CALIBRADO: 4kHz (era 2kHz) para hi-hat específico
        self._lp200 = 0.0
        # flux suavizado calibrado
        self._flux_s = 0.0
        self._last_mag_hi = None  # para flux en 4–12 kHz
        # buffer de envolvente (decimada a 200 Hz)
        self._env_sr = 200.0
        self._env_buf = np.zeros(0, dtype=np.float32)
        self._env_max = int(3.0 * self._env_sr)  # hasta 3 s

    def _lp1(self, x, sr, fc, state_attr):
        a = 1.0 - np.exp(-2.0*np.pi*fc/float(sr))
        y = np.empty_like(x, dtype=np.float32); s = getattr(self, state_attr)
        for i, xi in enumerate(x):
            s = s + a*(xi - s); y[i] = s
        setattr(self, state_attr, float(s)); return y

    def _flux_on_hi(self, hi, sr):
        """Flux calibrado para hi-hat: 4-12 kHz con suavizado optimizado."""
        n = len(hi); nfft = 1
        while nfft < n: nfft <<= 1
        H = np.fft.rfft(hi, nfft)
        mag = np.abs(H) + 1e-12
        f   = np.fft.rfftfreq(nfft, 1.0/sr)
        # CALIBRADO: 4-12 kHz para hi-hat específico (era 2-10 kHz)
        mask = (f >= 4000.0) & (f <= 12000.0)
        M = mag[mask]
        if self._last_mag_hi is None or self._last_mag_hi.shape != M.shape:
            flux = 0.0
        else:
            D = M - self._last_mag_hi; D[D < 0] = 0.0
            flux = float(np.sum(D) / (np.sum(M) + 1e-9))
            flux = float(np.clip(flux, 0.0, 1.0))
        self._last_mag_hi = M
        # Suavizado más agresivo para hi-hat (más estable)
        self._flux_s = 0.85 * self._flux_s + 0.15 * flux  # era 0.8/0.2
        return self._flux_s

    def process(self, block, sr):
        if block is None or sr is None or sr <= 0: return
        x = _mono(block); n = len(x)
        if n == 0: return
        dt = n/float(sr)

        # Gate de silencio duro
        rms = float(np.sqrt(np.mean(x*x)) + 1e-12)
        if rms < 2e-4:
            self._last_mag_hi = None
            self._env_buf = np.zeros(0, dtype=np.float32)
            self._flux_s = 0.0
            self._vu = 0.0; self._on=False; self._ton=0.0; self._toff=0.0
            try: self.card.set_status("silencio")
            except: pass
            self.card.set_value(0.0); self.card.set_led("hi", False); self.card.set_on(False)
            return

        # Bandas calibradas: hi = x - LP4k ; low = LP200(x)
        lp4k  = self._lp1(x, sr, 4000.0, "_lp4k")  # CALIBRADO: 4kHz para hi-hat
        lp200 = self._lp1(x, sr, 200.0,  "_lp200")
        hi  = x - lp4k  # Contenido > 4kHz
        low = lp200

        rms_hi  = float(np.sqrt(np.mean(hi*hi)) + 1e-12)
        rms_low = float(np.sqrt(np.mean(low*low)) + 1e-12)
        hi_ratio  = float(np.clip(rms_hi / rms, 0.0, 1.0))
        low_ratio = float(np.clip(rms_low / rms, 0.0, 1.0))

        flux_hi = self._flux_on_hi(hi, sr)

        # Compuertas calibradas (más estrictas para hi-hat)
        flux_on = float(np.clip(self.card.get_value("flux_on"), 0.05, 0.35))
        hi_req  = float(np.clip(self.card.get_value("hi_ratio_min"), 0.25, 0.75))
        raw_env = float(self.card.get_value("env_min"))
        env_min = raw_env*1e-3 if raw_env > 0.02 else raw_env
        env_min = float(np.clip(env_min, 5e-4, 8e-3))  # Calibrado para hi-hat
        low_veto= float(np.clip(self.card.get_value("low_veto"), 0.30, 0.75))

        # Envolvente hi calibrada (8 ms para hi-hat rápido)
        win = max(1, int(0.008 * sr))
        env = np.convolve(np.abs(hi), np.ones(win, dtype=np.float32)/win, mode="same")
        env_rms = float(np.sqrt(np.mean(env*env)) + 1e-12)
        
        # Decimación a 200 Hz
        step = max(1, int(round(sr / self._env_sr)))
        env_d = env[::step].astype(np.float32)

        # Acumular buffer de envolvente
        if env_d.size:
            self._env_buf = np.concatenate((self._env_buf, env_d))
            if self._env_buf.size > self._env_max:
                self._env_buf = self._env_buf[-self._env_max:]

        # Validación adicional: Crest Factor para hi-hat
        if hi.size > 0:
            hi_peak = float(np.max(np.abs(hi)))
            hi_rms_local = float(np.sqrt(np.mean(hi*hi)) + 1e-12)
            crest_factor_db = 20 * np.log10(hi_peak / hi_rms_local + 1e-12)
            crest_ok = (9.0 <= crest_factor_db <= 16.0)  # Hi-hat puede tener más crest
        else:
            crest_ok = False
            crest_factor_db = 0.0

        # Compuerta principal calibrada + fallback para hi-hat energético
        allow_core = (hi_ratio >= hi_req) and (env_rms >= env_min) and (low_ratio <= low_veto) and crest_ok
        allow_flux = (flux_hi >= flux_on) or (env_rms >= 3.0*env_min and hi_ratio >= (hi_req + 0.15))
        allow = allow_core and allow_flux

        # Suavizado visual calibrado
        smooth = float(np.clip(self.card.get_value("smooth"), 0.0, 0.85))
        aS = np.exp(-dt / ((60.0 + (400.0-60.0)*(smooth**2))/1000.0))  # Más rápido

        # Verificar buffer de envolvente
        win_s = float(np.clip(self.card.get_value("win_s"), 0.8, 2.5))
        need = int(max(80, round(win_s * self._env_sr)))  # muestras decimadas requeridas
        
        if self._env_buf.size < need or not allow:
            self._vu *= aS
            try:
                if self._env_buf.size < need:
                    self.card.set_status(f"fill {self._env_buf.size}/{need} | allow={allow} | hi%={hi_ratio:.2f} | low%={low_ratio:.2f} | flux={flux_hi:.2f}({flux_on:.2f}) | env={env_rms:.2e}>=min{env_min:.2e} | crest={crest_factor_db:.1f}dB")
                else:
                    self.card.set_status(f"allow={allow} | hi%={hi_ratio:.2f} | low%={low_ratio:.2f} | flux={flux_hi:.2f}({flux_on:.2f}) | env={env_rms:.2e}>=min{env_min:.2e} | crest={crest_factor_db:.1f}dB")
            except: pass
            return self._render(float(np.clip(self._vu,0.0,1.0)), dt)

        # FFT del tremolo calibrado para hi-hat
        seg = self._env_buf[-need:].astype(np.float32)
        seg -= float(np.mean(seg))
        nfft = 1
        while nfft < seg.size: nfft <<= 1
        E = np.fft.rfft(seg, nfft)
        P = (E.real*E.real + E.imag*E.imag) + 1e-20
        freqs = np.fft.rfftfreq(nfft, 1.0/self._env_sr)

        # Frecuencias calibradas para hi-hat roll
        f_lo  = float(np.clip(self.card.get_value("f_lo"),  6.0, 15.0))
        f_hi  = float(np.clip(self.card.get_value("f_hi"),  12.0, 25.0))
        pr_ok = float(np.clip(self.card.get_value("peak_ratio"), 1.5, 4.0))

        mask = (freqs >= f_lo) & (freqs <= f_hi)
        if not np.any(mask):
            v_raw = 0.0; ratio = 0.0
        else:
            band = float(np.mean(P[mask])); peak = float(np.max(P[mask]))
            ratio = float(np.clip(peak / max(band, 1e-9), 0.0, 12.0))
            v_raw = float(np.clip((ratio - 1.0)/max(1e-6, pr_ok - 1.0), 0.0, 1.0))

        self._vu = (1.0 - aS)*v_raw + aS*self._vu
        v = float(np.clip(self._vu, 0.0, 1.0))
        try:
            self.card.set_status(f"ok | hi%={hi_ratio:.2f} | low%={low_ratio:.2f} | fluxS={flux_hi:.2f}({flux_on:.2f}) | env={env_rms:.2e}>=min{env_min:.2e} | crest={crest_factor_db:.1f}dB | peak/band={ratio:.2f} | v={v:.2f}")
        except: pass
        self._render(v, dt)

    def _render(self, v, dt):
        self.card.set_value(v)
        hold_on  = float(np.clip(self.card.get_value("hold"), 120.0, 400.0))/1000.0
        hold_off = 1.4*hold_on  # Ligeramente más corto
        # Umbrales calibrados para hi-hat (más exigente)
        thr_on, thr_off = 0.70, 0.60  # Más exigente: era 0.60, 0.50
        if v >= thr_on:
            self._ton += dt; self._toff = 0.0
            if self._ton >= hold_on: self._on = True
        elif v <= thr_off:
            self._toff += dt; self._ton = 0.0
            if self._toff >= hold_off: self._on = False
        self.card.set_led("hi", self._on)

        lo, hi = self.card.get_thresholds()
        lo = _norm01(lo); hi = _norm01(hi)
        if hi < lo: lo, hi = hi, lo
        mreq = _norm_match(self.card.get_match())
        self.card.set_on((lo <= v <= hi) and ((v*100.0) >= mreq - 1e-6))