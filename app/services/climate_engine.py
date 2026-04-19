from __future__ import annotations

from typing import Any, Dict


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def detect_climate_pattern(weather: Dict[str, Any]) -> str:
    humidity = _safe_float(weather.get("humidity", 0), 0.0)
    rainfall = _safe_float(weather.get("rainfall", 0), 0.0)

    if humidity > 75:
        return "humid"

    if rainfall < 2:
        return "dry"

    return "normal"
