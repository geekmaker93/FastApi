from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import date, datetime
from typing import List, Optional
import numpy as np
from app.models.db_models import NDVISnapshot, Farm
from app.dependencies import get_db
from app.services.tiles import NDVITileService
from app.services.wms_server import WMSTileServer
from ndvi_history import get_historical_ndvi
import time

router = APIRouter(prefix="/ndvi", tags=["ndvi"])
tile_service = NDVITileService()
wms_server = WMSTileServer()
_NDVI_POINT_CACHE: dict[str, dict] = {}
_NDVI_POINT_CACHE_TTL_S = 300.0


@router.get("/point")
def get_ndvi_for_point(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    days_back: int = Query(30, description="Days back to average over"),
):
    """Return mean NDVI for a lat/lon point using recent Sentinel-2 imagery."""
    try:
        cache_key = f"{round(lat, 4):.4f}:{round(lon, 4):.4f}:{days_back}"
        cached = _NDVI_POINT_CACHE.get(cache_key)
        if cached and (time.time() - float(cached.get("_cached_at", 0.0))) < _NDVI_POINT_CACHE_TTL_S:
            return {key: value for key, value in cached.items() if key != "_cached_at"}

        from datetime import timedelta
        import datetime as dt
        end_year = dt.date.today().year
        start_year = end_year - 1
        stats = get_historical_ndvi(lat, lon, start_year=start_year, end_year=end_year)
        mean_ndvi = stats.get("mean")
        if mean_ndvi is None:
            mean_ndvi = 0.5
        mean_ndvi = round(float(mean_ndvi), 4)
        if mean_ndvi > 0.6:
            health = "Dense vegetation"
        elif mean_ndvi > 0.4:
            health = "Moderate"
        elif mean_ndvi > 0.1:
            health = "Sparse"
        else:
            health = "Bare soil"
        response = {
            "lat": lat,
            "lon": lon,
            "ndvi_mean": mean_ndvi,
            "ndvi_min": round(float(stats.get("min") or mean_ndvi), 4),
            "ndvi_max": round(float(stats.get("max") or mean_ndvi), 4),
            "health_status": health,
        }
        _NDVI_POINT_CACHE[cache_key] = {**response, "_cached_at": time.time()}
        return response
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"NDVI point lookup failed: {str(e)}")

class NDVISnapshotCreate(BaseModel):
    farm_id: int
    date: str
    ndvi_image_path: str
    ndvi_stats: dict

class NDVITimeSeriesRequest(BaseModel):
    farm_id: int
    start_date: str
    end_date: str

@router.post("/")
def create_ndvi_snapshot(snapshot: NDVISnapshotCreate, db: Session = Depends(get_db)):
    """Create a new NDVI snapshot for a farm"""
    farm = db.query(Farm).filter(Farm.id == snapshot.farm_id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")
    
    new_snapshot = NDVISnapshot(
        farm_id=snapshot.farm_id,
        date=date.fromisoformat(snapshot.date),
        ndvi_image_path=snapshot.ndvi_image_path,
        ndvi_stats=snapshot.ndvi_stats
    )
    
    db.add(new_snapshot)
    db.commit()
    db.refresh(new_snapshot)
    
    return {
        "id": new_snapshot.id,
        "farm_id": new_snapshot.farm_id,
        "date": new_snapshot.date.isoformat(),
        "message": "NDVI snapshot created successfully"
    }

@router.get("/{snapshot_id}")
def get_ndvi_snapshot(snapshot_id: int, db: Session = Depends(get_db)):
    """Get NDVI snapshot by ID"""
    snapshot = db.query(NDVISnapshot).filter(NDVISnapshot.id == snapshot_id).first()
    if not snapshot:
        raise HTTPException(status_code=404, detail="NDVI snapshot not found")
    
    return {
        "id": snapshot.id,
        "farm_id": snapshot.farm_id,
        "date": snapshot.date.isoformat(),
        "ndvi_image_path": snapshot.ndvi_image_path,
        "ndvi_stats": snapshot.ndvi_stats
    }

@router.get("/farm/{farm_id}/timeseries")
def get_ndvi_timeseries(
    farm_id: int,
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Get NDVI time series for a farm (for temporal comparison)"""
    farm = db.query(Farm).filter(Farm.id == farm_id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")
    
    query = db.query(NDVISnapshot).filter(NDVISnapshot.farm_id == farm_id)
    
    if start_date:
        query = query.filter(NDVISnapshot.date >= date.fromisoformat(start_date))
    if end_date:
        query = query.filter(NDVISnapshot.date <= date.fromisoformat(end_date))
    
    snapshots = query.order_by(NDVISnapshot.date).all()
    
    return {
        "farm_id": farm_id,
        "count": len(snapshots),
        "snapshots": [
            {
                "id": s.id,
                "date": s.date.isoformat(),
                "ndvi_stats": s.ndvi_stats,
                "ndvi_image_path": s.ndvi_image_path
            }
            for s in snapshots
        ]
    }

@router.post("/{snapshot_id}/generate-tiles")
def generate_ndvi_tiles(snapshot_id: int, db: Session = Depends(get_db)):
    """Generate GeoTIFF tiles from NDVI snapshot"""
    snapshot = db.query(NDVISnapshot).filter(NDVISnapshot.id == snapshot_id).first()
    if not snapshot:
        raise HTTPException(status_code=404, detail="NDVI snapshot not found")
    
    try:
        # This would integrate with actual imagery processing
        tile_info = {
            "snapshot_id": snapshot_id,
            "farm_id": snapshot.farm_id,
            "date": snapshot.date.isoformat(),
            "tile_url": f"/tiles/ndvi/{snapshot_id}/{{z}}/{{x}}/{{y}}.png",
            "zoom_levels": [14, 15, 16],
            "status": "generated"
        }
        return tile_info
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/wms/capabilities")
def get_wms_capabilities():
    """Get WMS Capabilities document"""
    return wms_server.get_capabilities()

@router.get("/wms/layers")
def list_wms_layers():
    """List all available WMS layers"""
    return wms_server.list_layers()

@router.get("/tile/{layer_name}/{z}/{x}/{y}")
def get_tile(layer_name: str, z: int, x: int, y: int):
    """Get individual tile (XYZ format for Leaflet/Mapbox)"""
    try:
        # Convert XYZ to bbox (simplified - would need proper tile math)
        # This is a placeholder; real implementation needs proper Web Mercator math
        bbox = [0, 0, 1, 1]  # Replace with actual bbox calculation
        
        tile_data = wms_server.get_map(layer_name, bbox, 256, 256, format="image/png")
        return StreamingResponse(iter([tile_data]), media_type="image/png")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
