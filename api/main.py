"""
911 Fiesta Core API - FastAPI Server
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Import routers
from api.routers import status, analyzers, cues, network, presets, config, alerts, calendar


# FastAPI app
app = FastAPI(
    title="911 Fiesta Core API",
    version="1.0.0",
    description="Control API for 911 Fiesta lighting system"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(status.router, prefix="/api/v1", tags=["status"])
app.include_router(analyzers.router, prefix="/api/v1", tags=["analyzers"])
app.include_router(cues.router, prefix="/api/v1", tags=["cues"])
app.include_router(network.router, prefix="/api/v1", tags=["network"])
app.include_router(presets.router, prefix="/api/v1", tags=["presets"])
app.include_router(config.router, prefix="/api/v1", tags=["config"])
app.include_router(alerts.router, prefix="/api/v1", tags=["alerts"])
app.include_router(calendar.router, prefix="/api/v1", tags=["calendar"])


@app.get("/")
async def root():
    """Root endpoint - API info"""
    return {
        "service": "911-fiesta-api",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    from services.app_state import AppState

    try:
        inst = AppState.get_instance()
        return {
            "status": "ok",
            "initialized": inst.is_initialized(),
            "uptime": inst.get_uptime(),
        }
    except:
        return {
            "status": "ok",
            "initialized": False,
            "uptime": 0
        }


def start_api_server(host: str = "0.0.0.0", port: int = 8000):
    """
    Funci�n para iniciar el servidor API.
    Llamada desde main.py en thread separado.
    """
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
        access_log=True
    )
