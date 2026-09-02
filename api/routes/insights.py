"""Insights API — cross-element findings + AI hypotheses for a table.

GET /insights/{source}/{table}?schema=...&include_ai=false
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import yaml
from fastapi import APIRouter, Depends, Query

from api.deps import get_paths, get_audit_store
from core.assessment import assess_table
from core.audit import AuditStore
from core.audit import events as audit_events
from core.catalog import load_catalog_dispatch

router = APIRouter(prefix="/insights", tags=["insights"])

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _load_source_catalog(sources_dir: Path, source: str) -> dict:
    path = sources_dir / f"{source}.yaml"
    # Respects catalog_backend (Phase 6) — in postgres mode there's no on-disk file to
    # gate on, so we always dispatch and let an empty result mean "not found".
    return load_catalog_dispatch(path)


def _readiness(findings: list[dict]) -> dict:
    blocking = sum(1 for f in findings if f.get("severity") == "high")
    medium = sum(1 for f in findings if f.get("severity") == "attention")
    info = sum(1 for f in findings if f.get("severity") == "info")
    return {
        "blocking": blocking,
        "medium": medium,
        "info": info,
        "not_ready": blocking > 0,
    }


@router.get("/{source}/{table}")
async def get_insights(
    source: str,
    table: str,
    schema: Optional[str] = Query(default=None),
    include_ai: bool = Query(default=False),
    paths: dict = Depends(get_paths),
    audit_store: AuditStore = Depends(get_audit_store),
):
    catalog = _load_source_catalog(paths["sources"], source)
    tbl_dict: dict | None = None
    for sc in catalog.get("schemas", []):
        if schema and sc.get("name") != schema:
            continue
        for tbl in sc.get("tables", []):
            if tbl.get("table_name") == table:
                tbl_dict = tbl
                break
        if tbl_dict:
            break

    findings: list[dict] = []
    if tbl_dict:
        try:
            result = assess_table(tbl_dict, include_ai=False)
            findings = result.get("findings", [])
        except Exception:
            pass

    hypotheses: list[dict] = []
    if include_ai and findings:
        try:
            import yaml as _yaml
            with (_ROOT / "project.yaml").open(encoding="utf-8") as fh:
                project = _yaml.safe_load(fh) or {}
            agent_cfg = project.get("agent", {})

            from core.insights import generate_hypotheses
            hypotheses = generate_hypotheses(findings, source, table, agent_cfg)

            audit_store.log_business(
                event_type=audit_events.INSIGHTS_GENERATED,
                subject_type="table",
                subject_id=f"{source}:{schema or ''}.{table}",
                payload={
                    "source": source,
                    "table": table,
                    "finding_count": len(findings),
                    "hypothesis_count": len(hypotheses),
                },
            )
        except Exception:
            pass

    return {
        "source": source,
        "table": table,
        "findings": findings,
        "hypotheses": hypotheses,
        "readiness": _readiness(findings),
    }
