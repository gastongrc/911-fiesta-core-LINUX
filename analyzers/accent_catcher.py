# analyzers/accent_catcher.py – ACCENT CATCHER (opuesto de SoftPeaks)
# Idea: SoftPeaks sube con transitorios SUAVES; AccentCatcher sube con ACENTOS FUERTES.
import numpy as np
from collections import deque
from base_module import BaseModule
from module_card import ModuleCard
from dsp_utils import mono

class AccentCatcher(BaseModule):
    name = "ACCENT CATCHER"
    flag_name = "ACCENT_CATCHER"  # V11: Flag para votación en BaseGolpe

    def __init__(self):
        super().__init__()
        self.card = ModuleCard(self.name)
        
        # Controles principales - OPTIMIZADO
        self.card.add_slider("sens",        "Sensibilidad",         0.2,  2.0, 0.9)
        self.card.add_slider("attack",      "Ventana (ms)",         6,    40,  12)
        self.card.add_slider("ratio",       "Ratio Lento",          2.0,  8.0, 4.0)
        self.card.add_slider("kl",          "K bajo",               0.5,  2.0, 0.9)
        self.card.add_slider("kh",          "K alto",               1.2,  3.0, 1.8)
        self.card.add_slider("smooth",      "Suavizado",            0.05, 0.5, 0.18)
        
        # Controles de densidad
        self.card.add_slider("dens_thresh", "Umbral Densidad",      0.1,  0.4, 0.25)
        self.card.add_slider("dens_boost",  "Boost Densidad",       1.0,  2.0, 1.25)
        self.card.add_slider("dens_cut",    "Corte Esporádico",     0.01, 0.05, 0.02)
        self.card.add_slider("sparse_atten", "Atenuar Esporádico",  0.3,  0.9, 0.7)
        
        # NUEVO: slider de hold
        self.card.add_slider("hold", "Hold LED (ms)", 20, 300, 60)
        
        self.card.add_led("accent", "Acentos fuertes")

        # Estado - OPTIMIZADO
        self._ema = 0.0
        self._p95_hist = deque(maxlen=100)  # Reducido de 200 a 100
        self._dbg = 0
        self._debug_enabled = False
        self._led_timer = 0.0  # Timer para hold del LED
        self.detected = False  # V11: Flag para votación en BaseGolpe

    # ---------- helpers ----------
    @staticmethod
    def _rms_env(x: np.ndarray, sr: int, ms: float) -> np.ndarray:
        """Calcula envolvente RMS OPTIMIZADA con ventana deslizante."""
        n = max(5, int(sr * (ms / 1000.0)))
        if n % 2 == 0: 
            n += 1
        
        # ✅ OPTIMIZADO: RMS directo sin conversión STD
        w = np.ones(n, dtype=np.float32) / float(n)
        rms_result = np.sqrt(np.convolve(x**2, w, mode="same") + 1e-12)
        return rms_result

    @staticmethod
    def _norm01(v):
        """Normaliza valor a rango [0, 1]."""
        if v is None: 
            return 0.0
        v = float(v)
        if v > 1.5: 
            v *= 0.01
        return float(np.clip(v, 0.0, 1.0))

    @staticmethod
    def _norm_match(val):
        """Normaliza valor de match a porcentaje."""
        m = 50.0 if val is None else float(val)
        if 0.0 <= m < 1.0: 
            m *= 100.0
        elif m == 1.0:     
            m = 1.0
        return float(np.clip(m, 0.0, 100.0))

    def _validate_input(self, block, sr):
        """Valida parámetros de entrada."""
        if block is None or block.size == 0:
            return False
        if sr <= 0 or sr > 192000:  # Límite realista para sample rate
            return False
        if len(block.shape) > 2:  # Evita arrays multidimensionales
            return False
        return True

    def _calculate_robust_baseline(self, rel):
        """Calcula baseline robusto usando MAD."""
        self._p95_hist.append(float(np.percentile(rel, 95)))
        
        if len(self._p95_hist) >= 20:
            hist_array = np.array(self._p95_hist)  # Más eficiente
            med = float(np.median(hist_array))
            mad = float(np.median(np.abs(hist_array - med))) + 1e-9
        else:
            med = float(np.median(rel))
            mad = float(np.median(np.abs(rel - med))) + 1e-9

        sigma = 1.4826 * mad
        return med, sigma

    def _handle_flat_signal(self, rel):
        """Maneja casos de señal plana usando percentiles."""
        baseline = float(np.percentile(rel, 75))
        top = float(np.percentile(rel, 90))
        
        # Asegurar separación mínima
        if top <= baseline:
            baseline = float(np.mean(rel))
            top = baseline + 1e-4
            
        return baseline, top

    def _apply_density_adjustments(self, v_raw, dens):
        """Aplica ajustes basados en densidad de transitorios."""
        dens_thresh = float(self.card.get_value("dens_thresh"))
        dens_boost = float(self.card.get_value("dens_boost"))
        dens_cut = float(self.card.get_value("dens_cut"))
        sparse_atten = float(self.card.get_value("sparse_atten"))
        
        if dens > dens_thresh:
            # Más denso → más acento (boost)
            v_raw *= dens_boost
        elif dens < dens_cut:
            # Ultra esporádico → menos (evita clicks sueltos)
            v_raw *= sparse_atten
            
        return float(np.clip(v_raw, 0.0, 1.0))

    def _log_debug_info(self, v, tmax, med, sigma, dens):
        """Log de información de debug."""
        try:
            print(f"[AccentCatcher] v={v:.3f} | tmax={tmax:.4g} | "
                  f"med={med:.4g} | σ={sigma:.4g} | dens={dens:.3f}")
        except Exception:
            pass

    def process(self, block, sr):
        try:
            if not self._validate_input(block, sr):
                return

            x = mono(block).astype(np.float32)
            n = len(x)
            dt = n / float(sr)  # Tiempo del bloque

            # 1) Parámetros de control
            atk_ms = float(np.clip(self.card.get_value("attack"), 4.0, 60.0))
            ratio = float(self.card.get_value("ratio"))
            
            # 2) Envolventes: rápida vs lenta
            env_f = self._rms_env(x, sr, atk_ms)
            env_s = self._rms_env(x, sr, max(16.0, atk_ms * ratio))

            # 3) Cálculo de incrementos relativos
            inc = env_f - env_s
            rel = np.maximum(0.0, inc) / (env_s + 1e-8)

            # 4) Estadísticos del bloque
            tmax = float(np.max(rel))
            dens = float(np.mean(rel > 0.0))

            # 5) Baseline robusto con historia
            med, sigma = self._calculate_robust_baseline(rel)
            
            # 6) Cálculo de umbrales
            sens = float(self.card.get_value("sens"))
            kl = float(self.card.get_value("kl"))
            kh = float(self.card.get_value("kh"))

            if sigma < 1e-6:
                # Señal plana → usar percentiles
                baseline, top = self._handle_flat_signal(rel)
            else:
                baseline = med + sigma * (sens * kl)
                top = med + sigma * max(1.0, sens * kh)

            # 7) ***DETECCIÓN DE ACENTOS FUERTES***
            # Medir cuánto se excede del umbral superior
            denom = max(1e-6, (top - baseline))
            over = max(0.0, (tmax - top)) / denom
            v_raw = float(np.clip(over, 0.0, 1.0))

            # 8) Ajustes por densidad
            v_raw = self._apply_density_adjustments(v_raw, dens)

            # 9) Suavizado temporal
            smooth_factor = float(np.clip(self.card.get_value("smooth"), 0.0, 1.0))
            self._ema = (1.0 - smooth_factor) * self._ema + smooth_factor * v_raw
            v = float(np.clip(self._ema, 0.0, 1.0))

            # 10) Actualizar UI
            self.card.set_value(v)
            
            # 11) LED con HOLD - NUEVO
            hold_ms = float(self.card.get_value("hold"))
            
            if v > 0.35:
                self._led_timer = hold_ms
            else:
                self._led_timer = max(0.0, self._led_timer - (dt * 1000.0))
            
            self.card.set_led("accent", self._led_timer > 0)
            self.detected = self._led_timer > 0  # V11: Flag para votación

            # 12) Control ON/OFF universal
            lo, hi = self.card.get_thresholds()
            lo = self._norm01(lo)
            hi = self._norm01(hi)
            if hi < lo: 
                lo, hi = hi, lo
            
            mreq = self._norm_match(self.card.get_match())
            self.card.set_on((lo <= v <= hi) and ((v * 100.0) >= mreq - 1e-6))

            # 13) Debug periódico
            self._dbg += 1
            if (self._dbg % 400) == 0 and self._debug_enabled:
                self._log_debug_info(v, tmax, med, sigma, dens)

        except Exception as e:
            # Fail-safe robusto
            if self._debug_enabled:
                print(f"[AccentCatcher] Error: {e}")
            # Mantener estado estable en caso de error
            try:
                self.card.set_value(0.0)
                self.card.set_led("accent", False)
                self.card.set_on(False)
            except Exception:
                pass

    def enable_debug(self, enable=True):
        """Habilita/deshabilita modo debug."""
        self._debug_enabled = enable
        
    def reset_state(self):
        """Reinicia el estado interno del módulo."""
        self._ema = 0.0
        self._p95_hist.clear()
        self._dbg = 0
        self._led_timer = 0.0