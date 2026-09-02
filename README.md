# ADIRRA (Agentic Data Intelligence for Regulatory Readiness Acceleration)

ADIRRA is a working-prototype data intelligence platform for regulatory and risk analytics in
financial institutions. It connects to source databases, extracts and profiles schemas, scores data
quality, resolves semantic types, and uses an LLM to automatically map columns from source datasets
to target regulatory data models (BIRD, CRDM today). It also includes a multi-agent chat interface
for querying CRR3 regulations and DPM data models, and a business glossary with LLM-powered
enrichment.

The platform vision is a full dataset lifecycle — datasets flow *onboarded → governed → profiled →
defined → measured → protected → modelled → mapped → transformed → visualised*. Today the
**Data Governance** layer is built (discovery, cataloguing, profiling, DQ scoring, semantic typing,
mapping); the rest is roadmap.

## Architecture

ADIRRA presents two surfaces over one canonical data layer:

- **FastAPI backend** (`api/`) — the single data/service layer (SSE streaming for mapping progress).
  This is the source of truth for all data access.
- **Vue 3 + Quasar frontend** (`frontend/`) — the target and only UI, covering Discovery, Catalog,
  Mapping, Asset Workspace, and data-quality and governance views.
- **PostgreSQL governance database** (`db/`) — the default persistence layer for governance/user
  state: Business Glossary, per-element Interpretation lifecycle, Reference Data, Audit log,
  source/target Catalog, semantic types, and DQ scores. Legacy YAML/DuckDB files are kept as a
  live, per-store rollback switch for most of these (see [db/README.md](db/README.md)) — semantic
  types and DQ scores have been fully cut over with no YAML fallback left.

LLM access is provider-agnostic (`azure` / `openai` / `gemini`, selected in `project.yaml`);
Azure Foundry is the current default, built through the single client factory `foundry_client.py`.

## Setup

### 1. Prerequisites

- Python 3.11+
- Node.js 20+ (frontend developed against Node 24; see `frontend/package.json`)
- Docker with Compose v2 (for the PostgreSQL governance database, step 4)
- An Azure Foundry API key

### 2. Install dependencies

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/macOS

pip install -r requirements.txt
```

### 3. Configure API key

Create a `.env` file in the project root:

```
AZURE_FOUNDRY_KEY=foundry_api_key
AZURE_FOUNDRY_ENDPOINT=foundry_endpoint
```

Do not use personal API keys. Contact the project maintainer for a shared Azure Foundry key.

### 4. Set up the governance database (PostgreSQL)

ADIRRA stores its governance/user state (Business Glossary, per-element Interpretation lifecycle,
Reference Data, Audit log, source/target Catalog, semantic types, DQ scores) in PostgreSQL by
default. Full detail (schema, backend-flag overrides, reset/reseed) is in
[db/README.md](db/README.md); the short version:

```bash
# 1. Start Postgres 16 in Docker
docker compose -f db/docker-compose.yml up -d

# 2. Apply migrations
alembic -c db/alembic.ini upgrade head

# 3. (Optional) seed from the legacy YAML/DuckDB files if you have existing data to carry over
python -m core.glossary_db.migrate_from_yaml
python -m core.catalog_db.migrate_from_yaml
```

A fresh clone with no prior YAML data can skip step 3 — sources are onboarded/profiled directly
into Postgres via step 8 below. The password comes from the `ADM_DB_PASSWORD` env var (add it to
`.env`); if unset, a local-only default lets a fresh clone boot without any extra setup.

### 5. Generate target catalogs

Target catalogs (`mappings/target_catalogs/bird.yaml`, `mappings/target_catalogs/crdm.yaml`) are **gitignored** and must be generated locally after cloning:

```bash
# BIRD target — converts Excel → DuckDB → YAML
python sources/loader/bird_to_duckdb.py
python sources/loader/bird_to_yaml.py

# CRDM target — converts DuckDB metadata → YAML
python sources/loader/crdm_to_yaml.py
```

### 6. Build DPM RAG index

The DPM FAISS index and supporting files are too large for git (~1.3 GB) and are stored outside the repo in a local cache directory (configured in `project.yaml` → `paths.rag_cache`, defaults to `~/.ai-timo/rag/`). Requires an Azure OpenAI API key for embeddings.

```bash
# 1. Build cell-level lookup JSON from DPM YAML
python rag/dpm/build_dpm_cells.py

