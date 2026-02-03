"""
Calendar Router - Endpoints de calendario para Control Room V7

Endpoints:
- GET  /api/v1/calendar/status   - Estado completo del calendario
- GET  /api/v1/calendar/week     - Schedule de la semana
- POST /api/v1/calendar/save     - Guardar schedule
- POST /api/v1/calendar/go       - GO manual (cambio inmediato o con delay)
- POST /api/v1/calendar/extend   - Extender bloque actual (+5/+10/+15 min)
- POST /api/v1/calendar/override - Activar override temporal
- POST /api/v1/calendar/override/stop - Detener override
"""
from fastapi import APIRouter, Depends, HTTPException
from api.models import (
    CalendarStatusResponse, CalendarWeekResponse,
    CalendarGoRequest, CalendarExtendRequest,
    CalendarOverrideRequest, CalendarSaveRequest
)
from api.dependencies import get_app_state
from services.app_state import AppState

router = APIRouter()


def _get_calendar_manager(app_state: AppState):
    """
    Obtiene el CalendarManager desde AppState.
    Intenta múltiples rutas por compatibilidad.
    """
    # Ruta 1: Directo en app_state
    cm = getattr(app_state, 'calendar_manager', None)
    if cm:
        return cm

    # Ruta 2: Desde main_window
    main_window = getattr(app_state, 'main_window', None)
    if main_window:
        cm = getattr(main_window, 'calendar_manager', None)
        if cm:
            return cm

    return None


# ==================== GET STATUS ====================

