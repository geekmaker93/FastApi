import requests
from datetime import datetime, timezone
from app.core.config import FARMONAUT_API_KEY, FARMONAUT_BASE_URL

def get_soil_data(polygon_id: str):
    """Fetch soil data from Farmonaut API with timeout"""
    url = f"{FARMONAUT_BASE_URL}/soil"
    params = {
        "polygon_id": polygon_id,
        "api_key": FARMONAUT_API_KEY
    }
    try:
        res = requests.get(url, params=params, timeout=5)
        res.raise_for_status()
        return res.json()
    except Exception:
        return {
            "polygon_id": polygon_id,
            "soil_type": "loamy",
            "ph": 6.5,
            "nitrogen": 45,
            "phosphorus": 30,
            "potassium": 200,
            "provider": "fallback"
        }


def get_weather_data(lat: float, lon: float):
    """Fetch weather data from Farmonaut API with timeout"""
    url = f"{FARMONAUT_BASE_URL}/weather"
    params = {
        "latitude": lat,
        "longitude": lon,
        "api_key": FARMONAUT_API_KEY
    }
    try:
        res = requests.get(url, params=params, timeout=5)  # Reduced timeout
        res.raise_for_status()
        return res.json()
    except Exception:
        # Quick fallback without retrying external APIs
        return {
            "latitude": lat,
            "longitude": lon,
            "temperature": 25.0,
            "humidity": 65.0,
            "precipitation": 0.0,
            "wind_speed": 5.0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "provider": "fallback"
        }


def get_vegetation_indices(polygon_id: str):
    """Fetch vegetation indices from Farmonaut API with timeout"""
    url = f"{FARMONAUT_BASE_URL}/vegetation"
    params = {
        "polygon_id": polygon_id,
        "api_key": FARMONAUT_API_KEY
    }
    try:
        res = requests.get(url, params=params, timeout=5)
        res.raise_for_status()
        return res.json()
    except Exception:
        return {
            "polygon_id": polygon_id,
            "ndvi": 0.5,
            "evi": 0.45,
            "lai": 3.0,
            "provider": "fallback"
        }


def get_historical_avg_rainfall(month: int):
    # placeholder — later replaced with real Agro Weather history
    historical_monthly_avg = {
        1: 78, 2: 65, 3: 70, 4: 90,
        5: 110, 6: 140, 7: 160,
        8: 155, 9: 145, 10: 130,
        11: 105, 12: 85
    }
    return historical_monthly_avg.get(month, 100)
