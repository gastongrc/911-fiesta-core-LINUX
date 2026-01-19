# core/cues/family_manager.py
"""
FamilyManager v6.5 - Gestión ON/OFF de familias de cues con pipeline CueEngine

Semántica:
- Una sola cue activa por familia a la vez (exclusividad)
- Al cambiar estado: kill cues previos, fire nuevo
- Al deshabilitar familia: kill todos (todo OFF)
- Edge-trigger: solo actúa en transiciones

PIPELINE UNIFICADO (v6.5):
- Si cue_engine está conectado, usa CueEngine.fire() para visibilidad en CueMonitor
- Fallback a avolites.fire_cue() si no hay cue_engine

USO:
    fm = FamilyManager(avolites)
    fm.set_cue_engine(cue_engine)  # Opcional: para pipeline unificado
    fm.activate_state("CLIMA", "clima_2")  # Kill C60,C62,C63, Fire C61
    fm.deactivate_family("CLIMA")          # Kill C60-C63
"""

from typing import Optional, Dict, Set, Any, TYPE_CHECKING
from .cue_map import (
    FAMILY_CUE_RANGES_EXTENDED,
    FAMILY_STATE_CUE_MAP,
    ALL_FAMILIES,
    get_cue_for_state,
    get_family_cues,
)

if TYPE_CHECKING:
    from cue_engine import CueEngine


