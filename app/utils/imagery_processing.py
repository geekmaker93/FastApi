import numpy as np
from typing import Tuple, Dict
import rasterio

def normalize_band(band_array: np.ndarray) -> np.ndarray:
    """Normalize band to 0-1 range"""
    min_val = np.min(band_array)
    max_val = np.max(band_array)
    if max_val - min_val == 0:
        return np.zeros_like(band_array)
    return (band_array - min_val) / (max_val - min_val)


def calculate_evi(nir: np.ndarray, red: np.ndarray, blue: np.ndarray) -> np.ndarray:
    """
    Calculate Enhanced Vegetation Index (EVI)
    EVI = 2.5 * (NIR - RED) / (NIR + 6 * RED - 7.5 * BLUE + 1)
    """
    numerator = nir - red
    denominator = nir + 6 * red - 7.5 * blue + 1
    evi = np.where(denominator != 0, 2.5 * numerator / denominator, 0)
    return evi


def calculate_savi(nir: np.ndarray, red: np.ndarray, l: float = 0.5) -> np.ndarray:
    """
    Calculate Soil-Adjusted Vegetation Index (SAVI)
    SAVI = ((NIR - RED) / (NIR + RED + L)) * (1 + L)
    L is the soil adjustment factor (default 0.5)
    """
    numerator = nir - red
    denominator = nir + red + l
    savi = np.where(denominator != 0, (numerator / denominator) * (1 + l), 0)
    return savi


def calculate_ndvi(nir: np.ndarray, red: np.ndarray) -> np.ndarray:
    """
    Calculate Normalized Difference Vegetation Index (NDVI)
    NDVI = (NIR - RED) / (NIR + RED)
    """
    numerator = nir - red
    denominator = nir + red
    ndvi = np.where(denominator != 0, numerator / denominator, 0)
    return ndvi


def extract_band_from_file(filepath: str, band_index: int) -> np.ndarray:
    """Extract specific band from raster file"""
    with rasterio.open(filepath) as src:
        return src.read(band_index)


def get_raster_metadata(filepath: str) -> Dict:
    """Get metadata from raster file"""
    with rasterio.open(filepath) as src:
        return {
            "width": src.width,
            "height": src.height,
            "count": src.count,
            "dtype": str(src.dtypes[0]),
            "crs": str(src.crs),
            "bounds": src.bounds._asdict(),
            "transform": str(src.transform)
        }
