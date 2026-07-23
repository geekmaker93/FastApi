"""Sentinel Hub tile URL generation for live Sentinel-2 layers."""
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional
from urllib.parse import urlencode


class SatelliteTileService:
    """Generate Sentinel Hub WMTS URLs consumable by Leaflet and Mapbox."""

    _WMTS_URL = "https://sh.dataspace.copernicus.eu/ogc/wmts/{instance_id}"

    def __init__(self):
        self.instance_id = os.getenv("SENTINELHUB_INSTANCE_ID", "").strip()

    def _configured_instance_id(self) -> Optional[str]:
        self.instance_id = os.getenv("SENTINELHUB_INSTANCE_ID", self.instance_id).strip()
        return self.instance_id or None

    def _tile_url(self, layer: str, days_back: int, cloud_cover_max: int) -> str:
        instance_id = self._configured_instance_id()
        if not instance_id:
            raise RuntimeError("SENTINELHUB_INSTANCE_ID is not configured")

        end_date = datetime.now(timezone.utc).date()
        start_date = end_date - timedelta(days=max(days_back, 1))
        query = urlencode({
            "REQUEST": "GetTile",
            "SERVICE": "WMTS",
            "VERSION": "1.0.0",
            "LAYER": layer,
            "STYLE": "default",
            "TILEMATRIXSET": "PopularWebMercator256",
            "TILEMATRIX": "{z}",
            "TILEROW": "{y}",
            "TILECOL": "{x}",
            "FORMAT": "image/png",
            "TIME": f"{start_date.isoformat()}/{end_date.isoformat()}",
            "MAXCC": str(max(0, min(cloud_cover_max, 100))),
        })
        return (
            f"{self._WMTS_URL.format(instance_id=instance_id)}?{query}"
            .replace("%7B", "{")
            .replace("%7D", "}")
        )

    def get_latest_sentinel2_tiles(
        self,
        lat: float,
        lon: float,
        buffer_km: float = 10,
        days_back: int = 7,
        cloud_cover_max: int = 20,
    ) -> Dict:
        try:
            _ = buffer_km
            tile_url = self._tile_url("TRUE_COLOR", days_back, cloud_cover_max)
            end_date = datetime.now(timezone.utc).date().isoformat()
            return {
                "tile_url": tile_url,
                "date": end_date,
                "provider": "Copernicus Sentinel-2",
                "bands": "True Color (RGB)",
                "cloud_cover": f"< {cloud_cover_max}%",
                "tilejson": self._create_tilejson(tile_url, lat, lon, f"Sentinel-2 {end_date}"),
            }
        except Exception as exc:
            return {"error": str(exc)}

    def get_ndvi_layer_tiles(
        self,
        lat: float,
        lon: float,
        buffer_km: float = 10,
        days_back: int = 7,
    ) -> Dict:
        try:
            _ = buffer_km
            tile_url = self._tile_url("VEGETATION_INDEX", days_back, 30)
            end_date = datetime.now(timezone.utc).date().isoformat()
            return {
                "tile_url": tile_url,
                "date": end_date,
                "provider": "Copernicus Sentinel-2",
                "layer": "NDVI",
                "tilejson": self._create_tilejson(tile_url, lat, lon, f"NDVI {end_date}"),
            }
        except Exception as exc:
            return {"error": str(exc)}

    @staticmethod
    def _create_tilejson(tile_url: str, lat: float, lon: float, name: str) -> Dict:
        return {
            "tilejson": "2.2.0",
            "name": name,
            "description": "Copernicus Sentinel-2 imagery tiles",
            "version": "1.0.0",
            "scheme": "xyz",
            "tiles": [tile_url],
            "center": [lon, lat, 12],
            "minzoom": 0,
            "maxzoom": 18,
        }

    @staticmethod
    def get_external_tile_sources() -> Dict:
        return {
            "mapbox_satellite": {
                "name": "Mapbox Satellite",
                "url": "https://api.mapbox.com/v4/mapbox.satellite/{z}/{x}/{y}.jpg?access_token={access_token}",
                "requires_key": True,
                "attribution": "© Mapbox © DigitalGlobe",
                "minzoom": 0,
                "maxzoom": 19,
            },
            "esri_world_imagery": {
                "name": "ESRI World Imagery",
                "url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
                "requires_key": False,
                "attribution": "© Esri",
                "minzoom": 0,
                "maxzoom": 19,
            },
            "nasa_gibs_modis": {
                "name": "NASA GIBS MODIS",
                "url": "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/MODIS_Terra_CorrectedReflectance_TrueColor/default/{time}/{tilematrixset}/{z}/{y}/{x}.jpg",
                "requires_key": False,
                "attribution": "© NASA EOSDIS",
                "time_format": "YYYY-MM-DD",
                "minzoom": 0,
                "maxzoom": 9,
            },
            "sentinel_hub_wmts": {
                "name": "Copernicus Sentinel Hub WMTS",
                "url": "https://services.sentinel-hub.com/ogc/wmts/{instance_id}",
                "requires_key": True,
                "attribution": "© Copernicus Sentinel Hub",
                "note": "Requires SENTINELHUB_INSTANCE_ID and configured TRUE-COLOR/NDVI layers",
            },
        }