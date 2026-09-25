import base64
import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

from app.services.ai_usage import PRO_PLAN

logger = logging.getLogger("crop_backend.google_play")

GOOGLE_PLAY_PACKAGE_NAME = os.getenv("GOOGLE_PLAY_PACKAGE_NAME", "").strip()
GOOGLE_PLAY_CREDENTIALS_B64 = os.getenv("GOOGLE_PLAY_CREDENTIALS_B64", "").strip()
GOOGLE_PLAY_CREDENTIALS_JSON = os.getenv("GOOGLE_PLAY_CREDENTIALS_JSON", "").strip()
GOOGLE_PLAY_CREDENTIALS_PATH = os.getenv("GOOGLE_PLAY_CREDENTIALS_PATH", "").strip()
GOOGLE_PLAY_PRO_PRODUCT_IDS = [
    item.strip() for item in (os.getenv("GOOGLE_PLAY_PRO_PRODUCT_IDS", "").split(",")) if item.strip()
]

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CREDENTIAL_FILES = (
    PROJECT_ROOT / "google-play-service-account.json",
    PROJECT_ROOT / "serviceAccountKey.json",
)

_ANDROID_PUBLISHER_SCOPE = "https://www.googleapis.com/auth/androidpublisher"
_SUBSCRIPTION_V2_URL = "https://androidpublisher.googleapis.com/androidpublisher/v3/applications/{package_name}/purchases/subscriptionsv2/tokens/{purchase_token}"
_PRODUCT_URL = "https://androidpublisher.googleapis.com/androidpublisher/v3/applications/{package_name}/purchases/products/{product_id}/tokens/{purchase_token}"


class GooglePlayBillingError(RuntimeError):
    pass


def _normalize_json(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return ""
    if value.startswith("GOOGLE_PLAY_CREDENTIALS_JSON="):
        value = value.split("=", 1)[1].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"\"", "'"}:
        value = value[1:-1].strip()
    return value


def _resolve_credentials_payload() -> Optional[dict[str, Any]]:
    if GOOGLE_PLAY_CREDENTIALS_B64:
        try:
            decoded = base64.b64decode(GOOGLE_PLAY_CREDENTIALS_B64).decode("utf-8")
            payload = json.loads(decoded)
            if isinstance(payload, dict):
                return payload
        except Exception:
            logger.exception("Invalid GOOGLE_PLAY_CREDENTIALS_B64 payload")

    normalized = _normalize_json(GOOGLE_PLAY_CREDENTIALS_JSON)
    if normalized:
        try:
            payload = json.loads(normalized)
            if isinstance(payload, dict):
                return payload
        except Exception:
            logger.exception("Invalid GOOGLE_PLAY_CREDENTIALS_JSON payload")

    if GOOGLE_PLAY_CREDENTIALS_PATH:
        candidate = Path(GOOGLE_PLAY_CREDENTIALS_PATH).expanduser()
        if not candidate.is_absolute():
            candidate = PROJECT_ROOT / candidate
        if candidate.is_file():
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    payload = json.load(f)
                if isinstance(payload, dict):
                    return payload
            except Exception:
                logger.exception("Failed loading GOOGLE_PLAY_CREDENTIALS_PATH file")

    for candidate in _DEFAULT_CREDENTIAL_FILES:
        if not candidate.is_file():
            continue
        try:
            with open(candidate, "r", encoding="utf-8") as f:
                payload = json.load(f)
            if isinstance(payload, dict):
                return payload
        except Exception:
            logger.exception("Failed loading Google Play fallback credentials from %s", candidate)

    return None


def _get_authorized_session():
    try:
        from google.auth.transport.requests import AuthorizedSession
        from google.oauth2 import service_account
    except Exception as exc:
        raise GooglePlayBillingError("google-auth is not installed") from exc

    payload = _resolve_credentials_payload()
    if not payload:
        raise GooglePlayBillingError("Google Play credentials are not configured")

    try:
        credentials = service_account.Credentials.from_service_account_info(
            payload,
            scopes=[_ANDROID_PUBLISHER_SCOPE],
        )
    except Exception as exc:
        raise GooglePlayBillingError("Invalid Google Play service account credentials") from exc

    return AuthorizedSession(credentials)


