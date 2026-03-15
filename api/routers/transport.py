"""
Transport Router - Transport status and switching endpoints

Allows querying the active transport (HTTP/ArtNet) and switching between them.
This is critical for diagnosing pipeline issues where fire() doesn't reach DMX.
"""
from fastapi import APIRouter, Depends, HTTPException
from api.models import (
    TransportStatusResponse,
    TransportSwitchRequest,
    TransportSwitchResponse,
)
from api.dependencies import get_app_state
from services.app_state import AppState

router = APIRouter()


@router.get("/transport", response_model=TransportStatusResponse)
async def get_transport_status(
    app_state: AppState = Depends(get_app_state),
):
    """
    Get the currently active transport and its stats.

    Returns:
        - active_transport: "TitanTransport" (HTTP) or "ArtNetTransport"
        - transport_stats: stats from the active transport
        - queue_stats: TitanQueue stats
        - config_transport: what the config file says
    """
    if not app_state.avolites:
        raise HTTPException(status_code=503, detail="Avolites controller not available")

    try:
        controller = app_state.avolites
        queue = controller._titan_queue
        transport = queue.get_transport()
        transport_name = type(transport).__name__

        transport_stats = {}
        if hasattr(transport, "get_stats"):
            transport_stats = transport.get_stats()

        queue_stats = queue.get_stats()
        config_transport = controller.config_manager.config.get("transport", "http")

        return TransportStatusResponse(
            active_transport=transport_name,
            transport_stats=transport_stats,
            queue_stats=queue_stats,
            config_transport=config_transport,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting transport status: {e}")


@router.post("/transport", response_model=TransportSwitchResponse)
async def switch_transport(
    request: TransportSwitchRequest,
    app_state: AppState = Depends(get_app_state),
):
    """
    Switch the active transport between HTTP and ArtNet.

    For ArtNet, optional params: net, subnet, universe, broadcast (bool).
    Also updates the config file so the change persists across restarts.
    """
    if not app_state.avolites:
        raise HTTPException(status_code=503, detail="Avolites controller not available")

    try:
        controller = app_state.avolites
        success = controller.set_transport(request.transport, artnet_params=request.artnet_params)

        # Persist to config
        if success:
            controller.config_manager.config["transport"] = request.transport
            if request.transport == "artnet" and request.artnet_params:
                controller.config_manager.config["artnet"] = request.artnet_params
            controller.config_manager.save_config()

        # Read back the active transport
        active = type(controller._titan_queue.get_transport()).__name__

        return TransportSwitchResponse(
            success=success,
            active_transport=active,
            message=f"Transport switched to {active}" if success else f"Failed to switch transport",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error switching transport: {e}")
