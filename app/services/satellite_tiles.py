"""
Satellite imagery tile service for live feeds
Supports multiple providers: Google Earth Engine, external tile services
"""
import ee
import google.auth
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
from app.core.config import GEE_PROJECT_ID


class SatelliteTileService:
    """Service for generating satellite imagery tile URLs"""
    
    def __init__(self):
        self.ee_initialized = False
        self._initialize_earth_engine()
    
    def _initialize_earth_engine(self):
        """Initialize Google Earth Engine"""
        try:
            if GEE_PROJECT_ID:
                scopes = [
                    "https://www.googleapis.com/auth/earthengine",
                    "https://www.googleapis.com/auth/cloud-platform",
                ]
                credentials, _ = google.auth.default(scopes=scopes)
                if hasattr(credentials, "with_quota_project"):
                    credentials = credentials.with_quota_project(GEE_PROJECT_ID)
                ee.Initialize(credentials=credentials, project=GEE_PROJECT_ID)
                try:
                    ee.data.setCloudApiUserProject(GEE_PROJECT_ID)
                except Exception:
                    pass
                self.ee_initialized = True
        except Exception as e:
            print(f"Earth Engine initialization failed: {e}")
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
            return {
                "error": "Earth Engine not initialized",
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
            used_attempt = None
            for attempt in search_attempts:
                aoi = point.buffer(attempt["buffer_km"] * 1000)
                start_date = end_date - timedelta(days=attempt["days"])
                coll = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED') \
                    .filterBounds(aoi) \
                    .filterDate(start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')) \
                    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', attempt["cloud"])) \
                    .sort('system:time_start', False)
                if coll.size().getInfo() > 0:
                    collection = coll
                    used_attempt = attempt
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
            return {"error": "Earth Engine not initialized"}
        
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
                    .sort('system:time_start', False)
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
