import ee
import os
import requests
from dotenv import load_dotenv

load_dotenv()

# Initialize Earth Engine
try:
    project_id = os.getenv("GEE_PROJECT_ID")
    if project_id:
        ee.Initialize(project=project_id)
    else:
        ee.Initialize()
    print("✓ Earth Engine initialized successfully")
except Exception as e:
    print(f"Error initializing Earth Engine: {e}")
    print("\nPlease run: python authenticate_gee.py")
    exit(1)

def fetch_ndvi_geotiff(lat, lon, start_date, end_date, output_path="NDVI_Point_Map.tif"):
    """Fetch NDVI GeoTIFF from Google Earth Engine"""
    
    # Define point and buffer (500m radius for visualization)
    point = ee.Geometry.Point(lon, lat)
    region = point.buffer(500).bounds()
    
    # Get Sentinel-2 imagery
    collection = (
        ee.ImageCollection("COPERNICUS/S2_SR")
        .filterBounds(point)
        .filterDate(start_date, end_date)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20))
    )
    
    if collection.size().getInfo() == 0:
        print("No images found for this location and date range")
        return None
    
    # Calculate NDVI
    def add_ndvi(image):
        ndvi = image.normalizedDifference(['B8', 'B4']).rename('NDVI')
        return ndvi
    
    ndvi_collection = collection.map(add_ndvi)
    ndvi_mean = ndvi_collection.mean()
    
    # Get download URL
    print("Generating download URL...")
    url = ndvi_mean.getDownloadURL({
        'region': region,
        'scale': 10,
        'format': 'GEO_TIFF',
        'bands': ['NDVI']
    })
    
    print(f"Download URL generated: {url[:50]}...")
    
    # Download the file
    print("Downloading GeoTIFF...")
    try:
        response = requests.get(url, timeout=30)
    except requests.exceptions.Timeout:
        print("Timeout downloading GeoTIFF after 30s")
        return None
    except Exception as e:
        print(f"Error downloading file: {e}")
        return None
    
    if response.status_code == 200:
        with open(output_path, 'wb') as f:
            f.write(response.content)
        print(f"✓ GeoTIFF saved to: {output_path}")
        return output_path
    else:
        print(f"Error downloading file: {response.status_code}")
        return None

# Run the process
if __name__ == "__main__":
    lat = 18.0179
    lon = -76.8099
    start_date = "2026-01-20"
    end_date = "2026-02-19"
    
    print(f"Fetching NDVI data for coordinates: ({lat}, {lon})")
    print(f"Date range: {start_date} to {end_date}")
    
    result = fetch_ndvi_geotiff(lat, lon, start_date, end_date)
    
    if result:
        print("\n✓ Process complete! You can now run ndvi_tif_to_png.py")
    else:
        print("\n✗ Failed to fetch NDVI data")
