# ============================================================================
# titan_sync.py v1.0 - TITAN STATE SYNC
# ============================================================================
# Watchdog que sincroniza estado entre 911 y Titan
#
# Features:
# - Consulta Titan cada 2 segundos (configurable)
# - GET /titan/script/Playbacks/GetActivePlaybacks
# - Detecta cues "colgados" (activos en Titan pero no en 911)
# - Envia KILL automatico para cues huerfanos
# - Resuelve pending_kills de la cola
# - Logging detallado de sincronizacion
# ============================================================================

from __future__ import annotations

import time
import threading
import logging
from typing import Optional, Dict, Any, Set, List, Callable
from dataclasses import dataclass, field
from enum import Enum

from .titan_transport import TitanTransport, TransportConfig
from .titan_queue import TitanQueue

# ===== LOGGING =====
logger = logging.getLogger("TitanStateSync")


class SyncState(Enum):
    """Estado del sync."""
    STOPPED = "STOPPED"
    RUNNING = "RUNNING"
    ERROR = "ERROR"


@dataclass
class SyncConfig:
    """Configuracion del sync."""
    poll_interval_s: float = 2.0  # Cada cuantos segundos consultar
    orphan_grace_period_ms: float = 500.0  # Grace period antes de considerar huerfano
    max_kills_per_cycle: int = 10  # Max KILLs por ciclo para no saturar
    retry_pending_interval_s: float = 1.0  # Cada cuanto reintentar pending_kills
    auto_kill_orphans: bool = True  # Matar huerfanos automaticamente


@dataclass
class SyncStats:
    """Estadisticas del sync."""
    polls_total: int = 0
    polls_ok: int = 0
    polls_failed: int = 0
    orphans_detected: int = 0
    orphans_killed: int = 0
    pending_resolved: int = 0
    last_poll_ts: float = 0.0
    last_error: Optional[str] = None
    titan_active_count: int = 0
    local_active_count: int = 0
    sync_delta: int = 0  # Diferencia entre titan y local


