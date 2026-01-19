# ============================================================================
# core/transport - TITAN HTTP TRANSPORT SYSTEM
# ============================================================================
# Sistema profesional de transporte HTTP para Avolites Titan
#
# Componentes:
# - TitanTransport: Envio HTTP con reintentos
# - TitanQueue: Cola asincrona con prioridad KILL > FIRE
# - TitanStateSync: Watchdog de sincronizacion de estado
# ============================================================================

from .titan_transport import (
    TitanTransport,
    TransportConfig,
    TransportStats,
    TransportResult,
)

from .titan_queue import (
    TitanQueue,
    QueueConfig,
    QueueStats,
    QueueState,
    TaskType,
)

from .titan_sync import (
    TitanStateSync,
    SyncConfig,
    SyncStats,
    SyncState,
)


__all__ = [
    # Transport
    "TitanTransport",
    "TransportConfig",
    "TransportStats",
    "TransportResult",
    # Queue
    "TitanQueue",
    "QueueConfig",
    "QueueStats",
    "QueueState",
    "TaskType",
    # Sync
    "TitanStateSync",
    "SyncConfig",
    "SyncStats",
    "SyncState",
]
