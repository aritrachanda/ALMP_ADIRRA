"""
FastAPI application for ADIRRA.

Exposes core/ and agents/ functionality over HTTP for the Vue/Quasar frontend.
"""
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import yaml
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import JSONResponse
from core.audit import make_audit_store, set_current_store
from core.element_state import ElementStateStore
from core.semantic_type_store import SemanticTypeStore
from core.reference_set_store import ReferenceSetStore
from core.reference_code_repo import ReferenceCodeRepo
from core.document_store import DocumentStore
from core.dq_config import DQScoringConfig
from core.dq_score_store import DQScoreStore
from core.dq_service import DQScoringService
from core.shared.db_availability import DatabaseUnavailableError

_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(_ROOT / ".env")


def _load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


# Shared state populated at startup, read by deps.py via app.state.
@asynccontextmanager
async def _lifespan(app: FastAPI):
    app.state.project = _load_yaml(_ROOT / "project.yaml")
    connections_file = app.state.project.get("connections_file", "connections.yaml")
    app.state.connections = _load_yaml(_ROOT / connections_file)
    app.state.root = _ROOT
    audit_db_path = Path(os.getenv("AI_TIMO_AUDIT_DB", str(_ROOT / "audit" / "audit.duckdb")))
    audit_store = make_audit_store(audit_db_path)
    app.state.audit_store = audit_store
    set_current_store(audit_store)
    _GOV = _ROOT / "governance"
    element_state_path = Path(os.getenv("AI_TIMO_ELEMENT_STATE", str(_GOV / "element_states.yaml")))
    app.state.element_state = ElementStateStore(element_state_path)
    app.state.semantic_type_store = SemanticTypeStore()
    # Phase 3: governed shared reference sets (read-only, hand-authored).
    app.state.reference_set_store = ReferenceSetStore()
    # Phase 5b.2: per-code Reference Data store (Postgres, behind the refdata_backend flag).
    app.state.reference_code_repo = ReferenceCodeRepo()
    # Bulk/direct Postgres access to reference sets + the column-to-set binding (govern-pg-d) —
    # separate app.state singleton from reference_set_store (which is the flag-aware yaml/pg
    # dual-mode reader); the Review Queue needs bulk binding lookups that ElementStateStore's
    # per-column get_reference_binding() doesn't expose.
    from core.reference_set_repo import ReferenceSetRepo
    app.state.reference_set_repo = ReferenceSetRepo()
    # Reference-set BINDING review lifecycle (govern-pg-d follow-up) — separate from the
    # binding data itself (ReferenceSetRepo); always Postgres, reuses the generic review
    # tables (no legacy YAML equivalent to fall back to).
    from core.reference_binding_review_repo import ReferenceBindingReviewRepo
    app.state.reference_binding_review_repo = ReferenceBindingReviewRepo()
    paths_cfg = app.state.project.get("paths", {})
    docs_root = _ROOT / paths_cfg.get("documents_root", "documents")
    docs_index = Path(os.getenv("AI_TIMO_DOCUMENTS", str(_GOV / "documents_index.yaml")))
    app.state.document_store = DocumentStore(docs_index, docs_root)

    # DQ scoring (U2a, headless): persist scores + re-score on semantic disposition.
    # Fully additive — nothing renders a score; guarded so startup never breaks.
    app.state.dq_score_store = DQScoreStore()
    try:
        _wire_dq_scoring(app, _ROOT, paths_cfg)
    except Exception:
        logging.getLogger(__name__).exception("DQ scoring service failed to initialize")

    # Business Glossary v2 (Phase 2): if the Postgres backend is active, log DB reachability
    # at startup so operators get an early, legible signal instead of a 503 on first use.
    # Default backend is 'yaml' (dormant), so this is a no-op for the current live path.
    try:
        from core.glossary_db.db import backend as _gl_backend, health as _gl_health

        app.state.glossary_backend = _gl_backend()
        if app.state.glossary_backend == "postgres":
            _log = logging.getLogger(__name__)
            if _gl_health():
                _log.info("Glossary backend=postgres; database reachable.")
            else:
                _log.warning(
                    "Glossary backend=postgres but database is UNREACHABLE — start it with "
                    "`docker compose -f db/docker-compose.yml up -d`. Glossary routes will 503."
                )
    except Exception:
        logging.getLogger(__name__).exception("Glossary backend health check failed")

    # Pre-warm source catalog cache so first requests are instant, not
    # blocked by a multi-second YAML parse of large catalogs like ALM Bank.
    await _prewarm_catalogs(app.state.project, _ROOT)

    yield
    audit_store.close()


