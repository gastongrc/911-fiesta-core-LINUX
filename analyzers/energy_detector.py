import numpy as np
import time
from collections import deque

class EnergyDetector:
    # Constantes públicas (compatibles con tu código)
    ENERGY_LOW = 0
    ENERGY_MEDIUM = 1
    ENERGY_HIGH = 2
    ENERGY_NAMES = ["BAJA", "MEDIA", "ALTA"]

    def __init__(
        self,
        card=None,
        smoothing_factor=0.3,        # EMA del RMS -> score
        hysteresis=0.05,             # margen anti-flap (0.03–0.08 sugerido)
        min_dwell_s=0.50,            # tiempo mínimo en cada nivel
        calib_seconds=8.0,           # ventana de auto-calibración inicial
        use_auto_calibration=True,   # activa p33/p66
        percentile_low=33.0,
        percentile_high=66.0,
        # AGC / normalización
        agc_enable=True,
        agc_window=3.0,              # seg para estimar P95 (depende de hop del engine)
        agc_max_gain=6.0,            # límite de ganancia automática (x6)
        # Guardas de umbrales
        t_floor=0.15,                # piso mínimo para t1
        t_ceil=0.85,                 # techo máximo para t2
        t_min_gap=0.15,              # separación mínima t2 - t1
        # Otros
        debug=True
    ):
        self.card = card
        self.name = "EnergyDetector"
        self.debug = debug

        # Estado de energía actual
        self.current_energy = self.ENERGY_LOW
        self.energy_score = 0.0

        # Historiales
        # Nota: energy_history es post-EMA + post-AGC; rms_history es pre-AGC (debug)
        self.energy_history = deque(maxlen=2048)
        self.rms_history = deque(maxlen=4096)

        # Parámetros de proceso
        self.smoothing_factor = float(np.clip(smoothing_factor, 0.01, 0.99))
        self.hysteresis = float(hysteresis)
        self.min_dwell_s = float(min_dwell_s)

        # Auto-calibración
        self.use_auto_calibration = bool(use_auto_calibration)
        self.percentile_low = float(percentile_low)
        self.percentile_high = float(percentile_high)
        self.calib_seconds = float(calib_seconds)
        self._calib_start_ts = None
        self._calib_done = False

        # Umbrales (iniciales; se ajustan si hay auto-calibración)
        self.low_threshold = 0.33
        self.high_threshold = 0.66

        # Guardas de umbrales
        self.t_floor = float(t_floor)
        self.t_ceil  = float(t_ceil)
        self.t_min_gap = float(t_min_gap)

        # AGC (auto-gain control) para normalizar score a [0..1]
        self.agc_enable = bool(agc_enable)
        self.agc_window = float(agc_window)
        self.agc_max_gain = float(max(1.0, agc_max_gain))
        self._agc_buf = deque(maxlen=4096)  # almacena RMS crudo reciente
        self._agc_last_ts = 0.0

        # Control de cambios
        self._last_change_ts = 0.0
        self._logged_non_finite = False  # evita spameo de warning

        print(f"[{self.name}] Inicializado | AutoCalib={'ON' if self.use_auto_calibration else 'OFF'} "
              f"(t≈{self.calib_seconds:.0f}s) | "
              f"Umbrales iniciales: Low={self.low_threshold:.2f} High={self.high_threshold:.2f} | "
              f"h={self.hysteresis:.03f} dwell={self.min_dwell_s:.2f}s | "
              f"AGC={'ON' if self.agc_enable else 'OFF'} max_gain={self.agc_max_gain:.1f}x")

    # ---------------- Config en caliente (opcionales) ----------------
    def set_thresholds(self, low: float, high: float):
        """Fija umbrales manualmente y apaga auto-calibración."""
        low = float(low); high = float(high)
        if low >= high:
            raise ValueError("low < high requerido")
        low, high = self._guard_thresholds(low, high)
        self.low_threshold = low
        self.high_threshold = high
        self.use_auto_calibration = False
        self._calib_done = True
        if self.debug:
            print(f"[{self.name}] Umbrales manuales: Low={low:.3f} High={high:.3f} (auto-calibración OFF)")

    def set_hysteresis(self, h: float):
        self.hysteresis = float(np.clip(h, 0.0, 0.5))
        if self.debug:
            print(f"[{self.name}] Histeresis={self.hysteresis:.03f}")

    def set_min_dwell(self, dwell_s: float):
        self.min_dwell_s = float(max(0.0, dwell_s))
        if self.debug:
            print(f"[{self.name}] Min dwell={self.min_dwell_s:.2f}s")

    def enable_auto_calibration(self, enabled: bool = True):
        self.use_auto_calibration = bool(enabled)
        self._calib_done = not enabled
        if enabled:
            self._calib_start_ts = None
        if self.debug:
            print(f"[{self.name}] Auto-calibración {'ON' if enabled else 'OFF'}")

    # ------------------------- Núcleo proceso ------------------------
    def process(self, audio_block, samplerate):
        """
        Recibe un bloque de audio mono/estéreo (numpy), calcula RMS,
        aplica AGC (opcional) y EMA, auto-calibra por percentiles con guardas,
        y emite nivel de energía con histeresis + dwell mínimo.
        """
        try:
            if audio_block is None:
                return

            audio = np.asarray(audio_block)

            # Si es estéreo (N x 2), colapsar a mono
            if audio.ndim == 2 and audio.shape[1] == 2:
                audio = audio.mean(axis=1)

            if audio.size == 0:
                return

            # Guardas contra NaN/Inf
            if not np.all(np.isfinite(audio)):
                audio = np.nan_to_num(audio, nan=0.0, posinf=0.0, neginf=0.0)
                if self.debug and not self._logged_non_finite:
                    print(f"[{self.name}] Aviso: audio no finito detectado → reemplazado por 0.")
                    self._logged_non_finite = True

            # RMS crudo
            rms_raw = float(np.sqrt(np.mean(audio ** 2)))
            self.rms_history.append(rms_raw)

            # -------- AGC: normaliza el RMS crudo para que score quede 0..1 --------
            if self.agc_enable:
                # buffer de RMS crudo para estimar percentil alto
                self._agc_buf.append(rms_raw)
                # estimar cada ~100 ms
                now = time.time()
                if (now - self._agc_last_ts) >= 0.10 and len(self._agc_buf) >= 16:
                    self._agc_last_ts = now
                    p95 = np.percentile(np.array(self._agc_buf), 95.0)
                    # evita divisiones raras
                    if p95 <= 1e-6:
                        gain = 1.0
                    else:
                        gain = min(self.agc_max_gain, 1.0 / p95)
                    self._agc_gain = gain
                # si aún no hay p95, asumir ganancia 1
                gain = getattr(self, "_agc_gain", 1.0)
                rms_norm = min(1.0, rms_raw * gain)
            else:
                rms_norm = rms_raw

            # EMA para estabilizar
            alpha = self.smoothing_factor
            self.energy_score = alpha * rms_norm + (1.0 - alpha) * self.energy_score
            # score acotado
            self.energy_score = float(np.clip(self.energy_score, 0.0, 1.0))
            self.energy_history.append(self.energy_score)

            now = time.time()

            # -------- Auto-calibración robusta: p33/p66 con guardas --------
            if self.use_auto_calibration and not self._calib_done:
                if self._calib_start_ts is None:
                    self._calib_start_ts = now

                if (now - self._calib_start_ts) >= self.calib_seconds and len(self.energy_history) >= 64:
                    arr = np.array(self.energy_history)
                    pL = float(np.percentile(arr, self.percentile_low))
                    pH = float(np.percentile(arr, self.percentile_high))
                    spread = pH - pL
                    std = float(np.std(arr))
                    mean = float(np.mean(arr))

                    # Guardas: si el audio fue muy “plano” o muy bajo, no confíes
                    good = (
                        spread >= 0.08 and      # separación mínima cruda
                        std   >= 0.04 and       # algo de variabilidad
                        mean  >= 0.03           # no silencio absoluto
                    )
                    if not good:
                        # fallback 33/66
                        pL, pH = 0.33, 0.66

                    pL, pH = self._guard_thresholds(pL, pH)
                    self.low_threshold = pL
                    self.high_threshold = pH
                    self._calib_done = True

                    if self.debug:
                        src = "auto" if good else "fallback"
                        print(f"[{self.name}] Umbrales {src}: "
                              f"t1={self.low_threshold:.3f} t2={self.high_threshold:.3f} "
                              f"(spread={spread:.3f}, std={std:.3f}, mean={mean:.3f})")

            # -------- Clasificación con histeresis + dwell --------
            new_energy = self._classify_with_hysteresis(self.energy_score)

            if new_energy is not None and new_energy != self.current_energy:
                if (now - self._last_change_ts) >= self.min_dwell_s:
                    if self.debug:
                        print(f"[{self.name}] Energía: "
                              f"{self.ENERGY_NAMES[self.current_energy]} → {self.ENERGY_NAMES[new_energy]} "
                              f"(score={self.energy_score:.3f}, "
                              f"t1={self.low_threshold:.3f}, t2={self.high_threshold:.3f})")
                    self.current_energy = new_energy
                    self._last_change_ts = now
                # si no cumple dwell, se ignora el cambio

        except Exception as e:
            print(f"[{self.name}] Error: {e}")

    # ----------------------- helpers internos -----------------------
    def _guard_thresholds(self, t1: float, t2: float):
        """
        Aplica pisos/techos y separación mínima para thresholds.
        Garantiza: t_floor <= t1 < t2 <= t_ceil  y  t2 - t1 >= t_min_gap
        """
        t1 = float(np.clip(t1, self.t_floor, self.t_ceil))
        t2 = float(np.clip(t2, self.t_floor, self.t_ceil))

        if t2 <= t1:
            t2 = min(self.t_ceil, t1 + self.t_min_gap)

        if (t2 - t1) < self.t_min_gap:
            mid = 0.5 * (t1 + t2)
            half = 0.5 * self.t_min_gap
            t1 = max(self.t_floor, mid - half)
            t2 = min(self.t_ceil,  mid + half)

        return t1, t2

    def _classify_with_hysteresis(self, score: float):
        """
        Devuelve un nivel nuevo si corresponde (respetando histeresis),
        o None si no hay cambio.
        """
        lo = self.low_threshold
        hi = self.high_threshold
        h = self.hysteresis

        lo_up   = lo + h
        lo_down = lo - h
        hi_up   = hi + h
        hi_down = hi - h

        cur = self.current_energy

        if cur == self.ENERGY_LOW:
            if score >= lo_up:
                return self.ENERGY_MEDIUM
            return None

        if cur == self.ENERGY_MEDIUM:
            if score < lo_down:
                return self.ENERGY_LOW
            if score >= hi_up:
                return self.ENERGY_HIGH
            return None

        if cur == self.ENERGY_HIGH:
            if score < hi_down:
                return self.ENERGY_MEDIUM
            return None

        return None

    # ----------------------- Getters de estado -----------------------
    def get_energy_level(self):
        return self.current_energy

    def get_energy_name(self):
        return self.ENERGY_NAMES[self.current_energy]

    def get_energy_score(self):
        return self.energy_score

    def get_debug_info(self):
        return {
            'energy_level': self.current_energy,
            'energy_name': self.get_energy_name(),
            'energy_score': float(self.energy_score),
            'low_threshold': float(self.low_threshold),
            'high_threshold': float(self.high_threshold),
            'hysteresis': float(self.hysteresis),
            'min_dwell_s': float(self.min_dwell_s),
            'auto_calibrated': bool(self._calib_done),
            'agc': getattr(self, "_agc_gain", 1.0) if self.agc_enable else 1.0,
        }

    # ----------------------- Control de calib ------------------------
    def reset_calibration(self):
        self._calib_start_ts = None
        self._calib_done = False
        self.energy_history.clear()
        self.rms_history.clear()
        self._agc_buf.clear()
        self.energy_score = 0.0
        if hasattr(self, "_agc_gain"):
            delattr(self, "_agc_gain")
        if self.debug:
            print(f"[{self.name}] Calibración reiniciada "
                  f"(auto={'ON' if self.use_auto_calibration else 'OFF'})")
