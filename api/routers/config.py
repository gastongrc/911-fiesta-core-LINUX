"""
Config Router - Configuration management endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from api.models import ConfigResponse, ConfigUpdateRequest, ConfigSection
from api.dependencies import get_app_state
from services.app_state import AppState
from typing import Dict, Any

router = APIRouter()


def get_audio_config(app_state: AppState) -> Dict[str, Any]:
    """Obtener configuracion de audio"""
    if not app_state.audio_engine:
        return {}

    try:
        return {
            "device": getattr(app_state.audio_engine, 'device_name', None),
            "samplerate": getattr(app_state.audio_engine, 'samplerate', 44100),
            "channels": 2,
            "buffer_size": getattr(app_state.audio_engine, 'buffer_size', None)
        }
    except Exception:
        return {}


def get_avolites_config(app_state: AppState) -> Dict[str, Any]:
    """Obtener configuracion de Avolites"""
    if not app_state.avolites:
        return {}

    try:
        config = {}
        if hasattr(app_state.avolites, 'config_manager'):
            config_data = app_state.avolites.config_manager.config
            config = {
                "console_ip": config_data.get("console_ip", ""),
                "console_port": config_data.get("console_port", 4430),
                "local_ip": config_data.get("local_ip", ""),
                "cue_offset": config_data.get("cue_offset", 0)
            }
        return config
    except Exception:
        return {}


def get_state_config(app_state: AppState) -> Dict[str, Any]:
    """Obtener configuracion de StateManager"""
    if not app_state.state_manager:
        return {}

    try:
        return {
            "state": app_state.state_manager.get_state(),
            "energy": app_state.state_manager.get_energy(),
            "state_locked": getattr(app_state.state_manager, 'state_locked', False),
            "brake_active": getattr(app_state.state_manager, 'brake_active', False)
        }
    except Exception:
        return {}


def get_modules_config(app_state: AppState) -> Dict[str, Any]:
    """Obtener configuracion de modulos (enabled states)"""
    if not app_state.state_manager:
        return {}

    try:
        modules = {}

        # Iterar por todos los estados y sus modulos
        for state_name in ["BAJADA", "BASE_GOLPE", "ATAQUE", "BRAKE"]:
            state_modules = app_state.state_manager.states.get(state_name, [])
            for module in state_modules:
                module_name = getattr(module, 'name', 'unknown')
                is_enabled = module.is_on() if hasattr(module, 'is_on') else False
                modules[module_name] = {
                    "enabled": is_enabled,
                    "state": state_name
                }

        return modules
    except Exception:
        return {}


def update_avolites_config(app_state: AppState, data: Dict[str, Any]) -> bool:
    """Actualizar configuracion de Avolites"""
    if not app_state.avolites:
        return False

    try:
        # Validar que solo se actualicen claves conocidas
        known_keys = {"console_ip", "console_port", "local_ip", "cue_offset"}
        unknown_keys = set(data.keys()) - known_keys

        if unknown_keys:
            raise ValueError(f"Unknown config keys: {unknown_keys}")

        # Aplicar cambios
        if "console_ip" in data or "console_port" in data:
            console_ip = data.get("console_ip", app_state.avolites.config_manager.config.get("console_ip"))
            console_port = data.get("console_port", app_state.avolites.config_manager.config.get("console_port", 4430))
            app_state.avolites.set_console_ip(console_ip, console_port)

        if "local_ip" in data:
            app_state.avolites.set_local_interface(data["local_ip"])

        if "cue_offset" in data:
            app_state.avolites.config_manager.set("cue_offset", data["cue_offset"])
            app_state.avolites.config_manager.save()

        return True
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


def update_modules_config(app_state: AppState, data: Dict[str, Any]) -> bool:
    """Actualizar configuracion de modulos (enabled states)"""
    if not app_state.state_manager:
        return False

    try:
        # data debe ser un dict de {module_name: {"enabled": bool}}
        for module_name, module_config in data.items():
            if not isinstance(module_config, dict) or "enabled" not in module_config:
                continue

            enabled = module_config["enabled"]

            # Buscar el modulo en todos los estados
            for state_name in ["BAJADA", "BASE_GOLPE", "ATAQUE", "BRAKE"]:
                state_modules = app_state.state_manager.states.get(state_name, [])
                for module in state_modules:
                    if getattr(module, 'name', '') == module_name:
                        if hasattr(module, 'turn_on') and hasattr(module, 'turn_off'):
                            if enabled:
                                module.turn_on()
                            else:
                                module.turn_off()
                        break

        return True
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/config/{section}", response_model=ConfigResponse)
async def get_config(
    section: ConfigSection,
    app_state: AppState = Depends(get_app_state)
):
    """
    Obtener configuracion de una seccion.

    Secciones disponibles:
    - audio: configuracion del AudioEngine
    - avolites: configuracion del AvolitesController
    - state: estado del StateManager
    - modules: estados enabled/disabled de modulos
    """
    config_getters = {
        ConfigSection.AUDIO: get_audio_config,
        ConfigSection.AVOLITES: get_avolites_config,
        ConfigSection.STATE: get_state_config,
        ConfigSection.MODULES: get_modules_config
    }

    getter = config_getters.get(section)
    if not getter:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown config section: {section}"
        )

    try:
        data = getter(app_state)
        return ConfigResponse(
            section=section,
            data=data
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving config: {str(e)}"
        )


@router.post("/config/{section}")
async def update_config(
    section: ConfigSection,
    request: ConfigUpdateRequest,
    app_state: AppState = Depends(get_app_state)
):
    """
    Actualizar configuracion de una seccion.

    Restricciones:
    - No se pueden actualizar claves desconocidas
    - Audio: solo lectura (no se puede actualizar)
    - State: solo lectura (no se puede actualizar)
    - Avolites: se pueden actualizar console_ip, console_port, local_ip, cue_offset
    - Modules: se pueden actualizar enabled states
    """
    # Audio y State son solo lectura
    if section in [ConfigSection.AUDIO, ConfigSection.STATE]:
        raise HTTPException(
            status_code=400,
            detail=f"Section {section} is read-only"
        )

    try:
        if section == ConfigSection.AVOLITES:
            success = update_avolites_config(app_state, request.data)
        elif section == ConfigSection.MODULES:
            success = update_modules_config(app_state, request.data)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown config section: {section}"
            )

        if success:
            return {
                "success": True,
                "message": f"Config section {section} updated successfully"
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to update config"
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error updating config: {str(e)}"
        )
