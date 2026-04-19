import requests
import ee
import os
from dotenv import load_dotenv

load_dotenv()

# ----------------------------
#  CONFIGURATION
# ----------------------------
AGRO_API_KEY = os.getenv("AGRO_API_KEY", "YOUR_AGROMONITORING_API_KEY")

# ----------------------------
# INITIALIZE EARTH ENGINE
# ----------------------------
try:
    project_id = os.getenv("GEE_PROJECT_ID", "ee-cropbackend")
    ee.Initialize(project=project_id, opt_url='https://earthengine-highvolume.googleapis.com')
except Exception as e:
    print(f"Warning: Earth Engine initialization failed: {e}")
    print("Will use AgroMonitoring data only.")

# ----------------------------
# AGROMONITORING FUNCTIONS
# ----------------------------
def get_agro_ndvi(lat, lon):
    """Get real-time NDVI from AgroMonitoring"""
    url = "https://api.agromonitoring.com/agro/1.0/ndvi"
    params = {"lat": lat, "lon": lon, "appid": AGRO_API_KEY}
    try:
        response = requests.get(url, params=params, timeout=8)
        if response.status_code != 200:
            print("AgroMonitoring API error:", response.text)
            return None
        data = response.json()
        if "data" not in data or len(data["data"]) == 0:
            return None
        return data["data"][0]["value"]
    except requests.exceptions.Timeout:
        print("AgroMonitoring API timeout after 8s")
        return None
    except Exception as e:
        print(f"AgroMonitoring API error: {e}")
        return None

def get_agro_weather(lat, lon):
    """Get basic weather from AgroMonitoring"""
    url = f"https://api.agromonitoring.com/agro/1.0/weather?lat={lat}&lon={lon}&appid={AGRO_API_KEY}"
    try:
        response = requests.get(url, timeout=8)
        if response.status_code != 200:
            print("Weather API error:", response.text)
            return None
        data = response.json()
        return {
            "temperature": data["main"]["temp"],
            "humidity": data["main"]["humidity"],
            "precipitation": data["rain"]["1h"] if "rain" in data else 0
        }
    except requests.exceptions.Timeout:
        print("Weather API timeout after 8s")
        return None
    except Exception as e:
        print(f"Weather API error: {e}")
        return None

# ----------------------------
# EARTH ENGINE FUNCTIONS
# ----------------------------
def get_historical_ndvi(lat, lon, start_date, end_date):
    """Returns average NDVI and NDVI trend"""
    try:
        point = ee.Geometry.Point(lon, lat)
        collection = (
            ee.ImageCollection("COPERNICUS/S2_SR")
            .filterBounds(point)
            .filterDate(start_date, end_date)
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20))
        )
        if collection.size().getInfo() == 0:
            return {"ndvi_avg": None, "ndvi_trend": None}

        def add_ndvi(img):
            ndvi = img.normalizedDifference(["B8", "B4"]).rename("NDVI")
            return img.addBands(ndvi)

        ndvi_collection = collection.map(add_ndvi)
        ndvi_mean = ndvi_collection.select("NDVI").mean()
        ndvi_avg = ndvi_mean.reduceRegion(
            reducer=ee.Reducer.mean(), geometry=point, scale=10
        ).getInfo()["NDVI"]

        ndvi_list = ndvi_collection.select("NDVI").aggregate_array("NDVI").getInfo()
        ndvi_trend = 0 if len(ndvi_list) < 2 else ndvi_list[-1] - ndvi_list[0]

        return {"ndvi_avg": ndvi_avg, "ndvi_trend": ndvi_trend}
    except Exception as e:
        print(f"Earth Engine unavailable: {e}")
        return {"ndvi_avg": 0.6, "ndvi_trend": 0.05}

# ----------------------------
# YIELD ENGINE FUNCTION (from Step 4)
# ----------------------------
def calculate_yield(ndvi_now, ndvi_avg, ndvi_trend):
    """Calculate crop yield score"""
    def normalize_ndvi(ndvi):
        return max(0, min((ndvi - 0.2) / (0.9 - 0.2), 1))

    ndvi_now_n = normalize_ndvi(ndvi_now)
    ndvi_avg_n = normalize_ndvi(ndvi_avg)
    stress = ndvi_now_n - ndvi_avg_n

    score = ndvi_now_n * 0.6 + ndvi_trend * 0.25 + stress * 0.15

    return {
        "yield_score": round(score, 3),
        "yield_percent": round(score * 100, 2),
        "stress_level": round(stress, 3)
    }

# ----------------------------
# MAIN PIPELINE FUNCTION
# ----------------------------
def run_yield_pipeline(lat, lon, start_date, end_date):
    ndvi_now = get_agro_ndvi(lat, lon)
    weather = get_agro_weather(lat, lon)
    historical = get_historical_ndvi(lat, lon, start_date, end_date)

    if ndvi_now is None or historical["ndvi_avg"] is None:
        print("Error: Missing NDVI data.")
        return None

    yield_result = calculate_yield(
        ndvi_now=ndvi_now,
        ndvi_avg=historical["ndvi_avg"],
        ndvi_trend=historical["ndvi_trend"]
    )

    return {
        "yield": yield_result,
        "ndvi_now": ndvi_now,
        "historical": historical,
        "weather": weather
    }

# ----------------------------
# TEST THE PIPELINE
# ----------------------------
if __name__ == "__main__":
    lat = 18.0179
    lon = -76.8099
    start_date = "2024-01-01"
    end_date = "2024-06-30"

    result = run_yield_pipeline(lat, lon, start_date, end_date)
    print(result)