class TitanStateSync:
    """
    Titan State Sync v1.0

    Watchdog que sincroniza estado entre el motor 911 y Avolites Titan.

    Funcion principal:
    - Cada 2 segundos consulta: GET /titan/script/Playbacks/GetActivePlaybacks
    - Compara con _active_cues local
    - Si Titan tiene cues que 911 no tiene -> KILL inmediato

    Esto elimina definitivamente cualquier cue "colgado".

    Uso:
        sync = TitanStateSync(transport, queue)
        sync.start()
        # ... operacion normal ...
        sync.stop()

    O integrado en el controller:
        controller.sync.get_stats()
    """

    def __init__(
        self,
        transport: TitanTransport,
        queue: TitanQueue,
        config: Optional[SyncConfig] = None,
        get_local_active: Optional[Callable[[], Set[int]]] = None,
        user_number_offset: int = 169,
    ):
        """
        Inicializa el sync.

        Args:
            transport: TitanTransport para consultas HTTP
            queue: TitanQueue para encolar KILLs
            config: Configuracion del sync
            get_local_active: Callback que retorna cues activos locales
            user_number_offset: Offset para mapeo de cues
        """
        self.config = config or SyncConfig()
        self.stats = SyncStats()

        self._transport = transport
        self._queue = queue
        self._get_local_active = get_local_active
        self._user_number_offset = user_number_offset

        # Estado
        self._state = SyncState.STOPPED
        self._worker_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Cache de ultimo estado Titan
        self._last_titan_active: Set[int] = set()
        self._titan_lock = threading.Lock()

        # Tracking de huerfanos detectados (para grace period)
        self._orphan_first_seen: Dict[int, float] = {}

        logger.info("[TitanStateSync] Inicializado")

    # ===== CONTROL =====

    def start(self) -> bool:
        """
        Inicia el worker de sync.

        Returns:
            bool: True si inicio correctamente
        """
        if self._state == SyncState.RUNNING:
            return True

        self._stop_event.clear()
        self._state = SyncState.RUNNING

        self._worker_thread = threading.Thread(
            target=self._sync_loop,
            name="TitanStateSync-Worker",
            daemon=True
        )
        self._worker_thread.start()

        logger.info("[TitanStateSync] Started")
        return True

    def stop(self, timeout: float = 2.0) -> bool:
        """
        Detiene el worker de sync.

        Args:
            timeout: Segundos a esperar por el thread

        Returns:
            bool: True si se detuvo correctamente
        """
        if self._state == SyncState.STOPPED:
            return True

        self._state = SyncState.STOPPED
        self._stop_event.set()

        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=timeout)

        logger.info("[TitanStateSync] Stopped")
        return True

    # ===== SYNC LOOP =====

    def _sync_loop(self):
        """Loop principal del sync."""
        logger.info(f"[TitanStateSync] Worker started (poll every {self.config.poll_interval_s}s)")

        last_poll = 0.0
        last_pending_check = 0.0

        while not self._stop_event.is_set():
            try:
                now = time.time()

                # Poll de estado Titan
                if (now - last_poll) >= self.config.poll_interval_s:
                    self._poll_titan_state()
                    last_poll = now

                # Reintentar pending_kills
                if (now - last_pending_check) >= self.config.retry_pending_interval_s:
                    self._retry_pending_kills()
                    last_pending_check = now

                # Sleep corto para no saturar CPU
                time.sleep(0.1)

            except Exception as e:
                self._state = SyncState.ERROR
                self.stats.last_error = str(e)
                logger.error(f"[TitanStateSync] Loop error: {e}")
                time.sleep(1.0)  # Esperar antes de reintentar

        logger.info("[TitanStateSync] Worker stopped")

    def _poll_titan_state(self):
        """Consulta estado de Titan y detecta huerfanos."""
        self.stats.polls_total += 1

        # Obtener playbacks activos de Titan
        response = self._transport.get_active_playbacks()

        if response is None:
            self.stats.polls_failed += 1
            return

        self.stats.polls_ok += 1
        self.stats.last_poll_ts = time.time()

        # Parsear respuesta de Titan
        titan_active = self._parse_active_playbacks(response)
        self.stats.titan_active_count = len(titan_active)

        with self._titan_lock:
            self._last_titan_active = titan_active.copy()

        # Obtener estado local
        local_active = self._get_local_state()
        self.stats.local_active_count = len(local_active)
        self.stats.sync_delta = len(titan_active) - len(local_active)

        # Detectar huerfanos (en Titan pero no en local)
        orphans = titan_active - local_active

        if orphans:
            self._handle_orphans(orphans)

        # Limpiar huerfanos que ya no estan
        current_time = time.time()
        self._orphan_first_seen = {
            cue: ts for cue, ts in self._orphan_first_seen.items()
            if cue in orphans
        }

    def _parse_active_playbacks(self, response: Any) -> Set[int]:
        """
        Parsea respuesta de GetActivePlaybacks.

        La respuesta de Titan puede variar segun version.
        Formato tipico: lista de objetos con userNumber.
        """
        result = set()

        try:
            # Si es lista directa
            if isinstance(response, list):
                for item in response:
                    if isinstance(item, dict):
                        user_num = item.get("userNumber") or item.get("UserNumber")
                        if user_num is not None:
                            # Convertir de real a logico (restar offset)
                            logical = int(user_num) - self._user_number_offset
                            if logical > 0:  # Ignorar negativos
                                result.add(logical)
                    elif isinstance(item, (int, float)):
                        # Numero directo
                        logical = int(item) - self._user_number_offset
                        if logical > 0:
                            result.add(logical)

            # Si es dict con key "playbacks"
            elif isinstance(response, dict):
                playbacks = response.get("playbacks") or response.get("Playbacks") or []
                return self._parse_active_playbacks(playbacks)

        except Exception as e:
            logger.warning(f"[TitanStateSync] Parse error: {e}")

        return result

    def _get_local_state(self) -> Set[int]:
        """Obtiene estado local de cues activos."""
        if self._get_local_active:
            try:
                return self._get_local_active()
            except Exception as e:
                logger.warning(f"[TitanStateSync] get_local_active error: {e}")

        # Fallback: usar estado de la cola
        return self._queue.get_active_cues()

    def _handle_orphans(self, orphans: Set[int]):
        """
        Maneja cues huerfanos detectados.

        Aplica grace period antes de matar para evitar falsos positivos
        durante operaciones rapidas.
        """
        current_time = time.time()
        grace_period_s = self.config.orphan_grace_period_ms / 1000.0
        kills_this_cycle = 0

        for cue_id in orphans:
            # Registrar primera vez visto
            if cue_id not in self._orphan_first_seen:
                self._orphan_first_seen[cue_id] = current_time
                logger.debug(f"[TitanStateSync] Orphan detected: C{cue_id}")
                continue

            # Verificar grace period
            first_seen = self._orphan_first_seen[cue_id]
            age_s = current_time - first_seen

            if age_s < grace_period_s:
                continue  # Aun en grace period

            # Grace period expirado -> matar
            self.stats.orphans_detected += 1
            logger.warning(f"[TitanStateSync] Orphan confirmed: C{cue_id} (age={age_s:.2f}s) -> KILL")

            if self.config.auto_kill_orphans:
                # Encolar KILL con prioridad maxima
                if self._queue.kill(cue_id, priority_boost=True):
                    self.stats.orphans_killed += 1
                    kills_this_cycle += 1

                    # Limpiar de tracking
                    del self._orphan_first_seen[cue_id]

            # Respetar limite por ciclo
            if kills_this_cycle >= self.config.max_kills_per_cycle:
                logger.warning(f"[TitanStateSync] Max kills per cycle reached ({kills_this_cycle})")
                break

    def _retry_pending_kills(self):
        """Reintenta KILLs pendientes que fallaron."""
        pending = self._queue.get_pending_kills()

        if not pending:
            return

        logger.info(f"[TitanStateSync] Retrying {len(pending)} pending kills")

        for cue_id in list(pending)[:self.config.max_kills_per_cycle]:
            # Enviar KILL directo (no encolar, ya estaba en pending)
            success = self._transport.send_kill(cue_id)

            if success:
                self._queue.clear_pending_kill(cue_id)
                self.stats.pending_resolved += 1
                logger.info(f"[TitanStateSync] Pending kill resolved: C{cue_id}")
            else:
                logger.warning(f"[TitanStateSync] Pending kill still failing: C{cue_id}")

    # ===== API PUBLICA =====

    def force_sync(self) -> Dict[str, Any]:
        """
        Fuerza una sincronizacion inmediata.

        Returns:
            Dict con resultado del sync
        """
        self._poll_titan_state()

        return {
            "titan_active": list(self._last_titan_active),
            "local_active": list(self._get_local_state()),
            "orphans_detected": self.stats.orphans_detected,
            "orphans_killed": self.stats.orphans_killed,
        }

    def get_titan_active(self) -> Set[int]:
        """Retorna cues activos segun ultimo poll de Titan."""
        with self._titan_lock:
            return self._last_titan_active.copy()

    def get_orphans(self) -> Set[int]:
        """Retorna cues huerfanos actualmente detectados."""
        return set(self._orphan_first_seen.keys())

    def kill_orphan_now(self, cue_id: int) -> bool:
        """
        Mata un huerfano inmediatamente (sin grace period).

        Args:
            cue_id: ID del cue huerfano

        Returns:
            bool: True si se encolo el KILL
        """
        if cue_id in self._orphan_first_seen:
            del self._orphan_first_seen[cue_id]

        return self._queue.kill(cue_id, priority_boost=True)

    def kill_all_orphans_now(self) -> int:
        """
        Mata todos los huerfanos inmediatamente.

        Returns:
            int: Numero de KILLs encolados
        """
        orphans = list(self._orphan_first_seen.keys())
        self._orphan_first_seen.clear()

        count = 0
        for cue_id in orphans:
            if self._queue.kill(cue_id, priority_boost=True):
                count += 1

        logger.info(f"[TitanStateSync] Killed all orphans: {count}")
        return count

    def set_local_active_callback(self, callback: Callable[[], Set[int]]):
        """
        Configura callback para obtener cues activos locales.

        Args:
            callback: Funcion que retorna Set[int] de cues activos
        """
        self._get_local_active = callback

    def set_user_number_offset(self, offset: int):
        """
        Configura offset de mapeo de cues.

        Args:
            offset: Nuevo offset
        """
        self._user_number_offset = offset
        logger.info(f"[TitanStateSync] Offset updated: {offset}")

    def get_stats(self) -> Dict[str, Any]:
        """Retorna estadisticas del sync."""
        return {
            "state": self._state.value,
            "polls_total": self.stats.polls_total,
            "polls_ok": self.stats.polls_ok,
            "polls_failed": self.stats.polls_failed,
            "orphans_detected": self.stats.orphans_detected,
            "orphans_killed": self.stats.orphans_killed,
            "pending_resolved": self.stats.pending_resolved,
            "last_poll_ts": self.stats.last_poll_ts,
            "last_error": self.stats.last_error,
            "titan_active_count": self.stats.titan_active_count,
            "local_active_count": self.stats.local_active_count,
            "sync_delta": self.stats.sync_delta,
            "current_orphans": list(self._orphan_first_seen.keys()),
            "poll_interval_s": self.config.poll_interval_s,
        }

    def __del__(self):
        try:
            self.stop()
        except:
            pass


__all__ = ["TitanStateSync", "SyncConfig", "SyncStats", "SyncState"]
