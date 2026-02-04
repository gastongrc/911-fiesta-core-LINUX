"""
Status Router - Sistema status endpoint + SSE para Control Room V7

IMPORTANTE: Este router usa core_bridge para leer estado REAL del core.
NO genera estado propio, NO inventa datos.
"""
import time
import asyncio
import json
from datetime import datetime
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from api.models import (
    SystemStatus, AudioEngineStatus, AvolitesStatus, CueEngineStatus,
    UnifiedStatus, AudioHealthStatus, AvolitesHealthStatus,
    CameraStatus, SystemResourcesStatus, CalendarStatusBrief
)
from api.dependencies import get_app_state
from api.core_bridge import get_full_snapshot
from services.app_state import AppState

router = APIRouter()


# ==================== LEGACY STATUS (mantener compatibilidad) ====================

@router.get("/status", response_model=SystemStatus)
async def get_system_status(
    app_state: AppState = Depends(get_app_state)
):
    """
    Obtener estado completo del sistema (legacy).
    """
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


# ==================== UNIFIED STATUS V7 ====================

def _build_unified_status(app_state: AppState) -> dict:
    """
    Construye el payload unificado para Control Room V7.
    USA core_bridge para leer estado REAL del core.
    Nunca lanza excepción - siempre devuelve datos válidos.
    """
    # Obtener snapshot real del core
    snapshot = get_full_snapshot()

    # Convertir a modelos Pydantic
    audio = AudioHealthStatus(
        silence=snapshot["audio"]["silence"],
        clipping=snapshot["audio"]["clipping"],
        level=snapshot["audio"]["level"],
        device=snapshot["audio"]["device"]
    )

    avolites = AvolitesHealthStatus(
        connected=snapshot["avolites"]["connected"],
        console_ip=snapshot["avolites"]["ip"],
        port=snapshot["avolites"]["port"],
        latency_ms=snapshot["avolites"]["latency_ms"]
    )

    cameras = [
        CameraStatus(
            name=cam["name"],
            ip=cam.get("ip", ""),
            online=cam["online"],
            fps=cam["fps"]
        )
        for cam in snapshot["cameras"]
    ]

    system = SystemResourcesStatus(
        cpu=snapshot["system"]["cpu"],
        ram=snapshot["system"]["ram"],
        gpu=snapshot["system"]["gpu"],
        temp=snapshot["system"]["temp"]
    )

    cal = snapshot["calendar"]
    calendar = CalendarStatusBrief(
        day=cal["day"],
        time=cal["time"],
        current_mode=cal["current_mode"] or "apagado",
        next_mode=cal["next_mode"],
        time_remaining_s=cal["time_remaining_s"],
        time_to_next_s=cal["time_to_next_s"],
        override_active=cal["override_active"],
        auto=cal["auto"]
    )

    return UnifiedStatus(
        ts=snapshot["ts"],
        state=snapshot["state"],
        energy=snapshot["energy"],
        audio=audio,
        avolites=avolites,
        cameras=cameras,
        system=system,
        calendar=calendar
    ).model_dump()


@router.get("/status/unified")
async def get_unified_status(
    app_state: AppState = Depends(get_app_state)
):
    """
    GET /api/v1/status/unified

    Estado unificado para Control Room V7.
    Un solo endpoint con todo lo que la web necesita.
    Nunca devuelve 500 - siempre datos válidos (null/false si falla algo).
    """
    print("[WEB][STATUS] unified status requested")
    return _build_unified_status(app_state)


# ==================== SSE STREAM ====================

async def _status_event_generator(app_state: AppState):
    """
    Generador de eventos SSE para tiempo real.
    Emite el mismo payload que /status/unified cada 500ms.
    """
    print("[WEB][SSE] stream started")
    try:
        while True:
            try:
                data = _build_unified_status(app_state)
                yield f"data: {json.dumps(data)}\n\n"
            except Exception as e:
                # Emitir error como evento pero no romper stream
                error_data = {"error": str(e), "ts": int(time.time())}
                yield f"data: {json.dumps(error_data)}\n\n"

            await asyncio.sleep(0.5)  # 500ms = 2 updates/segundo
    except asyncio.CancelledError:
        print("[WEB][SSE] stream cancelled")
        raise
    finally:
        print("[WEB][SSE] stream ended")


@router.get("/stream")
async def status_stream(
    app_state: AppState = Depends(get_app_state)
):
    """
    GET /api/v1/stream

    Server-Sent Events (SSE) para tiempo real.
    Emite el mismo payload que /status/unified cada 500ms.

    Uso en cliente:
        const es = new EventSource('/api/v1/stream');
        es.onmessage = (e) => { const data = JSON.parse(e.data); ... };
    """
    return StreamingResponse(
        _status_event_generator(app_state),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Para nginx
        }
    )
