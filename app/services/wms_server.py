import os
import json
from datetime import datetime
from typing import List, Dict, Any
import numpy as np
import rasterio
from rasterio.io import MemoryFile
from PIL import Image
import io

class WMSTileServer:
    """WMS-compatible tile server for serving NDVI and other layers"""
    
    def __init__(self, tiles_dir="./ndvi_tiles"):
        self.tiles_dir = tiles_dir
        os.makedirs(tiles_dir, exist_ok=True)
        self.layers = {}
    
    def register_layer(self, layer_name: str, layer_config: Dict[str, Any]):
        """
        Register a new layer in the WMS server
        
        Args:
            layer_name: Name of the layer (e.g., 'ndvi', 'yield', 'soil_moisture')
            layer_config: Configuration dict with source, bounds, style, etc.
        """
        self.layers[layer_name] = {
            "name": layer_name,
            "title": layer_config.get("title", layer_name),
            "abstract": layer_config.get("abstract", ""),
            "bounds": layer_config.get("bounds"),
            "crs": layer_config.get("crs", "EPSG:4326"),
            "source": layer_config.get("source"),
            "style": layer_config.get("style", {}),
            "created_at": datetime.now().isoformat()
        }
    
    def get_capabilities(self):
        """
        Get WMS Capabilities document (XML-like JSON representation)
        Used by mapping libraries to discover available layers
        """
        return {
            "service": "WMS",
            "version": "1.3.0",
            "title": "Crop Monitoring WMS Server",
            "abstract": "WMS service for agricultural monitoring data",
            "layers": list(self.layers.values())
        }
    
    def get_map(self, layer_name: str, bbox: List[float], width: int, height: int, 
                crs: str = "EPSG:4326", format: str = "image/png", **kwargs):
        """
        Get map tile for specified layer and bounding box
        
        Args:
            layer_name: Name of the layer to retrieve
            bbox: [minx, miny, maxx, maxy]
            width: Image width in pixels
            height: Image height in pixels
            crs: Coordinate reference system
            format: Image format (image/png, image/jpeg, etc.)
        
        Returns:
            Image bytes in specified format
        """
        if layer_name not in self.layers:
            raise ValueError(f"Layer '{layer_name}' not found")
        
        layer = self.layers[layer_name]
        
        # Load source data
        source_path = layer["source"]
        if not os.path.exists(source_path):
            raise FileNotFoundError(f"Source file not found: {source_path}")
        
        with rasterio.open(source_path) as src:
            # Read data for the requested bbox
            data = src.read(1, window=self._bbox_to_window(src, bbox))
        
        # Apply style if configured
        if layer["style"]:
            data = self._apply_style(data, layer["style"])
        
        # Resize to requested dimensions
        img = Image.fromarray(data.astype(np.uint8))
        img = img.resize((width, height), Image.Resampling.BILINEAR)
        
        # Convert to requested format
        output = io.BytesIO()
        img.save(output, format=self._get_pil_format(format))
        output.seek(0)
        
        return output.getvalue()
    
    def get_feature_info(self, layer_name: str, x: float, y: float, 
                        info_format: str = "application/json"):
        """
        Get feature information for a specific point
        
        Args:
            layer_name: Name of the layer
            x, y: Coordinates
            info_format: Format for response (json, html, text)
        
        Returns:
            Feature information
        """
        if layer_name not in self.layers:
            raise ValueError(f"Layer '{layer_name}' not found")
        
        layer = self.layers[layer_name]
        source_path = layer["source"]
        
        with rasterio.open(source_path) as src:
            # Get pixel value at coordinate
            row, col = src.index(x, y)
            if 0 <= row < src.height and 0 <= col < src.width:
                value = src.read(1)[int(row), int(col)]
                
                if info_format == "application/json":
                    return {
                        "layer": layer_name,
                        "coordinate": [x, y],
                        "value": float(value),
                        "interpretation": self._interpret_value(layer_name, value)
                    }
                else:
                    return f"{layer_name}: {value:.4f}"
            else:
                return {"error": "Coordinate outside layer bounds"}
    
    def list_layers(self):
        """List all available layers"""
        return {
            "count": len(self.layers),
            "layers": [
                {
                    "name": layer["name"],
                    "title": layer["title"],
                    "abstract": layer["abstract"]
                }
                for layer in self.layers.values()
            ]
        }
    
    def _bbox_to_window(self, src, bbox):
        """Convert bbox to rasterio window"""
        minx, miny, maxx, maxy = bbox
        
        # Get pixel indices
        row_start, col_start = src.index(minx, maxy)
        row_end, col_end = src.index(maxx, miny)
        
        return rasterio.windows.Window(
            col_start, row_start, 
            col_end - col_start, 
            row_end - row_start
        )
    
    def _apply_style(self, data: np.ndarray, style: Dict[str, Any]):
        """Apply style configuration to data"""
        if style.get("colormap"):
            # Apply colormap
            colormap = style["colormap"]
            colored = np.zeros((data.shape[0], data.shape[1], 3), dtype=np.uint8)
            
            for color_range, rgb in colormap.items():
                if isinstance(color_range, str) and "-" in color_range:
                    min_val, max_val = map(float, color_range.split("-"))
                    mask = (data >= min_val) & (data < max_val)
                    colored[mask] = rgb
            
            return colored
        
        return data
    
    def _interpret_value(self, layer_name: str, value: float) -> str:
        """Interpret pixel value based on layer type"""
        if layer_name == "ndvi":
            if value < 0.2:
                return "Poor vegetation"
            elif value < 0.4:
                return "Fair vegetation"
            elif value < 0.6:
                return "Moderate vegetation"
            else:
                return "Good vegetation"
        elif layer_name == "soil_moisture":
            if value < 20:
                return "Dry"
            elif value < 50:
                return "Moderate"
            else:
                return "Wet"
        elif layer_name == "yield":
            return f"Estimated yield: {value:.2f} units/ha"
        
        return str(value)
    
    def _get_pil_format(self, mime_type: str) -> str:
        """Convert MIME type to PIL format"""
        formats = {
            "image/png": "PNG",
            "image/jpeg": "JPEG",
            "image/tiff": "TIFF",
            "image/gif": "GIF"
        }
        return formats.get(mime_type, "PNG")
    
    def save_configuration(self, config_path: str = None):
        """Save WMS configuration to file"""
        if config_path is None:
            config_path = os.path.join(self.tiles_dir, "wms_config.json")
        
        config = {
            "service": "WMS",
            "version": "1.3.0",
            "layers": self.layers
        }
        
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        
        return config_path
    
    def load_configuration(self, config_path: str):
        """Load WMS configuration from file"""
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        self.layers = config.get("layers", {})
        return len(self.layers)
