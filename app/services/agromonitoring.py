import requests
from app.core.config import AGRO_API_KEY, AGRO_BASE_URL


def _normalize_polygon(coordinates: list):
    normalized = []
    for point in coordinates:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        a, b = float(point[0]), float(point[1])
        if abs(a) <= 90 and abs(b) > 90:
            lat, lon = a, b
            normalized.append([lon, lat])
        else:
            normalized.append([a, b])

    if len(normalized) >= 3 and normalized[0] != normalized[-1]:
        normalized.append(normalized[0])
    return normalized

def create_polygon(name: str, coordinates: list):
    url = f"{AGRO_BASE_URL}/polygons"
    polygon_coords = _normalize_polygon(coordinates)
    payload = {
        "name": name,
        "geo_json": {
            "type": "Feature",
            "properties": {},
            "geometry": {
                "type": "Polygon",
                "coordinates": [polygon_coords]
            }
        }
    }
    params = {"appid": AGRO_API_KEY}
    try:
        res = requests.post(url, json=payload, params=params, timeout=8)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        return {"name": name, "id": "unknown", "error": str(e), "provider": "fallback"}


def get_polygon(polygon_id: str):
    url = f"{AGRO_BASE_URL}/polygons/{polygon_id}"
    params = {"appid": AGRO_API_KEY}
    try:
        res = requests.get(url, params=params, timeout=8)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        return {"id": polygon_id, "error": str(e), "provider": "fallback"}


def get_polygon_coordinates(polygon: dict):
    geometry = polygon.get("geo_json", {}).get("geometry", {})
    coordinates = geometry.get("coordinates", [])
    if not coordinates or not isinstance(coordinates, list):
        raise ValueError("Polygon geometry coordinates not found")

    ring = coordinates[0] if coordinates else []
    if not ring or not isinstance(ring, list):
        raise ValueError("Polygon ring coordinates not found")

    normalized = []
    for point in ring:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        lon, lat = float(point[0]), float(point[1])
        normalized.append((lon, lat))

    if len(normalized) < 3:
        raise ValueError("Polygon has insufficient coordinate points")

    return normalized


def get_ndvi_history(polygon_id: str):
    url = f"{AGRO_BASE_URL}/ndvi/history"
    params = {
        "polyid": polygon_id,
        "appid": AGRO_API_KEY
    }
    try:
        res = requests.get(url, params=params, timeout=8)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        return {"polygon_id": polygon_id, "history": [], "error": str(e), "provider": "fallback"}
