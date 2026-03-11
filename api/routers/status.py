"""
Status Router - Sistema status endpoint + SSE para Control Room V7

ARQUITECTURA:
- El CORE (main.py) corre un HTTP server en 127.0.0.1:8010
- Este router FORWARDEA requests a ese server
- Si el CORE no está disponible → datos offline

NO genera estado propio, NO inventa datos.
"""
import time
import asyncio
import json
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from api.models import (
    SystemStatus, AudioEngineStatus, AvolitesStatus, CueEngineStatus,
    UnifiedStatus, AudioHealthStatus, AvolitesHealthStatus,
    CameraStatus, SystemResourcesStatus, CalendarStatusBrief
)
from api.dependencies import get_app_state
from services.app_state import AppState

router = APIRouter()

# URL del HTTP Snapshot Server del CORE
CORE_SNAPSHOT_URL = "http://127.0.0.1:8010/core/snapshot"

# Cache para evitar spam de requests
_last_snapshot: Optional[dict] = None
_last_snapshot_ts: float = 0
_snapshot_cache_ttl: float = 0.1  # 100ms cache


async def _fetch_core_snapshot() -> Optional[dict]:
    """
    Fetch snapshot del CORE via HTTP.
    Retorna None si el CORE no está disponible.
    """
    global _last_snapshot, _last_snapshot_ts

    # Check cache
    now = time.time()
    if _last_snapshot and (now - _last_snapshot_ts) < _snapshot_cache_ttl:
        return _last_snapshot

    try:
        import httpx
        async with httpx.AsyncClient(timeout=1.0) as client:
            response = await client.get(CORE_SNAPSHOT_URL)
            if response.status_code == 200:
                _last_snapshot = response.json()
                _last_snapshot_ts = now
                return _last_snapshot
    except Exception as e:
        print(f"[STATUS] CORE snapshot fetch failed: {e}")

    return None


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

def _offline_status() -> dict:
    """Retorna estado cuando CORE no está disponible."""
    now = datetime.now()
    days_es = {
        "monday": "lunes", "tuesday": "martes", "wednesday": "miércoles",
        "thursday": "jueves", "friday": "viernes", "saturday": "sábado", "sunday": "domingo"
    }
    # NO inventar valores - usar null para indicar "no disponible"
    return {
        "ts": int(time.time()),
        "core": {
            "online": False,
            "last_error": "snapshot_unreachable"
        },
        "state": None,
        "energy": None,
        "audio": None,
        "avolites": None,
        "cameras": None,
        "system": None,
        "calendar": {
            "day": days_es.get(now.strftime("%A").lower(), ""),
            "time": now.strftime("%H:%M:%S"),
            "current_mode": None,
            "next_mode": None,
            "time_remaining_s": -1,
            "time_to_next_s": -1,
            "override_active": False,
            "auto": True
        }
    }


async def _build_unified_status_async() -> dict:
    """
    Construye el payload unificado para Control Room V7.
    FORWARDEA a 127.0.0.1:8010 para obtener estado REAL del CORE.
    Si el CORE no está disponible → estado offline con core.online=false.
    """
    snapshot = await _fetch_core_snapshot()

    if not snapshot:
        return _offline_status()

    # core.online viene del snapshot (o true si hay snapshot)
    core_info = snapshot.get("core", {"online": True, "last_error": None})

    # Devolver snapshot con estructura consistente
    return {
        "ts": snapshot["ts"],
        "core": core_info,
        "state": snapshot.get("state"),
        "energy": snapshot.get("energy"),
        "audio": snapshot.get("audio"),
        "avolites": snapshot.get("avolites"),
        "cameras": snapshot.get("cameras"),
        "system": snapshot.get("system"),
        "calendar": snapshot.get("calendar"),
        "network": snapshot.get("network"),
        "last_cue": snapshot.get("last_cue"),
        "transport": snapshot.get("transport"),
    }


@router.get("/status/unified")
async def get_unified_status():
    """
    GET /api/v1/status/unified

    Estado unificado para Control Room V7.
    FORWARDEA a 127.0.0.1:8010 (CORE HTTP snapshot server).
    Nunca devuelve 500 - siempre datos válidos (null/false si falla algo).
    """
    return await _build_unified_status_async()


# ==================== SSE STREAM ====================

async def _status_event_generator():
    """
    Generador de eventos SSE para tiempo real.
    Emite snapshot del CORE cada 500ms via HTTP forward.
    """
    print("[WEB][SSE] stream started")
    try:
        while True:
            try:
                data = await _build_unified_status_async()
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
async def status_stream():
    """
    GET /api/v1/stream

    Server-Sent Events (SSE) para tiempo real.
    FORWARDEA snapshot del CORE (8010) cada 500ms.

    Uso en cliente:
        const es = new EventSource('/api/v1/stream');
        es.onmessage = (e) => { const data = JSON.parse(e.data); ... };
    """
    return StreamingResponse(
        _status_event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Para nginx
        }
    )
