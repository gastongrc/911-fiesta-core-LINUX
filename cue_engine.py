# cue_engine.py — Orquestador Modular v6.0 - DETERMINÍSTICO
# ===========================================================================
# LEY ABSOLUTA: Un cue NO cambia a otro cue SALVO:
#   1. Cambio de estado (StageManager via get_state())
#   2. Timer explícito documentado (ver mod_timed_sequence.py)
#   3. Orden directa del motor (off_now_for_family/off_now_for_state)
#
# PROHIBIDO:
#   ❌ Auto-advance implícito
#   ❌ Cycle_next sin timer documentado
#   ❌ Decisiones internas no declaradas
#   ❌ Heurísticas de comportamiento
#
# FLUJO DETERMINÍSTICO:
#   1. Lee estado/energía de StateManager (única fuente de verdad)
#   2. Si cambió estado → off_now_for_state(estado_anterior) (KILL primero)
#   3. Ejecuta módulos en orden estricto (FIRE nuevo estado)
# ===========================================================================

import time
import threading
from typing import Optional, Dict, Any, List, Set

# Módulos nuevos (deben existir en el mismo directorio)
from mod_control_dimmer import ControlDimmerModule
from mod_break import BreakModule
from mod_ataque import AtaqueModule
from mod_basegolpe import BaseGolpeModule
from mod_bajada import BajadaModule
from mod_movimiento import MovimientoModule
from mod_timed_sequence import TimedSequenceModule
from aux_state_manager import AuxStateManager

# Mapeo de conflictos entre familias (para referencia)
CONFLICT_FAMILIES = {
    "movimiento": {"posiciones", "posiciones_fijas"},
    "posiciones": {"movimiento"},
    "posiciones_fijas": {"movimiento"},
}

# ✅ Mapeo de estados a familias para OFF prioritario
STATE_TO_FAMILY = {
    "BAJADA": ["bajada", "posiciones"],
    "BASE_GOLPE": ["base_golpe"],
    "ATAQUE": ["ataque"],
    "BRAKE": ["brake"],
}

# ✅ Rangos de cues por familia para OFF rápido
FAMILY_CUE_RANGES = {
    "bajada": list(range(10, 28)),  # C10-27: Colores + Posiciones
    "posiciones": list(range(19, 28)),  # C19-27: Posiciones
    "base_golpe": list(range(1, 10)) + list(range(51, 60)),  # C1-9, C51-59
    "ataque": [37, 38, 39],  # C37-39
    "brake": [42, 43, 44],  # C42-44
    "movimiento": list(range(28, 37)),  # C28-36
}


