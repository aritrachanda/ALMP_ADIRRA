## 1. Resolve the blocking design question (before any code)

- [ ] 1.1 **BLOCKING — D1: decide what happens to the four fields B1's table cannot store.**
      Measured across all 2,290 live records (2026-08-14): `score_breakdown` (1,703 non-null),
      `resolution_reason` (443), `nearest_candidates` (23), `data_fingerprint` (49, legacy/stale).
      Present the three candidate resolutions from design.md D1 to the user, with the recommendation
      (option b: add columns for the three live fields, drop the dead `data_fingerprint`). **Do not
      write any code, and do not run any migration, until the user chooses.** This is a data-model
      decision and the user reviews SQL personally.
- [ ] 1.2 Confirm with the user that D2 (history table starts empty — no fabricated windows) reads
      correctly to them, since it differs from A2's newest→current/older→history mapping and is the
      one place where "B2 is like A2" would be a wrong assumption.

## 2. Schema (only if D1 requires it)

- [ ] 2.1 If D1 chooses (a) or (b): write the next-numbered Alembic migration adding the agreed
      columns to `semantic_type_assignment` — `score_breakdown` JSONB, `nearest_candidates` JSONB,
      `resolution_reason` TEXT (+ `data_fingerprint` TEXT only under option (a)). Full
      `COMMENT ON COLUMN` coverage in plain language, per the S0 standing rule. Keep the revision
      id ≤ 32 characters (see conventions.md — `alembic_version.version_num` is VARCHAR(32)).
- [ ] 2.2 Mirror those columns onto `SemanticTypeAssignment` in `core/shared/models/governance.py`.
- [ ] 2.3 Add the new fields to `_RECORD_FIELDS` in `core/semantic_type_repo.py` so they round-trip
      through `get()`/`set_record()` like every other field.
- [ ] 2.4 Apply to the real `adm` database AND to `adm_test`, then clear
      `db/migrations/__pycache__` — the two Alembic gotchas recorded in conventions.md from B1.

## 3. Migration script

- [ ] 3.1 Create `core/semantic_type_migrate.py` with `migrate_semantic_types()` + `parity_rows()`
      and a CLI entry point, mirroring `core/dq_score_migrate.py`'s established shape.
- [ ] 3.2 Migrate one current row per key; carry `latest_proposal` verbatim (67 records, D3); leave
      `system_deduced_type` null everywhere (D4 — 0 records carry a real value today).
- [ ] 3.3 Write zero `semantic_type_assignment_history` rows (D2). Assert this explicitly rather
      than leaving it implicit.
- [ ] 3.4 Idempotent by default; `--force` truncates and re-migrates (D6).
- [ ] 3.5 Never open the source YAML for writing — read-only for the whole run.

## 4. Parity

- [ ] 4.1 Compare every key through the REAL stores: `SemanticTypeStore.get()` in YAML mode vs
      `SemanticTypeRepo.get()` in Postgres mode (D5), not a re-parse of the file.
- [ ] 4.2 Report field-level mismatches per key; never pass silently on a difference.
- [ ] 4.3 Run against the real `adm` database and capture the full report for the user.

## 5. Tests

- [ ] 5.1 Postgres-gated `tests/test_semantic_type_migrate.py` against `adm_test`, built on a
      fixture created through the REAL `SemanticTypeStore` (not hand-rolled dicts) — same standard
      as `tests/test_dq_score_migrate.py`.
- [ ] 5.2 Cover: single-key migration, `latest_proposal` preservation, idempotency, `--force`
      replacement, parity pass, and parity correctly FAILING on an injected mismatch.
- [ ] 5.3 Assert `semantic_type_assignment_history` is still empty after a full migration (D2).
- [ ] 5.4 Assert the source YAML file is unmodified after a `--force` run.
- [ ] 5.5 Every existing semantic-type test still passes unmodified.

## 6. Gates, measurement, and review

- [ ] 6.1 Run the full backend test suite (server stopped). Expect 568+ passing, no new failures.
- [ ] 6.2 Measure `SemanticTypeStore` construction time in BOTH modes and report both numbers.
      Do not assume the postgres-mode guard works because B1 wrote one — A1 shipped exactly this
      bug (`DQScoreStore.__init__` still parsed the file after the flip). Prove it.
- [ ] 6.3 Re-run the migration with `--force` immediately before handing over, so parity is proven
      against the file's final state rather than a stale snapshot.
- [ ] 6.4 Update `/memories/repo/postgres-migration.md` with the outcome.
- [ ] 6.5 **STOP for user review — do not commit, and never flip the flag.** Present the parity
      report and both startup measurements. Flipping `semantic_backend: postgres` in `project.yaml`
      is the user's decision alone (standing rule §4.1).
