# analyzers/placeholder.py — BRAKE MODULE HOTFIX FINAL
# Implementa detección de frenado/parada con SNR adaptativo y múltiples evidencias

import numpy as np
import time
from collections import deque

EPS = 1e-9

def _mono(x):
    x = np.asarray(x)
    return x.astype(np.float32, copy=False) if x.ndim == 1 else x.mean(axis=1).astype(np.float32, copy=False)

def _energy_db_mono(x):
    """Energía total en dB (compatible con Energy Cliff)"""
    rms = np.sqrt(np.mean(np.square(x), dtype=np.float64) + EPS)
    return 10.0 * np.log10(rms + EPS)

def _clamp01(v):
    return float(np.clip(v, 0.0, 1.0))

def _lerp(a, b, t):
    return a + (b - a) * _clamp01(t)

class BrakeAnalyzer:
    name = "Brake"

    def __init__(self):
        from module_card import ModuleCard
        self.card = ModuleCard(self.name)

        # Sliders
        self.card.add_slider("enable", "Enable", 0.0, 1.0, 1.0)
        self.card.add_slider("sens", "Sensibilidad", 0.0, 1.0, 0.75)
        self.card.add_slider("hold_on", "Hold ON (ms)", 800.0, 2000.0, 1200.0)
        self.card.add_slider("hold_off", "Hold OFF (ms)", 1500.0, 3000.0, 2400.0)
        self.card.add_slider("min_gap", "Gap mínimo (ms)", 100.0, 1000.0, 300.0)

        # LED
        self.card.add_led("brake", "Brake")

        # Estados
        self._state = "IDLE"  # IDLE, CANDIDATE, ACTIVE, COOLDOWN
        self._active = False
        self._state_timer = 0.0
        self._refractory = 0.0

        # Buffers temporales (4s máx para noise floor)
        self._buf_total_db = deque(maxlen=200)  # ~4s @ 50Hz
        self._buf_mean_db = deque(maxlen=100)   # ~2s @ 50Hz
        self._buf_hiband = deque(maxlen=50)     # ~1s @ 50Hz
        self._buf_deriv = deque(maxlen=100)     # ~2s @ 50Hz

        # Noise floor (mediana móvil)
        self._noise_floor_db = -60.0
        self._init_noise_counter = 0

        # Ventana Hann cache
        self._hann_cache = {}

        # Confirmaciones
        self._conf_drop = 0
        self._conf_hiband = 0
        self._conf_deriv = 0

        # Máximo hiband
        self._hiband_max = -80.0
        self._hiband_sustain_timer = 0.0

        # Audio attachment
        self._audio = None
        self._win_sec = 0.320

        # Telemetría
        self._telem = {}

        self.card.set_status("Listo")

    def attach_audio(self, audio_engine, window_ms: int = 320):
        """Conecta al motor de audio"""
        self._audio = audio_engine
        self._win_sec = max(0.010, float(window_ms) / 1000.0)

    def process(self, block, sr):
        """Procesa bloque de audio"""
        # Pull automático si no hay block
        if block is None and self._audio is not None:
            try:
                block = self._audio.get_recent(self._win_sec, raw=True)
                if not sr or sr <= 0:
                    sr = getattr(self._audio, "samplerate", 0) or 0
            except:
                block = None

        # Sin audio válido
        if block is None or not sr or sr <= 0:
            self._decay_state(0.02)
            return

        # Convertir a mono
        try:
            x = _mono(block)
            n = len(x)
            dt = n / float(sr) if n > 0 else 0.02
        except:
            self._decay_state(0.02)
            return

        # Check enable
        enabled = float(self.card.get_value("enable") or 1.0) >= 0.5
        if not enabled:
            self._reset_state()
            self.card.set_led("brake", False)
            self.card.set_status("Deshabilitado")
            return

        # Sensibilidad
        sens = _clamp01(self.card.get_value("sens") or 0.75)

        # Energía total
        total_db = _energy_db_mono(x)
        self._buf_total_db.append(total_db)
        self._buf_mean_db.append(total_db)

        # Noise floor (mediana móvil 4s)
        if self._init_noise_counter < 100:  # primeros ~2s
            self._noise_floor_db = total_db
            self._init_noise_counter += 1
        else:
            if len(self._buf_total_db) >= 50:
                self._noise_floor_db = float(np.median(list(self._buf_total_db)))

        # SNR
        snr_db = total_db - self._noise_floor_db
        snr_soft_db = 2.0
        snr_hard_db = -6.0

        # Gating SNR
        if snr_db < snr_hard_db:
            # Bloquear evaluación
            self._decay_state(dt)
            self.card.set_status(f"SNR bajo: {snr_db:.1f}dB")
            return

        # Scale para SNR intermedio
        scale = 1.0
        if snr_hard_db <= snr_db < snr_soft_db:
            scale = _clamp01((snr_db - snr_hard_db) / (snr_soft_db - snr_hard_db))

        # Delta dB (caída respecto a media 2s)
        if len(self._buf_mean_db) >= 10:
            mean_db_2s = float(np.mean(list(self._buf_mean_db)))
            delta_db = total_db - mean_db_2s
        else:
            delta_db = 0.0

        # FFT con Hann
        if n not in self._hann_cache:
            self._hann_cache[n] = np.hanning(n)
        windowed = x * self._hann_cache[n]
        fft = np.fft.rfft(windowed)
        mag = np.abs(fft)
        freqs = np.fft.rfftfreq(n, 1.0/sr)

        # Bandas
        low_mask = freqs <= 120
        mid_mask = (freqs >= 300) & (freqs <= 3000)
        high_mask = (freqs >= 6000) & (freqs <= 12000)

        energy_low = np.sum(mag[low_mask]**2) + EPS
        energy_mid = np.sum(mag[mid_mask]**2) + EPS
        energy_high = np.sum(mag[high_mask]**2) + EPS

        db_mid = 10.0 * np.log10(energy_mid)
        db_high = 10.0 * np.log10(energy_high)

        # Hiband drop (respecto a máximo 1s)
        self._buf_hiband.append(db_high)
        if len(self._buf_hiband) >= 10:
            self._hiband_max = max(self._hiband_max * 0.98, float(np.max(list(self._buf_hiband))))
        hiband_drop_db = self._hiband_max - db_high

        # Derivada mid (stop-roll)
        self._buf_deriv.append(db_mid)
        if len(self._buf_deriv) >= 2:
            deriv_mid = float(np.diff(list(self._buf_deriv))[-1])
        else:
            deriv_mid = 0.0

        # MAD de derivada
        if len(self._buf_deriv) >= 10:
            derivs = np.diff(list(self._buf_deriv))
            mad_mid = float(np.median(np.abs(derivs - np.median(derivs))))
        else:
            mad_mid = 0.1

        # Umbrales adaptativos
        delta_db_thresh = _lerp(-4.5, -3.0, sens)
        hiband_drop_db_min = _lerp(8.5, 6.0, sens)
        hiband_sustain_ms = _lerp(220, 140, sens)
        deriv_limit = 1.8 * mad_mid + 0.05

        # Confianzas individuales
        c1 = _clamp01((-delta_db - (delta_db_thresh + 0.5)) / 4.5) * scale
        c2 = _clamp01((hiband_drop_db - (hiband_drop_db_min - 0.5)) / 6.5) * scale
        c3 = _clamp01((-deriv_mid - deriv_limit) / (1.8 * mad_mid + 0.30)) * scale

        # Confianza total (weighted)
        C = 0.45 * c2 + 0.35 * c1 + 0.20 * c3

        # Confirmaciones
        N1 = self._conf_drop
        N2 = self._conf_hiband
        N3 = self._conf_deriv

        if delta_db < delta_db_thresh:
            self._conf_drop = min(self._conf_drop + 1, 2)
        else:
            self._conf_drop = max(self._conf_drop - 1, 0)

        if hiband_drop_db >= hiband_drop_db_min:
            self._hiband_sustain_timer += dt * 1000
            if self._hiband_sustain_timer >= hiband_sustain_ms:
                self._conf_hiband = min(self._conf_hiband + 1, 2)
        else:
            self._hiband_sustain_timer = 0.0
            self._conf_hiband = max(self._conf_hiband - 1, 0)

        if deriv_mid < -deriv_limit:
            self._conf_deriv = min(self._conf_deriv + 1, 1)
        else:
            self._conf_deriv = max(self._conf_deriv - 1, 0)

        N1 = self._conf_drop
        N2 = self._conf_hiband
        N3 = self._conf_deriv

        # Regla de disparo (quórum)
        quorum = (N1 >= 2 and N2 >= 2) or (N2 >= 2 and c2 >= 0.72) or (N1 >= 2 and c1 >= 0.80)
        trigger = quorum and C >= 0.52

        # Máquina de estados
        HOLD_S = _lerp(1.2, 1.6, sens)
        COOLDOWN_S = 2.4
        REFRACTORY_EXTRA = 0.25

        self._state_timer += dt
        self._refractory = max(0.0, self._refractory - dt)

        if self._state == "IDLE":
            if trigger and self._refractory <= 0:
                self._state = "CANDIDATE"
                self._state_timer = 0.0
        elif self._state == "CANDIDATE":
            if not trigger:
                self._state = "IDLE"
                self._state_timer = 0.0
            elif self._state_timer >= 0.1:  # pequeña verificación
                self._state = "ACTIVE"
                self._state_timer = 0.0
                self._active = True
        elif self._state == "ACTIVE":
            if not trigger or self._state_timer >= HOLD_S:
                self._state = "COOLDOWN"
                self._state_timer = 0.0
                self._active = False
                self._refractory = REFRACTORY_EXTRA
        elif self._state == "COOLDOWN":
            if self._state_timer >= COOLDOWN_S:
                self._state = "IDLE"
                self._state_timer = 0.0

        # LED
        self.card.set_led("brake", self._active)

        # Nivel
        mag_val = max(abs(delta_db), hiband_drop_db)
        if mag_val < 7.5:
            level = "soft"
        elif mag_val < 13.5:
            level = "mid"
        else:
            level = "hard"

        # Status
        if self._active:
            hold_rem = max(0.0, HOLD_S - self._state_timer)
            self.card.set_status(f"BRAKE {level} | C={C:.2f} | hold {hold_rem:.1f}s")
        else:
            self.card.set_status(f"Δ={delta_db:.1f} | Hi↓={hiband_drop_db:.1f} | SNR={snr_db:.1f} | C={C:.2f}")

        # Telemetría
        self._telem = {
            "module": "Brake",
            "active": self._active,
            "level": level if self._active else "none",
            "confidence": round(C, 3),
            "snr_db": round(snr_db, 2),
            "delta_db": round(delta_db, 2),
            "delta_db_thresh": round(delta_db_thresh, 2),
            "hiband_drop_db": round(hiband_drop_db, 2),
            "hiband_drop_db_min": round(hiband_drop_db_min, 2),
            "deriv_mid": round(deriv_mid, 3),
            "mad_mid": round(mad_mid, 3),
            "state": self._state,
            "hold_s": HOLD_S,
            "cooldown_s": COOLDOWN_S,
            "hold_remaining": max(0.0, HOLD_S - self._state_timer) if self._state == "ACTIVE" else 0.0,
            "cooldown_remaining": max(0.0, COOLDOWN_S - self._state_timer) if self._state == "COOLDOWN" else 0.0
        }

    def _decay_state(self, dt):
        """Decay cuando no hay audio"""
        self._state_timer += dt
        if self._state == "ACTIVE":
            HOLD_S = 1.4
            if self._state_timer >= HOLD_S:
                self._state = "COOLDOWN"
                self._state_timer = 0.0
                self._active = False
        elif self._state == "COOLDOWN":
            if self._state_timer >= 2.4:
                self._state = "IDLE"
                self._state_timer = 0.0
        else:
            self._state = "IDLE"
            self._active = False

        self.card.set_led("brake", self._active)
        self.card.set_status("Sin audio")

    def _reset_state(self):
        """Reset completo"""
        self._state = "IDLE"
        self._active = False
        self._state_timer = 0.0
        self._refractory = 0.0
        self._conf_drop = 0
        self._conf_hiband = 0
        self._conf_deriv = 0

    def is_active(self):
        """Retorna si el brake está activo"""
        return self._active

    def get_telemetry(self):
        """Retorna telemetría detallada"""
        return self._telem.copy() if self._telem else {}


# Alias para compatibilidad
Placeholder = BrakeAnalyzer