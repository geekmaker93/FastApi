import numpy as np
import rasterio
from typing import Tuple, Dict
from app.core.config import GEE_API_KEY

def calculate_ndvi_from_raster(nir_band: str, red_band: str) -> np.ndarray:
    """
    Calculate NDVI from satellite raster bands (NIR and Red)
    """
    with rasterio.open(nir_band) as nir_src:
        nir = nir_src.read(1).astype(float)
    
    with rasterio.open(red_band) as red_src:
        red = red_src.read(1).astype(float)
    
    denominator = nir + red
    ndvi = np.where(denominator != 0, (nir - red) / denominator, 0)
    
    return ndvi


def get_sentinel2_imagery(lat: float, lon: float, start_date: str, end_date: str) -> Dict:
    """
    Get Sentinel-2 satellite imagery for a location
    Uses Google Earth Engine API
    """
    # This would integrate with GEE Python API
    return {
        "provider": "Sentinel-2",
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date,
        "end_date": end_date,
        "status": "pending"
    }


def process_satellite_imagery(imagery_path: str) -> Dict:
    """Process satellite imagery and extract bands"""
    try:
        with rasterio.open(imagery_path) as src:
            bands = src.count
            metadata = {
                "file": imagery_path,
                "bands": bands,
                "width": src.width,
                "height": src.height,
                "crs": str(src.crs),
                "bounds": src.bounds._asdict()
            }
            return metadata
    except Exception as e:
        raise ValueError(f"Error processing imagery: {str(e)}")