# 2. Build FAISS vector index (embeds all DPM datapoints). TAKES ABOUT 30+ minutes. Only run this once when you first clone the repo.
python rag/dpm/build_dpm_index.py

# 3. Build CRR3 FAISS index
python rag/crr/build_index.py
```

Output files are written to the `rag_cache` path (`~/.ai-timo/rag/dpm/` and `~/.ai-timo/rag/crr/` by default), so they survive `git pull` and are not committed to the repo.

### 7. Configure connections

Edit `connections.yaml` to point to your databases:

```yaml
connections:
  - name: banking
    type: duckdb
    database: ./sources/duckdb/test_bank.duckdb
    schemas: [src]         # optional: only extract these schemas

  - name: bird
    type: yaml
    file: ./mappings/target_catalogs/bird.yaml         # built by step 5

  - name: crdm
    type: yaml
    file: ./mappings/target_catalogs/crdm.yaml         # built by step 5
```

Supported types: `duckdb`, `yaml`.

- **duckdb** — Local DuckDB database file
- **yaml** — Pre-built YAML data catalog

### 8. Launch the app

#### Vue frontend
```bash
cd frontend
npm install
npm run dev
```
Opens at http://localhost:9000. Requires the FastAPI backend to be running (see below).

#### FastAPI backend
```bash
uvicorn api.main:app --port 8000
```
API docs at http://localhost:8000/docs. OpenAPI spec at [api/openapi.json](api/openapi.json).

> **Run only one backend at a time.** DuckDB is single-writer, so a second `uvicorn api.main:app`
> process will fail with a lock error and can interleave writes to any DuckDB-backed file still in
> use (source connection files under `sources/duckdb/`, and any governance store you've overridden
> back to its legacy `yaml`/`duckdb` backend — see [db/README.md](db/README.md); most governance
> data is PostgreSQL-backed by default today). Avoid `--reload`
> unless you understand the risk: its reloader spawns a worker child that holds the DuckDB lock, and
> killing only the parent orphans the child and leaves the lock held.

### 9. Build catalogs manually from the command line

```bash
# Build all catalogs (sources + targets)
python core/catalog_builder.py

# Build one specific catalog
python core/catalog_builder.py --name banking
python core/catalog_builder.py --name bird
```

### 10. Run the mapping agent manually from the command line

```bash
# Full run
python agents/mapping_agent.py

# Specific source/target pair
python agents/mapping_agent.py --source banking --target bird

# Dry run (no LLM calls)
python agents/mapping_agent.py --dry-run
```

---

## Project Structure

```
project.yaml          # Main configuration (sources, targets, agent settings)
connections.yaml      # Database connection configs
requirements.txt      # Python dependencies
foundry_client.py     # Single LLM client factory (Azure Foundry / OpenAI SDK)
persona.yaml          # Chat assistant persona/role config
AGENTS.md             # Instructions for AI coding agents
.env                  # API keys (gitignored)

db/                   # PostgreSQL governance database — see db/README.md
  docker-compose.yml  # Postgres 16 container (dev)
  alembic.ini         # Alembic config (DSN assembled in migrations/env.py, not stored here)
  migrations/         # Alembic migration scripts (glossary, catalog, dq_score,
                      #   semantic_type_assignment, reference_code, reference_sets,
                      #   audit_events, element_content, ...)

api/                  # FastAPI backend — the canonical data layer for BOTH UIs
  main.py             # App entry point, lifespan wiring of governance stores
  deps.py             # Shared dependencies (project/connections/stores)
  llm_errors.py       # Shared LLM-call error mapping
  sse_utils.py        # SSE streaming helpers (mapping/chat progress)
  semantic_types.py   # Semantic-type resolve/assign endpoints (top-level, not under routes/)
  openapi.json        # Generated OpenAPI spec
  openapi_gen.py      # Regenerates openapi.json
  routes/             # One module per route group: health, catalogs, discovery, mappings,
                      #   bird, chat, glossary, glossary_v2, element, audit, insights,
                      #   dashboard, settings, annotations, reference_data, reference_sets,
                      #   review_queue, documents
  schemas/            # Pydantic request/response models (annotation, catalog, chat,
                      #   discovery, glossary, mapping)

