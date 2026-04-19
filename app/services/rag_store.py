import json
import math
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.db_models import Farm, FarmerYieldReport, HistoricalYieldAverage, YieldResult

BASE_DIR = Path(__file__).resolve().parents[2]
RAG_DATA_DIR = BASE_DIR / "app" / "data"
RAG_INDEX_PATH = RAG_DATA_DIR / "rag_documents.json"

KB_FILES = [
    ("agri_products", BASE_DIR / "app" / "services" / "agri_products_kb.json"),
    ("fertilizer", BASE_DIR / "app" / "services" / "fertilizer_kb.json"),
    ("plant_options", BASE_DIR / "app" / "services" / "plant_options_kb.json"),
    ("agronomy_playbook", BASE_DIR / "app" / "services" / "agronomy_playbook_kb.json"),
]


def _normalize_text(text: str) -> str:
    return " ".join((text or "").strip().split())


def _chunk_text(text: str, chunk_size: int = 700, overlap: int = 120) -> List[str]:
    cleaned = _normalize_text(text)
    if not cleaned:
        return []
    if len(cleaned) <= chunk_size:
        return [cleaned]

    chunks: List[str] = []
    start = 0
    length = len(cleaned)
    while start < length:
        end = min(start + chunk_size, length)
        chunk = cleaned[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= length:
            break
        start = max(end - overlap, 0)
    return chunks


def _make_doc(text: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "text": text,
        "metadata": metadata,
    }


def _load_kb_documents() -> List[Dict[str, Any]]:
    documents: List[Dict[str, Any]] = []
    skip_top_level_keys = {"schema_version", "search_aliases"}

    for source_type, kb_path in KB_FILES:
        if not kb_path.exists():
            continue

        try:
            with kb_path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except Exception:
            continue

        if isinstance(payload, dict):
            iterable = [
                {"key": key, "value": value}
                for key, value in payload.items()
                if key not in skip_top_level_keys
            ]
        elif isinstance(payload, list):
            iterable = payload
        else:
            iterable = []

        for idx, item in enumerate(iterable):
            if isinstance(item, dict) and "key" in item and "value" in item:
                topic = str(item.get("key") or "general")
                value = item.get("value")
                text = f"Topic: {topic}. Content: {json.dumps(value, ensure_ascii=True)}"
            else:
                text = json.dumps(item, ensure_ascii=True)
            chunks = _chunk_text(text)
            for chunk_idx, chunk in enumerate(chunks):
                documents.append(
                    _make_doc(
                        text=chunk,
                        metadata={
                            "source_type": source_type,
                            "title": f"{source_type}-kb-{idx}",
                            "farm_id": None,
                            "chunk": chunk_idx,
                        },
                    )
                )

    return documents


def _load_farm_documents(db: Session) -> List[Dict[str, Any]]:
    documents: List[Dict[str, Any]] = []

    farms = db.query(Farm).limit(300).all()
    for farm in farms:
        text = (
            f"Farm profile: id={farm.id}, name={farm.name}, crop_type={farm.crop_type}. "
            f"Boundary polygon={farm.polygon}."
        )
        for chunk_idx, chunk in enumerate(_chunk_text(text)):
            documents.append(
                _make_doc(
                    text=chunk,
                    metadata={
                        "source_type": "farm_profile",
                        "title": f"farm-{farm.id}-profile",
                        "farm_id": farm.id,
                        "chunk": chunk_idx,
                    },
                )
            )

    recent_yields = db.query(YieldResult).order_by(YieldResult.date.desc()).limit(800).all()
    for row in recent_yields:
        text = (
            f"Yield estimate record for farm_id={row.farm_id} on date={row.date}: "
            f"yield_estimate={row.yield_estimate}, notes={row.notes}."
        )
        for chunk_idx, chunk in enumerate(_chunk_text(text)):
            documents.append(
                _make_doc(
                    text=chunk,
                    metadata={
                        "source_type": "yield_estimate",
                        "title": f"yield-{row.id}",
                        "farm_id": row.farm_id,
                        "chunk": chunk_idx,
                    },
                )
            )

    reports = db.query(FarmerYieldReport).order_by(FarmerYieldReport.date.desc()).limit(800).all()
    for row in reports:
        text = (
            f"Farmer report for farm_id={row.farm_id} on date={row.date}: "
            f"actual_yield={row.actual_yield}, notes={row.notes}."
        )
        for chunk_idx, chunk in enumerate(_chunk_text(text)):
            documents.append(
                _make_doc(
                    text=chunk,
                    metadata={
                        "source_type": "farmer_report",
                        "title": f"farmer-report-{row.id}",
                        "farm_id": row.farm_id,
                        "chunk": chunk_idx,
                    },
                )
            )

    historical = db.query(HistoricalYieldAverage).order_by(HistoricalYieldAverage.year.desc()).limit(800).all()
    for row in historical:
        text = (
            f"Historical average for farm_id={row.farm_id}, crop_type={row.crop_type}, year={row.year}: "
            f"avg={row.avg_yield}, min={row.min_yield}, max={row.max_yield}, samples={row.sample_count}."
        )
        for chunk_idx, chunk in enumerate(_chunk_text(text)):
            documents.append(
                _make_doc(
                    text=chunk,
                    metadata={
                        "source_type": "historical_yield",
                        "title": f"historical-{row.id}",
                        "farm_id": row.farm_id,
                        "chunk": chunk_idx,
                    },
                )
            )

    return documents


def load_index() -> Dict[str, Any]:
    if not RAG_INDEX_PATH.exists():
        return {"updated_at": None, "documents": []}

    try:
        with RAG_INDEX_PATH.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception:
        return {"updated_at": None, "documents": []}

    docs = payload.get("documents") if isinstance(payload, dict) else []
    if not isinstance(docs, list):
        docs = []

    return {
        "updated_at": payload.get("updated_at") if isinstance(payload, dict) else None,
        "documents": docs,
    }


def save_index(documents: List[Dict[str, Any]]) -> Dict[str, Any]:
    RAG_DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "documents": documents,
    }
    with RAG_INDEX_PATH.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2)
    return payload


