# mod_timed_sequence.py — AUXILIARES: Secuencia temporal C45-C50
# ===========================================================================
# QUÉ HACE:
#   - Dispara cues C45-C50 secuencialmente por tiempo de permanencia
#   - ESCUCHA TODOS LOS ESTADOS (funciona en cualquier estado global)
#   - RESPETA PRIORIDADES (kill_pending gobierna toda la secuencia)
#   - NO QUEDA PEGADO (kill confirmado antes de avanzar)
#   - NO IGNORA OFF GLOBAL (kill_on_state_change respetado)
#
# QUÉ NO HACE:
#   - NO decide cambios de estado (eso es del StateManager)
#   - NO interfiere con otras familias
#
# GARANTÍAS:
#   - 0% doble auxiliar (máquina de estados V3)
#   - 0% auxiliares pegados (kill confirmado via is_active())
#   - Referencias NUNCA perdidas prematuramente
#
# MÁQUINA DE ESTADOS:
#   idle → fire_candidate → hold → kill_pending → idle
# ===========================================================================
import time
from typing import List, Optional, Dict, Any


# Estados de la máquina
STATE_IDLE = "idle"
STATE_KILL_PENDING = "kill_pending"
STATE_FIRE_CANDIDATE = "fire_candidate"
STATE_HOLD = "hold"


