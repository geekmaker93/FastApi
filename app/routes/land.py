from fastapi import APIRouter
from app.services import ndvi
from app.models.schemas import NDVIRequest, NDVIResponse

router = APIRouter(prefix="/land", tags=["land"])

@router.post("/ndvi", response_model=NDVIResponse)
def calculate_ndvi(request: NDVIRequest):
    value = ndvi.calculate_ndvi(request.nir, request.red)
    if value > 0.6:
        health = "Dense vegetation"
    elif value > 0.4:
        health = "Moderate"
    elif value > 0.1:
        health = "Sparse"
    else:
        health = "Bare soil"
    return NDVIResponse(ndvi=value, health_status=health)