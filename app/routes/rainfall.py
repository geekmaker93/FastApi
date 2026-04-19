from datetime import datetime

from fastapi import APIRouter

from rainfall_anomaly import calculate_rainfall_anomaly
from app.services.farmonaut import get_historical_avg_rainfall

router = APIRouter(prefix="/rainfall", tags=["rainfall"])


@router.get("/anomaly")
def rainfall_anomaly(current_rainfall_mm: float):
    month = datetime.utcnow().month
    historical_avg = get_historical_avg_rainfall(month)

    anomaly = calculate_rainfall_anomaly(
        current_rainfall_mm,
        historical_avg
    )

    return {
        "current_rainfall_mm": current_rainfall_mm,
        "historical_avg_mm": historical_avg,
        "anomaly": anomaly
    }
