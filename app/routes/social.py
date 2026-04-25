import os
import shutil
import time
import uuid
import math
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
import requests

POST_TTL_MS = 30 * 24 * 60 * 60 * 1000  # 30 days in milliseconds
_REVERSE_GEOCODE_CACHE: dict[str, tuple[float, Optional[str]]] = {}
_REVERSE_GEOCODE_TTL_S = 24 * 60 * 60
_NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
_NOMINATIM_HEADERS = {
    "User-Agent": "FarmSenseSocial/1.0 (support@farmsense.app)",
    "Accept-Language": "en",
}

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.database import SessionLocal
from app.dependencies import get_current_user, get_db
from app.models.db_models import User
from app.models.social_models import (
    SocialComment,
    SocialConversation,
    SocialLike,
    SocialMessage,
    SocialPost,
    SocialProfile,
)
from app.services.firebase import send_message_notification, send_social_activity_notification
from app.services.social_realtime import social_connection_manager

router = APIRouter(prefix="/social", tags=["social"])
logger = logging.getLogger("crop_backend.social")


# ─── Pydantic schemas ─────────────────────────────────────────────────────────

class PostCreate(BaseModel):
    content: str
    image_url: Optional[str] = None
    media_type: Optional[str] = None  # "image" or "video"
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_global: bool = False


class PostOut(BaseModel):
    id: int
    user_id: str
    user_name: Optional[str] = None
    content: Optional[str] = None
    image_url: Optional[str] = None
    media_type: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_global: bool = False
    location_name: Optional[str] = None
    created_at: int
    like_count: int = 0
    comment_count: int = 0
    liked_by_me: bool = False


class GeoFeedItemOut(BaseModel):
    post: PostOut
    distance_km: float
    proximity_text: Optional[str] = None


class CommentCreate(BaseModel):
    content: str


class CommentOut(BaseModel):
    id: int
    post_id: int
    user_id: str
    user_name: Optional[str] = None
    content: Optional[str] = None
    created_at: int


class LikeOut(BaseModel):
    liked: bool
    like_count: int


class ConversationCreate(BaseModel):
    other_user_id: str
    other_user_name: str


class ConversationOut(BaseModel):
    id: int
    other_user_id: str
    other_user_name: Optional[str] = None
    last_message: Optional[str] = None
    updated_at: int
    unread_count: int = 0
    other_user_online: bool = False
    other_user_last_seen: Optional[str] = None


class MessageCreate(BaseModel):
    content: str


class MessageOut(BaseModel):
    id: int
    conversation_id: int
    sender_id: str
    sender_name: Optional[str] = None
    content: Optional[str] = None
    created_at: int
    is_delivered: bool = False
    delivered_at: Optional[int] = None
    is_read: bool = False
    seen_at: Optional[int] = None


class PresenceOut(BaseModel):
    user_id: str
    is_online: bool = False
    last_seen: Optional[str] = None


class SeenUpdateOut(BaseModel):
    conversation_id: int
    seen_count: int = 0
    message_ids: List[int] = []


class NotificationOut(BaseModel):
    type: str
    actor_id: str
    actor_name: Optional[str] = None
    post_id: int
    post_preview: Optional[str] = None
    content_preview: Optional[str] = None
    created_at: int


class ProfileUpdate(BaseModel):
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    bio: Optional[str] = None
    location: Optional[str] = None
    crops: Optional[str] = None
    farm_type: Optional[str] = None
    soil_type: Optional[str] = None
    irrigation_type: Optional[str] = None
    experience_level: Optional[str] = None
    planting_months: Optional[str] = None
    goals: Optional[str] = None


class ProfileOut(BaseModel):
    user_id: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    bio: Optional[str] = None
    location: Optional[str] = None
    crops: Optional[str] = None
    farm_type: Optional[str] = None
    soil_type: Optional[str] = None
    irrigation_type: Optional[str] = None
    experience_level: Optional[str] = None
    planting_months: Optional[str] = None
    goals: Optional[str] = None
    post_count: int = 0
    message_count: int = 0


