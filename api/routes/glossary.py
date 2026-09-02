"""Glossary API routes."""
from __future__ import annotations

import sys
from pathlib import Path

import yaml
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from api.deps import get_audit_store
from api.schemas.glossary import GlossaryTermSchema
from core.audit import AuditStore
from core.audit import events as audit_events

router = APIRouter(prefix="/glossary", tags=["glossary"])

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _agent():
    from agents.glossary_agent import GlossaryAgent
    from core.glossary_db.db import backend
    from core.shared.db_availability import require_reachable
    # When the Postgres backend is active, fail legibly (503) instead of a stack trace on
    # first page load if the database container isn't running. Shared with every other
    # Postgres-backed route family (govern-pg-s0-foundations, postgres-backend-resilience) —
    # the actual 503 shaping happens once, in api/main.py's DatabaseUnavailableError handler.
    require_reachable(backend, "Glossary")
    return GlossaryAgent()


def _format_context_generation_error(kind: str, exc: Exception) -> str:
    msg = str(exc)
    if "404" in msg:
        if kind == "dpm":
            return (
                "DPM generation unavailable: embedding deployment not found (404). "
                "RAG retrieval requires the configured embedding model deployment."
            )
        return (
            "CRR3 generation unavailable: model/deployment not found (404). "
            "Check both generation and embedding deployments for this endpoint."
        )
    if "401" in msg or "403" in msg:
        return f"{kind.upper()} generation unavailable: invalid credentials or unauthorized endpoint access."
    return f"{kind.upper()} generation unavailable: {msg}"


@router.get("")
def get_glossary():
    agent = _agent()
    return [t.to_dict() for t in agent.all_terms()]


@router.get("/terms/{term_id}")
def get_term(term_id: str):
    agent = _agent()
    term = agent.get(term_id)
    if not term:
        raise HTTPException(status_code=404, detail=f"Term '{term_id}' not found")
    return term.to_dict()


@router.put("/terms")
def create_or_update_term(
    body: GlossaryTermSchema,
    store: AuditStore = Depends(get_audit_store),
):
    from agents.glossary_agent import GlossaryTerm

    agent = _agent()
    term = GlossaryTerm.from_dict(body.model_dump())

    if term.id and agent.get(term.id):
        updated = agent.update(term)
        store.log_business(
            audit_events.GLOSSARY_TERM_UPDATED,
            "glossary_term",
            updated.id,
            {"id": updated.id, "title": updated.title, "domain": updated.domain,
             "status": updated.status},
        )
        return updated.to_dict()
    else:
        try:
            created = agent.add(term)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        store.log_business(
            audit_events.GLOSSARY_TERM_CREATED,
            "glossary_term",
            created.id,
            {"id": created.id, "title": created.title, "domain": created.domain,
             "status": created.status},
        )
        return created.to_dict()


