import math


def calculate_ndvi(nir: float, red: float) -> float:
    """
    Calculate NDVI (Normalized Difference Vegetation Index).
    Formula: (NIR - Red) / (NIR + Red)
    """
    if (nir + red) == 0:
        return 0.0
    return (nir - red) / (nir + red)


def calculate_ndwi(green: float, nir: float) -> float:
    """
    Calculate NDWI (Normalized Difference Water Index).
    Formula: (Green - NIR) / (Green + NIR)
    """
    if (green + nir) == 0:
        return 0.0
    return (green - nir) / (green + nir)


def calculate_lai_from_ndvi(ndvi: float) -> float:
    """
    Estimate LAI (Leaf Area Index) from NDVI using an empirical relationship:
    LAI = -ln((0.69 - NDVI) / 0.59) / 0.91

    LAI is constrained to the practical range [0, 8].
    """
    safe_ndvi = min(max(ndvi, -1.0), 0.68)
    lai = -math.log((0.69 - safe_ndvi) / 0.59) / 0.91
    return max(0.0, min(8.0, lai))