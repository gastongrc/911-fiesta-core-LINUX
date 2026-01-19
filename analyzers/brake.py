# analyzers/brake.py
"""
BRAKE ANALYZER - DeadAirSentinel (DAS)
Detector de corte real / dead air con confirmación y histéresis
Tuned for 911 Fiesta: sensible a cortes de ~12 dB con confirmación corta
"""

try:
    from module_card import ModuleCard
except ImportError:
    from ui.module_card import ModuleCard

import numpy as np
import time
from collections import deque

EPS = 1e-12


def _mono(x):
    """Convierte a mono si es necesario"""
    x = np.asarray(x)
    return x.astype(np.float32, copy=False) if x.ndim == 1 else x.mean(axis=1).astype(np.float32, copy=False)


def _mad(a):
    """Median Absolute Deviation"""
    if len(a) == 0: return 0.0
    m = np.median(a)
    return float(np.median(np.abs(a - m)) + 1e-12)


class BrakeAnalyzer:
    """
    DeadAirSentinel: Detector de corte real combinando múltiples señales
    """
    
    def __init__(self):
        self.name = "BRAKE ANALYZER (DAS)"
        self.card = ModuleCard(self.name)
        
        # Parámetros de detección - 911-Fiesta tuned
        self.card.add_slider("win_short", "Vent corta (s)",    0.08, 0.30, 0.14)
        self.card.add_slider("win_long",  "Vent larga (s)",    0.8,  2.5,  1.20)
        self.card.add_slider("drop_db_req", "Drop dB req",     8.0,  20.0, 12.0)
        self.card.add_slider("void_s",    "Void req (s)",      0.6,  2.5,  1.2)
        self.card.add_slider("flux_max",  "Flux máx",          0.05, 0.30, 0.12)
        self.card.add_slider("confirm_s", "Confirm (s)",       0.5,  2.5,  1.0)
        self.card.add_slider("smooth",    "Suavizado",         0.0,  0.90, 0.50)
        self.card.add_slider("hold",      "Hold ON (ms)",      200.0, 1200.0, 550.0)
        self.card.add_slider("hold_off",  "Hold OFF (ms)",     200.0, 1500.0, 700.0)
        
        # Histéresis
        self.card.add_slider("thr_on",  "Thr ON",   0.30, 0.90, 0.60)
        self.card.add_slider("thr_off", "Thr OFF",  0.20, 0.85, 0.50)
        
        # LED principal
        self.card.add_led("brake", "BRAKE")
        
        # Estados internos - Energía
        self._eS = 0.0  # EMA corta (RMS^2)
        self._eL = 0.0  # EMA larga (RMS^2)
        self._baseline_rms = 0.0  # Baseline adaptativo (~10s)
        
        # Estados internos - Flux y onsets
        self._last_mag = None
        self._flux_history = deque(maxlen=150)  # ~3s @ 50fps
        self._last_onset_t = -1e9
        self._t = 0.0  # Tiempo transcurrido
        
        # Estados internos - Score y decisión
        self._vu = 0.0  # Score suavizado
        self._ok_time = 0.0  # Tiempo acumulado cumpliendo condiciones
        self._on = False
        self._t_on = 0.0
        self._t_off = 0.0
        
        # Debug
        self._last_log_state = False
        self._frame_count = 0
        
    def _get_param(self, name, default):
        """Helper para leer parámetro con fallback"""
        try:
            return float(self.card.get_value(name))
        except:
            return float(default)
    
    def _detect_onsets(self, x, sr, refrac_ms=120.0):
        """
        Detecta onsets usando derivada positiva de envolvente
        Retorna True si hay onset en este frame
        """
        if len(x) < 2:
            return False
            
        # Envolvente suavizada
        win = max(1, int(0.010 * sr))
        env = np.abs(x)
        env = np.convolve(env, np.ones(win, dtype=np.float32)/win, mode="same")
        
        # Derivada positiva
        dpos = np.maximum(np.diff(env, prepend=env[0]), 0.0)
        
        # Umbral adaptativo basado en mediana + MAD
        thr = float(np.median(dpos) + 2.2 * 1.4826 * _mad(dpos))
        
        # Candidatos
        cand = np.where(dpos > thr)[0]
        if cand.size == 0:
            return False
        
        # Refractario: solo permitir onsets espaciados
        refr_samples = int((refrac_ms/1000.0) * sr)
        time_since_last = (self._t - self._last_onset_t) * sr
        
        # Si hay candidato y pasó suficiente tiempo
        if time_since_last >= refr_samples:
            # Verificar que sea pico local
            for i in cand:
                i0 = max(0, i-2)
                i1 = min(dpos.size, i+3)
                if dpos[i] == np.max(dpos[i0:i1]):
                    return True
        
        return False
    
    def _compute_flux(self, x, sr):
        """
        Calcula spectral flux normalizado con ventana Hann
        Retorna flux en [0..1] aproximadamente
        """
        n = len(x)
        if n < 4:
            return 0.0
        
        # FFT con ventana Hann
        nfft = 1
        while nfft < n:
            nfft <<= 1
        
        windowed = x * np.hanning(n)
        X = np.fft.rfft(windowed, nfft)
        mag = np.abs(X) + 1e-12
        
        # Flux = suma de incrementos positivos
        if self._last_mag is None or self._last_mag.shape != mag.shape:
            flux = 0.0
        else:
            diff = mag - self._last_mag
            diff[diff < 0] = 0.0
            flux = float(np.sum(diff) / (np.sum(mag) + 1e-9))
            flux = float(np.clip(flux, 0.0, 1.0))
        
        self._last_mag = mag
        self._flux_history.append(flux)
        
        return flux
    
    def process(self, block, sr):
        """Procesa un bloque de audio"""
        if block is None or sr is None or sr <= 0:
            return
        
        x = _mono(block)
        n = len(x)
        if n == 0:
            return
        
        dt = n / float(sr)
        self._t += dt
        self._frame_count += 1
        
        # Parámetros
        win_short = self._get_param("win_short", 0.14)
        win_long = self._get_param("win_long", 1.20)
        drop_db_req = self._get_param("drop_db_req", 12.0)
        void_s = self._get_param("void_s", 1.2)
        flux_max = self._get_param("flux_max", 0.12)
        confirm_s = self._get_param("confirm_s", 1.0)
        smooth = self._get_param("smooth", 0.50)
        
        # 1. ENERGÍA: Drop dB adaptativo
        rms = float(np.sqrt(np.mean(x*x)) + EPS)
        e_inst = float(rms * rms + 1e-12)
        
        # EMA corta y larga
        aS = np.exp(-dt / max(1e-3, win_short))
        aL = np.exp(-dt / max(1e-3, win_long))
        self._eS = (1.0 - aS) * e_inst + aS * self._eS
        self._eL = (1.0 - aL) * e_inst + aL * self._eL
        
        # Baseline adaptativo (~10s) con piso
        baseline_tau = 10.0
        aB = np.exp(-dt / baseline_tau)
        self._baseline_rms = (1.0 - aB) * max(rms, 0.001) + aB * self._baseline_rms
        self._baseline_rms = max(self._baseline_rms, 0.001)  # Piso
        
        # Drop dB
        drop_db = 10.0 * np.log10((self._eL + 1e-18) / (self._eS + 1e-18))
        ok_drop = (drop_db >= drop_db_req)
        
        # 2. SILENCIO RELATIVO
        ok_quiet = (rms <= 0.35 * self._baseline_rms)
        
        # 3. FLUX
        flux = self._compute_flux(x, sr)
        ok_flux = (flux <= flux_max)
        
        # 4. ONSETS / TIEMPO
        has_onset = self._detect_onsets(x, sr, refrac_ms=120.0)
        if has_onset:
            self._last_onset_t = self._t
        
        since_onset = self._t - self._last_onset_t
        ok_time = (since_onset >= void_s)
        
        # SCORE COMBINADO
        # Usar múltiples criterios con lógica OR parcial
        v_drop_quiet = 0.6 * (float(ok_drop) + 0.67 * float(ok_quiet))
        v_time = 0.6 * float(ok_time)
        v_flux = 0.5 * float(ok_flux)
        
        v_raw = float(np.clip(max(v_drop_quiet, v_time, v_flux), 0.0, 1.0))
        
        # CONFIRMACIÓN: acumular tiempo cumpliendo condiciones
        # energy_brake permite que caída de energía inicie acumulación aunque haya voz
        energy_brake = ok_drop and ok_quiet
        all_ok = energy_brake and ok_flux and ok_time
        if all_ok or energy_brake or v_raw > 0.7:
            self._ok_time = min(10.0, self._ok_time + dt)
        else:
            self._ok_time = max(0.0, self._ok_time - 2*dt)
        
        # Agregar factor de confirmación al score
        v_confirm = float(np.clip(self._ok_time / max(0.1, confirm_s), 0.0, 1.0))
        v_raw = float(np.clip(v_raw * 0.6 + v_confirm * 0.4, 0.0, 1.0))
        
        # SUAVIZADO
        tau_ms = 120.0 + (200.0 - 120.0) * (smooth ** 2)
        aV = np.exp(-dt / (tau_ms/1000.0))
        self._vu = (1.0 - aV) * v_raw + aV * self._vu
        v = float(np.clip(self._vu, 0.0, 1.0))
        
        # HISTÉRESIS + HOLD
        self._apply_hysteresis(v, dt)
        
        # UI UPDATE
        self.card.set_value(v)
        self.card.set_led("brake", self._on)
        self.card.set_on(self._on)
        
        # STATUS
        flags = f"{'D' if ok_drop else '-'}{'Q' if ok_quiet else '-'}{'F' if ok_flux else '-'}{'T' if ok_time else '-'}"
        self.card.set_status(
            f"drop={drop_db:.1f}dB rms={rms:.4f} base={self._baseline_rms:.4f} "
            f"flux={flux:.3f} t={since_onset:.2f}s | {flags} ok={self._ok_time:.2f}s v={v:.2f}"
        )
        
        # LOG en cambios de estado (sin spam)
        if self._on != self._last_log_state:
            state_str = "ON" if self._on else "OFF"
            print(
                f"[BRAKE] DAS {state_str} | drop={drop_db:.1f}dB q={ok_quiet} f={ok_flux} t={ok_time} v={v:.2f}"
            )
            self._last_log_state = self._on
    
    def _apply_hysteresis(self, v, dt):
        """Aplica histéresis con hold ON/OFF configurables"""
        hold_on_ms = self._get_param("hold", 550.0)
        hold_off_ms = self._get_param("hold_off", 700.0)
        thr_on = self._get_param("thr_on", 0.60)
        thr_off = self._get_param("thr_off", 0.50)
        
        hold_on_s = hold_on_ms / 1000.0
        hold_off_s = hold_off_ms / 1000.0
        
        if not self._on:
            # OFF -> ON
            if v >= thr_on:
                self._t_on += dt
                self._t_off = 0.0
                if self._t_on >= hold_on_s:
                    self._on = True
            else:
                self._t_on = 0.0
        else:
            # ON -> OFF
            if v <= thr_off:
                self._t_off += dt
                self._t_on = 0.0
                if self._t_off >= hold_off_s:
                    self._on = False
            else:
                self._t_off = 0.0
    
    def get_current_value(self):
        """Retorna el valor VU actual [0..1]"""
        return float(np.clip(self._vu, 0.0, 1.0))
    
    def is_match(self):
        """Retorna True si está en estado ON"""
        return bool(self._on)
    
    def get_status(self):
        """Retorna texto de status"""
        try:
            return self.card.get_status()
        except:
            return f"v={self._vu:.2f} on={self._on}"
    
    def reset(self):
        """Resetea el estado del analizador"""
        self._eS = 0.0
        self._eL = 0.0
        self._baseline_rms = 0.0
        self._last_mag = None
        self._flux_history.clear()
        self._last_onset_t = -1e9
        self._t = 0.0
        self._vu = 0.0
        self._ok_time = 0.0
        self._on = False
        self._t_on = 0.0
        self._t_off = 0.0
        self._frame_count = 0
    
    def debug_dict(self):
        """Retorna dict con info de debug"""
        return {
            "name": self.name,
            "vu": float(np.clip(self._vu, 0.0, 1.0)),
            "on": bool(self._on),
            "ok_time": float(self._ok_time),
            "drop_db": float(10.0 * np.log10((self._eL + 1e-18) / (self._eS + 1e-18))),
            "baseline_rms": float(self._baseline_rms),
            "since_onset": float(self._t - self._last_onset_t),
            "frames_processed": int(self._frame_count)
        }