def _build_profile_out_for_user(db: Session, target_user_id: str) -> dict:
    user = db.query(User).filter(User.email == target_user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    profile = db.query(SocialProfile).filter(SocialProfile.user_id == target_user_id).first()
    return {
        "user_id": target_user_id,
        "display_name": profile.display_name if profile and profile.display_name else _display(user),
        "avatar_url": profile.avatar_url if profile else None,
        "bio": profile.bio if profile else None,
        "location": profile.location if profile else None,
        "crops": profile.crops if profile else None,
        "farm_type": profile.farm_type if profile else None,
        "soil_type": profile.soil_type if profile else None,
        "irrigation_type": profile.irrigation_type if profile else None,
        "experience_level": profile.experience_level if profile else None,
        "planting_months": profile.planting_months if profile else None,
        "goals": profile.goals if profile else None,
        "post_count": db.query(SocialPost).filter(SocialPost.user_id == target_user_id).count(),
        "message_count": db.query(SocialMessage).filter(SocialMessage.sender_id == target_user_id).count(),
    }


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _now_ms() -> int:
    return int(time.time() * 1000)


def _display(user: User) -> str:
    return user.name or user.email.split("@")[0]


def _display_for_user_id(db: Session, user_id: str) -> str:
    profile = db.query(SocialProfile).filter(SocialProfile.user_id == user_id).first()
    if profile and profile.display_name:
        return profile.display_name

    user = db.query(User).filter(User.email == user_id).first()
    if user:
        return _display(user)
    return user_id.split("@")[0]


def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_radius_km = 6371.0
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return earth_radius_km * c


def _infer_location_name(lat: Optional[float], lon: Optional[float]) -> Optional[str]:
    if not _has_valid_coords(lat, lon):
        return None

    cache_key = f"{round(lat, 4):.4f},{round(lon, 4):.4f}"
    cached = _REVERSE_GEOCODE_CACHE.get(cache_key)
    now = time.time()
    if cached and now - cached[0] < _REVERSE_GEOCODE_TTL_S:
        return cached[1]

    label: Optional[str] = None
    try:
        response = requests.get(
            _NOMINATIM_URL,
            params={
                "format": "jsonv2",
                "lat": lat,
                "lon": lon,
                "zoom": 12,
                "addressdetails": 1,
            },
            headers=_NOMINATIM_HEADERS,
            timeout=3,
        )
        response.raise_for_status()
        payload = response.json() if response.content else {}
        address = payload.get("address", {}) if isinstance(payload, dict) else {}

        city = (
            address.get("city")
            or address.get("town")
            or address.get("village")
            or address.get("municipality")
            or address.get("county")
            or address.get("state")
        )
        country = address.get("country")

        if city and country:
            label = f"{city}, {country}"
        elif country:
            label = str(country)
        elif city:
            label = str(city)
    except Exception:
        label = None

    _REVERSE_GEOCODE_CACHE[cache_key] = (now, label)
    return label


def _has_valid_coords(lat: Optional[float], lon: Optional[float]) -> bool:
    return (
        lat is not None
        and lon is not None
        and -90.0 <= lat <= 90.0
        and -180.0 <= lon <= 180.0
    )


def _resolve_user_coords(
    db: Session,
    user_id: str,
    preferred_lat: Optional[float],
    preferred_lon: Optional[float],
) -> Tuple[Optional[float], Optional[float]]:
    if _has_valid_coords(preferred_lat, preferred_lon):
        return preferred_lat, preferred_lon

    latest_with_coords = (
        db.query(SocialPost)
        .filter(
            SocialPost.user_id == user_id,
            SocialPost.latitude.isnot(None),
            SocialPost.longitude.isnot(None),
        )
        .order_by(SocialPost.created_at.desc())
        .first()
    )
    if latest_with_coords and _has_valid_coords(latest_with_coords.latitude, latest_with_coords.longitude):
        return latest_with_coords.latitude, latest_with_coords.longitude

    return None, None


def _rank_posts_by_location(
    posts: List[SocialPost],
    me: str,
    user_lat: Optional[float],
    user_lon: Optional[float],
    radius_km: float,
) -> List[dict]:
    if not _has_valid_coords(user_lat, user_lon):
        return [
            {
                "post": _post_out(post, me),
                "distance_km": None,
                "proximity_text": _infer_location_name(post.latitude, post.longitude),
            }
            for post in posts
        ]

    nearby: List[dict] = []
    farther: List[dict] = []
    for post in posts:
        if not _has_valid_coords(post.latitude, post.longitude):
            farther.append(
                {
                    "post": _post_out(post, me),
                    "distance_km": None,
                    "proximity_text": _infer_location_name(post.latitude, post.longitude),
                }
            )
            continue

        distance_km = calculate_distance(user_lat, user_lon, post.latitude, post.longitude)
        location_name = _infer_location_name(post.latitude, post.longitude)
        item = {
            "post": _post_out(post, me),
            "distance_km": round(distance_km, 2),
            "proximity_text": location_name if distance_km <= 1.0 and location_name else None,
        }
        if distance_km <= radius_km:
            nearby.append(item)
        else:
            farther.append(item)

    # Close-by content first; ties are resolved by recency.
    nearby.sort(key=lambda item: (item["distance_km"], -item["post"]["created_at"]))
    farther.sort(key=lambda item: item["post"]["created_at"], reverse=True)
    return nearby + farther


def _post_out(post: SocialPost, me: str) -> dict:
    return {
        "id": post.id,
        "user_id": post.user_id,
        "user_name": post.user_name,
        "content": post.content,
        "image_url": post.image_url,
        "media_type": post.media_type,
        "latitude": post.latitude,
        "longitude": post.longitude,
        "is_global": bool(post.is_global),
        "location_name": _infer_location_name(post.latitude, post.longitude),
        "created_at": post.created_at,
        "like_count": len(post.likes),
        "comment_count": len(post.comments),
        "liked_by_me": any(lk.user_id == me for lk in post.likes),
    }


def _comment_out(c: SocialComment) -> dict:
    return {
        "id": c.id,
        "post_id": c.post_id,
        "user_id": c.user_id,
        "user_name": c.user_name,
        "content": c.content,
        "created_at": c.created_at,
    }


def _message_out(m: SocialMessage) -> dict:
    return {
        "id": m.id,
        "conversation_id": m.conversation_id,
        "sender_id": m.sender_id,
        "sender_name": m.sender_name,
        "content": m.content,
        "created_at": m.created_at,
        "is_delivered": bool(getattr(m, "is_delivered", False)),
        "delivered_at": getattr(m, "delivered_at", None),
        "is_read": m.is_read,
        "seen_at": getattr(m, "seen_at", None),
    }


def _trim_preview(value: Optional[str], limit: int = 96) -> Optional[str]:
    if not value:
        return None
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _notification_out(
    item_type: str,
    actor_id: str,
    actor_name: str,
    post_id: int,
    post_preview: Optional[str],
    content_preview: Optional[str],
    created_at: int,
) -> dict:
    return {
        "type": item_type,
        "actor_id": actor_id,
        "actor_name": actor_name,
        "post_id": post_id,
        "post_preview": _trim_preview(post_preview),
        "content_preview": _trim_preview(content_preview),
        "created_at": created_at,
    }


def _assert_participant(conv: SocialConversation, me: str) -> None:
    if conv.owner_id != me and conv.other_user_id != me:
        raise HTTPException(status_code=403, detail="Not a participant in this conversation")


def _last_seen_iso(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc).isoformat()
    return value.astimezone(timezone.utc).isoformat()


def _presence_out(user: Optional[User], fallback_user_id: str) -> dict:
    return {
        "user_id": fallback_user_id,
        "is_online": bool(user.is_online) if user else False,
        "last_seen": _last_seen_iso(user.last_seen) if user else None,
    }


def _conversation_peer(conv: SocialConversation, me: str) -> str:
    return conv.other_user_id if conv.owner_id == me else conv.owner_id


def _conversation_partner_ids(db: Session, me: str) -> List[str]:
    partners: set[str] = set()
    conversations = (
        db.query(SocialConversation)
        .filter(or_(SocialConversation.owner_id == me, SocialConversation.other_user_id == me))
        .all()
    )
    for conv in conversations:
        partners.add(_conversation_peer(conv, me))
    partners.discard(me)
    return sorted(partners)


def _compute_unread_count(db: Session, conv_id: int, me: str) -> int:
    return (
        db.query(SocialMessage)
        .filter(
            SocialMessage.conversation_id == conv_id,
            SocialMessage.sender_id != me,
            SocialMessage.is_read.is_(False),
        )
        .count()
    )


def _set_user_presence(db: Session, user: User, is_online: bool) -> None:
    user.is_online = is_online
    if not is_online:
        user.last_seen = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()


def _mark_messages_delivered(
    db: Session,
    me: str,
    conversation_id: Optional[int] = None,
) -> List[Tuple[str, int, int]]:
    query = (
        db.query(SocialMessage)
        .join(SocialConversation, SocialConversation.id == SocialMessage.conversation_id)
        .filter(
            or_(SocialConversation.owner_id == me, SocialConversation.other_user_id == me),
            SocialMessage.sender_id != me,
            SocialMessage.is_delivered.is_(False),
        )
    )
    if conversation_id is not None:
        query = query.filter(SocialMessage.conversation_id == conversation_id)

    messages = query.all()
    if not messages:
        return []

    delivered_at = _now_ms()
    # Snapshot scalar fields before commit so callers can safely use results
    # after the SQLAlchemy session is closed.
    delivery_events = [
        (str(message.sender_id), int(message.conversation_id), int(message.id))
        for message in messages
    ]
    for message in messages:
        message.is_delivered = True
        message.delivered_at = delivered_at
    db.commit()
    return delivery_events


def _mark_messages_seen(db: Session, conv: SocialConversation, me: str) -> List[SocialMessage]:
    messages = (
        db.query(SocialMessage)
        .filter(
            SocialMessage.conversation_id == conv.id,
            SocialMessage.sender_id != me,
            SocialMessage.is_read.is_(False),
        )
        .all()
    )
    if not messages:
        return []

    seen_at = _now_ms()
    for message in messages:
        if not message.is_delivered:
            message.is_delivered = True
            message.delivered_at = seen_at
        message.is_read = True
        message.seen_at = seen_at
    db.commit()
    return messages


def _conversation_out(db: Session, conv: SocialConversation, me: str) -> dict:
    other_user_id = _conversation_peer(conv, me)
    other_profile = db.query(SocialProfile).filter(SocialProfile.user_id == other_user_id).first()
    other_user = db.query(User).filter(User.email == other_user_id).first()
    if other_profile and other_profile.display_name:
        other_name = other_profile.display_name
    elif conv.owner_id == me and conv.other_user_name:
        other_name = conv.other_user_name
    else:
        other_name = _display_for_user_id(db, other_user_id)

    return {
        "id": conv.id,
        "other_user_id": other_user_id,
        "other_user_name": other_name,
        "last_message": conv.last_message,
        "updated_at": conv.updated_at,
        "unread_count": _compute_unread_count(db, conv.id, me),
        "other_user_online": bool(other_user.is_online) if other_user else False,
        "other_user_last_seen": _last_seen_iso(other_user.last_seen) if other_user else None,
    }


async def _emit_presence_event(user_id: str, is_online: bool, last_seen: Optional[str]) -> None:
    db = SessionLocal()
    try:
        partner_ids = _conversation_partner_ids(db, user_id)
    finally:
        db.close()

    event_type = "online" if is_online else "offline"
    await social_connection_manager.send_to_many(
        partner_ids,
        {
            "type": event_type,
            "user_id": user_id,
            "last_seen": last_seen,
        },
    )


async def _emit_feed_event(event_type: str, payload: dict) -> None:
    await social_connection_manager.send_to_all(
        {
            "type": event_type,
            **payload,
        }
    )


async def _send_presence_snapshot(websocket: WebSocket, user_id: str) -> None:
    db = SessionLocal()
    try:
        partner_ids = _conversation_partner_ids(db, user_id)
        if not partner_ids:
            return

        users = (
            db.query(User)
            .filter(User.email.in_(partner_ids))
            .all()
        )
        users_by_email = {user.email: user for user in users}
    finally:
        db.close()

    for partner_id in partner_ids:
        partner = users_by_email.get(partner_id)
        await websocket.send_json(
            {
                "type": "online" if partner and partner.is_online else "offline",
                "user_id": partner_id,
                "last_seen": _last_seen_iso(partner.last_seen) if partner else None,
            }
        )


async def _emit_delivery_events(recipient_id: str, delivery_events: List[Tuple[str, int, int]]) -> None:
    grouped: Dict[Tuple[str, int], List[int]] = defaultdict(list)
    for sender_id, conversation_id, message_id in delivery_events:
        grouped[(sender_id, conversation_id)].append(message_id)

    for (sender_id, conversation_id), message_ids in grouped.items():
        await social_connection_manager.send_to_user(
            sender_id,
            {
                "type": "delivered",
                "user_id": recipient_id,
                "conversation_id": conversation_id,
                "message_ids": message_ids,
            },
        )


def _authenticate_websocket_token(token: str) -> User:
    payload = decode_access_token(token)
    user_id = payload.get("sub")
    if user_id is None:
        raise ValueError("Invalid websocket token")

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == int(user_id)).first()
        if user is None:
            raise ValueError("User not found")
        db.expunge(user)
        return user
    finally:
        db.close()


