from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.services.climate_engine import detect_climate_pattern
from app.services.crop_normalizer import normalize_crop
from app.services.perenual_api import search_crops
from app.services.region_mapper import get_region
from app.services.region_profiles import REGION_PROFILES
from app.services.regional_bias import apply_regional_bias


def _safe_float(value: Any, default: Optional[float] = 0.0) -> Optional[float]:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def score_crop(crop: Dict[str, Any], farm: Dict[str, Any]) -> int:
    score = 0

    temperature = _safe_float(farm.get("temperature"), 0.0)
    sun_hours = _safe_float(farm.get("sun_hours"), 0.0)
    humidity = _safe_float(farm.get("humidity"), 0.0)

    if 20 <= temperature <= 35:
        score += 30

    sunlight = [str(s).lower() for s in (crop.get("sunlight") or [])]
    if "full sun" in sunlight and sun_hours >= 6:
        score += 30

    watering = str(crop.get("watering") or "").lower()
    if watering == "medium":
        score += 20
    if watering == "high" and humidity > 60:
        score += 20

    cycle = str(crop.get("cycle") or "").lower()
    if "perennial" not in cycle:
        score += 20

    return score


def _reason_crop_fit(crop: Dict[str, Any], farm: Dict[str, Any]) -> str:
    temperature = _safe_float(farm.get("temperature"), 0.0)
    sun_hours = _safe_float(farm.get("sun_hours"), 0.0)
    humidity = _safe_float(farm.get("humidity"), 0.0)
    watering = str(crop.get("watering") or "").lower()
    sunlight = [str(s).lower() for s in (crop.get("sunlight") or [])]

    reasons: List[str] = []
    if 20 <= temperature <= 35:
        reasons.append("temperature is in the optimal tropical range")
    if "full sun" in sunlight and sun_hours >= 6:
        reasons.append("sunlight availability matches full-sun needs")
    if watering == "medium":
        reasons.append("watering demand is moderate")
    if watering == "high" and humidity > 60:
        reasons.append("high humidity supports high-water-demand crops")
    cycle = str(crop.get("cycle") or "").lower()
    if "perennial" not in cycle:
        reasons.append("shorter cycle can give quicker returns")

    if not reasons:
        return "fit estimated from available farm signals and general agronomy"
    return "; ".join(reasons)


def get_top_crops(farm: Dict[str, Any], query: str = "fruit") -> List[Dict[str, Any]]:
    raw_crops = search_crops(query=query, limit=10)
    scored: List[Dict[str, Any]] = []

    for raw in raw_crops:
        if not isinstance(raw, dict):
            continue
        crop = normalize_crop(raw)
        score = score_crop(crop, farm)
        scored.append(
            {
                "name": crop["name"],
                "score": score,
                "reason": _reason_crop_fit(crop, farm),
                "data": crop,
            }
        )

    lat = _safe_float(farm.get("latitude"), None)
    lon = _safe_float(farm.get("longitude"), None)
    region = get_region(lat, lon)
    region_profile = REGION_PROFILES.get(region)
    weather_snapshot = {
        "temperature": _safe_float(farm.get("temperature"), 0.0),
        "humidity": _safe_float(farm.get("humidity"), 0.0),
        "rainfall": _safe_float(farm.get("rainfall"), 0.0),
    }
    climate_pattern = detect_climate_pattern(weather_snapshot)

    if region_profile:
        scored = apply_regional_bias(scored, region_profile, weather_snapshot)
        for item in scored:
            if isinstance(item, dict):
                item["region"] = region
                item["climate_pattern"] = climate_pattern

    scored.sort(key=lambda item: item.get("score", 0), reverse=True)
    return scored[:3]
