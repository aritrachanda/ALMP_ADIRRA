"""Documents API — source document metadata, file storage, and AI synopsis generation.

GET    /documents/{source}               → list all documents for a source
POST   /documents/{source}               → upload a new document (multipart)
GET    /documents/{source}/{doc_id}      → get single document record
DELETE /documents/{source}/{doc_id}      → delete document and its file
POST   /documents/{source}/{doc_id}/synopsis → generate (or regenerate) AI synopsis
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from api.deps import get_audit_store, get_document_store, get_project
from core.audit import AuditStore
from core.document_store import DocumentStore

router = APIRouter(prefix="/documents", tags=["documents"])

_VALID_DOC_TYPES = {"Data Dictionary", "Mapping Spec", "System Spec", "Quality Rules", "Other"}
_MAX_FILE_MB = 20


# ── Helpers ──────────────────────────────────────────────────────────────────

def _check_source(source: str) -> None:
    if not source or "/" in source or "\\" in source:
        raise HTTPException(status_code=422, detail="Invalid source name.")


def _check_doc(doc: dict[str, Any] | None, doc_id: str) -> dict[str, Any]:
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found.")
    return doc


def _generate_synopsis(doc: dict[str, Any], project: dict) -> str:
    """Generate a synopsis from document metadata using LLM, with rule-based fallback.

    Gap 1 (file text extraction) is intentionally skipped — synopsis is derived from
    metadata only. A richer extraction pass can be added in a future phase.
    """
    try:
        from foundry_client import create_foundry_client
        agent_cfg = project.get("agent", {})
        api_key = os.environ.get(agent_cfg.get("api_key_env", ""), "")
        if not api_key:
            raise ValueError("No API key")
        client = create_foundry_client(
            api_key=api_key,
            api_key_env=agent_cfg.get("api_key_env", ""),
        )
        model = agent_cfg.get("model", "")
        perms = doc.get("ai_permissions") or {}
        uses = [k for k, v in perms.items() if v]
        prompt = (
            f"You are a data governance specialist. Generate a concise 2–3 sentence synopsis "
            f"for this document based on its metadata:\n"
            f"- Name: {doc.get('name')}\n"
            f"- Type: {doc.get('doc_type')}\n"
            f"- Description: {doc.get('description') or 'Not provided'}\n"
            f"- Owner: {doc.get('owner') or 'Unknown'}\n"
            f"- Scope: {doc.get('scope')}\n"
            f"- Source system: {doc.get('source')}\n"
            f"- AI permitted for: {', '.join(uses) or 'none'}\n\n"
            f"Describe what this document likely contains, how it supports data governance, "
            f"and what AI can use it for. Be specific and practical."
        )
        response = client.responses.create(
            model=model, instructions="", input=prompt, temperature=0
        )
        return response.output_text.strip()
    except Exception:
        # Rule-based fallback — always works
        perms = doc.get("ai_permissions") or {}
        uses = [k for k, v in perms.items() if v]
        desc_part = f" Description: {doc['description']}." if doc.get("description") else ""
        return (
            f"This {doc.get('doc_type', 'document')} covers the {doc.get('source')} source system "
            f"(scope: {doc.get('scope', 'Source-level')}).{desc_part} "
            f"AI permitted for: {', '.join(uses) or 'none configured'}."
        )


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/{source}")
async def list_documents(
    source: str,
    doc_store: DocumentStore = Depends(get_document_store),
):
    """Return all documents for a source, newest first."""
    _check_source(source)
    return {"source": source, "documents": doc_store.list_source(source)}


@router.post("/{source}")
async def upload_document(
    source: str,
    name: str = Form(...),
    doc_type: str = Form(...),
    description: str = Form(""),
    owner: str = Form(""),
    scope: str = Form("Source-level"),
    ai_def: bool = Form(True),
    ai_map: bool = Form(True),
    ai_quality: bool = Form(False),
    file: UploadFile | None = File(default=None),
    doc_store: DocumentStore = Depends(get_document_store),
    audit_store: AuditStore = Depends(get_audit_store),
):
    """Upload a new document (with optional file attachment)."""
    _check_source(source)
    if doc_type not in _VALID_DOC_TYPES:
        raise HTTPException(status_code=422, detail=f"doc_type must be one of: {sorted(_VALID_DOC_TYPES)}")

    doc_id = str(uuid4())
    file_name: str | None = None
    file_path_rel: str | None = None
    file_size_kb: float | None = None

    if file and file.filename:
        content = await file.read()
        size_mb = len(content) / (1024 * 1024)
        if size_mb > _MAX_FILE_MB:
            raise HTTPException(status_code=413, detail=f"File exceeds {_MAX_FILE_MB} MB limit.")
        dest = doc_store.file_path(source, doc_id, file.filename)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
        file_name = file.filename
        file_path_rel = str(Path(source) / doc_id / file.filename)
        file_size_kb = round(len(content) / 1024, 1)

    doc = DocumentStore.default_record(
        doc_id=doc_id,
        source=source,
        name=name,
        doc_type=doc_type,
        description=description,
        owner=owner,
        scope=scope,
        file_name=file_name,
        file_path_rel=file_path_rel,
        file_size_kb=file_size_kb,
        ai_permissions={"definitions": ai_def, "mapping": ai_map, "quality": ai_quality},
    )
    saved = doc_store.add(doc)
    audit_store.log_business(
        event_type="document.uploaded",
        subject_type="document",
        subject_id=f"{source}:{doc_id}",
        payload={"source": source, "doc_id": doc_id, "name": name, "doc_type": doc_type},
    )
    return saved


@router.get("/{source}/{doc_id}")
async def get_document(
    source: str,
    doc_id: str,
    doc_store: DocumentStore = Depends(get_document_store),
):
    """Return a single document record."""
    _check_source(source)
    return _check_doc(doc_store.get(doc_id), doc_id)


@router.delete("/{source}/{doc_id}")
async def delete_document(
    source: str,
    doc_id: str,
    doc_store: DocumentStore = Depends(get_document_store),
    audit_store: AuditStore = Depends(get_audit_store),
):
    """Delete a document record and its file (if any)."""
    _check_source(source)
    doc = _check_doc(doc_store.get(doc_id), doc_id)

    # Remove file from disk
    if doc.get("file_name"):
        fpath = doc_store.file_path(source, doc_id, doc["file_name"])
        if fpath.exists():
            fpath.unlink()
        # Clean up empty directories
        for d in (fpath.parent, fpath.parent.parent):
            try:
                d.rmdir()
            except OSError:
                break

    deleted = doc_store.delete(doc_id)
    audit_store.log_business(
        event_type="document.deleted",
        subject_type="document",
        subject_id=f"{source}:{doc_id}",
        payload={"source": source, "doc_id": doc_id, "name": doc.get("name")},
    )
    return {"deleted": deleted, "doc_id": doc_id}


@router.post("/{source}/{doc_id}/synopsis")
async def generate_synopsis(
    source: str,
    doc_id: str,
    doc_store: DocumentStore = Depends(get_document_store),
    project: dict = Depends(get_project),
    audit_store: AuditStore = Depends(get_audit_store),
):
    """Generate (or regenerate) an AI synopsis for a document from its metadata.

    File text extraction is not performed (Gap 1 deferred). The synopsis is built
    from the document's stored metadata and source context.
    """
    _check_source(source)
    doc = _check_doc(doc_store.get(doc_id), doc_id)
    synopsis = _generate_synopsis(doc, project)
    updated = doc_store.set_synopsis(doc_id, synopsis, is_ai=True)
    audit_store.log_business(
        event_type="document.synopsis_generated",
        subject_type="document",
        subject_id=f"{source}:{doc_id}",
        payload={"source": source, "doc_id": doc_id, "synopsis_length": len(synopsis)},
    )
    return updated
