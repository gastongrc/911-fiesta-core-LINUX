# core/calendar/calendar_state.py
"""
CalendarState v6.4 - Estado del calendario con datos de timeline.

El estado incluye:
- Clima actual (modo canónico)
- Fuente del cambio (MANUAL, AUTO, OVERRIDE)
- Timestamps de inicio y próximo cambio
- Información del bloque activo
- Permisos actuales derivados del clima
- Estado de override activo

v6.4 NUEVO: Soporte para bloques compuestos:
- base_mode: Modo canónico obligatorio
- actions: Lista de acciones paralelas (0-5)
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum


class CalendarSource(Enum):
    """Fuente del cambio de clima"""
    MANUAL = "MANUAL"     # Usuario usó GO
    AUTO = "AUTO"         # Resuelto por horario automáticamente
    OVERRIDE = "OVERRIDE" # Override temporal activo


# Acciones válidas para bloques compuestos (v6.4)
VALID_ACTIONS = [
    "audio_911",
    "vision_haze",
    "vision_dj",
    "vision_artista",
    "tracking_cam",
    "dj_detection",
    "cues_clima",
    "system_idle",
]

# Máximo de acciones por bloque
MAX_ACTIONS_PER_BLOCK = 5


@dataclass
class ScheduleBlock:
    """
    Bloque de horario activo (v6.4 con soporte para acciones).

    Un bloque puede tener:
    - base_mode: Modo canónico obligatorio (clima_1, teatro, etc.)
    - actions: Lista de acciones paralelas opcionales (0-5)

    Compatibilidad total con formato anterior (sin actions).
    """
    from_time: str        # "20:00"
    to_time: str          # "22:00"
    mode: str             # "boliche_desarrollo" (base_mode)
    day: Optional[str] = None  # "monday", "tuesday", etc.
    actions: List[str] = field(default_factory=list)  # v6.4: acciones paralelas

    def __post_init__(self):
        """Validar acciones después de inicialización"""
        # Limitar a MAX_ACTIONS_PER_BLOCK
        if len(self.actions) > MAX_ACTIONS_PER_BLOCK:
            self.actions = self.actions[:MAX_ACTIONS_PER_BLOCK]
        # Filtrar acciones inválidas (silenciosamente para compatibilidad)
        self.actions = [a for a in self.actions if a in VALID_ACTIONS]

    @property
    def base_mode(self) -> str:
        """Alias semántico: el modo ES el base_mode"""
        return self.mode

    @property
    def has_actions(self) -> bool:
        """Indica si el bloque tiene acciones paralelas"""
        return len(self.actions) > 0

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "from": self.from_time,
            "to": self.to_time,
            "mode": self.mode,
            "base_mode": self.mode,  # v6.4: alias explícito
        }
        if self.day:
            result["day"] = self.day
        if self.actions:
            result["actions"] = self.actions.copy()
        return result


@dataclass
class PermissionState:
    """Estado de permisos derivados del clima actual"""
    cam: bool = False         # Cámaras habilitadas
    audio: bool = False       # Audio reactivo habilitado
    tracking: bool = False    # Tracking de artista habilitado
    dj: bool = False          # Modo DJ activo
    energy: Optional[str] = None  # "low", "medium", "high"
    disable_states: List[str] = field(default_factory=list)  # Estados a deshabilitar

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cam": self.cam,
            "audio": self.audio,
            "tracking": self.tracking,
            "dj": self.dj,
            "energy": self.energy,
            "disable_states": self.disable_states.copy()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PermissionState":
        """Crea PermissionState desde un diccionario de reglas"""
        return cls(
            cam=data.get("cam", False),
            audio=data.get("audio", False),
            tracking=data.get("tracking", False),
            dj=data.get("dj", False),
            energy=data.get("energy"),
            disable_states=data.get("disable_states", []).copy()
        )


@dataclass
class OverrideInfo:
    """Información del override activo"""
    mode: str                           # Modo del override
    original_mode: str                  # Modo que estaba antes
    started_at: datetime                # Cuándo empezó
    expires_at: Optional[datetime]      # Cuándo expira (None = permanente)
    reason: str = ""                    # Razón del override

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "original_mode": self.original_mode,
            "started_at": self.started_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "reason": self.reason
        }


@dataclass
class CalendarState:
    """
    Estado completo del calendario v6.4.

    Contiene toda la información necesaria para el gobierno contextual.
    """
    # ==================== MODO ACTUAL ====================

    # Clima actual (modo canónico)
    current_mode: str = "apagado"

    # Fuente del último cambio
    source: CalendarSource = CalendarSource.MANUAL

    # ==================== TIMESTAMPS ====================

    # Timestamp de inicio del modo actual
    since: Optional[datetime] = None

    # Bloque de horario activo (si viene de AUTO)
    active_block: Optional[ScheduleBlock] = None

    # ==================== PRÓXIMO CAMBIO ====================

    # Información del próximo cambio programado
    next_mode: Optional[str] = None
    next_change_at: Optional[datetime] = None

    # Tiempo restante en segundos (-1 si no hay cambio programado)
    time_remaining: int = -1

    # Progreso en el bloque actual (0.0 a 1.0)
    progress: float = 0.0

    # ==================== PERMISOS ====================

    # Permisos derivados del clima actual
    permissions: PermissionState = field(default_factory=PermissionState)

    # ==================== ACCIONES (v6.4) ====================

    # Acciones paralelas del bloque activo (0-5)
    current_actions: List[str] = field(default_factory=list)

    # ==================== OVERRIDE ====================

    # Override activo (si hay uno)
    override: Optional[OverrideInfo] = None

    # ==================== ALERTAS ====================

    # Alerta activa de cambio próximo (minutos restantes)
    alert_minutes: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convierte el estado a diccionario para la UI"""
        result = {
            "current_mode": self.current_mode,
            "base_mode": self.current_mode,  # v6.4: alias semántico
            "source": self.source.value,
            "since": self.since.isoformat() if self.since else None,
            "next_mode": self.next_mode,
            "next_change_at": self.next_change_at.isoformat() if self.next_change_at else None,
            "time_remaining": self.time_remaining,
            "progress": self.progress,
            "permissions": self.permissions.to_dict(),
            "alert_minutes": self.alert_minutes,
            # v6.4: acciones paralelas del bloque activo
            "current_actions": self.current_actions.copy(),
            "has_actions": len(self.current_actions) > 0,
        }

        if self.active_block:
            result["active_block"] = self.active_block.to_dict()

        if self.override:
            result["override"] = self.override.to_dict()

        return result

    def update_progress(self, now: datetime) -> None:
        """Actualiza el progreso basado en el tiempo actual"""
        if not self.since or not self.next_change_at:
            self.progress = 0.0
            self.time_remaining = -1
            self.alert_minutes = None
            return

        total_duration = (self.next_change_at - self.since).total_seconds()
        if total_duration <= 0:
            self.progress = 1.0
            self.time_remaining = 0
            return

        elapsed = (now - self.since).total_seconds()
        self.progress = min(1.0, max(0.0, elapsed / total_duration))
        self.time_remaining = max(0, int(total_duration - elapsed))

        # Calcular minutos de alerta
        remaining_minutes = self.time_remaining // 60
        if remaining_minutes <= 15:
            self.alert_minutes = remaining_minutes
        else:
            self.alert_minutes = None

    def is_alert_active(self, threshold_minutes: int = 5) -> bool:
        """Verifica si hay una alerta activa dentro del umbral"""
        if self.alert_minutes is None:
            return False
        return self.alert_minutes <= threshold_minutes

    def has_override(self) -> bool:
        """Verifica si hay un override activo"""
        return self.override is not None

    def is_state_allowed(self, state: str) -> bool:
        """Verifica si un estado de CueEngine está permitido"""
        if "ALL" in self.permissions.disable_states:
            return False
        return state not in self.permissions.disable_states

    # ==================== ALIAS PARA COMPATIBILIDAD ====================

    @property
    def current_climate(self) -> str:
        """Alias para compatibilidad con código anterior"""
        return self.current_mode

    @current_climate.setter
    def current_climate(self, value: str):
        """Alias setter para compatibilidad"""
        self.current_mode = value