@router.delete("/terms/{term_id}")
def delete_term(
    term_id: str,
    store: AuditStore = Depends(get_audit_store),
):
    agent = _agent()
    term = agent.get(term_id)
    try:
        agent.delete(term_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Term '{term_id}' not found")
    store.log_business(
        audit_events.GLOSSARY_TERM_DELETED,
        "glossary_term",
        term_id,
        {"id": term_id, "title": term.title if term else None},
    )
    return {"status": "deleted"}


@router.post("/terms/{term_id}/ai-suggest")
def ai_suggest(term_id: str):
    agent = _agent()
    term = agent.get(term_id)
    if not term:
        raise HTTPException(status_code=404, detail=f"Term '{term_id}' not found")
    suggestion = agent.suggest_term_update(term)
    return suggestion


class TermDecisionRequest(BaseModel):
    decided_by: str | None = None
    decided_by_role: str | None = None
    reason: str | None = None


@router.post("/terms/{term_id}/confirm")
def confirm_term(
    term_id: str,
    body: TermDecisionRequest | None = None,
    store: AuditStore = Depends(get_audit_store),
):
    """Confirm a glossary term (Steward review, Phase E2b).

    Sets the term status to 'approved' — this confirms the term for EVERY column
    it is linked to (glossary status is a term-level property, not per-link).
    """
    agent = _agent()
    term = agent.get(term_id)
    if not term:
        raise HTTPException(status_code=404, detail=f"Term '{term_id}' not found")
    payload = body or TermDecisionRequest()
    term.status = "approved"
    updated = agent.update(term)
    store.log_business(
        audit_events.GLOSSARY_TERM_UPDATED,
        "glossary_term",
        updated.id,
        {"id": updated.id, "title": updated.title, "status": updated.status,
         "decided_by": payload.decided_by, "decided_by_role": payload.decided_by_role},
    )
    return updated.to_dict()


@router.post("/terms/{term_id}/reject")
def reject_term(
    term_id: str,
    body: TermDecisionRequest | None = None,
    store: AuditStore = Depends(get_audit_store),
):
    """Reject a glossary term — reverts status to 'draft' for re-editing (Phase E2b)."""
    agent = _agent()
    term = agent.get(term_id)
    if not term:
        raise HTTPException(status_code=404, detail=f"Term '{term_id}' not found")
    payload = body or TermDecisionRequest()
    term.status = "draft"
    updated = agent.update(term)
    store.log_business(
        audit_events.GLOSSARY_TERM_UPDATED,
        "glossary_term",
        updated.id,
        {"id": updated.id, "title": updated.title, "status": updated.status,
         "decided_by": payload.decided_by, "decided_by_role": payload.decided_by_role,
         "reason": payload.reason},
    )
    return updated.to_dict()


@router.post("/terms/{term_id}/ai-suggest-fields")
def ai_suggest_fields(term_id: str, body: dict):
    """Generate AI suggestions for specific fields of a term.

    Body: { "fields": ["business_description", "detailed_description", ...] }
    Returns the same shape as ai-suggest but only the requested fields are generated.
    """
    agent = _agent()
    term = agent.get(term_id)
    if not term:
        raise HTTPException(status_code=404, detail=f"Term '{term_id}' not found")
    fields = body.get("fields", [])
    suggestion = agent.suggest_term_update(term)
    # Return only the requested fields plus metadata
    result: dict = {}
    generated_fields: list[str] = []
    for f in fields:
        if f not in suggestion:
            continue
        value = suggestion[f]
        result[f] = value
        if isinstance(value, list):
            if value:
                generated_fields.append(f)
        elif value:
            generated_fields.append(f)
    result["ai_generated_fields"] = generated_fields
    return result


@router.post("/terms/{term_id}/crr-context")
def generate_crr_context(term_id: str):
    """Generate CRR3 regulatory context for a term."""
    agent = _agent()
    term = agent.get(term_id)
    if not term:
        raise HTTPException(status_code=404, detail=f"Term '{term_id}' not found")

    from agents.crr_agent import generate_interactive as crr_generate

    parts = [term.title]
    if term.synonyms:
        parts.append(", ".join(term.synonyms))
    if term.business_description:
        parts.append(term.business_description.strip())
    query = ". ".join(parts)

    try:
        result = crr_generate(query)
    except Exception as exc:
        return {
            "CRR_context": "",
            "related_objects": [],
            "message": _format_context_generation_error("crr", exc),
        }
    if not result:
        return {"CRR_context": "", "related_objects": [], "message": "No relevant CRR3 content found."}
    return result


@router.post("/terms/{term_id}/dpm-context")
def generate_dpm_context(term_id: str):
    """Generate DPM 2.0 reporting context for a term."""
    agent = _agent()
    term = agent.get(term_id)
    if not term:
        raise HTTPException(status_code=404, detail=f"Term '{term_id}' not found")

    from agents.dpm_agent import generate_interactive as dpm_generate

    parts = [term.title]
    if term.synonyms:
        parts.append(", ".join(term.synonyms))
    if term.business_description:
        parts.append(term.business_description.strip())
    query = ". ".join(parts)

    try:
        result = dpm_generate(query)
    except Exception as exc:
        return {
            "DPM_context": "",
            "related_tables": [],
            "message": _format_context_generation_error("dpm", exc),
        }
    if not result:
        return {"DPM_context": "", "related_tables": [], "message": "No relevant DPM 2.0 content found."}
    return result


@router.get("/export")
def export_glossary():
    """Export full glossary as YAML download (backend-aware)."""
    from core.glossary_db.db import backend as _backend
    if _backend() == "postgres":
        agent = _agent()
        data = {"version": 1, "terms": [t.to_dict() for t in agent.all_terms()]}
    else:
        glossary_path = _ROOT / "glossary" / "glossary.yaml"
        if not glossary_path.exists():
            raise HTTPException(status_code=404, detail="Glossary file not found")
        with glossary_path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    content = yaml.safe_dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)
    return Response(
        content=content,
        media_type="application/x-yaml",
        headers={"Content-Disposition": "attachment; filename=glossary.yaml"},
    )


@router.get("/uncovered")
def uncovered_concepts():
    from core.glossary_intake import find_uncovered_source_concepts

    agent = _agent()
    terms = agent.all_terms()
    concepts = find_uncovered_source_concepts(terms)
    return [
        {
            "kind": c.kind,
            "dataset": c.dataset,
            "schema_name": c.schema,
            "table": c.table,
            "column": c.column,
            "data_type": c.data_type,
            "description": c.description,
            "related_object": c.related_object,
        }
        for c in concepts
    ]


@router.get("/cross-ref")
def cross_ref(ref: str):
    """Find glossary terms whose related_objects include the given catalog reference."""
    agent = _agent()
    terms = agent.cross_references(ref)
    return [t.to_dict() for t in terms]
