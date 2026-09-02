## Context

Today, profiling-derived and governance state for a data element/table is spread across seven
independently-evolved Postgres repos, each keyed by the same composite string
(`source|schema|table|column`, built by each repo's own `key()`/`make_key()` static method), but
none of them expose a bulk "delete everything for this table/source" operation:

| Store | Module | What it holds |
| --- | --- | --- |
| Catalog | `core/catalog_db/repository.py` (`CatalogDataset`/`CatalogElement`) | Profile stats (row/null/distinct counts, min/max, samples, code values) — plus onboarding-owned structure (column names, `data_type`, declared PK/FK/relations) that reset must NOT touch, see D5 |
| Semantic types | `core/semantic_type_repo.py` | `semantic_type_assignment` rows |
| DQ scores | `core/dq_score_repo.py` | `dq_score` + `dq_score_history` rows (column-level and dataset rollup) |
| Interpretation lifecycle | `core/element_lifecycle_repo.py` | Status (draft/submitted/approved/...) + submission overlay |
| Interpretation content | `core/element_content_repo.py` | Descriptions, business names, data stories, assessment scope |
| Reference Data (per-code) | `core/reference_code_repo.py` | Per-code review rows |
| Reference-set binding | `core/reference_set_repo.py` + `core/reference_binding_review_repo.py` | Column → shared set binding + its submit/approve status |
| Annotations | `core/annotation_repo.py` | AI-drafted/user-edited table & column descriptions |

The existing precedent for a cross-store, per-table operation is `refresh_table_profile` /
`rebuild_source_profiles` in `api/routes/discovery.py`: both call small, independently-guarded
per-store helper functions (`_resolve_table_semantic`, `_rescore_table_dq`) in sequence, each
wrapped so one store's failure is logged but never aborts the others or the whole response. This
design reuses that same shape for the opposite direction (clearing instead of computing).

All affected stores are Postgres-only in practice today (no YAML fallback needed per user
decision) and are exercised in the test suite as "Postgres-gated" tests against a throwaway
`adm_test` database (see `tests/test_dq_score_repo.py`'s `_pg_available()` / `_adm_test_db`
fixture pattern) — the same pattern this change's tests and dummy-source fixture will follow.

## Goals / Non-Goals

**Goals:**
- One orchestrator, `core/profile_reset.py`, with two entry points: `reset_table(source, schema,
  table)` and `reset_source(source)` (which internally calls `reset_table` for every table the
  catalog currently knows about).
- Enumerate the column list for a table from the *current* catalog before any store is cleared —
  the catalog is the only place that still has the column list once its own stats are wiped.
- Clear, per column: semantic type, DQ score (+ history), interpretation lifecycle + content,
  reference-code rows, reference-set binding + binding review, annotations. Clear, per table:
  the dataset-level DQ rollup row and the catalog's own table-level stats.
- Atomic per table: every store's clear for one table runs inside a single shared database
  transaction, so a failure anywhere rolls the whole table's reset back to its pre-reset state
  (see D3).
- Soft reset (close the SCD2 window) wherever a store already has history; hard delete only for
  the stores that deliberately have none (see D9).
- Idempotent: calling reset twice on already-blank data is a no-op, not an error.
- One audit event per reset call (source- or table-scoped), logged via the existing
  `AuditStore.log_business` path — append-only, this feature never deletes audit rows.
- New endpoints mirroring the existing `refresh`/`rebuild-all` pair:
  `POST /discovery/{dataset}/{table}/reset` and `POST /discovery/{dataset}/reset`, streaming
  progress over SSE (see D6).
- A single authoritative "is this dataset profiled?" helper that every caller uses (see D11).
- New Asset Workspace UI actions (source + table level) behind a confirmation modal, reusing the
  visual pattern of the existing "Rebuild all profiles" warning card.
- A test-only dummy-source fixture that seeds ~10 records into each of the seven stores under a
  throwaway source name, so the whole reset flow can be verified without touching any real
  project.yaml source.

**Non-Goals:**
- No YAML/DuckDB implementation for any store — Postgres-only, per user decision.
- No purging of audit history — the reset action is logged, never subtracted from.
- No re-extraction of schema/connection metadata. Column names, `data_type`, `description`, and
  **declared** `primary_key`/`foreign_keys`/`relations` are onboarding's output, not profiling's,
  and are left intact. Only the profiling-derived counterparts (`inferred_primary_key`,
  `inferred_relations`, `orphan_fk_count`, and the statistical columns) are cleared. An earlier
  draft of this design proposed re-running onboarding-time extraction during reset; that is
  explicitly retracted (see D5).
- No SCD2 consolidation of the current+history table pairs, no reset-snapshot pruning exemption,
  and no undo/restore UI — all deferred (see D12).
- No automatic re-trigger of profiling after a reset — reset and "Refresh Profile"/"Rebuild all
  profiles" remain two separate, explicit user actions.
- No changes to `core/governance_events.py` (in-process pub/sub, nothing persisted, nothing to
  clear) or to Business Glossary terms (glossary terms are not per-element profiling state).

## Decisions

**D1 — Orchestrator lives in `core/`, not `api/`.** `core/profile_reset.py` takes plain
arguments (source/schema/table, an already-loaded catalog dict for column enumeration) and
returns a plain result dict (counts cleared per store + any per-store errors). The two new
`api/routes/discovery.py` endpoints are thin wrappers, exactly like today's `refresh`/`rebuild-all`
delegate their real work to functions that don't import FastAPI. Keeps the orchestrator unit
testable without a running app, and reusable from a future CLI/script if ever needed.

**D2 — Column enumeration order: catalog read happens first, catalog clear happens last.** The
orchestrator loads the table's current column list up front (same `load_catalog_dispatch` call
`refresh_table_profile` already uses), runs every *other* store's clear using that column list,
and only clears the catalog's own stats last. Ordering is child-before-parent, so the catalog —
the "is this profiled at all" signal every reader keys off (D11) — is the last thing to change.
Because the whole sequence is one transaction (D3), a failure at any point leaves nothing
changed, so ordering is about correctness of enumeration, not damage limitation.

