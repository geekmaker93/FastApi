import os
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv

load_dotenv()


HTTP_TIMEOUT_SECONDS = 8
NOAA_USER_AGENT = "crop-backend/1.0 (agriculture assistant)"
NOAA_SOURCE = "NOAA NWS"
NASA_SOURCE = "NASA POWER"
ESA_SOURCE = "ESA Copernicus"
TREFLE_SOURCE = "Trefle"
TREFLE_API_KEY = os.getenv("TREFLE_API_KEY", "").strip()
PERENUAL_SOURCE = "Perenual"
PERENUAL_API_KEY = os.getenv("PERENUAL_API_KEY", "").strip()


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _error_payload(source: str, detail: str) -> Dict[str, Any]:
    return {
        "source": source,
        "available": False,
        "detail": detail,
    }


def _nasa_summary(parameter_data: Dict[str, Any]) -> Dict[str, Any]:
    t2m = _numeric_values(parameter_data.get("T2M") or {})
    rh2m = _numeric_values(parameter_data.get("RH2M") or {})
    precip = _numeric_values(parameter_data.get("PRECTOTCORR") or {})
    solar = _numeric_values(parameter_data.get("ALLSKY_SFC_SW_DWN") or {})
    return {
        "avg_temp_c": round(sum(t2m) / len(t2m), 2) if t2m else None,
        "avg_humidity_percent": round(sum(rh2m) / len(rh2m), 2) if rh2m else None,
        "total_precip_mm": round(sum(precip), 2) if precip else None,
        "avg_solar_kwh_m2_day": round(sum(solar) / len(solar), 2) if solar else None,
        "days_count": max(len(t2m), len(rh2m), len(precip), len(solar)),
    }


def _parse_wind_speed_kph(value: str) -> Optional[float]:
    if not value:
        return None
    digits: List[float] = []
    cleaned = value.replace("mph", "").replace("MPH", "").replace("to", " ")
    for token in cleaned.split():
        parsed = _safe_float(token, None)
        if parsed is not None:
            digits.append(parsed)
    if not digits:
        return None
    mph = sum(digits) / len(digits)
    return round(mph * 1.60934, 2)


