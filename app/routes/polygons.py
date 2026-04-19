from fastapi import APIRouter, HTTPException
from app.models.schemas import FarmCreate, FarmResponse
from app.services.agromonitoring import create_polygon, get_polygon, get_polygon_coordinates
from app.utils.geo import (
    validate_polygon_coordinates, calculate_polygon_area,
    get_polygon_centroid
)
from datetime import datetime
import uuid

router = APIRouter(prefix="/polygons", tags=["polygons"])

@router.post("/create", response_model=FarmResponse)
def create_field_polygon(farm: FarmCreate):
    """Create a polygon for a field/farm"""
    try:
        # Validate coordinates
        if not validate_polygon_coordinates(farm.polygon):
            raise ValueError("Invalid polygon coordinates")
        
        # Register with AgroMonitoring
        agg_polygon = create_polygon(farm.name, farm.polygon)
        
        return FarmResponse(
            id=str(uuid.uuid4()),
            name=farm.name,
            polygon_id=agg_polygon["id"],
            created_at=datetime.now()
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/area/{polygon_id}")
def get_field_area(polygon_id: str):
    """Get area of a polygon"""
    try:
        polygon = get_polygon(polygon_id)
        coordinates = get_polygon_coordinates(polygon)
        area_m2 = calculate_polygon_area(coordinates)
        return {
            "polygon_id": polygon_id,
            "area_m2": area_m2,
            "area_hectares": area_m2 / 10000
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/centroid/{polygon_id}")
def get_field_centroid(polygon_id: str):
    """Get center point of a polygon"""
    try:
        polygon = get_polygon(polygon_id)
        coordinates = get_polygon_coordinates(polygon)
        centroid = get_polygon_centroid(coordinates)
        return {
            "polygon_id": polygon_id,
            "centroid": [centroid[0], centroid[1]]
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
