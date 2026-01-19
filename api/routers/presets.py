"""
Presets Router - Preset save/load endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from api.models import (
    PresetListResponse,
    PresetInfo,
    PresetSaveRequest,
    PresetSaveResponse,
    PresetLoadRequest,
    PresetLoadResponse
)
from api.dependencies import get_preset_service, get_app_state
from services.preset_service import PresetService
from services.app_state import AppState

router = APIRouter()


@router.get("/presets", response_model=PresetListResponse)
async def list_presets(
    service: PresetService = Depends(get_preset_service)
):
    """
    Listar presets disponibles.

    Retorna lista de archivos .json en el directorio de presets.
    """
    try:
        presets_data = service.list_presets()

        presets = [
            PresetInfo(
                name=preset.get("name", ""),
                path=preset.get("path", ""),
                size=preset.get("size", 0),
                modified=preset.get("modified", 0.0)
            )
            for preset in presets_data
        ]

        return PresetListResponse(
            presets=presets,
            count=len(presets)
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error listing presets: {str(e)}"
        )


@router.post("/save", response_model=PresetSaveResponse)
async def save_preset(
    request: PresetSaveRequest,
    service: PresetService = Depends(get_preset_service),
    app_state: AppState = Depends(get_app_state)
):
    """
    Guardar configuracion actual como preset.

    Captura:
    - Todos los thresholds de analyzers
    - Estados enabled/disabled de modulos
    - Configuracion de net_panel
    - Configuracion de Avolites
    """
    try:
        # Construir datos del preset desde el estado actual
        preset_data = service.build_preset_data(app_state)

        # Validar estructura
        is_valid, errors = service.validate_preset(preset_data)
        if not is_valid:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid preset data: {', '.join(errors)}"
            )

        # Guardar a archivo
        success, error_msg = service.save_preset(request.filename, preset_data)

        if not success:
            raise HTTPException(
                status_code=400,
                detail=error_msg or "Failed to save preset"
            )

        return PresetSaveResponse(
            success=True,
            filename=request.filename,
            message=f"Preset saved successfully to {request.filename}"
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error saving preset: {str(e)}"
        )


@router.post("/load", response_model=PresetLoadResponse)
async def load_preset(
    request: PresetLoadRequest,
    service: PresetService = Depends(get_preset_service),
    app_state: AppState = Depends(get_app_state)
):
    """
    Cargar preset desde archivo.

    Aplica:
    - Thresholds de analyzers
    - Estados enabled/disabled
    - Configuracion de net_panel (si apply_network=True)
    - Configuracion de Avolites (si apply_avolites=True)
    """
    try:
        # Cargar datos del archivo
        preset_data, error_msg = service.load_preset(request.filename)

        if preset_data is None:
            raise HTTPException(
                status_code=404,
                detail=error_msg or "Preset file not found"
            )

        # Validar estructura
        is_valid, errors = service.validate_preset(preset_data)
        if not is_valid:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid preset file: {', '.join(errors)}"
            )

        # Aplicar preset al sistema
        success, warnings = service.apply_preset_data(preset_data, app_state)

        if not success:
            raise HTTPException(
                status_code=500,
                detail="Failed to apply preset"
            )

        message = f"Preset loaded successfully from {request.filename}"
        if warnings:
            message += f" (warnings: {', '.join(warnings)})"

        return PresetLoadResponse(
            success=True,
            filename=request.filename,
            message=message,
            applied_sections=[
                "analyzers",
                "network" if request.apply_network else None,
                "avolites" if request.apply_avolites else None
            ]
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error loading preset: {str(e)}"
        )
