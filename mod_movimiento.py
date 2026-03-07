# mod_movimiento.py — MOVIMIENTO: STATEFUL CANONICAL IMPLEMENTATION
# ===========================================================================
# BIBLIA 911 FIESTA — CANON ABSOLUTO
#
# NATURALEZA:
#   - MOVIMIENTO es STATEFUL
#   - Mantiene 1 cue activo (C28-36) mientras NO esté pausado
#   - Rota SOLO en cambio de estado global (no por energía ni tiempo)
#   - PIN de estabilidad de 30s post-fire
#   - UNION V1: Puente a subgrupo vecino tras 2 ciclos completos
#
# CUES:
#   BAJA  → C28, C29, C30
#   MEDIA → C31, C32, C33
#   ALTA  → C34, C35, C36
#
# COEXISTENCIA:
#   - Coexiste con BASE_GOLPE, ATAQUE, AUX
#   - BAJADA pausa/restaura (no mata)
#   - Nunca mata otras familias
#
# PROHIBICIONES:
#   - NO cambia por energía DENTRO del estado
#   - NO cambia por tiempo
#   - NO usa is_active() para decisiones
#   - NO reassert
# ===========================================================================

import time
import random
from typing import Dict, Any, List, Optional

PIN_SECONDS = 10.0  # Estabilidad post-fire (club mode: 30→10s)