# ─── Feed ─────────────────────────────────────────────────────────────────────

@router.get("/posts", response_model=List[PostOut])
def get_posts(
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    since_ms: Optional[int] = Query(None, ge=0),
    user_lat: Optional[float] = Query(None, ge=-90, le=90),
    user_lon: Optional[float] = Query(None, ge=-180, le=180),
    radius_km: float = Query(50.0, gt=0.0, le=1000.0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cutoff = int(time.time() * 1000) - POST_TTL_MS
    me = current_user.email
    resolved_lat, resolved_lon = _resolve_user_coords(db, me, user_lat, user_lon)

    query = db.query(SocialPost).filter(SocialPost.created_at >= cutoff)
    if since_ms is not None:
        query = query.filter(SocialPost.created_at > since_ms)

    posts = query.order_by(SocialPost.created_at.desc()).limit(1000).all()

    ranked = _rank_posts_by_location(posts, me, resolved_lat, resolved_lon, radius_km)
    paged = ranked[offset: offset + limit]
    return [item["post"] for item in paged]


@router.get("/geo-feed", response_model=List[GeoFeedItemOut])
def get_geo_feed(
    since_ms: Optional[int] = Query(None, ge=0),
    user_lat: Optional[float] = Query(None, ge=-90, le=90),
    user_lon: Optional[float] = Query(None, ge=-180, le=180),
    radius_km: float = Query(50.0, gt=0.0, le=1000.0),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cutoff = int(time.time() * 1000) - POST_TTL_MS
    query = (
        db.query(SocialPost)
        .filter(SocialPost.created_at >= cutoff)
        .filter(SocialPost.latitude.isnot(None), SocialPost.longitude.isnot(None))
    )
    if since_ms is not None:
        query = query.filter(SocialPost.created_at > since_ms)

    posts = query.order_by(SocialPost.created_at.desc()).limit(1000).all()

    me = current_user.email
    resolved_lat, resolved_lon = _resolve_user_coords(db, me, user_lat, user_lon)
    ranked = _rank_posts_by_location(posts, me, resolved_lat, resolved_lon, radius_km)

    # Geo feed must always include a numeric distance.
    geocoded = [item for item in ranked if item["distance_km"] is not None]
    return geocoded[offset: offset + limit]


@router.get("/global-feed", response_model=List[PostOut])
def get_global_feed(
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    since_ms: Optional[int] = Query(None, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cutoff = int(time.time() * 1000) - POST_TTL_MS
    me = current_user.email
    query = (
        db.query(SocialPost)
        .filter(SocialPost.created_at >= cutoff)
        .filter(SocialPost.is_global.is_(True))
    )
    if since_ms is not None:
        query = query.filter(SocialPost.created_at > since_ms)

    posts = query.order_by(SocialPost.created_at.desc()).offset(offset).limit(limit).all()
    return [_post_out(post, me) for post in posts]


@router.post("/posts", response_model=PostOut, status_code=201)
async def create_post(
    body: PostCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    me = current_user.email
    if (body.latitude is None) != (body.longitude is None):
        raise HTTPException(status_code=400, detail="Provide both latitude and longitude, or neither")
    if not _has_valid_coords(body.latitude, body.longitude) and body.latitude is not None:
        raise HTTPException(status_code=400, detail="Invalid latitude/longitude range")

    # Persist only the location provided for this post; never inherit stale past coordinates.
    lat, lon = body.latitude, body.longitude
    post = SocialPost(
        user_id=me,
        user_name=_display(current_user),
        content=body.content,
        image_url=body.image_url,
        media_type=body.media_type,
        latitude=lat,
        longitude=lon,
        is_global=body.is_global,
        created_at=_now_ms(),
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    post_payload = _post_out(post, me)
    await _emit_feed_event(
        "post_created",
        {
            "post": post_payload,
        },
    )
    return post_payload


def _delete_post_media_if_local(image_url: Optional[str]) -> None:
    if not image_url or not image_url.startswith("/uploads/social/"):
        return

    filename = image_url.split("/uploads/social/", 1)[-1].strip()
    if not filename:
        return

    upload_root = os.path.abspath("uploads/social")
    media_path = os.path.abspath(os.path.join(upload_root, filename))
    if not media_path.startswith(upload_root):
        return

    if os.path.exists(media_path):
        try:
            os.remove(media_path)
        except Exception:
            pass


@router.delete("/posts/{post_id}", status_code=204)
async def delete_post(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = db.query(SocialPost).filter(SocialPost.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.user_id != current_user.email:
        raise HTTPException(status_code=403, detail="Not your post")

    db.query(SocialComment).filter(SocialComment.post_id == post_id).delete(synchronize_session=False)
    db.query(SocialLike).filter(SocialLike.post_id == post_id).delete(synchronize_session=False)
    _delete_post_media_if_local(post.image_url)
    db.delete(post)
    db.commit()
    await _emit_feed_event(
        "post_deleted",
        {
            "post_id": int(post_id),
            "user_id": current_user.email,
        },
    )


# ─── Media upload ─────────────────────────────────────────────────────────────

_UPLOAD_DIR = "uploads/social"
_ALLOWED_IMAGE = {"image/jpeg", "image/png", "image/gif", "image/webp"}
_ALLOWED_VIDEO = {"video/mp4", "video/quicktime", "video/webm", "video/x-msvideo"}
_MAX_VIDEO_SECONDS = 60


def _media_ext(ct: str) -> str:
    return {
        "image/jpeg": ".jpg", "image/png": ".png",
        "image/gif": ".gif", "image/webp": ".webp",
        "video/mp4": ".mp4", "video/quicktime": ".mov",
        "video/webm": ".webm", "video/x-msvideo": ".avi",
    }.get(ct, "")


def _video_duration(path: str, ct: str) -> Optional[float]:
    try:
        if ct in ("video/mp4", "video/quicktime"):
            from mutagen.mp4 import MP4
            return MP4(path).info.length
    except Exception:
        pass
    try:
        import subprocess
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0 and r.stdout.strip():
            return float(r.stdout.strip())
    except Exception:
        pass
    return None


@router.post("/media/upload")
def upload_media(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    ct = file.content_type or ""
    is_image = ct in _ALLOWED_IMAGE
    is_video = ct in _ALLOWED_VIDEO
    if not is_image and not is_video:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Allowed: JPEG, PNG, GIF, WEBP, MP4, MOV, WEBM",
        )

    import tempfile

    os.makedirs(_UPLOAD_DIR, exist_ok=True)
    filename = uuid.uuid4().hex + _media_ext(ct)
    dest_path = os.path.join(_UPLOAD_DIR, filename)

    if is_video:
        ext = _media_ext(ct)
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=ext)
        try:
            with os.fdopen(tmp_fd, "wb") as tmp_file:
                shutil.copyfileobj(file.file, tmp_file)
            duration = _video_duration(tmp_path, ct)
            if duration is not None and duration > _MAX_VIDEO_SECONDS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Video exceeds {_MAX_VIDEO_SECONDS}s limit ({int(duration)}s).",
                )
            os.replace(tmp_path, dest_path)
        except HTTPException:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
    else:
        with open(dest_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

    return {
        "url": f"/uploads/social/{filename}",
        "media_type": "video" if is_video else "image",
    }


# ─── Likes ────────────────────────────────────────────────────────────────────

@router.post("/posts/{post_id}/like", response_model=LikeOut)
def toggle_like(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = db.query(SocialPost).filter(SocialPost.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    me = current_user.email
    existing = db.query(SocialLike).filter(
        SocialLike.post_id == post_id, SocialLike.user_id == me
    ).first()

    if existing:
        db.delete(existing)
        db.commit()
        liked = False
    else:
        like_created_at = _now_ms()
        db.add(SocialLike(post_id=post_id, user_id=me, created_at=like_created_at))
        db.commit()
        liked = True
        if post.user_id != me:
            try:
                send_social_activity_notification(
                    db=db,
                    recipient_email=post.user_id,
                    sender_id=me,
                    sender_name=_display(current_user),
                    activity_type="like",
                    post_id=post.id,
                    post_preview=post.content,
                    activity_preview="liked your post",
                )
            except Exception:
                logger.exception("Failed to send like notification for post %s", post_id)

    db.refresh(post)
    return {"liked": liked, "like_count": len(post.likes)}


# ─── Comments ─────────────────────────────────────────────────────────────────

@router.get("/posts/{post_id}/comments", response_model=List[CommentOut])
def get_comments(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    comments = (
        db.query(SocialComment)
        .filter(SocialComment.post_id == post_id)
        .order_by(SocialComment.created_at)
        .limit(100)
        .all()
    )
    return [_comment_out(c) for c in comments]


@router.post("/posts/{post_id}/comments", response_model=CommentOut, status_code=201)
def add_comment(
    post_id: int,
    body: CommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = db.query(SocialPost).filter(SocialPost.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    me = current_user.email
    comment = SocialComment(
        post_id=post_id,
        user_id=me,
        user_name=_display(current_user),
        content=body.content,
        created_at=_now_ms(),
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    if post.user_id != me:
        try:
            send_social_activity_notification(
                db=db,
                recipient_email=post.user_id,
                sender_id=me,
                sender_name=_display(current_user),
                activity_type="comment",
                post_id=post.id,
                post_preview=post.content,
                activity_preview=comment.content,
            )
        except Exception:
            logger.exception("Failed to send comment notification for post %s", post_id)
    return _comment_out(comment)


@router.get("/notifications", response_model=List[NotificationOut])
def get_notifications(
    since_ms: Optional[int] = Query(None, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    me = current_user.email
    my_post_ids = [
        post_id
        for (post_id,) in db.query(SocialPost.id).filter(SocialPost.user_id == me).all()
    ]
    if not my_post_ids:
        return []

    like_query = (
        db.query(SocialLike, SocialPost)
        .join(SocialPost, SocialLike.post_id == SocialPost.id)
        .filter(SocialLike.post_id.in_(my_post_ids), SocialLike.user_id != me)
        .order_by(SocialLike.created_at.desc())
    )
    if since_ms is not None:
        like_query = like_query.filter(SocialLike.created_at > since_ms)

    comment_query = (
        db.query(SocialComment, SocialPost)
        .join(SocialPost, SocialComment.post_id == SocialPost.id)
        .filter(SocialComment.post_id.in_(my_post_ids), SocialComment.user_id != me)
        .order_by(SocialComment.created_at.desc())
    )
    if since_ms is not None:
        comment_query = comment_query.filter(SocialComment.created_at > since_ms)

    notifications: List[dict] = []

    for like, post in like_query.limit(limit).all():
        notifications.append(
            _notification_out(
                "like",
                like.user_id,
                _display_for_user_id(db, like.user_id),
                post.id,
                post.content,
                "liked your post",
                like.created_at,
            )
        )

    for comment, post in comment_query.limit(limit).all():
        notifications.append(
            _notification_out(
                "comment",
                comment.user_id,
                comment.user_name or _display_for_user_id(db, comment.user_id),
                post.id,
                post.content,
                comment.content,
                comment.created_at,
            )
        )

    notifications.sort(key=lambda item: item["created_at"], reverse=True)
    return notifications[:limit]


# ─── Conversations ────────────────────────────────────────────────────────────

@router.get("/conversations", response_model=List[ConversationOut])
def get_conversations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    me = current_user.email
    result = []

    for conv in (
        db.query(SocialConversation)
        .filter(or_(SocialConversation.owner_id == me, SocialConversation.other_user_id == me))
        .order_by(SocialConversation.updated_at.desc())
        .limit(100)
        .all()
    ):
        if me in (conv.hidden_by or "").split(","):
            continue
        result.append(_conversation_out(db, conv, me))

    result.sort(key=lambda x: x["updated_at"], reverse=True)
    return result


@router.post("/conversations", response_model=ConversationOut, status_code=201)
def create_conversation(
    body: ConversationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    me = current_user.email

    # Already exists from my side?
    existing = db.query(SocialConversation).filter(
        SocialConversation.owner_id == me,
        SocialConversation.other_user_id == body.other_user_id,
    ).first()
    if existing:
        return {
            "id": existing.id,
            "other_user_id": existing.other_user_id,
            "other_user_name": existing.other_user_name,
            "last_message": existing.last_message,
            "updated_at": existing.updated_at,
            "unread_count": existing.unread_count,
        }

    # Already exists from their side?
    reverse = db.query(SocialConversation).filter(
        SocialConversation.owner_id == body.other_user_id,
        SocialConversation.other_user_id == me,
    ).first()
    if reverse:
        return {
            "id": reverse.id,
            "other_user_id": reverse.owner_id,
            "other_user_name": reverse.owner_id.split("@")[0],
            "last_message": reverse.last_message,
            "updated_at": reverse.updated_at,
            "unread_count": 0,
        }

    conv = SocialConversation(
        owner_id=me,
        other_user_id=body.other_user_id,
        other_user_name=body.other_user_name,
        last_message=None,
        updated_at=_now_ms(),
        unread_count=0,
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return {
        "id": conv.id,
        "other_user_id": conv.other_user_id,
        "other_user_name": conv.other_user_name,
        "last_message": conv.last_message,
        "updated_at": conv.updated_at,
        "unread_count": conv.unread_count,
    }


# ─── Messages ─────────────────────────────────────────────────────────────────

@router.get("/conversations/{conv_id}/messages", response_model=List[MessageOut])
async def get_messages(
    conv_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conv = db.query(SocialConversation).filter(SocialConversation.id == conv_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    _assert_participant(conv, current_user.email)

    messages = (
        db.query(SocialMessage)
        .filter(SocialMessage.conversation_id == conv_id)
        .order_by(SocialMessage.created_at)
        .limit(200)
        .all()
    )
    me = current_user.email
    visible = [m for m in messages if me not in (m.deleted_by or "").split(",")]
    delivered_messages = _mark_messages_delivered(db, me, conversation_id=conv_id)
    if delivered_messages:
        await _emit_delivery_events(me, delivered_messages)
    return [_message_out(m) for m in visible]


@router.post("/conversations/{conv_id}/messages", response_model=MessageOut, status_code=201)
async def send_message(
    conv_id: int,
    body: MessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conv = db.query(SocialConversation).filter(SocialConversation.id == conv_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    _assert_participant(conv, current_user.email)

    me = current_user.email
    recipient_email = _conversation_peer(conv, me)
    created_at = _now_ms()
    msg = SocialMessage(
        conversation_id=conv_id,
        sender_id=me,
        sender_name=_display(current_user),
        content=body.content,
        created_at=created_at,
        is_delivered=False,
        delivered_at=None,
        is_read=False,
    )
    db.add(msg)

    conv.last_message = body.content
    conv.updated_at = created_at

    db.commit()
    db.refresh(msg)

    message_payload = _message_out(msg)
    delivered_realtime = await social_connection_manager.send_to_user(
        recipient_email,
        {
            "type": "message",
            "conversation_id": conv_id,
            "message": message_payload,
        },
    )

    if delivered_realtime:
        msg.is_delivered = True
        msg.delivered_at = created_at
        db.commit()
        db.refresh(msg)
        message_payload = _message_out(msg)
        await social_connection_manager.send_to_user(
            me,
            {
                "type": "delivered",
                "user_id": recipient_email,
                "conversation_id": conv_id,
                "message_ids": [int(msg.id)],
            },
        )
    else:
        try:
            send_message_notification(
                db=db,
                recipient_email=recipient_email,
                sender_id=me,
                sender_name=_display(current_user),
                conversation_id=conv_id,
                message_id=msg.id,
                message_text=body.content,
            )
        except Exception:
            logger.exception("Failed to send FCM notification for social message %s", msg.id)

    return message_payload


@router.post("/conversations/{conv_id}/seen", response_model=SeenUpdateOut)
async def mark_conversation_seen(
    conv_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conv = db.query(SocialConversation).filter(SocialConversation.id == conv_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    _assert_participant(conv, current_user.email)

    me = current_user.email
    seen_messages = _mark_messages_seen(db, conv, me)
    message_ids = [int(message.id) for message in seen_messages]
    if message_ids:
        await social_connection_manager.send_to_user(
            _conversation_peer(conv, me),
            {
                "type": "seen",
                "user_id": me,
                "conversation_id": conv_id,
                "message_ids": message_ids,
            },
        )
    return {
        "conversation_id": conv_id,
        "seen_count": len(message_ids),
        "message_ids": message_ids,
    }


@router.get("/presence/{target_user_id:path}", response_model=PresenceOut)
def get_presence(
    target_user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    del current_user
    normalized = (target_user_id or "").strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="target_user_id is required")

    target_user = db.query(User).filter(User.email == normalized).first()
    return _presence_out(target_user, normalized)


@router.websocket("/ws")
async def social_websocket(websocket: WebSocket, token: str = Query(...)):
    try:
        current_user = _authenticate_websocket_token(token)
    except Exception:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    me = current_user.email
    await social_connection_manager.connect(me, websocket)

    db = SessionLocal()
    try:
        db_user = db.query(User).filter(User.id == current_user.id).first()
        if db_user is not None:
            _set_user_presence(db, db_user, True)
        delivered_messages = _mark_messages_delivered(db, me)
        await websocket.send_json({"type": "connected", "user_id": me})
        await _send_presence_snapshot(websocket, me)
        await _emit_presence_event(me, True, _last_seen_iso(db_user.last_seen) if db_user else None)
    finally:
        db.close()

    if delivered_messages:
        await _emit_delivery_events(me, delivered_messages)

    try:
        while True:
            data = await websocket.receive_json()
            event = str(data.get("type") or "").strip().lower()

            if event == "typing":
                receiver_id = str(data.get("receiver_id") or "").strip()
                if receiver_id and receiver_id != me:
                    await social_connection_manager.send_to_user(
                        receiver_id,
                        {
                            "type": "typing",
                            "user_id": me,
                            "conversation_id": data.get("conversation_id"),
                        },
                    )
            elif event == "seen":
                conv_id = int(data.get("conversation_id") or 0)
                peer_id: Optional[str] = None
                message_ids: List[int] = []
                db = SessionLocal()
                try:
                    conv = db.query(SocialConversation).filter(SocialConversation.id == conv_id).first()
                    if conv is None:
                        continue
                    _assert_participant(conv, me)
                    peer_id = _conversation_peer(conv, me)
                    seen_messages = _mark_messages_seen(db, conv, me)
                    message_ids = [int(message.id) for message in seen_messages]
                finally:
                    db.close()

                if message_ids and peer_id:
                    await social_connection_manager.send_to_user(
                        peer_id,
                        {
                            "type": "seen",
                            "user_id": me,
                            "conversation_id": conv_id,
                            "message_ids": message_ids,
                        },
                    )
            elif event == "online":
                db = SessionLocal()
                try:
                    db_user = db.query(User).filter(User.id == current_user.id).first()
                    if db_user is not None:
                        _set_user_presence(db, db_user, True)
                        await _emit_presence_event(me, True, _last_seen_iso(db_user.last_seen))
                finally:
                    db.close()
            elif event == "offline":
                break
            elif event == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Social websocket error for %s", me)
    finally:
        await social_connection_manager.disconnect(me, websocket)
        db = SessionLocal()
        last_seen = None
        try:
            db_user = db.query(User).filter(User.id == current_user.id).first()
            if db_user is not None:
                _set_user_presence(db, db_user, False)
                last_seen = _last_seen_iso(db_user.last_seen)
        finally:
            db.close()
        await _emit_presence_event(me, False, last_seen)


@router.delete("/conversations/{conv_id}/messages/{msg_id}", status_code=204)
def delete_message(
    conv_id: int,
    msg_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conv = db.query(SocialConversation).filter(SocialConversation.id == conv_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    _assert_participant(conv, current_user.email)

    msg = db.query(SocialMessage).filter(
        SocialMessage.id == msg_id,
        SocialMessage.conversation_id == conv_id,
    ).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    # Soft-delete: mark deleted for this user only
    existing = msg.deleted_by or ""
    deleted_set = set(x for x in existing.split(",") if x)
    deleted_set.add(current_user.email)
    msg.deleted_by = ",".join(deleted_set)

    # Hard-delete only when both participants have deleted it
    participants = {conv.owner_id, conv.other_user_id}
    if participants.issubset(deleted_set):
        db.delete(msg)

    db.commit()


@router.delete("/conversations/{conv_id}", status_code=204)
def delete_conversation(
    conv_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conv = db.query(SocialConversation).filter(SocialConversation.id == conv_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    _assert_participant(conv, current_user.email)

    me = current_user.email
    existing = conv.hidden_by or ""
    hidden_set = set(x for x in existing.split(",") if x)
    hidden_set.add(me)
    conv.hidden_by = ",".join(hidden_set)

    # Hard-delete only when both participants have hidden the conversation
    participants = {conv.owner_id, conv.other_user_id}
    if participants.issubset(hidden_set):
        db.query(SocialMessage).filter(SocialMessage.conversation_id == conv_id).delete()
        db.delete(conv)

    db.commit()


# ─── Profile ──────────────────────────────────────────────────────────────────

@router.get("/profile/me", response_model=ProfileOut)
def get_my_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    me = current_user.email
    profile = db.query(SocialProfile).filter(SocialProfile.user_id == me).first()
    return {
        "user_id": me,
        "display_name": profile.display_name if profile else _display(current_user),
        "avatar_url": profile.avatar_url if profile else None,
        "bio": profile.bio if profile else None,
        "location": profile.location if profile else None,
        "crops": profile.crops if profile else None,
        "farm_type": profile.farm_type if profile else None,
        "soil_type": profile.soil_type if profile else None,
        "irrigation_type": profile.irrigation_type if profile else None,
        "experience_level": profile.experience_level if profile else None,
        "planting_months": profile.planting_months if profile else None,
        "goals": profile.goals if profile else None,
        "post_count": db.query(SocialPost).filter(SocialPost.user_id == me).count(),
        "message_count": db.query(SocialMessage).filter(SocialMessage.sender_id == me).count(),
    }


@router.put("/profile/me", response_model=ProfileOut)
def update_my_profile(
    body: ProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    me = current_user.email
    profile = db.query(SocialProfile).filter(SocialProfile.user_id == me).first()
    if not profile:
        profile = SocialProfile(user_id=me)
        db.add(profile)

    if body.display_name is not None:
        profile.display_name = body.display_name
    if body.avatar_url is not None:
        profile.avatar_url = body.avatar_url
    if body.bio is not None:
        profile.bio = body.bio
    if body.location is not None:
        profile.location = body.location
    if body.crops is not None:
        profile.crops = body.crops
    if body.farm_type is not None:
        profile.farm_type = body.farm_type
    if body.soil_type is not None:
        profile.soil_type = body.soil_type
    if body.irrigation_type is not None:
        profile.irrigation_type = body.irrigation_type
    if body.experience_level is not None:
        profile.experience_level = body.experience_level
    if body.planting_months is not None:
        profile.planting_months = body.planting_months
    if body.goals is not None:
        profile.goals = body.goals

    db.commit()
    db.refresh(profile)
    return {
        "user_id": me,
        "display_name": profile.display_name,
        "avatar_url": profile.avatar_url,
        "bio": profile.bio,
        "location": profile.location,
        "crops": profile.crops,
        "farm_type": profile.farm_type,
        "soil_type": profile.soil_type,
        "irrigation_type": profile.irrigation_type,
        "experience_level": profile.experience_level,
        "planting_months": profile.planting_months,
        "goals": profile.goals,
        "post_count": db.query(SocialPost).filter(SocialPost.user_id == me).count(),
        "message_count": db.query(SocialMessage).filter(SocialMessage.sender_id == me).count(),
    }


@router.get("/profile/{target_user_id:path}", response_model=ProfileOut)
def get_profile_by_path(
    target_user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    del current_user
    normalized = (target_user_id or "").strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="target_user_id is required")
    return _build_profile_out_for_user(db, normalized)


@router.get("/profile", response_model=ProfileOut)
def get_profile_by_query(
    target_user_id: str = Query(..., min_length=1, max_length=320),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    del current_user
    normalized = target_user_id.strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="target_user_id is required")
    return _build_profile_out_for_user(db, normalized)


# ─── User Search ──────────────────────────────────────────────────────────────

class UserSearchResult(BaseModel):
    user_id: str
    display_name: str
    avatar_url: Optional[str] = None


@router.get("/users/search", response_model=List[UserSearchResult])
def search_users(
    q: str = Query("", max_length=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Search users by display name or email, or return all users when query is blank."""
    normalized = (q or "").strip()

    if normalized:
        pattern = f"%{normalized}%"
        matched_by_email = (
            db.query(User)
            .filter(User.email.ilike(pattern))
            .limit(50)
            .all()
        )
        email_set = {u.email for u in matched_by_email}

        matched_by_name = (
            db.query(SocialProfile)
            .filter(SocialProfile.display_name.ilike(pattern))
            .limit(50)
            .all()
        )
        for p in matched_by_name:
            email_set.add(p.user_id)
    else:
        email_set = {
            user.email
            for user in db.query(User).order_by(User.email.asc()).limit(100).all()
            if user.email
        }

    # Remove the caller from results
    email_set.discard(current_user.email)

    # Build results
    results = []
    for email in list(email_set)[:100]:
        profile = db.query(SocialProfile).filter(SocialProfile.user_id == email).first()
        display_name = profile.display_name if (profile and profile.display_name) else email.split("@")[0]
        results.append(
            UserSearchResult(
                user_id=email,
                display_name=display_name,
                avatar_url=profile.avatar_url if profile else None,
            )
        )

    # Sort alphabetically by display_name
    results.sort(key=lambda r: r.display_name.lower())
    return results
