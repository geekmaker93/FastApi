import json
import logging
import os
import base64
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import func

from app.core.config import FIREBASE_CREDENTIALS_PATH
from app.models.db_models import User, UserDeviceToken

logger = logging.getLogger("crop_backend.firebase")
PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIREBASE_CREDENTIALS_JSON = os.getenv("FIREBASE_CREDENTIALS_JSON", "").strip()
FIREBASE_CREDENTIALS_B64 = os.getenv("FIREBASE_CREDENTIALS_B64", "").strip()
FIREBASE_ANDROID_CHANNEL_ID = os.getenv("FIREBASE_ANDROID_CHANNEL_ID", "").strip()

_DEFAULT_CREDENTIAL_FILES = (
    PROJECT_ROOT / "serviceAccountKey.json",
    PROJECT_ROOT / "firebase-service-account.json",
    PROJECT_ROOT / "google-service-account.json",
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _normalize_credentials_json(raw_value: str) -> str:
    value = (raw_value or "").strip()
    if not value:
        return ""

    if value.startswith("FIREBASE_CREDENTIALS_JSON="):
        value = value.split("=", 1)[1].strip()

    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"\"", "'"}:
        value = value[1:-1].strip()

    return value


def _resolve_credentials_source() -> tuple[Optional[dict[str, Any]], Optional[Path]]:
    if FIREBASE_CREDENTIALS_B64:
        try:
            decoded = base64.b64decode(FIREBASE_CREDENTIALS_B64).decode("utf-8")
            payload = json.loads(decoded)
        except Exception:
            logger.exception("Firebase initialization skipped: FIREBASE_CREDENTIALS_B64 is not valid base64 JSON")
            return None, None
        if not isinstance(payload, dict):
            logger.warning("Firebase initialization skipped: FIREBASE_CREDENTIALS_B64 must decode to a JSON object")
            return None, None
        return payload, None

    if FIREBASE_CREDENTIALS_JSON:
        normalized_json = _normalize_credentials_json(FIREBASE_CREDENTIALS_JSON)
        if not normalized_json:
            logger.warning("Firebase initialization skipped: FIREBASE_CREDENTIALS_JSON is empty after normalization")
            return None, None
        try:
            payload = json.loads(normalized_json)
        except json.JSONDecodeError:
            logger.exception("Firebase initialization skipped: FIREBASE_CREDENTIALS_JSON is not valid JSON")
            return None, None
        if not isinstance(payload, dict):
            logger.warning("Firebase initialization skipped: FIREBASE_CREDENTIALS_JSON must decode to a JSON object")
            return None, None
        return payload, None

    if FIREBASE_CREDENTIALS_PATH:
        candidate = Path(FIREBASE_CREDENTIALS_PATH).expanduser()
        if not candidate.is_absolute():
            candidate = PROJECT_ROOT / candidate
        return None, candidate

    for candidate in _DEFAULT_CREDENTIAL_FILES:
        if candidate.is_file():
            return None, candidate

    return None, None


def initialize_firebase() -> bool:
    credentials_payload, credentials_path = _resolve_credentials_source()
    if credentials_payload is None and credentials_path is None:
        logger.info("Firebase initialization skipped: no Firebase credentials configured")
        return False

    if credentials_path is not None and not credentials_path.is_file():
        logger.warning(
            "Firebase initialization skipped: credentials file not found at %s",
            credentials_path,
        )
        return False

    try:
        import firebase_admin
        from firebase_admin import credentials
    except ImportError:
        logger.warning("Firebase initialization skipped: firebase_admin is not installed")
        return False

    if firebase_admin._apps:
        return True

    try:
        cred_source: dict[str, Any] | str = credentials_payload if credentials_payload is not None else str(credentials_path)
        cred = credentials.Certificate(cred_source)
        firebase_admin.initialize_app(cred)
        logger.info("Firebase Admin initialized")
        return True
    except Exception:
        logger.exception("Firebase initialization failed")
        return False


def register_device_token(db, user: User, token: str, platform: str = "android") -> UserDeviceToken:
    normalized_token = token.strip()
    existing = db.query(UserDeviceToken).filter(UserDeviceToken.token == normalized_token).first()
    if existing:
        existing.user_id = user.id
        existing.platform = platform
        existing.updated_at = _utc_now()
        return existing

    record = UserDeviceToken(
        user_id=user.id,
        token=normalized_token,
        platform=platform,
    )
    db.add(record)
    return record


