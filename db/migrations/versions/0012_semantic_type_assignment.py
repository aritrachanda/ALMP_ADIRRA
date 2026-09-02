"""Add semantic_type_assignment + semantic_type_assignment_history (govern-pg-b1-semantic-types-build)

Slice B1 of the governance YAML->Postgres migration: builds the Postgres-backed store for
per-column semantic-type assignments, fully dormant behind the `database.semantic_backend` flag
(default `yaml`). No `semantic_type_prior` table (D4, resolved 2026-08-13) -- the learned-patterns
subsystem it would have served was deleted from the codebase the same day (commit `a74802b`),
before this migration was written.

`semantic_type_assignment` is a near-verbatim mirror of `SemanticTypeStore`'s YAML record shape
(one row per column key) plus one new field, `system_deduced_type` -- captures the machine's
pre-override suggestion at the moment a steward first "Replace"s it via `confirm()`/`reject()`,
fixing a real data-loss bug where that suggestion was previously overwritten with no recovery
path. `latest_proposal` (the existing sticky-disposition mechanism) carries over unchanged, per
D3 ("no behavior simplification"). Unlike the YAML record, this table has NO `submitted_at`/
`submitted_by` of its own (user correction, 2026-08-13) -- a semantic type is never submitted on
its own, only as part of the whole Interpretation Set, so tracking a second "submission" concept
here would be a confusing duplicate of the Interpretation Set's own submission tracking.

`semantic_type_assignment_history` is a genuinely new concept, not a mirror of anything in the
YAML store: a real SCD2 window opens each time an Interpretation Set is submitted for review
(`POST /{source}/{table}/{column}/submit`), NOT on every `confirm()`/`reject()`/machine re-resolve
-- a steward can Accept -> Replace -> Accept many times in one editing session before ever
submitting, and only the submission moment is "official" (D1). Each row is self-contained SCD2
(unlike dq_score/reference_code's separate current+history split): `valid_from` is that
submission's own timestamp, `valid_to` is NULL while it is still the most recent submission for
that key and is set to the next submission's timestamp the moment a later submission supersedes
it -- enforced by a partial unique index allowing at most one open (`valid_to IS NULL`) row per
key.

Each history row carries the FULL accepted snapshot as real, named columns (mirroring almost
every column on `semantic_type_assignment` -- type_id, domain_role, confidence, state, source,
candidates, evidence, conflict flags, format/scope/entity/pii fields, tier, resolver_version,
confirm/reject bookkeeping, fingerprint) -- deliberately NOT collapsed into a JSONB blob (2026-08-13
user correction: an earlier draft of this migration compressed most of this into two JSONB
columns and lost real, queryable history detail; this version keeps everything as real columns,
using JSONB only for `candidates`/`evidence`, which are genuinely lists of multiple items, same
as the current table already does). A separate, smaller `deduced_*` column group captures what
the machine's OWN resolver independently believed at that same moment -- this can differ from the
accepted snapshot whenever a steward overrode the machine's suggestion. See
openspec/changes/govern-pg-b1-semantic-types-build/design.md for the full D1-D4 decision log.

No backend flag flip here, no data migration -- this migration only creates new, empty tables.
Slice B2 (a separate, later change) migrates real data, proves parity, and is the point at which
a user flips `semantic_backend: postgres`.
"""
from __future__ import annotations

from alembic import op

