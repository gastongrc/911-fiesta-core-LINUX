# analyzers/ambient_confirmator.py – AMBIENT CONFIRMATOR (calma/ambient)
# v2025-09-05: Fix completo - encoding, lógica silencio, parámetros configurables
# v2025-10-02-OPTIMIZED: smooth default 0.25 → 0.50

import numpy as np
from base_module import BaseModule
from module_card import ModuleCard
from dsp_utils import band_energy, mono

EPS = 1e-12

def _norm_match(m):
    """0..1 o 0..100 → 0..100 (incluye m==1.0 ⇒ 100%)."""
    try:
        m = float(50.0 if m is None else m)
    except:
        m = 50.0
    if 0.0 <= m <= 1.0:
        m *= 100.0
    return float(np.clip(m, 0.0, 100.0))

class AmbientConfirmator(BaseModule):
    name = "AMBIENT CONFIRMATOR"

    def __init__(self):
        super().__init__()
        self.card = ModuleCard(self.name)
        
        # Estabilidad/LED
        self.card.add_slider("tol",    "Tolerancia",          0.20, 0.95, 0.60)
        self.card.add_slider("stab",   "Estabilidad (ms)",     200, 1500, 600)
        
        # Gate & suavizado
        self.card.add_slider("sil_db", "Gate silencio (dB)",  40.0, 70.0, 60.0)
        # CORRECCIÓN: smooth default 0.25 → 0.50
        self.card.add_slider("smooth", "Suavizado",            0.0, 0.95, 0.50)
        
        # Parámetros configurables
        self.card.add_slider("trans_weight", "Peso Transitorios", 0.0, 1.0, 0.6)
        self.card.add_slider("high_sens", "Sensib. Agudos", 1.0, 10.0, 5.0)
        self.card.add_slider("silence_mode", "Modo Silencio", 0.0, 1.0, 0.0)

        self.card.add_led("amb", "Ambient")

        # Estado interno
        self._vu = 0.0
        self._ms_ok = 0.0
        self._last_valid_v = 0.5
        self._dbg = 0

    def _smooth_step(self, v_raw, dt):
        """Suavizado temporal con τ configurable"""
        smooth = float(np.clip(self.card.get_value("smooth"), 0.0, 0.95))
        tau_ms = 80.0 + (600.0 - 80.0) * (smooth ** 2)
        a = np.exp(-dt / (tau_ms / 1000.0))
        self._vu = (1.0 - a) * v_raw + a * self._vu
        return float(np.clip(self._vu, 0.0, 1.0))

    def _stable_update(self, v, dt):
        """Actualiza contador de estabilidad"""
        tol = float(np.clip(self.card.get_value("tol"), 0.0, 1.0))
        if v >= tol:
            self._ms_ok += dt * 1000.0
        else:
            self._ms_ok *= 0.95

    def _detect_transients_improved(self, x, sr):
        """Detección de transitorios mejorada"""
        if len(x) < 64:
            return 0.0
            
        hop_size = max(32, len(x) // 16)
        energy_frames = []
        
        for i in range(0, len(x) - hop_size, hop_size):
            frame = x[i:i + hop_size]
            frame_energy = np.sum(frame ** 2)
            energy_frames.append(frame_energy)
        
        if len(energy_frames) < 3:
            return 0.0
        
        energy_frames = np.array(energy_frames)
        energy_diff = np.abs(np.diff(energy_frames))
        mean_energy = np.mean(energy_frames) + EPS
        transient_ratio = np.sum(energy_diff) / (mean_energy * len(energy_diff))
        
        return float(np.clip(transient_ratio, 0.0, 1.0))

    def _detect_transients_classic(self, x):
        """Método clásico como fallback"""
        d = np.diff(x, prepend=x[0])
        trans = float(np.clip(np.std(d) / (np.std(x) + EPS), 0.0, 1.0))
        return trans

    def process(self, block, sr):
        """Procesamiento principal"""
        if block is None or sr is None or sr <= 0:
            return
            
        x = mono(block)
        if x is None or x.size == 0:
            return
            
        if not np.isfinite(x).any():
            return
            
        x = x.astype(np.float32, copy=False)
        n = x.size
        dt = n / float(sr)

        # Nivel global
        rms = float(np.linalg.norm(x) / np.sqrt(n))
        dbfs = 20.0 * np.log10(rms + EPS)

        # Gate de silencio
        sil_db = float(np.clip(self.card.get_value("sil_db"), 30.0, 80.0))
        silence_mode = self.card.get_value("silence_mode")
        
        if dbfs < -sil_db:
            if silence_mode > 0.5:
                v_raw = 1.0
            else:
                v_raw = self._last_valid_v * 0.9
                
            v = self._smooth_step(v_raw, dt)
            self._stable_update(v, dt)
            self._render(v, dbfs, trans=0.0, rel_hi=0.0)
            return

        # Análisis de contenido
        try:
            trans = self._detect_transients_improved(x, sr)
        except:
            trans = self._detect_transients_classic(x)
            
        calm = 1.0 - trans

        # Análisis de frecuencias agudas
        hi_hi = float(min(16000.0, 0.45 * sr))
        hi_lo = 6000.0 if hi_hi >= 6000.0 else 0.5 * hi_hi
        
        try:
            _, _, rel_hi = band_energy(x, sr, hi_lo, hi_hi)
        except:
            rel_hi = 0.0
            
        high_sens = float(self.card.get_value("high_sens"))
        few_high = float(np.clip(1.0 - high_sens * rel_hi, 0.0, 1.0))

        # Mezcla configurable
        trans_weight = float(self.card.get_value("trans_weight"))
        v_raw = trans_weight * calm + (1.0 - trans_weight) * few_high
        v = self._smooth_step(v_raw, dt)
        
        self._last_valid_v = v
        self._stable_update(v, dt)
        self._render(v, dbfs, trans=trans, rel_hi=rel_hi)

    def _render(self, v, dbfs, trans=0.0, rel_hi=0.0):
        """Renderizado de UI"""
        self.card.set_value(v)
        
        stable = self._ms_ok >= float(self.card.get_value("stab"))
        self.card.set_led("amb", stable)

        mreq = _norm_match(self.card.get_match())
        self.card.set_on((v * 100.0) >= mreq)

        self._dbg += 1
        if (self._dbg % 90) == 0:
            try:
                stable_str = 'ON' if stable else 'off'
                status = (f"{dbfs:.1f} dBFS | trans={trans:.2f} | "
                         f"hi_rel={rel_hi:.2f} | v={v:.2f} | LED={stable_str}")
                self.card.set_status(status)
            except Exception:
                pass

    tick = process

    def get_debug_info(self):
        """Información de debug"""
        return {
            'current_vu': self._vu,
            'stability_ms': self._ms_ok,
            'last_valid': self._last_valid_v,
            'stable_threshold': self.card.get_value("stab"),
            'tolerance': self.card.get_value("tol")
        }

    def reset_state(self):
        """Reset del estado"""
        self._vu = 0.0
        self._ms_ok = 0.0
        self._last_valid_v = 0.5
        self._dbg = 0