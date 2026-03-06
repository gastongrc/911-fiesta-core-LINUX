# mod_bajada.py — BAJADA: STATEFUL CANONICAL IMPLEMENTATION
# ===========================================================================
# BIBLIA 911 FIESTA — CANON ABSOLUTO
#
# NATURALEZA:
#   - BAJADA es STATEFUL solo durante estado BAJADA
#   - Fuera de BAJADA → NO existe
#   - NO reassert
#   - NO polling is_active()
#
# CUES:
#   Colores   → C10-18 (BAJA: 10,11,12 | MEDIA: 13,14,15 | ALTA: 16,17,18)
#   Posiciones → C19-27 (BAJA: 19,20,21 | MEDIA: 22,23,24 | ALTA: 25,26,27)
#
# INTERACCIÓN CON MOVIMIENTO:
#   - ENTRY: pause_for_positions() (una sola vez)
#   - EXIT: restore_from_positions() (una sola vez)
#   - NUNCA mata C28-36 directamente
#
# DISPARO:
#   - SOLO en ENTRY: 1 posición + 1 color (fair RR)
#   - RUN dentro de BAJADA = NO-OP
#   - EXIT: reset latches (CueEngine mata C10-27)
#
# PROHIBICIONES:
#   - NO reassert
#   - NO is_active() para decisiones
#   - NO kill MOVIMIENTO
#   - NO timers ni histéresis
# ===========================================================================

import json
import os
from typing import Dict, Any, List, Optional