**D3 — One shared transaction per table, with automatic rollback.** All seven stores share the
same Postgres engine and session factory (`core.glossary_db.db.session_scope`, database `adm`),
so a genuine cross-store transaction is essentially free: the orchestrator opens one session,
passes it into every store's clear call, and commits once at the end. Any failure rolls the whole
table's reset back — no bespoke undo logic, no snapshot-and-replay, because nothing was ever
committed. This supersedes an earlier "best-effort, collect per-store errors" draft, which would
have permitted a half-reset dataset (DQ cleared but semantic type still confirmed).

Source-level reset is **atomic for the whole source, not per table** (user decision, overriding
an earlier "per-table, loop continues past a failure" draft that mirrored
`rebuild_source_profiles`): every table's clear runs inside the SAME shared session/transaction
as the source-level reset call, and a single failing table rolls back every table's work, not
just its own. This trades `rebuild_source_profiles`'s "keep going, report per-table failures"
behavior for an honest all-or-nothing guarantee — a source-level reset never leaves some tables
cleared and others untouched. The trade-off (a large source holds its transaction/locks open for
the whole pass) is accepted; see Risks.

**D4 — New repo methods are additive, narrow, and named consistently:
`clear_for_table(source, schema, table)` and `clear_for_source(source)`.** Each of the seven repos
gets exactly these two new methods (the "source" variant just loops or issues a `WHERE source =`
delete — repo's choice). No existing method on any repo changes signature or behavior. This keeps
the surface area small and matches the existing "one repo, one store" boundary the codebase
already has (no repo currently reaches into another repo's tables).

**D5 — Catalog reset clears a NEW, narrower `PROFILE_DERIVED_FIELDS` list — it must NOT reuse any
existing stat-field list.** Three overlapping "profiling stats" lists already exist:
`DATASET_STAT_FIELDS`/`ELEMENT_STAT_FIELDS` (`core/catalog_db/repository.py:45-62`, used for
change-fingerprinting and the snapshot payload) and `_PROFILE_STAT_KEYS`/`_COL_STAT_KEYS`
(`core/catalog.py:159-171`, the YAML patch path). **All of them include `description`,
`data_type`, `primary_key`, `foreign_keys`, and `relations`** — precisely the fields that must
survive a reset. They exist to answer "did the stats change?", which is a different question from
"what does reset clear?". Reusing them would wipe declared PK/FK (breaking the Data Model tab) and
`data_type` (breaking column-type display).

The provenance rule: *reset clears what came from reading the data; it preserves what came from
onboarding-time metadata extraction.*

| | Preserve (onboarding) | Clear (profiling) |
| --- | --- | --- |
| Dataset | `schema_name`, `table_name`, `description`, `primary_key`, `foreign_keys`, `relations`, `origin_uri`, `ingested_at` | `row_count`, `row_count_error`, `inferred_primary_key`, `duplicate_count`, `duplicate_pct`, `orphan_fk_count`, `completeness_summary`, `pct_columns_described`, `profiled_at`; `profiling_status` → not-profiled |
| Element | `qualified_column_name`, `column_name`, `column_kind`, `nesting_level`, `ordinal`, `data_type`, `description` | all statistical columns (`null_*`, `distinct_count`, `uniqueness_pct`, `min_value`/`max_value`, `length_*`, `inferred_pattern`, `pattern_confidence`, `code_values`, `value_distribution`, `numeric_*`, `*_count`, `validator_pass_rates`, `constant_run_warning`, `sample_values`, `top_values`, `stats_error`) |

The resulting shape still matches `catalog_builder._schema_to_profile_tables` (what a never-profiled
table looks like), so a reset dataset and a never-profiled dataset remain indistinguishable to
downstream readers.

Two items to resolve during implementation: `inferred_relations` appears in `_PROFILE_STAT_KEYS`
but has no matching column on `CatalogDataset` — confirm whether it is YAML-only. And
`type_distribution`/`array_length_*` are structural discovery for nested/schema-on-read sources
(JSON, Parquet) but statistical for tabular ones — decide per connector.

**D5a — `fetch_constraints()` is metadata-only and is not profiling-dependent.**
`DuckDBConnector.fetch_constraints` (`core/connectors.py:166`) queries `duckdb_constraints()` and
reads no rows; `data_type` likewise comes from `information_schema.columns`, never from profiling.
`catalog_builder.build_catalog` already calls `fetch_constraints` in `schema_only` mode
(lines 162-172) but gates it to `schema_excel` connectors — a redundant allowlist, since
`BaseConnector.fetch_constraints` already returns `{}` by default (`connectors.py:53-71`).
Dropping that gate lets a never-profiled source carry its declared constraints, which is what makes
"preserve declared PK/FK on reset" consistent rather than preserving something a fresh onboard
never populated.

**D6 — Endpoints stream progress over SSE, reusing the `rebuild-all` pattern.** Reset touches
seven stores in a defined child-before-parent order, and the user requires visible, truthful
per-step progress ("which action is in progress"), so the operation reports rather than blocks.
Reuse the existing `started`/`progress`/`error`/`done` event shape and the progress-panel styling
already in `AssetWorkspace.vue` — no new streaming idiom. Every step (every store, for every
table) emits a `progress` event as it happens, but per D3 nothing actually commits until the
very end of the whole call (one commit for a table-level reset, one commit for an entire
source-level reset) — the progress stream is purely observational, not a sequence of small
committed steps. On failure the stream emits an event stating that everything was rolled back
and nothing changed. This supersedes an earlier "synchronous JSON, no progress reporting" draft.

**D7 — Confirmation UX mirrors `promptRebuildProfiles`/`startRebuildProfiles`, not a native
`confirm()`.** Consistent with the existing destructive-action pattern already in
`AssetWorkspace.vue`. Source-level reset gets the stronger confirmation (states the table count
that will be wiped); table-level gets a lighter one-click-confirm card. Neither requires
type-to-confirm text entry — the existing rebuild pattern doesn't use it either, and introducing
a new, stricter confirmation idiom for just this one action would be inconsistent with the rest
of the page.

**D8 — Dummy-source fixture is test-only, lives under `tests/`, and is never wired into
`project.yaml`.** It inserts directly into each repo's `adm_test` tables via the repos themselves
(not hand-rolled SQL), under a distinct source name (e.g. `profile_reset_dummy_source`) that
cannot collide with a real onboarded source. This both proves the repos' write paths work and
gives the reset orchestrator a real, inspectable fixture to clear in `tests/test_profile_reset.py`.

**D9 — Soft reset where SCD2 already exists; hard delete only where history was deliberately
omitted.** Audit is append-only (user decision), so a hard delete everywhere would record *that* a
reset happened while destroying the evidence of *what* was reset. Each store already has a
mechanism, so this costs almost nothing:

| Store | Reset mechanism |
| --- | --- |
| `dq_score` | Write `state='unscored'` with `reason='profile_reset'`. `dq_score_repo` already treats `scored → unscored` as a genuine gap-creating transition that closes the outgoing window into `dq_score_history`, and `as_of()` already guards the gap against a stale `valid_from` (see `core/dq_score_repo.py:11-13, 80-82, 126-128, 213-225`) |
| `reference_code` | `revoke_codes()` already closes windows into `reference_code_history` |
| `semantic_type_assignment`, `element_definition` | Close the open window (`valid_to = now`), blank the current row |
| `catalog_dataset` / `catalog_element` | `CatalogDatasetSnapshot`/`CatalogElementSnapshot` already exist and are already written by `upsert_table_profile()` — snapshot, then clear per D5 |
| `catalog_table_annotation`, `catalog_column_annotation`, `dataset_story`, `reference_set` / `element_reference_binding` | Hard delete — their model docstrings record explicit user decisions against having history |

**D10 — Reset writes only through repo methods, never raw SQL against current/history tables.**
This is what insulates the change from the future SCD2 consolidation (D12): when the current+history
pairs are merged, only repo internals move and no reset code changes.

**D11 — "Is this dataset profiled?" is answered in exactly one function,
`core.catalog_db.is_profiled()`.** Keyed on `catalog_dataset.profiling_status` alone, NOT also
`profiled_at` as originally planned — implementation surfaced that `save_catalog()` (a
whole-source rebuild) sets `profiling_status='profiled'` but never populates `profiled_at` (only
the per-table refresh path, `upsert_table_profile()`, does), so requiring both would misreport a
table as unprofiled immediately after a full catalog rebuild, independent of this change. Anything
other than `'discovered'`/absent counts as profiled (including `'failed'` — a profiling attempt
was made, even if it errored). The UI and API must never infer unprofiled state by counting rows
in the other stores. Without SCD2 consolidation, "unprofiled" is physically expressed three
different ways (`dq_score.state`, nulled catalog fields, absent rows elsewhere); funnelling the
question through one helper stops those representations drifting apart, and when the remodel
lands only that helper changes.

**D12 — SCD2 consolidation and full undo are explicitly deferred.** Recorded as tech-debt #4. This
change is scoped to: clear all seven stores at table + source level, single shared transaction with
rollback, SSE progress, audit event, UI confirmations, and unprofiled-state UI. Deferred: the
reset-snapshot pruning exemption, an undo/restore UI, and merging the current+history table pairs
into single SCD2 tables.

**D13 — The Data Model tab is three-state, not two.** Declared relationships render whenever the
connector supplies them (available pre-profiling per D5a); inferred relationships and orphan-FK
counts appear only after profiling; an empty state shows when neither exists. Specifying it as
"declared before profiling, inferred after" would ship a permanently blank diagram for the first
file-based source (CSV/Parquet on object storage, NoSQL, REST), none of which have declared
constraints.

## Risks / Trade-offs

- **[Risk] A store's clear silently no-ops instead of raising if the key format doesn't match
  exactly what the reset orchestrator built.** Every store finds its rows by a pipe-joined text key
  (`source|schema|table|column`). If reset builds that key even slightly differently from the code
  that wrote the row (wrong order, `None` vs `""` for schema, different casing), the delete matches
  **zero rows and still reports success** — the data is untouched but nothing crashes. →
  Mitigation: reuse each repo's own `key()`/`make_key()` static method for every lookup; never
  hand-format the key string in the orchestrator.
- **[Resolved] Partial failure leaving a half-reset dataset.** Eliminated by D3 — a table-level
  reset is one transaction, and a source-level reset is now ALSO one transaction spanning every
  table in it (user decision, superseding an earlier per-table-atomic draft) — so a failure
  anywhere rolls back the whole call and nothing changed. The SSE stream reports the rollback
  explicitly rather than implying a partial success.
- **[Trade-off] A whole-source reset holds one transaction open for as long as the largest source
  takes to clear.** Chosen deliberately (D3) over `rebuild_source_profiles`'s "keep going past a
  failed table" behavior, in exchange for an honest all-or-nothing guarantee at the source level.
  Unlike `rebuild_source_profiles` (which does live, per-table DB profiling and can genuinely run
  for minutes), a reset is a bounded set of deletes/nulls per table — expected to stay well within
  normal transaction/lock timeouts even for a large source. Revisit if a source turns out to have
  enough tables that this becomes a real operational problem.
- **[Retracted] Stale `schema_hash` after clearing catalog stats.** `schema_hash` is computed
  purely from column names and types, never from stats, so its value is identical whether or not a
  table has been profiled. The only reader, `ensure_catalogs()`, is not called anywhere in the
  running application. This risk does not apply.
- **[Risk] Unsubmitted drafts are irrecoverable.** `element_definition` and
  `semantic_type_assignment` only cut history rows on Interpretation Set *submission*, not on every
  save. A column with an unsubmitted draft definition therefore has no history record, so reset
  destroys it with nothing to restore from. → Mitigation: documented and accepted for this change;
  optionally cut a history row before blanking. This gap closes with tech-debt #4.
- **[Risk] A reset snapshot can be pruned away.** `_prune_snapshots`
  (`core/catalog_db/repository.py:86-103`) keeps the oldest plus the latest 49 and deletes the
  middle, so a pre-reset catalog snapshot is discarded after ~50 subsequent refreshes. → Accepted:
  the pruning exemption is deferred per D12, and no undo UI ships in this change, so nothing depends
  on that snapshot surviving. Documented so the deferral is a known choice, not a surprise.
- **[Trade-off] `PROFILE_DERIVED_FIELDS` (D5) becomes redundant later.** The identity/version split
  that comes with tech-debt #4 removes the need to curate any field list. ~40 lines of throwaway
  work, accepted as the cost of not blocking this change on a full data-model remodel.

## Migration Plan

No schema migration needed (no new tables/columns — every change is new methods on existing
repos operating on existing tables). Rollout is additive and reviewed like any other feature PR:
1. Add `clear_for_table`/`clear_for_source` to each of the seven repos, each accepting an injected
   session so the orchestrator can wrap them in one transaction (D3), independently testable.
2. Add the single "is this dataset profiled?" helper (D11).
3. Add `core/profile_reset.py` orchestrator + its own unit tests against the dummy-source fixture.
4. Wire the two new `api/routes/discovery.py` SSE endpoints (D6).
5. Wire the two new Asset Workspace UI actions + confirmation modals + progress panel.
6. Manual end-to-end verification against the dummy source before touching any real source.
No rollback mechanism is needed beyond normal git revert — nothing is deleted from the audit log,
and the feature is purely additive (new routes/buttons/methods), so reverting the change removes
the capability without affecting any other code path.

## Open Questions

- None outstanding. The three questions from the proposal discussion (annotations wipe, audit
  append-only, Postgres-only scope) plus the four raised during design review (silent-no-op
  explanation, rollback feasibility, `schema_hash` staleness, cross-store vs cross-repo) were all
  resolved by the user before this revision. Scope was confirmed as the trimmed set in D12.
- Two implementation-time confirmations remain, both noted in D5: whether `inferred_relations` has
  a real `CatalogDataset` column, and which side `type_distribution`/`array_length_*` fall on for
  nested/schema-on-read connectors.
