import os
from datetime import UTC, datetime
from typing import Any

from app.models.db_models import User

FREE_PLAN = "FREE"
PRO_PLAN = "PRO"
UNLIMITED_SENTINEL = -1
DEFAULT_FREE_LIMIT = int(os.getenv("AI_FREE_REQUEST_LIMIT", "25"))


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _start_of_next_month(now: datetime) -> datetime:
    if now.month == 12:
        return datetime(now.year + 1, 1, 1, tzinfo=UTC)
    return datetime(now.year, now.month + 1, 1, tzinfo=UTC)


def _as_utc(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=UTC)
    return timestamp.astimezone(UTC)


def _normalize_plan(plan: str | None) -> str:
    normalized = (plan or FREE_PLAN).strip().upper()
    return PRO_PLAN if normalized == PRO_PLAN else FREE_PLAN


def has_premium_access(user: User) -> bool:
    return _normalize_plan(getattr(user, "subscription_plan", None)) == PRO_PLAN


def ensure_usage_window(user: User, now: datetime | None = None) -> bool:
    now = now or _utc_now()
    changed = False

    if user.ai_requests_limit is None:
        user.ai_requests_limit = DEFAULT_FREE_LIMIT
        changed = True
    if user.ai_requests_used is None:
        user.ai_requests_used = 0
        changed = True

    normalized_plan = _normalize_plan(getattr(user, "subscription_plan", FREE_PLAN))
    if user.subscription_plan != normalized_plan:
        user.subscription_plan = normalized_plan
        changed = True

    expected_limit = UNLIMITED_SENTINEL if has_premium_access(user) else DEFAULT_FREE_LIMIT
    if user.ai_requests_limit != expected_limit:
        user.ai_requests_limit = expected_limit
        changed = True

    if user.ai_usage_reset_at is None:
        user.ai_usage_reset_at = _start_of_next_month(now)
        changed = True
    else:
        reset_at = _as_utc(user.ai_usage_reset_at)
        if reset_at != user.ai_usage_reset_at:
            user.ai_usage_reset_at = reset_at
            changed = True
        if now >= reset_at:
            user.ai_requests_used = 0
            user.ai_usage_reset_at = _start_of_next_month(now)
            changed = True

    return changed


def usage_snapshot(user: User, now: datetime | None = None) -> dict[str, Any]:
    ensure_usage_window(user, now=now)
    plan = _normalize_plan(user.subscription_plan)
    limit = int(user.ai_requests_limit if user.ai_requests_limit is not None else DEFAULT_FREE_LIMIT)
    used = int(user.ai_requests_used or 0)
    unlimited = has_premium_access(user)
    remaining = None if unlimited else max(0, limit - used)

    return {
        "subscription_plan": plan,
        "ai_requests_used": used,
        "ai_requests_limit": limit,
        "ai_requests_remaining": remaining,
        "ai_usage_reset_at": user.ai_usage_reset_at.isoformat() if user.ai_usage_reset_at else None,
        "is_unlimited": unlimited,
    }


def profile_badge_snapshot(user: User, now: datetime | None = None) -> dict[str, Any]:
    usage = usage_snapshot(user, now=now)
    is_premium = usage["subscription_plan"] == PRO_PLAN

    return {
        "has_badge": True,
        "badge_key": "leaf",
        "badge_variant": "gold" if is_premium else "green",
        "badge_label": "FarmConnect Premium" if is_premium else "FarmConnect",
        "is_premium": is_premium,
        "subscription_plan": usage["subscription_plan"],
    }


def can_consume_request(user: User, now: datetime | None = None) -> bool:
    usage = usage_snapshot(user, now=now)
    if usage["is_unlimited"]:
        return True
    return int(usage["ai_requests_used"]) < int(usage["ai_requests_limit"])


def consume_request(user: User, now: datetime | None = None) -> dict[str, Any]:
    now = now or _utc_now()
    ensure_usage_window(user, now=now)
    usage = usage_snapshot(user, now=now)
    if usage["is_unlimited"]:
        return usage
    if int(usage["ai_requests_used"]) >= int(usage["ai_requests_limit"]):
        return usage

    user.ai_requests_used = int(user.ai_requests_used or 0) + 1
    return usage_snapshot(user, now=now)
