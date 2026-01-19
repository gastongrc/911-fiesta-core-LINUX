# analyzers/burst_sharpness.py — ATAQUE: BURST SHARPNESS (balanceado para redobles)
# v2025-09-08-balanced: menos restrictivo pero enfocado en redobles

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

class BurstSharpness:
    name = "DRUM ROLL DETECTOR"
    flag_name = "BURST_SHARPNESS"  # V10: Flag para votación en BaseGolpe

    def __init__(self):
        from module_card import ModuleCard
        self.card = ModuleCard(self.name)
        
        # Parámetros más balanceados para redobles
        self.card.add_slider("cf_min",    "Crest mín (dB)",        10.0, 20.0, 12.0)  # Menos estricto
        self.card.add_slider("cent_min",  "Centroid min (kHz)",    2.0,  6.0,  3.0)   # Más permisivo
        self.card.add_slider("win_s",     "Ventana (s)",           0.5,  1.5,  0.8)   # Más corta
        
        # Gates básicos más permisivos
        self.card.add_slider("flux_on",   "Flux mín",              0.12, 0.40, 0.20)  # Más bajo
        self.card.add_slider("hi_ratio",  "%Agudos mín",           0.30, 0.70, 0.45)  # Más permisivo
        self.card.add_slider("env_min",   "Env RMS mín (×1e-3)",   1.50, 8.00, 3.00)  # Más bajo
        self.card.add_slider("low_veto",  "Veto graves",           0.35, 0.70, 0.50)  # Más permisivo
        
        # Detección de periodicidad más suave
        self.card.add_slider("period_min", "Período mín (Hz)",     6.0,  18.0, 10.0)  # Más amplio
        self.card.add_slider("period_max", "Período máx (Hz)",     20.0, 45.0, 30.0)  # Más amplio
        self.card.add_slider("period_str", "Fuerza periodicidad",  0.15, 0.60, 0.25)  # Menos estricto
        self.card.add_slider("period_on",  "Usar periodicidad",    0.0,  1.0,  0.0)   # Switch on/off
        
        # Duración más flexible
        self.card.add_slider("dur_min",   "Duración mín (s)",      0.2,  0.8,  0.4)   # Más corto
        self.card.add_slider("dur_max",   "Duración máx (s)",      1.5,  6.0,  3.0)   # Más permisivo
        self.card.add_slider("dur_on",    "Usar duración",         0.0,  1.0,  0.0)   # Switch on/off
        
        # Scoring balanceado
        self.card.add_slider("cf_weight", "Peso Crest",            0.2,  0.8,  0.5)    
        self.card.add_slider("cent_weight","Peso Centroid",        0.1,  0.6,  0.3)    
        self.card.add_slider("flux_weight","Peso Flux",            0.1,  0.5,  0.2)    
        
        # Control visual
        self.card.add_slider("smooth",    "Suavizado",             0.05, 0.40, 0.15)  
        self.card.add_slider("hold",      "Hold ON (ms)",          100.0, 600.0, 250.0)
        self.card.add_led("sharp", "Roll Detected")

        self._vu = 0.0
        self._on = False
        self._ton = 0.0
        self._toff = 0.0
        self._burst_start = None
        self._burst_duration = 0.0
        self._env_history = []
        
        # Filtros menos agresivos
        self._lp2k = 0.0   # Volvemos a 2kHz
        self._lp200 = 0.0
        self._last_mag_hi = None

    def _lp1(self, x, sr, fc, state_attr):
        a = 1.0 - np.exp(-2.0*np.pi*fc/float(sr))
        y = np.empty_like(x, dtype=np.float32)
        s = getattr(self, state_attr)
        for i, xi in enumerate(x):
            s = s + a*(xi - s)
            y[i] = s
        setattr(self, state_attr, float(s))
        return y

    def _hi_flux(self, band_hi, sr):
        """Flux espectral en 2–10 kHz (más amplio)."""
        n = len(band_hi)
        nfft = 1
        while nfft < n: 
            nfft <<= 1
        X = np.fft.rfft(band_hi, nfft)
        mag = np.abs(X) + 1e-12
        f = np.fft.rfftfreq(nfft, 1.0/sr)
        mask = (f >= 2000.0) & (f <= 10000.0)  # Rango más amplio
        M = mag[mask]
        
        if self._last_mag_hi is None or self._last_mag_hi.shape != M.shape:
            flux = 0.0
        else:
            D = M - self._last_mag_hi
            D[D < 0] = 0.0
            flux = float(np.sum(D) / (np.sum(M) + 1e-9))
            flux = float(np.clip(flux, 0.0, 1.0))
        
        self._last_mag_hi = M
        return flux

    def _detect_periodicity(self, env, sr):
        """Detecta periodicidad de forma más suave."""
        if len(env) < 50:  # Menos restrictivo
            return 0.0
            
        # Suavizar envelope primero
        if len(env) > 10:
            kernel_size = min(5, len(env)//4)
            kernel = np.ones(kernel_size) / kernel_size
            env = np.convolve(env, kernel, mode='same')
            
        env_norm = env - np.mean(env)
        if np.std(env_norm) < 1e-8:
            return 0.0
            
        # Autocorrelación más permisiva
        autocorr = np.correlate(env_norm, env_norm, mode='full')
        autocorr = autocorr[len(autocorr)//2:]
        
        if len(autocorr) < 10:
            return 0.0
            
        period_min = float(np.clip(self.card.get_value("period_min"), 5.0, 25.0))
        period_max = float(np.clip(self.card.get_value("period_max"), 15.0, 50.0))
        
        min_lag = max(1, int(sr / period_max))
        max_lag = min(len(autocorr)-1, int(sr / period_min))
        
        if min_lag >= max_lag or max_lag <= 0:
            return 0.0
            
        search_range = autocorr[min_lag:max_lag+1]
        if len(search_range) == 0:
            return 0.0
            
        # Buscar periodicidad más suave
        max_corr = np.max(search_range)
        mean_corr = np.mean(autocorr[max_lag:max_lag+20]) if max_lag+20 < len(autocorr) else 0.0
        
        periodicity = float(np.clip((max_corr - mean_corr) / (autocorr[0] + 1e-12), 0.0, 1.0))
        return periodicity

    def process(self, block, sr):
        if block is None or sr is None or sr <= 0: 
            return
            
        x = _mono(block)
        n = len(x)
        if n == 0: 
            return
            
        dt = n/float(sr)

        # Gate de silencio más permisivo
        rms = float(np.sqrt(np.mean(x*x)) + EPS)
        if rms < 2e-4:  # Menos estricto
            a = np.exp(-dt/0.2)
            self._vu *= a
            self._reset_burst()
            try: 
                self.card.set_status("silencio")
            except: 
                pass
            self.card.set_value(0.0)
            self.card.set_led("sharp", False)
            self.card.set_on(False)
            return

        # Filtrado más suave: volvemos a 2kHz
        lp2k = self._lp1(x, sr, 2000.0, "_lp2k")  
        lp200 = self._lp1(x, sr, 200.0, "_lp200")
        hi = x - lp2k
        low = lp200

        # Parámetros más permisivos
        flux_on = float(np.clip(self.card.get_value("flux_on"), 0.08, 0.50))
        hi_req = float(np.clip(self.card.get_value("hi_ratio"), 0.25, 0.75))
        raw_env = float(self.card.get_value("env_min"))
        env_min = raw_env*1e-3 if raw_env > 0.02 else raw_env
        env_min = float(np.clip(env_min, 5e-4, 10e-3))
        low_veto = float(np.clip(self.card.get_value("low_veto"), 0.30, 0.80))

        rms_hi = float(np.sqrt(np.mean(hi*hi)) + 1e-12)
        rms_low = float(np.sqrt(np.mean(low*low)) + 1e-12)
        hi_ratio = float(np.clip(rms_hi / (rms + 1e-12), 0.0, 1.0))
        low_ratio = float(np.clip(rms_low / (rms + 1e-12), 0.0, 1.0))
        flux_hi = self._hi_flux(hi, sr)

        # Ventana más balanceada
        win_s = float(np.clip(self.card.get_value("win_s"), 0.4, 2.0))
        take = int(max(1, round(win_s * sr)))
        seg = hi[-take:]

        # Envelope
        win_env = max(1, int(0.005 * sr))  # 5ms
        env = np.convolve(np.abs(seg), np.ones(win_env, dtype=np.float32)/win_env, mode="same")
        env_rms = float(np.sqrt(np.mean(env*env)) + 1e-12)

        # Gates básicos
        basic_allow = (hi_ratio >= hi_req) and (flux_hi >= flux_on) and (env_rms >= env_min) and (low_ratio <= low_veto)

        # Periodicidad opcional
        period_on = float(self.card.get_value("period_on")) > 0.5
        if period_on and basic_allow:
            periodicity = self._detect_periodicity(env, sr)
            period_req = float(np.clip(self.card.get_value("period_str"), 0.1, 0.8))
            period_allow = periodicity >= period_req
        else:
            periodicity = 0.0
            period_allow = True

        # Duración opcional
        dur_on = float(self.card.get_value("dur_on")) > 0.5
        if dur_on:
            duration_allow = self._check_burst_duration(basic_allow, dt)
        else:
            duration_allow = True
            if basic_allow:
                self._update_burst_duration(dt)

        # Combinación final
        allow = basic_allow and period_allow and duration_allow

        # Suavizado
        smooth = float(np.clip(self.card.get_value("smooth"), 0.02, 0.50))
        aS = np.exp(-dt / ((30.0 + (200.0-30.0)*(smooth**2))/1000.0))

        if not allow:
            self._vu *= aS
            try:
                status_parts = [f"basic={basic_allow}"]
                if period_on: status_parts.append(f"period={period_allow}({periodicity:.2f})")
                if dur_on: status_parts.append(f"dur={duration_allow}({self._burst_duration:.1f}s)")
                status_parts.extend([
                    f"hi%={hi_ratio:.2f}({hi_req:.2f})",
                    f"flux={flux_hi:.2f}({flux_on:.2f})",
                    f"env={env_rms:.2e}"
                ])
                self.card.set_status(" | ".join(status_parts))
            except: 
                pass
            return self._render(float(np.clip(self._vu, 0.0, 1.0)), dt)

        # SCORING más balanceado
        v_raw = 0.0
        
        if seg.size > 0:
            # Crest Factor
            seg_rms = float(np.sqrt(np.mean(seg*seg)) + EPS)
            seg_peak = float(np.max(np.abs(seg)) + EPS)
            crest_factor_db = 20 * np.log10(seg_peak / seg_rms + 1e-12)
            cf_min = float(np.clip(self.card.get_value("cf_min"), 8.0, 25.0))
            v_cf = float(np.clip((crest_factor_db - cf_min) / max(2.0, cf_min*0.3), 0.0, 1.0))

            # Spectral centroid
            nfft = 1
            while nfft < seg.size: 
                nfft <<= 1
            X = np.fft.rfft(seg, nfft)
            mag = np.abs(X) + 1e-12
            freqs = np.fft.rfftfreq(nfft, 1.0/sr)
            maskH = (freqs >= 1500.0) & (freqs <= 12000.0)
            
            if np.any(maskH):
                centroid = float(np.sum(freqs[maskH]*mag[maskH]) / (np.sum(mag[maskH]) + 1e-12)) / 1000.0
            else:
                centroid = 0.0
            
            cent_min = float(np.clip(self.card.get_value("cent_min"), 1.5, 8.0))
            v_cent = float(np.clip((centroid - cent_min) / max(1.5, cent_min), 0.0, 1.0))

            # Flux normalizado
            v_flux = float(np.clip((flux_hi - flux_on) / max(0.1, flux_on), 0.0, 1.0))

            # Scoring con pesos
            cf_weight = float(np.clip(self.card.get_value("cf_weight"), 0.1, 0.9))
            cent_weight = float(np.clip(self.card.get_value("cent_weight"), 0.1, 0.7))
            flux_weight = float(np.clip(self.card.get_value("flux_weight"), 0.1, 0.6))
            
            # Normalizar pesos
            total_w = cf_weight + cent_weight + flux_weight
            if total_w > 0:
                cf_weight /= total_w
                cent_weight /= total_w 
                flux_weight /= total_w
            else:
                cf_weight = cent_weight = flux_weight = 1.0/3.0
            
            v_raw = float(np.clip(cf_weight*v_cf + cent_weight*v_cent + flux_weight*v_flux, 0.0, 1.0))
        else:
            crest_factor_db = centroid = v_cf = v_cent = v_flux = 0.0

        # Bonus por periodicidad si está activa
        if period_on and periodicity > 0.3:
            v_raw = min(1.0, v_raw * (1.0 + 0.3*periodicity))

        # Suavizado y render
        self._vu = (1.0 - aS)*v_raw + aS*self._vu
        v = float(np.clip(self._vu, 0.0, 1.0))
        
        try:
            status_parts = [f"DETECTED! dur={self._burst_duration:.1f}s"]
            status_parts.append(f"CF={crest_factor_db:.1f}dB→{v_cf:.2f}")
            status_parts.append(f"cent={centroid:.1f}kHz→{v_cent:.2f}")
            status_parts.append(f"flux→{v_flux:.2f}")
            if period_on: status_parts.append(f"period→{periodicity:.2f}")
            status_parts.append(f"v={v:.2f}")
            self.card.set_status(" | ".join(status_parts))
        except: 
            pass
            
        self._render(v, dt)

    def _update_burst_duration(self, dt):
        """Actualiza duración sin restricciones."""
        if self._burst_start is None:
            self._burst_start = 0.0
        self._burst_start += dt
        self._burst_duration = self._burst_start

    def _check_burst_duration(self, is_active, dt):
        """Verifica duración solo si está habilitado."""
        dur_min = float(np.clip(self.card.get_value("dur_min"), 0.1, 1.5))
        dur_max = float(np.clip(self.card.get_value("dur_max"), 1.0, 8.0))
        
        if is_active:
            self._update_burst_duration(dt)
        else:
            self._reset_burst()
            return False
            
        return self._burst_duration >= dur_min and self._burst_duration <= dur_max

    def _reset_burst(self):
        """Resetea el contador de duración."""
        self._burst_start = None
        self._burst_duration = 0.0

    def _render(self, v, dt):
        self.card.set_value(v)
        
        # Umbrales más balanceados
        hold_on = float(np.clip(self.card.get_value("hold"), 80.0, 800.0))/1000.0
        hold_off = 1.2*hold_on
        thr_on, thr_off = 0.60, 0.50  # Menos estricto
        
        if v >= thr_on:
            self._ton += dt
            self._toff = 0.0
            if self._ton >= hold_on: 
                self._on = True
        elif v <= thr_off:
            self._toff += dt
            self._ton = 0.0
            if self._toff >= hold_off: 
                self._on = False
                
        self.card.set_led("sharp", self._on)

        # Thresholds
        lo, hi = self.card.get_thresholds()
        lo = _norm01(lo)
        hi = _norm01(hi)
        if hi < lo: 
            lo, hi = hi, lo
        mreq = _norm_match(self.card.get_match())
        self.card.set_on((lo <= v <= hi) and ((v*100.0) >= mreq - 1e-6))