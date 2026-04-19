from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models.db_models import User
from app.services.firebase import register_device_token

router = APIRouter(prefix="/users", tags=["users"])


class DeviceTokenRequest(BaseModel):
    token: str = Field(..., min_length=20, max_length=4096)


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