frontend/             # Vue 3 + Quasar + TypeScript + Vite target UI (dev port 9000)
  src/
    pages/            # Routed pages: HomePage, AssistantHomePage, DashboardPage,
                      #   DiscoveryPage, CatalogPage, AssetWorkspace, DataOnboardingPage,
                      #   MappingWorkspacePage, ChatPage, GlossaryPage, BusinessGlossaryPage (v2),
                      #   ReviewWorkspacePage, ReferenceDataspace, AuditPage, BirdKbPage,
                      #   RegulatoryKbPage, SettingsPage, AboutPage — plus colocated
                      #   display/formatting helpers (*Display.ts, dashboardPresets.ts,
                      #   assetWorkspaceDeepLink.ts)
    layouts/          # MainLayout.vue — single shell layout all routes render inside
    components/       # Shared components (TopMenu, SideMenu, panels, viz/, ...)
    stores/           # Pinia stores, one per domain (elementStore, glossaryStore,
                      #   glossaryV2Store, catalogStore, discoveryStore, mappingStore,
                      #   referenceDataStore, auditStore, birdKbStore, dashboardStore,
                      #   assistantChatStore, chatStore, personaStore, roleStore,
                      #   connectivityStore, annotationStore)
    api/              # Typed API client functions, one module per backend route group
                      #   (incl. glossaryV2.ts, bird.ts, dashboard.ts, documents.ts, sse.ts)
    composables/, utils/, config/, types/   # Shared composables, helpers, config, TS types
    router/           # Routes under a single MainLayout parent
    styles/           # tokens.scss (design tokens) + shared styles
  tests/              # Vitest + jsdom tests (frontend/tests/**/*.test.ts)

core/                 # Core infrastructure
  connectors.py       # Database connectors — DuckDB only (no Snowflake/other backends)
  catalog_builder.py  # Orchestrates schema extraction + profiling → catalog YAML
  catalog.py          # Catalog read/write utilities (yaml/postgres dispatch via catalog_backend)
  annotations.py, annotation_repo.py   # Table/column description annotations (yaml + Postgres repo)
  assessment.py       # Dataset assessment (scope + fingerprinting)
  chat_history.py     # Chat conversation persistence
  glossary.py         # Glossary read/write utilities (legacy yaml path)
  glossary_seeder.py  # LLM-powered glossary seeding from catalogs
  glossary_intake.py  # Glossary intake/normalisation
  glossary_db/        # Business Glossary v2 Postgres backend: db.py, models.py, read_api.py,
                      #   repository.py, status.py, migrate_from_yaml.py
  catalog_db/         # Source/target Catalog Postgres backend: db.py, repository.py,
                      #   migrate_from_yaml.py
  document_store.py   # Governed source-document index
  element_state.py    # Governance lifecycle state per data element (yaml/postgres dispatch)
  element_lifecycle_repo.py, element_lifecycle_migrate.py   # Postgres Interpretation-lifecycle
                      #   repo (review_subject/review_task/lifecycle_transition) + one-time migrator
  element_content_repo.py   # Postgres-backed per-element content (descriptions, etc.)
  lifecycle.py, lifecycle_vocab.py   # Canonical Interpretation-lifecycle state machine + vocabulary
  governance_events.py# Governance event log
  insights.py         # Cross-catalog insights
  bird_kb.py          # Shared read connection for the BIRD Knowledge Base (Postgres `bird` schema)
  # Data quality (Postgres-only — no YAML fallback)
  dq_service.py, dq_scorer.py, dq_dataset_scorer.py, dq_score_store.py, dq_score_repo.py,
  dq_config.py, dq_archetype.py, dq_remediation.py   # DQ scoring engine + persistence
  # Semantic types (assignments are Postgres-only; governed vocabulary stays YAML)
  semantic_types.py, semantic_type_store.py, semantic_type_repo.py, semantic_resolver.py,
  shape_detectors.py, type_validators.py             # Semantic-type resolution framework
  # Reference data
  reference_set_store.py, reference_set_repo.py      # Governed shared reference sets
                      #   (Postgres-only since Slice F; governance/reference_sets.yaml retired)
  reference_code_repo.py, reference_code_migrate.py  # Per-code Reference Data review (Postgres)
  reference_binding_review_repo.py   # Reference-set BINDING submit/approve lifecycle (Postgres)
  yaml_cache.py       # Cached YAML loading
  shared/             # Shared SQLAlchemy models + Postgres plumbing: base.py (shared Base),
                      #   glossary.py, governance.py, audit.py, catalog.py, db_availability.py,
                      #   json_utils.py
  audit/              # Audit store: store.py (DuckDB, legacy rollback), pg_store.py
                      #   (Postgres, default), events.py, migrate_from_duckdb.py
  extractors/         # Schema & profiling modules
    schema.py         # Schema extraction from DB / YAML loading
    profiler.py       # Column stats, constraints, data profiling

