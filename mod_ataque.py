# mod_ataque.py — ATAQUE: STATEFUL CANONICAL IMPLEMENTATION
# ===========================================================================
# BIBLIA 911 FIESTA — CANON ABSOLUTO
#
# NATURALEZA:
#   - ATAQUE es STATEFUL
#   - Tiene HOLD (2.0s)
#   - Tiene ENTRY / RUN / EXIT
#   - Puede cambiar cue solo si energía cambia Y HOLD expiró
#
# CUES (MAPEO FIJO):
#   BAJA  → C37
#   MEDIA → C38
#   ALTA  → C39
#
# PRIORIDAD:
#   - ATAQUE mata BASE_GOLPE (CueEngine lo hace via off_now_for_state)
#   - ATAQUE NO mata: MOVIMIENTO, AUX, CONTROL_DIMMER
#   - BRAKE siempre puede matar ATAQUE
#
# PROHIBICIONES:
#   - NO reassert
#   - NO polling is_active() para decisiones
#   - NO matar pools completos
#   - NO tocar otras familias
# ===========================================================================

import time
from typing import Dict, Any, List, Optional

# HOLD duration (canon: 2.0s)
HOLD_DURATION_S = 2.0

# Mapeo fijo energía → cue (CANON - NO MODIFICAR)
ENERGY_TO_CUE = {
    "BAJA": 37,
    "MEDIA": 38,
    "ALTA": 39,
}

CUE_SET = [37, 38, 39]


class AtaqueModule:
    """
    ATAQUE: Módulo STATEFUL canónico.

    - ENTRY: Fire cue por energía, activar HOLD
    - RUN: Solo cambiar si energía cambió Y HOLD expiró
    - EXIT: Kill cue actual, reset estado
    """

    def __init__(self, avolites):
        self.av = avolites

        # ESTADO PERMITIDO (SOLO ESTOS 4 - BIBLIA)
        self.current_cue: Optional[int] = None
        self.current_energy: Optional[str] = None
        self.hold_until: float = 0.0
        self.last_state_seen: Optional[str] = None

    def run(self, state: str, energy: str) -> Optional[int]:
        """
        Ciclo principal — STATEFUL con HOLD.

        ENTRY: Fire + HOLD
        RUN: Solo cambiar si energía cambió Y HOLD expiró
        EXIT: Kill current + reset
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

        is_entry = (prev_state != "ATAQUE" and state == "ATAQUE")
        is_exit = (prev_state == "ATAQUE" and state != "ATAQUE")

        # =====================================================================
        # EXIT: Kill cue actual y reset
        # =====================================================================
        if is_exit:
            if self.current_cue is not None:
                self.av.kill_cue(self.current_cue)
                print(f"[ATAQUE] EXIT → KILL C{self.current_cue}")

            # Reset estado interno
            self.current_cue = None
            self.current_energy = None
            self.hold_until = 0.0
            return None

        # =====================================================================
        # NO ESTAMOS EN ATAQUE: No hacer nada
        # =====================================================================
        if state != "ATAQUE":
            return None

        # =====================================================================
        # ENTRY: Fire cue por energía + activar HOLD
        # =====================================================================
        if is_entry:
            target = ENERGY_TO_CUE.get(energy, 38)
            self.av.fire_cue(target)

            self.current_cue = target
            self.current_energy = energy
            self.hold_until = time.time() + HOLD_DURATION_S

            print(f"[ATAQUE] ENTRY energy={energy} → FIRE C{target}")
            return target

        # =====================================================================
        # RUN: Dentro de ATAQUE (ticks posteriores)
        # =====================================================================

        # Si HOLD activo → NO hacer nada
        now = time.time()
        if now < self.hold_until:
            return self.current_cue

        # Si energía NO cambió → NO hacer nada
        if energy == self.current_energy:
            return self.current_cue

        # =====================================================================
        # ENERGY CHANGE: energía cambió Y HOLD expiró → cambiar cue
        # =====================================================================
        prev_cue = self.current_cue
        prev_energy = self.current_energy
        target = ENERGY_TO_CUE.get(energy, 38)

        # FIRE first (prioridad)
        self.av.fire_cue(target)

        # KILL diferido del anterior (solo si es diferente)
        if prev_cue is not None and prev_cue != target:
            self.av.kill_cue(prev_cue)

        # Actualizar estado
        self.current_cue = target
        self.current_energy = energy
        self.hold_until = time.time() + HOLD_DURATION_S

        print(f"[ATAQUE] ENERGY CHANGE {prev_energy}→{energy} → FIRE C{target}")
        return target

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
            "cue_set": CUE_SET,
            "active_cues": self.get_active_cues(),
        }

    def reset(self) -> None:
        """Reset del módulo."""
        if self.current_cue is not None:
            try:
                self.av.kill_cue(self.current_cue)
            except:
                pass

        self.current_cue = None
        self.current_energy = None
        self.hold_until = 0.0
        self.last_state_seen = None
        print("[ATAQUE] Reset")
