# union_bridge.py — UNION V1: Anti-repetición con puente entre familias
# ===========================================================================
# QUÉ HACE:
#   - Detecta ciclos completos de uso de cues en una familia
#   - Tras 2 ciclos completos, activa puente a familia vecina
#   - El puente fuerza 1 disparo en familia vecina, luego resetea
#
# QUÉ NO HACE:
#   - NO dispara cues (eso es del módulo)
#   - NO decide estados (eso es del StateManager)
#
# CONTRATO:
#   1. Cada módulo crea instancia de UnionBridge con sus energías
#   2. Al seleccionar cue: llamar register_use(energy, cue_id)
#   3. Antes de disparar: verificar is_bridge_due(energy)
#   4. Si hay puente: get_neighbor_energy(energy) y disparar ahí
#   5. Tras puente: llamar clear_bridge(energy)
# ===========================================================================
from typing import Dict, Set, Optional


class UnionBridge:
    """
    UNION V1: Detecta ciclos y activa puente entre familias.

    Parámetros:
        energies: Lista de nombres de energía/familia (ej: ["BAJA", "MEDIA", "ALTA"])
        cycles_for_bridge: Número de ciclos completos antes de activar puente (default 2)
        items_per_cycle: Número de items por ciclo (default 3, asume ternas)
    """

    def __init__(
        self,
        energies: list[str],
        cycles_for_bridge: int = 2,
        items_per_cycle: int = 3,
    ):
        self.energies = [e.upper() for e in energies]
        self.cycles_for_bridge = cycles_for_bridge
        self.items_per_cycle = items_per_cycle

        # Estado por energía
        self._used: Dict[str, Set[int]] = {e: set() for e in self.energies}
        self._cycle_count: Dict[str, int] = {e: 0 for e in self.energies}
        self._bridge_due: Dict[str, bool] = {e: False for e in self.energies}

        # Mapa de vecinos (circular: BAJA↔MEDIA↔ALTA)
        self._neighbor_map = self._build_neighbor_map()

    def _build_neighbor_map(self) -> Dict[str, str]:
        """Construye mapa de vecinos circular."""
        n = len(self.energies)
        if n == 0:
            return {}
        if n == 1:
            return {self.energies[0]: self.energies[0]}

        # Para 3 energías estándar: BAJA→MEDIA, MEDIA→ALTA, ALTA→MEDIA
        if n == 3:
            return {
                self.energies[0]: self.energies[1],  # BAJA→MEDIA
                self.energies[1]: self.energies[2],  # MEDIA→ALTA
                self.energies[2]: self.energies[1],  # ALTA→MEDIA
            }

        # Para otras cantidades: circular
        result = {}
        for i, e in enumerate(self.energies):
            next_idx = (i + 1) % n
            result[e] = self.energies[next_idx]
        return result

    def register_use(self, energy: str, cue_id: int) -> None:
        """
        Registra el uso de un cue. Detecta ciclos completos.

        Args:
            energy: Energía/familia del cue
            cue_id: ID del cue usado
        """
        e = energy.upper()
        if e not in self.energies:
            return

        self._used[e].add(cue_id)

        # Detectar ciclo completo
        if len(self._used[e]) >= self.items_per_cycle:
            self._cycle_count[e] += 1
            self._used[e].clear()

            # Activar puente tras N ciclos
            if self._cycle_count[e] >= self.cycles_for_bridge:
                self._bridge_due[e] = True

    def is_bridge_due(self, energy: str) -> bool:
        """Retorna True si hay puente pendiente para esta energía."""
        return self._bridge_due.get(energy.upper(), False)

    def get_neighbor_energy(self, energy: str) -> str:
        """Retorna la energía vecina para el puente."""
        e = energy.upper()
        return self._neighbor_map.get(e, e)

    def clear_bridge(self, energy: str) -> None:
        """
        Limpia el puente después de ejecutarlo.
        Resetea contadores de la energía original.
        """
        e = energy.upper()
        if e not in self.energies:
            return

        self._bridge_due[e] = False
        self._cycle_count[e] = 0

    def get_status(self) -> Dict[str, any]:
        """Retorna estado para telemetría."""
        return {
            "cycle_count": dict(self._cycle_count),
            "bridge_due": dict(self._bridge_due),
            "used_count": {e: len(s) for e, s in self._used.items()},
            "items_per_cycle": self.items_per_cycle,
            "cycles_for_bridge": self.cycles_for_bridge,
        }

    def reset(self) -> None:
        """Resetea todo el estado."""
        for e in self.energies:
            self._used[e].clear()
            self._cycle_count[e] = 0
            self._bridge_due[e] = False


# Instancia singleton para energías estándar
DEFAULT_ENERGIES = ["BAJA", "MEDIA", "ALTA"]


def create_union_bridge(
    energies: list[str] = None,
    cycles_for_bridge: int = 2,
    items_per_cycle: int = 3,
) -> UnionBridge:
    """
    Factory para crear UnionBridge.

    Args:
        energies: Lista de energías (default: BAJA, MEDIA, ALTA)
        cycles_for_bridge: Ciclos antes de puente (default: 2)
        items_per_cycle: Items por ciclo (default: 3)
    """
    return UnionBridge(
        energies=energies or DEFAULT_ENERGIES,
        cycles_for_bridge=cycles_for_bridge,
        items_per_cycle=items_per_cycle,
    )
