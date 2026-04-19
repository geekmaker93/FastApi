import numpy as np
from typing import Dict, List

def process_ndvi_data(ndvi_array: np.ndarray) -> Dict:
    """Process and analyze NDVI data"""
    return {
        "min": float(np.min(ndvi_array)),
        "max": float(np.max(ndvi_array)),
        "mean": float(np.mean(ndvi_array)),
        "std": float(np.std(ndvi_array)),
        "median": float(np.median(ndvi_array))
    }


def classify_vegetation_health(ndvi_value: float) -> str:
    """
    Classify vegetation health based on NDVI value
    NDVI ranges from -1 to 1
    """
    if ndvi_value < -0.1:
        return "Water/No vegetation"
    elif ndvi_value < 0.1:
        return "Bare soil"
    elif ndvi_value < 0.3:
        return "Sparse vegetation"
    elif ndvi_value < 0.5:
        return "Moderate vegetation"
    else:
        return "Dense vegetation"


def generate_vegetation_map(ndvi_array: np.ndarray) -> Dict:
    """Generate vegetation classification map"""
    health_map = {}
    unique_values = np.unique(ndvi_array)
    
    for val in unique_values:
        health_map[float(val)] = classify_vegetation_health(float(val))
    
    return {
        "classification": health_map,
        "statistics": process_ndvi_data(ndvi_array)
    }
