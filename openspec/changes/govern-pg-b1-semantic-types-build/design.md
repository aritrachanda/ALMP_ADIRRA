## Context

`SemanticTypeStore` (`core/semantic_type_store.py`) is a thread-safe YAML store, one record per
column key (`source|schema|table|column`). Record shape (~19 fields): `type_id`, `domain_role`,
`confidence`, `state` (`proposed`/`suggested`/`confirmed`/`rejected`), `source` (`rule`/`ai`),
`candidates`, `evidence`, conflict/format flags, `resolver_version`, `fingerprint`,
disposition fields (`confirmed_by`/`confirmed_at`/`rejected_by`/`rejected_at`/
`rejection_reason`/`corrected_type_id`). **`data_fingerprint` no longer exists as a separate field**
— folded back into the single `fingerprint` by the 2026-08-12 fix below (see D2). Real scale (measured 2026-08-11): 2,290 records (one per
column across 4 sources), state distribution `proposed=1235, suggested=403, unresolved=584,
confirmed=68, rejected=0`; 50 records carry a nested `latest_proposal` (a disposed — confirmed or
rejected — record that was later re-resolved with different underlying evidence; the disposition
itself is preserved, the machine's latest opinion is tucked underneath it, never overwriting the
steward's decision). A separate `priors` section (3 sources) holds learned per-token/type-id
patterns feeding the resolver's initiation logic — not part of the sticky-disposition machinery.

`set_record(record, *, preserve_disposed=True)` is the load-bearing rule: if the existing record's
`state` is `confirmed`/`rejected`, a new proposal is stored as `existing["latest_proposal"]`
instead of replacing the top-level record — the steward's decision is never silently overwritten.

`resolve_column()`'s cache-hit decision (the ACTUAL trigger for whether a real LLM/rule
re-evaluation happens) compares `existing.fingerprint == column_fingerprint(column, table_facts)`
(confirmed/rejected: fingerprint match alone is sufficient to skip) plus, for machine states
(`proposed`/`suggested`/`unresolved`), `existing.resolver_version == RESOLVER_VERSION` too.
`column_fingerprint()` used to include `_glossary_domain`/`_definition_state` — two governance
signals — alongside profiling stats; as of the 2026-08-12 fix (see D2) it no longer does (§
investigation below).

**Investigation finding (2026-08-11, this is why this slice exists in its current shape):**
Two facts, both verified directly against the real system, not assumed:
1. The catalog-stats side of the fingerprint is stable: two independent, uncached Postgres reads
   of the full catalog (2,290 columns, 4 sources) produced zero fingerprint differences.