revision = "0012_semantic_type_assignment"
down_revision = "0011_add_dq_score"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE semantic_type_assignment (
            id                          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            key                         TEXT NOT NULL UNIQUE,
            type_id                     TEXT NOT NULL,
            domain_role                 TEXT,
            confidence                  DOUBLE PRECISION NOT NULL DEFAULT 0,
            state                       TEXT NOT NULL,
            source                      TEXT,
            candidates                  JSONB NOT NULL DEFAULT '[]',
            evidence                    JSONB NOT NULL DEFAULT '[]',
            type_value_conflict         BOOLEAN NOT NULL DEFAULT false,
            type_datatype_difference    BOOLEAN NOT NULL DEFAULT false,
            format                      TEXT,
            format_source               TEXT,
            format_rationale            TEXT,
            scope                       TEXT,
            entity                      TEXT,
            pii                         BOOLEAN NOT NULL DEFAULT false,
            pii_category                TEXT,
            tier                        INTEGER NOT NULL DEFAULT 0,
            resolver_version            TEXT,
            resolved_at                 TIMESTAMPTZ,
            confirmed_by                TEXT,
            confirmed_by_role           TEXT,
            confirmed_at                TIMESTAMPTZ,
            rejected_by                 TEXT,
            rejected_by_role            TEXT,
            rejected_at                 TIMESTAMPTZ,
            rejection_reason            TEXT,
            corrected_type_id           TEXT,
            fingerprint                 TEXT,
            system_deduced_type         JSONB,
            latest_proposal             JSONB,
            created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT semantic_type_assignment_state_check
                CHECK (state IN ('proposed', 'suggested', 'confirmed', 'rejected', 'unresolved')),
            CONSTRAINT semantic_type_assignment_source_check
                CHECK (source IS NULL OR source IN ('rule', 'ai'))
        );
        """
    )
    op.execute("CREATE INDEX ix_semantic_type_assignment_key ON semantic_type_assignment (key);")

    op.execute(
        """
        CREATE TABLE semantic_type_assignment_history (
            id                              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            semantic_type_assignment_id     BIGINT NOT NULL
                REFERENCES semantic_type_assignment(id) ON DELETE CASCADE,
            key                             TEXT NOT NULL,

            -- Full accepted snapshot at submission time (same field names/shapes as
            -- semantic_type_assignment -- this is what a person actually confirmed).
            type_id                         TEXT NOT NULL,
            domain_role                     TEXT,
            confidence                      DOUBLE PRECISION,
            state                           TEXT NOT NULL,
            source                          TEXT,
            candidates                      JSONB NOT NULL DEFAULT '[]',
            evidence                        JSONB NOT NULL DEFAULT '[]',
            type_value_conflict             BOOLEAN NOT NULL DEFAULT false,
            type_datatype_difference        BOOLEAN NOT NULL DEFAULT false,
            format                          TEXT,
            format_source                   TEXT,
            format_rationale                TEXT,
            scope                           TEXT,
            entity                          TEXT,
            pii                             BOOLEAN NOT NULL DEFAULT false,
            pii_category                    TEXT,
            tier                            INTEGER NOT NULL DEFAULT 0,
            resolver_version                TEXT,
            confirmed_by                    TEXT,
            confirmed_by_role               TEXT,
            confirmed_at                    TIMESTAMPTZ,
            rejected_by                     TEXT,
            rejected_by_role                TEXT,
            rejected_at                     TIMESTAMPTZ,
            rejection_reason                TEXT,
            corrected_type_id               TEXT,
            fingerprint                     TEXT,

            -- The machine's own, independent opinion at that same moment (may differ from
            -- the accepted snapshot above whenever a steward overrode it).
            deduced_type_id                 TEXT NOT NULL,
            deduced_domain_role             TEXT,
            deduced_confidence               DOUBLE PRECISION,
            deduced_tier                     INTEGER,
            deduced_resolver_version         TEXT,

            submitted_by                    TEXT,
            valid_from                      TIMESTAMPTZ NOT NULL,
            valid_to                        TIMESTAMPTZ,
            created_at                      TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT semantic_type_assignment_history_state_check
                CHECK (state IN ('proposed', 'suggested', 'confirmed', 'rejected', 'unresolved')),
            CONSTRAINT semantic_type_assignment_history_source_check
                CHECK (source IS NULL OR source IN ('rule', 'ai')),
            CONSTRAINT semantic_type_assignment_history_window_check
                CHECK (valid_to IS NULL OR valid_to > valid_from)
        );
        """
    )
    op.execute(
        "CREATE INDEX ix_semantic_type_assignment_history_key_window "
        "ON semantic_type_assignment_history (key, valid_from);"
    )
    op.execute(
        "CREATE INDEX ix_semantic_type_assignment_history_assignment_id "
        "ON semantic_type_assignment_history (semantic_type_assignment_id);"
    )
    op.execute(
        "CREATE UNIQUE INDEX ux_semantic_type_assignment_history_open "
        "ON semantic_type_assignment_history (key) WHERE valid_to IS NULL;"
    )

    op.execute(
        """
        COMMENT ON TABLE semantic_type_assignment IS
          'The current (latest) semantic-type deduction/decision for one column. One row per key. Real Postgres-backed alternative to governance/semantic_type_assignments.yaml, dormant behind the semantic_backend flag until a later slice flips it.';
        COMMENT ON COLUMN semantic_type_assignment.id IS
          'Internal identifier for this column''s current assignment row.';
        COMMENT ON COLUMN semantic_type_assignment.key IS
          '"source|schema|table|column" -- which column this assignment is about.';
        COMMENT ON COLUMN semantic_type_assignment.type_id IS
          'The governed semantic type currently in effect for this column (e.g. "iban", "unresolved" if nothing has been deduced).';
        COMMENT ON COLUMN semantic_type_assignment.domain_role IS
          'The business role this column plays within its deduced type (e.g. which side of an account relationship).';
        COMMENT ON COLUMN semantic_type_assignment.confidence IS
          'The resolver''s own confidence (0-1) in its current type deduction.';
        COMMENT ON COLUMN semantic_type_assignment.state IS
          'Disposition of this deduction: proposed/suggested (machine opinion, not yet reviewed), confirmed/rejected (a steward decided), or unresolved (nothing could be deduced).';
        COMMENT ON COLUMN semantic_type_assignment.source IS
          'Whether the current type_id came from the deterministic rule engine or an AI call.';
        COMMENT ON COLUMN semantic_type_assignment.candidates IS
          'Every type the resolver considered for this column and how each scored, most recent resolve only.';
        COMMENT ON COLUMN semantic_type_assignment.evidence IS
          'The specific signals (naming, value patterns, validator pass rates, etc.) that led to the current deduction.';
        COMMENT ON COLUMN semantic_type_assignment.type_value_conflict IS
          'Whether the deduced type''s expected value shape conflicts with what the profiler actually observed in the data.';
        COMMENT ON COLUMN semantic_type_assignment.type_datatype_difference IS
          'Whether the deduced type''s expected storage datatype differs from the column''s actual declared datatype.';
        COMMENT ON COLUMN semantic_type_assignment.format IS
          'The specific value format recognised for this column (e.g. an IBAN country-prefix variant), when the type supports multiple formats.';
        COMMENT ON COLUMN semantic_type_assignment.format_source IS
          'Whether the recognised format came from the rule engine or was set by a person.';
        COMMENT ON COLUMN semantic_type_assignment.format_rationale IS
          'Plain-language explanation of why this format was picked.';
        COMMENT ON COLUMN semantic_type_assignment.scope IS
          'The business scope/context this column''s type applies within, when the vocabulary distinguishes by scope.';
        COMMENT ON COLUMN semantic_type_assignment.entity IS
          'Which real-world business entity (account, counterparty, contract, etc.) this column''s value identifies or describes.';
        COMMENT ON COLUMN semantic_type_assignment.pii IS
          'Whether this column''s governed type is considered personally identifiable information.';
        COMMENT ON COLUMN semantic_type_assignment.pii_category IS
          'The specific category of personal data this column holds, when pii is true.';
        COMMENT ON COLUMN semantic_type_assignment.tier IS
          'The evidence strength tier behind the current deduction (kept for parity with the YAML store; not currently surfaced in the UI).';
        COMMENT ON COLUMN semantic_type_assignment.resolver_version IS
          'Which version of the resolver''s scoring logic produced this deduction -- used to detect stale records when the resolver''s rules change.';
        COMMENT ON COLUMN semantic_type_assignment.resolved_at IS
          'When the resolver last computed this deduction.';
        COMMENT ON COLUMN semantic_type_assignment.confirmed_by IS
          'Who accepted this column''s semantic type, when state is confirmed.';
        COMMENT ON COLUMN semantic_type_assignment.confirmed_by_role IS
          'The role of whoever accepted this column''s semantic type.';
        COMMENT ON COLUMN semantic_type_assignment.confirmed_at IS
          'When this column''s semantic type was accepted.';
        COMMENT ON COLUMN semantic_type_assignment.rejected_by IS
          'Who rejected this column''s semantic type, when state is rejected.';
        COMMENT ON COLUMN semantic_type_assignment.rejected_by_role IS
          'The role of whoever rejected this column''s semantic type.';
        COMMENT ON COLUMN semantic_type_assignment.rejected_at IS
          'When this column''s semantic type was rejected.';
        COMMENT ON COLUMN semantic_type_assignment.rejection_reason IS
          'Free-text reason given for rejecting this column''s semantic type.';
        COMMENT ON COLUMN semantic_type_assignment.corrected_type_id IS
          'The replacement type_id a steward picked instead of the machine''s suggestion, when rejecting with a correction.';
        COMMENT ON COLUMN semantic_type_assignment.fingerprint IS
          'Hash of the inputs (profiling stats + naming) that produced the current deduction -- an unchanged fingerprint on a later resolve means nothing new to re-derive.';
        COMMENT ON COLUMN semantic_type_assignment.system_deduced_type IS
          'The machine''s own suggestion (type_id/domain_role/confidence) at the moment a steward FIRST replaced it with a different type -- preserves the original deduction that confirm()/reject() would otherwise silently overwrite with no recovery path.';
        COMMENT ON COLUMN semantic_type_assignment.latest_proposal IS
          'A fresh machine re-resolution parked here instead of overwriting an already-confirmed/rejected record -- the steward''s decision is never silently replaced by a later automatic re-deduction.';
        COMMENT ON COLUMN semantic_type_assignment.created_at IS
          'When this row was first written (system timestamp, not a business date).';
        COMMENT ON COLUMN semantic_type_assignment.updated_at IS
          'When this row was last updated in place (system timestamp, not a business date).';

        COMMENT ON TABLE semantic_type_assignment_history IS
          'One row per Interpretation Set submission for a column -- a full, real-column snapshot of what was officially accepted at that moment, plus a separate small group describing what the machine itself independently believed at that same moment.';
        COMMENT ON COLUMN semantic_type_assignment_history.id IS
          'Internal identifier for this historical submission row.';
        COMMENT ON COLUMN semantic_type_assignment_history.semantic_type_assignment_id IS
          'The column''s current semantic_type_assignment row this submission belongs to.';
        COMMENT ON COLUMN semantic_type_assignment_history.key IS
          '"source|schema|table|column" this submission was about, copied for direct querying without a join.';
        COMMENT ON COLUMN semantic_type_assignment_history.type_id IS
          'The governed semantic type that was in effect (accepted or rejected-with-correction) at the moment of this submission.';
        COMMENT ON COLUMN semantic_type_assignment_history.domain_role IS
          'The business role recorded for this column at the moment of this submission.';
        COMMENT ON COLUMN semantic_type_assignment_history.confidence IS
          'The resolver''s confidence for the accepted type_id, as it stood at submission time.';
        COMMENT ON COLUMN semantic_type_assignment_history.state IS
          'The disposition (confirmed/rejected) that was in effect at the moment of this submission.';
        COMMENT ON COLUMN semantic_type_assignment_history.source IS
          'Whether the accepted type_id came from the rule engine or an AI call, as it stood at submission time.';
        COMMENT ON COLUMN semantic_type_assignment_history.candidates IS
          'The alternative types considered, as they stood at submission time.';
        COMMENT ON COLUMN semantic_type_assignment_history.evidence IS
          'The specific signals behind the accepted deduction, as they stood at submission time.';
        COMMENT ON COLUMN semantic_type_assignment_history.type_value_conflict IS
          'Whether a value-shape conflict was flagged for the accepted type at submission time.';
        COMMENT ON COLUMN semantic_type_assignment_history.type_datatype_difference IS
          'Whether a storage-datatype difference was flagged for the accepted type at submission time.';
        COMMENT ON COLUMN semantic_type_assignment_history.format IS
          'The recognised value format at submission time, when applicable.';
        COMMENT ON COLUMN semantic_type_assignment_history.format_source IS
          'Whether the recognised format came from the rule engine or a person, at submission time.';
        COMMENT ON COLUMN semantic_type_assignment_history.format_rationale IS
          'Plain-language explanation of the recognised format, at submission time.';
        COMMENT ON COLUMN semantic_type_assignment_history.scope IS
          'The business scope recorded at submission time, when applicable.';
        COMMENT ON COLUMN semantic_type_assignment_history.entity IS
          'The real-world business entity recorded at submission time.';
        COMMENT ON COLUMN semantic_type_assignment_history.pii IS
          'Whether the accepted type was considered personal data at submission time.';
        COMMENT ON COLUMN semantic_type_assignment_history.pii_category IS
          'The personal-data category recorded at submission time, when pii is true.';
        COMMENT ON COLUMN semantic_type_assignment_history.tier IS
          'The evidence strength tier behind the accepted deduction at submission time.';
        COMMENT ON COLUMN semantic_type_assignment_history.resolver_version IS
          'Which version of the resolver produced the accepted deduction, at submission time.';
        COMMENT ON COLUMN semantic_type_assignment_history.confirmed_by IS
          'Who accepted this column''s semantic type, if state is confirmed at submission time.';
        COMMENT ON COLUMN semantic_type_assignment_history.confirmed_by_role IS
          'The role of whoever accepted this column''s semantic type, at submission time.';
        COMMENT ON COLUMN semantic_type_assignment_history.confirmed_at IS
          'When this column''s semantic type was accepted, as it stood at submission time.';
        COMMENT ON COLUMN semantic_type_assignment_history.rejected_by IS
          'Who rejected this column''s semantic type, if state is rejected at submission time.';
        COMMENT ON COLUMN semantic_type_assignment_history.rejected_by_role IS
          'The role of whoever rejected this column''s semantic type, at submission time.';
        COMMENT ON COLUMN semantic_type_assignment_history.rejected_at IS
          'When this column''s semantic type was rejected, as it stood at submission time.';
        COMMENT ON COLUMN semantic_type_assignment_history.rejection_reason IS
          'The rejection reason recorded at submission time, when applicable.';
        COMMENT ON COLUMN semantic_type_assignment_history.corrected_type_id IS
          'The replacement type_id a steward picked instead of the machine''s suggestion, recorded at submission time.';
        COMMENT ON COLUMN semantic_type_assignment_history.fingerprint IS
          'The fingerprint of the inputs behind the accepted deduction, as it stood at submission time.';
        COMMENT ON COLUMN semantic_type_assignment_history.deduced_type_id IS
          'What the machine''s own resolver independently believed the type was at the moment of this submission -- may differ from type_id above when a steward overrode the machine.';
        COMMENT ON COLUMN semantic_type_assignment_history.deduced_domain_role IS
          'The business role the machine''s own deduction assigned, at the moment of this submission.';
        COMMENT ON COLUMN semantic_type_assignment_history.deduced_confidence IS
          'The machine''s own confidence in its independent deduction, at the moment of this submission.';
        COMMENT ON COLUMN semantic_type_assignment_history.deduced_tier IS
          'The evidence strength tier behind the machine''s own independent deduction, at the moment of this submission.';
        COMMENT ON COLUMN semantic_type_assignment_history.deduced_resolver_version IS
          'Which version of the resolver produced the machine''s own independent deduction, at the moment of this submission.';
        COMMENT ON COLUMN semantic_type_assignment_history.submitted_by IS
          'Who submitted the Interpretation Set at this moment.';
        COMMENT ON COLUMN semantic_type_assignment_history.valid_from IS
          'The real timestamp this submission happened -- this row''s window opens here.';
        COMMENT ON COLUMN semantic_type_assignment_history.valid_to IS
          'The real timestamp a LATER submission for the same column superseded this one; NULL while this is still the most recent submission (enforced by a partial unique index, at most one open row per key).';
        COMMENT ON COLUMN semantic_type_assignment_history.created_at IS
          'When this historical row itself was written (system timestamp, not a business date).';
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS semantic_type_assignment_history;")
    op.execute("DROP TABLE IF EXISTS semantic_type_assignment;")
