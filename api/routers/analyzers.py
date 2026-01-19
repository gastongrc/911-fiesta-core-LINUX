"""
Analyzers Router - Analyzer state endpoints
"""
from fastapi import APIRouter, Depends
from api.models import AnalyzersResponse, AnalyzersByState, AnalyzerState, AnalyzerThresholds, EnergyState, AnalyzerStats
from api.dependencies import get_analyzer_service
from services.analyzer_service import AnalyzerService

router = APIRouter()


@router.get("/analyzers", response_model=AnalyzersResponse)
async def get_analyzers(
    service: AnalyzerService = Depends(get_analyzer_service)
):
    """
    Obtener estado de todos los analyzers organizados por estado.

    Incluye:
    - Analyzers por estado (BAJADA, BASE_GOLPE, ATAQUE, BRAKE)
    - Estado del energy detector
    - Estadisticas generales
    """
    # Obtener todos los analyzers
    all_analyzers = service.get_all_analyzers()

    # Convertir a modelos Pydantic
    analyzers_by_state = AnalyzersByState(
        BAJADA=[
            AnalyzerState(
                name=a["name"],
                type=a["type"],
                value=a["value"],
                thresholds=AnalyzerThresholds(**a["thresholds"]),
                match=a["match"],
                active=a["active"]
            )
            for a in all_analyzers.get("BAJADA", [])
        ],
        BASE_GOLPE=[
            AnalyzerState(
                name=a["name"],
                type=a["type"],
                value=a["value"],
                thresholds=AnalyzerThresholds(**a["thresholds"]),
                match=a["match"],
                active=a["active"]
            )
            for a in all_analyzers.get("BASE_GOLPE", [])
        ],
        ATAQUE=[
            AnalyzerState(
                name=a["name"],
                type=a["type"],
                value=a["value"],
                thresholds=AnalyzerThresholds(**a["thresholds"]),
                match=a["match"],
                active=a["active"]
            )
            for a in all_analyzers.get("ATAQUE", [])
        ],
        BRAKE=[
            AnalyzerState(
                name=a["name"],
                type=a["type"],
                value=a["value"],
                thresholds=AnalyzerThresholds(**a["thresholds"]),
                match=a["match"],
                active=a["active"]
            )
            for a in all_analyzers.get("BRAKE", [])
        ]
    )

    # Obtener estado de energ�a
    energy_data = service.get_energy_state()
    energy = EnergyState(**energy_data)

    # Obtener estad�sticas
    stats_data = service.get_analyzer_stats()
    stats = AnalyzerStats(**stats_data)

    return AnalyzersResponse(
        analyzers=analyzers_by_state,
        energy=energy,
        stats=stats
    )


@router.get("/analyzers/active")
async def get_active_analyzers(
    service: AnalyzerService = Depends(get_analyzer_service)
):
    """Obtener solo analyzers activos"""
    return {"active": service.get_active_analyzers()}


@router.get("/analyzers/matching")
async def get_matching_analyzers(
    service: AnalyzerService = Depends(get_analyzer_service)
):
    """Obtener solo analyzers con match"""
    return {"matching": service.get_matching_analyzers()}
