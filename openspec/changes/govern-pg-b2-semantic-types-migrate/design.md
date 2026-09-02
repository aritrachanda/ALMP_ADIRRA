## Context

B1 (committed `0f1f1e2`) built `semantic_type_assignment` (current row per column key) and
`semantic_type_assignment_history` (self-contained SCD2, one row per Interpretation Set
submission), plus `SemanticTypeRepo` mirroring `SemanticTypeStore`'s contract. Both tables exist
in the real `adm` database and are **empty** — nothing writes to them while `semantic_backend`
stays `yaml`.

B2 moves the real data in and proves it matches. Every number below was measured directly against
the live `governance/semantic_type_assignments.yaml` on 2026-08-14, not carried forward from an
earlier session's notes (the 2026-08-11 figures have already drifted with normal use:
confirmed 68→70, `latest_proposal` 50→67).

## Goals / Non-Goals

**Goals:**
- Migrate all 2,290 current records into `semantic_type_assignment` with zero data loss.
- Prove parity, field by field, against `SemanticTypeStore`'s YAML-mode output before any flip.
- Resolve the four-uncovered-fields gap (D1) explicitly, with the user, before data moves.

**Non-Goals:**
- No flag flip (user-owned, standing rule §4.1).
- No backfill of `semantic_type_assignment_history` — see D2; it correctly starts empty.
- No resolver/scoring behaviour change. B2 moves storage only.
- No deletion of `governance/semantic_type_assignments.yaml` — it stays intact as the permanent
  rollback safety net, exactly as `dq_scores.yaml` and the source catalogs did.

## Decisions

**D1 — OPEN, must be resolved with the user before any code: what happens to the four fields
B1's table cannot store?**

Enumerated across all 2,290 live records:

| Field | Coverage | What it holds |
| --- | --- | --- |
| `score_breakdown` | 2,290 present / 1,703 non-null | The resolver's scoring math for this column — `{base, final, tier, tier_label, adjustments, adjustment_total, adjustment_cap, adjustment_capped}`. Nested dict. |
| `resolution_reason` | 443 | Free-text explanation of how the column got resolved. |
| `nearest_candidates` | 23 | Runner-up types considered when nothing cleared the bar. |
| `data_fingerprint` | 49 | Legacy — the parallel fingerprint field that was merged away on 2026-08-12 (f8876ae). These 49 are stale leftovers, not live data. |

This gap exists because B1's table was built from `SemanticTypeStore.default_record()`'s field
list, which does not include these four — they are written by the resolver at runtime, not
declared in the default record. That is the same class of mistake as the 2026-08-05 lesson already
recorded in `docs/tech-debt.md` ("go to the actual writer, not a summary function"), and it is
being surfaced here *before* migrating rather than discovered afterwards.

Candidate resolutions (none chosen — for the user to decide):
  (a) **Add real columns for all four.** Faithful, no loss. Costs one more migration; `score_breakdown`
      would be JSONB (nested, versioned, shape has churned — same precedent as `dq_score.breakdown`
      and `term_version.attributes`), `nearest_candidates` JSONB (a list), `resolution_reason` TEXT,
      `data_fingerprint` TEXT.
  (b) **Add columns for the three live ones, drop `data_fingerprint`.** Same as (a) but treats the
      49 stale legacy values as genuinely dead (they are — the field was deliberately merged away
      in f8876ae) and lets them fall away with the migration.
  (c) **Migrate only what B1's table covers, accept the loss.** Cheapest, but silently discards
      1,703 columns' scoring math — directly contradicts the user's explicit 2026-08-13 direction
      ("must not miss out on things like this"). Listed only for completeness; not recommended.

Recommendation: **(b)**. It preserves everything real, and drops only the one field this codebase
already decided was redundant. But this is a data-model decision and the user reviews SQL
personally — no code until they choose.

**D2 — `semantic_type_assignment_history` starts empty. Nothing to backfill.**
Unlike `dq_scores.yaml` (a list of records per key, which A2 mapped to real SCD2 windows), this
file holds exactly one record per key and no history whatsoever. B1's history table opens a row
only at Interpretation Set submission — a governance event that did not exist as a recorded
concept before B1. Confirmed by measurement: **0 of 2,290 records carry `submitted_at`**, so there
is not even a partial signal to reconstruct windows from. Fabricating history rows from the
current state would invent business-effective dates that never existed — precisely what the SCD2
standing rule (§4.4) exists to prevent. The table therefore starts empty and fills from real
submissions after the flip. This is a deliberate decision, not an oversight.

**D3 — `latest_proposal` (67 records) migrates verbatim as JSONB.**
B1's table already has a `latest_proposal` JSONB column carrying the sticky-disposition mechanism
(a disposed record's later machine re-resolution parked underneath, never overwriting the
steward's decision). The 67 records carrying one migrate as-is, no reshaping.

**D4 — `system_deduced_type` migrates as null for every record.**
Measured: 1,971 records carry the *key* (added by `SemanticTypeStore._migrate_records`'s
`setdefault` at load time, introduced in B1) but **0 carry a real value**. That is correct and
expected — the field only populates the first time a steward *replaces* the machine's suggestion,
and B1 shipped only yesterday. Nothing to migrate; the column starts null everywhere.

**D5 — parity compares against the real `SemanticTypeStore`, not a re-parse of the YAML.**
Same approach A2 took: call the actual store's `get()` in YAML mode and the actual repo's `get()`
in Postgres mode, and diff the returned dicts. This proves the *contract* holds, not merely that
the file was copied — a re-parse could agree with the file while both disagree with what the
application actually serves.

**D6 — idempotent by default, `--force` to re-migrate.**
Identical to `core/dq_score_migrate.py`: skip keys that already have a row unless `--force`, which
truncates first. Lets the migration be re-run safely after the app writes more YAML during review.

## Risks / Trade-offs

[Risk] **D1 resolved wrongly loses real governance data.** 1,703 columns' scoring math is the
largest exposure.
→ Mitigation: D1 is blocking, user-decided, and the exact field coverage is measured and tabulated
above rather than estimated.

[Risk] **The YAML file keeps changing during review** — the live app writes to it on every
non-cache-hit resolve, so a parity report can go stale between the migration run and the flip.
→ Mitigation: `--force` re-run immediately before the flip, exactly as the glossary and DQ slices
did; parity is re-proven on the final state, not a snapshot.

[Risk] **Post-flip, the 6.5s startup parse should vanish — but A1 shipped a bug where it didn't**
(`DQScoreStore.__init__` still parsed the file in Postgres mode; the flag only skipped *using* the
result). B1 explicitly guarded against this in `SemanticTypeStore.__init__`.
→ Mitigation: measure construction time in both modes as an explicit task, don't assume the guard
works because it was written.

## Migration Plan

1. Resolve D1 with the user. No code before this.
2. If D1 requires columns: write the migration + ORM + repo field additions, apply to `adm`.
3. Build `core/semantic_type_migrate.py` + tests (pg-gated, `adm_test`).
4. Run against real `adm`; produce the parity report.
5. Re-run `--force`, re-prove parity, and measure startup cost in both modes.
6. STOP. Present parity + measurements. User decides on the flip.

**Rollback:** `governance/semantic_type_assignments.yaml` is never modified or deleted by any of
this. Flipping `semantic_backend` back to `yaml` and restarting fully restores the previous
behaviour, with no data loss, at any point.