class CueEngine:
    """
    Orquestador Modular v6.0 — DETERMINÍSTICO

    QUÉ HACE:
      - Lee estado/energía de StateManager (ÚNICA fuente de verdad)
      - Ejecuta OFF→ON en cambios de estado
      - Orquesta 7 módulos especializados en orden estricto
      - Provee off_now_for_family() para apagado prioritario

    QUÉ NO HACE:
      - NO decide estados (eso es del StateManager)
      - NO hace auto-advance de cues
      - NO interpreta audio/música
      - NO tiene heurísticas de comportamiento

    ORDEN DE EJECUCIÓN:
      1. control_dimmer (C41)
      2. break (C42-44)
      3. ataque (C37-39)
      4. base_golpe (C1-9, C51-59)
      5. bajada (C10-27)
      6. movimiento (C28-36)
      7. timed (C45-50)

    INPUTS: state_manager.get_state(), state_manager.get_energy()
    OUTPUTS: fire_cue(), kill_cue() via avolites_controller
    """

    def __init__(
        self,
        avolites_controller,
        state_manager,
        energy_detector,
        auto_update: bool = True,
        interval: float = 0.05,
    ):
        self.av = avolites_controller
        self.sm = state_manager

        # --- AUX-V2: Tabla de Estado Centralizada (NO controla hardware) ---
        self.aux = AuxStateManager()

        # --- Instancias de módulos ---
        # Pasar aux_manager a módulos que lo soporten
        self.m_control = ControlDimmerModule(self.av, aux_manager=self.aux)
        self.m_break = self._safe_new_break(self.av, self.m_control, self.aux)
        self.m_ataque = self._safe_new_ataque(self.av)
        self.m_bg = self._safe_new_basegolpe(self.av, self.m_control, self.aux)
        self.m_bajada = BajadaModule(self.av)
        self.m_move = MovimientoModule(self.av)
        self.m_timed = TimedSequenceModule(
            self.av, self.sm,
            start_after=20.0, interval=10.0, duration=10.0,
            cues=[45,46,47,48,49,50],
            kill_on_state_change=True,
            persist_index_across_states=True,
            aux_manager=self.aux
        )

        # Enchufe Bajada ↔ Movimiento
        if hasattr(self.m_bajada, "set_movement_controller"):
            try:
                self.m_bajada.set_movement_controller(self.m_move)
            except Exception:
                pass
        elif hasattr(self.m_bajada, "movement"):
            self.m_bajada.movement = self.m_move

        # Estado / estadísticas
        self.last_state: Optional[str] = None
        self.last_energy: Optional[str] = None
        self.stats: Dict[str, int] = {
            "updates": 0, 
            "state_changes": 0, 
            "energy_changes": 0,
            "total_updates": 0,
            "specialist_calls": 0,
            "specialist_errors": 0,
            "brake_interrupts": 0,
            "transport_throttles": 0,
            "cross_kills": 0,
            "atomic_switches": 0,
            "off_now_calls": 0,
            "off_now_latency_sum": 0.0,
        }
        
        # ✅ Tracking de cues activos por familia
        self.active_by_family: Dict[str, Optional[int]] = {
            "base_golpe": None, 
            "bajada": None, 
            "ataque": None, 
            "brake": None,
            "movimiento": None,
            "posiciones": None,
            "posiciones_fijas": None
        }
        
        # Timestamps y métricas
        self.start_time = time.time()
        self.last_update_time = time.time()
        self.last_error = None
        self.last_specialist = "None"

        # Tracking de logs de no-state
        self._last_no_state_log = 0.0

        # ✅ CALENDAR BRIDGE: Estados deshabilitados por calendario
        # Si un estado está en esta lista, el módulo correspondiente NO se ejecuta
        # Valores posibles: "BAJADA", "BASE_GOLPE", "ATAQUE", "BRAKE", "ALL"
        self._disabled_states: Set[str] = set()

        # V9.1 FIX: Referencia a FamilyManager para exponer cues activos de Vision
        self._family_manager = None

        # Loop automático
        self.interval = max(0.05, float(interval))
        self._auto = bool(auto_update)
        self._running = False
        self._auto_update_running = False
        self._thr: Optional[threading.Thread] = None

        print("[CueEngine] v6.0 listo - DETERMINÍSTICO + AUX-V2 (tabla de estado)")
        if self._auto:
            self.start_auto_update()

    @property
    def specialists(self) -> Dict[str, Any]:
        return {
            "aux": self.aux,
            "control_dimmer": self.m_control,
            "break": self.m_break,
            "ataque": self.m_ataque,
            "base_golpe": self.m_bg,
            "bajada": self.m_bajada,
            "movimiento": self.m_move,
            "timed": self.m_timed
        }

    def force_update(self):
        self.update()

    # ====== FIRE CENTRALIZADO (VISION/FAMILY PIPELINE) ======
    def _resolve_family(self, cue_id: int) -> Optional[str]:
        """Resolve which family a cue belongs to (for exclusivity enforcement)."""
        for family, cue_ids in FAMILY_CUE_RANGES.items():
            if cue_id in cue_ids:
                return family
        return None

    def fire(self, cue_id: int, source: str = "", meta: Optional[Dict[str, Any]] = None) -> bool:
        """
        Dispara un cue de forma centralizada (para Vision y FamilyManager).

        Garantiza:
        - KILL-BEFORE-FIRE: mata todos los otros cues de la misma familia antes de disparar
        - Registro en fire_history para CueMonitor
        - Logs determinísticos con source y meta
        - Envío a Avolites via av.fire_cue()

        Args:
            cue_id: ID del cue a disparar (ej: 64 para HAZE LOW)
            source: Origen del disparo (ej: "vision_haze", "family_manager")
            meta: Metadata adicional (ej: {"family": "HAZE", "state": "LOW"})

        Returns:
            bool: True si el disparo fue exitoso
        """
        if not self.av:
            print(f"[CueEngine] FIRE BLOCKED: no controller (C{cue_id}, source={source})")
            return False

        # ===== FAMILY EXCLUSIVITY: kill-before-fire =====
        family = self._resolve_family(cue_id)
        if family:
            siblings = [c for c in FAMILY_CUE_RANGES[family] if c != cue_id and self.av.is_active(c)]
            if siblings:
                self.av.kill_pool(siblings)
                print(f"[CueEngine] EXCLUSIVITY kill {siblings} before fire C{cue_id} (family={family})")

        # Registrar en historial para CueMonitor
        event = {
            "cue_id": cue_id,
            "source": source,
            "meta": meta or {},
            "timestamp": time.time(),
        }

        if not hasattr(self, '_fire_history'):
            self._fire_history: List[Dict[str, Any]] = []

        self._fire_history.append(event)
        # Mantener últimos 100 eventos
        if len(self._fire_history) > 100:
            self._fire_history.pop(0)

        # Log determinístico
        meta_str = ""
        if meta:
            meta_str = f" meta={meta}"
        print(f"[CueEngine] *** FIRE C{cue_id} *** source={source}{meta_str}")

        # Disparar via avolites
        try:
            result = self.av.fire_cue(cue_id)
            return result
        except Exception as e:
            print(f"[CueEngine] FIRE ERROR C{cue_id}: {e}")
            return False

    def kill(self, cue_id: int, source: str = "") -> bool:
        """
        Mata un cue de forma centralizada.

        Args:
            cue_id: ID del cue a matar
            source: Origen del kill

        Returns:
            bool: True si el kill fue exitoso
        """
        if not self.av:
            return False

        print(f"[CueEngine] KILL C{cue_id} source={source}")
        try:
            return self.av.kill_cue(cue_id)
        except Exception as e:
            print(f"[CueEngine] KILL ERROR C{cue_id}: {e}")
            return False

    def kill_pool_centralized(self, cue_ids: List[int], source: str = "") -> bool:
        """
        Mata múltiples cues de forma centralizada.

        Args:
            cue_ids: IDs de cues a matar
            source: Origen del kill

        Returns:
            bool: True si el kill fue exitoso
        """
        if not self.av or not cue_ids:
            return False

        print(f"[CueEngine] KILL_POOL {cue_ids} source={source}")
        try:
            return self.av.kill_pool(cue_ids)
        except Exception as e:
            print(f"[CueEngine] KILL_POOL ERROR {cue_ids}: {e}")
            return False

    def get_fire_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Obtiene el historial reciente de disparos.

        Args:
            limit: Número máximo de eventos a retornar

        Returns:
            Lista de eventos de disparo recientes
        """
        if not hasattr(self, '_fire_history'):
            return []
        return self._fire_history[-limit:]

    # ====== V9.1 FIX: FAMILY MANAGER INTEGRATION ======
    def set_family_manager(self, family_manager) -> None:
        """
        V9.1 FIX: Registra el FamilyManager para exponer cues activos de Vision.
        Permite que CueMonitor vea los cues activos de familias extendidas (DJ, HAZE, etc.)

        Args:
            family_manager: Instancia de FamilyManager
        """
        self._family_manager = family_manager
        print("[CueEngine] FamilyManager registrado para exposición de cues activos")

    def get_extended_family_active_cues(self) -> Set[int]:
        """
        V9.1 FIX: Obtiene los cues activos de familias extendidas (CLIMA, HAZE, DJ, ARTIST, TRACKING).
        Se usa para que CueMonitor muestre correctamente los cues de Vision.

        Returns:
            Set de cue IDs activos de familias extendidas (C60-C82)
        """
        active_cues = set()

        if self._family_manager is not None:
            try:
                # Obtener cues activos de todas las familias extendidas
                all_active = self._family_manager.get_all_active_cues()
                for family, cue_id in all_active.items():
                    if cue_id is not None:
                        active_cues.add(cue_id)
            except Exception as e:
                print(f"[CueEngine] Error obteniendo cues de FamilyManager: {e}")

        return active_cues

    def _safe_new_break(self, av, dim_ctrl, aux_mgr=None):
        try:
            mod = BreakModule(av, dim_ctrl, aux_manager=aux_mgr)
            return mod
        except TypeError:
            try:
                mod = BreakModule(av, dim_ctrl)
            except TypeError:
                mod = BreakModule(av)
                if hasattr(mod, "set_dimmer_controller"):
                    try:
                        mod.set_dimmer_controller(dim_ctrl)
                    except Exception:
                        pass
                elif hasattr(mod, "dimmer_controller"):
                    mod.dimmer_controller = dim_ctrl
            # Intentar setear aux_manager
            if aux_mgr and hasattr(mod, "set_aux_manager"):
                try:
                    mod.set_aux_manager(aux_mgr)
                except Exception:
                    pass
            elif aux_mgr:
                mod.aux_manager = aux_mgr
            return mod

    def _safe_new_basegolpe(self, av, dim_ctrl, aux_mgr=None):
        try:
            mod = BaseGolpeModule(av, dim_ctrl, aux_manager=aux_mgr)
            return mod
        except TypeError:
            try:
                mod = BaseGolpeModule(av, dim_ctrl)
            except TypeError:
                mod = BaseGolpeModule(av)
                if hasattr(mod, "set_dimmer_controller"):
                    try:
                        mod.set_dimmer_controller(dim_ctrl)
                    except Exception:
                        pass
                elif hasattr(mod, "dimmer_controller"):
                    mod.dimmer_controller = dim_ctrl
            # Intentar setear aux_manager
            if aux_mgr and hasattr(mod, "set_aux_manager"):
                try:
                    mod.set_aux_manager(aux_mgr)
                except Exception:
                    pass
            elif aux_mgr:
                mod.aux_manager = aux_mgr
            return mod

    def _safe_new_ataque(self, av):
        try:
            return AtaqueModule(av)
        except TypeError:
            return AtaqueModule()

    def connect_modules_golpe(self, modules_golpe: List) -> None:
        """
        V10: Conecta modules_golpe a BaseGolpeModule para lectura de flags.

        Args:
            modules_golpe: Lista de analizadores de BASE_GOLPE (incluye PulseFinderAnalyzer)
        """
        if self.m_bg is not None and hasattr(self.m_bg, 'set_modules_golpe'):
            self.m_bg.set_modules_golpe(modules_golpe)
            # Inicializar flags después de conectar
            if hasattr(self.m_bg, 'update_analyzer_flags'):
                self.m_bg.update_analyzer_flags()
            print("[CueEngine] V10: modules_golpe conectado a BaseGolpeModule")

    # ====== CALENDAR BRIDGE: CONTROL DE ESTADOS ======
    def set_disabled_states(self, states: List[str]) -> None:
        """
        Establece los estados deshabilitados por el calendario.

        Cuando un estado está deshabilitado:
        - El módulo correspondiente NO se ejecuta
        - Si el sistema está en ese estado, se comporta como BAJADA
        - Los cues activos de ese estado se apagan
        - StateManager tampoco elige ese estado como candidato (effective_score=0)

        Args:
            states: Lista de estados a deshabilitar (ej: ["ATAQUE", "BRAKE"])
                   Puede incluir "ALL" para deshabilitar todos

        IMPORTANTE: Este método es llamado por SystemBridge cuando el
        calendario cambia de modo. NO modificar lógica interna aquí.
        """
        old_disabled = self._disabled_states.copy()
        self._disabled_states = set(s.upper() for s in states)

        # ✅ CALENDAR BRIDGE: Propagar a StateManager para bloqueo en decisión
        if hasattr(self.sm, 'set_disabled_states'):
            self.sm.set_disabled_states(list(self._disabled_states))

        # Log cambios
        if self._disabled_states != old_disabled:
            if self._disabled_states:
                print(f"[CueEngine] 📅 Estados DESHABILITADOS: {sorted(self._disabled_states)}")
            else:
                print("[CueEngine] 📅 Todos los estados HABILITADOS")

        # Si "ALL" está en la lista, hard kill ALL musical cues immediately
        if "ALL" in self._disabled_states:
            print("[CueEngine] HARD OFF: ALL detected - killing all musical cues")
            all_musical_cues = []
            for family_cues in FAMILY_CUE_RANGES.values():
                all_musical_cues.extend(family_cues)
            active = [c for c in all_musical_cues if self.av.is_active(c)]
            if active:
                self.av.kill_pool(active)
                print(f"[CueEngine] HARD OFF: killed {active}")
            # Clear all family tracking
            for family in list(self.active_by_family.keys()):
                self.active_by_family[family] = None

    def is_state_disabled(self, state: str) -> bool:
        """
        Verifica si un estado está deshabilitado por el calendario.

        Args:
            state: Nombre del estado (ej: "ATAQUE")

        Returns:
            True si el estado está deshabilitado
        """
        if "ALL" in self._disabled_states:
            return True
        return state.upper() in self._disabled_states

    def get_disabled_states(self) -> List[str]:
        """
        Obtiene la lista de estados deshabilitados.

        Returns:
            Lista de nombres de estados deshabilitados
        """
        return sorted(list(self._disabled_states))

    # ====== OFF INSTANTÁNEO PRIORITARIO ======
    def _enforce_family_exclusivity(self) -> None:
        """
        Periodic sanity check: max 1 cue active per family.
        If >1 found, kill all except the most recently fired.
        """
        for family, cue_ids in FAMILY_CUE_RANGES.items():
            active = [c for c in cue_ids if self.av.is_active(c)]
            if len(active) > 1:
                # Keep last one (highest cue ID as proxy for most recent)
                to_kill = active[:-1]
                self.av.kill_pool(to_kill)
                print(f"[ENGINE] EXCLUSIVITY FIX: family={family} killed {to_kill}, kept C{active[-1]}")

    def off_now_for_family(self, family: str, extra_ids: Optional[List[int]] = None) -> None:
        """
        Apaga una familia de cues INMEDIATAMENTE sin contar contra rate limiting.
        
        CRÍTICO:
        - NO marca _sent_this_tick (permite ON en el mismo tick)
        - NO respeta transport_quiet_ms (bypasea throttling)
        - Usa kill_pool del driver que tiene PRIORITY_KILL y flush inmediato
        - Invalida active_by_family para esa familia
        - Logging con timestamps ms para medir latencia
        
        Args:
            family: Nombre de la familia ("bajada", "ataque", etc.)
            extra_ids: IDs adicionales a apagar (opcional)
        """
        if not family:
            return
        
        # Timestamp inicio (milisegundos)
        t_start_ms = time.time() * 1000
        
        # 1) Resolver IDs activos de esa familia
        ids_to_kill = set()
        
        # Consultar rangos predefinidos
        family_lower = family.lower()
        if family_lower in FAMILY_CUE_RANGES:
            range_ids = FAMILY_CUE_RANGES[family_lower]
            # Filtrar solo los activos según el driver
            active_in_range = [cid for cid in range_ids if self.av.is_active(cid)]
            ids_to_kill.update(active_in_range)
        
        # Agregar IDs extra si los hay
        if extra_ids:
            ids_to_kill.update(extra_ids)
        
        # Si no hay nada activo, salir temprano
        if not ids_to_kill:
            print(f"[ENGINE] OFF_NOW family={family} → nada activo (skip)")
            return
        
        # 2) Llamar a kill_pool inmediatamente (sin dedupe, con flush)
        ids_list = sorted(list(ids_to_kill))
        
        print(f"t={t_start_ms:.0f} [ENGINE] OFF_NOW family={family} ids={ids_list}")
        
        # Driver ya tiene PRIORITY_KILL y flush inmediato
        self.av.kill_pool(ids_list)
        
        # 3) Invalidar active_by_family
        if family in self.active_by_family:
            self.active_by_family[family] = None
        
        # 4) NO marcar _sent_this_tick - esto permite FIRE en el mismo tick
        # NO tocar transport_quiet_ms - este OFF es prioritario
        
        # 5) Tracking de métricas
        self.stats["off_now_calls"] = self.stats.get("off_now_calls", 0) + 1
        
        # Timestamp fin
        t_end_ms = time.time() * 1000
        latency_ms = t_end_ms - t_start_ms
        
        self.stats["off_now_latency_sum"] = self.stats.get("off_now_latency_sum", 0.0) + latency_ms
        
        print(f"t={t_end_ms:.0f} [ENGINE] OFF_NOW complete (latency={latency_ms:.1f}ms)")

    def off_now_for_state(self, state_name: str) -> None:
        """
        Apaga todas las familias asociadas a un estado INMEDIATAMENTE.
        
        Args:
            state_name: Nombre del estado ("BAJADA", "BASE_GOLPE", etc.)
        """
        if not state_name:
            return
        
        families = STATE_TO_FAMILY.get(state_name, [])
        if not families:
            return
        
        print(f"[ENGINE] OFF_NOW_FOR_STATE: {state_name} → families={families}")
        
        for family in families:
            self.off_now_for_family(family)
    
    def update(self):
        """
        Ciclo principal del motor — DETERMINÍSTICO.

        FLUJO:
          1. Leer estado/energía de StateManager
          2. Si cambió estado → OFF familia saliente (KILL primero)
          3. Ejecutar módulos en orden (FIRE nuevo estado)

        GARANTÍAS:
          - No hay auto-advance
          - No hay decisiones internas
          - Solo ejecuta lo que StateManager ordena
          - KILL antes de FIRE garantiza máximo 1 cue por familia
        """
        try:
            # ===== PASO 1: LEER ESTADO Y ENERGÍA =====
            if hasattr(self.sm, "get_state"):
                current_state = self.sm.get_state() or "UNKNOWN"
            else:
                current_state = getattr(self.sm, "current_state", "UNKNOWN")

            if hasattr(self.sm, "get_energy"):
                current_energy = self.sm.get_energy() or "MEDIA"
            else:
                current_energy = "MEDIA"
            
            # ✅ Log útil si no hay feed de estado (cada 5s)
            if current_state == "UNKNOWN":
                now = time.time()
                if (now - self._last_no_state_log) >= 5.0:
                    print("[CueEngine] no-state-feed: StateManager no entregó estado válido (siguiendo en UNKNOWN)")
                    self._last_no_state_log = now

            # ===== CALENDAR BRIDGE: VERIFICAR ESTADOS DESHABILITADOS =====
            # HARD OFF: "ALL" disabled = kill everything, skip ALL module execution
            if "ALL" in self._disabled_states:
                # Kill any remaining active musical cues (periodic enforcement)
                if self.stats.get("updates", 0) % 40 == 0:  # Every ~2s
                    all_musical_cues = []
                    for family_cues in FAMILY_CUE_RANGES.values():
                        all_musical_cues.extend(family_cues)
                    active = [c for c in all_musical_cues if self.av.is_active(c)]
                    if active:
                        self.av.kill_pool(active)
                        print(f"[CueEngine] HARD OFF: killed residual cues {active}")

                self.last_state = "OFF"
                self.last_energy = current_energy
                self.stats["updates"] = self.stats.get("updates", 0) + 1
                self.stats["total_updates"] = self.stats.get("total_updates", 0) + 1
                self.last_update_time = time.time()
                return  # NO module execution at all

            # Si el estado actual está deshabilitado por el calendario,
            # tratarlo como BAJADA (estado seguro por defecto)
            effective_state = current_state
            if self.is_state_disabled(current_state):
                effective_state = "BAJADA"
                # Log solo la primera vez que se bloquea
                if not hasattr(self, '_last_blocked_state') or self._last_blocked_state != current_state:
                    print(f"[CueEngine] Estado {current_state} BLOQUEADO por calendario → usando BAJADA")
                    self._last_blocked_state = current_state
            else:
                self._last_blocked_state = None

            state_changed = (effective_state != self.last_state)
            energy_changed = (current_energy != self.last_energy)

            # ===== PASO 2: KILL FAMILIA SALIENTE PRIMERO (si cambió estado) =====
            # KILL antes de FIRE: garantiza máximo 1 cue por familia en todo momento
            if state_changed and self.last_state is not None:
                t_change_ms = time.time() * 1000
                print(f"t={t_change_ms:.0f} [ENGINE] STATE CHANGE: {self.last_state} → {effective_state}")
                self.off_now_for_state(self.last_state)

            # Actualizar tracking
            if state_changed:
                self.stats["state_changes"] = self.stats.get("state_changes", 0) + 1
            if energy_changed:
                self.stats["energy_changes"] = self.stats.get("energy_changes", 0) + 1

            self.last_state = effective_state
            self.last_energy = current_energy

            # ===== PASO 3: EJECUTAR MÓDULOS EN ORDEN ESTRICTO =====
            # Cada módulo recibe (state, energy) y decide qué hacer con SU familia
            # FIRE del nuevo estado DESPUÉS del KILL (sin overlap)
            modules_in_order = [
                ("control_dimmer", self.m_control),
                ("break", self.m_break),
                ("ataque", self.m_ataque),
                ("base_golpe", self.m_bg),
                ("bajada", self.m_bajada),
                ("movimiento", self.m_move),
                ("timed", self.m_timed)
            ]

            for name, module in modules_in_order:
                try:
                    if hasattr(module, 'run'):
                        self.stats["specialist_calls"] = self.stats.get("specialist_calls", 0) + 1
                        module.run(effective_state, current_energy)
                        self.last_specialist = name
                except Exception as e:
                    self.stats["specialist_errors"] = self.stats.get("specialist_errors", 0) + 1
                    self.last_error = str(e)
                    print(f"[CueEngine] Error en módulo {name}: {e}")
            
            # ===== FAMILY EXCLUSIVITY CHECK (every 20 ticks = ~1s) =====
            self.stats["updates"] = self.stats.get("updates", 0) + 1
            if self.stats["updates"] % 20 == 0:
                self._enforce_family_exclusivity()

            self.stats["total_updates"] = self.stats.get("total_updates", 0) + 1
            self.last_update_time = time.time()

            # C41 WATCHDOG: every 200 ticks (~10s at 50ms interval)
            if self.stats["updates"] % 200 == 0:
                try:
                    self.m_control.ensure_c41_on()
                except Exception:
                    pass
            
        except Exception as e:
            self.last_error = str(e)
            print(f"[CueEngine] Error en update: {e}")

    def start_auto_update(self):
        if self._running:
            return

        self._running = True
        self._auto_update_running = True

        # =====================================================================
        # BOOT SYNC: Estado inicial del sistema = DIMMER ON (C41)
        # Dispara UNA SOLA VEZ al arranque, antes del loop
        # =====================================================================
        try:
            self.av.fire_cue(41)
            print("[CueEngine] BOOT SYNC: C41 fired (dimmer ON)")
        except Exception as e:
            print(f"[CueEngine] BOOT SYNC: C41 fire failed: {e}")

        def _loop():
            print(f"[CueEngine] Auto-update iniciado (intervalo: {self.interval}s)")
            while self._running:
                try:
                    self.update()
                    time.sleep(self.interval)
                except Exception as e:
                    print(f"[CueEngine] Error en loop: {e}")
                    time.sleep(self.interval)
        
        self._thr = threading.Thread(target=_loop, daemon=True)
        self._thr.start()

    def stop_auto_update(self):
        if not self._running:
            return
        
        print("[CueEngine] Deteniendo auto-update...")
        self._running = False
        self._auto_update_running = False
        
        if self._thr and self._thr.is_alive():
            self._thr.join(timeout=2.0)
        
        print("[CueEngine] Auto-update detenido")

    def get_status(self) -> Dict[str, Any]:
        current_time = time.time()
        uptime = max(current_time - self.start_time, 0.001)

        # Calcular latencia promedio de OFF_NOW
        off_now_calls = self.stats.get("off_now_calls", 0)
        off_now_avg_latency = 0.0
        if off_now_calls > 0:
            off_now_avg_latency = self.stats.get("off_now_latency_sum", 0.0) / off_now_calls

        # Obtener estado de AuxStateManager
        aux_status = {}
        try:
            aux_status = self.aux.get_status()
        except Exception:
            aux_status = {"error": "unavailable"}

        return {
            "version": "6.0",
            "architecture": "DETERMINISTIC+state_energy_feed+OFF_NOW_priority+AUX_V2",
            "current_state": self.last_state or "UNKNOWN",
            "current_energy": self.last_energy or "UNKNOWN",
            "last_specialist": self.last_specialist,
            "auto_update_running": self._auto_update_running,
            "uptime_seconds": uptime,
            "last_update_time": self.last_update_time,
            "stats": dict(self.stats),
            "last_error": self.last_error,
            "interval": self.interval,
            "modules_count": 7,
            "active_by_family": dict(self.active_by_family),
            "conflict_families": CONFLICT_FAMILIES,
            "brake_module_loaded": self.m_break is not None,
            "off_now_avg_latency_ms": off_now_avg_latency,
            "aux_status": aux_status,
            "disabled_states": self.get_disabled_states(),
            "calendar_governed": len(self._disabled_states) > 0,
        }

    def get_metrics(self) -> Dict[str, float]:
        current_time = time.time()
        uptime = max(current_time - self.start_time, 0.001)
        
        updates = self.stats.get("total_updates", 0)
        calls = self.stats.get("specialist_calls", 0)
        errors = self.stats.get("specialist_errors", 0)
        state_changes = self.stats.get("state_changes", 0)
        energy_changes = self.stats.get("energy_changes", 0)
        brake_ints = self.stats.get("brake_interrupts", 0)
        throttles = self.stats.get("transport_throttles", 0)
        cross_kills = self.stats.get("cross_kills", 0)
        atomic_switches = self.stats.get("atomic_switches", 0)
        off_now_calls = self.stats.get("off_now_calls", 0)
        
        # Latencia promedio OFF_NOW
        off_now_avg_latency = 0.0
        if off_now_calls > 0:
            off_now_avg_latency = self.stats.get("off_now_latency_sum", 0.0) / off_now_calls
        
        return {
            "uptime_seconds": uptime,
            "updates_per_second": updates / uptime,
            "specialist_calls_per_update": calls / max(updates, 1),
            "error_rate": errors / max(calls, 1),
            "state_change_frequency": (state_changes / uptime) * 60,
            "energy_change_frequency": (energy_changes / uptime) * 60,
            "brake_interrupt_rate": brake_ints / max(uptime / 60, 1),
            "transport_throttle_rate": throttles / max(calls, 1),
            "cross_kill_rate": cross_kills / max(uptime / 60, 1),
            "atomic_switch_rate": atomic_switches / max(uptime / 60, 1),
            "off_now_calls_total": off_now_calls,
            "off_now_avg_latency_ms": off_now_avg_latency,
        }

    def get_specialist_debug(self) -> str:
        try:
            lines = []
            modules = [
                ("Control", self.m_control),
                ("Break", self.m_break),
                ("Ataque", self.m_ataque),
                ("BaseGolpe", self.m_bg),
                ("Bajada", self.m_bajada),
                ("Movimiento", self.m_move),
                ("TimedSequence", self.m_timed)
            ]
            
            for name, module in modules:
                try:
                    if hasattr(module, 'get_status'):
                        status = module.get_status()
                        active_cues = status.get('active_cues', [])
                        if active_cues:
                            lines.append(f"{name}: cues {active_cues}")
                        else:
                            lines.append(f"{name}: idle")
                    else:
                        lines.append(f"{name}: no status")
                except Exception as e:
                    lines.append(f"{name}: error({e})")
            
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    def reset(self):
        """
        Reset general del engine.
        ✅ PERSISTENCIA RR: Llama a MovimientoModule.reset(hard=False) para conservar RR.
        """
        print("[CueEngine] Reset iniciado...")
        
        was_running = self._running
        if was_running:
            self.stop_auto_update()
        
        try:
            self.stats = {
                "updates": 0, 
                "state_changes": 0, 
                "energy_changes": 0,
                "total_updates": 0,
                "specialist_calls": 0,
                "specialist_errors": 0,
                "brake_interrupts": 0,
                "transport_throttles": 0,
                "cross_kills": 0,
                "atomic_switches": 0,
                "off_now_calls": 0,
                "off_now_latency_sum": 0.0,
            }
            
            self.start_time = time.time()
            self.last_update_time = time.time()
            self.last_error = None
            self.last_specialist = "None"
            self.last_state = None
            self.last_energy = None
            self.active_by_family = {k: None for k in self.active_by_family}
            self._last_no_state_log = 0.0
            
            modules = [
                self.m_control, 
                self.m_break, 
                self.m_ataque, 
                self.m_bg, 
                self.m_bajada, 
                self.m_move,  # especial: reset(hard=False)
                self.m_timed
            ]
            
            for module in modules:
                try:
                    if hasattr(module, 'reset'):
                        # ✅ PERSISTENCIA RR: MovimientoModule usa reset(hard=False)
                        if isinstance(module, MovimientoModule):
                            module.reset(hard=False)
                        else:
                            module.reset()
                except Exception as e:
                    print(f"[CueEngine] Error resetting module: {e}")
            
            print("[CueEngine] Reset completado")
            
        except Exception as e:
            print(f"[CueEngine] Error durante reset: {e}")
        
        if was_running:
            self.start_auto_update()

    def silent_reset(self):
        """
        KILL ALL CANÓNICO — Reset de estado SIN disparar cues.

        Para testing: mata todo en Titan Y limpia estado lógico.
        El sistema queda SILENTE hasta el próximo evento musical.

        IMPORTANTE:
        - NO dispara C41
        - NO hace restore de snapshots
        - NO reinicia auto-update
        - Solo limpia estado interno
        """
        print("[CueEngine] SILENT RESET (testing mode)...")

        # Reset estado del engine
        self.last_state = None
        self.last_energy = None
        self.active_by_family = {k: None for k in self.active_by_family}

        # Reset cada módulo SIN disparar cues
        # Solo limpiamos variables de estado

        # control_dimmer
        if self.m_control:
            self.m_control._reasons.clear()
            self.m_control._is_dim_off = False

        # brake
        if self.m_break:
            self.m_break.current_cue = None
            self.m_break.current_energy = None
            self.m_break.hold_until = 0.0
            self.m_break.last_state_seen = None
            self.m_break.freeze_snapshot = None
            self.m_break._dimmer_requested = False

        # ataque
        if self.m_ataque:
            self.m_ataque.current_cue = None
            self.m_ataque.current_energy = None
            self.m_ataque.hold_until = 0.0
            self.m_ataque.last_state_seen = None

        # base_golpe
        if self.m_bg:
            self.m_bg._last_state_seen = None
            self.m_bg._dimmer_requested = False

        # bajada
        if self.m_bajada:
            if hasattr(self.m_bajada, 'last_state_seen'):
                self.m_bajada.last_state_seen = None
            if hasattr(self.m_bajada, '_last_state_seen'):
                self.m_bajada._last_state_seen = None

        # movimiento
        if self.m_move:
            if hasattr(self.m_move, 'last_state_seen'):
                self.m_move.last_state_seen = None
            if hasattr(self.m_move, '_is_paused'):
                self.m_move._is_paused = False

        # timed_sequence
        if self.m_timed:
            if hasattr(self.m_timed, 'last_state_seen'):
                self.m_timed.last_state_seen = None
            if hasattr(self.m_timed, '_last_state_seen'):
                self.m_timed._last_state_seen = None

        print("[CueEngine] SILENT RESET completado — sistema SILENTE")

    def emergency_stop(self):
        print("[CueEngine] EMERGENCY STOP")
        
        self.stop_auto_update()
        
        try:
            if hasattr(self.av, 'kill_all_cues'):
                self.av.kill_all_cues()
            
            self.reset()
            
            print("[CueEngine] Emergency stop completado")
            
        except Exception as e:
            print(f"[CueEngine] Error durante emergency stop: {e}")

    def get_active_cues(self) -> List[int]:
        out: List[int] = []
        for m in (self.m_control, self.m_break, self.m_ataque, self.m_bg, self.m_bajada, self.m_move, self.m_timed):
            try:
                arr = m.get_active_cues()
                if arr:
                    out.extend(arr)
            except Exception:
                pass
        return sorted(list({int(x) for x in out}))

    def get_modules_status(self) -> Dict[str, Any]:
        def _st(mod):
            try:
                return mod.get_status()
            except Exception:
                return {"error": "no status"}
        return {
            "state": self.last_state,
            "energy": self.last_energy,
            "stats": dict(self.stats),
            "modules": {
                "control_dimmer": _st(self.m_control),
                "break": _st(self.m_break),
                "ataque": _st(self.m_ataque),
                "basegolpe": _st(self.m_bg),
                "bajada": _st(self.m_bajada),
                "movimiento": _st(self.m_move),
                "timed_sequence": _st(self.m_timed),
            }
        }

    def __del__(self):
        try:
            self.stop_auto_update()
        except Exception:
            pass


def create_cue_engine(
    avolites_controller,
    state_manager,
    energy_detector,
    auto_update: bool = True,
    interval: float = 0.05,
):
    """
    Factory function para crear instancia de CueEngine.
    
    ✅ v5.0: SIN GATE READY - motor siempre corre + feed state/energy
    ✅ PERSISTENCIA RR: reset(hard=False) para MovimientoModule conserva RR
    """
    return CueEngine(
        avolites_controller=avolites_controller,
        state_manager=state_manager,
        energy_detector=energy_detector,
        auto_update=auto_update,
        interval=interval,
    )


__all__ = ["CueEngine", "create_cue_engine"]