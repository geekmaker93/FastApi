"""
Satellite imagery tile service for live feeds
Supports multiple providers: Google Earth Engine, external tile services
"""
import logging
import os
import ee
import google.auth
from google.oauth2 import service_account
from pathlib import Path
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
from app.core.config import GEE_PROJECT_ID


logger = logging.getLogger("crop_backend.earth_engine")
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SYSTEM_TIME_START = "system:time_start"
_DEFAULT_CREDENTIAL_FILES = (
    PROJECT_ROOT / "serviceAccountKey.json",
    PROJECT_ROOT / "google-service-account.json",
    PROJECT_ROOT / "firebase-service-account.json",
)


class SatelliteTileService:
    """Service for generating satellite imagery tile URLs"""
    
    def __init__(self):
        self.ee_initialized = False
        self._init_error: Optional[str] = None
        self._initialize_earth_engine()

    def _resolve_credentials_file(self) -> Optional[Path]:
        configured_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
        if configured_path:
            candidate = Path(configured_path).expanduser()
            if not candidate.is_absolute():
                candidate = PROJECT_ROOT / candidate
            if candidate.is_file():
                return candidate

        for candidate in _DEFAULT_CREDENTIAL_FILES:
            if candidate.is_file():
                return candidate

        return None

    def _build_init_attempts(self, scopes: list[str]):
        configured_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
        credentials_file = self._resolve_credentials_file()

        if configured_path and credentials_file is not None:
            return [(
                "service_account_file",
                lambda: service_account.Credentials.from_service_account_file(
                    str(credentials_file),
                    scopes=scopes,
                ),
            )]

        attempts = [(
            "application_default_credentials",
            lambda: google.auth.default(scopes=scopes)[0],
        )]

        if credentials_file is not None:
            attempts.append((
                "service_account_file",
                lambda: service_account.Credentials.from_service_account_file(
                    str(credentials_file),
                    scopes=scopes,
                ),
            ))

        return attempts
    
    def _initialize_earth_engine(self):
        """Initialize Google Earth Engine"""
        if self.ee_initialized:
            return

        project_id = (GEE_PROJECT_ID or "").strip()
        if not project_id:
            self._init_error = "GEE_PROJECT_ID is not configured"
            logger.warning("Earth Engine initialization skipped: %s", self._init_error)
            return

        scopes = [
            "https://www.googleapis.com/auth/earthengine",
            "https://www.googleapis.com/auth/cloud-platform",
        ]

        try:
            init_attempts = self._build_init_attempts(scopes)

            last_error: Optional[Exception] = None
            for source_name, credentials_factory in init_attempts:
                try:
                    credentials = credentials_factory()
                    if hasattr(credentials, "with_quota_project"):
                        credentials = credentials.with_quota_project(project_id)
                    ee.Initialize(credentials=credentials, project=project_id)
                    try:
                        ee.data.setCloudApiUserProject(project_id)
                    except Exception:
                        pass
                    self.ee_initialized = True
                    self._init_error = None
                    logger.info("Earth Engine initialized using %s", source_name)
                    return
                except Exception as exc:
                    last_error = exc
                    logger.warning("Earth Engine initialization attempt failed using %s: %s", source_name, exc)

            self._init_error = str(last_error) if last_error else "Unknown initialization error"
        except Exception as e:
            self._init_error = str(e)

        logger.error("Earth Engine initialization failed: %s", self._init_error)
        self.ee_initialized = False
    
    def get_latest_sentinel2_tiles(
        self, 
        lat: float, 
        lon: float, 
        buffer_km: float = 10,
        days_back: int = 7,
        cloud_cover_max: int = 20
    ) -> Dict:
        """
        Get tile URL for latest Sentinel-2 imagery
        
        Args:
            lat: Latitude
            lon: Longitude
            buffer_km: Buffer around point in kilometers
            days_back: How many days back to search
            cloud_cover_max: Maximum cloud cover percentage
        
        Returns:
            Dict with tile URL and metadata
        """
        if not self.ee_initialized:
            self._initialize_earth_engine()

        if not self.ee_initialized:
            return {
                "error": "Earth Engine not initialized",
                "details": self._init_error,
                "fallback": "Use external tile service"
            }
        
        try:
            # Define area of interest
            point = ee.Geometry.Point([lon, lat])
            end_date = datetime.now()

            # Progressive fallback: relax cloud cover, widen buffer, extend date range
            search_attempts = [
                {"buffer_km": buffer_km,               "days": days_back,        "cloud": cloud_cover_max},
                {"buffer_km": buffer_km,               "days": max(90, days_back), "cloud": 60},
                {"buffer_km": max(50, buffer_km * 5),  "days": 180,              "cloud": 80},
                {"buffer_km": max(100, buffer_km * 10),"days": 365,              "cloud": 95},
            ]

            collection = None
            for attempt in search_attempts:
                aoi = point.buffer(attempt["buffer_km"] * 1000)
                start_date = end_date - timedelta(days=attempt["days"])
                coll = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED') \
                    .filterBounds(aoi) \
                    .filterDate(start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')) \
                    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', attempt["cloud"])) \
                    .sort(SYSTEM_TIME_START, False)
                if coll.size().getInfo() > 0:
                    collection = coll
                    break

            if collection is None:
                return {"error": "No Sentinel-2 imagery found for this location. Try again later."}

            latest_image = collection.first()
            
            # True color visualization
            vis_params = {
                'bands': ['B4', 'B3', 'B2'],  # RGB
                'min': 0,
                'max': 3000,
                'gamma': 1.4
            }
            
            # Get tile URL
            map_id = latest_image.getMapId(vis_params)
            tile_url = map_id['tile_fetcher'].url_format
            
            # Get image metadata
            image_date = ee.Date(latest_image.get('system:time_start')).format('YYYY-MM-dd').getInfo()
            
            return {
                "tile_url": tile_url,
                "date": image_date,
                "provider": "Sentinel-2",
                "bands": "True Color (RGB)",
                "cloud_cover": "< {}%".format(cloud_cover_max),
                "tilejson": self._create_tilejson(tile_url, lat, lon, f"Sentinel-2 {image_date}")
            }
        
        except Exception as e:
            return {"error": str(e)}
    
    def get_ndvi_layer_tiles(
        self,
        lat: float,
        lon: float,
        buffer_km: float = 10,
        days_back: int = 7
    ) -> Dict:
        """Get NDVI layer tiles from latest Sentinel-2"""
        if not self.ee_initialized:
            self._initialize_earth_engine()

        if not self.ee_initialized:
            return {
                "error": "Earth Engine not initialized",
                "details": self._init_error,
            }
        
        try:
            point = ee.Geometry.Point([lon, lat])
            end_date = datetime.now()

            # Progressive fallback: tighten → relax cloud cover → wider buffer → full year
            search_attempts = [
                {"buffer_km": buffer_km,      "days": days_back,      "cloud": 30},
                {"buffer_km": buffer_km,      "days": max(90, days_back),  "cloud": 60},
                {"buffer_km": max(50, buffer_km * 5), "days": 180,    "cloud": 80},
                {"buffer_km": max(100, buffer_km * 10), "days": 365,  "cloud": 95},
            ]

            collection = None
            used_attempt = None
            for attempt in search_attempts:
                aoi = point.buffer(attempt["buffer_km"] * 1000)
                start_date = end_date - timedelta(days=attempt["days"])
                coll = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED') \
                    .filterBounds(aoi) \
                    .filterDate(start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')) \
                    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', attempt["cloud"])) \
                    .sort(SYSTEM_TIME_START, False)
                if coll.size().getInfo() > 0:
                    collection = coll
                    used_attempt = attempt
                    break

            if collection is None:
                return {"error": "No Sentinel-2 imagery found for this location. Try again later."}

            aoi = point.buffer(used_attempt["buffer_km"] * 1000)
            latest_image = collection.first()
            
            # Calculate NDVI
            nir = latest_image.select('B8')
            red = latest_image.select('B4')
            ndvi = nir.subtract(red).divide(nir.add(red)).rename('NDVI')
            
            # NDVI visualization
            ndvi_vis = {
                'min': -1,
                'max': 1,
                'palette': ['red', 'yellow', 'green']
            }
            
            map_id = ndvi.getMapId(ndvi_vis)
            tile_url = map_id['tile_fetcher'].url_format
            
            image_date = ee.Date(latest_image.get('system:time_start')).format('YYYY-MM-dd').getInfo()
            
            return {
                "tile_url": tile_url,
                "date": image_date,
                "provider": "Sentinel-2",
                "layer": "NDVI",
                "tilejson": self._create_tilejson(tile_url, lat, lon, f"NDVI {image_date}")
            }
        
        except Exception as e:
            return {"error": str(e)}
    
    def _create_tilejson(self, tile_url: str, lat: float, lon: float, name: str) -> Dict:
        """Create TileJSON specification"""
        return {
            "tilejson": "2.2.0",
            "name": name,
            "description": "Satellite imagery tiles",
            "version": "1.0.0",
            "scheme": "xyz",
            "tiles": [tile_url],
            "center": [lon, lat, 12],
            "minzoom": 0,
            "maxzoom": 18
        }
    
    @staticmethod
    def get_external_tile_sources() -> Dict:
        """
        Get configuration for external satellite tile sources
        These can be used directly from frontend or proxied through backend
        """
        return {
            "mapbox_satellite": {
                "name": "Mapbox Satellite",
                "url": "https://api.mapbox.com/v4/mapbox.satellite/{z}/{x}/{y}.jpg?access_token={access_token}",
                "requires_key": True,
                "attribution": "© Mapbox © DigitalGlobe",
                "minzoom": 0,
                "maxzoom": 19
            },
            "esri_world_imagery": {
                "name": "ESRI World Imagery",
                "url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
                "requires_key": False,
                "attribution": "© Esri",
                "minzoom": 0,
                "maxzoom": 19
            },
            "nasa_gibs_modis": {
                "name": "NASA GIBS MODIS",
                "url": "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/MODIS_Terra_CorrectedReflectance_TrueColor/default/{time}/{tilematrixset}/{z}/{y}/{x}.jpg",
                "requires_key": False,
                "attribution": "© NASA EOSDIS",
                "time_format": "YYYY-MM-DD",
                "minzoom": 0,
                "maxzoom": 9
            },
            "sentinel_hub_ogc": {
                "name": "Sentinel Hub OGC",
                "url": "https://services.sentinel-hub.com/ogc/wms/{instance_id}?SERVICE=WMS&REQUEST=GetMap&LAYERS=TRUE-COLOR&BBOX={bbox}&WIDTH=256&HEIGHT=256&FORMAT=image/png",
                "requires_key": True,
                "attribution": "© Sentinel Hub",
                "note": "Requires instance_id configuration"
            }
        }