def _wire_dq_scoring(app: FastAPI, root: Path, paths_cfg: dict) -> None:
    """Build the DQ scoring service and subscribe it to semantic events (U2a)."""
    from api.routes.element import (
        _find_glossary_term,
        _load_source_catalog,
        _resolve_table_column,
        _resolve_table_for_bulk,
    )

    config = DQScoringConfig.from_project(app.state.project)
    sources_dir = root / paths_cfg.get("source_catalogs", "sources")

    def _column_loader(source, schema, table, column):
        try:
            catalog = _load_source_catalog(sources_dir, source)
        except Exception:
            return None
        result = _resolve_table_column(catalog, table, column, schema)
        if not result:
            return None
        col_dict, _resolved_schema, tbl_dict = result
        return col_dict, tbl_dict

    def _dataset_loader(source, schema, table):
        try:
            catalog = _load_source_catalog(sources_dir, source)
        except Exception:
            return None
        found = _resolve_table_for_bulk(catalog, table, schema)
        if not found:
            return None
        _resolved_schema, tbl_dict = found
        return tbl_dict

    def _glossary_provider(source, schema, table, column):
        term = _find_glossary_term(source, schema or "", table, column)
        if not term:
            return None
        return {"linked": True, "term_status": term.get("status")}

    element_state = app.state.element_state

    def _refdata_provider(source, schema, table, column):
        """Reference-data documentation from steward-entered element state.

        U2b Task 4 — wires the *existing* refdata signals the steward already
        maintains on the Reference Data tab (``refdata_meanings`` counts →
        codes documented, ``refdata_status`` → code-set approval). No new
        documentation source is invented; ``distinct_count`` is left to the
        scorer's ``col_dict`` fallback (the profiler's exact count / full
        ``code_values``).

        Phase 5b.2 — when ``refdata_backend='postgres'`` the per-code
        ``reference_code`` rows are authoritative for *unbound* fields (the
        derived set status + documented-code count). *Bound* fields stay
        set-driven: their documented count comes from the reference set and
        their status stays whatever the (unchanged) binding metadata implies —
        value-preserving vs the YAML path.
        """
        from core.reference_code_repo import make_key, refdata_backend

        # Fixed 2026-08-16: this used to read a metadata key that stopped being populated
        # once element_content_backend moved to Postgres (C2), silently zeroing out every
        # bound field's DQ credit for months. get_reference_binding() is the real source.
        bound_set_id = element_state.get_reference_binding(source, schema, table, column)
        if refdata_backend() == "postgres":
            if bound_set_id:
                # Bound → set-driven (2026-08-16 redesign). codes_documented is deliberately
                # left unset (not 0-with-a-denominator) so the scorer's own distinct_count
                # fallback grants full credit for the "codes documented" line item, same as
                # before; the ONLY thing that changed is where "status" comes from — now the
                # binding's OWN submit/approve lifecycle, not dead metadata. A binding that
                # is merely bound-but-never-submitted stays "candidate" (some credit, not
                # full) until a steward actually approves it.
                key = make_key(source, schema, table, column)
                binding_status = app.state.reference_binding_review_repo.get_status(key)
                status = {"approved": "approved", "in_review": "under_review"}.get(
                    binding_status, "candidate")
                return {"codes_documented": 0, "status": status}
            try:
                summary = app.state.reference_code_repo.summary(
                    make_key(source, schema, table, column))
                return {
                    "codes_documented": summary.get("codes_documented", 0),
                    "status": summary.get("status", "none"),
                }
            except Exception:
                # DB unreachable — degrade to the neutral (unscored) signal rather
                # than break the DQ hot path.
                return {"codes_documented": 0, "status": "none"}

        meta = element_state.get_metadata(source, schema, table, column) or {}
        meanings = meta.get("refdata_meanings") or {}
        codes_documented = sum(1 for v in meanings.values() if v and str(v).strip())
        return {
            "codes_documented": codes_documented,
            "status": meta.get("refdata_status") or "none",
        }

    service = DQScoringService(
        dq_store=app.state.dq_score_store,
        element_state=app.state.element_state,
        semantic_store=app.state.semantic_type_store,
        config=config,
        column_loader=_column_loader,
        dataset_loader=_dataset_loader,
        glossary_provider=_glossary_provider,
        refdata_provider=_refdata_provider,
    )
    service.register_subscribers()
    app.state.dq_service = service
    app.state.dq_config = config


