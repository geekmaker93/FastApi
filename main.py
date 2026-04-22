import logging
import os
import threading
import time
import uuid
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

from app.routes import land, farm, satellite, soil_weather, vegetation, polygons, yields, ndvi, tiles, news, products, ai_cloud, data_sources, rag, auth, snapshots, users
from app.routes import social as social_module
from app.database import engine
from app.models import db_models
from app.models import social_models
from app.services.farm_live import start_farm_live_refresh_worker
from app.services.firebase import initialize_firebase
from app.services.runtime_log_monitor import setup_log_monitor
from yield_engine import estimate_yield
from ndvi_history import get_historical_ndvi, normalize_ndvi
from pathlib import Path

# Create tables (just in case)
db_models.Base.metadata.create_all(bind=engine)
social_models.Base.metadata.create_all(bind=engine)
db_models.ensure_user_schema(engine)
social_models.ensure_social_schema(engine)
start_farm_live_refresh_worker()

app = FastAPI(
    title="Crop Backend API",
    description="Agricultural monitoring API with satellite imagery, soil/weather data, and vegetation analysis",
    version="1.0.0"
)


@app.on_event("startup")
def startup_event() -> None:
    initialize_firebase()

LOG_MONITOR_MAX_ENTRIES = int(os.getenv("LOG_MONITOR_MAX_ENTRIES", "1000"))
LOG_MONITOR_TOKEN = os.getenv("LOG_MONITOR_TOKEN", "").strip()
log_monitor = setup_log_monitor(max_entries=LOG_MONITOR_MAX_ENTRIES)
request_logger = logging.getLogger("crop_backend.http")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

mobile_app_dir = Path(__file__).parent / "mobile_app"
if mobile_app_dir.exists() and mobile_app_dir.is_dir():
    app.mount("/mobile_app", StaticFiles(directory=str(mobile_app_dir), html=True), name="mobile_app")

uploads_dir = Path(__file__).parent / "uploads"
uploads_dir.mkdir(exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")


# ─── Background post expiry cleanup (runs every hour) ─────────────────────────
_POST_TTL_MS = 30 * 24 * 60 * 60 * 1000  # 30 days
_CLEANUP_INTERVAL_S = 3600  # 1 hour

def _cleanup_expired_posts() -> None:
    from app.database import SessionLocal
    from app.models.social_models import SocialPost, SocialLike, SocialComment
    logger = logging.getLogger("crop_backend.cleanup")
    while True:
        time.sleep(_CLEANUP_INTERVAL_S)
        try:
            cutoff = int(time.time() * 1000) - _POST_TTL_MS
            db = SessionLocal()
            try:
                expired = db.query(SocialPost).filter(SocialPost.created_at < cutoff).all()
                for post in expired:
                    # Delete media file from disk if present
                    if post.image_url:
                        rel = post.image_url.lstrip("/")
                        full = Path(__file__).parent / rel
                        if full.exists():
                            full.unlink(missing_ok=True)
                    db.query(SocialLike).filter(SocialLike.post_id == post.id).delete()
                    db.query(SocialComment).filter(SocialComment.post_id == post.id).delete()
                    db.delete(post)
                if expired:
                    db.commit()
                    logger.info("Deleted %d expired post(s)", len(expired))
            finally:
                db.close()
        except Exception:
            logger.exception("Error during post expiry cleanup")

_cleanup_thread = threading.Thread(target=_cleanup_expired_posts, daemon=True, name="post-cleanup")
_cleanup_thread.start()


@app.middleware("http")
async def request_log_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())[:8]
    start = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        request_logger.exception(
            "[%s] %s %s -> 500 in %.1f ms | error=%s",
            request_id,
            request.method,
            request.url.path,
            elapsed_ms,
            str(exc),
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "request_id": request_id},
        )

    elapsed_ms = (time.perf_counter() - start) * 1000.0
    request_logger.info(
        "[%s] %s %s -> %s in %.1f ms",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    if request.url.path.startswith("/mobile_app"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    response.headers["X-Request-Id"] = request_id
    return response


def _authorize_log_access(token: Optional[str]) -> None:
    if LOG_MONITOR_TOKEN and token != LOG_MONITOR_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid log monitor token")

# Include routers
app.include_router(land.router)
app.include_router(farm.router)
app.include_router(satellite.router)
if hasattr(soil_weather, "router"):
    app.include_router(soil_weather.router)
app.include_router(vegetation.router)
app.include_router(polygons.router)
app.include_router(yields.router, prefix="/yields", tags=["yields"])
app.include_router(ndvi.router)
app.include_router(tiles.router, tags=["tiles"])
app.include_router(products.router)
app.include_router(news.router)
app.include_router(ai_cloud.router)
app.include_router(data_sources.router)
app.include_router(rag.router)
app.include_router(auth.router)
app.include_router(snapshots.router)
app.include_router(users.router)
app.include_router(social_module.router)

@app.get("/")
def read_root():
    return {
        "message": "Crop Backend API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs"
    }

@app.get("/health")
def health_check():
    return {"status": "healthy"}


@app.get("/debug/logs")
def debug_logs(
    limit: int = 200,
    since_id: Optional[int] = None,
    level: Optional[str] = None,
    contains: Optional[str] = None,
    logger: Optional[str] = None,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    _authorize_log_access(token)

    entries = log_monitor.query(
        limit=limit,
        since_id=since_id,
        level=level,
        contains=contains,
        logger=logger,
    )
    last_id = entries[-1]["id"] if entries else since_id
    return {
        "count": len(entries),
        "last_id": last_id,
        "entries": entries,
    }


@app.delete("/debug/logs")
def clear_debug_logs(token: Optional[str] = None) -> Dict[str, Any]:
    _authorize_log_access(token)
    cleared = log_monitor.clear()
    return {"cleared": cleared}

@app.get("/estimate-yield")
def calculate_yield_estimate(
    ndvi_value: float,
    evi_value: float,
    ndwi_value: float,
    rainfall: float,
    temperature: float,
    crop_type: str,
    lat: float = None,
    lon: float = None,
    ndvi_score: float = None,
    history: list = None
):
    """
    Calculate yield estimate based on vegetation indices and weather data.
    """
    yield_estimate = estimate_yield(
        ndvi=ndvi_value,
        evi=evi_value,
        ndwi=ndwi_value,
        rainfall_mm=rainfall,
        avg_temp_c=temperature,
        crop=crop_type
    )
    
    return {
        "location": {"lat": lat, "lon": lon},
        "indices": {
            "ndvi": ndvi_value,
            "evi": evi_value,
            "ndwi": ndwi_value
        },
        "weather": {
            "rainfall_mm": rainfall,
            "temperature_c": temperature
        },
        "crop": crop_type,
        "ndvi_health_score": ndvi_score,
        "ndvi_historical": history,
        "yield_estimate_tons_per_hectare": yield_estimate
    }

# Serve dashboard HTML
@app.get("/dashboard")
def get_dashboard():
    """Serve the crop monitoring dashboard"""
    from fastapi.responses import FileResponse
    dashboard_path = Path(__file__).parent / "dashboard.html"
    return FileResponse(dashboard_path, media_type="text/html")

@app.get("/dashboard.html")
def get_dashboard_html():
    """Serve the crop monitoring dashboard (with extension)"""
    from fastapi.responses import FileResponse
    dashboard_path = Path(__file__).parent / "dashboard.html"
    return FileResponse(dashboard_path, media_type="text/html")
