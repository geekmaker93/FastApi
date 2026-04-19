from __future__ import annotations

from typing import Any, Dict, List


def _as_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def normalize_crop(api_crop: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": api_crop.get("common_name") or api_crop.get("scientific_name") or "Unknown crop",
        "sunlight": _as_list(api_crop.get("sunlight", [])),
        "watering": str(api_crop.get("watering", "medium") or "medium").strip().lower(),
        "cycle": str(api_crop.get("cycle", "") or "").strip(),
    }
