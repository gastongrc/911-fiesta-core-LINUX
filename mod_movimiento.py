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

    def __init__(self, avolites):
        self.av = avolites

        # Estado principal
        self.current_cue: Optional[int] = None
        self.pin_until: float = 0.0

        # Pausa por BAJADA
        self.paused_by_positions: bool = False
        self.paused_cue: Optional[int] = None

        # Round-robin por energía (PERSISTE)
        self.idx = {"BAJA": 0, "MEDIA": 0, "ALTA": 0}

        # Detección de cambio de estado
        self.last_state_seen: Optional[str] = None
        self._cycle_due: bool = False

        # UNION V1: anti-repetición con puente
        self._cycle_count = {"BAJA": 0, "MEDIA": 0, "ALTA": 0}
        self._rr_len = {"BAJA": 3, "MEDIA": 3, "ALTA": 3}
        self._rr_used = {"BAJA": set(), "MEDIA": set(), "ALTA": set()}
        self._bridge_due = {"BAJA": False, "MEDIA": False, "ALTA": False}

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

    def _sub_for_energy(self, energy: str) -> List[int]:
        """Retorna subgrupo de cues para una energía."""
        return self.SUB.get((energy or "MEDIA").upper(), self.SUB["MEDIA"])

    def _neighbor_energy(self, e: str) -> str:
        """UNION V1: Retorna subgrupo vecino (BAJA↔MEDIA↔ALTA)."""
        e = e.upper()
        if e == "BAJA":
            return "MEDIA"
        elif e == "MEDIA":
            return "ALTA"
        else:
            return "MEDIA"

    def _next_rr(self, energy: str, avoid: Optional[int] = None) -> int:
        """
        Round-robin con UNION V1.
        Registra uso y detecta ciclos completos.
        Tras 2 ciclos, activa puente.

        Args:
            energy: Nivel de energía
            avoid: Cue a evitar (current_cue) — si RR lo retorna, avanza una más
        """
        e = (energy or "MEDIA").upper()
        seq = self._sub_for_energy(e)
        i = self.idx[e] % len(seq)
        choice = seq[i]
        self.idx[e] = (i + 1) % len(seq)

        # Skip-same-cue: if RR returned the cue to avoid, advance once more
        if avoid is not None and choice == avoid and len(seq) > 1:
            i2 = self.idx[e] % len(seq)
            choice = seq[i2]
            self.idx[e] = (i2 + 1) % len(seq)

        # Registrar uso
        self._rr_used[e].add(choice)

        # Detectar ciclo completo
        if len(self._rr_used[e]) == self._rr_len[e]:
            self._cycle_count[e] += 1
            self._rr_used[e].clear()

            # Activar puente tras 2 ciclos
            if self._cycle_count[e] >= 2:
                self._bridge_due[e] = True

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
            e = energy or "MEDIA"

            # UNION V1: verificar puente
            if self._bridge_due.get(e, False):
                e_bridge = self._neighbor_energy(e)
                choice = self._next_rr(e_bridge)
                if self._fire_cue(choice):
                    print(f"[MOVIMIENTO] BRIDGE C{choice} (pin {PIN_SECONDS:.0f}s)")
                    self._bridge_due[e] = False
                    self._cycle_count[e] = 0
                    return choice

            # Caso normal
            choice = self._next_rr(e)
            if self._fire_cue(choice):
                print(f"[MOVIMIENTO] ON C{choice} (pin {PIN_SECONDS:.0f}s)")
                return choice
            return None

        # Si rotación pendiente Y PIN expiró → rotar
        if self._cycle_due and not self._pin_active():
            e = energy or "MEDIA"

            # UNION V1: verificar puente (avoid current to guarantee rotation)
            if self._bridge_due.get(e, False):
                e_bridge = self._neighbor_energy(e)
                choice = self._next_rr(e_bridge, avoid=self.current_cue)
                if self._fire_cue(choice):
                    print(f"[MOVIMIENTO] BRIDGE C{choice} (pin {PIN_SECONDS:.0f}s)")
                    self._bridge_due[e] = False
                    self._cycle_count[e] = 0
                    self._cycle_due = False
                    return choice

            # Caso normal (avoid current to guarantee rotation)
            choice = self._next_rr(e, avoid=self.current_cue)
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
            "mode": "STATEFUL",
            "current_cue": self.current_cue,
            "pin_remaining_s": round(max(0.0, self.pin_until - time.time()), 2),
            "pin_seconds": PIN_SECONDS,
            "paused": self.paused_by_positions,
            "paused_cue": self.paused_cue,
            "last_state_seen": self.last_state_seen,
            "cycle_due": self._cycle_due,
            "idx": dict(self.idx),
            "cycle_count": dict(self._cycle_count),
            "bridge_due": dict(self._bridge_due),
            "active_cues": self.get_active_cues(),
        }

    def reset(self, hard: bool = True):
        """
        Reset del módulo.
        hard=True: Reset completo incluyendo RR indices
        hard=False: Conserva RR indices (persistencia)
        """
        self.current_cue = None
        self.pin_until = 0.0
        self.paused_by_positions = False
        self.paused_cue = None
        self.last_state_seen = None
        self._cycle_due = False

        if hard:
            self.idx = {"BAJA": 0, "MEDIA": 0, "ALTA": 0}
            self._cycle_count = {"BAJA": 0, "MEDIA": 0, "ALTA": 0}
            self._rr_used = {"BAJA": set(), "MEDIA": set(), "ALTA": set()}
            self._bridge_due = {"BAJA": False, "MEDIA": False, "ALTA": False}

        print(f"[MOVIMIENTO] Reset ({'hard' if hard else 'soft'})")
