import geopandas as gpd
from shapely.geometry import Polygon, Point
from typing import List, Tuple, Dict
import numpy as np

def create_polygon_from_coordinates(coordinates: List[Tuple[float, float]]) -> Polygon:
    """Create a Shapely Polygon from coordinate list"""
    return Polygon(coordinates)


def calculate_polygon_area(coordinates: List[Tuple[float, float]]) -> float:
    """Calculate area of polygon in square meters"""
    polygon = create_polygon_from_coordinates(coordinates)
    # Create GeoDataFrame with metric projection for accurate area calculation
    gdf = gpd.GeoDataFrame([1], geometry=[polygon], crs="EPSG:4326")
    gdf_projected = gdf.to_crs("EPSG:3857")  # Web Mercator
    area_m2 = gdf_projected.geometry.area[0]
    return area_m2


def get_polygon_centroid(coordinates: List[Tuple[float, float]]) -> Tuple[float, float]:
    """Get center point of polygon"""
    polygon = create_polygon_from_coordinates(coordinates)
    centroid = polygon.centroid
    return (centroid.y, centroid.x)


def validate_polygon_coordinates(coordinates: List[Tuple[float, float]]) -> bool:
    """Validate polygon coordinates are valid"""
    if len(coordinates) < 3:
        return False
    
    polygon = create_polygon_from_coordinates(coordinates)
    return polygon.is_valid


def buffer_polygon(coordinates: List[Tuple[float, float]], buffer_distance: float = 0.001) -> List[Tuple[float, float]]:
    """Create a buffered polygon (expand/shrink)"""
    polygon = create_polygon_from_coordinates(coordinates)
    buffered = polygon.buffer(buffer_distance)
    return list(buffered.exterior.coords)


def check_point_in_polygon(point: Tuple[float, float], coordinates: List[Tuple[float, float]]) -> bool:
    """Check if a point is inside polygon"""
    polygon = create_polygon_from_coordinates(coordinates)
    point_obj = Point(point[1], point[0])  # lon, lat
    return polygon.contains(point_obj)


def merge_polygons(polygon_list: List[List[Tuple[float, float]]]) -> Dict:
    """Merge multiple polygons into one"""
    polygons = [create_polygon_from_coordinates(coords) for coords in polygon_list]
    gdf = gpd.GeoDataFrame(geometry=polygons)
    merged = gdf.geometry.unary_union
    
    return {
        "type": "merged_polygon",
        "area": float(merged.area),
        "bounds": merged.bounds,
        "coordinates": list(merged.exterior.coords)
    }
