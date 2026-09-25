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
from app.services.ai_usage import DEFAULT_FREE_LIMIT, ensure_usage_window, usage_snapshot
from app.services.google_play_billing import (
    GooglePlayBillingError,
    verify_play_product,
    verify_play_subscription,
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


class GooglePlayVerifyRequest(BaseModel):
    purchase_token: str = Field(..., min_length=10, max_length=4096)
    package_name: str | None = None
    product_id: str | None = None
    purchase_type: str = Field(default="subscription")


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


@router.post(
    "/subscription/google-play/verify",
    responses={
        400: {"description": "Invalid verification request"},
        502: {"description": "Google Play verification error"},
    },
)
def verify_google_play_subscription(
    body: GooglePlayVerifyRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    purchase_type = (body.purchase_type or "subscription").strip().lower()
    try:
        if purchase_type == "inapp":
            verification = verify_play_product(
                purchase_token=body.purchase_token,
                product_id=body.product_id or "",
                package_name=body.package_name,
            )
        else:
            verification = verify_play_subscription(
                purchase_token=body.purchase_token,
                package_name=body.package_name,
            )
    except GooglePlayBillingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Google Play verification failed: {exc}") from exc

    is_pro = bool(verification.get("is_pro", False))
    current_user.subscription_plan = "PRO" if is_pro else "FREE"
    if is_pro:
        current_user.ai_requests_limit = -1
    else:
        current_user.ai_requests_limit = DEFAULT_FREE_LIMIT
        if ensure_usage_window(current_user):
            db.add(current_user)

    db.add(current_user)
    db.commit()
    db.refresh(current_user)

    return {
        "message": "Subscription verified" if is_pro else "Subscription not active",
        "is_pro": is_pro,
        "verification": {
            "ok": verification.get("ok"),
            "reason": verification.get("reason"),
            "status_code": verification.get("status_code"),
            "subscription_state": verification.get("subscription_state"),
            "product_id": verification.get("product_id"),
            "expiry_time": verification.get("expiry_time"),
            "product_allowed": verification.get("product_allowed"),
        },
        "usage": usage_snapshot(current_user),
    }