agents/               # AI agents (one file per LLM agent)
  mapping_agent.py    # LLM-powered column mapping agent (provider-dispatched _PROVIDERS)
  bird_mapping_agent.py # BIRD-specific mapping variant
  catalog_agent.py    # LLM-assisted catalog description drafting
  assessment_agent.py # Dataset assessment agent
  semantic_type_agent.py # LLM-assisted semantic-type suggestions
  chat_agent.py       # Conversational chat orchestrator
  crr_agent.py        # CRR regulation Q&A agent
  dpm_agent.py        # DPM (Data Point Model) Q&A agent
  glossary_agent.py   # Glossary enrichment agent
  agent_utils/        # Shared agent utilities
    crr_retrieval.py  # CRR RAG retrieval
    dpm_retrieval.py  # DPM RAG retrieval
    mapping_events.py # Mapping-agent progress event types
    mapping_sse.py    # SSE formatting for mapping-agent streaming

governance/           # Governance state — mostly gitignored runtime data; only two files
                      #   below are actually tracked in git (hand-authored config). The rest
                      #   are generated at runtime by the legacy yaml/duckdb rollback backends
                      #   and are never committed — some no longer exist at all:
  dq_scoring_config.yaml    # DQ scoring configuration (tracked)
  semantic_types.yaml       # Governed semantic-type vocabulary (tracked)
  element_states.yaml       # Per-element governance lifecycle state — gitignored; only
                      #   materializes if element_backend is flipped back to 'yaml'
  dq_scores.yaml            # Retired — DQ scores are Postgres-only, no YAML path left
  semantic_type_assignments.yaml   # Retired — assignments are Postgres-only, no YAML path left
  reference_sets.yaml       # Retired — reference sets are Postgres-only since Slice F; the old
                      #   hand-authored file was archived to docs/archive/yaml_migration/ (2026-08-18)

audit/                # audit.duckdb — gitignored runtime file, only created when audit_backend
                      #   is 'duckdb' (the legacy rollback); Postgres is the default today

knowledge_base/       # Structured knowledge assets
  bird/               # BIRD Knowledge Base source assets
    source/           # Raw ECB SMCube export (BIRD_all-frameworks_*.xlsx, gitignored)
    loader/           # bird_kb_loader.py (legacy DuckDB), bird_kb_postgres_loader.py (current —
                      #   loads the full export into the Postgres `bird` schema, see core/bird_kb.py)
    design/           # Design notes (lineage-traceability-findings.md, bird_kb_design_spec.md)

openspec/             # OpenSpec change-management workflow (specs + changes)

rag/                  # Retrieval-Augmented Generation indexes
  crr/                # CRR3 regulation index (FAISS)
  dpm/                # DPM 2.0 data model index (FAISS)

glossary/             # Business glossary source-of-truth
  glossary.yaml       # Categories → optional subcategories → terms
  glossary_meta.yaml  # Glossary metadata (last updated, seeding info)

chat_history/         # Persisted chat conversations as JSON (gitignored)

sources/              # Source catalog outputs (gitignored, auto-generated)
  generated/          # banking.yaml, ALM Bank.yaml, Faker.yaml, Kaggle.yaml + .annotations.yaml
  loader/             # Catalog/fixture generation scripts
    create_test_db.py                            # DuckDB fake bank data
    bird_to_duckdb.py, bird_to_yaml.py           # BIRD Excel → DuckDB → YAML pipeline
    crdm_to_yaml.py                              # CRDM DuckDB → YAML pipeline
    load_kaggle_to_duckdb.py                     # Kaggle CSVs → DuckDB
  duckdb/             # DuckDB fixture files (test_bank.duckdb, bird.duckdb, crdm.duckdb, almb_faker_kaggle.duckdb)
  original/           # Raw source files (xlsx/xlsm/csv/json)
  qa/                 # check_qa_profile_numeric.py — manual profiler sanity check

