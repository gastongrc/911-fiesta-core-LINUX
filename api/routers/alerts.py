from fastapi import APIRouter, Depends
from api.dependencies import get_app_state
from services.app_state import AppState
from pydantic import BaseModel

router = APIRouter()

class AlertsResponse(BaseModel):
    alerts: dict
    timestamp: float

@router.get("/alerts", response_model=AlertsResponse)
async def get_audio_alerts(app_state: AppState = Depends(get_app_state)):
    """
    Estado de alertas del monitor de audio.
    """
    monitor = getattr(app_state, "audio_monitor", None)

    if monitor is None:
        return AlertsResponse(alerts={}, timestamp=0)

    status = monitor.get_status()
    return AlertsResponse(**status)
