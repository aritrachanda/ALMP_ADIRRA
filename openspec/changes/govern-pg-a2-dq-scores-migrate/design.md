## Context

`governance/dq_scores.yaml` has 2,382 keys (2,290 column scores, 92 dataset roll-ups), 2,460 total
records, ~18 MB on disk. Only 45 keys have ever been re-scored to a genuinely different value/
state/signal (i.e. have more than 1 record — 78 historical records total across those 45 keys);
the remaining 2,337 keys have exactly 1 record each (never re-scored). Every one of the 2,382
current records has `state: "scored"` today — no key is presently sitting in the `unscored` gap
state A1's design added support for, though the schema must still handle it correctly for any
future column that goes out of scope.

Slice A1 (committed, `639fe3a`) already built `dq_score`/`dq_score_history` with real SCD2 windows
and `DQScoreRepo`, fully dormant. This slice is data-migration only — no new tables, no new
application code paths, no changes to `core/dq_service.py`/`api/main.py`/`core/dq_score_store.py`/
`core/dq_score_repo.py`.

## Goals / Non-Goals

**Goals:**
- Migrate every YAML record into the correct table (newest → `dq_score`, older →
  `dq_score_history`) with a real, correct SCD2 window on every historical row — no sentinels,
  no approximation.
- Prove parity: every key's current score/state/grade/breakdown_version and history row count
  must match `DQScoreStore.latest()`/`.history()`'s YAML-mode output exactly, with zero mismatches
  before recommending the user flip the flag.
- Idempotent, `--force`-gated re-runnability (same convention as every prior migration script in
  this codebase), so a second run (e.g. after the app wrote more scores since the first run) is
  safe and doesn't double-insert.

**Non-Goals:**
- No flag flip — that is exclusively the user's decision (`docs/governance-postgres-migration.md`
  §4.1, standing rule: "the agent never flips it").
- No changes to the scoring engine, `DQScoreStore`, or `DQScoreRepo` — A1 already built and tested
  these; this slice only feeds them real data.
- No fold-in work yet (retiring `_replace_with_retry`, wiring DQ re-scoring into bulk rebuild) —
  those only make sense to do AFTER the user flips the flag and confirms it's stable; per
  `docs/governance-postgres-migration.md`'s A2 fold-in list, they are explicitly deferred to that
  point, not part of this change's automated scope.

## Decisions

**D1 — Derive every migrated `valid_from`/`valid_to` directly from each YAML record's own
`scored_at` — no sentinel needed.** Unlike `reference_code`'s backfill (where a pre-existing
approved value's true real-world origin predates ADM ever tracking it, justifying a far-past
placeholder), every DQ score record's `scored_at` is a genuine, precisely-known timestamp of when
the scoring engine actually computed it — there is no "unknown true origin" to approximate. For a
key's history list (newest-first, index 0 = current): record `i`'s `valid_from` = record `i`'s own
`scored_at`; record `i`'s `valid_to` (for every `i > 0`, i.e. every record except the current one)
= record `i-1`'s `scored_at` (the moment the next-newer record superseded it). This exactly
mirrors the live `_close_current_into_history()`/`record()` behavior A1 already built and tested —
migration and live-write paths produce identically-shaped windows, not two different conventions.

**D2 — Single-key-at-a-time transaction, not one giant transaction.** Each key's current-plus-
history rows are written in their own `session_scope()` block, mirroring
`core/reference_code_migrate.py`'s per-field pattern. Alternative considered: one transaction for
the whole 2,382-key migration — rejected because a mid-run failure would roll back everything
already-correctly-migrated, forcing a full re-run of all 2,460 records instead of only the
un-migrated remainder; per-key transactions let `--force`-less re-runs skip keys already present.

**D3 — Parity is computed by calling `DQScoreStore.latest()`/`.history()` directly against the
YAML file, not by re-parsing the YAML separately.** Reusing the exact same read path the live app
uses (rather than writing a second, parallel YAML-parsing routine) guarantees the parity check
compares against the TRUE current behavior of the YAML store, not a re-implementation that could
silently drift from it — same reasoning as why A1's parity test called the real
`DQScoreStore`/`DQScoreRepo` methods instead of asserting against raw dicts.

**D4 — `key_kind` is derived from the key's own shape (pipe count), identical to A1's `DQScoreRepo`
logic** — not re-decided or looked up from anything else. `source|schema|table|column` (3 pipes)
is `column`; `source|schema|table` (2 pipes) is `dataset`. This is a pure, stateless function
already proven in A1's tests; the migration script reuses `DQScoreRepo._key_kind()` rather than
duplicating the rule.

**D5 — Idempotency check is per-key existence, not a blanket `--force` requirement.** A non-forced
run skips any key that already has a `dq_score` row (assumes it was already migrated correctly);
`--force` truncates `dq_score`/`dq_score_history` first (cascade via the FK) and re-migrates
everything from scratch. Mirrors `reference_code_migrate.py`'s exact `--force` semantics.

## Risks / Trade-offs

[Risk] The migration reads `governance/dq_scores.yaml` while the live app (still in `yaml` mode)
could concurrently be writing to it (e.g. a background rebuild-all-profiles run).
→ Mitigation: same accepted risk profile as every prior migration script in this codebase — the
documented recommended flow is "stop the backend or avoid concurrent writes during migration,
re-run with `--force` if the app wrote since the last run" (already how `reference_code`/glossary/
catalog migrations are operated), not a new risk this slice introduces.

[Risk] 45 keys with multi-version history means 78 `dq_score_history` rows to migrate correctly —
small in absolute count, but exactly the code path most likely to have an off-by-one window bug
(valid_to should equal the NEXT newer record's scored_at, not its own).
→ Mitigation: the parity check directly compares migrated `history()` length AND each window's
values against the YAML source per key — an off-by-one would show up as a length mismatch or a
wrong dq_score at a given history position, not silently pass.

[Risk] Retention: YAML's own `max_records` pruning (default 50, keep-baseline+latest-49) means some
keys' true oldest-ever record may already be gone from YAML — nothing this migration can recover,
since it only has what YAML still has.
→ Mitigation: not a regression — Postgres will hold exactly the same history depth YAML already
holds today, no better and no worse. Retention going forward (post-flip) is enforced by
`DQScoreRepo`'s own pruning (A1), independently.

## Migration Plan

1. Write `core/dq_score_migrate.py` + `parity_rows()`/`migrate_dq_scores()` (or similarly-named)
   functions, CLI entry point.
2. Run against `adm_test` in a new Postgres-gated test file, asserting parity across a synthetic
   YAML fixture (multi-record keys, single-record keys, a dataset key, a `state: unscored` key if
   representable) — not against the real 2,382-key file (too slow/heavy for a unit test; the real
   file is exercised in step 3 instead).
3. Run against the REAL `adm` database (agent-run), review the parity report with the user.
4. Pin `ADM_DQ_BACKEND=yaml` in `tests/conftest.py`.
5. Full backend suite gate.
6. STOP — present the parity report to the user. The user decides whether/when to flip
   `dq_backend: postgres` and restart; this change's automated scope ends before that point.

**Rollback:** set (or leave) `dq_backend: yaml`, restart. `governance/dq_scores.yaml` is never
modified or deleted by this migration — it remains the untouched, permanent safety net regardless
of how many times the migration script runs.

## Open Questions

None outstanding.
