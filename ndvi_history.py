"""Copernicus Data Space NDVI statistics helpers."""
import os
from datetime import date
from typing import Any, Dict

import requests


_TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
_STATISTICS_URL = "https://sh.dataspace.copernicus.eu/api/v1/statistics"
_NDVI_EVALSCRIPT = """//VERSION=3
function setup() { return {input: [\"B04\", \"B08\", \"dataMask\"], output: [{id: \"ndvi\", bands: 1}, {id: \"dataMask\", bands: 1}]}; }
function evaluatePixel(sample) { return {ndvi: [(sample.B08 - sample.B04) / (sample.B08 + sample.B04)], dataMask: [sample.dataMask]}; }"""


def _access_token() -> str:
    client_id = os.getenv("COPERNICUS_CLIENT_ID", "").strip()
    client_secret = os.getenv("COPERNICUS_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise RuntimeError("COPERNICUS_CLIENT_ID and COPERNICUS_CLIENT_SECRET must be configured")

    response = requests.post(
        _TOKEN_URL,
        data={"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret},
        timeout=20,
    )
    response.raise_for_status()
    token = response.json().get("access_token")
    if not token:
        raise RuntimeError("Copernicus token response did not contain an access token")
    return token


def get_historical_ndvi(lat, lon, start_year=2020, end_year=2024):
    """Return aggregate Sentinel-2 L2A NDVI statistics for a point."""
    start_date = date(int(start_year), 1, 1)
    end_date = date(int(end_year), 12, 31)
    payload: Dict[str, Any] = {
        "input": {
            "bounds": {"geometry": {"type": "Point", "coordinates": [float(lon), float(lat)]}},
            "data": [{"type": "sentinel-2-l2a", "dataFilter": {"maxCloudCoverage": 30}}],
        },
        "aggregation": {
            "timeRange": {"from": f"{start_date.isoformat()}T00:00:00Z", "to": f"{end_date.isoformat()}T23:59:59Z"},
            "aggregationInterval": {"of": "P1D"},
            "resx": 10,
            "resy": 10,
        },
        "evalscript": _NDVI_EVALSCRIPT,
    }
    response = requests.post(
        _STATISTICS_URL,
        headers={"Authorization": f"Bearer {_access_token()}"},
        json=payload,
        timeout=45,
    )
    response.raise_for_status()
    intervals = response.json().get("data", [])
    statistics = [
        entry["outputs"]["ndvi"]["bands"]["B0"]["stats"]
        for entry in intervals
        if entry.get("outputs", {}).get("ndvi", {}).get("bands", {}).get("B0", {}).get("stats", {}).get("sampleCount", 0)
    ]
    if not statistics:
        raise RuntimeError("No cloud-free Sentinel-2 NDVI observations found for this location and period")

    sample_count = sum(item["sampleCount"] for item in statistics)
    return {
        "min": min(item["min"] for item in statistics),
        "max": max(item["max"] for item in statistics),
        "mean": sum(item["mean"] * item["sampleCount"] for item in statistics) / sample_count,
    }


def normalize_ndvi(current_ndvi, hist_min, hist_max):
    if hist_max == hist_min:
        return 0.5
    return round((current_ndvi - hist_min) / (hist_max - hist_min), 2)