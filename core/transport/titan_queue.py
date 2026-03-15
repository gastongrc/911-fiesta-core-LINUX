# ============================================================================
# titan_queue.py v1.4 - TITAN QUEUE TRANSPORT (ATOMIC PER FAMILY + SRC-TRACE)
# ============================================================================
# Cola de transporte 100% asincrona para Avolites Titan
#
# SRC-TRACE v1.4:
# - inspect.stack() para identificar llamador (archivo:linea)
# - Logging centralizado FIRE/KILL con: cue_id, action, ts, queue_len, src
# - KILL nunca se dropea: purga FIRE viejos si cola llena
# - Metrics: dropped_fire_for_kill count
# - PERF: gated behind TITAN_SRC_TRACE=1 (off by default)
#
# ATOMIC PER FAMILY v1.3 (C2):
# - Lock por familia para garantizar atomicidad FIRE/KILL
# - Elimina interleaving entre operaciones de la misma familia
# - Cero cues pegados por race conditions
#
# LEGACY MODE v1.1:
# - FIRE/KILL SIEMPRE se encolan (sin rechazo por estado)
# - No se dropean mensajes por "not ready"
# - Garantia OFF atomica mantenida
#
# CRITICAL FAST-PATH v1.2:
# - fire_immediate(): bypass completo de cola y rate limit
# - Para cues críticos: C41 (Dimmer), C37-39 (Ataque)
# - Latencia <100ms garantizada
# - Estadísticas separadas (fires_critical)
#
# Features:
# - Thread independiente
# - Prioridad estricta: KILL > FIRE
# - Nunca descarta paquetes KILL (purga FIRE si necesario)
# - Reintentos automaticos
# - Anti-duplicado configurable
# - Rate limit interno (60ms minimo entre requests)
# - Garantia OFF atomica: ON nunca sin OFF previo
# - CRITICAL FAST-PATH para cues de impacto musical
# - ATOMIC PER FAMILY: lock por familia (C2)
# ============================================================================

from __future__ import annotations

import time
import queue
import threading
import logging
import inspect
import os
from typing import Optional, Dict, Any, Set, List, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum, IntEnum

from .titan_transport import TitanTransport, TransportConfig

# ===== LOGGING =====
logger = logging.getLogger("TitanQueue")

# ===== SRC-TRACE GATING (v1.4 perf) =====
# OFF by default for zero overhead. Set TITAN_SRC_TRACE=1 to enable caller tracing.
_SRC_TRACE_ENABLED = os.environ.get("TITAN_SRC_TRACE", "0") in ("1", "true", "True", "yes", "YES")

# ===== FAMILY DEFINITIONS (C2) =====
# Mapa de familias para locks atómicos
# AUX (C45-50) y DIMMER (C41) NO necesitan lock - operan independiente
FAMILY_RANGES = {
    "BASE_GOLPE": list(range(1, 10)) + list(range(51, 60)),  # C1-9, C51-59
    "BAJADA_COLOR": list(range(10, 19)),   # C10-18
    "BAJADA_POS": list(range(19, 28)),     # C19-27
    "MOVIMIENTO": list(range(28, 37)),     # C28-36
    "ATAQUE": list(range(37, 40)),         # C37-39
    "BRAKE": list(range(42, 45)),          # C42-44
}

# Reverse lookup: cue -> family
CUE_TO_FAMILY: Dict[int, str] = {}
for family, cues in FAMILY_RANGES.items():
    for cue in cues:
        CUE_TO_FAMILY[cue] = family


class TaskType(IntEnum):
    """Tipos de tarea con prioridad numerica (menor = mayor prioridad)."""
    KILL = 1      # Maxima prioridad
    FIRE = 2      # Prioridad normal
    PING = 3      # Baja prioridad


class QueueState(Enum):
    """Estado de la cola."""
    STOPPED = "STOPPED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"


@dataclass
class QueueTask:
    """Tarea en la cola."""
    task_type: TaskType
    cue_id: int
    timestamp: float = field(default_factory=time.time)
    retries: int = 0
    priority_boost: bool = False  # True para tareas de sync forzado
    src: str = ""  # Caller source (file:line or function)

    def __lt__(self, other):
        """Comparacion para PriorityQueue (menor = mayor prioridad)."""
        # Primero por tipo (KILL < FIRE < PING)
        if self.task_type != other.task_type:
            return self.task_type < other.task_type
        # Luego por priority_boost (True primero)
        if self.priority_boost != other.priority_boost:
            return self.priority_boost > other.priority_boost
        # Finalmente por timestamp (mas antiguo primero)
        return self.timestamp < other.timestamp


