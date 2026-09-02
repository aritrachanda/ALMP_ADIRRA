## ADDED Requirements

> **Status: already satisfied as of 2026-08-12 (commit f8876ae)**, by a different mechanism than
> originally envisioned when this spec was written. The original approach was a single shared
> enrichment function used by both call paths (governance-signal symmetry). What actually shipped:
> `_glossary_domain`/`_definition_state` were removed from `column_fingerprint()` (and from
> `_score_column()`'s confidence scoring) entirely, after measuring 0/54 real impact from the
> confidence nudge — see `openspec/changes/govern-pg-b1-semantic-types-build/design.md` D2. The
> requirements below are reworded to describe the resulting behavior rather than the originally
> planned mechanism. No dedicated regression test exists yet for either requirement — see
> tasks.md 5.3/5.4 (still open).

### Requirement: Column fingerprints do not depend on which UI path resolved them
The system SHALL compute `column_fingerprint()` for a column using only profiling-derived signals — never a signal that is populated by one call path (e.g. Element Detail) and not another (e.g. Table Overview) — so that the same column produces the same fingerprint regardless of which UI path most recently resolved it.

#### Scenario: Element Detail then Table Overview
- **WHEN** a column with a confirmed glossary link is resolved via Element Detail, then the same column is resolved via Table Overview without any real profile change
- **THEN** both paths compute the identical `column_fingerprint()` value and neither triggers a real re-resolution of the other's result

#### Scenario: Table Overview then Element Detail
- **WHEN** a column with an approved definition is resolved via Table Overview, then the same column is resolved via Element Detail without any real profile change
- **THEN** both paths compute the identical `column_fingerprint()` value and neither triggers a real re-resolution of the other's result

### Requirement: Catalog-read fingerprint stability
The system SHALL produce an identical `column_fingerprint()` for a column across independent, repeated catalog reads (e.g. across a server restart, a new session, or plain navigation) when no real profiling change has occurred.

#### Scenario: Repeated independent catalog reads
- **WHEN** the same column's catalog data is read twice via independent, uncached calls with no intervening profile refresh
- **THEN** `column_fingerprint()` computed from each read produces the same value
