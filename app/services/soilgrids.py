from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Dict, Optional

import requests
from sqlalchemy.orm import Session

from app.models.db_models import Farm, SoilProfile

SOILGRIDS_URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"
TOPSOIL_DEPTHS = ["0-5cm", "5-15cm"]
SOILGRIDS_PROPERTIES = [
    "bdod",
    "cec",
    "cfvo",
    "clay",
    "nitrogen",
    "phh2o",
    "sand",
    "silt",
    "soc",
]


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _round_coord(value: float) -> float:
    return round(float(value), 5)


def _source_ref(latitude: float, longitude: float) -> str:
    return f"soilgrids:{_round_coord(latitude):.5f}:{_round_coord(longitude):.5f}"


def _extract_point_from_polygon(polygon: Any) -> Dict[str, float]:
    if not isinstance(polygon, list) or not polygon:
        return {}

    latitudes = []
    longitudes = []
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


def _soilgrids_params(latitude: float, longitude: float) -> list[tuple[str, Any]]:
    params: list[tuple[str, Any]] = [("lat", latitude), ("lon", longitude)]
    for prop in SOILGRIDS_PROPERTIES:
        params.append(("property", prop))
    for depth in TOPSOIL_DEPTHS:
        params.append(("depth", depth))
    params.append(("value", "mean"))
    return params


def fetch_soilgrids_profile(latitude: float, longitude: float) -> Dict[str, Any]:
    # Reduced timeout from 20s to 5s for faster failure and better mobile UX
    response = requests.get(SOILGRIDS_URL, params=_soilgrids_params(latitude, longitude), timeout=5)
    response.raise_for_status()
    return response.json()


def _soilgrids_layers(payload: Dict[str, Any]) -> list[dict[str, Any]]:
    layers = (((payload or {}).get("properties") or {}).get("layers") or [])
    return [layer for layer in layers if isinstance(layer, dict)]


def _layer_name(layer: Dict[str, Any]) -> str:
    return str(layer.get("name") or "").strip()


def _depth_values(layer: Dict[str, Any]) -> Dict[str, float]:
    values: Dict[str, float] = {}
    for depth in layer.get("depths") or []:
        if not isinstance(depth, dict):
            continue
        label = str(depth.get("label") or "").strip()
        mean_value = _safe_float(((depth.get("values") or {}).get("mean")), None)
        if label and mean_value is not None:
            values[label] = mean_value
    return values


def _extract_property_values(payload: Dict[str, Any]) -> Dict[str, Dict[str, float]]:
    values: Dict[str, Dict[str, float]] = {}
    for layer in _soilgrids_layers(payload):
        name = _layer_name(layer)
        if not name:
            continue
        depth_values = _depth_values(layer)
        if depth_values:
            values[name] = depth_values
    return values


def _depth_average(property_values: Dict[str, Dict[str, float]], name: str) -> Optional[float]:
    by_depth = property_values.get(name) or {}
    values = [_safe_float(by_depth.get(depth), None) for depth in TOPSOIL_DEPTHS]
    valid = [value for value in values if value is not None]
    if not valid:
        return None
    return sum(valid) / len(valid)