async def _prewarm_catalogs(project: dict, root: Path) -> None:
    """Load all source (and target) YAML catalogs in background threads.

    Populates the shared mtime-cache in ``core.catalog`` so every route's first
    request is a fast cache-hit rather than a multi-second parse of a large catalog.
    """
    from core.catalog import load_catalog_dispatch

    paths_cfg = project.get("paths", {})
    sources_dir = root / paths_cfg.get("source_catalogs", "sources")
    targets_dir = root / paths_cfg.get("target_catalogs", "targets")

    loop = asyncio.get_event_loop()

    async def _load_one(name: str, catalog_dir: Path, kind: str = "source") -> None:
        path = catalog_dir / f"{name}.yaml"
        if not path.exists():
            return
        try:
            await loop.run_in_executor(None, lambda: load_catalog_dispatch(path, kind=kind))
        except Exception as exc:
            logging.getLogger(__name__).warning("Failed to pre-warm catalog %r: %s", name, exc)

    tasks = [
        _load_one(src["name"], sources_dir)
        for src in project.get("sources", [])
        if "name" in src
    ] + [
        _load_one(tgt["name"], targets_dir, "target")
        for tgt in project.get("targets", [])
        if "name" in tgt
    ]
    await asyncio.gather(*tasks)


app = FastAPI(
    title="ADIRRA API",
    version="0.1.0",
    lifespan=_lifespan,
)


@app.exception_handler(DatabaseUnavailableError)
async def _database_unavailable_handler(request: Request, exc: DatabaseUnavailableError) -> JSONResponse:
    """One shared clean-503 response for every Postgres-backed feature (S0 foundations,
    postgres-backend-resilience) — any route that lets a DatabaseUnavailableError propagate
    (instead of a raw connection exception) gets this same message for free."""
    return JSONResponse(
        status_code=503,
        content={
            "detail": (
                f"{exc.service_label} database is not running. Start it with: "
                "docker compose -f db/docker-compose.yml up -d"
            )
        },
    )

# CORS ------------------------------------------------------------------
_default_origins = "http://localhost:9000"
_origins = os.getenv("AI_TIMO_CORS_ORIGINS", _default_origins).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers ---------------------------------------------------------------
from api.routes.health import router as health_router  # noqa: E402
from api.routes.catalogs import router as catalogs_router  # noqa: E402
from api.routes.mappings import router as mappings_router  # noqa: E402
from api.routes.glossary import router as glossary_router  # noqa: E402
from api.routes.glossary_v2 import router as glossary_v2_router  # noqa: E402
from api.routes.chat import router as chat_router  # noqa: E402
from api.routes.discovery import router as discovery_router  # noqa: E402
from api.routes.annotations import router as annotations_router  # noqa: E402
from api.routes.dashboard import router as dashboard_router  # noqa: E402
from api.routes.settings import router as settings_router  # noqa: E402
from api.routes.audit import router as audit_router  # noqa: E402
from api.routes.element import router as element_router  # noqa: E402
from api.routes.insights import router as insights_router  # noqa: E402
from api.routes.bird import router as bird_router  # noqa: E402
from api.semantic_types import router as semantic_types_router  # noqa: E402
from api.routes.review_queue import router as review_queue_router  # noqa: E402
from api.routes.documents import router as documents_router  # noqa: E402
from api.routes.reference_data import router as reference_data_router  # noqa: E402
from api.routes.reference_sets import router as reference_sets_router  # noqa: E402

app.include_router(health_router)
app.include_router(catalogs_router)
app.include_router(mappings_router)
app.include_router(glossary_router)
app.include_router(glossary_v2_router)
app.include_router(chat_router)
app.include_router(discovery_router)
app.include_router(annotations_router)
app.include_router(dashboard_router)
app.include_router(settings_router)
app.include_router(audit_router)
app.include_router(element_router)
app.include_router(insights_router)
app.include_router(bird_router)
app.include_router(semantic_types_router)
app.include_router(review_queue_router)
app.include_router(documents_router)
app.include_router(reference_data_router)
app.include_router(reference_sets_router)
