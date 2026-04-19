from fastapi import APIRouter, HTTPException, Query
from app.models.schemas import (
    Sentinel2Request, SatelliteImageryRequest, 
    SatelliteImageryResponse, VegetationMap, NDVIAnalysis
)
from app.services import sentinel
from app.services.satellite_tiles import SatelliteTileService
from app.utils import imagery_processing as img_proc
from datetime import datetime
from typing import Optional

router = APIRouter(prefix="/sentinel", tags=["satellite"])
tile_service = SatelliteTileService()

@router.post("/imagery/request")
def request_imagery(request: Sentinel2Request):
    """Request Sentinel-2 satellite imagery for a location"""
    try:
        result = sentinel.get_sentinel2_imagery(
            lat=request.latitude,
            lon=request.longitude,
            start_date=request.start_date,
            end_date=request.end_date
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/ndvi/analyze")
def analyze_ndvi(nir_file: str, red_file: str) -> NDVIAnalysis:
    """Analyze NDVI from satellite bands"""
    try:
        ndvi_array = sentinel.calculate_ndvi_from_raster(nir_file, red_file)
        
        return NDVIAnalysis(
            min=float(ndvi_array.min()),
            max=float(ndvi_array.max()),
            mean=float(ndvi_array.mean()),
            std=float(ndvi_array.std()),
            median=float(ndvi_array.median())
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/metadata/{file_path}")
def get_metadata(file_path: str):
    """Get raster file metadata"""
    try:
        metadata = img_proc.get_raster_metadata(file_path)
        return metadata
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/live/tiles")
def get_live_satellite_tiles(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    buffer_km: float = Query(10, description="Buffer radius in kilometers"),
    days_back: int = Query(7, description="Days to search back for imagery"),
    cloud_cover_max: int = Query(20, description="Maximum cloud cover percentage")
):
    """
    Get live satellite imagery tiles (Sentinel-2 via Google Earth Engine)
    Returns tile URL and TileJSON for map integration
    
    Usage in frontend:
    - Leaflet: L.tileLayer(tile_url).addTo(map)
    - Mapbox: map.addSource('satellite', {type: 'raster', tiles: [tile_url]})
    """
    result = tile_service.get_latest_sentinel2_tiles(
        lat=lat,
        lon=lon,
        buffer_km=buffer_km,
        days_back=days_back,
        cloud_cover_max=cloud_cover_max
    )
    
    if "error" in result:
        raise HTTPException(status_code=503, detail=result["error"])
    
    return result


@router.get("/live/ndvi-tiles")
def get_live_ndvi_tiles(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    buffer_km: float = Query(10, description="Buffer radius in kilometers"),
    days_back: int = Query(7, description="Days to search back for imagery")
):
    """
    Get live NDVI layer tiles from latest Sentinel-2 imagery
    Returns NDVI visualization with color gradient (red=low, green=high)
    """
    result = tile_service.get_ndvi_layer_tiles(
        lat=lat,
        lon=lon,
        buffer_km=buffer_km,
        days_back=days_back
    )
    
    if "error" in result:
        raise HTTPException(status_code=503, detail=result["error"])
    
    return result


@router.get("/tile-sources")
def get_available_tile_sources():
    """
    Get list of available external satellite tile sources
    These can be used directly from your frontend without proxying
    
    Free options: ESRI World Imagery, NASA GIBS
    Paid options: Mapbox Satellite, Sentinel Hub (require API keys)
    """
    return tile_service.get_external_tile_sources()


@router.get("/farm/{farm_id}/live-tiles")
def get_farm_live_tiles(
    farm_id: int,
    days_back: int = Query(7, description="Days to search back"),
    layer: str = Query("rgb", description="Layer type: 'rgb' or 'ndvi'")
):
    """
    Get live satellite tiles centered on a specific farm
    Automatically uses farm's centroid coordinates
    """
    # TODO: Query farm from database to get coordinates
    # For now, return error with instruction
    raise HTTPException(
        status_code=501,
        detail="Farm-specific tiles require database integration. Use /live/tiles with farm coordinates instead."
    )


@router.get("/external/esri-world")
def get_esri_world_imagery():
    """
    Get ESRI World Imagery tiles (free, no authentication required)
    Best for: General satellite basemap
    Updates: Monthly
    """
    return {
        "provider": "ESRI World Imagery",
        "tile_url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "attribution": "© Esri, DigitalGlobe, GeoEye, Earthstar Geographics, CNES/Airbus DS, USDA, USGS, AeroGRID, IGN, and the GIS User Community",
        "minzoom": 0,
        "maxzoom": 19,
        "format": "JPEG",
        "tilejson": {
            "tilejson": "2.2.0",
            "name": "ESRI World Imagery",
            "tiles": ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
            "minzoom": 0,
            "maxzoom": 19
        }
    }


@router.get("/external/nasa-gibs")
def get_nasa_gibs_tiles(date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format, defaults to yesterday")):
    """
    Get NASA GIBS MODIS tiles (free, near real-time)
    Best for: Daily updates, large area coverage
    Updates: Daily (yesterday's data)
    Resolution: 250m
    """
    from datetime import datetime, timedelta
    
    if not date:
        # Default to yesterday (today's data not available yet)
        date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    
    tile_url = f"https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/MODIS_Terra_CorrectedReflectance_TrueColor/default/{date}/GoogleMapsCompatible_Level9/{{z}}/{{y}}/{{x}}.jpg"
    
    return {
        "provider": "NASA GIBS MODIS Terra",
        "tile_url": tile_url,
        "date": date,
        "attribution": "NASA EOSDIS GIBS",
        "minzoom": 0,
        "maxzoom": 9,
        "resolution": "250m",
        "format": "JPEG",
        "note": "Daily updates, yesterday's imagery",
        "tilejson": {
            "tilejson": "2.2.0",
            "name": f"NASA MODIS {date}",
            "tiles": [tile_url],
            "minzoom": 0,
            "maxzoom": 9
        }
    }
