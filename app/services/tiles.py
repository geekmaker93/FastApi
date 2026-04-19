import numpy as np
import rasterio
from rasterio.transform import from_bounds
from rasterio.crs import CRS
import os
from datetime import datetime
from PIL import Image
import json

class NDVITileService:
    """Service for generating GeoTIFF tiles from NDVI data"""
    
    def __init__(self, tiles_dir="./ndvi_tiles"):
        self.tiles_dir = tiles_dir
        os.makedirs(tiles_dir, exist_ok=True)
    
    def ndvi_to_geotiff(self, ndvi_array, bounds, crs_epsg=4326, date=None):
        """
        Convert NDVI numpy array to GeoTIFF file
        
        Args:
            ndvi_array: 2D numpy array with NDVI values (-1 to 1)
            bounds: (min_lon, min_lat, max_lon, max_lat)
            crs_epsg: EPSG code (default 4326 for WGS84)
            date: date string for filename
        
        Returns:
            path to generated GeoTIFF file
        """
        if date is None:
            date = datetime.now().strftime("%Y%m%d")
        
        filename = f"ndvi_{date}_{datetime.now().strftime('%H%M%S')}.tif"
        filepath = os.path.join(self.tiles_dir, filename)
        
        # Create georeferencing transform
        transform = from_bounds(bounds[0], bounds[1], bounds[2], bounds[3], 
                               ndvi_array.shape[1], ndvi_array.shape[0])
        
        # Write GeoTIFF
        with rasterio.open(
            filepath,
            'w',
            driver='GTiff',
            height=ndvi_array.shape[0],
            width=ndvi_array.shape[1],
            count=1,
            dtype=ndvi_array.dtype,
            crs=CRS.from_epsg(crs_epsg),
            transform=transform
        ) as dst:
            dst.write(ndvi_array, 1)
        
        return filepath
    
    def generate_tiles(self, geotiff_path, tile_size=256, zoom_levels=[14, 15, 16]):
        """
        Generate web tiles from GeoTIFF (XYZ format for Leaflet)
        
        Args:
            geotiff_path: path to GeoTIFF file
            tile_size: size of each tile in pixels
            zoom_levels: list of zoom levels to generate
        
        Returns:
            dict with tile server URL template
        """
        with rasterio.open(geotiff_path) as src:
            data = src.read(1)
            transform = src.transform
            crs = src.crs
        
        # Create tiles directory structure
        base_dir = os.path.join(self.tiles_dir, "tiles")
        os.makedirs(base_dir, exist_ok=True)
        
        tile_info = {
            "source": geotiff_path,
            "tile_url": f"/tiles/{{z}}/{{x}}/{{y}}.png",
            "bounds": self._get_bounds_from_transform(transform, data.shape),
            "zoom_levels": zoom_levels
        }
        
        # Save tile metadata
        metadata_path = os.path.join(base_dir, "metadata.json")
        with open(metadata_path, 'w') as f:
            json.dump(tile_info, f)
        
        return tile_info
    
    def _get_bounds_from_transform(self, transform, shape):
        """Extract bounds from rasterio transform"""
        left = transform.c
        top = transform.f
        right = left + transform.a * shape[1]
        bottom = top + transform.e * shape[0]
        return [left, bottom, right, top]
    
    def colorize_ndvi(self, ndvi_array):
        """
        Convert NDVI array to RGB image for visualization
        
        NDVI color scheme:
        < 0.2 (red): poor vegetation
        0.2-0.4 (yellow): fair vegetation
        0.4-0.6 (light green): moderate vegetation
        > 0.6 (dark green): good vegetation
        """
        # Normalize to 0-255
        ndvi_normalized = ((ndvi_array + 1) / 2 * 255).astype(np.uint8)
        
        # Create RGB image
        rgb = np.zeros((ndvi_array.shape[0], ndvi_array.shape[1], 3), dtype=np.uint8)
        
        # Apply color mapping
        mask_poor = ndvi_array < 0.2
        mask_fair = (ndvi_array >= 0.2) & (ndvi_array < 0.4)
        mask_moderate = (ndvi_array >= 0.4) & (ndvi_array < 0.6)
        mask_good = ndvi_array >= 0.6
        
        # Red for poor
        rgb[mask_poor] = [255, 0, 0]
        # Yellow for fair
        rgb[mask_fair] = [255, 255, 0]
        # Light green for moderate
        rgb[mask_moderate] = [144, 238, 144]
        # Dark green for good
        rgb[mask_good] = [0, 100, 0]
        
        return rgb
    
    def create_tif_with_colormap(self, ndvi_array, bounds, date=None):
        """Create a colorized GeoTIFF for direct map overlay"""
        if date is None:
            date = datetime.now().strftime("%Y%m%d")
        
        # Colorize NDVI
        rgb_array = self.colorize_ndvi(ndvi_array)
        
        filename = f"ndvi_colored_{date}_{datetime.now().strftime('%H%M%S')}.tif"
        filepath = os.path.join(self.tiles_dir, filename)
        
        transform = from_bounds(bounds[0], bounds[1], bounds[2], bounds[3],
                               rgb_array.shape[1], rgb_array.shape[0])
        
        with rasterio.open(
            filepath,
            'w',
            driver='GTiff',
            height=rgb_array.shape[0],
            width=rgb_array.shape[1],
            count=3,
            dtype=rgb_array.dtype,
            crs=CRS.from_epsg(4326),
            transform=transform
        ) as dst:
            dst.write(rgb_array[:, :, 0], 1)
            dst.write(rgb_array[:, :, 1], 2)
            dst.write(rgb_array[:, :, 2], 3)
        
        return filepath