mappings/             # Target catalogs + AI-generated mapping outputs (gitignored)
  target_catalogs/    # bird.yaml, bird.annotations.yaml, crdm.yaml — frozen target
                      # schema definitions (BIRD IL / CRDM), kept for the existing
                      # Mapping page until the new BIRD-KB-based Mapping Workspace replaces it
  results/            # banking_to_bird.yaml, banking_to_crdm.yaml, etc. — mapping agent outputs
```

---

## Main Components

### FastAPI Backend (`api/`)

The canonical data/service layer that serves the Vue frontend — all data access goes through it.
Exposes `core/` and `agents/` functionality over HTTP with one route module per domain (health,
catalogs, discovery, mappings, bird, chat, glossary + glossary_v2, dashboard, annotations, element,
audit, insights, reference data, reference sets, review queue, documents, settings). Uses SSE
streaming to report mapping progress. Governance stores (audit, element state, semantic types,
reference sets, reference-code review, documents, DQ scoring) are wired up at startup in
`api/main.py`. API docs at `http://localhost:8000/docs`; the generated spec lives in
[api/openapi.json](api/openapi.json).

> **DuckDB is single-writer** — only one `uvicorn api.main:app` process may run at a time, or the
> DuckDB lock will error and writes can corrupt any DuckDB-backed store still in use (source
> connection files, or a governance store you've overridden back to `yaml`/`duckdb` — most
> governance data is PostgreSQL-backed by default, see [db/README.md](db/README.md)).

### Vue Frontend (`frontend/`)

Vue 3 + Quasar 2 + TypeScript + Vite (dev server port 9000), Pinia stores. The target and only UI,
covering Discovery, Data Catalog, Mapping, Asset Workspace, plus data-quality and governance views.
Talks to the FastAPI backend via typed clients in `src/api/`. Conventions are documented in
[.github/instructions/frontend.instructions.md](.github/instructions/frontend.instructions.md).

### Catalog Builder (`core/catalog_builder.py`)

Extracts database schemas and enriches them with column-level statistics (row count, null count, distinct count, min/max, sample values). Produces unified catalog YAML files used by the mapping agent.

- Extracts schema directly from DB via `information_schema` (DuckDB)
- Loads pre-built YAML catalogs for targets
- Supports `schema_only: true` for targets that have schema metadata only
- Respects `schemas` filter in `connections.yaml`

### Connectors (`core/connectors.py`)

Database connector abstractions with a unified interface:

- **DuckDBConnector** — Local DuckDB files, extracts PK/FK from `duckdb_constraints()`

All connectors output a unified catalog structure with:
- `primary_key` — list of PK column names
- `foreign_keys` — flat list of FK column names
- `relations` — detailed relationship info (`reference_table`, `columns`, `reference_table_columns`)

### Agents (`agents/`)

- **mapping_agent.py** — LLM-powered column mapping (source → target). Pre-filters by token overlap, returns 3 ranked candidates per source table with confidence scores. Provider-dispatched via `_PROVIDERS` (`azure`/`openai`/`gemini`).
- **bird_mapping_agent.py** — BIRD-specific mapping variant with tailored prompts.
- **catalog_agent.py** — LLM-assisted drafting of table/column descriptions.
- **assessment_agent.py** — Dataset assessment (scope + fingerprinting).
- **semantic_type_agent.py** — LLM-assisted semantic-type suggestions.
- **chat_agent.py** — Conversational orchestrator that routes queries to specialized agents.
- **crr_agent.py** — CRR3 regulation Q&A using RAG over article text.
- **dpm_agent.py** — DPM 2.0 data model Q&A using RAG over DPM cells.
- **glossary_agent.py** — LLM-driven glossary enrichment.

### Data Governance (`core/` + `db/`)

The Data Governance layer is the part of the platform lifecycle that is built today. Its state is
PostgreSQL-backed by default (see [db/README.md](db/README.md)); legacy YAML/DuckDB files under
`governance/` remain as a per-store rollback switch except where noted:

- **Data quality scoring** (`dq_service.py`, `dq_scorer.py`, `dq_dataset_scorer.py`,
  `dq_score_store.py`) — scores datasets/elements and persists results to Postgres
  (`dq_score`/`dq_score_history`; **Postgres-only**, the legacy `governance/dq_scores.yaml` has
  been retired); scoring configuration itself stays in `governance/dq_scoring_config.yaml`.
