from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import threading
import time
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.db_models import Farm, FarmLiveState, NDVISnapshot
from app.routes.soil_weather import _build_weather_response_cached
from app.services.ndvi import calculate_lai_from_ndvi
from app.services.soilgrids import serialize_soil_profile, upsert_farm_soil_profile
from ndvi_history import get_historical_ndvi
from yield_engine import estimate_yield

FARM_LIVE_REFRESH_INTERVAL_S = max(300, int(os.getenv("FARM_LIVE_REFRESH_INTERVAL_S", "900")))
FARM_LIVE_NDVI_DELTA = max(0.0, float(os.getenv("FARM_LIVE_NDVI_DELTA", "0.02")))

_REFRESH_THREAD: Optional[threading.Thread] = None
_REFRESH_LOCK = threading.Lock()


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def extract_farm_coordinates(polygon: Any) -> Dict[str, float]:
    if not isinstance(polygon, list) or not polygon:
        return {}

    latitudes: list[float] = []
    longitudes: list[float] = []
    for point in polygon:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        longitude = _safe_float(point[0], None)
        latitude = _safe_float(point[1], None)
        if latitude is None or longitude is None:
            continue
        latitudes.append(latitude)
        longitudes.append(longitude)

    if not latitudes or not longitudes:
        return {}

    return {
        "latitude": round(sum(latitudes) / len(latitudes), 6),
        "longitude": round(sum(longitudes) / len(longitudes), 6),
    }


def _derive_vegetation_payload(latitude: float, longitude: float) -> Dict[str, Any]:
    end_year = datetime.now(timezone.utc).year
    start_year = end_year - 1
    stats = get_historical_ndvi(latitude, longitude, start_year=start_year, end_year=end_year)
    mean_ndvi = _safe_float(stats.get("mean"), 0.5)
    mean_ndvi = round(max(0.0, min(1.0, mean_ndvi or 0.5)), 4)
    evi = round((mean_ndvi * 0.85) + 0.05, 4)
    ndwi = round(max(-1.0, min(1.0, (mean_ndvi * 0.6) - 0.2)), 4)
    lai = round(calculate_lai_from_ndvi(mean_ndvi), 4)
    return {
        "ndvi": mean_ndvi,
        "evi": evi,
        "ndwi": ndwi,
        "lai": lai,
        "ndvi_min": round(_safe_float(stats.get("min"), mean_ndvi) or mean_ndvi, 4),
        "ndvi_max": round(_safe_float(stats.get("max"), mean_ndvi) or mean_ndvi, 4),
        "source": "sentinel-history",
    }


def _derive_yield_payload(crop_type: str, weather_data: Dict[str, Any], vegetation_data: Dict[str, Any]) -> Dict[str, Any]:
    current = weather_data.get("current") if isinstance(weather_data, dict) else {}
    rainfall_mm = _safe_float((current or {}).get("precipitation_mm"), 0.0) or 0.0
    temperature_c = _safe_float((current or {}).get("temperature_c"), 25.0) or 25.0
    yield_estimate = estimate_yield(
        ndvi=_safe_float(vegetation_data.get("ndvi"), 0.0) or 0.0,
        evi=_safe_float(vegetation_data.get("evi"), 0.0) or 0.0,
        ndwi=_safe_float(vegetation_data.get("ndwi"), 0.0) or 0.0,
        rainfall_mm=rainfall_mm,
        avg_temp_c=temperature_c,
        crop=(crop_type or "generic"),
    )
    return {
        "crop_type": crop_type or "generic",
        "estimated_tons_per_hectare": yield_estimate,
        "source": "yield-engine",
    }


