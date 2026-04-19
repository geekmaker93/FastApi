from datetime import datetime, timezone
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models.db_models import Farm, NDVISnapshot, SnapshotAnalysis, User

router = APIRouter(tags=["snapshots"])

FARM_NOT_FOUND = "Farm not found"
SNAPSHOT_NOT_FOUND = "Snapshot not found"


# ── Pydantic schemas ───────────────────────────────────────────────────────────

class SnapshotCreate(BaseModel):
    farm_id: int
    image_path: Optional[str] = None
    image_url: Optional[str] = None
    ndvi_avg: Optional[float] = None
    ndvi_min: Optional[float] = None
    ndvi_max: Optional[float] = None
    captured_at: Optional[datetime] = None


class SnapshotAnalysisOut(BaseModel):
    id: int
    green_percent: Optional[float]
    yellow_percent: Optional[float]
    red_percent: Optional[float]
    stress_level: Optional[str]
    notes: Optional[str]
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


class SnapshotOut(BaseModel):
    id: int
    farm_id: int
    image_path: Optional[str]
    image_url: Optional[str]
    ndvi_avg: Optional[float]
    ndvi_min: Optional[float]
    ndvi_max: Optional[float]
    captured_at: Optional[datetime]
    created_at: Optional[datetime]
    analysis: Optional[SnapshotAnalysisOut]

    class Config:
        from_attributes = True


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_owned_farm(db: Session, farm_id: int, user_id: int) -> Farm:
    farm = db.query(Farm).filter(Farm.id == farm_id, Farm.user_id == user_id).first()
    if not farm:
        raise HTTPException(status_code=404, detail=FARM_NOT_FOUND)
    return farm


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.post("/snapshots", response_model=SnapshotOut, status_code=201)
def save_snapshot(
    payload: SnapshotCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """Save NDVI snapshot metadata sent from the mobile client."""
    _get_owned_farm(db, payload.farm_id, current_user.id)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    capture_ts = payload.captured_at or now
    snapshot = NDVISnapshot(
        farm_id=payload.farm_id,
        image_path=payload.image_path,
        image_url=payload.image_url,
        ndvi_avg=payload.ndvi_avg,
        ndvi_min=payload.ndvi_min,
        ndvi_max=payload.ndvi_max,
        captured_at=capture_ts,
        created_at=now,
        # Mirror into legacy fields so LAI-trend and date filters work
        date=capture_ts.date(),
        ndvi_image_path=payload.image_path,
        ndvi_stats={
            "avg": payload.ndvi_avg,
            "min": payload.ndvi_min,
            "max": payload.ndvi_max,
        } if payload.ndvi_avg is not None else None,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot


@router.get("/farms/{farm_id}/snapshots/latest", response_model=SnapshotOut)
def get_latest_snapshot(
    farm_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """Return the most recent NDVI snapshot for a farm."""
    _get_owned_farm(db, farm_id, current_user.id)

    snapshot = (
        db.query(NDVISnapshot)
        .filter(NDVISnapshot.farm_id == farm_id)
        .order_by(NDVISnapshot.captured_at.desc().nullslast(), NDVISnapshot.created_at.desc().nullslast())
        .first()
    )
    if not snapshot:
        raise HTTPException(status_code=404, detail=SNAPSHOT_NOT_FOUND)
    return snapshot


@router.get("/farms/{farm_id}/snapshots", response_model=List[SnapshotOut])
def get_snapshot_history(
    farm_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """Return full snapshot history for a farm, newest first."""
    _get_owned_farm(db, farm_id, current_user.id)

    snapshots = (
        db.query(NDVISnapshot)
        .filter(NDVISnapshot.farm_id == farm_id)
        .order_by(NDVISnapshot.captured_at.desc().nullslast(), NDVISnapshot.created_at.desc().nullslast())
        .all()
    )
    return snapshots
