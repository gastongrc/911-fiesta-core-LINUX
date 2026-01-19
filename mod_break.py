# mod_break.py — BRAKE: STATEFUL CANONICAL IMPLEMENTATION
# ===========================================================================
# BIBLIA 911 FIESTA — CANON ABSOLUTO
#
# NATURALEZA:
#   - BRAKE es STATEFUL
#   - Tiene HOLD (2.0s)
#   - Tiene ENTRY / RUN / EXIT
#   - Puede cambiar cue solo si energía cambia Y HOLD expiró
#
# CUES (MAPEO FIJO):
#   BAJA  → C42 (FREEZE)
#   MEDIA → C43 (FREEZE)
#   ALTA  → C44 (RESTORE + dim_off)
#
# PRIORIDAD:
#   - BRAKE mata TODO (snapshot/restore)
#   - BRAKE domina mientras vive
#
# SNAPSHOT:
#   - is_active() SOLO permitido para construir snapshot (EXCEPCIÓN)
#   - Snapshot excluye C41, C42, C43, C44
#
# PROHIBICIONES:
#   - NO reassert
#   - NO polling is_active() para decisiones de fire
#   - NO kill-dual en lógica normal
# ===========================================================================

import time
from typing import Dict, Any, List, Optional

# HOLD duration (canon: 2.0s)
HOLD_DURATION_S = 2.0

# Mapeo fijo energía → cue (CANON - NO MODIFICAR)
ENERGY_TO_CUE = {
    "BAJA": 42,
    "MEDIA": 43,
    "ALTA": 44,
}

CUE_SET = [42, 43, 44]
# Nunca incluir en snapshot: C41 (dimmer), C42-44 (brake), C28-36 (movimiento)
# CANON: BRAKE NO mata MOVIMIENTO — queda vivo pero congelado
SNAPSHOT_EXCLUDE = [41, 42, 43, 44] + list(range(28, 37))  # C28-36 = MOVIMIENTO


