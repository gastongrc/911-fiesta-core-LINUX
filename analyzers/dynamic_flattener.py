# analyzers/dynamic_flattener.py – BAJADA: baja dinámica (RMS vs pico)
# v2025-09-05: corrección completa - encoding, optimización, lógica mejorada
# v2025-10-02-OPTIMIZED: smooth default 0.25 → 0.40

import numpy as np
from module_card import ModuleCard
from dsp_utils import mono

EPS = 1e-12

def _norm01(v):
    """Normaliza valor a rango [0,1], maneja porcentajes 0-100"""
    if v is None: 
        return 0.0
    try:
        v = float(v)
        if v > 1.5:
            v *= 0.01
        return float(np.clip(v, 0.0, 1.0))
    except (ValueError, TypeError):
        return 0.0

def _norm_match(m):
    """Normaliza match a rango [0,100]"""
    try: 
        m = float(50.0 if m is None else m)
    except (ValueError, TypeError): 
        m = 50.0
    
    if 0.0 <= m <= 1.0:
        m *= 100.0
    return float(np.clip(m, 0.0, 100.0))

class DynamicFlattener:
    name = "DYNAMIC FLATTENER"

    def __init__(self):
        self.card = ModuleCard(self.name)
        
        # Parámetros principales
        self.card.add_slider("rdmax",   "Rango dinámico máx (dB)",  2.0, 30.0, 8.0)
        self.card.add_slider("sil_db",  "Gate silencio (dB)",      30.0, 80.0, 60.0)
        # CORRECCIÓN: smooth default 0.25 → 0.40
        self.card.add_slider("smooth",  "Suavizado", 0.0, 0.95, 0.40)
        
        self.card.add_led("flat", "Dinámica baja")

        # Estado interno
        self._vu = 0.0
        self._debug_counter = 0
        
        # Cache para optimización
        self._cached_kernel = None
        self._cached_kernel_size = 0
        
        # Estadísticas
        self._stats = {
            'silent_blocks': 0,
            'processed_blocks': 0,
            'avg_crest': 0.0,
            'avg_dbfs': -60.0
        }

    def _get_env_kernel(self, n):
        """Cache del kernel de convolución"""
        if self._cached_kernel_size != n or self._cached_kernel is None:
            self._cached_kernel = np.ones(n, dtype=np.float32) / float(n)
            self._cached_kernel_size = n
        return self._cached_kernel

    def _env_rms_optimized(self, x, sr, window_ms=10.0):
        """Cálculo optimizado de envolvente RMS"""
        if x.size == 0:
            return np.array([], dtype=np.float32)
            
        n = max(3, int(sr * (window_ms / 1000.0)))
        if n % 2 == 0:
            n += 1
            
        n = min(n, min(1024, x.size))
        
        try:
            kernel = self._get_env_kernel(n)
            x_squared = np.square(x.astype(np.float32))
            env_squared = np.convolve(x_squared, kernel, mode="same")
            return np.sqrt(np.maximum(env_squared, EPS))
        except Exception:
            return np.full_like(x, float(np.sqrt(np.mean(x*x)) + EPS), dtype=np.float32)

    def _calculate_smoothing_params(self, smooth_param, dt):
        """Calcula parámetros de suavizado"""
        smooth_normalized = np.clip(smooth_param, 0.0, 0.95)
        tau_ms = 50.0 + (650.0 - 50.0) * (smooth_normalized ** 1.5)
        tau_seconds = max(tau_ms / 1000.0, dt * 2)
        alpha = np.exp(-dt / tau_seconds)
        return tau_ms, alpha

    def _analyze_dynamics(self, x, sr):
        """Análisis completo de dinámica"""
        try:
            env = self._env_rms_optimized(x, sr, window_ms=8.0)
            
            if env.size == 0:
                return 0.0, 0.0, 0.0
            
            rms_env = float(np.sqrt(np.mean(np.square(env))) + EPS)
            percentile_90 = float(np.percentile(env, 90))
            percentile_10 = float(np.percentile(env, 10))
            
            crest_db = 20.0 * np.log10((percentile_90 / (rms_env + EPS)) + EPS)
            dynamic_range_db = 20.0 * np.log10((percentile_90 / (percentile_10 + EPS)) + EPS)
            
            return crest_db, dynamic_range_db, rms_env
        except Exception:
            return 6.0, 12.0, float(np.sqrt(np.mean(x*x)) + EPS)

    def process(self, block, sr):
        """Procesamiento principal"""
        if block is None or sr is None or sr <= 0:
            return
            
        x = mono(block).astype(np.float32, copy=False)
        n = x.size
        if n == 0:
            return
            
        dt = n / float(sr)
        self._stats['processed_blocks'] += 1

        rms_global = float(np.sqrt(np.mean(np.square(x))) + EPS)
        dbfs = 20.0 * np.log10(rms_global + EPS)
        self._stats['avg_dbfs'] = 0.95 * self._stats['avg_dbfs'] + 0.05 * dbfs

        sil_threshold = float(np.clip(self.card.get_value("sil_db"), 30.0, 80.0))
        
        if dbfs < -sil_threshold:
            self._stats['silent_blocks'] += 1
            tau_silence = 0.15
            alpha_silence = np.exp(-dt / tau_silence)
            self._vu = (1.0 - alpha_silence) * 0.95 + alpha_silence * self._vu
            
            v_final = float(np.clip(self._vu, 0.0, 1.0))
            return self._render_output(v_final, crest_db=0.0, dbfs=dbfs, is_silent=True)

        crest_db, dynamic_range_db, rms_env = self._analyze_dynamics(x, sr)
        self._stats['avg_crest'] = 0.9 * self._stats['avg_crest'] + 0.1 * crest_db

        rdmax = float(np.clip(self.card.get_value("rdmax"), 2.0, 30.0))
        combined_metric = 0.7 * crest_db + 0.3 * dynamic_range_db
        v_raw = float(np.clip(1.0 - (combined_metric / rdmax), 0.0, 1.0))
        v_raw = v_raw ** 0.8

        smooth_param = float(np.clip(self.card.get_value("smooth"), 0.0, 0.95))
        tau_ms, alpha = self._calculate_smoothing_params(smooth_param, dt)
        
        self._vu = (1.0 - alpha) * v_raw + alpha * self._vu
        v_final = float(np.clip(self._vu, 0.0, 1.0))

        return self._render_output(v_final, crest_db=crest_db, dbfs=dbfs, 
                                 dynamic_range=dynamic_range_db, tau_ms=tau_ms)

    def _render_output(self, v, crest_db=0.0, dbfs=0.0, is_silent=False, 
                      dynamic_range=0.0, tau_ms=0.0):
        """Actualización de interfaz"""
        self.card.set_value(v)
        self.card.set_led("flat", v >= 0.5)

        lo, hi = self.card.get_thresholds()
        lo, hi = _norm01(lo), _norm01(hi)
        if hi < lo:
            lo, hi = hi, lo
            
        match_req = _norm_match(self.card.get_match())
        in_range = lo <= v <= hi
        meets_match = (v * 100.0) >= (match_req - 0.1)
        
        self.card.set_on(in_range and meets_match)

        self._debug_counter += 1
        if (self._debug_counter % 45) == 0:
            try:
                self._update_detailed_status(v, crest_db, dbfs, is_silent, 
                                           dynamic_range, tau_ms, match_req, 
                                           in_range, meets_match)
            except Exception:
                self.card.set_status(f"v={v:.2f}")

    def _update_detailed_status(self, v, crest_db, dbfs, is_silent, 
                               dynamic_range, tau_ms, match_req, in_range, meets_match):
        """Status detallado"""
        status_parts = [f"{dbfs:.1f}dBFS"]
        
        if is_silent:
            status_parts.append("SILENT")
        else:
            status_parts.append(f"C={crest_db:.1f}dB")
            if dynamic_range > 0:
                status_parts.append(f"DR={dynamic_range:.1f}dB")
        
        status_parts.append(f"v={v:.2f}")
        
        if not in_range:
            status_parts.append("OUT_RANGE")
        elif not meets_match:
            status_parts.append(f"<MATCH({match_req:.0f}%)")
        else:
            status_parts.append("ON")
        
        if tau_ms > 0 and not is_silent and tau_ms > 200:
            status_parts.append(f"τ={tau_ms:.0f}ms")
        
        if (self._debug_counter % 180) == 0:
            silent_ratio = self._stats['silent_blocks'] / max(self._stats['processed_blocks'], 1)
            if silent_ratio > 0.1:
                status_parts.append(f"sil={silent_ratio:.1%}")
        
        self.card.set_status(" | ".join(status_parts))

    def get_analysis_info(self):
        """Información para debugging"""
        return {
            "current_vu": self._vu,
            "debug_counter": self._debug_counter,
            "kernel_cache_size": self._cached_kernel_size,
            "stats": self._stats.copy(),
            "kernel_cached": self._cached_kernel is not None
        }

    def reset_stats(self):
        """Reinicia estadísticas"""
        self._stats = {
            'silent_blocks': 0,
            'processed_blocks': 0,
            'avg_crest': 0.0,
            'avg_dbfs': -60.0
        }
        self._debug_counter = 0