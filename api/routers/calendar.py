"""
Calendar Router - Forward a CORE 8010

ARQUITECTURA:
- Todos los comandos calendar se forwardean a 127.0.0.1:8010
- API NO usa AppState - CORE es source of truth
- Si CORE offline: {ok:false, error:"CORE_OFFLINE"}
"""
from fastapi import APIRouter, HTTPException
from api.models import (
    CalendarGoRequest, CalendarExtendRequest,
    CalendarOverrideRequest, CalendarSaveRequest
)

router = APIRouter()

CORE_URL = "http://127.0.0.1:8010"


async def _forward_to_core(endpoint: str, data: dict = None) -> dict:
    """Forward request a CORE 8010."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=2.0) as client:
            if data is not None:
                response = await client.post(f"{CORE_URL}{endpoint}", json=data)
            else:
                response = await client.get(f"{CORE_URL}{endpoint}")

            if response.status_code == 200:
                return response.json()
            else:
                return {"ok": False, "error": f"core_http_{response.status_code}"}
    except Exception as e:
        return {"ok": False, "error": "CORE_OFFLINE", "detail": str(e)}


async def _get_calendar_from_snapshot() -> dict:
    """Obtiene calendar desde snapshot."""
    result = await _forward_to_core("/core/snapshot")
    if "calendar" in result:
        return result["calendar"]
    return None


# ==================== GET STATUS ====================

@router.get("/calendar/status")
async def get_calendar_status():
    """
    GET /api/v1/calendar/status
    Forward a CORE snapshot, extrae calendar.
    """
    snapshot = await _forward_to_core("/core/snapshot")

    if "error" in snapshot and snapshot.get("ok") is False:
        return {
            "current_mode": None,
            "error": snapshot.get("error"),
            "core_online": False
        }

    cal = snapshot.get("calendar", {})
    return {
        "current_mode": cal.get("current_mode"),
        "next_mode": cal.get("next_mode"),
        "source": cal.get("source", "AUTO"),
        "time_remaining_s": cal.get("time_remaining_s", -1),
        "time_to_next_s": cal.get("time_to_next_s", -1),
        "override_active": cal.get("override_active", False),
        "auto": cal.get("auto", True),
        "core_online": True
    }


# ==================== GO ====================

@router.post("/calendar/go")
async def calendar_go(request: CalendarGoRequest):
    """
    POST /api/v1/calendar/go
    Forward a CORE 8010.
    """
    result = await _forward_to_core("/core/calendar/go", {
        "mode": request.mode,
        "delay_minutes": request.delay_minutes
    })

    if result.get("ok"):
        return {
            "success": True,
            "message": f"GO: {request.mode}",
            "calendar": result.get("calendar")
        }
    else:
        return {
            "success": False,
            "error": result.get("error"),
            "calendar": result.get("calendar")
        }


# ==================== OVERRIDE ====================

@router.post("/calendar/override")
async def calendar_override(request: CalendarOverrideRequest):
    """
    POST /api/v1/calendar/override
    Forward a CORE 8010.
    """
    result = await _forward_to_core("/core/calendar/override", {
        "mode": request.mode,
        "minutes": request.duration_minutes,
        "reason": request.reason
    })

    if result.get("ok"):
        return {
            "success": True,
            "message": f"Override: {request.mode} por {request.duration_minutes}min",
            "calendar": result.get("calendar")
        }
    else:
        return {
            "success": False,
            "error": result.get("error"),
            "calendar": result.get("calendar")
        }


# ==================== CLEAR OVERRIDE ====================

@router.post("/calendar/override/stop")
async def calendar_override_stop():
    """
    POST /api/v1/calendar/override/stop
    Forward a CORE 8010.
    """
    result = await _forward_to_core("/core/calendar/clear_override", {})

    if result.get("ok"):
        return {
            "success": True,
            "message": "Override detenido",
            "calendar": result.get("calendar")
        }
    else:
        return {
            "success": False,
            "error": result.get("error")
        }


# ==================== AUTO MODE ====================

@router.post("/calendar/auto")
async def calendar_auto(enabled: bool = True):
    """
    POST /api/v1/calendar/auto?enabled=true
    Forward a CORE 8010.
    """
    result = await _forward_to_core("/core/calendar/auto", {"enabled": enabled})

    if result.get("ok"):
        return {
            "success": True,
            "message": f"Auto mode: {'ON' if enabled else 'OFF'}",
            "calendar": result.get("calendar")
        }
    else:
        return {
            "success": False,
            "error": result.get("error")
        }


# ==================== EXTEND (implementado como override) ====================

@router.post("/calendar/extend")
async def calendar_extend(request: CalendarExtendRequest):
    """
    POST /api/v1/calendar/extend
    Extiende bloque actual como override del modo actual.
    """
    # Obtener modo actual
    snapshot = await _forward_to_core("/core/snapshot")
    current_mode = snapshot.get("calendar", {}).get("current_mode")

    if not current_mode:
        return {"success": False, "error": "no_current_mode"}

    # Override con modo actual
    result = await _forward_to_core("/core/calendar/override", {
        "mode": current_mode,
        "minutes": request.minutes,
        "reason": f"Extend +{request.minutes}min"
    })

    if result.get("ok"):
        return {
            "success": True,
            "message": f"Extendido +{request.minutes}min",
            "calendar": result.get("calendar")
        }
    else:
        return {
            "success": False,
            "error": result.get("error")
        }
