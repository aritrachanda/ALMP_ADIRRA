"""Business Glossary v2 API (Phase 4a).

Additive, Postgres-direct endpoints for the v2 UI: hierarchy tree + reparent, faceted
full-text search, term history (versions + transitions), the bulk review queue, and the
configurable regulatory-attribute list. These read the repository directly (independent of the
``glossary_backend`` flag) — building the v2 surface does not require the cutover flip.

All handlers are plain ``def`` so FastAPI runs them in a threadpool (the psycopg driver is
synchronous — never block the event loop).
"""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import yaml
from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import StreamingResponse

from core.glossary_db.db import health, session_scope
from core.glossary_db.repository import GlossaryRepository
from api.llm_errors import format_llm_error
from api.sse_utils import format_sse, stream_with_progress

router = APIRouter(prefix="/glossary/v2", tags=["glossary_v2"])

_ROOT = Path(__file__).resolve().parent.parent.parent

# Fields the AI-generate endpoint can draft. Regulatory attributes (crr3/dpm) route through the
# RAG agents; the free-text fields route through the glossary suggestion agent.
_TEXT_GEN_FIELDS = {"business_description", "detailed_description", "synonyms", "tags"}

# Regulatory attributes rendered from configuration (so CRR3/DPM are data, not hardcoded form
# fields). Backed by term_version.attributes JSONB keys. Could move to project.yaml later.
ATTR_CONFIG = [
    {"key": "crr3", "label": "CRR3 interpretation", "attribute": "crr3_context",
     "hint": "regulatory.crr3", "generator": "crr"},
    {"key": "dpm", "label": "DPM 2.0 interpretation", "attribute": "dpm2_context",
     "hint": "regulatory.dpm2", "generator": "dpm"},
]


def _guard() -> None:
    if not health():
        raise HTTPException(
            status_code=503,
            detail=("Glossary database is not running. Start it with: "
                    "docker compose -f db/docker-compose.yml up -d"),
        )


@contextmanager
def _repo():
    with session_scope() as session:
        yield GlossaryRepository(session)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _agent_model() -> str:
    """Configured model name for provenance — read from project.yaml (never hardcoded)."""
    try:
        with (_ROOT / "project.yaml").open(encoding="utf-8") as fh:
            return (yaml.safe_load(fh) or {}).get("agent", {}).get("model", "") or ""
    except OSError:
        return ""


def _rag_query(term_dict: dict) -> str:
    parts = [term_dict.get("title", "")]
    if term_dict.get("synonyms"):
        parts.append(", ".join(term_dict["synonyms"]))
    if term_dict.get("business_description"):
        parts.append(str(term_dict["business_description"]).strip())
    return ". ".join(p for p in parts if p)


def _generate_regulatory(field: str, term_dict: dict) -> tuple[str, str]:
    query = _rag_query(term_dict)
    if field == "crr3":
        from agents.crr_agent import generate_interactive as crr_generate
        result = crr_generate(query) or {}
        return (result.get("CRR_context", "") if isinstance(result, dict) else ""), "crr.context"
    from agents.dpm_agent import generate_interactive as dpm_generate
    result = dpm_generate(query) or {}
    return (result.get("DPM_context", "") if isinstance(result, dict) else ""), "dpm.context"


def _generate_text_field(field: str, term_dict: dict):
    from agents.glossary_agent import GlossaryAgent, GlossaryTerm
    term = GlossaryTerm.from_dict(term_dict)
    suggestion = GlossaryAgent().suggest_term_update(term)
    return suggestion.get(field, ""), f"glossary.suggest.{field}"


@router.get("/tree")
def get_tree():
    _guard()
    with _repo() as repo:
        return repo.tree()


@router.get("/facets")
def get_facets():
    _guard()
    with _repo() as repo:
        return repo.facets()


@router.get("/search")
def search(
    q: str | None = Query(default=None),
    domain: str | None = Query(default=None),
    category: str | None = Query(default=None),
    status: str | None = Query(default=None),
    steward: str | None = Query(default=None),
    has_linkage: bool | None = Query(default=None),
    ai_generated: bool | None = Query(default=None),
):
    _guard()
    with _repo() as repo:
        return repo.faceted_search(q, domain=domain, category=category, status=status,
                                   steward=steward, has_linkage=has_linkage, ai_generated=ai_generated)


@router.get("/terms/{slug}/history")
def get_history(slug: str):
    _guard()
    with _repo() as repo:
        h = repo.history(slug)
    if h is None:
        raise HTTPException(status_code=404, detail=f"Term '{slug}' not found")
    return h


@router.get("/review-queue")
def review_queue():
    _guard()
    with _repo() as repo:
        return repo.review_queue()


@router.patch("/terms/{slug}/assign")
def assign_review(slug: str, body: dict = Body(default={})):
    _guard()
    with _repo() as repo:
        try:
            repo.assign_review(slug, body.get("assignee"))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
    return {"status": "assigned", "assignee": body.get("assignee")}


