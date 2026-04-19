import ee

try:
    ee.Initialize()
except Exception as e:
    print(f"Earth Engine initialization warning: {e}")
    pass

def get_historical_ndvi(lat, lon, start_year=2020, end_year=2024):
    point = ee.Geometry.Point(lon, lat)

    collection = (
        ee.ImageCollection("COPERNICUS/S2_SR")
        .filterBounds(point)
        .filterDate(f"{start_year}-01-01", f"{end_year}-12-31")
        .map(lambda img: img.normalizedDifference(["B8", "B4"]).rename("ndvi"))
    )

    stats = collection.reduce(
        ee.Reducer.min()
        .combine(ee.Reducer.max(), "", True)
        .combine(ee.Reducer.mean(), "", True)
    )

    values = stats.reduceRegion(
        reducer=ee.Reducer.first(),
        geometry=point,
        scale=10
    )

    return {
        "min": values.get("ndvi_min").getInfo(),
        "max": values.get("ndvi_max").getInfo(),
        "mean": values.get("ndvi_mean").getInfo()
    }

def normalize_ndvi(current_ndvi, hist_min, hist_max):
    if hist_max == hist_min:
        return 0.5
    return round(
        (current_ndvi - hist_min) / (hist_max - hist_min),
        2
    )