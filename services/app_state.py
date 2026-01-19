"""
AppState - Singleton global para referencias a managers del CORE.
Permite que la API acceda al estado sin acoplarse a main.py.
"""
import time
from typing import Optional, Dict, List, Any


class AppState:
    """
    Singleton global que mantiene referencias a los managers del CORE.
    Permite que la API acceda al estado sin acoplarse a main.py.
    """

    _instance = None

    # Referencias a managers (inicializadas como None)
    state_manager: Optional[Any] = None
    audio_engine: Optional[Any] = None
    cue_engine: Optional[Any] = None
    avolites: Optional[Any] = None
    vision_manager: Optional[Any] = None

    # Referencias a modulos organizados por estado
    modules_by_state: Optional[Dict[str, List]] = None

    # Referencia a energy detector
    energy_detector: Optional[Any] = None

    # Referencia a audio monitor
    audio_monitor: Optional[Any] = None

    # Referencia a AutoClock/TAP Tempo
    auto_clock: Optional[Any] = None

    # Metadata del sistema
    app_start_time: float = 0.0
    version: str = "1.0.0"

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def initialize(
        cls,
        state_manager,
        audio_engine,
        cue_engine,
        avolites,
        vision_manager,
        modules_by_state,
        energy_detector,
        audio_monitor=None,
        auto_clock=None
    ):
        """
        Llamado una sola vez desde main.py despues de inicializar todo.
        """
        inst = cls()
        inst.state_manager = state_manager
        inst.audio_engine = audio_engine
        inst.cue_engine = cue_engine
        inst.avolites = avolites
        inst.vision_manager = vision_manager
        inst.modules_by_state = modules_by_state
        inst.energy_detector = energy_detector
        inst.audio_monitor = audio_monitor
        inst.auto_clock = auto_clock
        inst.app_start_time = time.time()

    @classmethod
    def get_instance(cls) -> "AppState":
        """Obtener instancia singleton"""
        if cls._instance is None:
            raise RuntimeError("AppState not initialized")
        return cls._instance

    def is_initialized(self) -> bool:
        """Verificar si AppState fue inicializado"""
        return self.state_manager is not None

    def get_uptime(self) -> float:
        """Retorna uptime en segundos"""
        if self.app_start_time == 0.0:
            return 0.0
        return time.time() - self.app_start_time

    def get_tap_tempo_status(self) -> Dict[str, Any]:
        """Retorna estado del TAP Tempo/AutoClock"""
        if self.auto_clock is None:
            return {
                "available": False,
                "interval_ms": 0,
                "bpm": 0,
                "manual_active": False,
                "manual_bpm": 0
            }

        try:
            return {
                "available": True,
                "interval_ms": self.auto_clock.get_interval_ms(),
                "bpm": self.auto_clock.get_bpm(),
                "manual_active": self.auto_clock.manual_override_active(),
                "manual_bpm": self.auto_clock.get_manual_bpm(),
            }
        except Exception:
            return {
                "available": True,
                "interval_ms": 0,
                "bpm": 0,
                "manual_active": False,
                "manual_bpm": 0
            }
