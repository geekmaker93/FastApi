from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Date, cast, func
from sqlalchemy.orm import Session
from app.models.schemas import FarmCreate, SoilProfileLocationRequest
from app.models.db_models import Farm, User, NDVISnapshot, SoilProfile, FarmLiveState
from app.services.agromonitoring import create_polygon
from app.dependencies import get_current_user, get_db
from app.services.ndvi import calculate_lai_from_ndvi
from app.services.farm_live import extract_farm_coordinates, refresh_farm_live_state, serialize_live_state
from app.services.region_mapper import get_region
from app.services.region_profiles import REGION_PROFILES
from app.services.soilgrids import serialize_soil_profile, upsert_farm_soil_profile, upsert_soil_profile

router = APIRouter(prefix="/farms", tags=["farms"])
FARM_NOT_FOUND = "Farm not found"


def _safe_float(value, default=None):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _extract_farm_coordinates(polygon):
    return extract_farm_coordinates(polygon)


def _derive_region_metadata(polygon):
    coordinates = _extract_farm_coordinates(polygon)
    latitude = _safe_float(coordinates.get("latitude"), None)
    longitude = _safe_float(coordinates.get("longitude"), None)
    region = get_region(latitude, longitude)
    profile = REGION_PROFILES.get(region, {}) if region else {}
    preferred_crops = [str(item).strip() for item in (profile.get("preferred_crops") or []) if str(item).strip()][:3]
    risk_factors = [str(item).strip() for item in (profile.get("risk_factors") or []) if str(item).strip()]

    return {
        "region": region or "default",
        "coordinates": coordinates,
        "regional_recommendations": preferred_crops,
        "risk_factors": risk_factors,
    }


def _resolve_snapshot_ndvi(snapshot: NDVISnapshot):
    stats = snapshot.ndvi_stats if isinstance(snapshot.ndvi_stats, dict) else {}
    for key in ("mean", "avg", "median"):
        value = _safe_float(stats.get(key), None)
        if value is not None:
            return value
    # Fall back to the dedicated column (used by snapshots saved from the mobile app)
    return _safe_float(getattr(snapshot, "ndvi_avg", None), None)



def _lai_health(lai_value: float) -> str:
    if lai_value >= 4.0:
        return "High canopy density"
    if lai_value >= 2.0:
        return "Moderate canopy density"
    if lai_value > 0.0:
        return "Low canopy density"
    return "Bare or very sparse vegetation"


def _soil_summary(profile: SoilProfile | None):
    if profile is None:
        return None
    return {
        "fetched_at": profile.fetched_at,
        "source": profile.source,
        "derived_properties": (profile.derived_properties or {}),
    }


def _get_owned_farm_or_404(db: Session, farm_id: int, user_id: int) -> Farm:
    farm = db.query(Farm).filter(Farm.id == farm_id, Farm.user_id == user_id).first()
    if not farm:
        raise HTTPException(status_code=404, detail=FARM_NOT_FOUND)
    return farm