class BajadaModule:
    """
    BAJADA: Módulo STATEFUL canónico.

    - ENTRY: Pausa MOVIMIENTO + fire 1 posición + 1 color
    - RUN: NO-OP (latch)
    - EXIT: Restore MOVIMIENTO + reset latches
    """

    # Rangos canónicos
    COLORES = {"BAJA": [10, 11, 12], "MEDIA": [13, 14, 15], "ALTA": [16, 17, 18]}
    POSICIONES = {"BAJA": [19, 20, 21], "MEDIA": [22, 23, 24], "ALTA": [25, 26, 27]}

    # Fair rotation groups
    COLOR_GROUPS = [[10, 11, 12], [13, 14, 15], [16, 17, 18]]
    COLOR_BASE_ORDER = [2, 1, 0]  # Prioridad: G3 > G2 > G1
    _COL_STORE = "bajada_colors_rr.json"

    POS_GROUPS = [[19, 20, 21], [22, 23, 24], [25, 26, 27]]
    POS_BASE_ORDER = [2, 1, 0]  # Prioridad: P3 > P2 > P1
    _POS_STORE = "bajada_positions_rr.json"

    def __init__(self, avolites):
        self.av = avolites
        self.movement = None

        # Estado canónico
        self.in_bajada: bool = False
        self.latched_pos: Optional[int] = None
        self.latched_col: Optional[int] = None
        self.last_state_seen: Optional[str] = None

        # Fair RR (persistente)
        self._load_color_usage()
        self._load_pos_usage()

        print("[BAJADA] init (STATEFUL canonical)")

    def set_movement_controller(self, movement_module):
        """Conecta referencia a MOVIMIENTO."""
        self.movement = movement_module

    # =========================================================================
    # FAIR ROTATION — COLORES (persistente en JSON)
    # =========================================================================

    def _load_color_usage(self):
        """Carga usage de colores desde JSON."""
        self._color_usage = {c: 0 for g in self.COLOR_GROUPS for c in g}
        self._last_col_used = None
        try:
            if os.path.exists(self._COL_STORE):
                with open(self._COL_STORE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    usage = data.get("usage", {})
                    for k, v in usage.items():
                        k = int(k)
                        if k in self._color_usage:
                            self._color_usage[k] = int(v)
                    self._last_col_used = data.get("last", None)
        except Exception:
            pass

    def _save_color_usage(self):
        """Guarda usage de colores a JSON."""
        try:
            with open(self._COL_STORE, "w", encoding="utf-8") as f:
                json.dump({"usage": self._color_usage, "last": self._last_col_used}, f, indent=2)
        except Exception:
            pass

    def _choose_color_fair(self) -> Optional[int]:
        """Elige color por fair rotation."""
        cycles = [min(self._color_usage[c] for c in g) for g in self.COLOR_GROUPS]
        order = sorted(range(3), key=lambda gi: (cycles[gi], self.COLOR_BASE_ORDER.index(gi)))
        group = self.COLOR_GROUPS[order[0]]

        mins = [(c, self._color_usage[c]) for c in group]
        mins.sort(key=lambda t: t[1])
        candidates = [c for c, u in mins if u == mins[0][1]]

        # Anti-repetition: always skip last used color if alternatives exist
        if self._last_col_used in candidates and len(candidates) > 1:
            candidates = [c for c in candidates if c != self._last_col_used]

        chosen = candidates[0]
        self._color_usage[chosen] += 1
        self._last_col_used = chosen
        self._save_color_usage()
        return chosen

    # =========================================================================
    # FAIR ROTATION — POSICIONES (persistente en JSON)
    # =========================================================================

    def _load_pos_usage(self):
        """Carga usage de posiciones desde JSON."""
        self._pos_usage = {c: 0 for g in self.POS_GROUPS for c in g}
        self._last_pos_used = None
        try:
            if os.path.exists(self._POS_STORE):
                with open(self._POS_STORE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    usage = data.get("usage", {})
                    for k, v in usage.items():
                        k = int(k)
                        if k in self._pos_usage:
                            self._pos_usage[k] = int(v)
                    self._last_pos_used = data.get("last", None)
        except Exception:
            pass

    def _save_pos_usage(self):
        """Guarda usage de posiciones a JSON."""
        try:
            with open(self._POS_STORE, "w", encoding="utf-8") as f:
                json.dump({"usage": self._pos_usage, "last": self._last_pos_used}, f, indent=2)
        except Exception:
            pass

    def _choose_pos_fair(self) -> Optional[int]:
        """Elige posición por fair rotation."""
        cycles = [min(self._pos_usage[c] for c in g) for g in self.POS_GROUPS]
        order = sorted(range(3), key=lambda gi: (cycles[gi], self.POS_BASE_ORDER.index(gi)))
        group = self.POS_GROUPS[order[0]]

        mins = [(c, self._pos_usage[c]) for c in group]
        mins.sort(key=lambda t: t[1])
        candidates = [c for c, u in mins if u == mins[0][1]]

        # Anti-repetition: always skip last used position if alternatives exist
        if self._last_pos_used in candidates and len(candidates) > 1:
            candidates = [c for c in candidates if c != self._last_pos_used]

        chosen = candidates[0]
        self._pos_usage[chosen] += 1
        self._last_pos_used = chosen
        self._save_pos_usage()
        return chosen

    # =========================================================================
    # RUN PRINCIPAL
    # =========================================================================

    def run(self, state: str, energy: str) -> Optional[int]:
        """
        Ciclo principal — STATEFUL.

        ENTRY: Pausa MOVIMIENTO + fire pos + fire col
        RUN: NO-OP
        EXIT: Restore MOVIMIENTO + reset latches
        """
        state = (state or "").upper()

        # =====================================================================
        # DETECCIÓN DE TRANSICIONES
        # =====================================================================
        prev_state = self.last_state_seen
        self.last_state_seen = state

        is_entry = (prev_state != "BAJADA" and state == "BAJADA")
        is_exit = (prev_state == "BAJADA" and state != "BAJADA")

        # =====================================================================
        # EXIT: Restore MOVIMIENTO + reset latches
        # =====================================================================
        if is_exit:
            # Restaurar MOVIMIENTO (una sola vez)
            if self.movement is not None:
                try:
                    self.movement.restore_from_positions()
                except Exception:
                    pass

            # Reset latches
            self.latched_pos = None
            self.latched_col = None
            self.in_bajada = False

            print("[BAJADA] EXIT → restore MOVIMIENTO")
            return None

        # =====================================================================
        # NO ESTAMOS EN BAJADA: No hacer nada
        # =====================================================================
        if state != "BAJADA":
            return None

        # =====================================================================
        # ENTRY: Pausa MOVIMIENTO + fire cues
        # =====================================================================
        if is_entry:
            # Pausar MOVIMIENTO (una sola vez)
            if self.movement is not None:
                try:
                    self.movement.pause_for_positions()
                except Exception:
                    pass

            # Elegir cues por fair rotation
            pos = self._choose_pos_fair()
            col = self._choose_color_fair()

            # FIRE posición
            if pos is not None:
                self.av.fire_cue(pos)
                self.latched_pos = pos
                print(f"[BAJADA] ENTRY → POS C{pos}")

            # FIRE color
            if col is not None:
                self.av.fire_cue(col)
                self.latched_col = col
                print(f"[BAJADA] ENTRY → COL C{col}")

            self.in_bajada = True
            return self.latched_pos or self.latched_col

        # =====================================================================
        # RUN: Dentro de BAJADA = NO-OP (latch)
        # =====================================================================
        return self.latched_pos or self.latched_col

    # =========================================================================
    # API PÚBLICA
    # =========================================================================

    def get_active_cues(self) -> List[int]:
        """Retorna cues latcheados si existe."""
        active = []
        if self.latched_pos is not None:
            active.append(self.latched_pos)
        if self.latched_col is not None:
            active.append(self.latched_col)
        return active

    def get_status(self) -> Dict[str, Any]:
        """Telemetría."""
        return {
            "mode": "STATEFUL",
            "in_bajada": self.in_bajada,
            "latched_pos": self.latched_pos,
            "latched_col": self.latched_col,
            "last_state_seen": self.last_state_seen,
            "color_usage": dict(self._color_usage),
            "pos_usage": dict(self._pos_usage),
            "active_cues": self.get_active_cues(),
        }

    def reset(self) -> None:
        """Reset del módulo."""
        # Restaurar MOVIMIENTO si estaba pausado
        if self.in_bajada and self.movement is not None:
            try:
                self.movement.restore_from_positions()
            except Exception:
                pass

        self.in_bajada = False
        self.latched_pos = None
        self.latched_col = None
        self.last_state_seen = None

        print("[BAJADA] Reset")