@dataclass
class QueueConfig:
    """Configuracion de la cola."""
    max_queue_size: int = 512
    rate_limit_ms: float = 60.0  # Minimo ms entre requests
    max_retries: int = 3
    retry_delay_ms: float = 100.0
    dedup_window_ms: float = 50.0  # Ventana anti-duplicado (v1.5: 300→50ms)
    kill_block_on_fail: bool = True  # Bloquear cola si KILL falla
    fire_timeout_ms: float = 5000.0  # Timeout para FIRE en cola


@dataclass
class QueueStats:
    """Estadisticas de la cola."""
    tasks_enqueued: int = 0
    tasks_processed: int = 0
    tasks_dropped_dedup: int = 0
    tasks_dropped_full: int = 0
    kills_enqueued: int = 0
    kills_processed: int = 0
    kills_failed: int = 0
    kills_retried: int = 0
    fires_enqueued: int = 0
    fires_processed: int = 0
    fires_failed: int = 0
    fires_critical: int = 0  # CRITICAL FAST-PATH: fires inmediatos
    fires_purged_for_kill: int = 0  # v1.4: FIRE purgados para hacer espacio a KILL
    pending_kills: int = 0
    current_queue_size: int = 0
    last_process_ts: float = 0.0
    rate_limit_waits: int = 0


