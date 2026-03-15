# ============================================================================
# core/transport - TRANSPORT SYSTEM (HTTP + ART-NET DMX)
# ============================================================================
# Sistema profesional de transporte para Avolites Titan
#
# Componentes HTTP:
# - TitanTransport: Envio HTTP con reintentos
# - TitanQueue: Cola asincrona con prioridad KILL > FIRE
# - TitanStateSync: Watchdog de sincronizacion de estado
#
# Componentes Art-Net DMX:
# - DmxState: Consola DMX virtual (512 canales, estado persistente)
# - ArtNetEngine: Motor Art-Net (emisor continuo UDP, 40fps)
# - CueOutputAdapter: Adaptador CueEngine → DMX
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

from .dmx_state import (
    DmxState,
    DMX_CHANNELS,
    DMX_ON_VALUE,
    DMX_OFF_VALUE,
)

from .artnet_engine import (
    ArtNetEngine,
    build_artnet_dmx_packet,
    ARTNET_PORT,
)

from .cue_output_adapter import (
    CueOutputAdapter,
)


__all__ = [
    # Transport HTTP
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
    # DMX State
    "DmxState",
    "DMX_CHANNELS",
    "DMX_ON_VALUE",
    "DMX_OFF_VALUE",
    # Art-Net
    "ArtNetEngine",
    "build_artnet_dmx_packet",
    "ARTNET_PORT",
    # Adapter
    "CueOutputAdapter",
]