2. The governance-signal side is NOT stable across call paths: `api/routes/element.py`'s single-
   column Element Detail handler enriches `col_dict` with `_glossary_domain`/`_definition_state`
   (from `_find_glossary_term()` + `element_state.get_description()`/lifecycle state) before
   calling `resolve_column()`. The Table Overview path (`_resolve_table_once` → `resolver.
   resolve_table()` → `resolve_column()`, same file) passes the RAW, un-enriched column dict for
   every column — never adding those two fields. A column with a confirmed glossary link or an
   approved definition therefore has TWO different "correct" fingerprints depending on which
   screen resolved it last, and visiting the other screen is a guaranteed cache-miss → real
   re-resolution. A prior fix (2026-08-10) added a parallel, governance-blind
   `data_only_fingerprint()` used ONLY for the progress-status *wording* ("Re-checking X...") —
   it explicitly left `column_fingerprint()`/the real cache-hit decision untouched, deferring the
   actual fix. This proposal pulled that fix into B1 (user's explicit direction).

>> RESOLVED 2026-08-12, COMMITTED (f8876ae) — see D2 below. Landed as part of a separate,
   broader fingerprint-churn investigation/fix (root cause was actually non-deterministic
   `sample_values` ordering, not this asymmetry — see `/memories/repo/semantic-fingerprint-fix-plan.md`),
   not as a standalone B1 commit, but it fully satisfies this slice's D2/fingerprint-consistency goal.
   The chosen approach was symmetry-by-removal (drop the 2 signals from the fingerprint AND from
   scoring, measured 0/54 real impact) rather than symmetry-by-unification (the enrichment function
   this doc originally proposed) — see D2's resolution note for the full reasoning.

## Goals / Non-Goals

**Goals:**
- Build a Postgres-backed `SemanticTypeRepo` reproducing `SemanticTypeStore`'s exact semantics
  (sticky disposition via `preserve_disposed`, the `latest_proposal` nesting, priors).
- Make `SemanticTypeStore` backend-aware without changing its public method signatures.
- ~~Fix the governance-signal enrichment asymmetry at its root...~~ **DONE 2026-08-12** (see D2) —
  fixed by removing the 2 governance signals from the fingerprint/scoring entirely, not by
  unifying two enrichment paths. No longer open work for this slice.
- Add regression tests proving fingerprint stability across repeated/independent catalog reads
  (codifying the investigation's empirical findings so they can never silently regress) — still
  relevant, now framed as "no path-dependent signal exists at all" rather than "both paths agree."

**Non-Goals:**
- No migration of real data, no flag flip (both B2).
- No change to the resolver's actual scoring/tiering/evidence logic beyond the 2026-08-12 removal
  already shipped (D2) — no further scoring changes in this slice.
- ~~No fix for the `fingerprint`/`data_fingerprint` parallel-field duplication (B3's own fold-in)~~
  — **already done 2026-08-12** as part of the same commit that resolved D2 (the two fields were
  always going to merge once the governance-signal split disappeared; there was nothing left to
  keep them separate for). Nothing remains for B3 here.

## Decisions

**D1 — RESOLVED 2026-08-13: window boundary = Interpretation Set submission, not disposition.**
Superseding the original 3 candidates below (kept for history). Through discussion the actual
mechanism landed on something more specific than any of the 3: a new `semantic_type_assignment_history`
row is written only when the **Interpretation Set is submitted** (`POST
/{source}/{table}/{column}/submit`, today's `submit_definition_for_review` in `api/routes/element.py`)
— not on every `confirm()`/`reject()` call, and not on every machine re-resolve. Rationale (the
user's own framing): a steward can Accept → Replace → Accept again multiple times in one editing
session before ever submitting; each of those individually still fires today's existing
`SEMANTIC_TYPE_CONFIRMED`/`REJECTED` audit events (unchanged, that lightweight "what happened, who
did it" trail stays as-is) but would be noisy/premature as a *governed history* entry. Submission is
the one moment "this is now official."

**Row shape — two named columns, not a nested trick.** Each row carries:
  - `system_deduced_type` — what the machine's own resolver currently thinks (confidence, tier,
    evidence travel with it), independent of any human decision.
  - `accepted_type` — whatever a human actually confirmed at submission time (null if the column
    somehow reached submission unconfirmed — see the backend-enforcement point below for why that
    shouldn't happen in practice).
  This replaces today's awkward nested `latest_proposal` — while a disposition stands, the machine
  can keep updating `system_deduced_type` on the *current* (not-yet-submitted) row in place; a new
  row is only appended at the next actual submission.

**Known gap found during discussion, must be fixed as part of this slice, not deferred:**
`SemanticTypeStore.confirm()`/`reject()` currently **overwrite** the record's `type_id` in place
when a steward picks a different type than the machine suggested ("Replace") — the machine's
original, pre-override suggestion is lost from the live record (recoverable only by replaying
`prior_type_id` out of the audit log, which is not a real design). Fix: `confirm()`/`reject()` must
capture the machine's pre-override type_id/confidence into an explicit `system_deduced_type`-shaped
field at the moment of the FIRST override, instead of relying on it being reconstructable after the
fact. Without this fix, `system_deduced_type` in the history row would be wrong/stale for any column
where a steward replaced (not just accepted) the machine's suggestion.

**Backend enforcement added to this slice's scope (2026-08-13, user-directed):** today's
`submit_definition_for_review` has **zero server-side validation** — the "description + business
name + accepted semantic type" gate (`submitGateMet` in `AssetWorkspace.vue`) is frontend-only.
There is already an exact precedent for the shape this should take: `submit_reference_codes` (same
file, ~L2779) already gates on an Accepted semantic type server-side —
```python
record = semantic_store.get(source, resolved_schema, table, column)
if not (record and record.get("state") == "confirmed"):
    raise HTTPException(status_code=409, detail="The semantic type must be Accepted before submitting reference codes.")
```
— and its own docstring literally says "matching the interpretation-set submit gate," meaning this
was already the intended design; it just was never actually built for the Interpretation Set route
itself. Fix: add the equivalent 409 check (semantic type confirmed, plus description and business
name non-empty via `element_state.get_description()`/`get_business_name()`, mirroring
`submitGateMet`'s 3 conditions exactly) to `submit_definition_for_review` before calling
`element_state.submit_for_review(...)`. This is what lets the history-row-write logic safely assume
an `accepted_type` exists at submission, rather than defensively handling a null case that should be
structurally impossible. Cross-references the already-parked "None applies" tech-debt item, which
flagged this exact FE-only gate gap previously — this slice now closes it for real.

**`submit_definition_for_review` must also be extended to know about semantic type at all** — today
its audit payload (`ELEMENT_DEFINITION_SUBMITTED`) carries zero semantic-type fields. It needs a
`SemanticTypeStore`/`SemanticTypeRepo` dependency added so it can both (a) run the new gate check
above and (b) read the current record to write the history row.

_Original 3 candidates (2026-08-11, superseded above, kept for history):_
  (a) Window boundary = every `set_record()` call that actually changes the top-level record
      (a fresh proposal before any disposition, or the disposition event itself) — `confirmed`/
      `rejected` states would rarely reopen a window (matches how rarely they change today: 0
      rejected, 68 confirmed, out of 2,290).
  (b) Window boundary = only DISPOSITION events (propose→confirm, propose→reject) — the nested
      `latest_proposal` updates (machine re-resolution while a disposition already stands) would
      NOT open a new window, treating them as "not yet officially true" the same way a draft edit
      doesn't move `reference_code`'s window.
  (c) Two independent windowed dimensions (disposition state history AND machine-proposal history)
      rather than forcing one shared window — more faithful to the current data shape's own
      duality but more schema complexity.

**Resubmission after return/reject/withdraw: RESOLVED 2026-08-13 — yes, always a new row.**
Regardless of why a submission left `in_review` (returned, rejected, withdrawn), any further work
done in Draft and then resubmitted gets its own fresh history row — a resubmission is itself a new
"this is now official" moment, same as any first-time submission. No special-casing by the
lifecycle reason that preceded it.

**D2 — RESOLVED 2026-08-12 (committed f8876ae): removed, not unified.** The original decision
below (kept for history) proposed fixing the asymmetry by symmetry — making both call sites build
an identical enriched column dict. That was NOT what shipped. Instead, during a separate,
broader investigation into fingerprint churn (see `/memories/repo/semantic-fingerprint-fix-plan.md`),
the user directed measuring the real confidence-nudge impact first: **0 of 54 recently re-deduced
columns were actually governance-linked** — the nudge was not the real cause of observed churn,
and empirically contributed nothing measurable. Given that, the simpler, lower-risk fix was taken:
`_glossary_domain`/`_definition_state` were removed from BOTH `_FINGERPRINT_COL_FIELDS` and the
`_score_column()` confidence nudges entirely, rather than making Table Overview enrich like
Element Detail does. This makes the asymmetry structurally impossible (there is no longer a
governance signal for either path to disagree about) instead of merely reconciled. Trade-off
accepted: a confirmed glossary link / approved definition no longer nudges semantic-type
confidence at all (previously +0.05 each) — acceptable per the measured 0/54 real-world impact.
No bulk per-table governance-lookup mechanism was needed as a result (see Open Questions — item 2
is now moot).

_Original decision (2026-08-11, superseded above, kept for history):_ Both call sites (Element
Detail, Table Overview) call the SAME function to build the governance-enriched column dict before
resolving/fingerprinting. Alternative considered: leave Table Overview un-enriched and instead strip
`_glossary_domain`/`_definition_state` OUT of `column_fingerprint()` entirely — rejected at the time
because those 2 signals were believed to be load-bearing for the scoring model. That assumption was
disproved by the 0/54 measurement above, which is why the removal path was taken instead once real
data was measured.

**D3 — `SemanticTypeRepo` mirrors `SemanticTypeStore`'s method surface exactly, including
`preserve_disposed`.** No behavior simplification — `latest_proposal` nesting, the state-value
CHECK set, and `resolver_version`/`fingerprint` (single field, `data_fingerprint` no longer
exists — see D2) all carry over faithfully. This
matches A1's own precedent (`DQScoreRepo` mirrors `DQScoreStore` exactly) and the plan's explicit
instruction for B1: "must be reproduced faithfully — this is not the slice to improve them"
(except for the enrichment-asymmetry bug, which is a correctness fix, not a scope improvement).

**D4 — RESOLVED 2026-08-13: no `semantic_type_prior` table at all.** Superseding the original
plan below. The learned-patterns/priors subsystem it would have stored (`pattern_learning.py`,
`learned_pattern_store.py`, the resolver's naming-prior nudge) was deleted from the codebase
entirely on 2026-08-13 (commit `a74802b`, measured zero real impact before removal), and
`SemanticTypeStore` now purges any legacy `priors` YAML section on load. There is no longer any
data or subsystem for this table to serve. Confirmed with the user before implementation began —
B1 builds only `semantic_type_assignment` + `semantic_type_assignment_history`.

_Original plan (2026-08-11, superseded above, kept for history):_ Priors are learned-
pattern initiation hints (token → type_id, per source), not reviewed/disposed governance objects —
there is no revoke/re-approve workflow for them (they are silently superseded when a newer pattern
is learned for the same token). Current + latest only, same as any plain upsert table; the SCD2
standing rule's own logic (§4.4: "decide what event marks a window boundary... it does not get to
skip windowing") arguably does not even apply here since priors are not the kind of "governance
history" the rule targets.

## Risks / Trade-offs

[Risk] D1 (SCD2 window boundary) is a real open design question, not a rubber-stamp of A1's
DQ-score answer — picking the wrong boundary could mean over-churning history (a window opens on
every low-signal machine re-resolution) or under-capturing real disposition history.
→ Mitigation: explicitly deferred to build-time design, with three concrete candidate shapes and
the real state-distribution evidence needed to evaluate them, rather than silently defaulting to
whichever is easiest to code.

[Risk — RESOLVED 2026-08-12] The enrichment-path fix (D2) changes live YAML-mode resolver behavior.
Actual outcome: because the fingerprint HASH FORMULA itself changed (governance fields dropped,
sample_values now hashed as a sorted set for an unrelated reason found in the same investigation),
literally all 2,290 stored fingerprints mismatched once, on their next resolve — a known, accepted,
one-time cost, not specific to the D2 population. No new regression observed; full backend suite
ran green (593/593) before committing.

[Risk — MOOT 2026-08-12] Building a per-table bulk governance-lookup for Table Overview (D2's
original implementation note) — no longer needed; nothing to look up once the signals were removed.

## Migration Plan

1. Resolve D1 (SCD2 window shape) before writing the migration DDL.
2. Alembic migration: `semantic_type_assignment`, `semantic_type_assignment_history` (per D1's
   resolution), `semantic_type_prior` (+ comments), additive only.
3. `SemanticTypeRepo` + ORM models, imported nowhere yet outside their own tests.
4. ~~Fix D2 (enrichment asymmetry)~~ — **already done 2026-08-12, committed f8876ae**, ahead of
   the rest of this slice. Nothing left to do here.
5. `SemanticTypeStore` gains the backend branch; `semantic_backend` defaults `yaml`.
6. Full backend suite gate, including new fingerprint-consistency regression tests.
7. STOP for user review before committing — matches every prior slice's pattern.

**Rollback:** the storage side (B1 proper) has no live-data risk — nothing is wired into the
running path while `semantic_backend` stays `yaml`. The D2 enrichment fix is the one piece with
real rollback weight (it changes live behavior); if it causes unexpected re-resolution churn,
revert just that commit — it is independent of the Postgres storage work and does not need the
schema/repo to be reverted alongside it.

## Open Questions

1. D1 (SCD2 window boundary) — needs a build-time decision, not resolved here (see Decisions D1).
2. ~~Exact bulk governance-lookup mechanism for Table Overview (D2's implementation note)~~ —
   **moot as of 2026-08-12**; D2 was resolved by removing the signals, not by adding a lookup.
3. Whether `semantic_type_prior` needs SCD2 at all (D4) — flagged, not asserted. Still open.