class BreakModule:
    """
    BRAKE: Módulo STATEFUL canónico.

    - ENTRY: Snapshot + fire cue + HOLD
    - RUN: Solo cambiar si energía cambió Y HOLD expiró
    - EXIT: Restore snapshot + kill pool + release dimmer
    """

    def __init__(self, avolites, dimmer_ctrl=None, aux_manager=None):
        self.av = avolites
        self.dim = dimmer_ctrl

        # ESTADO PERMITIDO (BIBLIA)
        self.current_cue: Optional[int] = None
        self.current_energy: Optional[str] = None
        self.hold_until: float = 0.0
        self.last_state_seen: Optional[str] = None
        self.freeze_snapshot: Optional[List[int]] = None
        self._dimmer_requested: bool = False

        print("[BRAKE] init (STATEFUL canonical)")

    def run(self, state: str, energy: str) -> Optional[int]:
        """
        Ciclo principal — STATEFUL con HOLD.

        ENTRY: Snapshot + fire + HOLD
        RUN: Solo cambiar si energía cambió Y HOLD expiró
        EXIT: Restore + kill pool + release dimmer
        """
        state = (state or "").upper()
        energy = (energy or "MEDIA").upper()

        # Normalizar energía
        energy = {"LOW": "BAJA", "MEDIUM": "MEDIA", "HIGH": "ALTA"}.get(energy, energy)
        if energy not in ("BAJA", "MEDIA", "ALTA"):
            energy = "MEDIA"

        # =====================================================================
        # DETECCIÓN DE TRANSICIONES
        # =====================================================================
        prev_state = self.last_state_seen
        self.last_state_seen = state

        is_entry = (prev_state != "BRAKE" and state == "BRAKE")
        is_exit = (prev_state == "BRAKE" and state != "BRAKE")

        # =====================================================================
        # EXIT: Restore + kill pool + release dimmer
        # =====================================================================
        if is_exit:
            self._handle_exit()
            return None

        # =====================================================================
        # NO ESTAMOS EN BRAKE: No hacer nada
        # =====================================================================
        if state != "BRAKE":
            return None

        # =====================================================================
        # ENTRY: Snapshot + fire + HOLD
        # =====================================================================
        if is_entry:
            return self._handle_entry(energy)

        # =====================================================================
        # RUN: Dentro de BRAKE (ticks posteriores)
        # =====================================================================

        # Si HOLD activo → NO-OP
        if time.time() < self.hold_until:
            return self.current_cue

        # Si energía NO cambió → NO-OP
        if energy == self.current_energy:
            return self.current_cue

        # Energía cambió Y HOLD expiró → cambiar cue
        return self._handle_energy_change(energy)

    def _handle_entry(self, energy: str) -> Optional[int]:
        """ENTRY: Snapshot + fire cue + HOLD"""
        # Tomar snapshot (is_active PERMITIDO aquí — EXCEPCIÓN)
        self.freeze_snapshot = self._take_snapshot()
        if self.freeze_snapshot:
            print(f"[BRAKE] SNAPSHOT {self.freeze_snapshot}")
            self._kill_snapshot()

        target = ENERGY_TO_CUE.get(energy, 43)
        self.av.fire_cue(target)

        self.current_cue = target
        self.current_energy = energy
        self.hold_until = time.time() + HOLD_DURATION_S

        # C44 = RESTORE → request dim_off
        if target == 44 and self.dim is not None:
            try:
                self.dim.request_dim_off("BREAK_C44")
                self._dimmer_requested = True
            except:
                pass

        print(f"[BRAKE] ENTRY energy={energy} → FIRE C{target}")
        return target

    def _handle_energy_change(self, energy: str) -> Optional[int]:
        """Energy change dentro de BRAKE: fire nuevo, kill anterior"""
        prev_cue = self.current_cue
        prev_energy = self.current_energy
        target = ENERGY_TO_CUE.get(energy, 43)

        # FIRE first (prioridad)
        self.av.fire_cue(target)

        # KILL anterior (solo si es diferente)
        if prev_cue is not None and prev_cue != target:
            try:
                self.av.kill_cue(prev_cue)
            except:
                pass

        # Release dimmer si salimos de C44
        if prev_cue == 44 and target != 44:
            self._release_dimmer()

        # Request dimmer si entramos a C44
        if target == 44 and prev_cue != 44 and self.dim is not None:
            try:
                self.dim.request_dim_off("BREAK_C44")
                self._dimmer_requested = True
            except:
                pass

        self.current_cue = target
        self.current_energy = energy
        self.hold_until = time.time() + HOLD_DURATION_S

        print(f"[BRAKE] ENERGY CHANGE {prev_energy}→{energy} → FIRE C{target}")
        return target

    def _handle_exit(self) -> None:
        """EXIT: Restore snapshot + kill pool + release dimmer"""
        # Restore snapshot
        if self.freeze_snapshot:
            for c in self.freeze_snapshot:
                try:
                    self.av.fire_cue(c)
                except:
                    pass
            print(f"[BRAKE] EXIT → RESTORE {self.freeze_snapshot}")
            self.freeze_snapshot = None

        # Kill pool C42-44
        if self.current_cue is not None:
            print(f"[BRAKE] EXIT → KILL C{self.current_cue}")
        for c in CUE_SET:
            try:
                self.av.kill_cue(c)
            except:
                pass

        # Release dimmer
        self._release_dimmer()

        # Reset estado interno
        self.current_cue = None
        self.current_energy = None
        self.hold_until = 0.0

    def _take_snapshot(self) -> List[int]:
        """
        Snapshot de cues activos.
        EXCEPCIÓN: is_active() permitido SOLO aquí para construir snapshot.
        Excluye C41, C42, C43, C44.
        """
        snapshot = []
        for c in range(1, 51):
            if c in SNAPSHOT_EXCLUDE:
                continue
            try:
                if self.av.is_active(c):
                    snapshot.append(c)
            except:
                pass
        return snapshot

    def _kill_snapshot(self) -> None:
        """Mata todos los cues del snapshot"""
        if not self.freeze_snapshot:
            return
        for c in self.freeze_snapshot:
            try:
                self.av.kill_cue(c)
            except:
                pass

    def _release_dimmer(self) -> None:
        """Libera dim_off si estaba activo por C44"""
        if self._dimmer_requested and self.dim is not None:
            try:
                self.dim.release_dim_off("BREAK_C44")
            except:
                pass
            self._dimmer_requested = False

    def get_active_cues(self) -> List[int]:
        """Retorna cue actual si existe."""
        if self.current_cue is not None:
            return [self.current_cue]
        return []

    def get_status(self) -> Dict[str, Any]:
        """Telemetría."""
        now = time.time()
        hold_remaining = max(0.0, self.hold_until - now)
        return {
            "mode": "STATEFUL",
            "current_cue": self.current_cue,
            "current_energy": self.current_energy,
            "hold_active": now < self.hold_until,
            "hold_remaining_s": round(hold_remaining, 2),
            "hold_duration_s": HOLD_DURATION_S,
            "last_state_seen": self.last_state_seen,
            "freeze_snapshot": self.freeze_snapshot,
            "dimmer_requested": self._dimmer_requested,
            "cue_set": CUE_SET,
            "active_cues": self.get_active_cues(),
        }

    def reset(self) -> None:
        """Reset del módulo."""
        # Restore snapshot si existe
        if self.freeze_snapshot:
            for c in self.freeze_snapshot:
                try:
                    self.av.fire_cue(c)
                except:
                    pass
            self.freeze_snapshot = None

        # Kill pool
        if self.current_cue is not None:
            try:
                self.av.kill_cue(self.current_cue)
            except:
                pass

        # Release dimmer
        self._release_dimmer()

        # Reset estado
        self.current_cue = None
        self.current_energy = None
        self.hold_until = 0.0
        self.last_state_seen = None

        print("[BRAKE] Reset")
