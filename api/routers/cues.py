"""
Cues Router - Cue control endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from api.models import (
    CueStatusResponse,
    CueFireRequest,
    CueFireResponse,
    CueKillRequest,
    CueKillResponse,
    CueEngineStatus
)
from api.dependencies import get_app_state
from services.app_state import AppState

router = APIRouter()


@router.get("/cues", response_model=CueStatusResponse)
async def get_cue_status(
    app_state: AppState = Depends(get_app_state)
):
    """
    Obtener estado del sistema de cues.

    Incluye:
    - Cues activos actualmente
    - Estado del CueEngine
    """
    active_cues = []
    if app_state.avolites:
        try:
            active_cues_set = getattr(app_state.avolites, '_active_cues', set())
            active_cues = sorted(list(active_cues_set))
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

    return CueStatusResponse(
        active_cues=active_cues,
        cue_engine=cue_engine_status
    )


@router.post("/cues/fire", response_model=CueFireResponse)
async def fire_cue(
    request: CueFireRequest,
    app_state: AppState = Depends(get_app_state)
):
    """
    Disparar un cue manualmente.

    Args:
        cue_number: Numero logico del cue (1-300)
        force: Si True, usa fire_cue_manual (bypass READY state)
    """
    if not app_state.avolites:
        raise HTTPException(
            status_code=503,
            detail="Avolites controller not available"
        )

    try:
        if request.force:
            # Usar fire_cue_manual para bypass READY
            success = app_state.avolites.fire_cue_manual(request.cue_number)
        else:
            # Usar fire_cue normal (respeta READY)
            success = app_state.avolites.fire_cue(request.cue_number)

        return CueFireResponse(
            success=success,
            cue_number=request.cue_number,
            message=f"Cue {request.cue_number} fired successfully" if success else f"Failed to fire cue {request.cue_number}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error firing cue: {str(e)}"
        )


@router.delete("/cues/kill", response_model=CueKillResponse)
async def kill_cues(
    request: CueKillRequest,
    app_state: AppState = Depends(get_app_state)
):
    """
    Matar uno o m�s cues.

    Args:
        cue_numbers: Lista de n�meros l�gicos de cues
        force: Si True, usa kill_cue_manual
    """
    if not app_state.avolites:
        raise HTTPException(
            status_code=503,
            detail="Avolites controller not available"
        )

    try:
        killed = []
        for cue_number in request.cue_numbers:
            if request.force:
                # Usar kill_cue_manual para bypass READY
                success = app_state.avolites.kill_cue_manual(cue_number)
            else:
                # Usar kill_cue normal (respeta READY)
                success = app_state.avolites.kill_cue(cue_number)

            if success:
                killed.append(cue_number)

        return CueKillResponse(
            success=len(killed) > 0,
            killed_count=len(killed),
            cue_numbers=killed,
            message=f"Killed {len(killed)} cue(s)" if killed else "No cues were killed"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error killing cues: {str(e)}"
        )