class MovimientoModule:
    """
    MOVIMIENTO: Módulo STATEFUL canónico.

    - Mantiene 1 cue activo (C28-36) salvo pausa por BAJADA
    - Rota SOLO en cambio de estado global
    - PIN 30s bloquea rotación (no bloquea fire inicial ni restore)
    - UNION V1: Puente a subgrupo vecino tras 2 ciclos
    - Fire first, kill same-tick (latencia reducida)
    """

    SUB = {"BAJA": [28, 29, 30], "MEDIA": [31, 32, 33], "ALTA": [34, 35, 36]}
    ALL_CUES = list(range(28, 37))  # C28-C36, all 9 movement cues

    def __init__(self, avolites):
        self.av = avolites

        # Estado principal
        self.current_cue: Optional[int] = None
        self.pin_until: float = 0.0

        # Pausa por BAJADA
        self.paused_by_positions: bool = False
        self.paused_cue: Optional[int] = None

        # Shuffle-bag: use ALL 9 cues before repeating any
        self._bag: List[int] = []
        self._last_n: List[int] = []  # Last N cues played (anti-repeat buffer)
        self._ANTI_REPEAT = 2  # Avoid repeating last 2 cues at bag boundary

        # Detección de cambio de estado
        self.last_state_seen: Optional[str] = None
        self._cycle_due: bool = False

    # =========================================================================
    # API DESDE BAJADA
    # =========================================================================

    def pause_for_positions(self):
        """Pausa por BAJADA: guarda cue, kill, flag."""
        if self.paused_by_positions:
            return

        if self.current_cue:
            self.paused_cue = self.current_cue
            try:
                self.av.kill_cue(self.current_cue)
            except:
                pass
            print(f"[MOVIMIENTO] PAUSE by BAJADA (C{self.current_cue})")

        self.paused_by_positions = True
        self.current_cue = None

    def restore_from_positions(self):
        """Restore post-BAJADA: fire cue guardado, kill otros, respeta PIN."""
        if not self.paused_by_positions:
            return

        c = self.paused_cue
        self.paused_by_positions = False
        self.paused_cue = None

        if c:
            try:
                self.av.fire_cue(c)
                self.current_cue = c

                # Kill inmediato post-fire (mismo tick)
                for d in range(28, 37):
                    if d != c:
                        try:
                            self.av.kill_cue(d)
                        except:
                            pass

                # Solo resetear PIN si ya venció
                if not self._pin_active():
                    self.pin_until = time.time() + PIN_SECONDS
                    print(f"[MOVIMIENTO] RESTORE C{c} (pin {PIN_SECONDS:.0f}s)")
                else:
                    remaining = self.pin_until - time.time()
                    print(f"[MOVIMIENTO] RESTORE C{c} (pin activo, {remaining:.1f}s restantes)")
            except:
                pass

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _shuffle_pick(self, avoid: Optional[int] = None) -> int:
        """
        Shuffle-bag across ALL 9 cues (C28-C36).
        Guarantees all 9 cues used before any repeats.
        Avoids last N cues at bag refill boundary.

        Args:
            avoid: Cue to avoid (current_cue) — skipped if possible
        """
        if not self._bag:
            # Refill bag: all 9 cues, shuffled, avoiding recent cues at start
            new_bag = list(self.ALL_CUES)
            random.shuffle(new_bag)

            # Move any cue from _last_n to end of bag (avoid repeat at boundary)
            if self._last_n:
                front = [c for c in new_bag if c not in self._last_n]
                back = [c for c in new_bag if c in self._last_n]
                new_bag = front + back

            self._bag = new_bag

        # Pick first cue from bag, skip avoid if possible
        choice = self._bag[0]
        if avoid is not None and choice == avoid and len(self._bag) > 1:
            # Swap with next available
            choice = self._bag[1]
            self._bag.pop(1)
        else:
            self._bag.pop(0)

        # Update anti-repeat buffer
        self._last_n.append(choice)
        if len(self._last_n) > self._ANTI_REPEAT:
            self._last_n.pop(0)

        return choice

    def _pin_active(self) -> bool:
        """Verifica si PIN está activo."""
        return time.time() < self.pin_until

    def _fire_cue(self, cue: int) -> bool:
        """
        Fire con kill inmediato post-fire (mismo tick).
        Fire first, kill same-tick — elimina 200ms de latencia.
        """
        if not self.av.fire_cue(cue):
            return False

        self.current_cue = cue
        self.pin_until = time.time() + PIN_SECONDS

        # Kill inmediato post-fire (mismo tick, fire-first respetado)
        for c in range(28, 37):
            if c != cue:
                try:
                    self.av.kill_cue(c)
                except:
                    pass

        return True

    # =========================================================================
    # RUN PRINCIPAL
    # =========================================================================

    def run(self, state: str, energy: str) -> Optional[int]:
        """
        Ciclo principal — STATEFUL.

        - Detecta cambio de estado → marca rotación pendiente
        - Si no hay cue → fire inicial
        - Si rotación pendiente Y PIN expiró → rotar
        - Kills se ejecutan en mismo tick (post-fire)
        """
        state = (state or "").upper()
        energy = (energy or "MEDIA").upper()

        # Si pausado → early return
        if self.paused_by_positions:
            return None

        # Detectar cambio de estado global
        if self.last_state_seen is not None and state != self.last_state_seen:
            self._cycle_due = True
        self.last_state_seen = state

        # Si no hay cue (arranque o post-pausa) → fire inicial
        if self.current_cue is None:
            choice = self._shuffle_pick()
            if self._fire_cue(choice):
                print(f"[MOVIMIENTO] ON C{choice} (pin {PIN_SECONDS:.0f}s)")
                return choice
            return None

        # Si rotación pendiente Y PIN expiró → rotar
        if self._cycle_due and not self._pin_active():
            choice = self._shuffle_pick(avoid=self.current_cue)
            if self._fire_cue(choice):
                print(f"[MOVIMIENTO] ROTATE → C{choice} (pin {PIN_SECONDS:.0f}s)")
                self._cycle_due = False
                return choice

        return self.current_cue

    # =========================================================================
    # API PÚBLICA
    # =========================================================================

    def get_active_cues(self) -> List[int]:
        """Retorna cue actual si existe."""
        if self.current_cue is not None:
            return [self.current_cue]
        return []

    def get_status(self) -> Dict[str, Any]:
        """Telemetría."""
        return {
            "mode": "SHUFFLE_BAG",
            "current_cue": self.current_cue,
            "pin_remaining_s": round(max(0.0, self.pin_until - time.time()), 2),
            "pin_seconds": PIN_SECONDS,
            "paused": self.paused_by_positions,
            "paused_cue": self.paused_cue,
            "last_state_seen": self.last_state_seen,
            "cycle_due": self._cycle_due,
            "bag_remaining": len(self._bag),
            "last_n": list(self._last_n),
            "active_cues": self.get_active_cues(),
        }

    def reset(self, hard: bool = True):
        """
        Reset del módulo.
        hard=True: Reset completo incluyendo shuffle bag
        hard=False: Conserva shuffle bag (persistencia)
        """
        self.current_cue = None
        self.pin_until = 0.0
        self.paused_by_positions = False
        self.paused_cue = None
        self.last_state_seen = None
        self._cycle_due = False

        if hard:
            self._bag = []
            self._last_n = []

        print(f"[MOVIMIENTO] Reset ({'hard' if hard else 'soft'})")