def rebuild_index(db: Session) -> Dict[str, Any]:
    kb_docs = _load_kb_documents()
    farm_docs = _load_farm_documents(db)
    payload = save_index(kb_docs + farm_docs)
    payload["document_count"] = len(payload.get("documents", []))
    return payload


def ensure_index(db: Session) -> Dict[str, Any]:
    payload = load_index()
    if payload.get("documents"):
        return payload
    return rebuild_index(db)


def _empty_query_result(updated_at: Optional[str], warning: str) -> Dict[str, Any]:
    return {
        "results": [],
        "used_documents": 0,
        "index_updated_at": updated_at,
        "warning": warning,
    }


def _filter_documents_by_farm(documents: List[Dict[str, Any]], farm_id: Optional[int]) -> List[Dict[str, Any]]:
    if farm_id is None:
        return documents

    filtered_docs: List[Dict[str, Any]] = []
    for doc in documents:
        meta = doc.get("metadata", {}) if isinstance(doc, dict) else {}
        doc_farm_id = meta.get("farm_id")
        if doc_farm_id is None or doc_farm_id == farm_id:
            filtered_docs.append(doc)
    return filtered_docs or documents


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def _compute_similarity_scores(question: str, documents: List[Dict[str, Any]]) -> List[float]:
    query_tokens = _tokenize(question)
    if not query_tokens:
        return [0.0 for _ in documents]

    token_doc_freq: Dict[str, int] = {}
    doc_tokens_list: List[List[str]] = []

    for doc in documents:
        tokens = _tokenize(str(doc.get("text", "")))
        doc_tokens_list.append(tokens)
        for token in set(tokens):
            token_doc_freq[token] = token_doc_freq.get(token, 0) + 1

    doc_count = max(len(documents), 1)
    scores: List[float] = []
    for tokens in doc_tokens_list:
        if not tokens:
            scores.append(0.0)
            continue

        token_count: Dict[str, int] = {}
        for token in tokens:
            token_count[token] = token_count.get(token, 0) + 1

        score = 0.0
        for query_token in query_tokens:
            tf = token_count.get(query_token, 0)
            if tf <= 0:
                continue
            df = token_doc_freq.get(query_token, 1)
            idf = math.log(1.0 + (doc_count / max(1, df)))
            score += (1.0 + math.log(tf)) * idf

        # Normalize to avoid very long snippets dominating retrieval.
        score /= math.sqrt(len(tokens))
        scores.append(score)

    return scores


def _build_ranked_results(
    documents: List[Dict[str, Any]],
    similarity_scores: List[float],
    top_k: int,
    min_score: float,
) -> List[Dict[str, Any]]:
    ranked = sorted(enumerate(similarity_scores), key=lambda row: row[1], reverse=True)
    results: List[Dict[str, Any]] = []

    for idx, score in ranked:
        if len(results) >= max(1, top_k):
            break
        if float(score) < min_score:
            continue

        doc = documents[idx]
        text = str(doc.get("text", "")).strip()
        metadata = doc.get("metadata", {}) if isinstance(doc, dict) else {}
        results.append(
            {
                "id": doc.get("id"),
                "score": round(float(score), 4),
                "snippet": text[:420],
                "metadata": {
                    "title": metadata.get("title"),
                    "source_type": metadata.get("source_type"),
                    "farm_id": metadata.get("farm_id"),
                },
            }
        )
    return results


def query_index(
    db: Session,
    question: str,
    farm_id: Optional[int] = None,
    top_k: int = 5,
    min_score: float = 0.08,
) -> Dict[str, Any]:
    payload = ensure_index(db)
    documents = payload.get("documents", [])
    updated_at = payload.get("updated_at")

    if not question or not documents:
        return _empty_query_result(updated_at, "empty_question_or_index")

    filtered_docs = _filter_documents_by_farm(documents, farm_id)
    similarity_scores = _compute_similarity_scores(question, filtered_docs)

    results = _build_ranked_results(filtered_docs, similarity_scores, top_k, min_score)

    return {
        "results": results,
        "used_documents": len(filtered_docs),
        "index_updated_at": updated_at,
        "warning": None,
    }
