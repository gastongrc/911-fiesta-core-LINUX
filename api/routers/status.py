"""
Status Router - Sistema status endpoint
"""
from fastapi import APIRouter, Depends
from api.models import SystemStatus, AudioEngineStatus, AvolitesStatus, CueEngineStatus
from api.dependencies import get_app_state
from services.app_state import AppState

router = APIRouter()


@router.get("/status", response_model=SystemStatus)
async def get_system_status(
    app_state: AppState = Depends(get_app_state)
):
    """
    Obtener estado completo del sistema.

    Incluye:
    - Estado del StateManager (state, energy, locked, brake)
    - Estado del AudioEngine (device, samplerate, running)
    - Estado del AvolitesController (conexion, IP, cues activos)
    - Estado del CueEngine (modulos activos, updates)
    - Uptime del sistema
    """
    # Estado del StateManager
    state = "BAJADA"
    energy = "BAJA"
    state_locked = False
    brake_active = False

    if app_state.state_manager:
        try:
            state = app_state.state_manager.get_state()
            energy = app_state.state_manager.get_energy()
            state_locked = getattr(app_state.state_manager, 'state_locked', False)
            brake_active = getattr(app_state.state_manager, 'brake_active', False)
        except Exception:
            pass

    # Estado del AudioEngine
    audio_status = AudioEngineStatus(
        device=None,
        samplerate=44100,
        channels=2,
        running=False,
        buffer_size=None
    )

    if app_state.audio_engine:
        try:
            audio_status = AudioEngineStatus(
                device=getattr(app_state.audio_engine, 'device_name', None),
                samplerate=getattr(app_state.audio_engine, 'samplerate', 44100),
                channels=2,
                running=getattr(app_state.audio_engine, 'is_running', False),
                buffer_size=None
            )
        except Exception:
            pass

    # Estado del Avolites
    avolites_status = AvolitesStatus(
        connection_state="NOT_READY",
        is_connected=False,
        console_ip="",
        console_port=4430,
        last_error=None,
        active_cues_count=0
    )

    if app_state.avolites:
        try:
            status = app_state.avolites.get_status()
            active_cues = getattr(app_state.avolites, '_active_cues', set())

            avolites_status = AvolitesStatus(
                connection_state=status.get("connection_state", "NOT_READY"),
                is_connected=status.get("is_connected", False),
                console_ip=status.get("console_ip", ""),
                console_port=status.get("console_port", 4430),
                last_error=status.get("last_error"),
                active_cues_count=len(active_cues) if isinstance(active_cues, set) else 0
            )
        except Exception:
            pass

    # Estado del CueEngine
    cue_engine_status = CueEngineStatus(
        modules_active=0,
        total_updates=0,
        last_state="",
        running=False
    )

    if app_state.cue_engine:
        try:
            status = app_state.cue_engine.get_status()
            cue_engine_status = CueEngineStatus(
                modules_active=status.get("modules_active", 0),
                total_updates=status.get("total_updates", 0),
                last_state=status.get("last_state", ""),
                running=status.get("running", False)
            )
        except Exception:
            pass

    return SystemStatus(
        state=state,
        energy=energy,
        state_locked=state_locked,
        brake_active=brake_active,
        uptime_seconds=app_state.get_uptime(),
        version=app_state.version,
        audio=audio_status,
        avolites=avolites_status,
        cue_engine=cue_engine_status
    )