@router.get("/calendar/status")
async def get_calendar_status(
    app_state: AppState = Depends(get_app_state)
):
    """
    GET /api/v1/calendar/status

    Estado completo del calendario incluyendo:
    - Modo actual y próximo
    - Override activo
    - Alertas pendientes
    - GO pendiente
    - Modos disponibles
    """
    print("[CALENDAR] GET status")

    cm = _get_calendar_manager(app_state)
    if not cm:
        # No hay calendario - devolver estado por defecto
        return {
            "current_mode": "apagado",
            "next_mode": None,
            "source": "NONE",
            "since": None,
            "time_remaining_s": -1,
            "time_to_next_s": -1,
            "progress": 0.0,
            "override": None,
            "alert": None,
            "pending_go": None,
            "auto_mode_enabled": False,
            "available_modes": [
                "clima_1", "clima_2", "clima_3", "clima_4",
                "boliche_inicio", "boliche_desarrollo", "boliche_fin",
                "apagado", "extra_1", "extra_2", "extra_3"
            ]
        }

    try:
        state = cm.get_state()
        return {
            "current_mode": state.get("current_mode", "apagado"),
            "next_mode": state.get("next_mode"),
            "source": state.get("source", "AUTO"),
            "since": state.get("since"),
            "time_remaining_s": state.get("time_remaining_s", -1),
            "time_to_next_s": state.get("time_to_next_s", -1),
            "progress": state.get("progress", 0.0),
            "override": state.get("override"),
            "alert": state.get("alert"),
            "pending_go": state.get("pending_go"),
            "auto_mode_enabled": state.get("auto_mode_enabled", True),
            "available_modes": state.get("available_modes", [])
        }
    except Exception as e:
        print(f"[CALENDAR][ERR] status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== GET WEEK ====================

@router.get("/calendar/week")
async def get_calendar_week(
    app_state: AppState = Depends(get_app_state)
):
    """
    GET /api/v1/calendar/week

    Schedule completo de la semana.
    Formato: { "week": { "monday": [...], "tuesday": [...], ... } }
    """
    print("[CALENDAR] GET week")

    cm = _get_calendar_manager(app_state)
    if not cm:
        # Devolver schedule vacío
        return {
            "week": {
                "monday": [], "tuesday": [], "wednesday": [],
                "thursday": [], "friday": [], "saturday": [], "sunday": []
            }
        }

    try:
        schedule = cm.get_schedule()
        return {"week": schedule.get("week", {})}
    except Exception as e:
        print(f"[CALENDAR][ERR] week: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== SAVE ====================

@router.post("/calendar/save")
async def save_calendar(
    request: CalendarSaveRequest,
    app_state: AppState = Depends(get_app_state)
):
    """
    POST /api/v1/calendar/save

    Guarda el schedule en config/calendar.json.
    Body: { "week": { "monday": [...], ... } }
    """
    print("[CALENDAR] POST save")

    cm = _get_calendar_manager(app_state)
    if not cm:
        raise HTTPException(status_code=503, detail="CalendarManager not available")

    try:
        success = cm.save_schedule({"week": request.week})
        if success:
            print("[CALENDAR] schedule saved OK")
            return {"success": True, "message": "Schedule guardado correctamente"}
        else:
            raise HTTPException(status_code=500, detail="Error guardando schedule")
    except HTTPException:
        raise
    except Exception as e:
        print(f"[CALENDAR][ERR] save: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== GO ====================

@router.post("/calendar/go")
async def calendar_go(
    request: CalendarGoRequest,
    app_state: AppState = Depends(get_app_state)
):
    """
    POST /api/v1/calendar/go

    GO manual - cambia al modo especificado.
    Puede tener delay opcional (0, 5, 10, 15 minutos).

    Body: { "mode": "boliche_desarrollo", "delay_minutes": 0 }
    """
    print(f"[CALENDAR] POST go -> {request.mode} (delay={request.delay_minutes}min)")

    cm = _get_calendar_manager(app_state)
    if not cm:
        raise HTTPException(status_code=503, detail="CalendarManager not available")

    try:
        # Importar CalendarSource para el GO
        from core.calendar.calendar_state import CalendarSource

        success = cm.go(
            mode=request.mode,
            source=CalendarSource.MANUAL,
            delay_minutes=request.delay_minutes
        )

        if success:
            if request.delay_minutes > 0:
                return {
                    "success": True,
                    "message": f"GO programado: {request.mode} en {request.delay_minutes} minutos"
                }
            else:
                return {
                    "success": True,
                    "message": f"GO ejecutado: {request.mode}"
                }
        else:
            raise HTTPException(status_code=400, detail="GO fallido")

    except HTTPException:
        raise
    except Exception as e:
        print(f"[CALENDAR][ERR] go: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== EXTEND ====================

@router.post("/calendar/extend")
async def calendar_extend(
    request: CalendarExtendRequest,
    app_state: AppState = Depends(get_app_state)
):
    """
    POST /api/v1/calendar/extend

    Extiende el bloque actual por N minutos (+5, +10, +15).
    Implementado como override temporal del modo actual.

    Body: { "minutes": 10 }
    """
    print(f"[CALENDAR] POST extend -> +{request.minutes}min")

    cm = _get_calendar_manager(app_state)
    if not cm:
        raise HTTPException(status_code=503, detail="CalendarManager not available")

    try:
        # Obtener modo actual
        current_mode = cm.get_current_mode()

        # Usar override temporal para "extender"
        from core.calendar.calendar_manager import OverrideType

        success = cm.set_override(
            mode=current_mode,
            override_type=OverrideType.TEMPORARY,
            duration_minutes=request.minutes,
            reason=f"Extend +{request.minutes}min"
        )

        if success:
            return {
                "success": True,
                "message": f"Bloque extendido +{request.minutes} minutos",
                "mode": current_mode,
                "extended_minutes": request.minutes
            }
        else:
            raise HTTPException(status_code=400, detail="Extend fallido")

    except HTTPException:
        raise
    except Exception as e:
        print(f"[CALENDAR][ERR] extend: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== OVERRIDE ====================

@router.post("/calendar/override")
async def calendar_override(
    request: CalendarOverrideRequest,
    app_state: AppState = Depends(get_app_state)
):
    """
    POST /api/v1/calendar/override

    Activa override temporal - fuerza un modo por N minutos.
    Durante el override, el calendario automático NO cambiará el modo.

    Body: { "mode": "boliche_fin", "duration_minutes": 30, "reason": "Show especial" }
    """
    print(f"[CALENDAR] POST override -> {request.mode} ({request.duration_minutes}min)")

    cm = _get_calendar_manager(app_state)
    if not cm:
        raise HTTPException(status_code=503, detail="CalendarManager not available")

    try:
        from core.calendar.calendar_manager import OverrideType

        success = cm.set_override(
            mode=request.mode,
            override_type=OverrideType.TEMPORARY,
            duration_minutes=request.duration_minutes,
            reason=request.reason or "Override desde web"
        )

        if success:
            return {
                "success": True,
                "message": f"Override activo: {request.mode} por {request.duration_minutes} minutos",
                "mode": request.mode,
                "duration_minutes": request.duration_minutes
            }
        else:
            raise HTTPException(status_code=400, detail="Override fallido")

    except HTTPException:
        raise
    except Exception as e:
        print(f"[CALENDAR][ERR] override: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== OVERRIDE STOP ====================

@router.post("/calendar/override/stop")
async def calendar_override_stop(
    app_state: AppState = Depends(get_app_state)
):
    """
    POST /api/v1/calendar/override/stop

    Detiene el override activo y vuelve al modo automático.
    """
    print("[CALENDAR] POST override/stop")

    cm = _get_calendar_manager(app_state)
    if not cm:
        raise HTTPException(status_code=503, detail="CalendarManager not available")

    try:
        was_active = cm.is_override_active()
        cm.clear_override()

        if was_active:
            return {"success": True, "message": "Override detenido, volviendo a modo automático"}
        else:
            return {"success": True, "message": "No había override activo"}

    except Exception as e:
        print(f"[CALENDAR][ERR] override/stop: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== ACKNOWLEDGE ALERT ====================

@router.post("/calendar/alert/ack")
async def calendar_alert_acknowledge(
    app_state: AppState = Depends(get_app_state)
):
    """
    POST /api/v1/calendar/alert/ack

    Confirma la alerta de cambio próximo.
    """
    print("[CALENDAR] POST alert/ack")

    cm = _get_calendar_manager(app_state)
    if not cm:
        raise HTTPException(status_code=503, detail="CalendarManager not available")

    try:
        success = cm.acknowledge_alert()
        if success:
            return {"success": True, "message": "Alerta confirmada"}
        else:
            return {"success": False, "message": "No hay alerta pendiente"}
    except Exception as e:
        print(f"[CALENDAR][ERR] alert/ack: {e}")
        raise HTTPException(status_code=500, detail=str(e))