@router.post("/terms/{slug}/confirm")
def confirm_term(slug: str, body: dict = Body(default={})):
    """Approve a term (v2 review). Postgres-direct, flag-neutral — writes a lifecycle
    transition so the History tab shows the decision trail."""
    _guard()
    with _repo() as repo:
        try:
            return repo.set_status(
                slug, "approved", actor=body.get("decided_by"),
                actor_role=body.get("decided_by_role"), reason=body.get("reason"))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))


@router.post("/terms/{slug}/reject")
def reject_term(slug: str, body: dict = Body(default={})):
    """Reject a term back to draft (v2 review)."""
    _guard()
    with _repo() as repo:
        try:
            return repo.set_status(
                slug, "draft", actor=body.get("decided_by"),
                actor_role=body.get("decided_by_role"), reason=body.get("reason"))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))


@router.put("/terms/{slug}")
def update_term(slug: str, body: dict = Body(...)):
    """Edit a term (v2). Single-version, in-place write (matches v1 semantics); Phase 5 adds
    versioning-on-edit and the revalidation coupling."""
    _guard()
    data = dict(body)
    data["id"] = slug
    with _repo() as repo:
        try:
            return repo.update_term(data)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))


@router.post("/terms/{slug}/generate")
def generate_field(slug: str, body: dict = Body(default={})):
    """Draft a single field with AI and return it plus provenance (model, prompt_id,
    timestamp). Read-only — nothing is persisted until the caller saves via PUT. No
    confidence is reported on generated prose, by design."""
    _guard()
    field = body.get("field")
    if not field:
        raise HTTPException(status_code=400, detail="Body must include 'field'.")
    if field not in _TEXT_GEN_FIELDS and field not in {"crr3", "dpm"}:
        raise HTTPException(status_code=400, detail=f"Unsupported field '{field}'.")
    with _repo() as repo:
        term_dict = repo.get_term(slug)
    if term_dict is None:
        raise HTTPException(status_code=404, detail=f"Term '{slug}' not found")

    provenance = {"model": _agent_model(), "generated_at": _now_iso()}
    try:
        if field in ("crr3", "dpm"):
            value, prompt_id = _generate_regulatory(field, term_dict)
        else:
            value, prompt_id = _generate_text_field(field, term_dict)
    except Exception as exc:  # generation is best-effort — surface, don't 500
        err = format_llm_error(exc)
        return {"field": field, "value": None, "provenance": None,
                "message": err["summary"], "error": err}
    provenance["prompt_id"] = prompt_id
    return {"field": field, "value": value, "provenance": provenance}


@router.patch("/terms/{slug}/parent")
def reparent(slug: str, body: dict = Body(default={})):
    _guard()
    with _repo() as repo:
        try:
            return repo.reparent(slug, body.get("parent"))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))


@router.get("/attributes-config")
def attributes_config():
    return ATTR_CONFIG


@router.get("/coverage")
def coverage():
    return _build_coverage()


@router.post("/coverage/stream")
async def stream_coverage():
    """Same data as GET /coverage, streamed as SSE with real progress checkpoints."""
    loop = asyncio.get_event_loop()

    def work(emit):
        return _build_coverage(emit=emit)

    async def generate():
        async for event, data in stream_with_progress(loop, work):
            yield format_sse(event, data)

    return StreamingResponse(
        generate(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


def _build_coverage(*, emit: Callable[[str, dict], None] = lambda *_a: None) -> dict:
    """Build the glossary coverage payload.

    Same real-checkpoint ``emit`` contract as ``element.py``'s builders (2 stages here):
    ``emit("progress", {"completed": n})`` fires once a whole stage genuinely finishes.
    """
    _guard()
    with _repo() as repo:
        data = repo.coverage()
    emit("progress", {"completed": 1})  # stage 0: coverage tallied

    # denominator (total onboarded source columns) comes from the catalogs, not Postgres
    from core.glossary_db.migrate_from_yaml import _Resolver
    total = _Resolver().total_source_columns()
    linked = data["distinct_linked_source_columns"]
    data["total_source_columns"] = total
    data["column_coverage_pct"] = round(100.0 * linked / total, 1) if total else 0.0
    emit("progress", {"completed": 2})  # stage 1: catalog linkages checked
    return data


@router.get("/terms/{slug}")
def get_term(slug: str):
    _guard()
    with _repo() as repo:
        term = repo.get_term(slug)
    if term is None:
        raise HTTPException(status_code=404, detail=f"Term '{slug}' not found")
    return term


@router.get("/diagnostics/multi-term-columns")
def multi_term_columns():
    _guard()
    with _repo() as repo:
        return {"columns_with_multiple_terms": repo.multi_term_column_count()}
