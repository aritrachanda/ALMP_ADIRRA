"""Settings API routes — export and import governance artifacts."""
from __future__ import annotations

import datetime as dt
import io
import json
import re
import zipfile
from pathlib import Path

import yaml
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse

from api.deps import get_paths, get_root

router = APIRouter(prefix="/settings", tags=["settings"])

# ---------------------------------------------------------------------------
# Persona config
# ---------------------------------------------------------------------------

_PERSONA_FILE = Path(__file__).resolve().parent.parent.parent / "persona.yaml"

_PERSONA_DEFAULTS: dict = {
    "name": "Assistant",
    "role": "Senior Data Governance Analyst and AI assistant",
    "expertise": ["CRR3", "BIRD", "FINREP", "COREP", "IFRS 9"],
    "tone": "precise",
    "verbosity": "balanced",
    "response_format": "prose",
    "avatar_url": "",
    "context": {
        "glossary_links": True,
        "mapping_candidates": True,
        "profiling_stats": True,
        "audit_history": False,
    },
    "knowledge_sources": {
        "crr3_regulation": True,
        "eba_dpm": True,
        "internal_kb": False,
        "policy_documents": False,
    },
    "inference": {
        "temperature": 0.3,
    },
}


def _load_persona() -> dict:
    """Read persona.yaml fresh — no caching so edits apply on the next request."""
    if not _PERSONA_FILE.exists():
        return {**_PERSONA_DEFAULTS}
    with _PERSONA_FILE.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    merged = {**_PERSONA_DEFAULTS, **data}
    merged["context"] = {**_PERSONA_DEFAULTS["context"], **data.get("context", {})}
    merged["knowledge_sources"] = {**_PERSONA_DEFAULTS["knowledge_sources"], **data.get("knowledge_sources", {})}
    merged["inference"] = {**_PERSONA_DEFAULTS["inference"], **data.get("inference", {})}
    return merged


@router.get("/persona")
async def get_persona():
    """Return the current AI persona configuration."""
    return _load_persona()


@router.put("/persona")
async def save_persona(body: dict):
    """Persist AI persona settings to persona.yaml."""
    name = body.get("name", "")
    if not isinstance(name, str) or not name.strip():
        raise HTTPException(status_code=400, detail="'name' is required and must be a non-empty string.")
    # Ensure nested keys exist with defaults
    body.setdefault("context", _PERSONA_DEFAULTS["context"])
    body.setdefault("inference", _PERSONA_DEFAULTS["inference"])
    with _PERSONA_FILE.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(body, fh, allow_unicode=True, sort_keys=False, default_flow_style=False)
    return body


@router.post("/persona/reset")
async def reset_persona():
    """Reset persona to factory defaults."""
    with _PERSONA_FILE.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(_PERSONA_DEFAULTS, fh, allow_unicode=True, sort_keys=False, default_flow_style=False)
    return _PERSONA_DEFAULTS


# ---------------------------------------------------------------------------
# Shared helpers (export/import)
# ---------------------------------------------------------------------------

