# tempo/tap_bridge.py
# Tempo Engine v3 - Bridge para enviar TAPs a Titan/Avolites
# Solo envía TAPs cuando AutoClock está LOCKED
# Restaurado desde rama historica para 911 Fiesta V11

import time
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from avolites_config import AvolitesController
    from .auto_clock import AutoClock


class TapBridge:
    """
    Bridge para enviar TAPs a Titan/Avolites.

    V3 Features:
    - Gate por estado LOCKED del AutoClock
    - Rate limit estricto (250ms mínimo entre TAPs)
    - Logging de eventos (solo en transiciones)

    Responsabilidades:
    - Enviar TAPs reales a Titan cuando clock está LOCKED
    - Respetar rate limits para no saturar la consola
    - Solo envía si hay conexión activa

    Uso:
        bridge = TapBridge(avolites_controller, auto_clock)
        bridge.feed_kick(is_golpe=True)  # Solo envía si LOCKED
    """

    # Configuración v3
    MIN_TAP_INTERVAL_MS = 250  # Mínimo entre TAPs (era 50, ahora 250)
    MAX_TAPS_BURST = 4         # Máximo TAPs en ráfaga
    TAP_TIMEOUT_MS = 500       # Timeout para considerar "ráfaga terminada"

    def __init__(self, avolites: Optional['AvolitesController'] = None,
                 auto_clock: Optional['AutoClock'] = None):
        """
        Inicializa el bridge.

        Args:
            avolites: Instancia de AvolitesController (opcional)
            auto_clock: Instancia de AutoClock para consultar lock state (opcional)
        """
        self._avolites = avolites
        self._auto_clock = auto_clock
        self._last_tap_ts: float = 0.0
        self._tap_count: int = 0
        self._burst_start_ts: float = 0.0
        self._total_taps_sent: int = 0
        self._enabled: bool = True
        self._last_logged_lock_state: str = ""

        print("[TapBridge] v3 Initialized (gated by LOCKED state)")

    def set_avolites(self, avolites: 'AvolitesController'):
        """
        Setea el controlador de Avolites.

        Args:
            avolites: Instancia de AvolitesController
        """
        self._avolites = avolites

    def set_auto_clock(self, auto_clock: 'AutoClock'):
        """
        Setea el AutoClock para consultar lock state.

        Args:
            auto_clock: Instancia de AutoClock
        """
        self._auto_clock = auto_clock
        print("[TapBridge] AutoClock connected for lock state gating")

    def send_taps(self, count: int = 4, bpm: Optional[float] = None) -> int:
        """
        Envía múltiples TAPs a Titan.
        SOLO envía si AutoClock está LOCKED.

        Args:
            count: Número de TAPs a enviar (1-4)
            bpm: BPM opcional para calcular intervalo

        Returns:
            int: Número de TAPs enviados exitosamente
        """
        if not self._enabled:
            return 0

        if not self._is_locked():
            return 0

        if not self._can_send():
            return 0

        count = max(1, min(count, self.MAX_TAPS_BURST))
        sent = 0

        for i in range(count):
            if self._send_single_tap_internal():
                sent += 1

                # Pequeño delay entre TAPs si hay BPM
                if bpm and bpm > 0 and i < count - 1:
                    # Delay basado en BPM (milisegundos)
                    delay_ms = max(self.MIN_TAP_INTERVAL_MS, 60000.0 / bpm / 4)
                    time.sleep(delay_ms / 1000.0)

        return sent

    def send_single_tap(self) -> bool:
        """
        Envía un solo TAP a Titan.
        SOLO envía si AutoClock está LOCKED.

        Returns:
            bool: True si se envió exitosamente
        """
        if not self._enabled:
            return False

        if not self._is_locked():
            return False

        if not self._can_send():
            return False

        return self._send_single_tap_internal()

    def send_bpm(self, bpm: float) -> bool:
        """
        Envía BPM directamente a Titan.
        SOLO envía si AutoClock está LOCKED.

        Usa el endpoint send_bpm de AvolitesController.

        Args:
            bpm: BPM a enviar

        Returns:
            bool: True si se envió exitosamente
        """
        if not self._enabled:
            return False

        if not self._is_locked():
            return False

        if not self._avolites:
            return False

        try:
            if hasattr(self._avolites, 'send_bpm'):
                result = self._avolites.send_bpm(bpm)
                if result:
                    print(f"[TapBridge] BPM {bpm:.1f} enviado a Titan")
                return result
            return False
        except Exception as e:
            print(f"[TapBridge] Error enviando BPM: {e}")
            return False

    def is_connected(self) -> bool:
        """Verifica si hay conexión con Titan."""
        if not self._avolites:
            return False

        try:
            return getattr(self._avolites, 'is_connected', False)
        except Exception:
            return False

    def enable(self):
        """Habilita el bridge."""
        self._enabled = True

    def disable(self):
        """Deshabilita el bridge."""
        self._enabled = False

    def is_enabled(self) -> bool:
        """Verifica si el bridge está habilitado."""
        return self._enabled

    def get_stats(self) -> dict:
        """Retorna estadísticas del bridge."""
        lock_state = "UNKNOWN"
        if self._auto_clock and hasattr(self._auto_clock, 'get_lock_state'):
            lock_state = self._auto_clock.get_lock_state().value

        return {
            "enabled": self._enabled,
            "connected": self.is_connected(),
            "total_taps_sent": self._total_taps_sent,
            "last_tap_ts": self._last_tap_ts,
            "lock_state": lock_state,
            "is_locked": self._is_locked(),
        }

    def feed_kick(self, is_golpe: bool) -> bool:
        """
        V11: Alimenta el bridge con detección de kick desde BaseGolpe.

        NOTE: Titan TAP sending is DISABLED (user request).
        Kicks are fed to AutoClock via main.py:register_hit() instead.
        This method only logs lock state transitions for debugging.

        Args:
            is_golpe: True si BaseGolpe detectó golpe válido (votes >= 3)

        Returns:
            bool: Always False (Titan sending disabled)
        """
        if not is_golpe:
            return False

        # Check lock state for logging only (no Titan sending)
        self._is_locked()

        # V11: Titan sending DISABLED - kicks go to AutoClock directly
        # The clock locking happens via auto_clock.register_hit() in main.py
        return False

    # ============================================================
    # INTERNAL
    # ============================================================

    def _is_locked(self) -> bool:
        """
        Verifica si AutoClock está LOCKED.
        Sin AutoClock = siempre False (fail-safe).
        """
        if not self._auto_clock:
            return False

        try:
            if hasattr(self._auto_clock, 'is_locked'):
                locked = self._auto_clock.is_locked()

                # Log cambio de estado (solo en transiciones)
                current_state = "LOCKED" if locked else "NOT_LOCKED"
                if current_state != self._last_logged_lock_state:
                    if locked:
                        print("[TapBridge] AutoClock LOCKED - TAPs habilitados")
                    self._last_logged_lock_state = current_state

                return locked
            return False
        except Exception:
            return False

    def _can_send(self) -> bool:
        """Verifica si se puede enviar un TAP (rate limit)."""
        if not self._avolites:
            return False

        now = time.time()
        delta_ms = (now - self._last_tap_ts) * 1000.0

        # Rate limit estricto: 250ms mínimo
        if delta_ms < self.MIN_TAP_INTERVAL_MS:
            return False

        return True

    def _send_single_tap_internal(self) -> bool:
        """Envía un TAP sin verificaciones."""
        if not self._avolites:
            return False

        try:
            # Intentar send_tap (agregado en avolites_config.py)
            if hasattr(self._avolites, 'send_tap'):
                result = self._avolites.send_tap()
            elif hasattr(self._avolites, 'tap'):
                result = self._avolites.tap()
            else:
                print("[TapBridge] WARN: No send_tap method in Avolites")
                return False

            if result:
                self._last_tap_ts = time.time()
                self._total_taps_sent += 1
                self._tap_count += 1
                # Log TAP enviado
                bpm = 0.0
                if self._auto_clock and hasattr(self._auto_clock, 'get_bpm'):
                    bpm = self._auto_clock.get_bpm()
                print(f"[TapBridge] TAP #{self._total_taps_sent} sent (BPM={bpm:.1f})")
                return True

            return False

        except Exception as e:
            print(f"[TapBridge] Error enviando TAP: {e}")
            return False


__all__ = ['TapBridge']
