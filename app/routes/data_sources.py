from typing import Annotated, Any, Dict, Optional

from fastapi import APIRouter, Query

from app.services.external_data_sources import (
    fetch_crop_knowledge_bundle,
    fetch_esa_sentinel2_scene,
    fetch_external_sources_bundle,
    fetch_nasa_power_agro,
    fetch_noaa_nws_snapshot,
    fetch_perenual_plants,
    fetch_trefle_plants,
)


router = APIRouter(prefix="/data-sources", tags=["data-sources"])


@router.get("/catalog")
def get_data_source_catalog() -> Dict[str, Any]:
    return {
        "sources": [
            {
                "key": "nasa",
                "name": "NASA POWER",
                "type": "agro-climate",
                "coverage": "global",
                "notes": "Daily temperature, humidity, precipitation, and solar radiation.",
            },
            {
                "key": "noaa",
                "name": "NOAA National Weather Service",
                "type": "weather forecast",
                "coverage": "primarily US and territories",
                "notes": "Forecast grid and period-level weather snapshots.",
            },
            {
                "key": "esa",
                "name": "ESA Copernicus Sentinel-2",
                "type": "satellite metadata",
                "coverage": "global",
                "notes": "Latest scene metadata including acquisition time and cloud cover when available.",
            },
            {
                "key": "perenual",
                "name": "Perenual",
                "type": "plant care database",
                "coverage": "global",
                "notes": "Plant care guidance including watering, sunlight, growth rate, and care level.",
            },
            {
                "key": "trefle",
                "name": "Trefle",
                "type": "botanical plant database",
                "coverage": "global",
                "notes": "Plant taxonomy and species metadata searchable by crop name (requires TREFLE_API_KEY).",
            },
        ]
    }


@router.get("/nasa")
def get_nasa_source(
    lat: Annotated[float, Query(description="Latitude")],
    lon: Annotated[float, Query(description="Longitude")],
    start_date: Annotated[Optional[str], Query(description="Optional start date YYYY-MM-DD")] = None,
    end_date: Annotated[Optional[str], Query(description="Optional end date YYYY-MM-DD")] = None,
) -> Dict[str, Any]:
    return fetch_nasa_power_agro(latitude=lat, longitude=lon, start_date=start_date, end_date=end_date)


@router.get("/noaa")
def get_noaa_source(
    lat: Annotated[float, Query(description="Latitude")],
    lon: Annotated[float, Query(description="Longitude")],
) -> Dict[str, Any]:
    return fetch_noaa_nws_snapshot(latitude=lat, longitude=lon)


@router.get("/esa")
def get_esa_source(
    lat: Annotated[float, Query(description="Latitude")],
    lon: Annotated[float, Query(description="Longitude")],
) -> Dict[str, Any]:
    return fetch_esa_sentinel2_scene(latitude=lat, longitude=lon)


@router.get("/perenual")
def get_perenual_source(
    query: Annotated[Optional[str], Query(description="Optional plant/crop query (e.g. tomato, lettuce, basil)")] = None,
    limit: Annotated[int, Query(description="Result size 1-50", ge=1, le=50)] = 10,
) -> Dict[str, Any]:
    return fetch_perenual_plants(query=query, limit=limit)


@router.get("/trefle")
def get_trefle_source(
    query: Annotated[Optional[str], Query(description="Optional crop/plant query (e.g. tomato, maize, citrus)")] = None,
    limit: Annotated[int, Query(description="Result size 1-20", ge=1, le=20)] = 5,
) -> Dict[str, Any]:
    return fetch_trefle_plants(query=query, limit=limit)


@router.get("/crop-knowledge")
def get_crop_knowledge_source(
    crop_query: Annotated[str, Query(description="Crop to enrich using Perenual + Trefle")],
    limit: Annotated[int, Query(description="Result size 1-20", ge=1, le=20)] = 5,
) -> Dict[str, Any]:
    return fetch_crop_knowledge_bundle(crop_query=crop_query, limit=limit)


@router.get("/fusion")
def get_fused_sources(
    lat: Annotated[float, Query(description="Latitude")],
    lon: Annotated[float, Query(description="Longitude")],
    start_date: Annotated[Optional[str], Query(description="Optional start date YYYY-MM-DD for NASA POWER")] = None,
    end_date: Annotated[Optional[str], Query(description="Optional end date YYYY-MM-DD for NASA POWER")] = None,
    crop_query: Annotated[Optional[str], Query(description="Optional crop query for Perenual/Trefle knowledge enrichment")] = None,
) -> Dict[str, Any]:
    return fetch_external_sources_bundle(
        latitude=lat,
        longitude=lon,
        start_date=start_date,
        end_date=end_date,
        crop_query=crop_query,
    )
