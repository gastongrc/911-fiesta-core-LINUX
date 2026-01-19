"""
Network Router - Network configuration endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from api.models import (
    NetworkInterfacesResponse,
    NetworkInterface,
    NetworkSetInterfaceRequest,
    NetworkSetConsoleRequest,
    NetworkPingRequest,
    NetworkPingResponse
)
from api.dependencies import get_app_state
from services.app_state import AppState

router = APIRouter()


@router.get("/network/interfaces", response_model=NetworkInterfacesResponse)
async def list_network_interfaces(
    app_state: AppState = Depends(get_app_state)
):
    """
    Listar todas las interfaces de red disponibles.
    """
    import network_utils

    try:
        interfaces_data = network_utils.list_interfaces()

        interfaces = [
            NetworkInterface(
                name=iface.get("name", ""),
                display_name=iface.get("display_name", ""),
                ips=iface.get("ips", []),
                is_up=iface.get("is_up", False)
            )
            for iface in interfaces_data
        ]

        # Obtener interfaz actual
        current = None
        if app_state.avolites:
            try:
                current = app_state.avolites.config_manager.config.get("local_ip")
            except Exception:
                pass

        return NetworkInterfacesResponse(
            interfaces=interfaces,
            current_interface=current
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error listing interfaces: {str(e)}"
        )


@router.post("/network/interface")
async def set_network_interface(
    request: NetworkSetInterfaceRequest,
    app_state: AppState = Depends(get_app_state)
):
    """
    Cambiar interfaz de red local.
    """
    if not app_state.avolites:
        raise HTTPException(
            status_code=503,
            detail="Avolites controller not available"
        )

    try:
        success = app_state.avolites.set_local_interface(request.interface_name)
        if success:
            return {"success": True, "message": f"Interface set to {request.interface_name}"}
        else:
            raise HTTPException(
                status_code=400,
                detail="Failed to set interface"
            )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error setting interface: {str(e)}"
        )


@router.post("/network/console")
async def set_console_target(
    request: NetworkSetConsoleRequest,
    app_state: AppState = Depends(get_app_state)
):
    """
    Cambiar IP/puerto del destino Avolites.
    """
    if not app_state.avolites:
        raise HTTPException(
            status_code=503,
            detail="Avolites controller not available"
        )

    try:
        success = app_state.avolites.set_console_ip(
            request.console_ip,
            request.console_port
        )
        if success:
            return {
                "success": True,
                "message": f"Console target set to {request.console_ip}:{request.console_port}"
            }
        else:
            raise HTTPException(
                status_code=400,
                detail="Failed to set console target"
            )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error setting console target: {str(e)}"
        )


@router.post("/network/ping", response_model=NetworkPingResponse)
async def ping_host(request: NetworkPingRequest):
    """
    Hacer ping a un host.
    """
    import network_utils
    import time

    try:
        start_time = time.time()
        reachable = network_utils.ping_host(request.host, request.timeout)
        end_time = time.time()

        latency_ms = None
        if reachable:
            latency_ms = (end_time - start_time) * 1000

        return NetworkPingResponse(
            host=request.host,
            reachable=reachable,
            latency_ms=latency_ms
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error pinging host: {str(e)}"
        )