def _validate_package_name(package_name: Optional[str]) -> str:
    provided = (package_name or "").strip()
    configured = GOOGLE_PLAY_PACKAGE_NAME.strip()

    if configured and provided and provided != configured:
        raise GooglePlayBillingError("Package name mismatch with server configuration")
    if configured:
        return configured
    if provided:
        return provided
    raise GooglePlayBillingError("Package name is required")


def _product_allowed(product_id: Optional[str]) -> bool:
    return bool(product_id and product_id in GOOGLE_PLAY_PRO_PRODUCT_IDS)


def _require_pro_product_ids() -> None:
    if not GOOGLE_PLAY_PRO_PRODUCT_IDS:
        raise GooglePlayBillingError(
            "Google Play Premium product IDs are not configured"
        )


def verify_play_subscription(*, purchase_token: str, package_name: Optional[str] = None) -> dict[str, Any]:
    token = (purchase_token or "").strip()
    if not token:
        raise GooglePlayBillingError("purchase_token is required")

    _require_pro_product_ids()
    resolved_package = _validate_package_name(package_name)
    session = _get_authorized_session()
    url = _SUBSCRIPTION_V2_URL.format(package_name=resolved_package, purchase_token=token)

    response = session.get(url, timeout=25)
    if response.status_code == 404:
        return {
            "ok": False,
            "is_pro": False,
            "reason": "not_found",
            "status_code": 404,
        }
    if response.status_code >= 400:
        return {
            "ok": False,
            "is_pro": False,
            "reason": "api_error",
            "status_code": response.status_code,
            "error": response.text[:400],
        }

    payload = response.json() if response.content else {}
    state = str(payload.get("subscriptionState") or "")
    active_states = {
        "SUBSCRIPTION_STATE_ACTIVE",
        "SUBSCRIPTION_STATE_IN_GRACE_PERIOD",
    }

    line_items = payload.get("lineItems") or []
    product_id = ""
    expiry_time = None
    if isinstance(line_items, list) and line_items:
        first = line_items[0] if isinstance(line_items[0], dict) else {}
        product_id = str(first.get("productId") or "")
        expiry_time = first.get("expiryTime")

    product_allowed = _product_allowed(product_id)
    is_active = state in active_states and product_allowed

    return {
        "ok": True,
        "is_pro": is_active,
        "plan": PRO_PLAN if is_active else "FREE",
        "subscription_state": state,
        "package_name": resolved_package,
        "product_id": product_id or None,
        "expiry_time": expiry_time,
        "product_allowed": product_allowed,
        "raw": payload,
    }


def verify_play_product(*, purchase_token: str, product_id: str, package_name: Optional[str] = None) -> dict[str, Any]:
    token = (purchase_token or "").strip()
    product = (product_id or "").strip()
    if not token:
        raise GooglePlayBillingError("purchase_token is required")
    if not product:
        raise GooglePlayBillingError("product_id is required")

    _require_pro_product_ids()
    resolved_package = _validate_package_name(package_name)
    session = _get_authorized_session()
    url = _PRODUCT_URL.format(package_name=resolved_package, product_id=product, purchase_token=token)

    response = session.get(url, timeout=25)
    if response.status_code == 404:
        return {
            "ok": False,
            "is_pro": False,
            "reason": "not_found",
            "status_code": 404,
        }
    if response.status_code >= 400:
        return {
            "ok": False,
            "is_pro": False,
            "reason": "api_error",
            "status_code": response.status_code,
            "error": response.text[:400],
        }

    payload = response.json() if response.content else {}
    purchase_state = int(payload.get("purchaseState", -1))
    is_active = purchase_state == 0 and _product_allowed(product)

    return {
        "ok": True,
        "is_pro": is_active,
        "plan": PRO_PLAN if is_active else "FREE",
        "package_name": resolved_package,
        "product_id": product,
        "purchase_state": purchase_state,
        "acknowledgement_state": payload.get("acknowledgementState"),
        "consumption_state": payload.get("consumptionState"),
        "product_allowed": _product_allowed(product),
        "raw": payload,
    }