@router.post("/")
def create_farm(
    farm: FarmCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """Create a new farm with polygon and store in database"""
    try:
        # Register polygon with AgroMonitoring (best-effort)
        agro_polygon = None
        agro_error = None
        try:
            agro_polygon = create_polygon(farm.name, farm.polygon)
        except Exception as agro_exc:
            agro_error = str(agro_exc)
        
        # Create farm in database
        new_farm = Farm(
            user_id=current_user.id,
            name=farm.name,
            crop_type="Not specified",  # Can be added to FarmCreate schema
            polygon=farm.polygon
        )
        db.add(new_farm)
        db.commit()
        db.refresh(new_farm)

        soil_profile = None
        soil_warning = None
        try:
            soil_profile = upsert_farm_soil_profile(db, new_farm, force_refresh=True)
        except Exception as soil_exc:
            soil_warning = f"SoilGrids fetch failed: {soil_exc}"

        live_state = None
        live_warning = None
        try:
            live_state = refresh_farm_live_state(db, new_farm, force_refresh_soil=False)
        except Exception as live_exc:
            live_warning = f"Live farm data refresh failed: {live_exc}"

        region_meta = _derive_region_metadata(new_farm.polygon)

        response = {
            "id": new_farm.id,
            "name": new_farm.name,
            "polygon_id": agro_polygon["id"] if agro_polygon and "id" in agro_polygon else None,
            "message": "Farm created successfully",
            "region": region_meta["region"],
            "coordinates": region_meta["coordinates"],
            "regional_recommendations": region_meta["regional_recommendations"],
            "regional_risk_factors": region_meta["risk_factors"],
            "soil_profile": _soil_summary(soil_profile),
            "live_data": serialize_live_state(live_state),
        }
        warnings = []
        if agro_error:
            warnings.append(f"AgroMonitoring polygon registration failed: {agro_error}")
        if soil_warning:
            warnings.append(soil_warning)
        if live_warning:
            warnings.append(live_warning)
        if warnings:
            response["warning"] = " | ".join(warnings)

        return response
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{farm_id}")
def get_farm(
    farm_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """Get farm by ID"""
    farm = _get_owned_farm_or_404(db, farm_id, current_user.id)
    soil_profile = db.query(SoilProfile).filter(SoilProfile.farm_id == farm_id).first()
    live_state = db.query(FarmLiveState).filter(FarmLiveState.farm_id == farm_id).first()
    
    return {
        "id": farm.id,
        "name": farm.name,
        "crop_type": farm.crop_type,
        "polygon": farm.polygon,
        "user_id": farm.user_id,
        "soil_profile": _soil_summary(soil_profile),
        "live_data": serialize_live_state(live_state),
    }

@router.get("/")
def list_farms(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """List all farms"""
    farms = db.query(Farm).filter(Farm.user_id == current_user.id).all()
    soil_profiles = db.query(SoilProfile).filter(SoilProfile.farm_id.is_not(None)).all()
    live_states = db.query(FarmLiveState).all()
    soil_by_farm = {profile.farm_id: profile for profile in soil_profiles}
    live_by_farm = {state.farm_id: state for state in live_states}
    return [
        {
            "id": farm.id,
            "name": farm.name,
            "crop_type": farm.crop_type,
            "user_id": farm.user_id,
            "polygon": farm.polygon,
            "soil_profile": _soil_summary(soil_by_farm.get(farm.id)),
            "live_data": serialize_live_state(live_by_farm.get(farm.id)),
        }
        for farm in farms
    ]


@router.get("/{farm_id}/live-data")
def get_farm_live_data(
    farm_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    farm = _get_owned_farm_or_404(db, farm_id, current_user.id)
    live_state = db.query(FarmLiveState).filter(FarmLiveState.farm_id == farm.id).first()
    if live_state is None:
        live_state = refresh_farm_live_state(db, farm, force_refresh_soil=False)
    return serialize_live_state(live_state)


@router.post("/{farm_id}/live-data/refresh")
def force_refresh_farm_live_data(
    farm_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    farm = _get_owned_farm_or_404(db, farm_id, current_user.id)
    live_state = refresh_farm_live_state(db, farm, force_refresh_soil=True)
    return serialize_live_state(live_state)


@router.post("/soil-profile/location")
def get_location_soil_profile(
    body: SoilProfileLocationRequest,
    _current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """Fetch and persist a SoilGrids profile for a tapped location."""
    try:
        profile = upsert_soil_profile(
            db=db,
            latitude=body.latitude,
            longitude=body.longitude,
            farm=None,
            force_refresh=False,
            label=body.label,
        )
        return serialize_soil_profile(profile)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"SoilGrids unavailable: {exc}")

@router.get("/{farm_id}/ndvi")
def get_farm_ndvi_snapshots(
    farm_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """Get all NDVI snapshots for a specific farm"""
    # Check if farm exists
    farm = _get_owned_farm_or_404(db, farm_id, current_user.id)
    
    # Get all NDVI snapshots for this farm
    snapshots = db.query(NDVISnapshot).filter(NDVISnapshot.farm_id == farm_id).all()
    
    return {
        "farm_id": farm_id,
        "farm_name": farm.name,
        "total_snapshots": len(snapshots),
        "snapshots": [
            {
                "id": snapshot.id,
                "date": snapshot.date.isoformat(),
                "ndvi_image_path": snapshot.ndvi_image_path,
                "ndvi_stats": snapshot.ndvi_stats
            }
            for snapshot in snapshots
        ]
    }
@router.post("/{farm_id}/soil-profile/refresh")
def refresh_farm_soil_profile(
    farm_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    farm = _get_owned_farm_or_404(db, farm_id, current_user.id)

    try:
        profile = upsert_farm_soil_profile(db, farm, force_refresh=True)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"SoilGrids unavailable: {exc}")

    if profile is None:
        raise HTTPException(status_code=400, detail="Farm polygon is missing valid coordinates")

    return serialize_soil_profile(profile)


@router.get("/{farm_id}/soil-profile")
def get_farm_soil_profile(
    farm_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    farm = _get_owned_farm_or_404(db, farm_id, current_user.id)

    soil_profile = db.query(SoilProfile).filter(SoilProfile.farm_id == farm_id).first()
    if soil_profile is None:
        try:
            soil_profile = upsert_farm_soil_profile(db, farm, force_refresh=True)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"SoilGrids unavailable: {exc}")

    if soil_profile is None:
        raise HTTPException(status_code=400, detail="Farm polygon is missing valid coordinates")

    return serialize_soil_profile(soil_profile)


@router.get("/{farm_id}/lai-trend")
def get_farm_lai_trend(
    farm_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    start_date: Annotated[str | None, Query()] = None,
    end_date: Annotated[str | None, Query()] = None,
):
    """Get LAI trend for a farm by converting stored NDVI history into LAI values."""
    farm = _get_owned_farm_or_404(db, farm_id, current_user.id)

    query = db.query(NDVISnapshot).filter(NDVISnapshot.farm_id == farm_id)
    if start_date:
        query = query.filter(
            func.coalesce(NDVISnapshot.date, cast(NDVISnapshot.captured_at, Date)) >= date.fromisoformat(start_date)
        )
    if end_date:
        query = query.filter(
            func.coalesce(NDVISnapshot.date, cast(NDVISnapshot.captured_at, Date)) <= date.fromisoformat(end_date)
        )

    snapshots = query.order_by(
        func.coalesce(NDVISnapshot.date, cast(NDVISnapshot.captured_at, Date)).asc().nullslast()
    ).all()
    points = []
    for snapshot in snapshots:
        ndvi_value = _resolve_snapshot_ndvi(snapshot)
        if ndvi_value is None:
            continue
        lai_value = calculate_lai_from_ndvi(ndvi_value)
        points.append(
            {
                "snapshot_id": snapshot.id,
                "date": snapshot.date.isoformat() if snapshot.date else None,
                "ndvi": round(ndvi_value, 4),
                "lai": round(lai_value, 4),
                "health_status": _lai_health(lai_value),
            }
        )

    latest_lai = points[-1]["lai"] if points else None
    first_lai = points[0]["lai"] if points else None
    change = round(latest_lai - first_lai, 4) if latest_lai is not None and first_lai is not None else None

    return {
        "farm_id": farm.id,
        "farm_name": farm.name,
        "crop_type": farm.crop_type,
        "location": _extract_farm_coordinates(farm.polygon),
        "count": len(points),
        "points": points,
        "summary": {
            "latest_lai": latest_lai,
            "trend_change": change,
            "latest_health_status": points[-1]["health_status"] if points else "No LAI history yet",
        },
    }
