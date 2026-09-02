"""Add dq_score + dq_score_history (govern-pg-a1-dq-scores-build)

Slice A1 of the governance YAML->Postgres migration: builds the Postgres-backed store for DQ
column/dataset scores, fully dormant behind the `database.dq_backend` flag (default `yaml`).

Real SCD2 for both tables (per docs/governance-postgres-migration.md S4.4, the standing rule
established while building this slice): `dq_score` holds the current record per key and carries
its own `valid_from`; `dq_score_history` holds every superseded record, each with a real, never-
placeholder `valid_from`/`valid_to` window. A window opens/closes on every genuine change to
`dq_score`/`state`/`signal_fingerprint` (S16.2's existing no-op-detection rule decides what counts
as "changed") -- including a column's `scored -> unscored` transition (out of scope / an emptied
table), which plays the same gap-creating role reference_code's revoke does. See
openspec/changes/govern-pg-a1-dq-scores-build/design.md for the full D1-D8 decision log.

The scorer's breakdown (core/dq_scorer.py) is a deeply nested, versioned dict (BREAKDOWN_VERSION
has already changed 7 times) -- stored verbatim as JSONB rather than exploded into columns, same
precedent as term_version.attributes/ai_provenance.

No backend flag flip here, no data migration -- this migration only creates new, empty tables.
Slice A2 (a separate, later change) migrates real data, proves parity, and is the point at which
a user flips `dq_backend: postgres`.
"""
from __future__ import annotations

from alembic import op

