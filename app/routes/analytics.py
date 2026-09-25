import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models.db_models import AnalyticsEvent, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["Analytics"])


class AnalyticsEventCreate(BaseModel):
    event_name: str = Field(..., min_length=1, max_length=100)
    event_data: dict[str, Any] | None = None
    session_id: str | None = Field(default=None, max_length=128)
    platform: str | None = Field(default=None, max_length=30)
    app_version: str | None = Field(default=None, max_length=30)


@router.post("/events")
def create_analytics_event(
    event: AnalyticsEventCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    event_name = event.event_name.strip()
    if not event_name:
        raise HTTPException(status_code=422, detail="event_name cannot be blank")

    analytics_event = AnalyticsEvent(
        user_id=current_user.id,
        session_id=event.session_id,
        event_name=event_name,
        event_data=event.event_data or {},
        platform=event.platform,
        app_version=event.app_version,
    )

    try:
        db.add(analytics_event)
        db.commit()
        db.refresh(analytics_event)
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Failed to record analytics event")
        raise HTTPException(
            status_code=500,
            detail="Failed to record analytics event",
        ) from exc

    return {"success": True, "event_id": analytics_event.id}