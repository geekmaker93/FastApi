from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models.db_models import AnalyticsEvent, User

router = APIRouter(prefix="/admin", tags=["Admin"])


def require_admin(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


def _mask_email(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    local_part, domain = email.split("@", 1)
    return f"{local_part[:1]}***@{domain}"


@router.get("/overview")
def admin_overview(
    db: Annotated[Session, Depends(get_db)],
    admin_user: Annotated[User, Depends(require_admin)],
):
    total_users = db.query(func.count(User.id)).scalar()
    total_events = db.query(func.count(AnalyticsEvent.id)).scalar()
    active_users = (
        db.query(func.count(func.distinct(AnalyticsEvent.user_id)))
        .filter(AnalyticsEvent.user_id.isnot(None))
        .scalar()
    )
    return {
        "total_users": total_users or 0,
        "total_events": total_events or 0,
        "active_users": active_users or 0,
    }


@router.get("/users")
def admin_users(
    db: Annotated[Session, Depends(get_db)],
    admin_user: Annotated[User, Depends(require_admin)],
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    event_counts = (
        db.query(
            AnalyticsEvent.user_id.label("user_id"),
            func.count(AnalyticsEvent.id).label("event_count"),
        )
        .filter(AnalyticsEvent.user_id.isnot(None))
        .group_by(AnalyticsEvent.user_id)
        .subquery()
    )
    rows = (
        db.query(User, func.coalesce(event_counts.c.event_count, 0))
        .outerjoin(event_counts, User.id == event_counts.c.user_id)
        .order_by(User.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [
        {
            "id": user.id,
            "name": user.name,
            "email_masked": _mask_email(user.email),
            "subscription_plan": user.subscription_plan,
            "is_verified": user.is_verified,
            "is_online": user.is_online,
            "created_at": getattr(user, "created_at", None),
            "event_count": event_count,
        }
        for user, event_count in rows
    ]


@router.get("/users/{user_id}")
def admin_user_activity(
    user_id: int,
    db: Annotated[Session, Depends(get_db)],
    admin_user: Annotated[User, Depends(require_admin)],
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    events = (
        db.query(AnalyticsEvent)
        .filter(AnalyticsEvent.user_id == user_id)
        .order_by(AnalyticsEvent.created_at.desc(), AnalyticsEvent.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "subscription_plan": user.subscription_plan,
            "is_verified": user.is_verified,
        },
        "events": [
            {
                "id": event.id,
                "event_name": event.event_name,
                "event_data": event.event_data,
                "session_id": event.session_id,
                "platform": event.platform,
                "app_version": event.app_version,
                "created_at": event.created_at,
            }
            for event in events
        ],
    }


@router.get("/analytics/features")
def feature_analytics(
    db: Annotated[Session, Depends(get_db)],
    admin_user: Annotated[User, Depends(require_admin)],
):
    results = (
        db.query(
            AnalyticsEvent.event_name,
            func.count(AnalyticsEvent.id).label("usage"),
        )
        .group_by(AnalyticsEvent.event_name)
        .order_by(func.count(AnalyticsEvent.id).desc(), AnalyticsEvent.event_name)
        .all()
    )
    return [{"event_name": event_name, "usage": usage} for event_name, usage in results]


@router.get("/analytics/events")
def analytics_events(
    db: Annotated[Session, Depends(get_db)],
    admin_user: Annotated[User, Depends(require_admin)],
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    events = (
        db.query(AnalyticsEvent)
        .order_by(AnalyticsEvent.created_at.desc(), AnalyticsEvent.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [
        {
            "id": event.id,
            "user_id": event.user_id,
            "event_name": event.event_name,
            "event_data": event.event_data,
            "session_id": event.session_id,
            "platform": event.platform,
            "app_version": event.app_version,
            "created_at": event.created_at,
        }
        for event in events
    ]