revision = "0011_add_dq_score"
down_revision = "0010_reference_code_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE dq_score (
            id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            key                 TEXT NOT NULL UNIQUE,
            key_kind            TEXT NOT NULL,
            state               TEXT NOT NULL,
            dq_score            INTEGER,
            grade_label         TEXT,
            breakdown_version   INTEGER,
            signal_fingerprint  TEXT,
            config_fingerprint  TEXT,
            breakdown           JSONB NOT NULL,
            valid_from          TIMESTAMPTZ NOT NULL,
            scored_at           TIMESTAMPTZ NOT NULL,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT dq_score_key_kind_check CHECK (key_kind IN ('column', 'dataset'))
        );
        """
    )
    op.execute("CREATE INDEX ix_dq_score_key ON dq_score (key);")

    op.execute(
        """
        CREATE TABLE dq_score_history (
            id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            dq_score_id         BIGINT NOT NULL REFERENCES dq_score(id) ON DELETE CASCADE,
            key                 TEXT NOT NULL,
            key_kind            TEXT NOT NULL,
            state               TEXT NOT NULL,
            dq_score            INTEGER,
            grade_label         TEXT,
            breakdown_version   INTEGER,
            signal_fingerprint  TEXT,
            config_fingerprint  TEXT,
            breakdown           JSONB NOT NULL,
            valid_from          TIMESTAMPTZ NOT NULL,
            valid_to            TIMESTAMPTZ NOT NULL,
            scored_at           TIMESTAMPTZ NOT NULL,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT dq_score_history_key_kind_check CHECK (key_kind IN ('column', 'dataset')),
            CONSTRAINT dq_score_history_window_check CHECK (valid_to > valid_from)
        );
        """
    )
    op.execute("CREATE INDEX ix_dq_score_history_key_window ON dq_score_history (key, valid_from);")
    op.execute("CREATE INDEX ix_dq_score_history_dq_score_id ON dq_score_history (dq_score_id);")

    op.execute(
        """
        COMMENT ON TABLE dq_score IS
          'The current (latest) data-quality score for one column or dataset roll-up. One row per key. Real Postgres-backed alternative to governance/dq_scores.yaml, dormant behind the dq_backend flag until a later slice flips it.';
        COMMENT ON COLUMN dq_score.id IS
          'Internal identifier for this key''s current score row.';
        COMMENT ON COLUMN dq_score.key IS
          'Which thing is scored: "source|schema|table|column" for a column, "source|schema|table" for a dataset roll-up.';
        COMMENT ON COLUMN dq_score.key_kind IS
          'Whether this key identifies a single column or a whole dataset roll-up.';
        COMMENT ON COLUMN dq_score.state IS
          'Whether this key currently has a real score ("scored") or is temporarily unscored (out of scope, or its table is empty).';
        COMMENT ON COLUMN dq_score.dq_score IS
          'The overall 0-100 data-quality score, when state is scored; null when unscored.';
        COMMENT ON COLUMN dq_score.grade_label IS
          'The human-readable grade band this score falls into (e.g. "Good", "Needs Attention"), when scored.';
        COMMENT ON COLUMN dq_score.breakdown_version IS
          'Which version of the scoring engine''s output shape produced this record -- used to detect and heal stale records when the scorer''s display shape changes.';
        COMMENT ON COLUMN dq_score.signal_fingerprint IS
          'Hash of the inputs that fed this score (profiler facts + governance signals). Unchanged fingerprint on a re-score means nothing new to record.';
        COMMENT ON COLUMN dq_score.config_fingerprint IS
          'Hash of the scoring configuration (weights, thresholds) in effect when this score was computed.';
        COMMENT ON COLUMN dq_score.breakdown IS
          'The full scored breakdown as produced by the scoring engine (component scores, line items, remediation actions) -- stored as-is; its shape has changed multiple times as the scoring model evolved.';
        COMMENT ON COLUMN dq_score.valid_from IS
          'The business-effective date this key''s CURRENT score/state took effect. The first-ever record for a key uses its own scored_at (a brand-new key has no earlier true origination to approximate). Every later change opens a new valid_from at that change''s real timestamp.';
        COMMENT ON COLUMN dq_score.scored_at IS
          'When this record was actually computed by the scoring engine.';
        COMMENT ON COLUMN dq_score.created_at IS
          'When this row was first written (system timestamp, not a business date).';
        COMMENT ON COLUMN dq_score.updated_at IS
          'When this row was last updated in place (system timestamp, not a business date).';

        COMMENT ON TABLE dq_score_history IS
          'Retired data-quality score versions, one row per version that was ever superseded for a key. valid_from/valid_to are ALWAYS two real, concrete dates (never a placeholder) since a row only lands here the instant a genuine change (or a scored/unscored transition) closes it.';
        COMMENT ON COLUMN dq_score_history.id IS
          'Internal identifier for this historical version.';
        COMMENT ON COLUMN dq_score_history.dq_score_id IS
          'The current dq_score row this historical version used to be.';
        COMMENT ON COLUMN dq_score_history.key IS
          'Which thing was scored, copied from dq_score at the moment this version was retired.';
        COMMENT ON COLUMN dq_score_history.key_kind IS
          'Whether this historical key identified a single column or a whole dataset roll-up.';
        COMMENT ON COLUMN dq_score_history.state IS
          'Whether this version was scored or unscored, as it was during this version''s window.';
        COMMENT ON COLUMN dq_score_history.dq_score IS
          'The overall 0-100 score during this version''s window, when it was scored.';
        COMMENT ON COLUMN dq_score_history.grade_label IS
          'The grade band during this version''s window, when it was scored.';
        COMMENT ON COLUMN dq_score_history.breakdown_version IS
          'Which version of the scoring engine''s output shape produced this historical record.';
        COMMENT ON COLUMN dq_score_history.signal_fingerprint IS
          'Hash of the inputs that fed this historical version''s score.';
        COMMENT ON COLUMN dq_score_history.config_fingerprint IS
          'Hash of the scoring configuration in effect for this historical version.';
        COMMENT ON COLUMN dq_score_history.breakdown IS
          'The full scored breakdown as it was during this version''s window, copied from dq_score at the moment this version was retired.';
        COMMENT ON COLUMN dq_score_history.valid_from IS
          'The real, business-effective date this version became the current score/state. Never a placeholder.';
        COMMENT ON COLUMN dq_score_history.valid_to IS
          'The real date this version stopped being the current score/state (the moment it was superseded). Never a placeholder -- always known, since a row is only created once this date is known.';
        COMMENT ON COLUMN dq_score_history.scored_at IS
          'When this historical version was actually computed by the scoring engine.';
        COMMENT ON COLUMN dq_score_history.created_at IS
          'When this historical row itself was written (system timestamp, not a business date).';
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS dq_score_history;")
    op.execute("DROP TABLE IF EXISTS dq_score;")