def _load_yaml(path: Path):
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _list_yaml(folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    return sorted(
        p for p in folder.glob("*.yaml")
        if not p.name.endswith(".annotations.yaml")
    )


def _list_annotation_files(folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    return sorted(folder.glob("*.annotations.yaml"))


def _filter_term(term: dict, include_descriptions: bool, include_synonyms_tags: bool,
                 include_related: bool, include_governance: bool, include_ai: bool) -> dict:
    filtered = {
        "id": term.get("id", ""),
        "title": term.get("title", ""),
        "domain": term.get("domain", ""),
        "category": term.get("category", ""),
    }
    if include_descriptions:
        for k in ("business_description", "detailed_description", "CRR_context", "DPM_context"):
            if k in term:
                filtered[k] = term[k]
    if include_synonyms_tags:
        for k in ("synonyms", "tags"):
            if k in term:
                filtered[k] = term[k]
    if include_related and "related_objects" in term:
        filtered["related_objects"] = term["related_objects"]
    if include_governance:
        for k in ("status", "steward"):
            if k in term:
                filtered[k] = term[k]
    if include_ai and "ai_generated_fields" in term:
        filtered["ai_generated_fields"] = term["ai_generated_fields"]
    return filtered


# ── Export inventory (what's available to export) ──

@router.get("/export/inventory")
async def export_inventory(paths: dict = Depends(get_paths), root: Path = Depends(get_root)):
    from core.glossary_db.read_api import glossary_terms
    terms = glossary_terms()

    source_files = _list_yaml(paths["sources"])
    target_files = _list_yaml(paths["targets"])
    mapping_files = _list_yaml(paths["mappings"])
    annotation_files = _list_annotation_files(paths["sources"]) + _list_annotation_files(paths["targets"])

    return {
        "glossary_terms": len(terms),
        "term_options": [
            {"id": t.get("id", ""), "title": t.get("title", t.get("id", "Untitled"))}
            for t in terms
        ],
        "source_datasets": [p.stem for p in source_files],
        "target_datasets": [p.stem for p in target_files],
        "mapping_files": [p.name for p in mapping_files],
        "annotation_count": len(annotation_files),
    }


# ── ZIP export ──

@router.post("/export/zip")
async def export_zip(
    config: dict,
    paths: dict = Depends(get_paths),
    root: Path = Depends(get_root),
):
    glossary_meta_path = root / "glossary" / "glossary_meta.yaml"
    glossary_meta = _load_yaml(glossary_meta_path)
    from core.glossary_db.read_api import glossary_terms
    all_terms = glossary_terms()

    glossary_enabled = config.get("glossary_enabled", True)
    glossary_scope = config.get("glossary_scope", "entire")
    selected_term_ids = config.get("selected_term_ids", [])
    include_meta = config.get("include_meta", True)
    include_descriptions = config.get("include_descriptions", True)
    include_synonyms_tags = config.get("include_synonyms_tags", True)
    include_related = config.get("include_related", True)
    include_governance = config.get("include_governance", True)
    include_ai = config.get("include_ai", False)
    selected_sources = config.get("selected_sources", [])
    selected_targets = config.get("selected_targets", [])
    include_annotations = config.get("include_annotations", True)
    selected_mappings = config.get("selected_mappings", [])

    source_map = {p.stem: p for p in _list_yaml(paths["sources"])}
    target_map = {p.stem: p for p in _list_yaml(paths["targets"])}
    mapping_map = {p.name: p for p in _list_yaml(paths["mappings"])}

    manifest = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "package": "agentic-data-management-export",
        "files": [],
    }
    has_content = False
    buf = io.BytesIO()

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        if glossary_enabled:
            terms = all_terms if glossary_scope != "selected" else [
                t for t in all_terms if t.get("id") in selected_term_ids
            ]
            if terms:
                payload = {"version": 1, "terms": [
                    _filter_term(t, include_descriptions, include_synonyms_tags,
                                 include_related, include_governance, include_ai)
                    for t in terms
                ]}
                archive.writestr("glossary/glossary.yaml",
                                 yaml.safe_dump(payload, sort_keys=False, allow_unicode=True))
                manifest["files"].append("glossary/glossary.yaml")
                has_content = True
            if include_meta and glossary_meta:
                archive.writestr("glossary/glossary_meta.yaml",
                                 yaml.safe_dump(glossary_meta, sort_keys=False, allow_unicode=True))
                manifest["files"].append("glossary/glossary_meta.yaml")
                has_content = True

        for ds in selected_sources:
            p = source_map.get(ds)
            if p and p.exists():
                archive.write(p, arcname=f"sources/{p.name}")
                manifest["files"].append(f"sources/{p.name}")
                has_content = True
                ann = p.with_name(p.stem + ".annotations.yaml")
                if include_annotations and ann.exists():
                    archive.write(ann, arcname=f"sources/{ann.name}")
                    manifest["files"].append(f"sources/{ann.name}")

        for ds in selected_targets:
            p = target_map.get(ds)
            if p and p.exists():
                archive.write(p, arcname=f"targets/{p.name}")
                manifest["files"].append(f"targets/{p.name}")
                has_content = True
                ann = p.with_name(p.stem + ".annotations.yaml")
                if include_annotations and ann.exists():
                    archive.write(ann, arcname=f"targets/{ann.name}")
                    manifest["files"].append(f"targets/{ann.name}")

        for name in selected_mappings:
            p = mapping_map.get(name)
            if p and p.exists():
                archive.write(p, arcname=f"mappings/{p.name}")
                manifest["files"].append(f"mappings/{p.name}")
                has_content = True

        if has_content:
            archive.writestr("manifest.json", json.dumps(manifest, indent=2))

    if not has_content:
        raise HTTPException(status_code=400, detail="No artifacts selected for export.")

    buf.seek(0)
    filename = f"adirra-export-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── PDF export ──

def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _build_summary_pdf(lines: list[str]) -> bytes:
    objects: list[bytes] = []
    page_chunks = [lines[i:i + 34] for i in range(0, len(lines), 34)] or [["ADIRRA export summary"]]

    def add_obj(payload: bytes) -> int:
        objects.append(payload)
        return len(objects)

    font_id = add_obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    pages_slot = len(objects)
    objects.append(b"")

    page_ids: list[int] = []
    for chunk in page_chunks:
        rows = [b"BT", b"/F1 11 Tf", b"50 792 Td"]
        for idx, line in enumerate(chunk):
            safe = _pdf_escape(line[:110]).encode("latin-1", errors="replace")
            rows.append(b"(" + safe + b") Tj" if idx == 0 else b"0 -18 Td (" + safe + b") Tj")
        rows.append(b"ET")
        stream = b"\n".join(rows)
        content_id = add_obj(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream")
        page_id = add_obj(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {content_id} 0 R "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> >>".encode()
        )
        page_ids.append(page_id)

    refs = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects[pages_slot] = f"<< /Type /Pages /Count {len(page_ids)} /Kids [{refs}] >>".encode()
    catalog_id = add_obj(b"<< /Type /Catalog /Pages 2 0 R >>")

    pdf = io.BytesIO()
    pdf.write(b"%PDF-1.4\n")
    offsets: list[int] = []
    for i, payload in enumerate(objects, start=1):
        offsets.append(pdf.tell())
        pdf.write(f"{i} 0 obj\n".encode())
        pdf.write(payload)
        pdf.write(b"\nendobj\n")
    xref = pdf.tell()
    pdf.write(f"xref\n0 {len(objects) + 1}\n".encode())
    pdf.write(b"0000000000 65535 f \n")
    for o in offsets:
        pdf.write(f"{o:010d} 00000 n \n".encode())
    pdf.write(f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    return pdf.getvalue()


@router.post("/export/pdf")
async def export_pdf(
    config: dict,
    paths: dict = Depends(get_paths),
    root: Path = Depends(get_root),
):
    lines = [
        "ADIRRA Export Summary",
        f"Generated at: {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "Selected components:",
    ]
    for c in config.get("components", ["None selected"]):
        lines.append(f"- {c}")
    lines.extend([
        "",
        f"Glossary enabled: {'Yes' if config.get('glossary_enabled') else 'No'}",
        f"Glossary scope: {config.get('glossary_scope', 'entire')}",
        f"Source datasets: {len(config.get('selected_sources', []))}",
        f"Target datasets: {len(config.get('selected_targets', []))}",
        f"Mapping files: {len(config.get('selected_mappings', []))}",
    ])
    pdf_bytes = _build_summary_pdf(lines)
    buf = io.BytesIO(pdf_bytes)
    filename = f"adirra-export-summary-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Import: glossary ──

def _slugify(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower())
    return text.strip("_") or "item"


def _is_empty(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, dict)):
        return len(value) == 0
    return False


def _normalize_term(term: dict) -> dict:
    normalized = {
        "id": str(term.get("id") or _slugify(term.get("title", "term"))).strip(),
        "domain": str(term.get("domain") or "").strip(),
        "category": str(term.get("category") or "").strip(),
        "title": str(term.get("title") or "").strip(),
    }
    if not normalized["title"]:
        normalized["title"] = normalized["id"].replace("_", " ").title()
    for f in ("business_description", "detailed_description", "CRR_context", "DPM_context", "steward", "status"):
        if f in term and not _is_empty(term.get(f)):
            normalized[f] = str(term[f]).strip()
    for f in ("synonyms", "tags", "ai_generated_fields"):
        v = term.get(f)
        if isinstance(v, list) and v:
            normalized[f] = v
    related = term.get("related_objects")
    if isinstance(related, list) and related:
        normalized["related_objects"] = related
    if "status" not in normalized:
        normalized["status"] = "draft"
    if "steward" not in normalized:
        normalized["steward"] = ""
    return normalized


def _merge_terms(existing: list[dict], incoming: list[dict], mode: str) -> tuple[list[dict], dict]:
    merged = [dict(t) for t in existing]
    idx = {str(t.get("id")): i for i, t in enumerate(merged)}
    stats = {"created": 0, "updated": 0, "skipped": 0, "unchanged": 0}
    for imp in incoming:
        tid = str(imp.get("id"))
        if tid not in idx:
            merged.append(imp)
            idx[tid] = len(merged) - 1
            stats["created"] += 1
            continue
        if mode == "skip":
            stats["skipped"] += 1
            continue
        existing_term = dict(merged[idx[tid]])
        changed = False
        for k, v in imp.items():
            if k == "id":
                continue
            if mode == "empty" and _is_empty(existing_term.get(k)) and not _is_empty(v):
                existing_term[k] = v
                changed = True
            elif mode == "overwrite" and not _is_empty(v) and existing_term.get(k) != v:
                existing_term[k] = v
                changed = True
        merged[idx[tid]] = existing_term
        stats["updated" if changed else "unchanged"] += 1
    return merged, stats


@router.post("/import/glossary")
async def import_glossary(
    file: UploadFile = File(...),
    merge_mode: str = Form("skip"),
    root: Path = Depends(get_root),
):
    content = await file.read()
    try:
        raw = yaml.safe_load(content.decode("utf-8-sig")) or {}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {exc}")

    if isinstance(raw, dict):
        rows = raw.get("terms", [])
    elif isinstance(raw, list):
        rows = raw
    else:
        raise HTTPException(status_code=400, detail="YAML must contain a 'terms' list.")

    incoming = [_normalize_term(r) for r in rows if isinstance(r, dict) and (r.get("id") or r.get("title"))]

    from core.glossary_db.read_api import _use_pg, glossary_terms
    if _use_pg():
        existing = glossary_terms()
        merged, stats = _merge_terms(existing, incoming, merge_mode)
        # Postgres backend: upsert the merged set through the repository instead of
        # rewriting glossary.yaml (which is no longer the source of truth after cutover).
        from core.glossary_db.db import session_scope
        from core.glossary_db.repository import GlossaryRepository
        with session_scope() as session:
            repo = GlossaryRepository(session)
            for term in merged:
                data = dict(term)
                data["id"] = term.get("id") or term.get("title")
                repo.update_term(data)
        return {"status": "ok", "stats": stats}

    glossary_path = root / "glossary" / "glossary.yaml"
    glossary_data = _load_yaml(glossary_path)
    existing = glossary_data.get("terms", [])

    merged, stats = _merge_terms(existing, incoming, merge_mode)

    glossary_path.parent.mkdir(parents=True, exist_ok=True)
    with glossary_path.open("w", encoding="utf-8", newline="\n") as fh:
        yaml.safe_dump({"version": glossary_data.get("version", 1), "terms": merged},
                       fh, sort_keys=False, allow_unicode=True)

    return {"status": "ok", "stats": stats}


# ── Import: mappings ──

@router.post("/import/mapping")
async def import_mapping(
    file: UploadFile = File(...),
    destination: str = Form(""),
    replace: bool = Form(False),
    paths: dict = Depends(get_paths),
):
    content = await file.read()
    try:
        raw = yaml.safe_load(content.decode("utf-8-sig")) or {}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {exc}")

    if not isinstance(raw, dict) or not isinstance(raw.get("tables"), list):
        raise HTTPException(status_code=400, detail="Mapping YAML must have a 'tables' list.")

    # Sanitize destination filename
    dest_name = Path(destination or file.filename or "import.yaml").name
    if not dest_name.lower().endswith((".yaml", ".yml")):
        dest_name = f"{_slugify(dest_name)}.yaml"
    # Prevent path traversal
    dest_name = Path(dest_name).name

    dest_path = paths["mappings"] / dest_name
    if dest_path.exists() and not replace:
        raise HTTPException(status_code=409, detail="File already exists. Set replace=true to overwrite.")

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with dest_path.open("w", encoding="utf-8", newline="\n") as fh:
        yaml.safe_dump(raw, fh, sort_keys=False, allow_unicode=True)

    return {"status": "ok", "destination": f"mappings/{dest_name}"}
