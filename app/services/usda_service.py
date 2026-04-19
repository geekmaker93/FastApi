import os
from typing import Any, Dict

import requests

USDA_API_KEY = os.getenv("USDA_API_KEY")
BASE_URL = "https://quickstats.nass.usda.gov/api/api_GET/"


def get_crop_data(crop_name: str, state: str = "") -> Dict[str, Any]:
    if not crop_name or not str(crop_name).strip():
        return {
            "available": False,
            "error": "Missing crop name",
        }

    if not USDA_API_KEY:
        return {
            "available": False,
            "error": "USDA_API_KEY is not set",
        }

    params = {
        "key": USDA_API_KEY,
        "commodity_desc": str(crop_name).upper(),
        "year__GE": 2020,
        "format": "JSON",
    }

    if state:
        params["state_name"] = state

    try:
        res = requests.get(BASE_URL, params=params, timeout=10)
        res.raise_for_status()
        data = res.json()
        rows = data.get("data", []) if isinstance(data, dict) else []

        return {
            "available": True,
            "count": len(rows),
            "data": rows[:5],
        }
    except Exception as e:
        return {
            "available": False,
            "error": str(e),
        }
