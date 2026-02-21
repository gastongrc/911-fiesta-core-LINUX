"""
Calendar Router - Forward a CORE 8010

ARQUITECTURA:
- Todos los comandos calendar se forwardean a 127.0.0.1:8010
- API NO usa AppState - CORE es source of truth
- Si CORE offline: {ok:false, error:"CORE_OFFLINE"}
"""
import logging
from fastapi import APIRouter, HTTPException
from api.models import (
    CalendarGoRequest, CalendarExtendRequest,
    CalendarOverrideRequest, CalendarSaveRequest,
    CalendarControlModeRequest, CalendarForceBlockRequest,
)

router = APIRouter()
logger = logging.getLogger("calendar")
logging.basicConfig(level=logging.INFO)

CORE_URL = "http://127.0.0.1:8010"


async def _forward_to_core(endpoint: str, data: dict = None, method: str = None) -> dict:
    """Forward request a CORE 8010."""
    import httpx
    http_method = "POST" if (method == "POST" or data is not None) else "GET"
    logger.info(f"[CALENDAR] {http_method} {endpoint} | body={data}")

    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            if http_method == "POST":
                response = await client.post(f"{CORE_URL}{endpoint}", json=data or {})
            else:
                response = await client.get(f"{CORE_URL}{endpoint}")

            result = response.json() if response.status_code == 200 else {"ok": False, "error": f"core_http_{response.status_code}"}
            logger.info(f"[CALENDAR] {http_method} {endpoint} | status={response.status_code} | result_ok={result.get('ok', 'n/a')}")
            return result
    except Exception as e:
        logger.error(f"[CALENDAR] {http_method} {endpoint} | CORE_OFFLINE | {e}")
        return {"ok": False, "error": "CORE_OFFLINE"}


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
        "control_mode": cal.get("control_mode", "AUTO"),
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


# ==================== CONTROL MODE ====================

@router.post("/calendar/control_mode")
async def calendar_control_mode(request: CalendarControlModeRequest):
    """
    POST /api/v1/calendar/control_mode
    Switch between AUTO and MANUAL control modes.
    """
    result = await _forward_to_core("/core/calendar/control_mode", {
        "mode": request.mode
    })

    if result.get("ok"):
        return {
            "success": True,
            "control_mode": result.get("control_mode"),
            "calendar": result.get("calendar")
        }
    else:
        return {
            "success": False,
            "error": result.get("error"),
            "calendar": result.get("calendar")
        }


# ==================== FORCE BLOCK ====================

@router.post("/calendar/force_block")
async def calendar_force_block(request: CalendarForceBlockRequest):
    """
    POST /api/v1/calendar/force_block
    Force a specific schedule block (MANUAL mode).
    """
    result = await _forward_to_core("/core/calendar/force_block", {
        "block_id": request.block_id
    })

    if result.get("ok"):
        return {
            "success": True,
            "block_id": result.get("block_id"),
            "calendar": result.get("calendar")
        }
    else:
        return {
            "success": False,
            "error": result.get("error"),
            "calendar": result.get("calendar")
        }


# ==================== WEEK SCHEDULE ====================

@router.get("/calendar/week")
async def get_calendar_week():
    """
    GET /api/v1/calendar/week
    Obtiene schedule semanal desde CORE.
    """
    result = await _forward_to_core("/core/calendar/week")

    if result.get("ok", True) and "week" in result:
        return {"week": result["week"]}
    elif result.get("error") == "CORE_OFFLINE":
        return {"week": {}, "error": "CORE_OFFLINE"}
    else:
        return {"week": result.get("week", {}), "error": result.get("error")}


@router.post("/calendar/save")
async def save_calendar(request: CalendarSaveRequest):
    """
    POST /api/v1/calendar/save
    Guarda schedule semanal en CORE y aplica inmediatamente.

    Retorna:
    - success: bool
    - week: el week REAL que quedó en CORE (para pisar estado local)
    - warnings: lista de solapamientos detectados
    - applied: estado aplicado actual (mode, actions, next_mode)
    """
    logger.info(f"[CALENDAR] SAVE request with {len(request.week)} days")
    result = await _forward_to_core("/core/calendar/save", {"week": request.week})

    if result.get("ok"):
        warnings = result.get("warnings", [])
        week_data = result.get("week", {})
        applied = result.get("applied", {})

        week_days = list(week_data.keys()) if week_data else []
        total_blocks = sum(len(week_data.get(d, [])) for d in week_days)

        # Log del estado aplicado
        applied_mode = applied.get("mode") if applied else None
        applied_actions = applied.get("actions", []) if applied else []
        actions_str = f", actions={applied_actions}" if applied_actions else ""
        logger.info(f"[CALENDAR] SAVE OK | blocks={total_blocks} | applied={applied_mode}{actions_str} | warnings={len(warnings)}")

        return {
            "success": True,
            "week": week_data,
            "warnings": warnings,
            "applied": applied
        }
    else:
        logger.error(f"[CALENDAR] SAVE FAILED: {result.get('error')}")
        return {
            "success": False,
            "week": {},
            "warnings": [],
            "applied": None,
            "error": result.get("error")
        }
