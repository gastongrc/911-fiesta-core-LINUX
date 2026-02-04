"""
FastAPI Dependencies - Dependency Injection

REGLA: NUNCA tirar 503. Devolver estado degradado si el CORE no está listo.
La web debe mostrar "OFFLINE" o "NOT READY", no quedarse colgada.
"""
from fastapi import Depends
from services.app_state import AppState
from services.preset_service import PresetService
from services.analyzer_service import AnalyzerService


# Singleton para modo degradado (cuando CORE no está listo)
_degraded_state = None


def get_app_state() -> AppState:
    """
    Dependency que retorna AppState.

    NUNCA tira 503 - devuelve instancia vacía si no está inicializado.
    Los endpoints deben verificar is_initialized() si necesitan CORE activo.
    """
    global _degraded_state

    try:
        app_state = AppState.get_instance()
        return app_state
    except RuntimeError:
        # CORE no inicializado - devolver estado degradado
        if _degraded_state is None:
            _degraded_state = AppState()
            print("[API] AppState not initialized - returning degraded state")
        return _degraded_state


def get_preset_service() -> PresetService:
    """Dependency que retorna PresetService"""
    return PresetService()


def get_analyzer_service(
    app_state: AppState = Depends(get_app_state)
) -> AnalyzerService:
    """Dependency que retorna AnalyzerService"""
    return AnalyzerService(app_state)
