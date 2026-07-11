from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models.db_models import User
from app.services.firebase import (
    get_device_token_status,
    register_device_token,
    send_test_notification,
    send_test_notification_detailed,
)

router = APIRouter(prefix="/users", tags=["users"])


class DeviceTokenRequest(BaseModel):
    token: str = Field(..., min_length=20, max_length=4096)


class PushTestOut(BaseModel):
    recipient_email: str
    recipient_found: bool
    token_count: int
    success_count: int


class PushTestDetailedOut(BaseModel):
    recipient_email: str
    firebase_initialized: bool
    recipient_found: bool
    token_count: int
    success_count: int
    failure_count: int
    results: list[dict]


@router.post("/device-token", responses={400: {"description": "Invalid device token"}})
def upsert_device_token(
    body: DeviceTokenRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    token = body.token.strip()
    if not token:
        raise HTTPException(status_code=400, detail="Device token is required")

    register_device_token(db, current_user, token)
    db.commit()
    return {"message": "Device token registered"}


@router.get("/device-token/status")
def device_token_status(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    return get_device_token_status(db, current_user.email)


@router.post("/push-test", response_model=PushTestOut)
def push_test(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    status = get_device_token_status(db, current_user.email)
    success_count = send_test_notification(db, current_user.email)
    return {
        "recipient_email": status.get("recipient_email", current_user.email),
        "recipient_found": bool(status.get("recipient_found", False)),
        "token_count": int(status.get("token_count", 0)),
        "success_count": int(success_count),
    }


@router.post("/push-test/detailed", response_model=PushTestDetailedOut)
def push_test_detailed(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    return send_test_notification_detailed(db, current_user.email)