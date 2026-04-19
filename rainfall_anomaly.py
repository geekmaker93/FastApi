def calculate_rainfall_anomaly(
    current_rainfall_mm: float,
    historical_avg_mm: float
):
    """
    Returns anomaly ratio and classification
    """

    if historical_avg_mm == 0:
        return {
            "anomaly_ratio": 0,
            "status": "no_historical_data"
        }

    anomaly_ratio = round(
        (current_rainfall_mm - historical_avg_mm) / historical_avg_mm,
        2
    )

    if anomaly_ratio < -0.3:
        status = "drought"
    elif anomaly_ratio > 0.3:
        status = "excess_rain"
    else:
        status = "normal"

    return {
        "anomaly_ratio": anomaly_ratio,
        "status": status
    }
