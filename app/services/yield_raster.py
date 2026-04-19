import os
from datetime import datetime
from typing import List, Tuple
import numpy as np
import rasterio
from rasterio.transform import from_bounds
from rasterio.crs import CRS
from shapely.geometry import Polygon


def _normalize_coords(coords: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """Return coords as (lon, lat) tuples, handling (lat, lon) input."""
    normalized = []
    for a, b in coords:
        # If first value is outside latitude range, treat as lon
        if abs(a) > 90 and abs(b) <= 90:
            lon, lat = a, b
        # If second value is outside latitude range, treat as lon
        elif abs(b) > 90 and abs(a) <= 90:
            lon, lat = b, a
        else:
            # Assume (lat, lon)
            lon, lat = b, a
        normalized.append((lon, lat))
    return normalized


def _polygon_bounds(coords: List[Tuple[float, float]]) -> Tuple[float, float, float, float]:
    normalized = _normalize_coords(coords)
    if len(normalized) < 4:
        # Close ring if missing last point
        if len(normalized) >= 3:
            normalized = normalized + [normalized[0]]
        else:
            raise ValueError("Polygon requires at least 4 coordinates (including closure).")
    if normalized[0] != normalized[-1]:
        normalized.append(normalized[0])
    poly = Polygon(normalized)
    return poly.bounds  # (minx, miny, maxx, maxy)


def _yield_colormap(values: np.ndarray) -> np.ndarray:
    """Colorize yield raster (low=blue, mid=green/yellow, high=red)."""
    vmin = float(np.nanmin(values))
    vmax = float(np.nanmax(values))
    if vmax - vmin < 1e-6:
        vmax = vmin + 1.0
    norm = (values - vmin) / (vmax - vmin)
    rgb = np.zeros((values.shape[0], values.shape[1], 3), dtype=np.uint8)

    # 0-0.33: blue -> green
    mask = norm <= 0.33
    ratio = np.clip(norm / 0.33, 0, 1)
    rgb[..., 0][mask] = 0
    rgb[..., 1][mask] = (ratio[mask] * 255).astype(np.uint8)
    rgb[..., 2][mask] = (255 - ratio[mask] * 155).astype(np.uint8)

    # 0.33-0.66: green -> yellow
    mask = (norm > 0.33) & (norm <= 0.66)
    ratio = (norm - 0.33) / 0.33
    rgb[..., 0][mask] = (ratio[mask] * 255).astype(np.uint8)
    rgb[..., 1][mask] = 255
    rgb[..., 2][mask] = 0

    # 0.66-1.0: yellow -> red
    mask = norm > 0.66
    ratio = (norm - 0.66) / 0.34
    rgb[..., 0][mask] = 255
    rgb[..., 1][mask] = (255 - ratio[mask] * 255).astype(np.uint8)
    rgb[..., 2][mask] = 0

    return rgb


def generate_yield_raster(
    farm_id: int,
    polygon_coords: List[Tuple[float, float]],
    yield_values: List[float],
    output_dir: str = "./tiles/yield",
    size: int = 256,
) -> Tuple[str, str]:
    """Create a yield GeoTIFF + colored GeoTIFF for a farm.

    Returns (raw_path, colored_path).
    """
    if not polygon_coords:
        raise ValueError("Farm polygon is required to generate yield raster.")
    if not yield_values:
        raise ValueError("Yield values are required to generate yield raster.")

    os.makedirs(output_dir, exist_ok=True)

    minx, miny, maxx, maxy = _polygon_bounds(polygon_coords)

    # Create synthetic raster based on yield statistics
    mean_yield = float(np.mean(yield_values))
    std_yield = float(np.std(yield_values))
    noise = np.random.normal(loc=0.0, scale=max(std_yield, 1.0), size=(size, size))
    raster = np.clip(mean_yield + noise, a_min=0, a_max=None).astype(np.float32)

    transform = from_bounds(minx, miny, maxx, maxy, size, size)

    date_tag = datetime.now().strftime("%Y%m%d%H%M%S")
    raw_path = os.path.join(output_dir, f"yield_farm_{farm_id}_{date_tag}.tif")
    colored_path = os.path.join(output_dir, f"yield_farm_{farm_id}_{date_tag}_colored.tif")

    # Write raw raster
    with rasterio.open(
        raw_path,
        "w",
        driver="GTiff",
        height=size,
        width=size,
        count=1,
        dtype=raster.dtype,
        crs=CRS.from_epsg(4326),
        transform=transform,
        nodata=0,
        compress="lzw",
    ) as dst:
        dst.write(raster, 1)
        dst.update_tags(1, mean_yield=mean_yield, std_yield=std_yield)

    # Write colored raster
    rgb = _yield_colormap(raster)
    with rasterio.open(
        colored_path,
        "w",
        driver="GTiff",
        height=size,
        width=size,
        count=3,
        dtype=rgb.dtype,
        crs=CRS.from_epsg(4326),
        transform=transform,
        nodata=0,
        compress="lzw",
    ) as dst:
        dst.write(rgb[:, :, 0], 1)
        dst.write(rgb[:, :, 1], 2)
        dst.write(rgb[:, :, 2], 3)

    return raw_path, colored_path
