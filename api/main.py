"""
911 Fiesta Core API - FastAPI Server

ARQUITECTURA:
- Este server corre en puerto 8000
- FORWARDEA /api/v1/status/* a CORE HTTP (127.0.0.1:8010)
- FORWARDEA /api/v1/vision/* a Vision Flask (127.0.0.1:5000)
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
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


# ==================== VISION PROXY (forward to Flask 5000) ====================

VISION_FLASK_URL = "http://127.0.0.1:5000"


@app.get("/api/v1/vision/frame/{camera}")
async def vision_frame_proxy(camera: str):
    """
    Proxy para obtener frame de cámara desde Vision Flask.
    GET /api/v1/vision/frame/{haze|people|tracking}
    """
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{VISION_FLASK_URL}/frame/{camera}")
            return Response(
                content=response.content,
                status_code=response.status_code,
                media_type=response.headers.get("content-type", "image/jpeg")
            )
    except Exception as e:
        return Response(content=f"Vision offline: {e}", status_code=503)


@app.get("/api/v1/vision/stream/{camera}")
async def vision_stream_proxy(camera: str):
    """
    Proxy para stream MJPEG desde Vision Flask.
    GET /api/v1/vision/stream/{haze|people|tracking}
    """
    try:
        import httpx

        async def stream_generator():
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("GET", f"{VISION_FLASK_URL}/stream/{camera}") as response:
                    async for chunk in response.aiter_bytes():
                        yield chunk

        return StreamingResponse(
            stream_generator(),
            media_type="multipart/x-mixed-replace; boundary=frame"
        )
    except Exception as e:
        return Response(content=f"Vision offline: {e}", status_code=503)


@app.get("/api/v1/vision/status")
async def vision_status_proxy():
    """
    Proxy para estado de Vision desde Flask.
    """
    try:
        import httpx
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(f"{VISION_FLASK_URL}/status")
            return Response(
                content=response.content,
                status_code=response.status_code,
                media_type="application/json"
            )
    except Exception as e:
        return {"online": False, "error": str(e)}


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