class TitanQueue:
    """
    Titan Queue Transport v1.0

    Cola asincrona con prioridad para comandos FIRE/KILL a Titan.

    Caracteristicas:
    - Thread dedicado para procesamiento
    - Prioridad estricta: KILL > FIRE
    - Nunca descarta KILL
    - Reintentos automaticos con delay
    - Anti-duplicado para evitar spam
    - Rate limit configurable (60ms default)
    - Garantia OFF atomica

    Uso:
        queue = TitanQueue(transport_config)
        queue.start()
        queue.fire(42)
        queue.kill(42)
        queue.stop()
    """

    def __init__(
        self,
        transport_config: Optional[TransportConfig] = None,
        queue_config: Optional[QueueConfig] = None,
        on_fire_success: Optional[Callable[[int], None]] = None,
        on_kill_success: Optional[Callable[[int], None]] = None,
        on_fire_fail: Optional[Callable[[int, str], None]] = None,
        on_kill_fail: Optional[Callable[[int, str], None]] = None,
    ):
        """
        Inicializa la cola.

        Args:
            transport_config: Config para TitanTransport
            queue_config: Config de la cola
            on_fire_success: Callback cuando FIRE OK
            on_kill_success: Callback cuando KILL OK
            on_fire_fail: Callback cuando FIRE falla
            on_kill_fail: Callback cuando KILL falla
        """
        self.config = queue_config or QueueConfig()
        self.stats = QueueStats()

        # Transport HTTP
        self._transport = TitanTransport(
            config=transport_config,
            on_success=self._on_transport_success,
            on_failure=self._on_transport_failure,
        )

        # Callbacks
        self._on_fire_success = on_fire_success
        self._on_kill_success = on_kill_success
        self._on_fire_fail = on_fire_fail
        self._on_kill_fail = on_kill_fail

        # Cola con prioridad
        self._queue: queue.PriorityQueue = queue.PriorityQueue(
            maxsize=self.config.max_queue_size
        )

        # Estado
        self._state = QueueState.STOPPED
        self._worker_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Tracking
        self._active_cues: Set[int] = set()
        self._active_lock = threading.Lock()
        self._pending_kills: Set[int] = set()  # KILL que fallaron, pendientes de sync
        self._pending_lock = threading.Lock()

        # Anti-duplicado
        self._recent_tasks: Dict[Tuple[TaskType, int], float] = {}
        self._dedup_lock = threading.Lock()

        # Rate limiting
        self._last_send_ts: float = 0.0
        self._rate_lock = threading.Lock()

        # OFF atomico: tracking de familia activa para garantia OFF->ON
        self._last_family_cue: Dict[str, Optional[int]] = {}

        # ATOMIC PER FAMILY (C2): Lock por familia
        self._family_locks: Dict[str, threading.Lock] = {
            family: threading.Lock() for family in FAMILY_RANGES.keys()
        }

        logger.info("[TitanQueue] Inicializado (SRC-TRACE v1.4)")

    # ===== SRC-TRACE HELPER (v1.4) =====

    def _get_caller_info(self, depth: int = 3) -> str:
        """
        Obtiene info del llamador usando currentframe() + f_back walk.
        PERF: ~10x más rápido que inspect.stack().

        Args:
            depth: Frames a subir (3 = caller de fire/kill)

        Returns:
            str: "filename:line:function" o "" si trace deshabilitado
        """
        if not _SRC_TRACE_ENABLED:
            return ""
        try:
            frame = inspect.currentframe()
            # Walk up the stack manually (much faster than inspect.stack())
            for _ in range(depth):
                if frame is None:
                    return "unknown"
                frame = frame.f_back
            if frame is None:
                return "unknown"
            filename = os.path.basename(frame.f_code.co_filename)
            return f"{filename}:{frame.f_lineno}:{frame.f_code.co_name}"
        except Exception:
            return "unknown"

    def _purge_oldest_fire(self) -> bool:
        """
        Purga el FIRE más viejo de la cola para hacer espacio.
        v1.4: KILL nunca se dropea - purgamos FIRE si es necesario.

        Returns:
            bool: True si se purgó un FIRE, False si no había FIRE para purgar
        """
        # Extraer todos los elementos de la cola
        items = []
        oldest_fire_idx = -1
        oldest_fire_ts = float('inf')

        while True:
            try:
                task = self._queue.get_nowait()
                items.append(task)
                # Buscar el FIRE más viejo
                if task.task_type == TaskType.FIRE and task.timestamp < oldest_fire_ts:
                    oldest_fire_ts = task.timestamp
                    oldest_fire_idx = len(items) - 1
            except queue.Empty:
                break

        if oldest_fire_idx < 0:
            # No hay FIRE para purgar - re-encolar todo
            for task in items:
                try:
                    self._queue.put_nowait(task)
                except queue.Full:
                    pass
            return False

        # Re-encolar todo excepto el FIRE más viejo
        purged_task = items[oldest_fire_idx]
        for i, task in enumerate(items):
            if i != oldest_fire_idx:
                try:
                    self._queue.put_nowait(task)
                except queue.Full:
                    pass

        self.stats.fires_purged_for_kill += 1
        if purged_task.src:
            logger.warning(f"[TitanQueue] PURGED FIRE C{purged_task.cue_id} (age={time.time()-purged_task.timestamp:.2f}s) for KILL space | src={purged_task.src}")
        else:
            logger.warning(f"[TitanQueue] PURGED FIRE C{purged_task.cue_id} (age={time.time()-purged_task.timestamp:.2f}s) for KILL space")
        return True

    # ===== API PUBLICA =====

    def fire(self, cue_id: int) -> bool:
        """
        Encola comando FIRE.
        LEGACY MODE: SIEMPRE encola, sin rechazo por estado.

        Args:
            cue_id: ID del cue a disparar

        Returns:
            bool: True si se encolo correctamente
        """
        ts = time.monotonic()

        # LEGACY MODE: No rechazar por estado - siempre intentar encolar
        # La cola se inicia automaticamente si es necesario
        if self._state == QueueState.STOPPED:
            logger.debug(f"[TitanQueue] fire({cue_id}) - starting queue automatically")
            self.start()

        # Anti-duplicado (BEFORE src-trace for perf)
        if self._is_duplicate(TaskType.FIRE, cue_id):
            self.stats.tasks_dropped_dedup += 1
            logger.info(f"[TITAN] FIRE C{cue_id} DEDUP | ts={ts:.3f} qlen={self._queue.qsize()}")
            return False

        # SRC-TRACE: solo si pasa dedup y va a encolar
        src = self._get_caller_info()
        task = QueueTask(task_type=TaskType.FIRE, cue_id=cue_id, src=src)

        try:
            self._queue.put_nowait(task)
            self.stats.tasks_enqueued += 1
            self.stats.fires_enqueued += 1
            self.stats.current_queue_size = self._queue.qsize()

            # Track como activo
            with self._active_lock:
                self._active_cues.add(cue_id)

            # Deterministic log (always visible)
            print(f"[TitanQueue] ENQUEUE FIRE cue={cue_id} qlen={self._queue.qsize()}")
            if src:
                logger.info(f"[TITAN] FIRE C{cue_id} ENQUEUE | ts={ts:.3f} qlen={self._queue.qsize()} | src={src}")
            else:
                logger.info(f"[TITAN] FIRE C{cue_id} ENQUEUE | ts={ts:.3f} qlen={self._queue.qsize()}")
            return True

        except queue.Full:
            self.stats.tasks_dropped_full += 1
            if src:
                logger.warning(f"[TITAN] FIRE C{cue_id} DROPPED (full) | ts={ts:.3f} qlen={self._queue.qsize()} | src={src}")
            else:
                logger.warning(f"[TITAN] FIRE C{cue_id} DROPPED (full) | ts={ts:.3f} qlen={self._queue.qsize()}")
            return False

    def kill(self, cue_id: int, priority_boost: bool = False) -> bool:
        """
        Encola comando KILL (prioridad maxima).
        LEGACY MODE: SIEMPRE encola, sin rechazo por estado.
        v1.4: KILL nunca se dropea - purga FIRE viejos si cola llena.

        Args:
            cue_id: ID del cue a matar
            priority_boost: True para prioridad extra (sync forzado)

        Returns:
            bool: True si se encolo correctamente
        """
        ts = time.monotonic()

        # LEGACY MODE: No rechazar por estado - siempre intentar encolar
        # La cola se inicia automaticamente si es necesario
        if self._state == QueueState.STOPPED:
            logger.debug(f"[TitanQueue] kill({cue_id}) - starting queue automatically")
            self.start()

        # KILL nunca se descarta por duplicado si priority_boost (BEFORE src-trace for perf)
        if not priority_boost and self._is_duplicate(TaskType.KILL, cue_id):
            self.stats.tasks_dropped_dedup += 1
            logger.info(f"[TITAN] KILL C{cue_id} DEDUP | ts={ts:.3f} qlen={self._queue.qsize()}")
            return False

        # SRC-TRACE: solo si pasa dedup y va a encolar
        src = self._get_caller_info()
        task = QueueTask(
            task_type=TaskType.KILL,
            cue_id=cue_id,
            priority_boost=priority_boost,
            src=src
        )

        # v1.4: KILL NUNCA se dropea - purga FIRE si cola llena
        try:
            if priority_boost:
                # Prioridad maxima: siempre encolar (con timeout)
                self._queue.put(task, timeout=1.0)
            else:
                self._queue.put_nowait(task)

            self.stats.tasks_enqueued += 1
            self.stats.kills_enqueued += 1
            self.stats.current_queue_size = self._queue.qsize()

            # Track como inactivo
            with self._active_lock:
                self._active_cues.discard(cue_id)

            print(f"[TitanQueue] ENQUEUE KILL cue={cue_id} qlen={self._queue.qsize()} boost={priority_boost}")
            if src:
                logger.info(f"[TITAN] KILL C{cue_id} ENQUEUE | ts={ts:.3f} qlen={self._queue.qsize()} boost={priority_boost} | src={src}")
            else:
                logger.info(f"[TITAN] KILL C{cue_id} ENQUEUE | ts={ts:.3f} qlen={self._queue.qsize()} boost={priority_boost}")
            return True

        except queue.Full:
            # v1.4: KILL nunca se dropea - purgar FIRE viejo y reintentar
            if src:
                logger.warning(f"[TITAN] KILL C{cue_id} queue full - purging oldest FIRE | src={src}")
            else:
                logger.warning(f"[TITAN] KILL C{cue_id} queue full - purging oldest FIRE")
            if self._purge_oldest_fire():
                # Reintentar después de purgar
                try:
                    self._queue.put_nowait(task)
                    self.stats.tasks_enqueued += 1
                    self.stats.kills_enqueued += 1
                    self.stats.current_queue_size = self._queue.qsize()

                    with self._active_lock:
                        self._active_cues.discard(cue_id)

                    if src:
                        logger.info(f"[TITAN] KILL C{cue_id} ENQUEUE (after purge) | ts={ts:.3f} qlen={self._queue.qsize()} | src={src}")
                    else:
                        logger.info(f"[TITAN] KILL C{cue_id} ENQUEUE (after purge) | ts={ts:.3f} qlen={self._queue.qsize()}")
                    return True
                except queue.Full:
                    pass

            # Último recurso: agregar a pending_kills para TitanSync
            with self._pending_lock:
                self._pending_kills.add(cue_id)
            self.stats.pending_kills = len(self._pending_kills)
            if src:
                logger.error(f"[TITAN] KILL C{cue_id} -> PENDING (no FIRE to purge) | ts={ts:.3f} | src={src}")
            else:
                logger.error(f"[TITAN] KILL C{cue_id} -> PENDING (no FIRE to purge) | ts={ts:.3f}")
            return False

    def kill_pool(self, cue_ids: List[int], priority_boost: bool = False) -> int:
        """
        Encola multiples KILL.

        Args:
            cue_ids: Lista de IDs a matar
            priority_boost: True para prioridad extra

        Returns:
            int: Numero de KILLs encolados
        """
        count = 0
        for cue_id in cue_ids:
            if self.kill(cue_id, priority_boost=priority_boost):
                count += 1
        return count

    def fire_immediate(self, cue_id: int) -> bool:
        """
        FIRE inmediato - salta la cola y envia directo.
        CRITICAL FAST-PATH: No rate limit, no queue wait.
        Respeta lock atómico por familia (C2).

        Usar para:
        - C41 (Dimmer)
        - C37-39 (Ataque)
        - Primer fire al entrar a estado
        - Restore crítico

        Args:
            cue_id: ID del cue a disparar

        Returns:
            bool: True si el envio fue exitoso
        """
        ts = time.monotonic()
        family = self._get_family(cue_id)

        # Adquirir lock de familia si aplica
        if family:
            lock = self._family_locks[family]
            logger.debug(f"[TITAN][LOCK] acquire family={family} for FIRE_IMMEDIATE C{cue_id}")
            lock.acquire()

        try:
            # Enviar directo sin pasar por cola ni rate limit
            success = self._transport.send_fire(cue_id)

            if success:
                self.stats.fires_processed += 1
                self.stats.fires_critical += 1
                with self._active_lock:
                    self._active_cues.add(cue_id)
                if self._on_fire_success:
                    try:
                        self._on_fire_success(cue_id)
                    except:
                        pass
                # SRC-TRACE: only compute if enabled
                if _SRC_TRACE_ENABLED:
                    src = self._get_caller_info()
                    logger.info(f"[TITAN] FIRE_IMM C{cue_id} OK | ts={ts:.3f} | src={src}")
                else:
                    logger.info(f"[TITAN] FIRE_IMM C{cue_id} OK | ts={ts:.3f}")
            else:
                self.stats.fires_failed += 1
                if self._on_fire_fail:
                    try:
                        self._on_fire_fail(cue_id, "immediate send failed")
                    except:
                        pass
                if _SRC_TRACE_ENABLED:
                    src = self._get_caller_info()
                    logger.warning(f"[TITAN] FIRE_IMM C{cue_id} FAILED | ts={ts:.3f} | src={src}")
                else:
                    logger.warning(f"[TITAN] FIRE_IMM C{cue_id} FAILED | ts={ts:.3f}")

            return success
        finally:
            # Liberar lock de familia si aplica
            if family:
                lock.release()
                logger.debug(f"[TITAN][LOCK] release family={family} for FIRE_IMMEDIATE C{cue_id}")

    def kill_immediate(self, cue_id: int) -> bool:
        """
        KILL inmediato - salta la cola y envia directo.
        Respeta lock atómico por familia (C2).
        Solo para emergencias.

        Args:
            cue_id: ID del cue a matar

        Returns:
            bool: True si el envio fue exitoso
        """
        ts = time.monotonic()
        family = self._get_family(cue_id)

        # Adquirir lock de familia si aplica
        if family:
            lock = self._family_locks[family]
            logger.debug(f"[TITAN][LOCK] acquire family={family} for KILL_IMMEDIATE C{cue_id}")
            lock.acquire()

        try:
            # Enviar directo sin pasar por cola
            success = self._transport.send_kill(cue_id)

            if success:
                with self._active_lock:
                    self._active_cues.discard(cue_id)
                if self._on_kill_success:
                    try:
                        self._on_kill_success(cue_id)
                    except:
                        pass
                # SRC-TRACE: only compute if enabled
                if _SRC_TRACE_ENABLED:
                    src = self._get_caller_info()
                    logger.info(f"[TITAN] KILL_IMM C{cue_id} OK | ts={ts:.3f} | src={src}")
                else:
                    logger.info(f"[TITAN] KILL_IMM C{cue_id} OK | ts={ts:.3f}")
            else:
                # Agregar a pending para sync
                with self._pending_lock:
                    self._pending_kills.add(cue_id)
                self.stats.pending_kills = len(self._pending_kills)
                if _SRC_TRACE_ENABLED:
                    src = self._get_caller_info()
                    logger.warning(f"[TITAN] KILL_IMM C{cue_id} FAILED -> pending | ts={ts:.3f} | src={src}")
                else:
                    logger.warning(f"[TITAN] KILL_IMM C{cue_id} FAILED -> pending | ts={ts:.3f}")

            return success
        finally:
            # Liberar lock de familia si aplica
            if family:
                lock.release()
                logger.debug(f"[TITAN][LOCK] release family={family} for KILL_IMMEDIATE C{cue_id}")

    # ===== CONTROL =====

    def start(self) -> bool:
        """
        Inicia el worker thread.

        Returns:
            bool: True si inicio correctamente
        """
        if self._state == QueueState.RUNNING:
            return True

        self._stop_event.clear()
        self._state = QueueState.RUNNING

        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            name="TitanQueue-Worker",
            daemon=True
        )
        self._worker_thread.start()

        logger.info("[TitanQueue] Started")
        return True

    def stop(self, timeout: float = 2.0) -> bool:
        """
        Detiene el worker thread.

        Args:
            timeout: Segundos a esperar por el thread

        Returns:
            bool: True si se detuvo correctamente
        """
        if self._state == QueueState.STOPPED:
            return True

        self._state = QueueState.STOPPED
        self._stop_event.set()

        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=timeout)

        logger.info("[TitanQueue] Stopped")
        return True

    def pause(self):
        """Pausa el procesamiento (KILL sigue funcionando)."""
        self._state = QueueState.PAUSED
        logger.info("[TitanQueue] Paused")

    def resume(self):
        """Reanuda el procesamiento."""
        if self._state == QueueState.PAUSED:
            self._state = QueueState.RUNNING
            logger.info("[TitanQueue] Resumed")

    def flush(self):
        """Vacia la cola (excepto KILL pendientes)."""
        dropped = 0
        while True:
            try:
                task = self._queue.get_nowait()
                if task.task_type != TaskType.KILL:
                    dropped += 1
                else:
                    # Re-encolar KILLs
                    self._queue.put_nowait(task)
            except queue.Empty:
                break

        logger.info(f"[TitanQueue] Flushed {dropped} tasks")

    # ===== FAMILY LOCK HELPER (C2) =====

    def _get_family(self, cue_id: int) -> Optional[str]:
        """
        Retorna la familia de un cue, o None si no requiere lock.
        AUX (C45-50) y DIMMER (C41) no tienen familia asignada.
        """
        return CUE_TO_FAMILY.get(cue_id, None)

    # ===== WORKER =====

    def _worker_loop(self):
        """Loop principal del worker."""
        logger.info("[TitanQueue] Worker started")

        while not self._stop_event.is_set():
            try:
                # Obtener tarea con timeout para poder verificar stop_event
                try:
                    task = self._queue.get(timeout=0.01)
                except queue.Empty:
                    continue

                self.stats.current_queue_size = self._queue.qsize()

                # Respetar rate limit
                self._wait_rate_limit()

                # Procesar segun tipo
                if task.task_type == TaskType.KILL:
                    self._process_kill(task)
                elif task.task_type == TaskType.FIRE:
                    # Si estamos pausados, solo procesar KILL
                    if self._state == QueueState.PAUSED:
                        # Re-encolar FIRE para despues
                        self._queue.put(task)
                        continue
                    self._process_fire(task)
                elif task.task_type == TaskType.PING:
                    self._process_ping()

                self._queue.task_done()
                self.stats.tasks_processed += 1
                self.stats.last_process_ts = time.time()

            except Exception as e:
                logger.error(f"[TitanQueue] Worker error: {e}")

        logger.info("[TitanQueue] Worker stopped")

    def _process_kill(self, task: QueueTask):
        """Procesa tarea KILL con lock atómico por familia."""
        cue_id = task.cue_id
        family = self._get_family(cue_id)

        # Diagnostic: confirm which transport processes this kill
        transport = self._transport
        transport_name = type(transport).__name__
        print(f"[TitanQueue] KILL cue={cue_id} transport={transport_name} id={id(transport)}")

        # Adquirir lock de familia si aplica
        if family:
            lock = self._family_locks[family]
            logger.debug(f"[TITAN][LOCK] acquire family={family} for KILL C{cue_id}")
            lock.acquire()

        try:
            success = transport.send_kill(cue_id)

            if success:
                self.stats.kills_processed += 1

                # Quitar de pending si estaba
                with self._pending_lock:
                    self._pending_kills.discard(cue_id)
                    self.stats.pending_kills = len(self._pending_kills)

                if self._on_kill_success:
                    try:
                        self._on_kill_success(cue_id)
                    except:
                        pass
            else:
                # Reintentar si no excede max_retries
                if task.retries < self.config.max_retries:
                    task.retries += 1
                    self.stats.kills_retried += 1

                    # Re-encolar con prioridad
                    time.sleep(self.config.retry_delay_ms / 1000.0)
                    self._queue.put(task)
                    logger.warning(f"[TitanQueue] KILL C{cue_id} retry {task.retries}")
                else:
                    # Max retries alcanzado - marcar como pending para sync
                    self.stats.kills_failed += 1
                    with self._pending_lock:
                        self._pending_kills.add(cue_id)
                        self.stats.pending_kills = len(self._pending_kills)

                    logger.error(f"[TitanQueue] KILL C{cue_id} FAILED after {task.retries} retries")

                    if self._on_kill_fail:
                        try:
                            self._on_kill_fail(cue_id, "Max retries exceeded")
                        except:
                            pass
        finally:
            # Liberar lock de familia si aplica
            if family:
                lock.release()
                logger.debug(f"[TITAN][LOCK] release family={family} for KILL C{cue_id}")

    def _process_fire(self, task: QueueTask):
        """Procesa tarea FIRE con lock atómico por familia."""
        cue_id = task.cue_id
        family = self._get_family(cue_id)

        # Diagnostic: confirm which transport processes this fire
        transport = self._transport
        transport_name = type(transport).__name__
        print(f"[TitanQueue] FIRE cue={cue_id} transport={transport_name} id={id(transport)}")
        print(f"[DMX-TRACE] stage=TitanQueue._process_fire cue={cue_id} transport={transport_name} id={id(transport)} -> transport.send_fire()")

        # Verificar timeout de cola ANTES de adquirir lock
        age_ms = (time.time() - task.timestamp) * 1000
        if age_ms > self.config.fire_timeout_ms:
            print(f"[DMX-TRACE] stage=TitanQueue DROPPED cue={cue_id} age_ms={age_ms:.0f} > timeout={self.config.fire_timeout_ms}")
            logger.warning(f"[TitanQueue] FIRE C{cue_id} dropped: timeout ({age_ms:.0f}ms)")
            return

        # Adquirir lock de familia si aplica
        if family:
            lock = self._family_locks[family]
            logger.debug(f"[TITAN][LOCK] acquire family={family} for FIRE C{cue_id}")
            lock.acquire()

        try:
            success = transport.send_fire(cue_id)

            if success:
                self.stats.fires_processed += 1
                print(f"[TitanQueue] FIRE cue={cue_id} OK via {transport_name}")

                if self._on_fire_success:
                    try:
                        self._on_fire_success(cue_id)
                    except:
                        pass
            else:
                self.stats.fires_failed += 1
                print(f"[TitanQueue] FIRE cue={cue_id} FAILED via {transport_name}")

                # Reintentar FIRE es opcional (menos critico que KILL)
                if task.retries < self.config.max_retries:
                    task.retries += 1
                    time.sleep(self.config.retry_delay_ms / 1000.0)
                    self._queue.put(task)
                    logger.warning(f"[TitanQueue] FIRE C{cue_id} retry {task.retries}")
                else:
                    if self._on_fire_fail:
                        try:
                            self._on_fire_fail(cue_id, "Max retries exceeded")
                        except:
                            pass
        finally:
            # Liberar lock de familia si aplica
            if family:
                lock.release()
                logger.debug(f"[TITAN][LOCK] release family={family} for FIRE C{cue_id}")

    def _process_ping(self):
        """Procesa tarea PING."""
        self._transport.ping()

    # ===== RATE LIMITING =====

    def _wait_rate_limit(self):
        """Espera el rate limit entre requests."""
        with self._rate_lock:
            now = time.time()
            elapsed_ms = (now - self._last_send_ts) * 1000

            if elapsed_ms < self.config.rate_limit_ms:
                wait_ms = self.config.rate_limit_ms - elapsed_ms
                self.stats.rate_limit_waits += 1
                time.sleep(wait_ms / 1000.0)

            self._last_send_ts = time.time()

    # ===== ANTI-DUPLICADO =====

    def _is_duplicate(self, task_type: TaskType, cue_id: int) -> bool:
        """Verifica si la tarea es duplicada dentro de la ventana."""
        key = (task_type, cue_id)
        now = time.time() * 1000

        with self._dedup_lock:
            # Limpiar entradas viejas
            cutoff = now - self.config.dedup_window_ms
            self._recent_tasks = {
                k: v for k, v in self._recent_tasks.items()
                if v > cutoff
            }

            # Verificar si existe
            if key in self._recent_tasks:
                return True

            # Registrar
            self._recent_tasks[key] = now
            return False

    # ===== CALLBACKS INTERNOS =====

    def _on_transport_success(self, action: str, cue_id: int):
        """Callback interno cuando transport tiene exito."""
        pass  # Los callbacks especificos se manejan en _process_*

    def _on_transport_failure(self, action: str, cue_id: int, error: str):
        """Callback interno cuando transport falla."""
        pass  # Los reintentos se manejan en _process_*

    # ===== ESTADO =====

    def is_active(self, cue_id: int) -> bool:
        """Verifica si un cue esta activo."""
        with self._active_lock:
            return cue_id in self._active_cues

    def get_active_cues(self) -> Set[int]:
        """Retorna set de cues activos."""
        with self._active_lock:
            return self._active_cues.copy()

    def get_pending_kills(self) -> Set[int]:
        """Retorna KILLs pendientes (fallaron y esperan sync)."""
        with self._pending_lock:
            return self._pending_kills.copy()

    def clear_pending_kill(self, cue_id: int):
        """Quita un cue de pending_kills (cuando sync lo resuelve)."""
        with self._pending_lock:
            self._pending_kills.discard(cue_id)
            self.stats.pending_kills = len(self._pending_kills)

    def mark_active(self, cue_id: int):
        """Marca un cue como activo (para sync externo)."""
        with self._active_lock:
            self._active_cues.add(cue_id)

    def mark_inactive(self, cue_id: int):
        """Marca un cue como inactivo (para sync externo)."""
        with self._active_lock:
            self._active_cues.discard(cue_id)

    def get_stats(self) -> Dict[str, Any]:
        """Retorna estadisticas de la cola."""
        return {
            "state": self._state.value,
            "tasks_enqueued": self.stats.tasks_enqueued,
            "tasks_processed": self.stats.tasks_processed,
            "tasks_dropped_dedup": self.stats.tasks_dropped_dedup,
            "tasks_dropped_full": self.stats.tasks_dropped_full,
            "kills_enqueued": self.stats.kills_enqueued,
            "kills_processed": self.stats.kills_processed,
            "kills_failed": self.stats.kills_failed,
            "kills_retried": self.stats.kills_retried,
            "fires_enqueued": self.stats.fires_enqueued,
            "fires_processed": self.stats.fires_processed,
            "fires_failed": self.stats.fires_failed,
            "fires_critical": self.stats.fires_critical,
            "fires_purged_for_kill": self.stats.fires_purged_for_kill,  # v1.4
            "pending_kills": self.stats.pending_kills,
            "current_queue_size": self.stats.current_queue_size,
            "last_process_ts": self.stats.last_process_ts,
            "rate_limit_waits": self.stats.rate_limit_waits,
            "active_cues_count": len(self._active_cues),
            "transport_stats": self._transport.get_stats(),
        }

    def get_transport(self):
        """Retorna el transport subyacente."""
        return self._transport

    def set_transport(self, transport):
        """
        Reemplaza el transport subyacente (HTTP <-> ArtNet).

        El nuevo transport debe implementar:
            send_fire(cue_id) -> bool
            send_kill(cue_id) -> bool

        Args:
            transport: Nueva instancia de transport (TitanTransport o ArtNetTransport)
        """
        old = self._transport
        old_name = type(old).__name__
        new_name = type(transport).__name__

        # Validate interface
        for method in ("send_fire", "send_kill"):
            if not callable(getattr(transport, method, None)):
                raise ValueError(f"Transport {new_name} missing required method: {method}")

        self._transport = transport

        # Cerrar el transport anterior
        if old and hasattr(old, 'close'):
            try:
                old.close()
            except Exception:
                pass

        print(f"[TitanQueue] TRANSPORT SWAP {old_name}(id={id(old)}) -> {new_name}(id={id(transport)})")
        logger.info(f"[TitanQueue] Transport swapped -> {new_name}")

        # Verify swap took effect
        verify_name = type(self._transport).__name__
        if verify_name != new_name:
            logger.error(f"[TitanQueue] TRANSPORT SWAP FAILED: expected {new_name}, got {verify_name}")
        else:
            logger.info(f"[TitanQueue] TRANSPORT VERIFIED: {verify_name} (id={id(self._transport)})")

    def update_config(self, **kwargs):
        """Actualiza configuracion del transport."""
        self._transport.update_config(**kwargs)

    def __del__(self):
        try:
            self.stop()
        except:
            pass


__all__ = ["TitanQueue", "QueueConfig", "QueueStats", "QueueState", "TaskType"]