class FamilyManager:
    """
    Gestiona activación/desactivación de cues por familia.

    Garantiza:
    - Un solo cue activo por familia
    - Kill limpio al cambiar estado
    - No spam (edge-trigger)
    - Pipeline unificado via CueEngine (si conectado)
    """

    def __init__(self, avolites_controller, cue_engine: Optional["CueEngine"] = None):
        """
        Inicializa el FamilyManager.

        Args:
            avolites_controller: Controlador Avolites con fire_cue/kill_cue
            cue_engine: CueEngine para pipeline unificado (opcional)
        """
        self._av = avolites_controller
        self._cue_engine: Optional["CueEngine"] = cue_engine

        # Estado actual por familia: familia → cue_id activo (None = todo OFF)
        self._active_cue: Dict[str, Optional[int]] = {f: None for f in ALL_FAMILIES}

        # Familias deshabilitadas (gating)
        self._disabled_families: Set[str] = set()

        pipeline_mode = "CueEngine" if cue_engine else "Avolites directo"
        print(f"[FamilyManager] v6.5 Inicializado - familias C60-C82, pipeline: {pipeline_mode}")

    def set_cue_engine(self, cue_engine: "CueEngine") -> None:
        """
        Conecta el CueEngine para pipeline unificado.
        V9.1 FIX: También registra FamilyManager en CueEngine para exposición de cues activos.

        Args:
            cue_engine: CueEngine para fire/kill centralizados
        """
        self._cue_engine = cue_engine

        # V9.1 FIX: Registrar FamilyManager en CueEngine para que CueMonitor vea cues activos
        if hasattr(cue_engine, 'set_family_manager'):
            cue_engine.set_family_manager(self)

        print("[FamilyManager] CueEngine conectado - pipeline unificado activado")

    def activate_state(self, family: str, state, force: bool = False, source: str = "") -> bool:
        """
        Activa un estado en una familia (ON/OFF exclusivo).

        1. Mata todos los cues de la familia excepto el nuevo
        2. Dispara el cue del nuevo estado via CueEngine (si conectado) o Avolites

        Args:
            family: Nombre de familia (CLIMA, HAZE, DJ, ARTIST, TRACKING)
            state: Estado a activar (string o int según familia)
            force: Si True, dispara aunque ya esté activo
            source: Origen del disparo (para logs)

        Returns:
            True si se activó correctamente
        """
        family = family.upper()
        src = f" (source={source})" if source else ""

        if family not in ALL_FAMILIES:
            print(f"[FamilyManager] REJECT: unknown family '{family}'{src}")
            return False

        # Si familia está deshabilitada, no hacer nada
        if family in self._disabled_families:
            print(f"[FamilyManager] REJECT: {family} DISABLED (gating){src}")
            return False

        # Obtener cue para el estado
        new_cue = get_cue_for_state(family, state)
        if new_cue is None:
            print(f"[FamilyManager] REJECT: no cue for state '{state}' in {family}{src}")
            return False

        # Edge-trigger: no hacer nada si ya está activo (salvo force)
        current_cue = self._active_cue.get(family)
        if current_cue == new_cue and not force:
            return True  # Ya está activo

        # Verificar controller (CueEngine o Avolites)
        if not self._cue_engine and not self._av:
            print(f"[FamilyManager] REJECT: no controller connected for {family}{src}")
            return False

        # 1. Kill todos los cues de la familia (excepto el nuevo)
        family_cues = get_family_cues(family)
        cues_to_kill = [c for c in family_cues if c != new_cue]

        if cues_to_kill:
            if self._cue_engine:
                self._cue_engine.kill_pool_centralized(cues_to_kill, source=f"family_{family.lower()}")
            elif self._av:
                self._av.kill_pool(cues_to_kill)

        # 2. Fire el nuevo cue via pipeline unificado
        fire_meta = {"family": family, "state": state}
        fire_source = source or f"family_{family.lower()}"

        if self._cue_engine:
            # Pipeline unificado: CueEngine registra evento y dispara
            self._cue_engine.fire(new_cue, source=fire_source, meta=fire_meta)
        elif self._av:
            # Fallback: Avolites directo
            self._av.fire_cue(new_cue)
            print(f"[FamilyManager] *** FIRE C{new_cue} *** {family}:{state}{src}")

        # 3. Actualizar estado interno
        self._active_cue[family] = new_cue

        return True

    def deactivate_family(self, family: str) -> bool:
        """
        Desactiva todos los cues de una familia (todo OFF).

        Args:
            family: Nombre de familia

        Returns:
            True si se desactivó correctamente
        """
        family = family.upper()

        if family not in ALL_FAMILIES:
            return False

        # Kill todos los cues de la familia via pipeline unificado
        family_cues = get_family_cues(family)
        if family_cues:
            if self._cue_engine:
                self._cue_engine.kill_pool_centralized(family_cues, source=f"family_{family.lower()}_deactivate")
            elif self._av:
                self._av.kill_pool(family_cues)

        # Actualizar estado interno
        self._active_cue[family] = None

        print(f"[FamilyManager] {family}: ALL OFF")
        return True

    def disable_family(self, family: str) -> None:
        """
        Marca familia como deshabilitada (gating).
        Desactiva todos los cues de la familia.

        Args:
            family: Nombre de familia
        """
        family = family.upper()
        if family in ALL_FAMILIES:
            self._disabled_families.add(family)
            self.deactivate_family(family)
            print(f"[FamilyManager] {family}: DISABLED (gating)")

    def enable_family(self, family: str) -> None:
        """
        Habilita una familia previamente deshabilitada.

        Args:
            family: Nombre de familia
        """
        family = family.upper()
        self._disabled_families.discard(family)
        print(f"[FamilyManager] {family}: ENABLED")

    def is_family_disabled(self, family: str) -> bool:
        """Verifica si una familia está deshabilitada."""
        return family.upper() in self._disabled_families

    def get_active_cue(self, family: str) -> Optional[int]:
        """
        Obtiene el cue activo de una familia.

        Args:
            family: Nombre de familia

        Returns:
            Cue ID activo o None si todo OFF
        """
        return self._active_cue.get(family.upper())

    def get_all_active_cues(self) -> Dict[str, Optional[int]]:
        """
        Obtiene estado de todas las familias.

        Returns:
            Dict {familia: cue_activo o None}
        """
        return self._active_cue.copy()

    def get_status(self) -> Dict:
        """
        Obtiene estado completo del manager.

        Returns:
            Dict con estado de todas las familias
        """
        return {
            "active_cues": self._active_cue.copy(),
            "disabled_families": list(self._disabled_families),
            "families": ALL_FAMILIES,
        }

    # ==================== MULTI-ZONE SUPPORT (DJ) ====================

    def activate_zone(self, family: str, zone_id: int, source: str = "") -> bool:
        """
        Activa una zona SIN matar otros cues de la familia.
        Usar para familias multi-zona (ej: DJ).

        A diferencia de activate_state(), NO mata otros cues antes de disparar.
        Permite múltiples cues activos simultáneamente en la misma familia.

        Args:
            family: Nombre de familia (ej: DJ)
            zone_id: ID de zona (1-5)
            source: Origen del disparo (para logs)

        Returns:
            True si se disparó correctamente
        """
        family = family.upper()
        src = f" (source={source})" if source else ""

        if family not in ALL_FAMILIES:
            print(f"[FamilyManager] REJECT: unknown family '{family}'{src}")
            return False

        if family in self._disabled_families:
            print(f"[FamilyManager] REJECT: {family} DISABLED (gating){src}")
            return False

        cue_id = get_cue_for_state(family, zone_id)
        if cue_id is None:
            print(f"[FamilyManager] REJECT: no cue for zone {zone_id} in {family}{src}")
            return False

        # Verificar controller
        if not self._cue_engine and not self._av:
            print(f"[FamilyManager] REJECT: no controller connected{src}")
            return False

        # Fire el cue SIN matar otros (multi-zona)
        fire_meta = {"family": family, "zone": zone_id}
        fire_source = source or f"family_{family.lower()}"

        if self._cue_engine:
            self._cue_engine.fire(cue_id, source=fire_source, meta=fire_meta)
        elif self._av:
            self._av.fire_cue(cue_id)

        print(f"[FamilyManager] *** FIRE C{cue_id} *** {family}:{zone_id}{src}")
        return True

    def deactivate_zone(self, family: str, zone_id: int, source: str = "") -> bool:
        """
        Desactiva solo el cue de una zona específica (NO toda la familia).
        Usar para familias multi-zona (ej: DJ).

        Args:
            family: Nombre de familia (ej: DJ)
            zone_id: ID de zona (1-5)
            source: Origen del kill (para logs)

        Returns:
            True si se mató correctamente
        """
        family = family.upper()
        src = f" (source={source})" if source else ""

        if family not in ALL_FAMILIES:
            return False

        cue_id = get_cue_for_state(family, zone_id)
        if cue_id is None:
            print(f"[FamilyManager] REJECT: no cue for zone {zone_id} in {family}{src}")
            return False

        # Kill solo este cue (NO toda la familia)
        if self._cue_engine:
            self._cue_engine.kill_pool_centralized([cue_id], source=f"family_{family.lower()}_zone_off")
        elif self._av:
            self._av.kill_cue(cue_id)

        print(f"[FamilyManager] *** KILL C{cue_id} *** {family}:{zone_id}{src}")
        return True
