# tempo/auto_clock.py
# AutoClock v10 - Clock autónomo con lock state machine + PLL + interval-gated anti-double
# V10: Interval-gated anti-double hit (dt < 0.55*interval = REJECT when LOCKING/LOCKED)
# V9: Acepta intervalos que son multiplos del intervalo esperado (n*expected for n=2..4)
# V8: Seed/reset/drop logic para estabilidad

import time
import numpy as np
from enum import Enum
from typing import Optional, List

try:
    from scipy.signal import butter, lfilter
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False


class LockState(Enum):
    """Estados del clock para TAP gating."""
    UNLOCKED = "UNLOCKED"   # Juntando evidencia, no enviar TAPs
    LOCKING = "LOCKING"     # Necesita K pulsos consistentes
    LOCKED = "LOCKED"       # Estable, habilitar TAPs a Titan


class AutoClock:
    """
    Clock autónomo que late solo y se corrige con golpes graves reales (BOOM).

    V10 Features (new):
    - Interval-gated anti-double hit: when LOCKING/LOCKED, dt < 0.55*interval = REJECT
    - Better logging: HIT_ACCEPT_1X vs HIT_PLL_ACCEPT

    V9 Features:
    - PLL multiple acceptance: accepts dt ~= n * expected_interval (n=2,3,4)
    - Useful when kick detector misses beats but catches every 2nd/3rd/4th

    V8 Features:
    - TAP tempo manual con freeze de 5 segundos
    - Corrección suave del clock basada en kicks reales
    - Filtro pasa-banda para detección de BOOM (40-120 Hz)
    - Anti-double-hit protection
    - Smoothing configurable
    - Lock state machine (UNLOCKED → LOCKING → LOCKED)
    - TAP gating: solo enviar TAPs cuando LOCKED
    - Seed/reset/drop logic para estabilidad

    Lock States:
    - UNLOCKED: Juntando evidencia (< 3 hits)
    - LOCKING: Tiene hits pero intervalos inconsistentes
    - LOCKED: Intervalos estables, OK para TAP a Titan
    """

    # Constantes para lock state machine
    MIN_HITS_FOR_LOCKING = 3      # Hits mínimos para empezar a evaluar
    MIN_HITS_FOR_LOCKED = 5       # Hits mínimos para LOCKED
    MAX_INTERVAL_VARIANCE = 0.15  # 15% varianza máxima para LOCKED
    LOCK_TIMEOUT_S = 4.0          # Timeout sin hits = volver a UNLOCKED

    # V9: PLL multiple acceptance
    PLL_MULTIPLES = [2, 3, 4]     # Accept intervals that are 2x, 3x, 4x expected
    PLL_TOLERANCE = 0.18          # 18% tolerance for multiple matching

    # V10: Interval-gated anti-double hit
    DOUBLE_HIT_RATIO = 0.55       # dt < 0.55*interval = too fast (double hit)
    ABSOLUTE_MIN_HIT_MS = 120.0   # Safety: absolute minimum regardless of tempo

    def __init__(self, interval_ms: float = 750, correction_period: float = 3.0):
        # Intervalo principal (ms entre beats)
        self.interval_ms = float(interval_ms)
        self.tick_interval = self.interval_ms / 1000.0

        # Corrección cada X segundos
        self.correction_period = correction_period

        # Flags de tiempo
        self.last_tick_ts = time.time()
        self.last_hit_ts = 0.0
        self.last_correction_ts = time.time()

        # TAP tempo state
        self._tap_last = 0.0
        self._manual_bpm = 0.0
        self._manual_ts = 0.0
        self._manual_freeze_s = 5.0  # Congelar autocalibration por 5s tras TAP

        # Historial para calcular promedios
        self.hit_times: List[float] = []

        # Lock state machine (v8)
        self._lock_state = LockState.UNLOCKED
        self._last_lock_change_ts = time.time()
        self._consecutive_good_intervals = 0

        # Parámetros configurables (sliders)
        self.params = {
            "peak_thresh": 0.20,
            "rms_thresh": 0.05,
            "ratio_thresh": 1.6,
            "low_cut": 40,
            "high_cut": 120,
            "min_hit_ms": 140,      # Era 180, ahora 140 (debounce ~143 BPM max)
            "smooth": 0.30,
            "interval_min_ms": 333,  # 180 BPM max
            "interval_max_ms": 1000, # 60 BPM min (más estricto)
        }

        # Filtro inicial
        self.b_bpf = None
        self.a_bpf = None
        self._samplerate = 44100
        self._update_filter(samplerate=44100)

        # Estado de detección
        self._kick_detected = False
        self._last_kick_ts = 0.0

    # ============================================================
    # CONFIG
    # ============================================================

    def set_param(self, name: str, value, samplerate: int = 44100):
        """Actualizar parametros desde sliders"""
        if name in self.params:
            old_value = self.params[name]
            self.params[name] = type(self.params[name])(value)

            # Log param change
            print(f"[AutoClock] PARAM {name}={self.params[name]} (was {old_value})")

            # Si cambia el filtro, se recalcula
            if name in ("low_cut", "high_cut"):
                self._update_filter(samplerate)

    def _update_filter(self, samplerate: int):
        """Recalcula filtro pasa-banda para deteccion de BOOM."""
        if not SCIPY_AVAILABLE:
            return

        self._samplerate = samplerate
        nyq = samplerate / 2.0
        low = max(0.01, self.params["low_cut"] / nyq)
        high = min(0.99, self.params["high_cut"] / nyq)

        if low >= high:
            low = 0.01
            high = 0.99

        try:
            self.b_bpf, self.a_bpf = butter(2, [low, high], btype="band")
        except Exception:
            self.b_bpf = None
            self.a_bpf = None

    # ============================================================
    # TICK - CLOCK INTERNO
    # ============================================================

    def tick(self) -> bool:
        """
        Avanza el clock. Retorna True si hay un tick (beat).
        Llamar desde el loop principal (~60Hz o mas).
        """
        now = time.time()

        # Si hay manual override activo, usar ese BPM
        if self._is_manual_active():
            self.tick_interval = 60.0 / self._manual_bpm
            self.interval_ms = self.tick_interval * 1000.0

        if now - self.last_tick_ts >= self.tick_interval:
            self.last_tick_ts = now
            return True
        return False

    def _is_manual_active(self) -> bool:
        """Verifica si el BPM manual (TAP) esta activo."""
        if self._manual_bpm <= 0:
            return False
        elapsed = time.time() - self._manual_ts
        return elapsed < self._manual_freeze_s

    # ============================================================
    # REGISTRO DE GOLPE (BOOM GRAVE)
    # ============================================================

    # V12: Very large gap threshold for forced reset (8 seconds)
    FORCE_RESET_MS = 8000.0

    def _check_pll_multiple(self, delta_ms: float) -> tuple:
        """
        V9: Check if delta is a multiple of expected interval.

        When LOCKED, we have a stable interval. If the incoming delta
        is approximately 2x, 3x, or 4x that interval, we accept it
        (the detector missed some beats but is still on track).

        Args:
            delta_ms: Time since last hit in milliseconds

        Returns:
            tuple: (is_multiple: bool, n: int, ratio: float)
                   is_multiple=True if delta ~= n * interval_ms
                   n = which multiple (2, 3, or 4), 0 if not a multiple
                   ratio = actual ratio delta/interval
        """
        if self.interval_ms <= 0:
            return (False, 0, 0.0)

        ratio = delta_ms / self.interval_ms

        for n in self.PLL_MULTIPLES:
            expected_ratio = float(n)
            tolerance = self.PLL_TOLERANCE * expected_ratio
            if abs(ratio - expected_ratio) <= tolerance:
                return (True, n, ratio)

        return (False, 0, ratio)

    def register_hit(self, timestamp: float):
        """
        V10: Registra golpe con seed/reset/drop + PLL + interval-gated anti-double.

        - SEED: Primer hit sin checks (establece punto cero)
        - ABSOLUTE_DEBOUNCE: dt < 120ms = always reject (safety)
        - INTERVAL_DOUBLE (when LOCKING/LOCKED): dt < 0.55*interval = reject (double hit)
        - FORCE_RESET: dt > 8s = always reseed (lost track completely)
        - PLL_ACCEPT (when LOCKED): dt ~= n*interval = accept as valid beat
        - DROP (when LOCKED): dt > max and not PLL match = drop hit
        - RESET (when not LOCKED): dt > max_interval = reseed (new sequence)
        - ACCEPT_1X: dt in range = register and update lock state

        Args:
            timestamp: Monotonic timestamp from time.monotonic()
        """
        # SEED: First hit ever - no checks, just seed
        if self.last_hit_ts == 0 or len(self.hit_times) == 0:
            self.last_hit_ts = timestamp
            self.hit_times = [timestamp]
            self._kick_detected = True
            self._last_kick_ts = timestamp
            self._hit_count = getattr(self, '_hit_count', 0) + 1
            print(f"[AutoClock] HIT_SEED t={timestamp:.3f}")
            return

        delta_ms = (timestamp - self.last_hit_ts) * 1000.0

        # V10: ABSOLUTE_DEBOUNCE: Safety minimum regardless of tempo
        if delta_ms < self.ABSOLUTE_MIN_HIT_MS:
            print(f"[AutoClock] HIT_REJECT (absolute<{self.ABSOLUTE_MIN_HIT_MS:.0f}ms) dt={delta_ms:.0f}ms")
            return

        # V10: INTERVAL_DOUBLE: When LOCKING/LOCKED, use interval-gated anti-double
        if self._lock_state in (LockState.LOCKING, LockState.LOCKED):
            min_interval_gated = self.interval_ms * self.DOUBLE_HIT_RATIO
            if delta_ms < min_interval_gated:
                print(f"[AutoClock] HIT_REJECT (double<{self.DOUBLE_HIT_RATIO:.0%}*{self.interval_ms:.0f}={min_interval_gated:.0f}ms) dt={delta_ms:.0f}ms")
                return
        else:
            # UNLOCKED: use legacy min_hit_ms debounce
            if delta_ms < self.params["min_hit_ms"]:
                print(f"[AutoClock] HIT_REJECT (debounce) dt={delta_ms:.0f}ms")
                return

        # FORCE_RESET: Very large gap - always reseed regardless of lock
        if delta_ms > self.FORCE_RESET_MS:
            self.last_hit_ts = timestamp
            self.hit_times = [timestamp]
            self._kick_detected = True
            self._last_kick_ts = timestamp
            self._hit_count = getattr(self, '_hit_count', 0) + 1
            self._lock_state = LockState.UNLOCKED
            print(f"[AutoClock] HIT_RESET (dt>{self.FORCE_RESET_MS:.0f}ms) dt={delta_ms:.0f}ms -> reseed")
            return

        # GAP handling depends on lock state
        if delta_ms > self.params["interval_max_ms"]:
            if self._lock_state == LockState.LOCKED:
                # V9: Check if this is a PLL multiple before dropping
                is_mult, n, ratio = self._check_pll_multiple(delta_ms)
                if is_mult:
                    # PLL_ACCEPT: Gap is a multiple of expected interval
                    self.last_hit_ts = timestamp
                    self.hit_times.append(timestamp)
                    self._kick_detected = True
                    self._last_kick_ts = timestamp
                    self._hit_count = getattr(self, '_hit_count', 0) + 1
                    print(f"[AutoClock] HIT_PLL_ACCEPT n={n}x dt={delta_ms:.0f}ms ratio={ratio:.2f}")
                    if len(self.hit_times) > 10:
                        self.hit_times = self.hit_times[-10:]
                    self._update_lock_state()
                    return
                else:
                    # DROP: When LOCKED and not PLL match, don't corrupt tempo
                    print(f"[AutoClock] HIT_DROP (gap while LOCKED) dt={delta_ms:.0f}ms ratio={ratio:.2f}")
                    # Update last_hit_ts to prevent accumulating gap
                    self.last_hit_ts = timestamp
                    return
            else:
                # RESET: When not LOCKED, treat gap as new sequence
                self.last_hit_ts = timestamp
                self.hit_times = [timestamp]
                self._kick_detected = True
                self._last_kick_ts = timestamp
                self._hit_count = getattr(self, '_hit_count', 0) + 1
                print(f"[AutoClock] HIT_RESET (gap while UNLOCKED) dt={delta_ms:.0f}ms -> reseed")
                return

        # V10: ACCEPT_1X: dt in valid range - register hit as 1x beat
        self.last_hit_ts = timestamp
        self.hit_times.append(timestamp)
        self._kick_detected = True
        self._last_kick_ts = timestamp
        self._hit_count = getattr(self, '_hit_count', 0) + 1

        print(f"[AutoClock] HIT_ACCEPT_1X dt={delta_ms:.0f}ms hits={self._hit_count}")

        # Limitar historial
        if len(self.hit_times) > 10:
            self.hit_times = self.hit_times[-10:]

        # Actualizar lock state machine
        self._update_lock_state()

    def was_kick_detected(self) -> bool:
        """Retorna True si hubo kick desde la última consulta."""
        result = self._kick_detected
        self._kick_detected = False
        return result

    # ============================================================
    # LOCK STATE MACHINE (v8)
    # ============================================================

    def _update_lock_state(self):
        """
        V8.1: Actualiza la máquina de estados basada en historial de hits.
        UNLOCKED → LOCKING → LOCKED
        Uses monotonic time for consistency with register_hit().
        """
        now = time.monotonic()
        old_state = self._lock_state

        # Timeout check: sin hits por mucho tiempo = UNLOCKED
        if self.last_hit_ts > 0 and (now - self.last_hit_ts) > self.LOCK_TIMEOUT_S:
            if self._lock_state != LockState.UNLOCKED:
                self._lock_state = LockState.UNLOCKED
                self._consecutive_good_intervals = 0
                print(f"[AutoClock] UNLOCK (reason=timeout)")
            return

        num_hits = len(self.hit_times)

        # UNLOCKED: muy pocos hits
        if num_hits < self.MIN_HITS_FOR_LOCKING:
            if self._lock_state != LockState.UNLOCKED:
                prev = self._lock_state.value
                self._lock_state = LockState.UNLOCKED
                print(f"[AutoClock] STATE {prev}→UNLOCKED (hits={num_hits})")
            return

        # Calcular varianza de intervalos
        intervals_ms = self._get_valid_intervals_ms()
        if len(intervals_ms) < 2:
            return

        median_interval = np.median(intervals_ms)
        variance = np.std(intervals_ms) / median_interval if median_interval > 0 else 1.0

        # LOCKING → LOCKED si varianza baja y suficientes hits
        if variance <= self.MAX_INTERVAL_VARIANCE and num_hits >= self.MIN_HITS_FOR_LOCKED:
            if self._lock_state != LockState.LOCKED:
                prev = self._lock_state.value
                self._lock_state = LockState.LOCKED
                bpm = 60000.0 / median_interval if median_interval > 0 else 0
                print(f"[AutoClock] STATE {prev}→LOCKED bpm={bpm:.1f}")
        elif num_hits >= self.MIN_HITS_FOR_LOCKING:
            if self._lock_state == LockState.UNLOCKED:
                self._lock_state = LockState.LOCKING
                print(f"[AutoClock] STATE UNLOCKED→LOCKING")
            elif self._lock_state == LockState.LOCKED and variance > self.MAX_INTERVAL_VARIANCE * 1.5:
                # Lost lock - varianza demasiado alta
                self._lock_state = LockState.LOCKING
                print(f"[AutoClock] STATE LOCKED→LOCKING (variance={variance:.1%})")

    def _get_valid_intervals_ms(self) -> List[float]:
        """
        Obtiene intervalos válidos entre hits (en ms).
        V8.1: Aplica filtro MAD para rechazar outliers.
        """
        if len(self.hit_times) < 2:
            return []

        # Primero obtener intervalos en rango BPM válido
        raw_intervals = []
        for i in range(1, len(self.hit_times)):
            delta_ms = (self.hit_times[i] - self.hit_times[i - 1]) * 1000.0
            if self.params["interval_min_ms"] <= delta_ms <= self.params["interval_max_ms"]:
                raw_intervals.append(delta_ms)

        if len(raw_intervals) < 3:
            return raw_intervals

        # V8.1: Filtrar outliers usando MAD (Median Absolute Deviation)
        median = np.median(raw_intervals)
        mad = np.median(np.abs(np.array(raw_intervals) - median))
        if mad < 1e-6:
            return raw_intervals

        # Threshold: 2.5 MAD (más estricto que 3 sigmas)
        threshold = 2.5 * 1.4826 * mad  # 1.4826 convierte MAD a equivalente sigma
        intervals = [x for x in raw_intervals if abs(x - median) <= threshold]

        return intervals if intervals else raw_intervals

    def get_lock_state(self) -> LockState:
        """Retorna el estado actual del lock."""
        # Check timeout
        if time.time() - self.last_hit_ts > self.LOCK_TIMEOUT_S:
            if self._lock_state != LockState.UNLOCKED:
                self._lock_state = LockState.UNLOCKED
        return self._lock_state

    def is_locked(self) -> bool:
        """Retorna True si el clock está LOCKED (estable)."""
        return self.get_lock_state() == LockState.LOCKED

    # ============================================================
    # CORRECCION SUAVE DEL CLOCK
    # ============================================================

    def apply_correction(self):
        """
        V8.1: Aplica correccion suave basada en historial de kicks.
        Llamar periodicamente (~1Hz).
        NO aplica si hay TAP manual activo.
        Usa intervalos filtrados por MAD para robustez.
        """
        now = time.time()

        # No corregir si hay TAP manual activo
        if self._is_manual_active():
            return

        if (now - self.last_correction_ts) < self.correction_period:
            return

        # V8.1: Usar intervalos filtrados por MAD
        intervals = self._get_valid_intervals_ms()

        if len(intervals) < 2:
            return

        # V8.1: Usar mediana en lugar de promedio (más robusto)
        target_interval = float(np.median(intervals))

        # EMA smoothing (exponential moving average)
        s = self.params["smooth"]
        self.interval_ms = (self.interval_ms * (1 - s)) + (target_interval * s)

        # Clamps
        p = self.params
        self.interval_ms = min(
            max(self.interval_ms, p["interval_min_ms"]),
            p["interval_max_ms"]
        )

        self.tick_interval = self.interval_ms / 1000.0

        # Reset historial (mantener últimos 2 para continuidad)
        if len(self.hit_times) > 2:
            self.hit_times = self.hit_times[-2:]
        self.last_correction_ts = now

    # ============================================================
    # TAP - Sincronizacion manual
    # ============================================================

    def tap(self):
        """
        Seteo manual del intervalo usando taps sucesivos.
        Congela autocalibration por 5 segundos.
        """
        now = time.time()

        if self._tap_last > 0:
            delta = (now - self._tap_last) * 1000.0

            if 200 <= delta <= 2000:
                # Mas duro: 60% TAP / 40% clock
                new_int = (self.interval_ms * 0.4) + (delta * 0.6)

                # Limitar
                p = self.params
                new_int = min(
                    max(new_int, p["interval_min_ms"]),
                    p["interval_max_ms"]
                )

                self.interval_ms = new_int
                self.tick_interval = new_int / 1000.0

                # Calcular BPM manual
                self._manual_bpm = 60000.0 / new_int
                self._manual_ts = now

        self._tap_last = now

    def set_manual_bpm(self, bpm: float):
        """
        Setea BPM manual directamente.
        Congela autocalibration por 5 segundos.
        """
        if bpm <= 0:
            self._manual_bpm = 0.0
            return

        self._manual_bpm = float(bpm)
        self._manual_ts = time.time()
        self.interval_ms = 60000.0 / bpm
        self.tick_interval = self.interval_ms / 1000.0

    def get_manual_bpm(self) -> float:
        """Retorna BPM manual si esta activo, 0 si no."""
        if self._is_manual_active():
            return self._manual_bpm
        return 0.0

    def manual_override_active(self) -> bool:
        """Verifica si el override manual esta activo."""
        return self._is_manual_active()

    # ============================================================
    # API
    # ============================================================

    def get_bpm(self) -> float:
        """Retorna BPM actual basado en interval_ms."""
        if self.interval_ms <= 0:
            return 0.0
        return 60000.0 / self.interval_ms

    def get_interval_ms(self) -> float:
        """Retorna intervalo actual en ms."""
        return self.interval_ms

    def get_status(self) -> dict:
        """Retorna estado completo del clock."""
        return {
            "interval_ms": self.interval_ms,
            "bpm": self.get_bpm(),
            "manual_active": self._is_manual_active(),
            "manual_bpm": self._manual_bpm,
            "last_kick_ts": self._last_kick_ts,
            "hits_in_buffer": len(self.hit_times),
            "lock_state": self.get_lock_state().value,
            "is_locked": self.is_locked(),
            "params": self.params.copy(),
        }

    def reset(self):
        """Resetea el clock a valores por defecto."""
        self.interval_ms = 750.0
        self.tick_interval = 0.75
        self.hit_times = []
        self._manual_bpm = 0.0
        self._manual_ts = 0.0
        self._tap_last = 0.0
        self._lock_state = LockState.UNLOCKED
        self._consecutive_good_intervals = 0
        self.last_hit_ts = 0.0
        print("[AutoClock] Reset complete")


__all__ = ['AutoClock', 'LockState']
