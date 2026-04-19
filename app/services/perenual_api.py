from __future__ import annotations

from typing import Any, Dict, List

from app.services.external_data_sources import fetch_perenual_plants


def search_crops(query: str = "fruit", limit: int = 10) -> List[Dict[str, Any]]:
    payload = fetch_perenual_plants(query=query, limit=limit)
    plants = payload.get("plants") if isinstance(payload, dict) else []
    return plants if isinstance(plants, list) else []
