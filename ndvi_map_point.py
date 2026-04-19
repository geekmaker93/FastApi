import ee
import requests
from datetime import date
import os
from dotenv import load_dotenv

load_dotenv()

# Initialize Earth Engine with project ID
project_id = os.getenv("GEE_PROJECT_ID")
ee.Initialize(project=project_id)

# -----------------------
# Step 1: Define farm point
# -----------------------
lat = 18.0179
lon = -76.8099

point = ee.Geometry.Point(lon, lat)
area = point.buffer(500).bounds()

# -----------------------
# Step 2: Get Sentinel-2 image
# -----------------------
image = (
    ee.ImageCollection("COPERNICUS/S2_SR")
    .filterBounds(area)
    .filterDate("2024-06-01", "2024-06-30")
    .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20))
    .median()
)

ndvi = image.normalizedDifference(["B8", "B4"]).clip(area)

# -----------------------
# Step 3: Export NDVI to PNG
# -----------------------
# (This example assumes you have a method to convert TIFF to PNG)
ndvi_image_path = "mobile_map/ndvi_map.png"
# You would use GDAL or Earth Engine Export to PNG here
# For now, assume the file exists

print(f"NDVI image ready at {ndvi_image_path}")

# -----------------------
# Step 4: Upload NDVI info to FastAPI
# -----------------------
api_url = "http://127.0.0.1:8000/ndvi/"

ndvi_data = {
    "farm_id": 1,  # replace with the real farm ID
    "date": str(date.today()),
    "ndvi_image_path": ndvi_image_path,
    "ndvi_stats": {
        "min": 0.0,
        "max": 1.0,
        "avg": 0.65  # optional: compute average NDVI from image
    }
}

response = requests.post(api_url, json=ndvi_data)
if response.status_code == 200 or response.status_code == 201:
    print("NDVI snapshot uploaded successfully!")
else:
    print("Error uploading NDVI snapshot:", response.text)

