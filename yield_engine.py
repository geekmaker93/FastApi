def estimate_yield(
    ndvi: float,
    evi: float,
    ndwi: float,
    rainfall_mm: float,
    avg_temp_c: float,
    crop: str = "generic"
):
    """
    Returns estimated yield in tons per hectare
    """

    # --- Base vegetation score ---
    veg_score = (ndvi * 0.6) + (evi * 0.25) + (ndwi * 0.15)

    # --- Weather influence ---
    rainfall_factor = min(rainfall_mm / 500, 1)   # normalize
    temp_factor = 1 - abs(avg_temp_c - 25) / 25   # ideal temp ≈25°C

    weather_score = (rainfall_factor * 0.6) + (temp_factor * 0.4)

    # --- Crop coefficient ---
    crop_coefficients = {
        "maize": 1.2,
        "rice": 1.3,
        "wheat": 1.1,
        "soybean": 1.0,
        "generic": 1.0
    }

    crop_factor = crop_coefficients.get(crop.lower(), 1.0)

    # --- Final yield ---
    yield_tph = veg_score * weather_score * crop_factor * 8

    return round(max(yield_tph, 0), 2)