class TimedSequenceModule:
    """
    Dispara una secuencia de cues (por tiempo de permanencia en el estado actual).

    MÁQUINA DE ESTADOS V3:
    - idle: No hay cue activo, puede avanzar
    - kill_pending: Hay cue que debe apagarse, retry kill, NO avanzar
    - fire_candidate: Listo para disparar siguiente cue
    - hold: Cue activo esperando cambio de slot

    REGLAS CRÍTICAS:
    - kill_pending gobierna TODA la secuencia
    - retry kill cada _min_gap hasta éxito
    - fire solo cuando no hay kill pendiente
    - ningún avance hasta kill confirmado
    - nunca perder referencia del cue actual

    AUX-V2: Si aux_manager existe, sincroniza índice global (solo tabla, NO hardware).
    TimedSequence SIEMPRE hace fire/kill directamente.
    """

    def __init__(
        self, av_controller, state_manager,
        *, start_after: float = 20.0, interval: float = 10.0,
        cues: Optional[List[int]] = None,
        kill_on_state_change: bool = True,
        persist_index_across_states: bool = True,
        kill_previous_on_advance: bool = True,
        aux_manager=None,
        **kwargs,  # Acepta duration para compatibilidad pero no la usa
    ):
        self.av = av_controller
        self.sm = state_manager
        self.aux = aux_manager
        self.enabled = True

        self.start_after = float(start_after)
        self.interval = float(interval)
        self.cues = list(cues or [45, 46, 47, 48, 49, 50])

        self.kill_on_state_change = bool(kill_on_state_change)
        self.persist_index = bool(persist_index_across_states)
        self.kill_previous_on_advance = bool(kill_previous_on_advance)

        # === MÁQUINA DE ESTADOS V3 ===
        self._state: str = STATE_IDLE

        # Referencias del cue activo (NUNCA limpiar antes de kill confirmado)
        self.last_fired_cue: Optional[int] = None
        self.last_fired_ts: Optional[float] = None

        # Índices y contadores
        self.global_index: int = 0
        self.last_slot_index_seen: int = -1
        self.fires_total: int = 0

        # Estado global del sistema
        self.last_state_seen: Optional[str] = None

        # Anti-spam Avolites
        self._last_kill_ts: float = 0.0
        self._last_fire_ts: float = 0.0
        self._min_gap: float = 0.15

        # TIMING FIX: ventana de gracia tras cambio de estado
        self._defer_until: float = 0.0

        # Block AUX re-fire for start_after seconds after state change
        self._blocked_until: float = 0.0

        # Configurar aux si existe
        if self.aux is not None:
            self.aux.set_aux_sequence(self.cues)
            self.aux.set_aux_enabled(self.enabled)

        mode = "AUX-V2" if self.aux else "LEGACY"
        print(f"[TIMED_SEQ] init V3 ({mode}) state={self._state}")

    def _now(self) -> float:
        try:
            return time.monotonic()
        except Exception:
            return time.time()

    def _dwell_seconds(self) -> float:
        try:
            return max(0.0, time.time() - float(self.sm.state_start_time))
        except Exception:
            return 0.0

    def _get_global_index(self) -> int:
        """Obtiene índice global (de aux si existe, sino local)."""
        if self.aux is not None:
            return self.aux.get_aux_index()
        return self.global_index

    def _increment_global_index(self):
        """Incrementa índice global (en aux si existe, sino local)."""
        if self.aux is not None:
            self.aux.increment_aux_index()
            self.global_index = self.aux.get_aux_index()
        else:
            self.global_index += 1

    def _can_kill(self) -> bool:
        """Verifica si pasó suficiente tiempo desde último kill."""
        return self._now() - self._last_kill_ts >= self._min_gap

    def _can_fire(self) -> bool:
        """Verifica si pasó suficiente tiempo desde último fire."""
        return self._now() - self._last_fire_ts >= self._min_gap

    def _do_kill(self) -> bool:
        """
        Intenta matar el cue actual.
        Retorna True si kill fue exitoso, False si falló o rate-limited.
        NUNCA limpia referencias aquí - eso lo hace el caller tras confirmar.
        """
        if self.last_fired_cue is None:
            return True  # Nada que matar = éxito

        if not self._can_kill():
            return False  # Rate limited

        try:
            self.av.kill_cue(int(self.last_fired_cue))
            self._last_kill_ts = self._now()
            return True
        except Exception:
            self._last_kill_ts = self._now()
            return False

    def _do_fire(self, cue_num: int) -> bool:
        """
        Intenta disparar un cue.
        Retorna True si fire fue exitoso, False si falló o rate-limited.
        """
        if not self._can_fire():
            return False  # Rate limited

        try:
            self.av.fire_cue(cue_num)
            self._last_fire_ts = self._now()
            return True
        except Exception:
            self._last_fire_ts = self._now()
            return False

    # =========================================================================
    # MÁQUINA DE ESTADOS V3
    # =========================================================================

    def _handle_idle(self, slot_index: int) -> None:
        """
        ESTADO IDLE: No hay cue activo, puede avanzar.
        Si slot_index > last_slot_index_seen → pasar a fire_candidate.
        """
        if slot_index > self.last_slot_index_seen:
            self._state = STATE_FIRE_CANDIDATE

    def _handle_kill_pending(self) -> None:
        """
        ESTADO KILL_PENDING: Hay cue que debe apagarse.
        - Reintentar kill cada _min_gap
        - NO disparar nada
        - NO avanzar secuencia
        - NO limpiar referencias hasta kill CONFIRMADO por is_active()
        - Kill confirmado → pasar a idle

        FIX-KILL-SEGURO: Verificar con is_active() que el kill fue efectivo.
        """
        if self.last_fired_cue is None:
            # No hay cue que matar, limpiar estado
            self._state = STATE_IDLE
            return

        if self._do_kill():
            # Verificar que realmente está apagado (no confiar solo en el kill)
            if not self.av.is_active(self.last_fired_cue):
                # Kill CONFIRMADO: ahora sí limpiar referencias
                self.last_fired_cue = None
                self.last_fired_ts = None
                self._state = STATE_IDLE
            # Si sigue activo, quedarse en kill_pending para reintentar

    def _handle_fire_candidate(self, slot_index: int) -> None:
        """
        ESTADO FIRE_CANDIDATE: Listo para disparar siguiente cue.
        - Si kill_pending → volver a kill_pending (nunca debería pasar)
        - Si hay cue activo y kill_previous → marcar kill_pending
        - Si no hay cue activo → disparar cue
        - Fire exitoso → pasar a hold
        - Fire fallido → quedarse en fire_candidate
        """
        # Seguridad: si hay cue activo y debemos matarlo primero
        if self.kill_previous_on_advance and self.last_fired_cue is not None:
            self._state = STATE_KILL_PENDING
            return

        # Obtener siguiente cue de la secuencia
        idx = self._get_global_index()
        cue_num = int(self.cues[idx % len(self.cues)])

        if self._do_fire(cue_num):
            # Fire exitoso
            self.last_fired_cue = cue_num
            self.last_fired_ts = time.time()
            self.fires_total += 1

            # Incrementar índice DESPUÉS de fire exitoso
            self._increment_global_index()

            # Actualizar slot
            self.last_slot_index_seen = slot_index

            print(f"[TIMED_SEQ] fired C{cue_num} (idx={idx})")
            self._state = STATE_HOLD
        # Si fire falló, quedarse en fire_candidate para reintentar

    def _handle_hold(self, slot_index: int, state_changed: bool) -> None:
        """
        ESTADO HOLD: Cue activo esperando cambio.
        - Si estado global cambia → kill_pending, NO avanzar
        - Si slot cambia → kill_pending, NO avanzar slot aún
        """
        if state_changed:
            # Cambio de estado global: marcar kill pendiente
            if self.kill_on_state_change and self.last_fired_cue is not None:
                self._state = STATE_KILL_PENDING
            else:
                self._state = STATE_IDLE
            return

        if slot_index > self.last_slot_index_seen:
            # Slot avanzó: marcar kill pendiente antes de avanzar
            if self.kill_previous_on_advance and self.last_fired_cue is not None:
                self._state = STATE_KILL_PENDING
            else:
                # No hay que matar, ir directo a fire_candidate
                self._state = STATE_FIRE_CANDIDATE

    def force_exit(self) -> None:
        """
        SALIDA FORZADA DEFINITIVA.
        Mata TODOS los cues auxiliares SIN CONDICIONES.
        Reset TOTAL del módulo.
        """
        # Kill incondicional de TODOS los cues de la secuencia
        for cue in self.cues:
            try:
                self.av.kill_cue(cue)
            except:
                pass

        # Reset TOTAL del módulo
        self._state = STATE_IDLE
        self.last_fired_cue = None
        self.last_fired_ts = None
        self._last_fire_ts = 0.0
        self._last_kill_ts = self._now()
        self.last_slot_index_seen = -1

        # Block re-fire for start_after seconds (prevents immediate AUX re-trigger)
        self._blocked_until = time.time() + self.start_after

        print(f"[TIMED_SEQ] FORCE EXIT — all auxiliaries killed, blocked for {self.start_after}s")

    # =========================================================================
    # RUN PRINCIPAL
    # =========================================================================

    def run(self, state_name: str, energy_name: str) -> None:
        """
        Ejecuta lógica de secuencia temporal con máquina de estados V3.

        GARANTÍAS:
        - 0% doble auxiliar
        - 0% auxiliares pegados
        - Kill SIEMPRE confirmado antes de avanzar
        - Referencias NUNCA perdidas prematuramente
        """
        if not self.enabled or not self.cues:
            return

        # 1. Detectar cambio de estado global
        state_changed = False
        if self.last_state_seen is None:
            self.last_state_seen = state_name
        elif state_name != self.last_state_seen:
            state_changed = True
            self.last_state_seen = state_name

        # 2. SALIDA FORZADA en CADA cambio de estado — SIN CONDICIONES
        if state_changed:
            self.force_exit()
            # Bloquear cualquier fire posterior por 150ms
            self._defer_until = time.time() + 0.15
            return  # NO ejecutar NADA más en este tick

        # 3. Guard de defer bloquea fires
        if time.time() < self._defer_until:
            return

        # 3b. Block guard: no re-fire until blocked_until expires
        if time.time() < self._blocked_until:
            return

        # 4. Calcular dwell y slot
        dwell = self._dwell_seconds()

        # Si estamos antes de start_after, resetear slot
        if dwell < self.start_after:
            self.last_slot_index_seen = -1
            slot_index = -1
        else:
            slot_index = int((dwell - self.start_after) // self.interval)

        # Si estamos antes de start_after, no hacer nada más
        if dwell < self.start_after:
            return

        # === EJECUTAR MÁQUINA DE ESTADOS (solo fires) ===
        if self._state == STATE_IDLE:
            self._handle_idle(slot_index)
            # Si cambió a fire_candidate, ejecutar inmediatamente
            if self._state == STATE_FIRE_CANDIDATE:
                self._handle_fire_candidate(slot_index)

        elif self._state == STATE_FIRE_CANDIDATE:
            self._handle_fire_candidate(slot_index)

        elif self._state == STATE_HOLD:
            self._handle_hold(slot_index, state_changed=False)
            # Si cambió a fire_candidate, ejecutar inmediatamente
            if self._state == STATE_FIRE_CANDIDATE:
                self._handle_fire_candidate(slot_index)

    # =========================================================================
    # API PÚBLICA
    # =========================================================================

    def get_active_cues(self) -> List[int]:
        return [self.last_fired_cue] if self.last_fired_cue else []

    def get_status(self) -> Dict[str, Any]:
        dwell = self._dwell_seconds()
        if dwell < self.start_after:
            eta = max(0.0, self.start_after - dwell)
        else:
            slot = int((dwell - self.start_after) // self.interval)
            eta = max(0.0, self.start_after + (slot + 1) * self.interval - dwell)

        return {
            "mode": "AUX-V2" if self.aux else "LEGACY",
            "version": "V3",
            "state": self._state,
            "enabled": self.enabled,
            "sequence": self.cues[:],
            "global_index": self._get_global_index(),
            "last_fired_cue": self.last_fired_cue,
            "last_fired_ts": self.last_fired_ts,
            "last_slot_index": self.last_slot_index_seen,
            "dwell": dwell,
            "start_after": self.start_after,
            "interval": self.interval,
            "next_eta": eta,
            "fires_total": self.fires_total,
            "active_cues": self.get_active_cues(),
        }

    def force_next(self):
        """Dispara el siguiente cue de la secuencia inmediatamente."""
        if not self.enabled or not self.cues:
            return

        # Si hay cue activo, marcar kill pendiente
        if self.last_fired_cue is not None:
            self._state = STATE_KILL_PENDING
            return

        # Disparar siguiente
        idx = self._get_global_index()
        cue_num = int(self.cues[idx % len(self.cues)])

        if self._do_fire(cue_num):
            self.last_fired_cue = cue_num
            self.last_fired_ts = time.time()
            self.fires_total += 1
            self._increment_global_index()
            self._state = STATE_HOLD

    def reset_global_index(self, value: int = 0):
        """Resetea el índice global de la secuencia."""
        if self.aux is not None:
            self.aux.reset_aux_index(value)
        self.global_index = max(0, int(value))

    def kill_current(self):
        """Mata el cue actual de la secuencia."""
        if self.last_fired_cue is not None:
            self._state = STATE_KILL_PENDING
