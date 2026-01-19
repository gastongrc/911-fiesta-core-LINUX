"""
API Models - Pydantic Models for FASE 2
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum


# ==================== ENUMS ====================

class StateEnum(str, Enum):
    """Estado del sistema"""
    BAJADA = "BAJADA"
    BASE_GOLPE = "BASE_GOLPE"
    ATAQUE = "ATAQUE"
    BRAKE = "BRAKE"


class EnergyEnum(str, Enum):
    """Nivel de energía"""
    BAJA = "BAJA"
    MEDIA = "MEDIA"
    ALTA = "ALTA"


class ConnectionState(str, Enum):
    """Estado de conexión"""
    NOT_READY = "NOT_READY"
    READY = "READY"


class ConfigSection(str, Enum):
    """Secciones de configuración"""
    AUDIO = "audio"
    AVOLITES = "avolites"
    STATE = "state"
    MODULES = "modules"


# ==================== STATUS MODELS ====================

class AudioEngineStatus(BaseModel):
    """Estado del AudioEngine"""
    device: Optional[str] = None
    samplerate: int
    channels: int = 2
    running: bool
    buffer_size: Optional[int] = None


class AvolitesStatus(BaseModel):
    """Estado del AvolitesController"""
    connection_state: str
    is_connected: bool
    console_ip: str
    console_port: int
    last_error: Optional[str] = None
    active_cues_count: int


class CueEngineStatus(BaseModel):
    """Estado del CueEngine"""
    modules_active: int
    total_updates: int
    last_state: str
    running: bool


class SystemStatus(BaseModel):
    """Estado completo del sistema"""
    state: StateEnum
    energy: EnergyEnum
    state_locked: bool
    brake_active: bool
    uptime_seconds: float
    version: str
    audio: AudioEngineStatus
    avolites: AvolitesStatus
    cue_engine: CueEngineStatus


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    initialized: bool
    uptime: float


# ==================== ANALYZER MODELS ====================

class AnalyzerThresholds(BaseModel):
    """Thresholds de un analyzer"""
    low: Optional[float] = None
    medium: Optional[float] = None
    high: Optional[float] = None


class AnalyzerState(BaseModel):
    """Estado de un analyzer individual"""
    name: str
    type: str
    value: float
    thresholds: AnalyzerThresholds
    match: bool
    active: bool


class AnalyzersByState(BaseModel):
    """Analyzers organizados por estado"""
    BAJADA: List[AnalyzerState]
    BASE_GOLPE: List[AnalyzerState]
    ATAQUE: List[AnalyzerState]
    BRAKE: List[AnalyzerState]


class AnalyzerStats(BaseModel):
    """Estadísticas de analyzers"""
    total_count: int
    active_count: int
    matching_count: int
    by_state: Dict[str, int]


class EnergyState(BaseModel):
    """Estado del energy detector"""
    level: EnergyEnum
    score: float
    raw_value: float
    threshold_low: float
    threshold_high: float


class AnalyzersResponse(BaseModel):
    """Respuesta completa de analyzers"""
    analyzers: AnalyzersByState
    energy: EnergyState
    stats: AnalyzerStats


# ==================== CUE MODELS ====================

class CueFireRequest(BaseModel):
    """Request para disparar un cue"""
    cue_number: int = Field(..., ge=1, le=300, description="Número lógico del cue (1-300)")
    force: bool = Field(default=False, description="Si True, usa fire_cue_manual (bypass READY)")


class CueKillRequest(BaseModel):
    """Request para matar cues"""
    cue_numbers: List[int] = Field(..., min_length=1, description="Lista de números lógicos de cues")
    force: bool = Field(default=False, description="Si True, usa kill_cue_manual")


class CueFireResponse(BaseModel):
    """Respuesta de fire cue"""
    success: bool
    cue_number: int
    message: Optional[str] = None


class CueKillResponse(BaseModel):
    """Respuesta de kill cues"""
    success: bool
    killed_count: int
    cue_numbers: List[int]
    message: Optional[str] = None


class CueStatusResponse(BaseModel):
    """Estado del sistema de cues"""
    active_cues: List[int]
    cue_engine: CueEngineStatus


# ==================== NETWORK MODELS ====================

class NetworkInterface(BaseModel):
    """Información de una interfaz de red"""
    name: str
    display_name: str
    ips: List[str]
    is_up: bool


class NetworkInterfacesResponse(BaseModel):
    """Lista de interfaces de red"""
    interfaces: List[NetworkInterface]
    current_interface: Optional[str] = None


class NetworkSetInterfaceRequest(BaseModel):
    """Request para cambiar interfaz de red"""
    interface_name: str


class NetworkSetConsoleRequest(BaseModel):
    """Request para cambiar destino Avolites"""
    console_ip: str
    console_port: int = Field(default=4430, ge=1, le=65535)


class NetworkPingRequest(BaseModel):
    """Request para ping"""
    host: str
    timeout: float = Field(default=1.0, ge=0.1, le=10.0)


class NetworkPingResponse(BaseModel):
    """Respuesta de ping"""
    host: str
    reachable: bool
    latency_ms: Optional[float] = None


# ==================== CONFIG MODELS ====================

class ConfigResponse(BaseModel):
    """Respuesta de config"""
    section: ConfigSection
    data: Dict[str, Any]


class ConfigUpdateRequest(BaseModel):
    """Request para actualizar config"""
    data: Dict[str, Any]


# ==================== PRESET MODELS ====================

class PresetInfo(BaseModel):
    """Informacion de un preset"""
    name: str
    path: str
    size: int
    modified: float


class PresetListResponse(BaseModel):
    """Lista de presets"""
    presets: List[PresetInfo]
    count: int


class PresetSaveRequest(BaseModel):
    """Request para guardar preset"""
    filename: str
    overwrite: bool = Field(default=False)


class PresetSaveResponse(BaseModel):
    """Respuesta de guardar preset"""
    success: bool
    filename: str
    message: str


class PresetLoadRequest(BaseModel):
    """Request para cargar preset"""
    filename: str
    apply_network: bool = Field(default=True)
    apply_avolites: bool = Field(default=True)


class PresetLoadResponse(BaseModel):
    """Respuesta de cargar preset"""
    success: bool
    filename: str
    message: str
    applied_sections: List[Optional[str]]


# ==================== ERROR MODELS ====================

class ErrorResponse(BaseModel):
    """Respuesta de error"""
    detail: str
    error_code: Optional[str] = None