- **Semantic types** (`semantic_types.py`, `semantic_resolver.py`, `type_validators.py`,
  `shape_detectors.py`, `semantic_type_store.py`) — resolves columns to semantic types via
  validators, structural shape detectors, and name evidence, with tiered confidence thresholds
  (see `semantic_type_resolver` in `project.yaml`). Assignments persist to Postgres
  (**Postgres-only**, `governance/semantic_type_assignments.yaml` retired); the governed type
  vocabulary itself stays in `governance/semantic_types.yaml`.
- **Element lifecycle state** (`element_state.py`) — governance disposition (draft/submit/approve/
  ...) per data element; Postgres by default (`element_backend`), `governance/element_states.yaml`
  kept as the rollback.
- **Reference sets** (`reference_set_store.py`, `reference_set_repo.py`) — governed shared code
  lists a source field can bind to; **Postgres-only** since the Slice F cutover (no `project.yaml`
  flag, no YAML fallback) — the legacy `governance/reference_sets.yaml` hand-authored file was
  retired and archived once the migration proved stable. Per-code Reference Data review (the
  binding target's individual code rows) is a separate, Postgres-backed-by-default store
  (`refdata_backend`, `reference_code_repo.py`).
- **Audit** (`core/audit/`) — change history for all governed edits; Postgres by default
  (`audit_backend`), the legacy `audit/audit.duckdb` kept as the rollback.
- **Source/target Catalog** — schema + profiling metadata; Postgres by default (`catalog_backend`),
  the legacy `sources/generated/*.yaml`/`mappings/target_catalogs/*.yaml` files kept as the
  rollback.
- **Profile reset** (`core/profile_reset.py`) — returns a dataset/table, or an entire source, to
  the same pre-profiling shape a freshly onboarded (never profiled) table already has: catalog
  stats, semantic types, DQ scores, Interpretation (descriptions/business names/review status),
  Reference Data, reference-set bindings, and annotations are all cleared, while schema, column
  names/types, and declared keys are preserved. Exposed as a "Reset Profile" action in the Asset
  Workspace at both table and source level; the whole operation is one atomic transaction per
  call (a source-level reset spans every table in it), so a failure anywhere rolls back
  everything with nothing changed. **Postgres-only** — no YAML-mode support, by design.

### BIRD Knowledge Base (`core/bird_kb.py` + `knowledge_base/bird/`)

The full ECB BIRD SMCube export (all data models, all nine frameworks, 60 sheets) loaded
faithfully — no renaming, reshaping, filtering, or invention — into its own `bird` schema in the
same PostgreSQL database as the rest of governance data (migration `0019_bird_knowledge_base`,
loaded via `knowledge_base/bird/loader/bird_kb_postgres_loader.py`). Replaces the standalone
DuckDB file (`knowledge_base/bird/data/bird_kb.duckdb`, now legacy) so the KB — which *is* the
target data model for mapping — lives alongside everything else instead of a side file only one
page could read. `BIRD_KB_FRAMEWORKS` scopes the read endpoints (`api/routes/bird.py`) to BIRD +
AnaCredit only; the same schema also holds eight other frameworks (FINREP, Asset Encumbrance,
Securities Holdings Statistics, ...) as seed data for a future Regulatory KB, not yet exposed.
Browsable in the frontend via `BirdKbPage.vue` / `RegulatoryKbPage.vue`.

### RAG Indexes (`rag/`)

FAISS-based retrieval indexes for regulation and data model knowledge:

- **crr/** — CRR3 articles index (build with `build_index.py`)
- **dpm/** — DPM 2.0 data point model index (build with `build_dpm_index.py`)

### Configuration (`project.yaml`)

Central config file controlling:

- Sources and targets (names, connections)
- Output paths for catalogs and mappings
- Agent settings (provider, model, temperature, `max_target_tables`, rate limits)
- `database:` block — PostgreSQL connection (host/port/name/user/schema; password via
  `ADM_DB_PASSWORD`) and the per-store backend flags (`glossary_backend`, `element_backend`,
  `refdata_backend`, `audit_backend`, `catalog_backend`), each also overridable per-process via its
  own `ADM_*_BACKEND` env var — see [db/README.md](db/README.md)