def _cleanup_invalid_tokens(db, token_records, responses) -> None:
    stale_ids = []
    for token_record, response in zip(token_records, responses):
        if response.success:
            continue
        exception = response.exception
        logger.warning(
            "Firebase send failed for token %s: %s",
            token_record.id,
            exception,
        )
        error_code = getattr(exception, "code", "") or ""
        error_text = str(exception).lower()
        if error_code in {"registration-token-not-registered", "unregistered"}:
            stale_ids.append(token_record.id)
            continue
        if "registration token is not a valid" in error_text or "requested entity was not found" in error_text:
            stale_ids.append(token_record.id)

    if stale_ids:
        db.query(UserDeviceToken).filter(UserDeviceToken.id.in_(stale_ids)).delete(synchronize_session=False)
        db.commit()


def _get_recipient_tokens(db, recipient_email: str):
    raw_identifier = (recipient_email or "").strip()
    if not raw_identifier:
        logger.warning("Skipping notification: empty recipient identifier")
        return None, []

    normalized_identifier = raw_identifier.lower()
    recipient = db.query(User).filter(func.lower(User.email) == normalized_identifier).first()
    if recipient is None and raw_identifier.isdigit():
        recipient = db.query(User).filter(User.id == int(raw_identifier)).first()
    if recipient is None:
        matches = (
            db.query(User)
            .filter(User.name.isnot(None), func.lower(User.name) == normalized_identifier)
            .limit(2)
            .all()
        )
        if len(matches) == 1:
            recipient = matches[0]

    if recipient is None:
        logger.warning("Skipping notification: recipient not found for identifier '%s'", raw_identifier)
        return None, []

    token_records = (
        db.query(UserDeviceToken)
        .filter(UserDeviceToken.user_id == recipient.id)
        .order_by(UserDeviceToken.updated_at.desc())
        .all()
    )
    return recipient, token_records


def _build_multicast_message(messaging, tokens: list[str], title: str, body: str, data: dict[str, str]):
    notification_payload = {
        "title": title,
        "body": body,
    }
    android_notification_payload = {
        "title": title,
        "body": body,
        "sound": "default",
        "click_action": "FLUTTER_NOTIFICATION_CLICK",
    }
    # Only force a specific channel when explicitly configured.
    # If the app has not created that channel, Android may suppress display.
    if FIREBASE_ANDROID_CHANNEL_ID:
        android_notification_payload["channel_id"] = FIREBASE_ANDROID_CHANNEL_ID

    android_payload = {
        "priority": "high",
        "ttl": timedelta(seconds=120),
        "collapse_key": "social_message",
        "notification": messaging.AndroidNotification(**android_notification_payload),
    }
    data_payload = dict(data)
    data_payload["title"] = title
    data_payload["body"] = body

    return messaging.MulticastMessage(
        tokens=tokens,
        notification=messaging.Notification(**notification_payload),
        data=data_payload,
        android=messaging.AndroidConfig(**android_payload),
    )


def _send_multicast_notification(db, recipient_email: str, title: str, body: str, data: dict[str, str]) -> int:
    if not initialize_firebase():
        return 0

    recipient, token_records = _get_recipient_tokens(db, recipient_email)
    if not token_records:
        logger.info(
            "Skipping Firebase notification: no device tokens for recipient '%s'",
            getattr(recipient, "email", recipient_email),
        )
        return 0

    try:
        from firebase_admin import messaging
    except ImportError:
        logger.warning("Firebase messaging unavailable: firebase_admin is not installed")
        return 0

    try:
        message = _build_multicast_message(
            messaging,
            tokens=[record.token for record in token_records],
            title=title,
            body=body,
            data=data,
        )
    except Exception:
        logger.exception("Failed to build Firebase notification payload for %s", recipient_email)
        return 0

    try:
        response = messaging.send_each_for_multicast(message)
    except Exception:
        logger.exception("Failed to send Firebase notification to %s", recipient_email)
        return 0

    _cleanup_invalid_tokens(db, token_records, response.responses)
    logger.info(
        "Firebase notification sent to %s: %s/%s success",
        recipient_email,
        response.success_count,
        len(token_records),
    )
    return response.success_count


