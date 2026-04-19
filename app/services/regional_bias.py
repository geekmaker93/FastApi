from __future__ import annotations

from typing import Any, Dict, List


def apply_regional_bias(crops: List[Dict[str, Any]], region_profile: Dict[str, Any], weather: Dict[str, Any]) -> List[Dict[str, Any]]:
    boosted: List[Dict[str, Any]] = []
    preferred = {str(name).strip().lower() for name in region_profile.get("preferred_crops", [])}
    min_temp = float((region_profile.get("avg_temp_range") or (0, 0))[0])
    weather_temp = float(weather.get("temperature", 0) or 0)

    for crop in crops:
        if not isinstance(crop, dict):
            continue

        updated = dict(crop)
        score = float(updated.get("score", 0) or 0)
        boosts: List[str] = []
        crop_name = str(updated.get("name") or "").strip().lower()

        if crop_name in preferred:
            score += 3
            boosts.append("regional_preferred_crop")

        if weather_temp >= min_temp:
            score += 1
            boosts.append("regional_temperature_alignment")

        updated["score"] = int(round(score))
        if boosts:
            updated["regional_boosts"] = boosts

        boosted.append(updated)

    return sorted(boosted, key=lambda item: item.get("score", 0), reverse=True)
