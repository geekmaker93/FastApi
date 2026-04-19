from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.dependencies import get_db
from app.models.db_models import Farm, YieldResult
from app.services.yield_raster import generate_yield_raster
import io
import math
import os
from typing import Optional
import rasterio
from rasterio.windows import from_bounds
from PIL import Image

router = APIRouter(prefix="/tiles", tags=["tiles"])

YIELD_TILES_DIR = "./tiles/yield"


def _tile_bounds(z: int, x: int, y: int):
    n = 2 ** z
    lon_min = x / n * 360.0 - 180.0
    lon_max = (x + 1) / n * 360.0 - 180.0
    lat_min = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))
    lat_max = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    return lon_min, lat_min, lon_max, lat_max


def _render_tile_from_raster(raster_path: str, z: int, x: int, y: int) -> bytes:
    with rasterio.open(raster_path) as src:
        lon_min, lat_min, lon_max, lat_max = _tile_bounds(z, x, y)
        window = from_bounds(lon_min, lat_min, lon_max, lat_max, src.transform)
        window = window.round_offsets().round_lengths()

        if src.count >= 3:
            data = src.read([1, 2, 3], window=window, boundless=True, fill_value=0)
            rgb = data.transpose(1, 2, 0)
            img = Image.fromarray(rgb.astype("uint8"), mode="RGB")
        else:
            data = src.read(1, window=window, boundless=True, fill_value=0)
            img = Image.fromarray(data.astype("uint8"), mode="L").convert("RGB")

        img = img.resize((256, 256), Image.Resampling.NEAREST)
        output = io.BytesIO()
        img.save(output, format="PNG")
        output.seek(0)
        return output.read()

@router.get("/ndvi/farm/{farm_id}/tilejson")
async def get_ndvi_tilejson(farm_id: int, date: str):
    """Get TileJSON manifest"""
    return {
        "tilejson": "2.2.0",
        "name": f"NDVI Farm {farm_id}",
        "date": date,
        "tiles": [f"/tiles/ndvi/farm/{farm_id}/tile/{{z}}/{{x}}/{{y}}.png?date={date}"]
    }

@router.get("/ndvi/farm/{farm_id}/tile/{z}/{x}/{y}.png")
async def get_ndvi_tile(farm_id: int, z: int, x: int, y: int, date: str = None):
    """Get NDVI tile"""
    return {"tile": f"z={z}, x={x}, y={y}", "farm_id": farm_id, "date": date}

@router.get("/yield/farm/{farm_id}/tilejson")
async def get_yield_tilejson(farm_id: int):
    """Get yield TileJSON"""
    return {
        "tilejson": "2.2.0",
        "name": f"Yield Farm {farm_id}",
        "tiles": [f"/tiles/yield/farm/{farm_id}/tile/{{z}}/{{x}}/{{y}}.png"],
        "minzoom": 10,
        "maxzoom": 19
    }

@router.get("/yield/farm/{farm_id}/tile/{z}/{x}/{y}.png")
async def get_yield_tile(farm_id: int, z: int, x: int, y: int):
    """Get yield tile"""
    # Use the most recent generated yield tile for the farm
    if not os.path.isdir(YIELD_TILES_DIR):
        raise HTTPException(status_code=404, detail="Yield tiles not generated")

    candidates = [
        f for f in os.listdir(YIELD_TILES_DIR)
        if f.startswith(f"yield_farm_{farm_id}_") and f.endswith("_colored.tif")
    ]

    if not candidates:
        raise HTTPException(status_code=404, detail="Yield tiles not generated")

    latest = sorted(candidates)[-1]
    raster_path = os.path.join(YIELD_TILES_DIR, latest)
    tile_bytes = _render_tile_from_raster(raster_path, z, x, y)
    return StreamingResponse(io.BytesIO(tile_bytes), media_type="image/png")


@router.post("/yield/farm/{farm_id}/generate")
def generate_yield_tiles(farm_id: int, db: Session = Depends(get_db)):
    """Generate yield raster tiles for a farm."""
    try:
        farm = db.query(Farm).filter(Farm.id == farm_id).first()
        if not farm:
            raise HTTPException(status_code=404, detail="Farm not found")

        yields = db.query(YieldResult).filter(YieldResult.farm_id == farm_id).all()
        if not yields:
            raise HTTPException(status_code=404, detail="No yield data for farm")

        polygon_coords = farm.polygon or []
        if len(polygon_coords) < 3:
            polygon_coords = [
                (18.0176, -76.8103),
                (18.0184, -76.8103),
                (18.0184, -76.8095),
                (18.0176, -76.8095)
            ]
        yield_values = [y.yield_estimate for y in yields]

        _, colored_path = generate_yield_raster(
            farm_id=farm_id,
            polygon_coords=polygon_coords,
            yield_values=yield_values,
            output_dir=YIELD_TILES_DIR,
            size=256,
        )

        return {
            "status": "generated",
            "farm_id": farm_id,
            "raster": colored_path,
            "tilejson": f"/tiles/yield/farm/{farm_id}/tilejson"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/wms/capabilities")
async def get_wms_capabilities():
    """WMS capabilities"""
    return {
        "service": "WMS",
        "version": "1.3.0",
        "layers": ["ndvi", "yield"]
    }


