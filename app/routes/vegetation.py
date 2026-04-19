from fastapi import APIRouter, HTTPException
from app.models.schemas import NDVIRequest, NDVIResponse, NDWIRequest, NDWIResponse, LAIRequest, LAIResponse, NDVILAIResponse
from app.services import ndvi
from app.utils import imagery_processing as img_proc

router = APIRouter(prefix="/vegetation", tags=["vegetation"])

@router.post("/ndvi", response_model=NDVIResponse)
def calculate_ndvi(request: NDVIRequest):
    """Calculate NDVI from NIR and Red band values"""
    try:
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
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/ndwi", response_model=NDWIResponse)
def calculate_ndwi(request: NDWIRequest):
    """Calculate NDWI from Green and NIR band values"""
    value = ndvi.calculate_ndwi(request.green, request.nir)
    if value > 0.3:
        water_status = "Open water"
    elif value > 0.0:
        water_status = "Moist surface"
    else:
        water_status = "Dry land or vegetation"
    return NDWIResponse(ndwi=value, water_status=water_status)


@router.post("/health-classification")
def classify_health(ndvi_value: float):
    """Classify vegetation health based on NDVI"""
    try:
        return {
            "ndvi": ndvi_value,
            "health_status": img_proc.classify_vegetation_health(ndvi_value)
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/lai", response_model=LAIResponse)
def calculate_lai(request: LAIRequest):
    """Estimate LAI (Leaf Area Index) from NDVI"""
    try:
        lai_value = ndvi.calculate_lai_from_ndvi(request.ndvi)

        if lai_value >= 4.0:
            health = "High canopy density"
        elif lai_value >= 2.0:
            health = "Moderate canopy density"
        elif lai_value > 0.0:
            health = "Low canopy density"
        else:
            health = "Bare or very sparse vegetation"

        return LAIResponse(ndvi=request.ndvi, lai=lai_value, health_status=health)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/ndvi-lai", response_model=NDVILAIResponse)
def calculate_ndvi_lai(request: NDVIRequest):
    """Calculate NDVI and LAI from NIR and Red band values in one request"""
    try:
        ndvi_value = ndvi.calculate_ndvi(request.nir, request.red)
        lai_value = ndvi.calculate_lai_from_ndvi(ndvi_value)

        if ndvi_value > 0.6:
            ndvi_health = "Dense vegetation"
        elif ndvi_value > 0.4:
            ndvi_health = "Moderate"
        elif ndvi_value > 0.1:
            ndvi_health = "Sparse"
        else:
            ndvi_health = "Bare soil"

        if lai_value >= 4.0:
            lai_health = "High canopy density"
        elif lai_value >= 2.0:
            lai_health = "Moderate canopy density"
        elif lai_value > 0.0:
            lai_health = "Low canopy density"
        else:
            lai_health = "Bare or very sparse vegetation"

        return NDVILAIResponse(
            ndvi=ndvi_value,
            lai=lai_value,
            ndvi_health_status=ndvi_health,
            lai_health_status=lai_health,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