def fetch_noaa_nws_snapshot(latitude: float, longitude: float) -> Dict[str, Any]:
    """Fetch NOAA NWS forecast point data (best coverage in the US and territories)."""
    headers = {
        "User-Agent": NOAA_USER_AGENT,
        "Accept": "application/geo+json",
    }
    points_url = f"https://api.weather.gov/points/{latitude},{longitude}"

    try:
        points_response = requests.get(points_url, headers=headers, timeout=HTTP_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        return _error_payload(NOAA_SOURCE, f"request_failed: {exc}")

    if points_response.status_code == 404:
        return _error_payload(
            NOAA_SOURCE,
            "coverage_unavailable_for_coordinates (NOAA NWS is primarily US-focused)",
        )
    if not points_response.ok:
        return _error_payload(NOAA_SOURCE, f"points_http_{points_response.status_code}")

    points_data = points_response.json()
    props = points_data.get("properties") or {}
    forecast_hourly_url = props.get("forecastHourly") or props.get("forecast")
    if not forecast_hourly_url:
        return _error_payload(NOAA_SOURCE, "missing_forecast_url")

    try:
        forecast_response = requests.get(forecast_hourly_url, headers=headers, timeout=HTTP_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        return _error_payload(NOAA_SOURCE, f"forecast_request_failed: {exc}")

    if not forecast_response.ok:
        return _error_payload(NOAA_SOURCE, f"forecast_http_{forecast_response.status_code}")

    forecast_data = forecast_response.json()
    periods = ((forecast_data.get("properties") or {}).get("periods") or [])
    current = periods[0] if periods else {}

    return {
        "source": NOAA_SOURCE,
        "available": True,
        "coverage": "US and territories",
        "office": props.get("cwa"),
        "grid": {
            "grid_id": props.get("gridId"),
            "x": props.get("gridX"),
            "y": props.get("gridY"),
        },
        "current": {
            "period": current.get("name"),
            "start": current.get("startTime"),
            "end": current.get("endTime"),
            "temperature": current.get("temperature"),
            "temperature_unit": current.get("temperatureUnit"),
            "wind_speed_kph": _parse_wind_speed_kph(str(current.get("windSpeed") or "")),
            "wind_direction": current.get("windDirection"),
            "forecast": current.get("shortForecast"),
        },
    }


def _nasa_dates(start_date: Optional[str], end_date: Optional[str]) -> Dict[str, str]:
    if start_date and end_date:
        return {
            "start": start_date.replace("-", ""),
            "end": end_date.replace("-", ""),
        }

    end = datetime.now(timezone.utc).date() - timedelta(days=1)
    start = end - timedelta(days=6)
    return {
        "start": start.strftime("%Y%m%d"),
        "end": end.strftime("%Y%m%d"),
    }


def _numeric_values(values: Dict[str, Any]) -> List[float]:
    parsed: List[float] = []
    for value in values.values():
        number = _safe_float(value, None)
        if number is None or number <= -999.0:
            continue
        parsed.append(number)
    return parsed


def fetch_nasa_power_agro(latitude: float, longitude: float, start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict[str, Any]:
    """Fetch NASA POWER daily agro-climate values (global coverage)."""
    date_window = _nasa_dates(start_date, end_date)
    params = {
        "parameters": "T2M,RH2M,PRECTOTCORR,ALLSKY_SFC_SW_DWN",
        "community": "AG",
        "longitude": longitude,
        "latitude": latitude,
        "start": date_window["start"],
        "end": date_window["end"],
        "format": "JSON",
    }

    try:
        response = requests.get("https://power.larc.nasa.gov/api/temporal/daily/point", params=params, timeout=HTTP_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        return _error_payload(NASA_SOURCE, f"request_failed: {exc}")

    if not response.ok:
        return _error_payload(NASA_SOURCE, f"http_{response.status_code}")

    data = response.json()
    parameter_data = ((data.get("properties") or {}).get("parameter") or {})

    return {
        "source": NASA_SOURCE,
        "available": True,
        "coverage": "global",
        "date_range": date_window,
        "summary": _nasa_summary(parameter_data),
        "parameters": {
            "T2M": parameter_data.get("T2M") or {},
            "RH2M": parameter_data.get("RH2M") or {},
            "PRECTOTCORR": parameter_data.get("PRECTOTCORR") or {},
            "ALLSKY_SFC_SW_DWN": parameter_data.get("ALLSKY_SFC_SW_DWN") or {},
        },
    }


def _extract_cloud_cover(attributes: Any) -> Optional[float]:
    if not isinstance(attributes, list):
        return None
    for item in attributes:
        if not isinstance(item, dict):
            continue
        name = str(item.get("Name") or item.get("name") or "").lower()
        if "cloud" not in name:
            continue
        value = _safe_float(item.get("Value") or item.get("value"), None)
        if value is not None:
            return value
    return None

def fetch_perenual_plants(query: Optional[str] = None, limit: int = 10) -> Dict[str, Any]:
    """Fetch crop/plant care info from Perenual API."""
    params: Dict[str, Any] = {
        "page": 1,
    }
    if PERENUAL_API_KEY:
        params["key"] = PERENUAL_API_KEY
    if query and query.strip():
        params["q"] = query.strip()

    headers = {
        "Accept": "application/json",
        "User-Agent": NOAA_USER_AGENT,
    }

    try:
        response = requests.get("https://perenual.com/api/species-list", params=params, headers=headers, timeout=HTTP_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        return _error_payload(PERENUAL_SOURCE, f"request_failed: {exc}")

    if not response.ok:
        return _error_payload(PERENUAL_SOURCE, f"http_{response.status_code}")

    payload = response.json() if response.content else {}
    raw_data = payload.get("data") if isinstance(payload, dict) else []
    if not isinstance(raw_data, list):
        return _error_payload(PERENUAL_SOURCE, "unexpected_response_schema")

    plants: List[Dict[str, Any]] = []
    for item in raw_data[: max(1, min(limit, 50))]:
        if isinstance(item, dict):
            plants.append(
                {
                    "id": item.get("id"),
                    "common_name": item.get("common_name"),
                    "scientific_name": item.get("scientific_name"),
                    "care_level": item.get("care_level"),
                    "watering": item.get("watering"),
                    "sunlight": item.get("sunlight"),
                    "growth_rate": item.get("growth_rate"),
                    "indoor": item.get("indoor"),
                    "image_url": item.get("default_image", {}).get("medium_url") if isinstance(item.get("default_image"), dict) else None,
                }
            )

    return {
        "source": PERENUAL_SOURCE,
        "available": True,
        "coverage": "global plant care database",
        "query": (query or "").strip() or None,
        "results_count": len(plants),
        "plants": plants,
    }


def _normalize_trefle_item(item: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    return {
        "id": item.get("id"),
        "common_name": item.get("common_name"),
        "scientific_name": item.get("scientific_name"),
        "family": item.get("family"),
        "genus": item.get("genus"),
        "image_url": item.get("image_url"),
        "year": item.get("year"),
        "bibliography": item.get("bibliography"),
    }


def fetch_trefle_plants(query: Optional[str] = None, limit: int = 5) -> Dict[str, Any]:
    """Fetch plant knowledge from Trefle using crop query text."""
    if not TREFLE_API_KEY:
        return _error_payload(TREFLE_SOURCE, "missing_api_key")

    params: Dict[str, Any] = {
        "token": TREFLE_API_KEY,
        "page_size": max(1, min(limit, 20)),
    }
    if query and query.strip():
        params["q"] = query.strip()

    headers = {
        "Accept": "application/json",
        "User-Agent": NOAA_USER_AGENT,
    }

    try:
        response = requests.get("https://trefle.io/api/v1/plants/search", params=params, headers=headers, timeout=HTTP_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        return _error_payload(TREFLE_SOURCE, f"request_failed: {exc}")

    if not response.ok:
        return _error_payload(TREFLE_SOURCE, f"http_{response.status_code}")

    payload = response.json() if response.content else {}
    raw_items = payload.get("data") if isinstance(payload, dict) else []
    if not isinstance(raw_items, list):
        return _error_payload(TREFLE_SOURCE, "unexpected_response_schema")

    plants = [_normalize_trefle_item(item) for item in raw_items[: max(1, min(limit, 20))]]

    return {
        "source": TREFLE_SOURCE,
        "available": True,
        "coverage": "global botanical and plant taxonomy",
        "query": (query or "").strip() or None,
        "results_count": len(plants),
        "plants": plants,
    }


def _build_crop_knowledge_card(crop_query: Optional[str], perenual: Dict[str, Any], trefle: Dict[str, Any]) -> Dict[str, Any]:
    perenual_plant = ((perenual or {}).get("plants") or [None])[0] if isinstance(perenual, dict) else None
    trefle_plant = ((trefle or {}).get("plants") or [None])[0] if isinstance(trefle, dict) else None

    if not isinstance(perenual_plant, dict):
        perenual_plant = {}
    if not isinstance(trefle_plant, dict):
        trefle_plant = {}

    available = bool((perenual or {}).get("available") or (trefle or {}).get("available"))

    return {
        "available": available,
        "crop_query": (crop_query or "").strip() or None,
        "perenual_care_guidance": {
            "common_name": perenual_plant.get("common_name"),
            "care_level": perenual_plant.get("care_level"),
            "watering": perenual_plant.get("watering"),
            "sunlight": perenual_plant.get("sunlight"),
            "growth_rate": perenual_plant.get("growth_rate"),
            "indoor_suitable": perenual_plant.get("indoor"),
        },
        "trefle_taxonomy": {
            "scientific_name": trefle_plant.get("scientific_name"),
            "family": trefle_plant.get("family"),
            "genus": trefle_plant.get("genus"),
        },
        "reasoning_use": [
            "Use Perenual care guidance for planting/cultivation advice and watering/sunlight requirements.",
            "Use Trefle taxonomy for scientific classification and crop family identification.",
        ],
    }


def fetch_crop_knowledge_bundle(crop_query: Optional[str], limit: int = 5) -> Dict[str, Any]:
    with ThreadPoolExecutor(max_workers=2) as executor:
        perenual_future = executor.submit(fetch_perenual_plants, query=crop_query, limit=limit)
        trefle_future = executor.submit(fetch_trefle_plants, query=crop_query, limit=limit)

        perenual = perenual_future.result()
        trefle = trefle_future.result()

    available_count = sum(1 for source in (perenual, trefle) if source.get("available"))
    return {
        "sources": {
            "perenual": perenual,
            "trefle": trefle,
        },
        "crop_knowledge": _build_crop_knowledge_card(crop_query, perenual, trefle),
        "availability": {
            "available_count": available_count,
            "total_sources": 2,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def fetch_esa_sentinel2_scene(latitude: float, longitude: float) -> Dict[str, Any]:
    """Fetch latest ESA Sentinel-2 scene metadata from Copernicus Data Space catalogue."""
    filter_expr = (
        "Collection/Name eq 'SENTINEL-2' "
        f"and OData.CSC.Intersects(area=geography'SRID=4326;POINT({longitude} {latitude})')"
    )
    params = {
        "$filter": filter_expr,
        "$orderby": "ContentDate/Start desc",
        "$top": 1,
        "$expand": "Attributes",
    }

    try:
        response = requests.get("https://catalogue.dataspace.copernicus.eu/odata/v1/Products", params=params, timeout=HTTP_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        return _error_payload(ESA_SOURCE, f"request_failed: {exc}")

    if not response.ok:
        return _error_payload(ESA_SOURCE, f"http_{response.status_code}")

    data = response.json()
    values = data.get("value") or []
    if not values:
        return _error_payload(ESA_SOURCE, "no_scene_found_for_location")

    latest = values[0]
    content = latest.get("ContentDate") or {}

    return {
        "source": "ESA Copernicus Sentinel-2",
        "available": True,
        "coverage": "global",
        "scene": {
            "id": latest.get("Id"),
            "name": latest.get("Name"),
            "collection": (latest.get("Collection") or {}).get("Name"),
            "start": content.get("Start"),
            "end": content.get("End"),
            "cloud_cover_percent": _extract_cloud_cover(latest.get("Attributes")),
        },
    }


def fetch_external_sources_bundle(
    latitude: float,
    longitude: float,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    crop_query: Optional[str] = None,
) -> Dict[str, Any]:
    with ThreadPoolExecutor(max_workers=5) as executor:
        nasa_future = executor.submit(
            fetch_nasa_power_agro,
            latitude=latitude,
            longitude=longitude,
            start_date=start_date,
            end_date=end_date,
        )
        noaa_future = executor.submit(
            fetch_noaa_nws_snapshot,
            latitude=latitude,
            longitude=longitude,
        )
        esa_future = executor.submit(
            fetch_esa_sentinel2_scene,
            latitude=latitude,
            longitude=longitude,
        )
        perenual_future = executor.submit(
            fetch_perenual_plants,
            query=crop_query,
            limit=10,
        )
        trefle_future = executor.submit(
            fetch_trefle_plants,
            query=crop_query,
            limit=5,
        )

        nasa = nasa_future.result()
        noaa = noaa_future.result()
        esa = esa_future.result()
        perenual = perenual_future.result()
        trefle = trefle_future.result()

    crop_knowledge = _build_crop_knowledge_card(crop_query, perenual, trefle)

    available_count = sum(1 for source in (nasa, noaa, esa, perenual, trefle) if source.get("available"))
    return {
        "coordinates": {
            "latitude": latitude,
            "longitude": longitude,
        },
        "sources": {
            "nasa": nasa,
            "noaa": noaa,
            "esa": esa,
            "perenual": perenual,
            "trefle": trefle,
        },
        "crop_knowledge": crop_knowledge,
        "availability": {
            "available_count": available_count,
            "total_sources": 5,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }