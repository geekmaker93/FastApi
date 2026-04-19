import os
import random
import re
import threading
from datetime import datetime, timezone
from typing import Annotated, Any, Dict, List, Optional

import requests
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from app.dependencies import get_current_user, get_db
from app.models.db_models import Farm, FarmerYieldReport, HistoricalYieldAverage, NDVISnapshot, SoilProfile, User, YieldResult
from app.routes.soil_weather import get_climate_report, get_weather
from app.services.climate_engine import detect_climate_pattern
from app.services.crop_engine import get_top_crops
from app.services.external_data_sources import fetch_crop_knowledge_bundle, fetch_external_sources_bundle
from app.services.usda_service import get_crop_data
from app.services.product_mapper import map_products
from app.services.region_mapper import get_region
from app.services.region_profiles import REGION_PROFILES
from app.services.rag_store import query_index
from app.services.product_locator import (
    find_nearby_stores,
    format_products_for_ai,
    format_stores_for_ai,
    get_procurement_guidelines,
    get_product_recommendations,
)

load_dotenv()

router = APIRouter(prefix="/ai", tags=["ai"])

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("CLOUD_AI_MODEL", "gemini-2.5-flash-lite").strip()
GEMINI_TIMEOUT_SECONDS = int(os.getenv("CLOUD_AI_TIMEOUT", "35"))
EXPOSE_AI_INTERNALS = os.getenv("EXPOSE_AI_INTERNALS", "false").strip().lower() == "true"
FARM_POLYGON_HALF_SIZE_DEGREES = 0.01
DEFAULT_CROP_TYPE = "Not specified"
DEFAULT_CROP_TYPE_NORMALIZED = DEFAULT_CROP_TYPE.lower()
AI_CONVERSATION_MAX_TURNS = int(os.getenv("AI_CONVERSATION_MAX_TURNS", "6"))
AI_SUMMARY_TRIGGER_MESSAGES = int(os.getenv("AI_SUMMARY_TRIGGER_MESSAGES", "10"))
AI_SUMMARY_KEEP_RECENT_MESSAGES = int(os.getenv("AI_SUMMARY_KEEP_RECENT_MESSAGES", "6"))
AI_SUMMARY_MAX_CHARS = int(os.getenv("AI_SUMMARY_MAX_CHARS", "1600"))
MAX_RAG = int(os.getenv("AI_MAX_RAG", "2"))
MAX_HISTORY = int(os.getenv("AI_MAX_HISTORY", "5"))
MAX_CROPS = int(os.getenv("AI_MAX_CROPS", "3"))
COVER_CROP_FOCUS = "cover crop"

PLANT_TYPES: Dict[str, list[str]] = {
    "fruit": ["banana", "plantain", "papaya", "strawberry", "apple", "orange", "mango", "grape", "melon"],
    "vegetable": ["tomato", "cabbage", "pepper", "onion", "carrot", "potato", "lettuce", "spinach", "okra"],
    "ornamental": ["sunflower", "marigold", "petunia", "zinnia", "rose", "hibiscus", "lavender"],
    "shade_tree": ["maple", "oak", "cedar", "pine", "spruce"],
    "cover_crop": ["clover", "ryegrass", "vetch", "mustard", "buckwheat"],
}

FALLBACK_FLOWERS: List[str] = ["zinnia", "cosmos", "aster", "calendula", "snapdragon"]

FLOWER_GROWTH_PROFILES: Dict[str, Dict[str, Any]] = {
    "sunflower": {"germination_days": 7, "maturity_days": 85, "water_needs": "moderate"},
    "marigold": {"germination_days": 5, "maturity_days": 60, "water_needs": "moderate"},
    "petunia": {"germination_days": 8, "maturity_days": 90, "water_needs": "moderate"},
    "zinnia": {"germination_days": 5, "maturity_days": 75, "water_needs": "moderate"},
    "cosmos": {"germination_days": 7, "maturity_days": 90, "water_needs": "low-moderate"},
    "aster": {"germination_days": 10, "maturity_days": 110, "water_needs": "moderate"},
    "calendula": {"germination_days": 6, "maturity_days": 60, "water_needs": "moderate"},
    "snapdragon": {"germination_days": 10, "maturity_days": 100, "water_needs": "moderate"},
    "hibiscus": {"germination_days": 10, "maturity_days": 120, "water_needs": "moderate"},
    "lavender": {"germination_days": 14, "maturity_days": 160, "water_needs": "low"},
    "rose": {"germination_days": 14, "maturity_days": 120, "water_needs": "moderate"},
}

EXCLUSION_PATTERNS: Dict[str, list[str]] = {
    "fruit": ["not fruit", "no fruit", "exclude fruit", "without fruit", "not fruits", "no fruits"],
    "vegetable": [
        "not vegetable",
        "not vegetables",
        "no vegetable",
        "no vegetables",
        "exclude vegetable",
        "exclude vegetables",
        "without vegetable",
        "without vegetables",
    ],
}

_CONVERSATION_STORE: Dict[str, list[Dict[str, str]]] = {}
_CONVERSATION_META: Dict[str, Dict[str, Any]] = {}
_CONVERSATION_LOCK = threading.Lock()

SYSTEM_PROMPT = """
You are a smart agricultural assistant.

- Speak naturally, not like a report.
- Always give a clear recommendation first.
- Use provided crop recommendations as the primary answer whenever they are available.
- If data is missing, use general agricultural knowledge and still provide a practical answer.
- Be confident and action-oriented.

Rules:
- Never say "insufficient data", "not enough information", or "I cannot determine".
- If top crop recommendations are provided, you MUST use them and do not ignore them.
- Do not invent weather values, products, or stores that are not present in context.
- If USDA crop data is available, use it to validate crop recommendations and prefer crops with stable or increasing yield trends.
- Keep responses concise, practical, and conversational.
"""


_VALID_ATTACHMENT_TYPES = {"ndvi", "plant", "soil", "text"}


class CloudAIChatRequest(BaseModel):
    question: str = Field(..., min_length=2, max_length=3000)
    farm_id: Optional[int] = None
    context: Optional[Dict[str, Any]] = None
    image_base64: Optional[str] = None
    image_mime_type: Optional[str] = None
    # Attachment type: ndvi | plant | soil | text
    attachment_type: Optional[str] = None


@router.get("/status")
def ai_status() -> Dict[str, Any]:
    return {
        "provider": "gemini",
        "model": GEMINI_MODEL,
        "configured": bool(GEMINI_API_KEY),
        "capabilities": {
            "farm_creation_from_ai_request": True,
            "realtime_weather_compare": True,
            "product_and_store_recommendations": True,
            "local_structured_advice": True,
            "app_section_statistics": True,
            "nasa_noaa_esa_sources": True,
            "rag_retrieval": True,
            "agronomy_reasoning": True,
        },
    }


# ── Snapshot analysis ─────────────────────────────────────────────────────────

class _AnalyzeSnapshotRequest(BaseModel):
    farm_id: int


@router.post("/analyze-snapshot")
def analyze_snapshot(
    payload: _AnalyzeSnapshotRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Dict[str, Any]:
    """Run AI analysis on the latest NDVI snapshot metadata for a farm."""
    farm = db.query(Farm).filter(Farm.id == payload.farm_id, Farm.user_id == current_user.id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")

    snapshot = (
        db.query(NDVISnapshot)
        .filter(NDVISnapshot.farm_id == payload.farm_id)
        .order_by(NDVISnapshot.captured_at.desc().nullslast(), NDVISnapshot.date.desc().nullslast())
        .first()
    )
    if not snapshot:
        raise HTTPException(status_code=404, detail="No snapshot found for this farm")

    ndvi_avg = snapshot.ndvi_avg
    if ndvi_avg is None and isinstance(snapshot.ndvi_stats, dict):
        ndvi_avg = snapshot.ndvi_stats.get("avg") or snapshot.ndvi_stats.get("mean")

    ndvi_min = snapshot.ndvi_min
    ndvi_max = snapshot.ndvi_max
    if ndvi_min is None and isinstance(snapshot.ndvi_stats, dict):
        ndvi_min = snapshot.ndvi_stats.get("min")
    if ndvi_max is None and isinstance(snapshot.ndvi_stats, dict):
        ndvi_max = snapshot.ndvi_stats.get("max")

    crop = farm.crop_type or "unspecified crop"

    if ndvi_avg is None:
        return {
            "farm_id": payload.farm_id,
            "snapshot_id": snapshot.id,
            "ndvi_avg": None,
            "analysis": "NDVI data is not yet available for this snapshot.",
        }

    # Build a lightweight AI prompt
    prompt = (
        f"You are an agronomist AI. A farm named '{farm.name}' grows {crop}.\n"
        f"The latest NDVI snapshot shows: avg={ndvi_avg:.3f}, min={ndvi_min}, max={ndvi_max}.\n"
        f"NDVI scale: <0.2 bare/very stressed, 0.2-0.4 sparse/stressed, 0.4-0.6 moderate, 0.6-0.8 healthy, >0.8 dense.\n"
        f"Provide: (1) vegetation health summary, (2) likely stress indicators if any, "
        f"(3) one actionable recommendation for the farmer. Keep it under 120 words."
    )

    analysis_text = "AI not configured."
    if GEMINI_API_KEY:
        try:
            resp = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
                f"?key={GEMINI_API_KEY}",
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=GEMINI_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            data = resp.json()
            analysis_text = (
                data.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "No response from AI.")
            )
        except Exception as exc:
            analysis_text = f"AI request failed: {exc}"

    return {
        "farm_id": payload.farm_id,
        "snapshot_id": snapshot.id,
        "ndvi_avg": ndvi_avg,
        "ndvi_min": ndvi_min,
        "ndvi_max": ndvi_max,
        "captured_at": snapshot.captured_at or snapshot.date,
        "analysis": analysis_text,
    }


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _extract_point_from_polygon(polygon: Any) -> Dict[str, float]:
    if not isinstance(polygon, list) or not polygon:
        return {}

    lat_values = []
    lon_values = []
    for point in polygon:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        lon = _safe_float(point[0], None)
        lat = _safe_float(point[1], None)
        if lon is None or lat is None:
            continue
        lon_values.append(lon)
        lat_values.append(lat)

    if not lat_values or not lon_values:
        return {}

    return {
        "latitude": round(sum(lat_values) / len(lat_values), 6),
        "longitude": round(sum(lon_values) / len(lon_values), 6),
    }


def _make_square_polygon(latitude: float, longitude: float, half_size: float = FARM_POLYGON_HALF_SIZE_DEGREES) -> list:
    return [
        [longitude - half_size, latitude - half_size],
        [longitude + half_size, latitude - half_size],
        [longitude + half_size, latitude + half_size],
        [longitude - half_size, latitude + half_size],
        [longitude - half_size, latitude - half_size],
    ]


def _get_farm_context(db: Session, farm_id: Optional[int], user_id: Optional[int] = None) -> Dict[str, Any]:
    if not farm_id:
        return {}

    query = db.query(Farm).filter(Farm.id == farm_id)
    if user_id is not None:
        query = query.filter(Farm.user_id == user_id)
    farm = query.first()
    if not farm:
        return {"farm_id": farm_id, "warning": "farm_not_found"}

    recent_yields = (
        db.query(YieldResult)
        .filter(YieldResult.farm_id == farm_id)
        .order_by(YieldResult.date.desc())
        .limit(5)
        .all()
    )
    recent_ndvi = (
        db.query(NDVISnapshot)
        .filter(NDVISnapshot.farm_id == farm_id)
        .order_by(NDVISnapshot.date.desc())
        .limit(5)
        .all()
    )
    recent_reports = (
        db.query(FarmerYieldReport)
        .filter(FarmerYieldReport.farm_id == farm_id)
        .order_by(FarmerYieldReport.date.desc())
        .limit(5)
        .all()
    )
    historical_averages = (
        db.query(HistoricalYieldAverage)
        .filter(HistoricalYieldAverage.farm_id == farm_id)
        .order_by(HistoricalYieldAverage.year.desc())
        .limit(5)
        .all()
    )
    farm_point = _extract_point_from_polygon(farm.polygon)
    farm_region = get_region(
        _safe_float(farm_point.get("latitude"), None),
        _safe_float(farm_point.get("longitude"), None),
    )
    soil_profile = db.query(SoilProfile).filter(SoilProfile.farm_id == farm_id).first()

    return {
        "farm_id": farm.id,
        "farm_name": farm.name,
        "crop_type": farm.crop_type,
        "polygon": farm.polygon,
        "coordinates": farm_point,
        "region": farm_region,
        "soil_profile": {
            "source": soil_profile.source,
            "fetched_at": soil_profile.fetched_at,
            "topsoil_metrics": soil_profile.topsoil_metrics,
            "derived_properties": soil_profile.derived_properties,
        } if soil_profile else None,
        "recent_yields": [
            {
                "date": row.date.isoformat() if row.date else None,
                "yield_estimate": row.yield_estimate,
                "notes": row.notes,
            }
            for row in recent_yields
        ],
        "recent_ndvi": [
            {
                "date": row.date.isoformat() if row.date else None,
                "ndvi_stats": row.ndvi_stats,
            }
            for row in recent_ndvi
        ],
        "recent_reports": [
            {
                "date": row.date.isoformat() if row.date else None,
                "actual_yield": row.actual_yield,
                "notes": row.notes,
            }
            for row in recent_reports
        ],
        "historical_averages": [
            {
                "year": row.year,
                "crop_type": row.crop_type,
                "avg_yield": row.avg_yield,
                "min_yield": row.min_yield,
                "max_yield": row.max_yield,
                "sample_count": row.sample_count,
            }
            for row in historical_averages
        ],
    }


def _derive_issue_from_question(question: str, weather_payload: Dict[str, Any], climate_payload: Dict[str, Any]) -> str:
    text = (question or "").lower()

    current = weather_payload.get("current") if isinstance(weather_payload, dict) else {}
    climate_daily = climate_payload.get("daily_snapshot") if isinstance(climate_payload, dict) else {}
    temp_c = _safe_float((current or {}).get("temperature"), _safe_float((climate_daily or {}).get("temperature_c"), 0.0)) or 0.0
    humidity = _safe_float((current or {}).get("humidity"), _safe_float((climate_daily or {}).get("humidity_percent"), 0.0)) or 0.0

    issue_rules = [
        ("fungal_pressure", ["fungus", "fungal", "mold", "blight"]),
        ("pest_pressure", ["pest", "bug", "insect", "aphid"]),
        ("acidic_soil", ["acid", "ph", "acidic"]),
        ("early_vigor", ["nitrogen", "growth", "vigor", "fertilizer"]),
    ]

    if humidity >= 85.0:
        return "fungal_pressure"
    if _matches_any(text, ["soil", "top soil", "compost", "organic matter"]) or temp_c < 18.0:
        return "low_organic_matter"

    for issue_name, keywords in issue_rules:
        if _matches_any(text, keywords):
            return issue_name
    return "general"


def _matches_any(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _normalize_category_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    normalized: list[str] = []
    for item in values:
        text = str(item or "").strip().lower()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _extract_excluded_categories_from_question(question: str) -> list[str]:
    text = (question or "").strip().lower()
    if not text:
        return []

    excluded: list[str] = []
    for category, patterns in EXCLUSION_PATTERNS.items():
        if any(pattern in text for pattern in patterns):
            excluded.append(category)
    return excluded


def _merge_excluded_categories(existing: Any, from_turn: list[str]) -> list[str]:
    merged = _normalize_category_list(existing)
    for item in from_turn:
        if item not in merged:
            merged.append(item)
    return merged


def _extract_constraints_from_context(app_context: Dict[str, Any]) -> Dict[str, Any]:
    constraints = _as_dict((app_context or {}).get("constraints"))
    excluded = _normalize_category_list(constraints.get("exclude_categories"))
    return {"exclude_categories": excluded}


def _classify_plant_type(name: str) -> str:
    text = str(name or "").strip().lower()
    for category, names in PLANT_TYPES.items():
        if text in names:
            return category
    return "other"


def _apply_category_constraints(crops: list[Dict[str, Any]], excluded_categories: list[str]) -> list[Dict[str, Any]]:
    excluded = set(_normalize_category_list(excluded_categories))
    if not excluded:
        return crops

    filtered: list[Dict[str, Any]] = []
    for crop in crops:
        if not isinstance(crop, dict):
            continue
        category = _classify_plant_type(crop.get("name"))
        if category in excluded:
            continue
        enriched = dict(crop)
        enriched["plant_type"] = category
        filtered.append(enriched)
    return filtered


def _needs_vague_category_clarification(question: str) -> bool:
    text = (question or "").strip().lower()
    if not text:
        return False
    vague_markers = [
        "regular plant",
        "normal plant",
        "ordinary plant",
        "just plant",
    ]
    return any(marker in text for marker in vague_markers)


def _extract_plant_focus_query(question: str, app_context: Dict[str, Any], conversation_meta: Dict[str, Any]) -> Optional[str]:
    explicit_focus = str((app_context or {}).get("plant_focus_query") or "").strip().lower()
    if explicit_focus:
        return explicit_focus

    text = (question or "").strip().lower()
    focus_keywords = {
        "flower": ["flower", "flowers", "ornamental", "ornamentals", "bloom", "blooms"],
        "tree": ["tree", "trees", "shade tree", "shade trees"],
        COVER_CROP_FOCUS: [COVER_CROP_FOCUS, "cover crops", "ground cover"],
    }
    for focus_query, keywords in focus_keywords.items():
        if any(keyword in text for keyword in keywords):
            return focus_query

    remembered_focus = str((conversation_meta or {}).get("last_focus_query") or "").strip().lower()
    if remembered_focus:
        return remembered_focus

    remembered_crop = str((conversation_meta or {}).get("last_recommended_crop") or "").strip().lower()
    if remembered_crop:
        return remembered_crop
    return None


def _preferred_plant_type_for_focus(focus_query: Optional[str]) -> Optional[str]:
    text = str(focus_query or "").strip().lower()
    if text == "flower":
        return "ornamental"
    if text == "tree":
        return "shade_tree"
    if text == "cover crop":
        return "cover_crop"
    return None


def _build_action_results(question: str, app_context: Dict[str, Any], db: Session, current_user: User) -> Dict[str, Any]:
    action_results: Dict[str, Any] = {}
    action_request = _extract_action_request(question, app_context)
    if not action_request:
        return action_results

    try:
        action_results["create_farm"] = _create_farm_from_action(db, action_request, current_user.id)
    except Exception as exc:
        db.rollback()
        action_results["create_farm"] = {
            "created": False,
            "reason": f"error: {exc}",
        }
    return action_results


def _build_common_payload(body: CloudAIChatRequest, db: Session, current_user: User) -> Dict[str, Any]:
    farm_context = _get_farm_context(db, body.farm_id, current_user.id)
    if body.farm_id and farm_context.get("warning") == "farm_not_found":
        raise HTTPException(status_code=404, detail="Farm not found")
    app_context = body.context or {}
    question = body.question.strip()

    effective_app_context = dict(app_context) if isinstance(app_context, dict) else {}
    effective_app_context["user_id"] = current_user.id
    conversation_key = _build_conversation_key(body.farm_id, effective_app_context, current_user.id)
    conversation_meta = _get_conversation_meta(conversation_key)
    plant_focus_query = _extract_plant_focus_query(question, effective_app_context, conversation_meta)

    prior_exclusions = _normalize_category_list((conversation_meta or {}).get("exclude_categories"))
    turn_exclusions = _extract_excluded_categories_from_question(question)
    merged_exclusions = _merge_excluded_categories(prior_exclusions, turn_exclusions)
    constraints = _as_dict(effective_app_context.get("constraints"))
    constraints["exclude_categories"] = merged_exclusions
    effective_app_context["constraints"] = constraints

    crop_query = _extract_crop_query(question, effective_app_context, farm_context)
    if not crop_query and plant_focus_query:
        crop_query = plant_focus_query
    if not crop_query:
        remembered_crop = str(conversation_meta.get("last_crop") or "").strip()
        if remembered_crop:
            crop_query = remembered_crop

    existing_crop = str(effective_app_context.get("crop_type") or "").strip().lower()
    if crop_query and (not existing_crop or existing_crop == DEFAULT_CROP_TYPE_NORMALIZED):
        effective_app_context["crop_type"] = crop_query
    if plant_focus_query:
        effective_app_context["plant_focus_query"] = plant_focus_query

    coordinates = _resolve_coordinates(effective_app_context, farm_context)
    action_results = _build_action_results(question, effective_app_context, db, current_user)
    realtime_context = _build_realtime_context(
        question,
        coordinates,
        crop_query=crop_query,
        farm_context=farm_context,
        constraints=constraints,
        plant_focus_query=plant_focus_query,
    )
    return {
        "question": question,
        "farm_context": farm_context,
        "app_context": effective_app_context,
        "constraints": constraints,
        "plant_focus_query": plant_focus_query,
        "conversation_key": conversation_key,
        "action_results": action_results,
        "realtime_context": realtime_context,
    }


def _load_user_memory(farm_id: Optional[int], app_context: Dict[str, Any], current_user: User) -> Dict[str, Any]:
    conversation_key = _build_conversation_key(farm_id, app_context, current_user.id)
    return {
        "conversation_key": conversation_key,
        "conversation_history": _get_conversation_history(conversation_key),
        "conversation_summary": _get_conversation_summary(conversation_key),
        "conversation_meta": _get_conversation_meta(conversation_key),
    }


def _with_memory_crop_context(
    question: str,
    farm_context: Dict[str, Any],
    app_context: Dict[str, Any],
    realtime_context: Dict[str, Any],
    conversation_meta: Dict[str, Any],
    conversation_history: list[Dict[str, str]],
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    def _rebuild_with_crop(source_app_context: Dict[str, Any], crop_value: str) -> tuple[Dict[str, Any], Dict[str, Any]]:
        updated_context = dict(source_app_context)
        updated_context["crop_type"] = crop_value
        coordinates = _resolve_coordinates(updated_context, farm_context)
        updated_realtime = _build_realtime_context(
            question,
            coordinates,
            crop_query=crop_value,
            farm_context=farm_context,
            constraints=_extract_constraints_from_context(updated_context),
        )
        return updated_context, updated_realtime

    remembered_crop = str((conversation_meta or {}).get("last_crop") or "").strip().lower()
    current_crop = str((app_context or {}).get("crop_type") or "").strip().lower()
    if remembered_crop and (not current_crop or current_crop == DEFAULT_CROP_TYPE_NORMALIZED):
        return _rebuild_with_crop(app_context, remembered_crop)

    if not current_crop or current_crop == DEFAULT_CROP_TYPE_NORMALIZED:
        inferred_crop = _extract_crop_from_conversation_history(conversation_history)
        if inferred_crop:
            return _rebuild_with_crop(app_context, inferred_crop)

    return app_context, realtime_context


def _first_non_empty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _build_conversation_key(farm_id: Optional[int], app_context: Dict[str, Any], authenticated_user_id: Optional[int] = None) -> str:
    resolved_user_id = _first_non_empty(authenticated_user_id)
    if isinstance(app_context, dict):
        explicit_id = _first_non_empty(
            app_context.get("conversation_id")
            , app_context.get("chat_id")
            , app_context.get("session_id")
            , app_context.get("memory_key")
        )
        if explicit_id:
            if resolved_user_id:
                return f"user:{resolved_user_id}:conversation:{explicit_id}"
            return f"conversation:{explicit_id}"

        user_id = resolved_user_id or _first_non_empty(app_context.get("user_id"), app_context.get("uid"), app_context.get("user"))
        screen = str(app_context.get("screen") or "").strip()
        if user_id and farm_id:
            return f"user:{user_id}:farm:{farm_id}"
        if user_id and screen:
            return f"user:{user_id}:screen:{screen}"
        if user_id:
            return f"user:{user_id}"

        lat = _safe_float(app_context.get("latitude"), None)
        lon = _safe_float(app_context.get("longitude"), None)
        if lat is not None and lon is not None:
            return f"loc:{round(lat, 4)}:{round(lon, 4)}"

    if resolved_user_id and farm_id is not None:
        return f"user:{resolved_user_id}:farm:{farm_id}"
    if resolved_user_id:
        return f"user:{resolved_user_id}:global"
    if farm_id is not None:
        return f"farm:{farm_id}"
    return "global:default"


def _get_conversation_history(conversation_key: str) -> list[Dict[str, str]]:
    with _CONVERSATION_LOCK:
        history = _CONVERSATION_STORE.get(conversation_key, [])
        return [dict(item) for item in history]


def _get_conversation_meta(conversation_key: str) -> Dict[str, Any]:
    with _CONVERSATION_LOCK:
        meta = _CONVERSATION_META.get(conversation_key, {})
        return dict(meta)


def _get_conversation_summary(conversation_key: str) -> str:
    with _CONVERSATION_LOCK:
        meta = _CONVERSATION_META.get(conversation_key, {})
        return str(meta.get("conversation_summary") or "").strip()


def _shorten_text(text: str, limit: int = 220) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(0, limit - 3)] + "..."


def _build_history_summary(messages: list[Dict[str, str]], max_items: int = 12) -> str:
    snippets: list[str] = []
    for item in messages[-max_items:]:
        role = str(item.get("role") or "").strip().lower()
        content = _shorten_text(str(item.get("content") or ""), limit=180)
        if not content:
            continue
        role_prefix = "U" if role == "user" else "A" if role == "assistant" else "O"
        snippets.append(f"{role_prefix}: {content}")
    return " | ".join(snippets)


def _merge_summaries(previous: str, newest: str) -> str:
    if not previous:
        merged = newest
    elif not newest:
        merged = previous
    else:
        merged = previous + " || " + newest
    return _shorten_text(merged, limit=max(400, AI_SUMMARY_MAX_CHARS))


def _summarize_if_needed_locked(conversation_key: str, history: list[Dict[str, str]]) -> list[Dict[str, str]]:
    if len(history) <= AI_SUMMARY_TRIGGER_MESSAGES:
        return history

    keep_recent = max(2, AI_SUMMARY_KEEP_RECENT_MESSAGES)
    archival = history[:-keep_recent]
    if not archival:
        return history

    newest_summary = _build_history_summary(archival)
    meta = dict(_CONVERSATION_META.get(conversation_key, {}))
    previous_summary = str(meta.get("conversation_summary") or "")
    meta["conversation_summary"] = _merge_summaries(previous_summary, newest_summary)
    meta["summary_turns"] = int(meta.get("summary_turns") or 0) + len(archival)
    meta["last_summarized_at"] = datetime.now(timezone.utc).isoformat()
    _CONVERSATION_META[conversation_key] = meta
    return history[-keep_recent:]


def _update_conversation_meta(
    conversation_key: str,
    question: str,
    crop_query: Optional[str],
    intent: str,
    excluded_categories: Optional[list[str]] = None,
    plant_focus_query: Optional[str] = None,
    last_recommended_crop: Optional[str] = None,
) -> None:
    with _CONVERSATION_LOCK:
        meta = dict(_CONVERSATION_META.get(conversation_key, {}))
        if crop_query and str(crop_query).strip():
            meta["last_crop"] = str(crop_query).strip().lower()
        if plant_focus_query and str(plant_focus_query).strip():
            meta["last_focus_query"] = str(plant_focus_query).strip().lower()
        if last_recommended_crop and str(last_recommended_crop).strip():
            meta["last_recommended_crop"] = str(last_recommended_crop).strip().lower()
        if excluded_categories is not None:
            meta["exclude_categories"] = _normalize_category_list(excluded_categories)
        if intent:
            meta["last_intent"] = intent
        meta["last_question"] = (question or "").strip()[:300]
        meta["last_updated_at"] = datetime.now(timezone.utc).isoformat()
        _CONVERSATION_META[conversation_key] = meta


def _finalize_conversation(
    conversation_key: str,
    question: str,
    answer: str,
    crop_query: Optional[str],
    intent: str,
    excluded_categories: Optional[list[str]] = None,
    plant_focus_query: Optional[str] = None,
    last_recommended_crop: Optional[str] = None,
    stored_user_message: Optional[str] = None,
) -> str:
    cleaned_answer = _sanitize_answer_text(answer)
    # Store a compact user message for image turns to avoid polluting history
    # with verbose instruction prefixes that bias subsequent image analyses.
    _append_conversation_turn(conversation_key, "user", stored_user_message or question)
    _append_conversation_turn(conversation_key, "assistant", cleaned_answer)
    _update_conversation_meta(
        conversation_key=conversation_key,
        question=question,
        crop_query=crop_query,
        intent=intent,
        excluded_categories=excluded_categories,
        plant_focus_query=plant_focus_query,
        last_recommended_crop=last_recommended_crop,
    )
    return cleaned_answer


def _append_conversation_turn(conversation_key: str, role: str, content: str) -> None:
    text = (content or "").strip()
    if not text:
        return

    max_messages = max(
        AI_SUMMARY_TRIGGER_MESSAGES + AI_SUMMARY_KEEP_RECENT_MESSAGES + 2,
        AI_CONVERSATION_MAX_TURNS * 3,
    )
    with _CONVERSATION_LOCK:
        history = _CONVERSATION_STORE.get(conversation_key, [])
        history.append({"role": role, "content": text[:2500]})
        history = _summarize_if_needed_locked(conversation_key, history)
        if len(history) > max_messages:
            history = history[-max_messages:]
        _CONVERSATION_STORE[conversation_key] = history


def _extract_structured_top_crops(realtime_context: Dict[str, Any]) -> List[Dict[str, Any]]:
    crops = realtime_context.get("top_crop_recommendations") if isinstance(realtime_context, dict) else []
    if not isinstance(crops, list):
        return []

    structured: List[Dict[str, Any]] = []
    for crop in crops[: max(1, MAX_CROPS)]:
        if not isinstance(crop, dict):
            continue
        structured.append(
            {
                "name": str(crop.get("name") or "Unknown crop"),
                "plant_type": str(crop.get("plant_type") or _classify_plant_type(crop.get("name"))),
                "score": int(_safe_float(crop.get("score"), 0) or 0),
                "reason": str(crop.get("reason") or "fit estimated from local farm and weather conditions"),
            }
        )
    return structured


def _extract_structured_inputs(realtime_context: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw_inputs = realtime_context.get("recommended_inputs") if isinstance(realtime_context, dict) else []
    if not isinstance(raw_inputs, list):
        return []

    structured: List[Dict[str, Any]] = []
    for item in raw_inputs[:5]:
        if isinstance(item, dict):
            structured.append(
                {
                    "name": str(item.get("name") or "Input"),
                    "type": str(item.get("type") or "general"),
                    "reason": str(item.get("reason") or "recommended from crop-fit logic"),
                    "timing": str(item.get("timing") or "apply according to label guidance"),
                }
            )
        else:
            text = str(item).strip()
            if text:
                structured.append(
                    {
                        "name": text,
                        "type": "general",
                        "reason": "recommended from crop-fit logic",
                        "timing": "apply according to label guidance",
                    }
                )
    return structured


def _extract_external_flower_candidates(external_sources: Dict[str, Any]) -> List[Dict[str, Any]]:
    sources = _as_dict((external_sources or {}).get("sources"))
    candidates: Dict[str, Dict[str, Any]] = {}

    for source_name in ("perenual", "trefle"):
        source_payload = _as_dict(sources.get(source_name))
        plants = source_payload.get("plants")
        if not isinstance(plants, list):
            continue

        for item in plants[:20]:
            if not isinstance(item, dict):
                continue
            name = str(item.get("common_name") or item.get("scientific_name") or "").strip().lower()
            if not name:
                continue
            plant_type = _classify_plant_type(name)
            if plant_type != "ornamental":
                continue
            if name not in candidates:
                candidates[name] = {
                    "name": name,
                    "source": source_name,
                    "watering": str(item.get("watering") or "").strip().lower() or None,
                }
    return list(candidates.values())


def _build_flower_risk_notes(
    weather_payload: Dict[str, Any],
    climate_payload: Dict[str, Any],
    regional_risk_alerts: List[str],
) -> str:
    current = _as_dict(_as_dict(weather_payload).get("current"))
    climate_daily = _as_dict(_as_dict(climate_payload).get("daily_snapshot"))
    humidity = _safe_float(current.get("humidity"), _safe_float(climate_daily.get("humidity_percent"), 65.0)) or 65.0
    rainfall = _safe_float(_as_dict(weather_payload).get("precipitation_mm"), 0.0) or 0.0

    notes: List[str] = []
    if humidity >= 80:
        notes.append("High humidity raises fungal pressure")
    if rainfall >= 10:
        notes.append("Recent rainfall increases damping-off risk for seedlings")
    if "hurricane" in [str(item).strip().lower() for item in (regional_risk_alerts or [])]:
        notes.append("Regional storm risk: protect young transplants from wind")
    if not notes:
        notes.append("No extreme flower-specific risk signal detected")
    return "; ".join(notes[:2])


def _build_dynamic_flower_recommendation(
    plant_focus_query: Optional[str],
    preferred_plant_type: Optional[str],
    external_sources: Dict[str, Any],
    weather_payload: Dict[str, Any],
    climate_payload: Dict[str, Any],
    regional_risk_alerts: List[str],
) -> Dict[str, Any]:
    focus = str(plant_focus_query or "").strip().lower()
    preferred = str(preferred_plant_type or "").strip().lower()
    is_flower_focus = preferred == "ornamental" or focus in {"flower", "ornamental"}
    if not is_flower_focus:
        return {}

    api_candidates = _extract_external_flower_candidates(external_sources)
    if api_candidates:
        picked = random.choice(api_candidates)
        picked_name = str(picked.get("name") or "").strip().lower()
        profile = FLOWER_GROWTH_PROFILES.get(picked_name, {
            "germination_days": 7,
            "maturity_days": 90,
            "water_needs": "moderate",
        })
        water_needs = str(picked.get("watering") or profile.get("water_needs") or "moderate")
        source_mode = "external_api"
    else:
        picked_name = random.choice(FALLBACK_FLOWERS)
        profile = FLOWER_GROWTH_PROFILES.get(picked_name, {
            "germination_days": 7,
            "maturity_days": 90,
            "water_needs": "moderate",
        })
        water_needs = str(profile.get("water_needs") or "moderate")
        source_mode = "fallback_pool"

    return {
        "name": picked_name.title(),
        "germination_days": int(_safe_float(profile.get("germination_days"), 7) or 7),
        "maturity_days": int(_safe_float(profile.get("maturity_days"), 90) or 90),
        "water_needs": water_needs,
        "risk_notes": _build_flower_risk_notes(weather_payload, climate_payload, regional_risk_alerts),
        "selection_mode": source_mode,
    }


def _format_dynamic_flower_recommendation(realtime_context: Dict[str, Any]) -> str:
    flower = _as_dict((realtime_context or {}).get("dynamic_flower_recommendation"))
    if not flower:
        return ""

    name = str(flower.get("name") or "Flower")
    germination = int(_safe_float(flower.get("germination_days"), 7) or 7)
    maturity = int(_safe_float(flower.get("maturity_days"), 90) or 90)
    water_needs = str(flower.get("water_needs") or "moderate")
    risk_notes = str(flower.get("risk_notes") or "No extreme flower-specific risk signal detected")

    lines = [
        f"Top Flower Recommendation: {name} (dynamic selection)",
        f"Growth Timeline: {germination}-{maturity} days",
        f"Water Needs: {water_needs}",
        f"Risk Notes: {risk_notes}",
    ]
    return "\n".join(lines)


def _build_image_context_prefix(
    attachment_type: Optional[str],
    farm_context: Dict[str, Any],
    realtime_context: Dict[str, Any],
) -> str:
    """Build a type-specific instruction prefix for image-attached messages."""
    atype = str(attachment_type or "").strip().lower()
    if atype not in _VALID_ATTACHMENT_TYPES or atype == "text":
        return "[Image attached — analyze it and provide relevant agricultural insights.]\n\n"

    farm_name = str((farm_context or {}).get("farm_name") or "this farm").strip()
    crop = str((farm_context or {}).get("crop_type") or "unspecified").strip()

    weather = _as_dict((realtime_context or {}).get("weather"))
    current = _as_dict(weather.get("current"))
    temp = _safe_float(current.get("temperature"), None)
    humidity = _safe_float(current.get("humidity"), None)
    rain = _safe_float(weather.get("precipitation_mm"), None)
    weather_parts: List[str] = []
    if temp is not None:
        weather_parts.append(f"Temp: {temp}°C")
    if humidity is not None:
        weather_parts.append(f"Humidity: {humidity}%")
    if rain is not None:
        weather_parts.append(f"Rain: {rain} mm")
    weather_line = (", ".join(weather_parts) + " | ") if weather_parts else ""

    if atype == "ndvi":
        return (
            f"[NDVI / Satellite Image — Farm: {farm_name}, Crop: {crop}, {weather_line}]\n"
            "Analyze this NDVI image carefully and:\n"
            "1. Evaluate overall vegetation health (NDVI scale: <0.2 bare/stressed, "
            "0.2-0.4 sparse, 0.4-0.6 moderate, 0.6-0.8 healthy, >0.8 dense).\n"
            "2. Identify stress zones — describe colour patterns (dark green=healthy, "
            "yellow/brown/red=stressed).\n"
            "3. Estimate the percentage of healthy vs stressed canopy cover.\n"
            "4. Suggest the most likely causes of any stress.\n"
            "5. Give 3 specific, actionable recommendations the farmer should apply this week.\n\n"
        )
    if atype == "plant":
        return (
            f"[Plant Health Photo — Farm: {farm_name}, Crop: {crop}, {weather_line}]\n"
            "Analyze this plant image carefully and:\n"
            "1. Identify the plant species or crop type visible.\n"
            "2. Assess overall plant health (Healthy / Fair / Moderate Stress / Severe Stress).\n"
            "3. Detect any signs of disease, pest damage, or nutrient deficiency.\n"
            "4. Describe visible symptoms (leaf colour, spots, curling, wilting, etc.).\n"
            "5. Recommend 3 specific treatment steps the farmer should take immediately.\n\n"
        )
    if atype == "soil":
        return (
            f"[Soil / Land Image — Farm: {farm_name}, Crop: {crop}, {weather_line}]\n"
            "Analyze this soil or land image carefully and:\n"
            "1. Estimate soil condition (colour, texture, surface moisture).\n"
            "2. Detect signs of dryness, compaction, erosion, waterlogging, or surface crust.\n"
            "3. Assess whether this soil is ready for planting or needs preparation.\n"
            "4. Suggest 3 specific soil improvement or preparation steps.\n\n"
        )
    return "[Image attached — analyze it and provide relevant agricultural insights.]\n\n"


_ISSUE_KEYWORD_MAP: List[tuple[str, List[str]]] = [
    ("Leaf Blight", ["blight", "leaf blight"]),
    ("Fungal Infection", ["fungal", "fungus", "mold", "mildew", "rust"]),
    ("Pest Damage", ["pest", "insect", "aphid", "caterpillar", "bug", "mite", "whitefly"]),
    ("Nutrient Deficiency", ["deficiency", "nitrogen", "phosphorus", "potassium", "yellowing", "chlorosis"]),
    ("Water Stress / Drought", ["drought stress", "water stress", "wilting", "dry soil", "lack of moisture"]),
    ("Waterlogging", ["waterlog", "flooding", "overwater", "soggy", "saturated"]),
    ("Soil Compaction", ["compaction", "compacted", "hardpan"]),
    ("Erosion", ["erosion", "eroded", "runoff", "gully"]),
]


def _parse_structured_image_response(answer: str, attachment_type: Optional[str]) -> Dict[str, Any]:
    """Extract structured fields (plant, health, issue, recommendations) from AI answer text."""
    atype = str(attachment_type or "").strip().lower()
    if not answer or atype not in _VALID_ATTACHMENT_TYPES or atype == "text":
        return {}

    result: Dict[str, Any] = {"type": atype}
    text_lower = answer.lower()

    # Health status
    if any(kw in text_lower for kw in ["severe stress", "critical", "very poor", "dying", "dead"]):
        result["health"] = "Severe Stress"
    elif any(kw in text_lower for kw in ["moderate stress", "stressed", "unhealthy", "poor health", "diseased"]):
        result["health"] = "Moderate Stress"
    elif any(kw in text_lower for kw in ["healthy", "good health", "vigorous", "dense vegetation", "no stress"]):
        result["health"] = "Healthy"
    else:
        result["health"] = "Fair"

    # Plant name (only for plant type)
    if atype == "plant":
        for names in PLANT_TYPES.values():
            for name in names:
                if re.search(rf"\b{re.escape(name)}s?\b", answer, flags=re.IGNORECASE):
                    result["plant"] = name.title()
                    break
            if "plant" in result:
                break

    # Detected issue
    for issue_label, keywords in _ISSUE_KEYWORD_MAP:
        if any(kw in text_lower for kw in keywords):
            result["issue"] = issue_label
            break

    # Recommendations — numbered / bulleted lines
    recommendations: List[str] = []
    for line in answer.splitlines():
        stripped = line.strip()
        if re.match(r"^(\d+[\.\)]\s+|[-•*]\s+)", stripped) and len(stripped) > 12:
            clean = re.sub(r"^(\d+[\.\)]\s+|[-•*]\s+)", "", stripped).strip()
            if clean and len(clean) > 8:
                recommendations.append(clean)
    if recommendations:
        result["recommendations"] = recommendations[:5]

    return result


def _build_local_crop_response(realtime_context: Dict[str, Any]) -> str:
    top_crops = _extract_structured_top_crops(realtime_context)
    inputs = _extract_structured_inputs(realtime_context)
    excluded_categories = _normalize_category_list((realtime_context or {}).get("excluded_categories"))
    external_sources = _as_dict((realtime_context or {}).get("external_sources"))
    dynamic_flower = _as_dict((realtime_context or {}).get("dynamic_flower_recommendation"))

    if dynamic_flower:
        flower_block = _format_dynamic_flower_recommendation(realtime_context)
        lines = [
            "Using dynamic flower selection from live source data:",
            flower_block,
            "",
            "I can also give exact planting depth, spacing, and first-week watering for this flower if you want.",
        ]
        return "\n".join([line for line in lines if str(line).strip()])

    if top_crops:
        lines: List[str] = [
            "Based on your current farm conditions, these are the best crop options right now:",
            "",
        ]
        for crop in top_crops:
            lines.append(f"- {crop['name']} ({crop['score']}% suitability) — {crop['reason']}")

        if inputs:
            lines.extend(["", "Recommended inputs:"])
            for item in inputs:
                lines.append(f"- {item['name']}: {item['reason']} (timing: {item['timing']})")

        lines.extend([
            "",
            "Next step: start with the top-ranked crop in a small pilot area, monitor moisture and pest pressure for 7-10 days, then scale.",
        ])
        return "\n".join(lines)

    external_lines = _format_external_sources_summary(realtime_context)
    perenual = _as_dict(_as_dict(external_sources.get("sources")).get("perenual"))
    trefle = _as_dict(_as_dict(external_sources.get("sources")).get("trefle"))
    perenual_plants = perenual.get("plants") if isinstance(perenual.get("plants"), list) else []
    trefle_plants = trefle.get("plants") if isinstance(trefle.get("plants"), list) else []

    candidate_names: List[str] = []
    for item in perenual_plants[:5]:
        if isinstance(item, dict):
            name = str(item.get("common_name") or item.get("scientific_name") or "").strip()
            if name and name.lower() not in {n.lower() for n in candidate_names}:
                candidate_names.append(name)
    for item in trefle_plants[:5]:
        if isinstance(item, dict):
            name = str(item.get("common_name") or item.get("scientific_name") or "").strip()
            if name and name.lower() not in {n.lower() for n in candidate_names}:
                candidate_names.append(name)

    if candidate_names:
        lines = [
            "I used live plant data from available external sources and could not produce a confident suitability ranking from farm signals alone.",
            "",
            "External plant matches:",
        ]
        for name in candidate_names[:5]:
            lines.append(f"- {name}")
        if external_lines:
            lines.extend(["", external_lines])
        lines.extend(
            [
                "",
                "If you want a strict recommendation order, provide your target crop or tighter constraints (sunlight preference, watering level, or purpose such as ornamental/food).",
            ]
        )
        return "\n".join(lines)

    return (
        "I could not find enough plant records from external endpoints to give a data-backed crop recommendation right now. "
        + ("Current exclusions applied: " + ", ".join(excluded_categories) + ". " if excluded_categories else "")
        + "Please retry with a specific crop query so I can pull targeted Perenual/Trefle records and answer from those sources."
    )


def _extract_recommended_crop_from_answer(answer: str) -> Optional[str]:
    text = str(answer or "")
    if not text.strip():
        return None

    for names in PLANT_TYPES.values():
        for name in names:
            if re.search(rf"\b{re.escape(name)}s?\b", text, flags=re.IGNORECASE):
                return str(name).strip().lower()
    return None


def _is_planting_follow_up(question: str) -> bool:
    text = (question or "").strip().lower()
    markers = [
        "planting recommendation",
        "how should i plant",
        "how do i plant",
        "planting method",
        "can you give me a planting recommendation",
    ]
    return any(marker in text for marker in markers)


def _build_crop_planting_guide(crop_name: str) -> str:
    crop = str(crop_name or "").strip().lower()
    guides = {
        "sunflower": [
            "Planting method: direct seed.",
            "Depth: 2-3 cm.",
            "Spacing: 15-30 cm between plants with 45-60 cm between rows.",
            "Water immediately after sowing and keep the top seed zone lightly moist until emergence.",
        ],
        "marigold": [
            "Planting method: transplant seedlings or direct sow in warm soil.",
            "Depth: 0.5-1 cm if direct seeding.",
            "Spacing: 20-30 cm between plants.",
            "Water gently right after planting and keep moisture even during the first 7-10 days.",
        ],
        "zinnia": [
            "Planting method: direct seed or transplant carefully.",
            "Depth: about 1 cm.",
            "Spacing: 20-25 cm between plants.",
            "Water after sowing and avoid waterlogging while seedlings establish.",
        ],
    }
    lines = guides.get(
        crop,
        [
            "Planting method: use a direct sow or transplant approach suited to the crop.",
            "Depth: use shallow placement for small seed and deeper placement for larger seed.",
            "Spacing: leave enough room for airflow and mature canopy spread.",
            "Water immediately after planting and keep the seed zone evenly moist during establishment.",
        ],
    )
    return "\n".join(lines)


def _append_crop_specific_planting_guidance(answer: str, question: str, remembered_crop: Optional[str]) -> str:
    if not _is_planting_follow_up(question):
        return answer

    crop_name = str(remembered_crop or "").strip().lower() or _extract_recommended_crop_from_answer(answer)
    if not crop_name:
        return answer

    planting_guide = _build_crop_planting_guide(crop_name)
    if planting_guide.lower() in str(answer or "").lower():
        return answer
    return f"{answer}\n\nRecommended planting setup for {crop_name.title()}:\n{planting_guide}"


def _build_response_payload(
    answer: str,
    provider: str,
    model: str,
    action_results: Dict[str, Any],
    realtime_context: Dict[str, Any],
    rag_context: Optional[Dict[str, Any]] = None,
    professional_analysis: Optional[Dict[str, Any]] = None,
    warning: Optional[str] = None,
    image_analysis: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    rag_context = rag_context or {}
    rag_results = rag_context.get("results", []) if isinstance(rag_context, dict) else []
    top_crops = _extract_structured_top_crops(realtime_context)
    recommended_inputs = _extract_structured_inputs(realtime_context)
    confidence = str((professional_analysis or {}).get("confidence") or "medium")

    payload = {
        "answer": _sanitize_answer_text(answer),
        "provider": provider,
        "model": model,
        "confidence": confidence,
        "region": str(realtime_context.get("region") or "default") if isinstance(realtime_context, dict) else "default",
        "regional_recommendations": realtime_context.get("regional_recommendations", []) if isinstance(realtime_context, dict) else [],
        "regional_risk_alerts": realtime_context.get("regional_risk_alerts", []) if isinstance(realtime_context, dict) else [],
        "top_crops": top_crops,
        "recommended_inputs": recommended_inputs,
        "action_results": action_results,
        "professional_analysis": professional_analysis or {},
        "constraints": _as_dict((professional_analysis or {}).get("constraints")),
        "risk_profile": _as_dict((professional_analysis or {}).get("risk_profile")),
        "realtime_summary": {
            "available": bool(realtime_context.get("available")),
            "coordinates": realtime_context.get("coordinates", {}),
            "derived_issue": realtime_context.get("derived_issue"),
            "region": str(realtime_context.get("region") or "default") if isinstance(realtime_context, dict) else "default",
            "climate_pattern": realtime_context.get("climate_pattern", "normal") if isinstance(realtime_context, dict) else "normal",
            "excluded_categories": realtime_context.get("excluded_categories", []) if isinstance(realtime_context, dict) else [],
            "stores_count": len(realtime_context.get("nearby_stores", [])) if isinstance(realtime_context, dict) else 0,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if EXPOSE_AI_INTERNALS:
        citations = [
            {
                "title": item.get("metadata", {}).get("title"),
                "source_type": item.get("metadata", {}).get("source_type"),
                "farm_id": item.get("metadata", {}).get("farm_id"),
                "score": item.get("score"),
            }
            for item in rag_results
        ]
        payload["citations"] = citations
        payload["rag_summary"] = {
            "available": bool(rag_context.get("available")),
            "results_count": len(rag_results),
            "used_documents": rag_context.get("used_documents", 0),
        }

    if warning:
        payload["warning"] = warning
    if image_analysis:
        payload["image_analysis"] = image_analysis
    return payload


_INTENT_RULES: Dict[str, Dict[str, Any]] = {
    "planting_and_siting": {
        "priority": 50,
        "phrases": [
            "when to plant",
            "when should i plant",
            "best place",
            "where should i plant",
            "spacing between",
            "seed rate",
            "planting window",
            "transplant shock",
        ],
        "stems": ["plant", "sow", "seed", "transplant", "spacing", "nurser", "germinat", "site", "location"],
        "regex": [r"\bplant\s+in\b", r"\bhow\s+deep\s+to\s+plant\b"],
    },
    "soil_and_fertility": {
        "priority": 40,
        "phrases": [
            "soil ph",
            "soil test",
            "nutrient deficiency",
            "fertilizer schedule",
            "organic matter",
            "n p k",
            "how much fertilizer",
        ],
        "stems": ["soil", "fertiliz", "nutrient", "compost", "manure", "npk", "ph", "potash", "phosph", "nitrogen"],
        "regex": [r"\bn\s*[:/-]\s*p\s*[:/-]\s*k\b", r"\b(ph|ec)\s*(level|value)?\b"],
    },
    "crop_protection": {
        "priority": 45,
        "phrases": [
            "pest control",
            "disease management",
            "leaf spot",
            "powdery mildew",
            "integrated pest management",
            "fungicide spray",
            "insecticide",
        ],
        "stems": ["disease", "pest", "fung", "blight", "mold", "rot", "wilt", "virus", "insect", "spray"],
        "regex": [r"\b(infected|infestation|symptom[s]?)\b", r"\bhow\s+to\s+treat\b"],
    },
    "irrigation_and_water": {
        "priority": 35,
        "phrases": [
            "how often to water",
            "irrigation schedule",
            "drip irrigation",
            "water stress",
            "soil moisture",
            "waterlogging",
        ],
        "stems": ["water", "irrig", "moisture", "drainage", "drought", "evap", "rain", "flood", "runoff"],
        "regex": [r"\bmm\s*/\s*day\b", r"\b(field\s+capacity|wilting\s+point)\b"],
    },
    "yield_and_forecast": {
        "priority": 30,
        "phrases": [
            "expected yield",
            "yield forecast",
            "harvest date",
            "how much will i harvest",
            "production estimate",
            "yield loss",
        ],
        "stems": ["yield", "harvest", "forecast", "predict", "estimate", "production", "ton", "kg", "bushel"],
        "regex": [r"\b(yield|harvest)\s*(prediction|forecast|estimate)\b", r"\b(per\s+acre|per\s+hectare)\b"],
    },
}


def _normalize_for_intent(text: str) -> str:
    lowered = (text or "").lower().strip()
    lowered = re.sub(r"[^a-z0-9\s/.-]", " ", lowered)
    return re.sub(r"\s+", " ", lowered)


def _score_intents(normalized_text: str) -> Dict[str, float]:
    tokens = [tok for tok in normalized_text.split(" ") if tok]
    scores: Dict[str, float] = dict.fromkeys(_INTENT_RULES.keys(), 0.0)

    for intent_name, rules in _INTENT_RULES.items():
        phrases = rules.get("phrases", [])
        stems = rules.get("stems", [])
        regexes = rules.get("regex", [])
        priority = float(rules.get("priority", 0)) / 100.0

        phrase_hits = sum(1 for phrase in phrases if phrase in normalized_text)
        if phrase_hits:
            scores[intent_name] += phrase_hits * 2.5

        stem_hits = 0
        for token in tokens:
            if any(token.startswith(stem) for stem in stems):
                stem_hits += 1
        if stem_hits:
            scores[intent_name] += min(stem_hits, 4) * 1.0

        regex_hits = 0
        for pattern in regexes:
            if re.search(pattern, normalized_text):
                regex_hits += 1
        if regex_hits:
            scores[intent_name] += regex_hits * 2.0

        scores[intent_name] += priority

    if "not about" in normalized_text or "not related to" in normalized_text:
        for intent_name in scores:
            scores[intent_name] = max(0.0, scores[intent_name] - 1.5)
    return scores


def _infer_intent(question: str) -> str:
    normalized = _normalize_for_intent(question)
    if not normalized:
        return "general_agronomy"

    scores = _score_intents(normalized)
    best_intent = max(scores, key=scores.get)
    best_score = scores.get(best_intent, 0.0)

    if best_score < 1.2:
        return "general_agronomy"
    return best_intent


def _append_unique_question(target: list[str], question: str) -> None:
    text = (question or "").strip()
    if not text:
        return
    lowered = text.lower()
    if any(item.lower() == lowered for item in target):
        return
    target.append(text)


def _intent_specific_follow_ups(intent: str, has_coords: bool) -> list[str]:
    if intent == "planting_and_siting":
        questions = ["What does the target area look like for sunlight hours, drainage after rain, and soil texture?"]
        if not has_coords:
            questions.append("Can you share the exact field location so I can anchor recommendations to local weather and source data?")
        return questions
    if intent == "soil_and_fertility":
        return ["Do you have recent soil pH, organic matter, or EC test values for this plot?"]
    if intent == "crop_protection":
        return ["What symptoms and crop stage are you seeing, and how fast is the issue spreading?"]
    if intent == "irrigation_and_water":
        return ["What is your current irrigation method and how quickly does the field drain after watering?"]
    if intent == "yield_and_forecast":
        return ["What was your most recent actual yield and what management changes were made this season?"]
    return []


def _build_follow_up_questions(
    intent: str,
    farm_context: Dict[str, Any],
    app_context: Dict[str, Any],
    realtime_context: Dict[str, Any],
) -> list[str]:
    questions: list[str] = []
    crop_type = str((farm_context or {}).get("crop_type") or (app_context or {}).get("crop_type") or "").strip()
    has_coords = bool((realtime_context or {}).get("available"))

    if not crop_type or crop_type.lower() == DEFAULT_CROP_TYPE_NORMALIZED:
        _append_unique_question(questions, "Which crop variety and growth stage are you managing right now?")

    for candidate in _intent_specific_follow_ups(intent, has_coords):
        _append_unique_question(questions, candidate)
    return questions[:3]


def _evidence_score(farm_context: Dict[str, Any], realtime_context: Dict[str, Any], rag_context: Dict[str, Any], sections_used: list[str]) -> int:
    score = 0
    if (realtime_context or {}).get("available"):
        score += 1
    if sections_used:
        score += 1
    if (rag_context or {}).get("results"):
        score += 1
    if (farm_context or {}).get("recent_yields"):
        score += 1
    return score


def _confidence_from_score(score: int) -> str:
    if score >= 4:
        return "high"
    if score >= 2:
        return "medium"
    return "low"


def _month_name(month: int) -> str:
    names = {
        1: "January",
        2: "February",
        3: "March",
        4: "April",
        5: "May",
        6: "June",
        7: "July",
        8: "August",
        9: "September",
        10: "October",
        11: "November",
        12: "December",
    }
    return names.get(month, "Unknown")


def _estimate_soil_moisture_drop(rainfall_mm: float, humidity_percent: float, temp_c: float) -> str:
    if rainfall_mm >= 5.0:
        return "5-10%"
    if rainfall_mm >= 1.0:
        return "10-15%"
    if humidity_percent < 45.0 or temp_c > 28.0:
        return "20-30%"
    return "15-25%"


def _is_clay_dominant_soil(farm_context: Dict[str, Any]) -> bool:
    soil_profile = _as_dict((farm_context or {}).get("soil_profile"))
    topsoil = _as_dict(soil_profile.get("topsoil_metrics"))
    clay_value = _safe_float(topsoil.get("clay"), None)
    return clay_value is not None and clay_value >= 35.0


def _compute_risk_profile(realtime_context: Dict[str, Any], farm_context: Dict[str, Any]) -> Dict[str, Any]:
    weather = _as_dict((realtime_context or {}).get("weather"))
    current = _as_dict(weather.get("current"))
    climate = _as_dict((realtime_context or {}).get("climate_report"))
    daily = _as_dict(climate.get("daily_snapshot"))
    region = str((realtime_context or {}).get("region") or "default")
    region_profile = _as_dict((realtime_context or {}).get("region_profile"))
    risk_factors = [str(item).strip().lower() for item in (region_profile.get("risk_factors") or [])]

    rainfall_mm = _safe_float(weather.get("precipitation_mm"), 0.0) or 0.0
    humidity_percent = _safe_float(current.get("humidity"), _safe_float(daily.get("humidity_percent"), 60.0)) or 60.0
    temp_c = _safe_float(current.get("temperature"), _safe_float(daily.get("temperature_c"), 20.0)) or 20.0
    germination_temp_c = 12.0

    risk_score = 0
    drivers: List[str] = []

    if rainfall_mm < 1.0:
        risk_score += 30
        drivers.append("Dry conditions (+30%)")

    if _is_clay_dominant_soil(farm_context):
        risk_score += 20
        drivers.append("Clay-heavy soil drainage risk (+20%)")

    if temp_c < germination_temp_c:
        delta = min(25, int(round((germination_temp_c - temp_c) * 2)))
        risk_score += delta
        drivers.append(f"Suboptimal germination temperature (+{delta}%)")

    month = datetime.now(timezone.utc).month
    if "frost" in risk_factors and month < 5:
        risk_score += 25
        drivers.append("Early-season frost exposure (+25%)")
    elif "frost" in risk_factors and month >= 10:
        risk_score += 20
        drivers.append("Late-season frost probability (+20%)")

    risk_percent = max(0, min(int(round(risk_score)), 100))
    if risk_percent >= 70:
        level = "high"
    elif risk_percent >= 45:
        level = "moderate-high"
    elif risk_percent >= 25:
        level = "moderate"
    else:
        level = "low"

    moisture_drop = _estimate_soil_moisture_drop(rainfall_mm, humidity_percent, temp_c)
    timeline_impact = {
        "day_1_3": [
            f"No meaningful rainfall trend keeps soil moisture drop around {moisture_drop}.",
            "Evapotranspiration pressure remains moderate to elevated when daytime heat persists.",
            "Germination failure risk rises after day 2 if the seed zone is not kept consistently moist.",
        ]
    }

    seasonal_notes: List[str] = []
    if "frost" in risk_factors:
        if month < 5:
            seasonal_notes.append(f"{region} early season: frost risk is active; delay sensitive planting or use row cover.")
        elif 5 <= month <= 8:
            seasonal_notes.append(f"{region} warm season: planting window is generally open for most annuals.")
        else:
            seasonal_notes.append(f"{region} late season: planting options narrow; prioritize cold-tolerant choices.")

    return {
        "risk_percent": risk_percent,
        "risk_level": level,
        "drivers": drivers,
        "timeline_impact": timeline_impact,
        "seasonal_notes": seasonal_notes,
        "reference_month": _month_name(month),
    }


def _build_clarification_response(excluded_categories: list[str]) -> str:
    blocked = ", ".join(excluded_categories) if excluded_categories else "fruit and vegetable"
    return (
        f"Understood. I will exclude {blocked} options. "
        "When you say regular plant, do you mean ornamental plants, shade trees, or non-edible cover crops?"
    )


def _build_professional_analysis(
    question: str,
    farm_context: Dict[str, Any],
    app_context: Dict[str, Any],
    realtime_context: Dict[str, Any],
    rag_context: Dict[str, Any],
    detected_intent: Optional[str] = None,
) -> Dict[str, Any]:
    intent = detected_intent or _infer_intent(question)
    sections_used: list[str] = []
    rag_results = (rag_context or {}).get("results") or []
    has_realtime = bool((realtime_context or {}).get("available"))
    score = _evidence_score(farm_context, realtime_context, rag_context, sections_used)
    confidence = _confidence_from_score(score)
    constraints = _extract_constraints_from_context(app_context)
    risk_profile = _compute_risk_profile(realtime_context, farm_context)

    follow_ups = _build_follow_up_questions(intent, farm_context, app_context, realtime_context)
    return {
        "intent": intent,
        "confidence": confidence,
        "reasoning_mode": "evidence_weighted_agronomy",
        "plant_focus_query": str((app_context or {}).get("plant_focus_query") or "").strip() or None,
        "evidence": {
            "realtime_available": has_realtime,
            "app_sections_used": sections_used,
            "rag_results_count": len(rag_results),
            "farm_history_points": len((farm_context or {}).get("recent_yields") or []),
        },
        "constraints": constraints,
        "risk_profile": risk_profile,
        "follow_up_questions": follow_ups,
    }


def _append_precision_questions(answer: str, professional_analysis: Dict[str, Any]) -> str:
    text = (answer or "").strip()
    confidence = str((professional_analysis or {}).get("confidence") or "").lower()
    follow_ups = (professional_analysis or {}).get("follow_up_questions") or []
    if confidence == "high":
        return text

    intent = str((professional_analysis or {}).get("intent") or "")
    lines = [item.strip() for item in follow_ups if isinstance(item, str) and item.strip()]

    missing_data = confidence in {"low", "medium"}
    if not missing_data:
        return text

    if "quick question:" in text.lower():
        return text

    if lines:
        quick_question = lines[0]
    elif intent == "planting_and_siting":
        quick_question = "How many sunlight hours does your farm get daily?"
    else:
        quick_question = "Can you share your crop stage and current field conditions so I can fine-tune the recommendation?"

    if not quick_question.endswith("?"):
        quick_question = quick_question.rstrip(".") + "?"

    return f"{text}\n\nQuick question: {quick_question}"


def _sanitize_answer_text(answer: str) -> str:
    text = (answer or "").strip()
    if not text:
        return ""

    forbidden_prefixes = (
        "sources:",
        "top sources:",
        "retrieved context",
        "docs considered",
        "missing data:",
    )

    kept_lines = []
    skip_precision_block = False
    for line in text.splitlines():
        normalized = line.strip().lower()
        if normalized.startswith("to make this recommendation more precise, confirm:"):
            skip_precision_block = True
            continue
        if skip_precision_block:
            if normalized.startswith("-") or not normalized:
                continue
            skip_precision_block = False
        if any(normalized.startswith(prefix) for prefix in forbidden_prefixes):
            continue
        kept_lines.append(line)

    return "\n".join(kept_lines).strip()


def _resolve_coordinates(app_context: Dict[str, Any], farm_context: Dict[str, Any]) -> Dict[str, float]:
    lat = _safe_float(app_context.get("latitude"), None)
    lon = _safe_float(app_context.get("longitude"), None)

    if lat is not None and lon is not None:
        return {"latitude": lat, "longitude": lon}

    farm_coords = farm_context.get("coordinates") if isinstance(farm_context, dict) else {}
    lat = _safe_float((farm_coords or {}).get("latitude"), None)
    lon = _safe_float((farm_coords or {}).get("longitude"), None)
    if lat is not None and lon is not None:
        return {"latitude": lat, "longitude": lon}

    return {}


def _extract_action_request(question: str, app_context: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(app_context, dict):
        return {}

    actions = app_context.get("ai_actions")
    if isinstance(actions, dict) and isinstance(actions.get("create_farm"), dict):
        return actions.get("create_farm")

    text = (question or "").strip()
    lowered = text.lower()
    farm_request_phrases = ["create farm", "add farm", "make a farm", "set up farm", "register farm"]
    if not any(phrase in lowered for phrase in farm_request_phrases):
        return {}

    name_match = re.search(r"(?:create|add|make|register|set up)\s+(?:a\s+)?farm(?:\s+(?:called|named))?\s+([a-z0-9 '-]{2,50})", text, flags=re.IGNORECASE)
    name = (name_match.group(1).strip() if name_match else "").strip(" .,;")
    if not name:
        return {}

    crop_match = re.search(r"(?:for|with|growing|planting)\s+([a-z][a-z0-9 -]{2,40})", text, flags=re.IGNORECASE)
    crop_type = (crop_match.group(1).strip() if crop_match else "").strip(" .,;")

    lat = _safe_float(app_context.get("latitude"), None)
    lon = _safe_float(app_context.get("longitude"), None)
    if lat is None or lon is None:
        return {}

    return {
        "name": name,
        "latitude": lat,
        "longitude": lon,
        "crop_type": crop_type or str(app_context.get("crop_type") or DEFAULT_CROP_TYPE),
    }


def _extract_crop_query(question: str, app_context: Dict[str, Any], farm_context: Dict[str, Any]) -> Optional[str]:
    crop_candidates = [
        str((farm_context or {}).get("crop_type") or "").strip(),
        str((app_context or {}).get("crop_type") or "").strip(),
    ]
    for crop in crop_candidates:
        if crop and crop.lower() != DEFAULT_CROP_TYPE_NORMALIZED:
            return crop

    text = (question or "").strip()
    patterns = [
        r"(?:plant|grow|sow|cultivate)\s+([a-z][a-z\s\-]{2,40})",
        r"(?:for|about)\s+([a-z][a-z\s\-]{2,40})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            candidate = match.group(1).strip(" .,;:!?\"'")
            if candidate:
                return candidate[:40]
    return None


def _extract_crop_from_conversation_history(conversation_history: list[Dict[str, str]]) -> Optional[str]:
    if not isinstance(conversation_history, list):
        return None

    patterns = [
        r"(?:for|about|growing|planting|care(?:ing)?\s+methods\s+for)\s+([a-z][a-z\s\-]{2,40})",
        r"\b([a-z]{3,20}s?)\b",
    ]
    generic_tokens = {
        "overview",
        "advice",
        "help",
        "recommendation",
        "methods",
        "care",
        "farming",
        "planting",
    }

    user_messages = [
        str(item.get("content") or "")
        for item in conversation_history
        if isinstance(item, dict) and str(item.get("role") or "").lower() == "user"
    ]
    for text in reversed(user_messages):
        cleaned = text.strip()
        if not cleaned:
            continue
        for pattern in patterns:
            match = re.search(pattern, cleaned, flags=re.IGNORECASE)
            if not match:
                continue
            candidate = match.group(1).strip(" .,;:!?\"'").lower()
            if not candidate or candidate in generic_tokens:
                continue
            return candidate[:40]
    return None


def _create_farm_from_action(db: Session, request: Dict[str, Any], owner_user_id: int) -> Dict[str, Any]:
    if not isinstance(request, dict):
        return {"created": False, "reason": "invalid_request"}

    name = str(request.get("name", "")).strip()
    latitude = _safe_float(request.get("latitude"), None)
    longitude = _safe_float(request.get("longitude"), None)
    crop_type = str(request.get("crop_type") or DEFAULT_CROP_TYPE).strip() or DEFAULT_CROP_TYPE

    if not name:
        return {"created": False, "reason": "missing_name"}
    if len(name) > 60:
        return {"created": False, "reason": "name_too_long"}
    if latitude is None or longitude is None:
        return {"created": False, "reason": "missing_coordinates"}
    if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
        return {"created": False, "reason": "invalid_coordinates"}

    existing = db.query(Farm).filter(Farm.name.ilike(name)).first()
    if existing:
        existing_point = _extract_point_from_polygon(existing.polygon)
        return {
            "created": False,
            "reason": "already_exists",
            "farm": {
                "id": existing.id,
                "name": existing.name,
                "latitude": existing_point.get("latitude", latitude),
                "longitude": existing_point.get("longitude", longitude),
            },
        }

    polygon = _make_square_polygon(latitude, longitude)
    new_farm = Farm(
        user_id=owner_user_id,
        name=name,
        crop_type=crop_type,
        polygon=polygon,
    )
    db.add(new_farm)
    db.commit()
    db.refresh(new_farm)

    region = get_region(latitude, longitude)
    region_profile = REGION_PROFILES.get(region, {}) if region else {}
    regional_recommendations = [str(item).strip() for item in (region_profile.get("preferred_crops") or []) if str(item).strip()][:3]
    regional_risk_factors = [str(item).strip() for item in (region_profile.get("risk_factors") or []) if str(item).strip()]

    return {
        "created": True,
        "farm": {
            "id": new_farm.id,
            "name": new_farm.name,
            "crop_type": new_farm.crop_type,
            "latitude": latitude,
            "longitude": longitude,
            "region": region or "default",
            "regional_recommendations": regional_recommendations,
            "regional_risk_factors": regional_risk_factors,
        },
    }


def _build_crop_farm_profile(
    farm_context: Dict[str, Any],
    weather_payload: Dict[str, Any],
    climate_payload: Dict[str, Any],
) -> Dict[str, Any]:
    current = weather_payload.get("current") if isinstance(weather_payload, dict) else {}
    climate_daily = climate_payload.get("daily_snapshot") if isinstance(climate_payload, dict) else {}

    temperature = _safe_float((current or {}).get("temperature"), _safe_float((climate_daily or {}).get("temperature_c"), 26.0))
    humidity = _safe_float((current or {}).get("humidity"), _safe_float((climate_daily or {}).get("humidity_percent"), 65.0))
    sun_hours = _safe_float((climate_daily or {}).get("sunshine_duration_hours"), 6.0)
    rainfall = _safe_float((weather_payload or {}).get("precipitation_mm"), 0.0)
    coords = _as_dict((farm_context or {}).get("coordinates"))
    latitude = _safe_float(coords.get("latitude"), None)
    longitude = _safe_float(coords.get("longitude"), None)

    return {
        "temperature": temperature if temperature is not None else 26.0,
        "humidity": humidity if humidity is not None else 65.0,
        "sun_hours": sun_hours if sun_hours is not None else 6.0,
        "rainfall": rainfall if rainfall is not None else 0.0,
        "latitude": latitude,
        "longitude": longitude,
        "crop_type": str((farm_context or {}).get("crop_type") or "").strip() or None,
    }


def _build_regional_risk_alerts(region_profile: Dict[str, Any], climate_pattern: str, weather_signals: Dict[str, Any]) -> List[str]:
    alerts: List[str] = []
    risk_factors = [str(item).strip().lower() for item in (region_profile.get("risk_factors") or [])]
    rainfall = _safe_float(weather_signals.get("rainfall"), 0.0) or 0.0

    if "fungal_risk" in risk_factors and climate_pattern == "humid":
        alerts.append("fungal_risk")
    if "flooding" in risk_factors and rainfall >= 12.0:
        alerts.append("flooding")
    if "hurricane" in risk_factors:
        alerts.append("hurricane")

    deduped: List[str] = []
    for alert in alerts:
        if alert not in deduped:
            deduped.append(alert)
    return deduped


def _top_crops_context(
    farm_context: Dict[str, Any],
    weather_payload: Dict[str, Any],
    climate_payload: Dict[str, Any],
    crop_query: Optional[str],
    constraints: Optional[Dict[str, Any]] = None,
    plant_focus_query: Optional[str] = None,
) -> Dict[str, Any]:
    farm_profile = _build_crop_farm_profile(farm_context, weather_payload, climate_payload)
    lat = _safe_float(farm_profile.get("latitude"), None)
    lon = _safe_float(farm_profile.get("longitude"), None)
    region = str((farm_context or {}).get("region") or "").strip() or get_region(lat, lon)
    region_profile = REGION_PROFILES.get(region, {}) if region else {}
    weather_signals = {
        "temperature": _safe_float(farm_profile.get("temperature"), 0.0),
        "humidity": _safe_float(farm_profile.get("humidity"), 0.0),
        "rainfall": _safe_float(farm_profile.get("rainfall"), 0.0),
    }
    climate_pattern = detect_climate_pattern(weather_signals)

    ranked = get_top_crops(farm=farm_profile, query=(crop_query or "fruit"))
    excluded_categories = _normalize_category_list((constraints or {}).get("exclude_categories"))
    filtered_ranked = _apply_category_constraints(ranked, excluded_categories)
    preferred_plant_type = _preferred_plant_type_for_focus(plant_focus_query or crop_query)
    if preferred_plant_type:
        filtered_ranked = [
            dict(item, plant_type=str(item.get("plant_type") or _classify_plant_type(item.get("name"))))
            for item in filtered_ranked
            if str(item.get("plant_type") or _classify_plant_type(item.get("name"))) == preferred_plant_type
        ]
    if excluded_categories:
        ranked = filtered_ranked[: max(1, MAX_CROPS)]
    else:
        ranked = (filtered_ranked or ranked)[: max(1, MAX_CROPS)]

    # Keep rankings empty when external data cannot produce candidates.
    # This prevents synthetic fallback responses and forces data-backed answers.
    best_crop = ranked[0].get("data") if ranked else {}
    preferred_crops = region_profile.get("preferred_crops", []) if isinstance(region_profile, dict) else []
    regional_recommendations = [str(item).strip() for item in preferred_crops if str(item).strip()][:3]
    regional_risk_alerts = _build_regional_risk_alerts(
        region_profile=region_profile if isinstance(region_profile, dict) else {},
        climate_pattern=climate_pattern,
        weather_signals=weather_signals,
    )

    return {
        "farm_profile": farm_profile,
        "top_crops": ranked,
        "recommended_inputs": map_products(best_crop) if isinstance(best_crop, dict) else [],
        "excluded_categories": excluded_categories,
        "plant_focus_query": plant_focus_query,
        "preferred_plant_type": preferred_plant_type,
        "region": region,
        "region_profile": region_profile if isinstance(region_profile, dict) else {},
        "climate_pattern": climate_pattern,
        "regional_recommendations": regional_recommendations,
        "regional_risk_alerts": regional_risk_alerts,
    }


def _build_realtime_context(
    question: str,
    coordinates: Dict[str, float],
    crop_query: Optional[str] = None,
    farm_context: Optional[Dict[str, Any]] = None,
    constraints: Optional[Dict[str, Any]] = None,
    plant_focus_query: Optional[str] = None,
) -> Dict[str, Any]:
    latitude = _safe_float(coordinates.get("latitude"), None)
    longitude = _safe_float(coordinates.get("longitude"), None)
    if latitude is None or longitude is None:
        excluded_categories = _normalize_category_list((constraints or {}).get("exclude_categories"))
        crop_knowledge = fetch_crop_knowledge_bundle(crop_query=crop_query, limit=5) if crop_query else {
            "sources": {},
            "crop_knowledge": {"available": False, "crop_query": None},
            "availability": {"available_count": 0, "total_sources": 2},
        }
        return {
            "available": False,
            "reason": "missing_coordinates",
            "excluded_categories": excluded_categories,
            "external_sources": crop_knowledge,
        }

    import concurrent.futures as _cf
    with _cf.ThreadPoolExecutor(max_workers=3) as _pool:
        _f_weather = _pool.submit(get_weather, latitude=latitude, longitude=longitude)
        _f_climate = _pool.submit(get_climate_report, latitude=latitude, longitude=longitude)
        _f_ext = _pool.submit(fetch_external_sources_bundle, latitude=latitude, longitude=longitude, crop_query=crop_query)
        try:
            weather_payload = _f_weather.result(timeout=12)
        except Exception:
            weather_payload = {}
        try:
            climate_payload = _f_climate.result(timeout=12)
        except Exception:
            climate_payload = {}
        try:
            external_sources = _f_ext.result(timeout=12)
        except Exception:
            external_sources = {}
    crop_ranking = _top_crops_context(
        farm_context=farm_context or {},
        weather_payload=weather_payload,
        climate_payload=climate_payload,
        crop_query=crop_query,
        constraints=constraints or {},
        plant_focus_query=plant_focus_query,
    )
    issue = _derive_issue_from_question(question, weather_payload, climate_payload)
    dynamic_flower_recommendation = _build_dynamic_flower_recommendation(
        plant_focus_query=crop_ranking.get("plant_focus_query"),
        preferred_plant_type=crop_ranking.get("preferred_plant_type"),
        external_sources=external_sources,
        weather_payload=weather_payload,
        climate_payload=climate_payload,
        regional_risk_alerts=crop_ranking.get("regional_risk_alerts", []),
    )
    products = get_product_recommendations(issue)
    stores = find_nearby_stores(latitude, longitude, radius_km=80)
    guidelines = get_procurement_guidelines()

    usda_query = crop_query or crop_ranking.get("plant_focus_query")
    if not usda_query:
        top_crops = crop_ranking.get("top_crops") or []
        if top_crops:
            usda_query = str((top_crops[0] or {}).get("name") or "").strip() or None
    usda_data = get_crop_data(usda_query or "", state="")

    return {
        "available": True,
        "coordinates": {
            "latitude": latitude,
            "longitude": longitude,
        },
        "derived_issue": issue,
        "weather": weather_payload,
        "climate_report": climate_payload,
        "farm_profile": crop_ranking.get("farm_profile", {}),
        "top_crop_recommendations": crop_ranking.get("top_crops", []),
        "recommended_inputs": crop_ranking.get("recommended_inputs", []),
        "region": crop_ranking.get("region", "default"),
        "region_profile": crop_ranking.get("region_profile", {}),
        "climate_pattern": crop_ranking.get("climate_pattern", "normal"),
        "regional_recommendations": crop_ranking.get("regional_recommendations", []),
        "regional_risk_alerts": crop_ranking.get("regional_risk_alerts", []),
        "excluded_categories": crop_ranking.get("excluded_categories", []),
        "plant_focus_query": crop_ranking.get("plant_focus_query"),
        "preferred_plant_type": crop_ranking.get("preferred_plant_type"),
        "dynamic_flower_recommendation": dynamic_flower_recommendation,
        "external_sources": external_sources,
        "usda_crop_data": usda_data,
        "product_recommendations": products,
        "nearby_stores": stores[:8],
        "guidelines": guidelines,
        "products_formatted": format_products_for_ai(products),
        "stores_formatted": format_stores_for_ai(stores),
    }


def _format_farm_summary(farm_context: Dict[str, Any]) -> str:
    if not farm_context or farm_context.get("warning"):
        return ""
    lines: List[str] = []
    name = farm_context.get("farm_name")
    crop = farm_context.get("crop_type")
    if name:
        lines.append(f"Farm: {name}")
    if crop and str(crop).lower() not in ("not specified", ""):
        lines.append(f"Crop: {crop}")
    coords = farm_context.get("coordinates") or {}
    if coords.get("latitude") and coords.get("longitude"):
        lines.append(f"Location: {coords['latitude']:.4f}, {coords['longitude']:.4f}")
    soil = farm_context.get("soil_profile") or {}
    topsoil = _as_dict(soil.get("topsoil_metrics"))
    if topsoil:
        parts = []
        if topsoil.get("ph"):
            parts.append(f"pH {topsoil['ph']}")
        if topsoil.get("organic_carbon"):
            parts.append(f"OC {topsoil['organic_carbon']}")
        if topsoil.get("clay"):
            parts.append(f"clay {topsoil['clay']}%")
        if parts:
            lines.append("Soil: " + ", ".join(parts))
    recent_yields = farm_context.get("recent_yields") or []
    if recent_yields:
        last = recent_yields[0]
        est = last.get("yield_estimate")
        date = str(last.get("date") or "")[:10]
        if est:
            lines.append(f"Last yield: {est} (recorded {date})" if date else f"Last yield: {est}")
    recent_ndvi = farm_context.get("recent_ndvi") or []
    if recent_ndvi:
        stats = _as_dict((recent_ndvi[0] or {}).get("ndvi_stats"))
        mean = stats.get("mean") or stats.get("avg")
        date = str((recent_ndvi[0] or {}).get("date") or "")[:10]
        if mean is not None:
            lines.append(f"Latest NDVI: {mean:.2f} ({date})" if date else f"Latest NDVI: {mean:.2f}")
    return "\n".join(lines)


def _format_weather_summary(realtime_context: Dict[str, Any]) -> str:
    if not isinstance(realtime_context, dict) or not realtime_context.get("available"):
        return ""
    lines: List[str] = []
    weather = _as_dict(realtime_context.get("weather"))
    current = _as_dict(weather.get("current"))
    climate = _as_dict(realtime_context.get("climate_report"))
    daily = _as_dict(climate.get("daily_snapshot"))
    impacts = _as_dict(climate.get("climate_impact_indicators"))

    temp = current.get("temperature") or daily.get("temperature_c")
    humidity = current.get("humidity") or daily.get("humidity_percent")
    wind = current.get("wind_kph")
    precip = weather.get("precipitation_mm")
    condition = current.get("condition") or current.get("description")
    uv = daily.get("uv_index")
    anomaly = impacts.get("temperature_anomaly_vs_historical_month_c")

    if temp is not None:
        lines.append(f"Temperature: {temp}°C")
    if humidity is not None:
        lines.append(f"Humidity: {humidity}%")
    if wind is not None:
        lines.append(f"Wind: {wind} kph")
    if precip is not None:
        lines.append(f"Precipitation: {precip} mm")
    if condition:
        lines.append(f"Condition: {condition}")
    if uv is not None and float(uv) >= 6:
        lines.append(f"UV index: {uv} (elevated)")
    if anomaly is not None:
        a = float(anomaly)
        if a > 1:
            lines.append(f"Temp is {a:.1f}°C above the seasonal baseline — heat stress risk.")
        elif a < -1:
            lines.append(f"Temp is {abs(a):.1f}°C below the seasonal baseline — cold stress risk.")
    return "\n".join(lines)


def _format_region_summary(realtime_context: Dict[str, Any]) -> str:
    if not isinstance(realtime_context, dict) or not realtime_context.get("available"):
        return ""

    region = str(realtime_context.get("region") or "default").strip()
    profile = _as_dict(realtime_context.get("region_profile"))
    preferred = [str(item).strip() for item in (profile.get("preferred_crops") or []) if str(item).strip()]
    climate_pattern = str(realtime_context.get("climate_pattern") or "normal").strip()
    risks = [str(item).strip() for item in (realtime_context.get("regional_risk_alerts") or []) if str(item).strip()]

    lines: List[str] = [f"Region type: {region}"]
    if preferred:
        lines.append("Preferred crops in this region: " + ", ".join(preferred))
    if climate_pattern:
        lines.append(f"Current climate pattern: {climate_pattern}")
    if risks:
        lines.append("Regional risk factors to watch: " + ", ".join(risks))
    return "\n".join(lines)


def _format_external_sources_summary(realtime_context: Dict[str, Any]) -> str:
    if not isinstance(realtime_context, dict) or not realtime_context.get("available"):
        return ""

    external = _as_dict(realtime_context.get("external_sources"))
    availability = _as_dict(external.get("availability"))
    sources = _as_dict(external.get("sources"))

    lines: List[str] = []
    available_count = int(_safe_float(availability.get("available_count"), 0) or 0)
    total_sources = int(_safe_float(availability.get("total_sources"), 0) or 0)
    if total_sources > 0:
        lines.append(f"External endpoint availability: {available_count}/{total_sources} sources available")

    for key in ["perenual", "trefle", "nasa", "noaa", "esa"]:
        src = _as_dict(sources.get(key))
        if not src:
            continue
        status = "available" if src.get("available") else "unavailable"
        detail = str(src.get("error") or "").strip()
        if detail:
            lines.append(f"- {key}: {status} ({detail})")
        else:
            lines.append(f"- {key}: {status}")
    return "\n".join(lines)


def _format_top_crops_and_inputs(realtime_context: Dict[str, Any]) -> str:
    if not isinstance(realtime_context, dict) or not realtime_context.get("available"):
        return ""

    top_crops = realtime_context.get("top_crop_recommendations")
    recommended_inputs = realtime_context.get("recommended_inputs")
    if not isinstance(top_crops, list) or not top_crops:
        return ""

    lines: List[str] = ["Top crop recommendations:"]
    for crop in top_crops[: max(1, MAX_CROPS)]:
        if not isinstance(crop, dict):
            continue
        name = str(crop.get("name") or "Unknown crop").strip()
        score = int(_safe_float(crop.get("score"), 0) or 0)
        reason = str(crop.get("reason") or "").strip()
        if reason:
            lines.append(f"- {name} ({score}% suitability): {reason}")
        else:
            lines.append(f"- {name} ({score}% suitability)")

    if isinstance(recommended_inputs, list) and recommended_inputs:
        lines.append("")
        lines.append("Recommended inputs:")
        for product in recommended_inputs[:5]:
            if isinstance(product, dict):
                name = str(product.get("name") or "Input").strip()
                reason = str(product.get("reason") or "").strip()
                timing = str(product.get("timing") or "").strip()
                if reason and timing:
                    lines.append(f"- {name}: {reason}; timing: {timing}")
                elif reason:
                    lines.append(f"- {name}: {reason}")
                else:
                    lines.append(f"- {name}")
            else:
                item = str(product).strip()
                if item:
                    lines.append(f"- {item}")

    return "\n".join(lines)


def _format_rag_snippets(rag_context: Dict[str, Any]) -> str:
    results = (rag_context or {}).get("results") or []
    snippets: List[str] = []
    for item in results[: max(1, MAX_RAG)]:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or item.get("text") or "").strip()
        if content:
            snippets.append(content[:300])
    return "\n---\n".join(snippets)


_PRODUCT_INTENTS = {"crop_protection", "soil_and_fertility", "irrigation_and_water", "planting_and_siting"}


def _format_products_if_relevant(intent: str, realtime_context: Dict[str, Any]) -> str:
    if intent not in _PRODUCT_INTENTS:
        return ""
    lines: List[str] = []
    products = _as_dict((realtime_context or {}).get("product_recommendations"))
    for category, items in products.items():
        if not isinstance(items, list):
            continue
        for item in items[:2]:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            use_for = (item.get("use_for") or [])
            use_text = f" — for {use_for[0]}" if isinstance(use_for, list) and use_for else ""
            if name:
                lines.append(f"- {name} ({category}){use_text}")
    stores = (realtime_context or {}).get("nearby_stores") or []
    store_names = [s.get("name") for s in stores[:3] if isinstance(s, dict) and s.get("name")]
    if store_names:
        lines.append("Nearby suppliers: " + ", ".join(store_names))
    return "\n".join(lines)


def _format_action_notice(action_results: Dict[str, Any]) -> str:
    create = _as_dict((action_results or {}).get("create_farm"))
    if create.get("created"):
        farm = _as_dict(create.get("farm"))
        return f"Farm '{farm.get('name', 'Unnamed')}' was just created and is ready."
    if create.get("reason") == "already_exists":
        farm = _as_dict(create.get("farm"))
        return f"Farm '{farm.get('name', 'Unnamed')}' already exists — using that record."
    return ""


def _format_conversation_history(
    history: list[Dict[str, str]],
    summary: str,
    max_turns: Optional[int] = None,
) -> str:
    parts: List[str] = []
    if summary:
        parts.append(f"[Earlier context] {summary}")
    limit = max_turns if max_turns is not None else max(1, MAX_HISTORY)
    for item in history[-limit:]:
        role = str(item.get("role") or "").capitalize()
        content = str(item.get("content") or "").strip()[:400]
        if role and content:
            parts.append(f"{role}: {content}")
    return "\n".join(parts)


def _format_analysis_summary(professional_analysis: Dict[str, Any]) -> str:
    analysis = professional_analysis if isinstance(professional_analysis, dict) else {}
    constraints = _as_dict(analysis.get("constraints"))
    plant_focus_query = str(analysis.get("plant_focus_query") or "").strip()
    excluded = [str(item).strip() for item in (constraints.get("exclude_categories") or []) if str(item).strip()]
    risk = _as_dict(analysis.get("risk_profile"))
    drivers = [str(item).strip() for item in (risk.get("drivers") or []) if str(item).strip()]
    timeline = _as_dict(risk.get("timeline_impact"))
    day_impact = [str(item).strip() for item in (timeline.get("day_1_3") or []) if str(item).strip()]
    seasonal_notes = [str(item).strip() for item in (risk.get("seasonal_notes") or []) if str(item).strip()]

    lines: List[str] = []
    if plant_focus_query:
        lines.append(f"Active plant focus: {plant_focus_query}")
    if excluded:
        lines.append("User exclusions: " + ", ".join(excluded))

    risk_percent = _safe_float(risk.get("risk_percent"), None)
    risk_level = str(risk.get("risk_level") or "").strip()
    if risk_percent is not None:
        lines.append(f"Germination risk: {int(risk_percent)}% ({risk_level or 'moderate'})")

    if drivers:
        lines.append("Risk drivers:")
        for item in drivers[:4]:
            lines.append(f"- {item}")

    if day_impact:
        lines.append("Day 1-3 forecast impact:")
        for item in day_impact[:3]:
            lines.append(f"- {item}")

    if seasonal_notes:
        lines.append("Seasonal notes:")
        for item in seasonal_notes[:2]:
            lines.append(f"- {item}")

    return "\n".join(lines)


def _build_prompt(
    question: str,
    farm_context: Dict[str, Any],
    realtime_context: Dict[str, Any],
    action_results: Dict[str, Any],
    rag_context: Dict[str, Any],
    professional_analysis: Dict[str, Any],
    conversation_history: list[Dict[str, str]],
    conversation_summary: str,
    image_turn: bool = False,
) -> str:
    intent = str((professional_analysis or {}).get("intent") or "")

    farm_summary = _format_farm_summary(farm_context)
    weather_summary = _format_weather_summary(realtime_context)
    region_summary = _format_region_summary(realtime_context)
    top_crops_text = _format_top_crops_and_inputs(realtime_context)
    dynamic_flower_text = _format_dynamic_flower_recommendation(realtime_context)
    external_sources_text = _format_external_sources_summary(realtime_context)
    usda_crop_data = _as_dict(realtime_context.get("usda_crop_data"))
    rag_snippets = _format_rag_snippets(rag_context)
    product_text = _format_products_if_relevant(intent, realtime_context)
    action_notice = _format_action_notice(action_results)
    # For image turns, only include the last 2 history turns to avoid prompt bloat
    # and prevent old image analyses from biasing the fresh image analysis.
    history_text = _format_conversation_history(
        conversation_history,
        conversation_summary,
        max_turns=2 if image_turn else None,
    )
    analysis_text = _format_analysis_summary(professional_analysis)

    sections: List[str] = []
    if farm_summary:
        sections.append(f"Farm info:\n{farm_summary}")
    if weather_summary:
        sections.append(f"Current conditions:\n{weather_summary}")
    if region_summary:
        sections.append(region_summary)
    if dynamic_flower_text:
        sections.append(dynamic_flower_text)
    if top_crops_text:
        sections.append(top_crops_text)
    if external_sources_text:
        sections.append(f"External source status:\n{external_sources_text}")
        # Do not fabricate fallback crops when ranking is empty.
        # Keep an empty ranking so downstream response logic uses live external-source records instead.
    if usda_crop_data:
        usda_available = bool(usda_crop_data.get("available"))
        usda_count = int(_safe_float(usda_crop_data.get("count"), 0) or 0)
        if usda_available:
            sections.append(
                "USDA Crop Insights:\n"
                f"- Data points available: {usda_count}\n"
                "- Recent yield trends included\n"
                "- Use this to validate crop suitability and performance"
            )
        else:
            usda_error = str(usda_crop_data.get("error") or "Unavailable")
            sections.append(f"USDA Crop Insights:\n- Data unavailable: {usda_error}")
    if rag_snippets:
        sections.append(f"Relevant knowledge:\n{rag_snippets}")
    if product_text:
        sections.append(f"Available products / suppliers:\n{product_text}")
    if analysis_text:
        sections.append(f"Risk and constraints:\n{analysis_text}")
    if action_notice:
        sections.append(f"Recent action: {action_notice}")
    if history_text:
        sections.append(f"Conversation so far:\n{history_text}")

    context_block = "\n\n".join(sections) if sections else "No specific farm data provided."

    return (
        f"{SYSTEM_PROMPT.strip()}\n\n"
        "Priority directive:\n"
        "- If Top crop recommendations are present in context, use them as the primary recommendation in your answer.\n"
        "- Keep crop ranking consistent with provided suitability scores.\n"
        "- Always provide at least one concrete recommendation, even when context is partial.\n"
        "- If the user asks for a planting recommendation and a top crop is available, give the planting method for the top-ranked crop, including seeding or transplant guidance, depth, spacing, and first watering.\n"
        "- If the current focus is flowers or ornamentals, stay within flower or ornamental recommendations and do not switch to generic irrigation-only advice.\n\n"
        f"---\n\n"
        f"{context_block}\n\n"
        f"---\n\n"
        f"Question: {question}\n\n"
        "Answer:"
    )


def _build_rag_context(db: Session, question: str, farm_id: Optional[int]) -> Dict[str, Any]:
    try:
        result = query_index(
            db=db,
            question=question,
            farm_id=farm_id,
            top_k=max(1, MAX_RAG),
            min_score=0.08,
        )
        return {
            "available": bool(result.get("results")),
            "results": result.get("results", []),
            "used_documents": result.get("used_documents", 0),
            "index_updated_at": result.get("index_updated_at"),
            "warning": result.get("warning"),
        }
    except Exception as exc:
        return {
            "available": False,
            "results": [],
            "used_documents": 0,
            "warning": f"rag_unavailable: {exc}",
        }


@router.post("/chat", responses={502: {"description": "Cloud AI provider error"}, 503: {"description": "Cloud AI not configured"}})
def cloud_ai_chat(
    body: CloudAIChatRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Dict[str, Any]:
    # 1) User message -> detect intent
    question = (body.question or "").strip()
    # Prepend type-specific image context so the model knows what to analyze
    if body.image_base64:
        question = (
            _build_image_context_prefix(body.attachment_type, {}, {})
            + question
        )
    detected_intent = _infer_intent(question)

    # 2) Get user memory
    incoming_context = body.context or {}
    effective_incoming_context = dict(incoming_context) if isinstance(incoming_context, dict) else {}
    effective_incoming_context["user_id"] = current_user.id
    memory = _load_user_memory(body.farm_id, effective_incoming_context, current_user)
    conversation_key = str(memory["conversation_key"])
    conversation_history = memory["conversation_history"]
    conversation_summary = str(memory["conversation_summary"])
    conversation_meta = memory["conversation_meta"]

    # 3) Add farm + crop context
    common = _build_common_payload(body, db, current_user)
    farm_context = common["farm_context"]
    app_context = common["app_context"]
    plant_focus_query = str(common.get("plant_focus_query") or "").strip() or None
    constraints = common.get("constraints", {})
    excluded_categories = _normalize_category_list((constraints or {}).get("exclude_categories"))
    action_results = common["action_results"]
    realtime_context = common["realtime_context"]
    app_context, realtime_context = _with_memory_crop_context(
        question=question,
        farm_context=farm_context,
        app_context=app_context,
        realtime_context=realtime_context,
        conversation_meta=conversation_meta,
        conversation_history=conversation_history,
    )

    # Now that we have farm + realtime context, rebuild the image prefix with real data
    if body.image_base64:
        base_question = (body.question or "").strip()
        question = (
            _build_image_context_prefix(body.attachment_type, farm_context, realtime_context)
            + base_question
        )

    if _needs_vague_category_clarification(question):
        last_recommended_crop = str((((realtime_context or {}).get("top_crop_recommendations") or [{}])[0] or {}).get("name") or "").strip() or None
        clarify_answer = _build_clarification_response(excluded_categories)
        clarify_answer = _finalize_conversation(
            conversation_key=conversation_key,
            question=question,
            answer=clarify_answer,
            crop_query=str((app_context or {}).get("crop_type") or "").strip() or None,
            intent="clarification_required",
            excluded_categories=excluded_categories,
            plant_focus_query=plant_focus_query,
            last_recommended_crop=last_recommended_crop,
        )
        clarification_analysis = {
            "intent": "clarification_required",
            "confidence": "medium",
            "constraints": {"exclude_categories": excluded_categories},
            "risk_profile": _compute_risk_profile(realtime_context, farm_context),
            "follow_up_questions": [
                "Do you mean ornamental plants, shade trees, or non-edible cover crops?",
            ],
        }
        return _build_response_payload(
            answer=clarify_answer,
            provider="local-clarifier",
            model="rule-based-clarification",
            action_results=action_results,
            realtime_context=realtime_context,
            rag_context={},
            professional_analysis=clarification_analysis,
        )

    authorized_farm_id = body.farm_id if (farm_context or {}).get("farm_id") else None
    rag_context = _build_rag_context(db=db, question=question, farm_id=authorized_farm_id)
    professional_analysis = _build_professional_analysis(
        question=question,
        farm_context=farm_context,
        app_context=app_context,
        realtime_context=realtime_context,
        rag_context=rag_context,
        detected_intent=detected_intent,
    )
    last_recommended_crop = str((((realtime_context or {}).get("top_crop_recommendations") or [{}])[0] or {}).get("name") or "").strip() or None

    # Compute once — used across all paths (Gemini, fallback, no-key)
    is_image_turn = bool(body.image_base64)
    stored_user_message: Optional[str] = None
    if is_image_turn:
        base_q = (body.question or "").strip()
        atype = str(body.attachment_type or "image").strip().lower()
        stored_user_message = f"[Uploaded {atype} image] {base_q}" if base_q else f"[Uploaded {atype} image]"

    if not GEMINI_API_KEY:
        answer = _build_local_crop_response(realtime_context=realtime_context)
        answer = _finalize_conversation(
            conversation_key=conversation_key,
            question=question,
            answer=answer,
            crop_query=str((app_context or {}).get("crop_type") or "").strip() or None,
            intent=str((professional_analysis or {}).get("intent") or ""),
            excluded_categories=excluded_categories,
            plant_focus_query=plant_focus_query,
            last_recommended_crop=last_recommended_crop,
            stored_user_message=stored_user_message,
        )
        return _build_response_payload(
            answer=answer,
            provider="local-crop-engine",
            model="rule-based-fallback",
            action_results=action_results,
            realtime_context=realtime_context,
            rag_context=rag_context,
            professional_analysis=professional_analysis,
            warning="Gemini API key missing, using local crop intelligence fallback",
        )

    prompt = _build_prompt(
        question,
        farm_context,
        realtime_context,
        action_results,
        rag_context,
        professional_analysis,
        conversation_history,
        conversation_summary,
        image_turn=is_image_turn,
    )

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
        f"?key={GEMINI_API_KEY}"
    )

    # Build content parts — add image inlineData when provided
    parts: list = []
    if is_image_turn:
        parts.append({
            "inlineData": {
                "mimeType": body.image_mime_type or "image/jpeg",
                "data": body.image_base64,
            }
        })
    parts.append({"text": prompt})

    # Image requests need a longer timeout and more output tokens
    request_timeout = max(GEMINI_TIMEOUT_SECONDS, 55) if is_image_turn else GEMINI_TIMEOUT_SECONDS
    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 1000 if is_image_turn else 650,
        },
    }

    try:
        response = requests.post(url, json=payload, timeout=request_timeout)
    except requests.RequestException as exc:
        fallback_answer = _build_local_crop_response(realtime_context=realtime_context)
        answer = _finalize_conversation(
            conversation_key=conversation_key,
            question=question,
            answer=fallback_answer,
            crop_query=str((app_context or {}).get("crop_type") or "").strip() or None,
            intent=str((professional_analysis or {}).get("intent") or ""),
            excluded_categories=excluded_categories,
            plant_focus_query=plant_focus_query,
            last_recommended_crop=last_recommended_crop,
            stored_user_message=stored_user_message,
        )
        return _build_response_payload(
            answer=answer,
            provider="gemini",
            model=GEMINI_MODEL,
            action_results=action_results,
            realtime_context=realtime_context,
            rag_context=rag_context,
            professional_analysis=professional_analysis,
            warning=f"Cloud AI request failed: {exc}",
        )

    if response.status_code == 429:
        fallback_answer = _build_local_crop_response(realtime_context=realtime_context)
        answer = _finalize_conversation(
            conversation_key=conversation_key,
            question=question,
            answer=fallback_answer,
            crop_query=str((app_context or {}).get("crop_type") or "").strip() or None,
            intent=str((professional_analysis or {}).get("intent") or ""),
            excluded_categories=excluded_categories,
            plant_focus_query=plant_focus_query,
            last_recommended_crop=last_recommended_crop,
            stored_user_message=stored_user_message,
        )
        return _build_response_payload(
            answer=answer,
            provider="gemini",
            model=GEMINI_MODEL,
            action_results=action_results,
            realtime_context=realtime_context,
            rag_context=rag_context,
            professional_analysis=professional_analysis,
            warning="Gemini quota exceeded or billing is not enabled for this API key",
        )

    if not response.ok:
        fallback_answer = _build_local_crop_response(realtime_context=realtime_context)
        answer = _finalize_conversation(
            conversation_key=conversation_key,
            question=question,
            answer=fallback_answer,
            crop_query=str((app_context or {}).get("crop_type") or "").strip() or None,
            intent=str((professional_analysis or {}).get("intent") or ""),
            excluded_categories=excluded_categories,
            plant_focus_query=plant_focus_query,
            last_recommended_crop=last_recommended_crop,
            stored_user_message=stored_user_message,
        )
        return _build_response_payload(
            answer=answer,
            provider="gemini",
            model=GEMINI_MODEL,
            action_results=action_results,
            realtime_context=realtime_context,
            rag_context=rag_context,
            professional_analysis=professional_analysis,
            warning=f"Cloud AI error: {response.text[:300]}",
        )

    data = response.json()
    candidates = data.get("candidates") or []
    parts = (((candidates[0] if candidates else {}).get("content") or {}).get("parts") or [])
    answer = "\n".join([p.get("text", "") for p in parts if p.get("text")]).strip()

    if not answer:
        answer = _build_local_crop_response(realtime_context=realtime_context)

    extracted_crop_from_answer = _extract_recommended_crop_from_answer(answer)
    answer = _append_crop_specific_planting_guidance(
        answer=answer,
        question=question,
        remembered_crop=last_recommended_crop or extracted_crop_from_answer,
    )

    answer = _finalize_conversation(
        conversation_key=conversation_key,
        question=question,
        answer=answer,
        crop_query=str((app_context or {}).get("crop_type") or "").strip() or None,
        intent=str((professional_analysis or {}).get("intent") or ""),
        excluded_categories=excluded_categories,
        plant_focus_query=plant_focus_query,
        last_recommended_crop=last_recommended_crop or extracted_crop_from_answer,
        stored_user_message=stored_user_message,
    )

    image_analysis = (
        _parse_structured_image_response(answer, body.attachment_type)
        if body.image_base64 and body.attachment_type
        else None
    )

    return _build_response_payload(
        answer=answer,
        provider="gemini",
        model=GEMINI_MODEL,
        action_results=action_results,
        realtime_context=realtime_context,
        rag_context=rag_context,
        professional_analysis=professional_analysis,
        image_analysis=image_analysis,
    )