def _payload_hash(payload: Dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _serialize_live_state(state: FarmLiveState | None) -> Optional[Dict[str, Any]]:
    if state is None:
        return None
    return {
        "farm_id": state.farm_id,
        "status": state.status,
        "coordinates": {
            "latitude": state.latitude,
            "longitude": state.longitude,
        },
        "weather": state.weather_data or {},
        "vegetation": state.vegetation_data or {},
        "yield_forecast": state.yield_data or {},
        "soil_profile": state.soil_data or {},
        "sources": state.source_data or {},
        "refreshed_at": state.refreshed_at.isoformat() if state.refreshed_at else None,
        "changed_at": state.changed_at.isoformat() if state.changed_at else None,
    }


def serialize_live_state(state: FarmLiveState | None) -> Optional[Dict[str, Any]]:
    return _serialize_live_state(state)


def _persist_ndvi_snapshot(db: Session, farm: Farm, vegetation_data: Dict[str, Any], refreshed_at: datetime) -> None:
    ndvi_value = _safe_float(vegetation_data.get("ndvi"), None)
    if ndvi_value is None:
        return

    latest = (
        db.query(NDVISnapshot)
        .filter(NDVISnapshot.farm_id == farm.id)
        .order_by(NDVISnapshot.captured_at.desc().nullslast(), NDVISnapshot.id.desc())
        .first()
    )
    latest_ndvi = _safe_float(getattr(latest, "ndvi_avg", None), None)
    same_day = bool(latest and latest.captured_at and latest.captured_at.date() == refreshed_at.date())
    if same_day and latest_ndvi is not None and abs(latest_ndvi - ndvi_value) < FARM_LIVE_NDVI_DELTA:
        return

    snapshot = NDVISnapshot(
        farm_id=farm.id,
        date=refreshed_at.date(),
        ndvi_image_path=None,
        ndvi_stats={
            "mean": ndvi_value,
            "min": _safe_float(vegetation_data.get("ndvi_min"), ndvi_value),
            "max": _safe_float(vegetation_data.get("ndvi_max"), ndvi_value),
        },
        ndvi_avg=ndvi_value,
        ndvi_min=_safe_float(vegetation_data.get("ndvi_min"), ndvi_value),
        ndvi_max=_safe_float(vegetation_data.get("ndvi_max"), ndvi_value),
        captured_at=refreshed_at,
        created_at=refreshed_at,
    )
    db.add(snapshot)


def refresh_farm_live_state(db: Session, farm: Farm, *, force_refresh_soil: bool = False) -> FarmLiveState:
    coordinates = extract_farm_coordinates(farm.polygon)
    latitude = _safe_float(coordinates.get("latitude"), None)
    longitude = _safe_float(coordinates.get("longitude"), None)
    refreshed_at = datetime.now(timezone.utc)

    state = db.query(FarmLiveState).filter(FarmLiveState.farm_id == farm.id).first()
    if state is None:
        state = FarmLiveState(farm_id=farm.id)

    if latitude is None or longitude is None:
        state.latitude = latitude
        state.longitude = longitude
        state.status = "missing_coordinates"
        state.weather_data = {}
        state.vegetation_data = {}
        state.yield_data = {}
        state.soil_data = {}
        state.source_data = {}
        state.refreshed_at = refreshed_at
        state.changed_at = refreshed_at if state.changed_at is None else state.changed_at
        db.add(state)
        db.commit()
        db.refresh(state)
        return state

    weather_data: Dict[str, Any] = {}
    vegetation_data: Dict[str, Any] = {}
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        weather_future = executor.submit(_build_weather_response_cached, latitude, longitude)
        vegetation_future = executor.submit(_derive_vegetation_payload, latitude, longitude)

        try:
            weather_data = weather_future.result(timeout=12)
        except Exception as exc:
            errors.append(f"weather: {exc}")
            weather_data = {
                "current": {
                    "temperature_c": 25.0,
                    "humidity_pct": 65.0,
                    "precipitation_mm": 0.0,
                    "condition": "Unknown",
                    "wind_kph": 5.0,
                },
                "source": "fallback",
            }

        try:
            vegetation_data = vegetation_future.result(timeout=20)
        except Exception as exc:
            errors.append(f"vegetation: {exc}")
            vegetation_data = {
                "ndvi": 0.5,
                "evi": 0.475,
                "ndwi": 0.1,
                "lai": round(calculate_lai_from_ndvi(0.5), 4),
                "ndvi_min": 0.5,
                "ndvi_max": 0.5,
                "source": "fallback",
            }

    soil_profile = None
    try:
        soil_profile = upsert_farm_soil_profile(db, farm, force_refresh=force_refresh_soil)
    except Exception as exc:
        errors.append(f"soil: {exc}")

    soil_data = serialize_soil_profile(soil_profile) if soil_profile is not None else {}
    yield_data = _derive_yield_payload(farm.crop_type or "generic", weather_data, vegetation_data)

    combined = {
        "coordinates": {"latitude": latitude, "longitude": longitude},
        "weather": weather_data,
        "vegetation": vegetation_data,
        "yield_forecast": yield_data,
        "soil_profile": soil_data,
    }
    payload_hash = _payload_hash(combined)

    state.latitude = latitude
    state.longitude = longitude
    state.weather_data = weather_data
    state.vegetation_data = vegetation_data
    state.yield_data = yield_data
    state.soil_data = soil_data
    state.source_data = {
        "weather": weather_data.get("source") or weather_data.get("provider") or "open-meteo",
        "vegetation": vegetation_data.get("source") or "sentinel-history",
        "yield_forecast": yield_data.get("source") or "yield-engine",
        "soil_profile": soil_data.get("source") or "SoilGrids",
        "errors": errors,
    }
    state.status = "degraded" if errors else "ready"
    state.refreshed_at = refreshed_at
    if state.data_hash != payload_hash:
        state.changed_at = refreshed_at
        state.data_hash = payload_hash

    _persist_ndvi_snapshot(db, farm, vegetation_data, refreshed_at)
    db.add(state)
    db.commit()
    db.refresh(state)
    return state


def refresh_stale_farm_live_states(force_refresh_soil: bool = False) -> int:
    db = SessionLocal()
    refreshed = 0
    stale_before = datetime.now(timezone.utc) - timedelta(seconds=FARM_LIVE_REFRESH_INTERVAL_S)
    try:
        farms = db.query(Farm).all()
        for farm in farms:
            state = db.query(FarmLiveState).filter(FarmLiveState.farm_id == farm.id).first()
            if state is not None and state.refreshed_at is not None and state.refreshed_at > stale_before:
                continue
            refresh_farm_live_state(db, farm, force_refresh_soil=force_refresh_soil)
            refreshed += 1
    finally:
        db.close()
    return refreshed


def _refresh_loop() -> None:
    while True:
        try:
            refresh_stale_farm_live_states(force_refresh_soil=False)
        except Exception:
            pass
        time.sleep(FARM_LIVE_REFRESH_INTERVAL_S)


def start_farm_live_refresh_worker() -> None:
    global _REFRESH_THREAD
    with _REFRESH_LOCK:
        if _REFRESH_THREAD is not None and _REFRESH_THREAD.is_alive():
            return
        _REFRESH_THREAD = threading.Thread(target=_refresh_loop, daemon=True, name="farm-live-refresh")
        _REFRESH_THREAD.start()