def _scale_units(metric_name: str, value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    if metric_name == "bdod":
        return value / 100.0
    if metric_name == "cec":
        return value / 10.0
    if metric_name == "nitrogen":
        return value / 100.0
    if metric_name == "soc":
        return value / 10.0
    return value


def normalize_topsoil_metrics(payload: Dict[str, Any]) -> Dict[str, Optional[float]]:
    raw_values = _extract_property_values(payload)
    normalized = {}
    for metric_name in SOILGRIDS_PROPERTIES:
        normalized[metric_name] = _scale_units(metric_name, _depth_average(raw_values, metric_name))
    return normalized


def _soil_texture_class(sand: Optional[float], silt: Optional[float], clay: Optional[float]) -> str:
    sand = _safe_float(sand, 0.0) or 0.0
    silt = _safe_float(silt, 0.0) or 0.0
    clay = _safe_float(clay, 0.0) or 0.0
    if clay >= 40:
        return "clay"
    if sand >= 70 and clay <= 15:
        return "sandy"
    if silt >= 50 and clay < 27:
        return "silty"
    if 20 <= clay <= 35 and 25 <= sand <= 55:
        return "loam"
    if clay > 27 and sand > 45:
        return "sandy clay loam"
    if clay > 27 and silt > 40:
        return "silty clay loam"
    return "mixed loam"


def _drainage_class(metrics: Dict[str, Optional[float]]) -> str:
    clay = _safe_float(metrics.get("clay"), 0.0) or 0.0
    sand = _safe_float(metrics.get("sand"), 0.0) or 0.0
    coarse_fragments = _safe_float(metrics.get("cfvo"), 0.0) or 0.0
    bulk_density = _safe_float(metrics.get("bdod"), 0.0) or 0.0
    if sand >= 65 and clay <= 15:
        return "well drained"
    if clay >= 40 or bulk_density >= 1.55:
        return "poorly drained"
    if coarse_fragments >= 35:
        return "excessively drained"
    if 25 <= clay < 40:
        return "moderately well drained"
    return "moderately drained"


def _water_holding_estimate(metrics: Dict[str, Optional[float]]) -> float:
    clay = _safe_float(metrics.get("clay"), 0.0) or 0.0
    silt = _safe_float(metrics.get("silt"), 0.0) or 0.0
    sand = _safe_float(metrics.get("sand"), 0.0) or 0.0
    soc = _safe_float(metrics.get("soc"), 0.0) or 0.0
    coarse_fragments = _safe_float(metrics.get("cfvo"), 0.0) or 0.0
    estimate = 40.0 + (clay * 1.2) + (silt * 0.35) + (soc * 3.0) - (sand * 0.45) - (coarse_fragments * 0.55)
    return round(max(15.0, min(220.0, estimate)), 2)


def _fertility_score(metrics: Dict[str, Optional[float]]) -> float:
    ph = _safe_float(metrics.get("phh2o"), 5.5) or 5.5
    soc = _safe_float(metrics.get("soc"), 0.0) or 0.0
    cec = _safe_float(metrics.get("cec"), 0.0) or 0.0
    nitrogen = _safe_float(metrics.get("nitrogen"), 0.0) or 0.0

    ph_score = max(0.0, 100.0 - (abs(ph - 6.5) * 25.0))
    soc_score = min(100.0, soc * 12.5)
    cec_score = min(100.0, cec * 4.5)
    nitrogen_score = min(100.0, nitrogen * 18.0)
    score = (ph_score * 0.25) + (soc_score * 0.3) + (cec_score * 0.25) + (nitrogen_score * 0.2)
    return round(max(0.0, min(100.0, score)), 1)


def derive_soil_properties(metrics: Dict[str, Optional[float]]) -> Dict[str, Any]:
    soil_type = _soil_texture_class(metrics.get("sand"), metrics.get("silt"), metrics.get("clay"))
    drainage = _drainage_class(metrics)
    water_holding = _water_holding_estimate(metrics)
    fertility = _fertility_score(metrics)
    return {
        "soil_type": soil_type,
        "drainage_class": drainage,
        "water_holding_estimate_mm_per_m": water_holding,
        "fertility_score": fertility,
    }


def _fallback_metric(latitude: float, longitude: float, base: float, spread: float) -> float:
    # Blend low and high frequency components so nearby points can differ while
    # remaining geographically smooth and deterministic.
    low_freq = math.sin(latitude * 0.9) + math.cos(longitude * 0.8)
    high_freq = math.sin(latitude * 27.0) + math.cos(longitude * 23.0)
    cross_term = math.sin((latitude + longitude) * 19.0)
    signal = (low_freq * 0.45) + (high_freq * 0.4) + (cross_term * 0.35)
    smooth = max(0.0, min(1.0, (signal + 2.4) / 4.8))

    # Add a stable coordinate hash component so close-but-different pinpoints
    # do not collapse into nearly identical values when upstream data is down.
    lat_key = int(round((latitude + 90.0) * 10000))
    lon_key = int(round((longitude + 180.0) * 10000))
    mixed = (lat_key * 73856093) ^ (lon_key * 19349663)
    hashed = (mixed & 0xFFFF) / 65535.0

    normalized = (smooth * 0.65) + (hashed * 0.35)
    return round(base + (normalized * spread), 2)


def fallback_topsoil_metrics(latitude: float, longitude: float) -> Dict[str, Optional[float]]:
    sand = _fallback_metric(latitude, longitude, 38.0, 24.0)
    clay = _fallback_metric(longitude, latitude, 18.0, 16.0)
    silt = max(10.0, round(100.0 - sand - clay, 2))
    return {
        "bdod": _fallback_metric(latitude, longitude, 1.18, 0.28),
        "cec": _fallback_metric(longitude, latitude, 11.0, 8.0),
        "cfvo": _fallback_metric(latitude + longitude, longitude, 6.0, 12.0),
        "clay": clay,
        "nitrogen": _fallback_metric(latitude, longitude, 3.0, 2.0),
        "phh2o": _fallback_metric(longitude, latitude, 5.6, 1.2),
        "sand": sand,
        "silt": silt,
        "soc": _fallback_metric(latitude, longitude, 6.5, 5.0),
    }


def serialize_soil_profile(profile: SoilProfile) -> Dict[str, Any]:
    return {
        "id": profile.id,
        "farm_id": profile.farm_id,
        "latitude": profile.latitude,
        "longitude": profile.longitude,
        "source": profile.source,
        "source_ref": profile.source_ref,
        "fetched_at": profile.fetched_at,
        "status": (profile.derived_properties or {}).get("status", "ready"),
        "topsoil_metrics": profile.topsoil_metrics or {},
        "derived_properties": profile.derived_properties or {},
        "raw_payload": profile.raw_payload or {},
    }


def upsert_soil_profile(
    db: Session,
    latitude: float,
    longitude: float,
    *,
    farm: Optional[Farm] = None,
    force_refresh: bool = False,
    label: Optional[str] = None,
) -> SoilProfile:
    reference = _source_ref(latitude, longitude)
    profile = None
    if farm is not None:
        profile = db.query(SoilProfile).filter(SoilProfile.farm_id == farm.id).first()
    if profile is None:
        profile = db.query(SoilProfile).filter(SoilProfile.source_ref == reference, SoilProfile.farm_id.is_(None)).first()

    if profile is not None and not force_refresh:
        if farm is not None and profile.farm_id != farm.id:
            profile.farm_id = farm.id
            db.add(profile)
            db.commit()
            db.refresh(profile)
        return profile

    payload: Dict[str, Any]
    metrics: Dict[str, Optional[float]]
    source = "SoilGrids"
    status = "ready"
    try:
        payload = fetch_soilgrids_profile(latitude=latitude, longitude=longitude)
        metrics = normalize_topsoil_metrics(payload)
    except Exception as exc:
        if profile is not None:
            if farm is not None and profile.farm_id != farm.id:
                profile.farm_id = farm.id
                db.add(profile)
                db.commit()
                db.refresh(profile)
            return profile
        payload = {"error": str(exc), "provider": "SoilGrids", "fallback": True}
        metrics = fallback_topsoil_metrics(latitude, longitude)
        source = "SoilGrids-fallback"
        status = "upstream_unavailable"

    derived = derive_soil_properties(metrics)
    derived["label"] = label or (farm.name if farm is not None else None)
    derived["status"] = status

    if profile is None:
        profile = SoilProfile(
            farm_id=farm.id if farm is not None else None,
            latitude=latitude,
            longitude=longitude,
            source="SoilGrids",
            source_ref=reference,
        )

    profile.farm_id = farm.id if farm is not None else profile.farm_id
    profile.latitude = latitude
    profile.longitude = longitude
    profile.source = source
    profile.source_ref = reference
    profile.fetched_at = datetime.now(timezone.utc).isoformat()
    profile.raw_payload = payload
    profile.topsoil_metrics = metrics
    profile.derived_properties = derived

    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def upsert_farm_soil_profile(db: Session, farm: Farm, force_refresh: bool = False) -> Optional[SoilProfile]:
    coordinates = _extract_point_from_polygon(farm.polygon)
    latitude = _safe_float(coordinates.get("latitude"), None)
    longitude = _safe_float(coordinates.get("longitude"), None)
    if latitude is None or longitude is None:
        return None
    return upsert_soil_profile(db, latitude, longitude, farm=farm, force_refresh=force_refresh)