def send_social_activity_notification(
    db,
    recipient_email: str,
    sender_id: str,
    sender_name: str,
    activity_type: str,
    post_id: int,
    post_preview: Optional[str],
    activity_preview: Optional[str] = None,
) -> int:
    sender_label = sender_name or sender_id or "Someone"
    trimmed_post_preview = (post_preview or "").strip()
    if len(trimmed_post_preview) > 96:
        trimmed_post_preview = trimmed_post_preview[:93].rstrip() + "..."

    if activity_type == "like":
        title = "New Like"
        body = f"{sender_label} liked your post"
        if trimmed_post_preview:
            body = f"{body}: {trimmed_post_preview}"
    elif activity_type == "comment":
        title = "New Comment"
        snippet = (activity_preview or "").strip()
        if len(snippet) > 96:
            snippet = snippet[:93].rstrip() + "..."
        body = f"{sender_label} commented on your post"
        if snippet:
            body = f"{body}: {snippet}"
    elif activity_type == "mention":
        title = "New Mention"
        body = f"{sender_label} mentioned you in a post"
    else:
        title = "New Activity"
        body = activity_preview or f"{sender_label} interacted with your post"

    data = {
        "type": f"social_{activity_type}",
        "sender_id": sender_id or "",
        "sender_name": sender_name or "",
        "post_id": str(post_id),
    }
    if activity_preview:
        data["activity_preview"] = activity_preview
    if post_preview:
        data["post_preview"] = post_preview

    return _send_multicast_notification(
        db=db,
        recipient_email=recipient_email,
        title=title,
        body=body,
        data=data,
    )


def send_message_notification(
    db,
    recipient_email: str,
    sender_id: str,
    sender_name: str,
    conversation_id: int,
    message_id: int,
    message_text: str,
) -> int:
    preview = (message_text or "").strip()
    if len(preview) > 140:
        preview = preview[:137].rstrip() + "..."

    title = sender_name or sender_id or "New message"
    data = {
        "type": "social_message",
        "conversation_id": str(conversation_id),
        "message_id": str(message_id),
        "sender_id": sender_id or "",
        "sender_name": sender_name or "",
    }
    return _send_multicast_notification(
        db=db,
        recipient_email=recipient_email,
        title=title,
        body=preview or "You have a new message",
        data=data,
    )


def get_device_token_status(db, recipient_email: str) -> dict[str, Any]:
    recipient, token_records = _get_recipient_tokens(db, recipient_email)
    if recipient is None:
        return {
            "recipient_email": recipient_email,
            "recipient_found": False,
            "token_count": 0,
            "tokens": [],
        }

    tokens = []
    for record in token_records:
        token_value = (record.token or "").strip()
        masked = token_value[:12] + "..." if len(token_value) > 12 else token_value
        tokens.append(
            {
                "id": int(record.id),
                "platform": record.platform,
                "updated_at": record.updated_at.isoformat() if record.updated_at else None,
                "token_prefix": masked,
            }
        )

    return {
        "recipient_email": recipient.email,
        "recipient_found": True,
        "token_count": len(token_records),
        "tokens": tokens,
    }


def send_test_notification(db, recipient_email: str) -> int:
    return _send_multicast_notification(
        db=db,
        recipient_email=recipient_email,
        title="FarmSense test notification",
        body="Push delivery test from backend",
        data={"type": "debug_push"},
    )


def send_test_notification_detailed(db, recipient_email: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "recipient_email": recipient_email,
        "firebase_initialized": False,
        "recipient_found": False,
        "token_count": 0,
        "success_count": 0,
        "failure_count": 0,
        "results": [],
    }

    if not initialize_firebase():
        result["error"] = "firebase_not_initialized"
        return result

    result["firebase_initialized"] = True
    recipient, token_records = _get_recipient_tokens(db, recipient_email)
    if recipient is not None:
        result["recipient_email"] = recipient.email
        result["recipient_found"] = True

    if not token_records:
        result["error"] = "no_device_tokens"
        return result

    result["token_count"] = len(token_records)

    try:
        from firebase_admin import messaging
    except ImportError:
        result["error"] = "firebase_admin_not_installed"
        return result

    try:
        message = _build_multicast_message(
            messaging,
            tokens=[record.token for record in token_records],
            title="FarmSense test notification",
            body="Push delivery test from backend",
            data={"type": "debug_push"},
        )
    except Exception as exc:
        result["error"] = "build_payload_failed"
        result["error_detail"] = str(exc)
        return result

    try:
        response = messaging.send_each_for_multicast(message)
    except Exception as exc:
        result["error"] = "send_failed"
        result["error_detail"] = str(exc)
        return result

    result["success_count"] = int(response.success_count)
    result["failure_count"] = int(len(token_records) - response.success_count)

    per_token_results: list[dict[str, Any]] = []
    for token_record, token_response in zip(token_records, response.responses):
        token_value = (token_record.token or "").strip()
        token_prefix = token_value[:12] + "..." if len(token_value) > 12 else token_value
        entry: dict[str, Any] = {
            "token_id": int(token_record.id),
            "token_prefix": token_prefix,
            "success": bool(token_response.success),
        }
        if not token_response.success:
            exc = token_response.exception
            entry["error"] = str(exc)
            entry["error_code"] = getattr(exc, "code", None)
        per_token_results.append(entry)

    result["results"] = per_token_results
    _cleanup_invalid_tokens(db, token_records, response.responses)
    return result