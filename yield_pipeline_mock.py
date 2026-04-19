"""
Yield Pipeline - Mock version for testing
Uses simulated data when APIs are unavailable
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ----------------------------
#  CONFIGURATION
# ----------------------------
AGRO_API_KEY = os.getenv("AGRO_API_KEY", "YOUR_AGROMONITORING_API_KEY")

# ----------------------------
# MOCK AGROMONITORING FUNCTIONS
# ----------------------------
def get_agro_ndvi(lat, lon):
    """Get simulated NDVI from AgroMonitoring"""
    # Simulate NDVI value between 0.3 and 0.9
    import random
    return round(random.uniform(0.5, 0.85), 3)

def get_agro_weather(lat, lon):
    """Get simulated weather data"""
    import random
    return {
        "temperature": round(random.uniform(20, 35), 2),
        "humidity": round(random.uniform(50, 90), 2),
        "precipitation": round(random.uniform(0, 20), 2)
    }

# ----------------------------
# MOCK EARTH ENGINE FUNCTIONS
# ----------------------------
def get_historical_ndvi(lat, lon, start_date, end_date):
    """Returns simulated average NDVI and NDVI trend"""
    import random
    return {
        "ndvi_avg": round(random.uniform(0.45, 0.75), 3),
        "ndvi_trend": round(random.uniform(-0.1, 0.15), 3)
    }

# ----------------------------
# YIELD ENGINE FUNCTION
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
    """Run complete yield prediction pipeline"""
    print(f"\n🌾 YIELD PIPELINE - Running for ({lat}, {lon})")
    print(f"   Period: {start_date} to {end_date}\n")
    
    # Get current NDVI
    ndvi_now = get_agro_ndvi(lat, lon)
    print(f"✓ Current NDVI: {ndvi_now}")
    
    # Get weather
    weather = get_agro_weather(lat, lon)
    print(f"✓ Weather - Temp: {weather['temperature']}°C, Humidity: {weather['humidity']}%, Precipitation: {weather['precipitation']}mm")
    
    # Get historical data
    historical = get_historical_ndvi(lat, lon, start_date, end_date)
    print(f"✓ Historical NDVI avg: {historical['ndvi_avg']}, Trend: {historical['ndvi_trend']}")

    if ndvi_now is None or historical["ndvi_avg"] is None:
        print("❌ Error: Missing NDVI data.")
        return None

    # Calculate yield
    yield_result = calculate_yield(
        ndvi_now=ndvi_now,
        ndvi_avg=historical["ndvi_avg"],
        ndvi_trend=historical["ndvi_trend"]
    )

    print(f"\n📊 YIELD PREDICTION:")
    print(f"   Yield Score: {yield_result['yield_score']}")
    print(f"   Yield %: {yield_result['yield_percent']}%")
    print(f"   Stress Level: {yield_result['stress_level']}\n")

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
    # Test coordinates: Jamaica area
    lat = 18.0179
    lon = -76.8099
    start_date = "2024-01-01"
    end_date = "2024-06-30"

    result = run_yield_pipeline(lat, lon, start_date, end_date)
    if result:
        print("Pipeline completed successfully! ✅")
