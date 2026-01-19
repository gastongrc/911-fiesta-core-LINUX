"""
FastAPI Dependencies - Dependency Injection
"""
from fastapi import Depends, HTTPException
from services.app_state import AppState
from services.preset_service import PresetService
from services.analyzer_service import AnalyzerService


def get_app_state() -> AppState:
    """
    Dependency que retorna AppState.
    Verifica que esté inicializado.
    """
    try:
        app_state = AppState.get_instance()
        if not app_state.is_initialized():
            raise HTTPException(
                status_code=503,
                detail="System not initialized"
            )
        return app_state
    except RuntimeError:
        raise HTTPException(
            status_code=503,
            detail="AppState not initialized"
        )


def get_preset_service() -> PresetService:
    """Dependency que retorna PresetService"""
    return PresetService()


def get_analyzer_service(
    app_state: AppState = Depends(get_app_state)
) -> AnalyzerService:
    """Dependency que retorna AnalyzerService"""
    return AnalyzerService(app_state)
