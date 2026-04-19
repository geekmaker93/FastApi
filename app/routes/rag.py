from typing import Annotated, Any, Dict, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.services.rag_store import RAG_INDEX_PATH, ensure_index, load_index, query_index, rebuild_index

router = APIRouter(prefix="/rag", tags=["rag"])


class RAGQueryRequest(BaseModel):
    question: str = Field(..., min_length=2, max_length=3000)
    farm_id: Optional[int] = None
    top_k: int = Field(default=5, ge=1, le=12)
    min_score: float = Field(default=0.08, ge=0.0, le=1.0)


class RAGReindexRequest(BaseModel):
    force: bool = True


@router.get("/status")
def rag_status(db: Annotated[Session, Depends(get_db)]) -> Dict[str, Any]:
    payload = load_index()
    doc_count = len(payload.get("documents", []))

    if doc_count == 0:
        payload = ensure_index(db)
        doc_count = len(payload.get("documents", []))

    return {
        "enabled": True,
        "index_path": str(RAG_INDEX_PATH),
        "document_count": doc_count,
        "updated_at": payload.get("updated_at"),
    }


@router.post("/reindex")
def rag_reindex(body: RAGReindexRequest, db: Annotated[Session, Depends(get_db)]) -> Dict[str, Any]:
    payload = rebuild_index(db) if body.force else ensure_index(db)
    return {
        "ok": True,
        "document_count": len(payload.get("documents", [])),
        "updated_at": payload.get("updated_at"),
        "forced": body.force,
    }


@router.post("/query")
def rag_query(body: RAGQueryRequest, db: Annotated[Session, Depends(get_db)]) -> Dict[str, Any]:
    result = query_index(
        db=db,
        question=body.question,
        farm_id=body.farm_id,
        top_k=body.top_k,
        min_score=body.min_score,
    )
    return {
        "ok": True,
        "question": body.question,
        "farm_id": body.farm_id,
        "results": result.get("results", []),
        "used_documents": result.get("used_documents", 0),
        "index_updated_at": result.get("index_updated_at"),
        "warning": result.get("warning"),
    }
