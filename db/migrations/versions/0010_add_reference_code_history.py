"""Add reference_code_history + reference_code.valid_from (historize-reference-codes)

Point-in-time historization for reference codes: `reference_code` (already live, Phase 5b.2)
gains one column, `valid_from` — the business-effective date its current value took effect.
No `valid_to`/`is_current` on this table: every row here is current by construction.

`reference_code_history` holds retired versions: one row per value/meaning that was ever
superseded. `valid_from`/`valid_to` on THIS table are always two real, concrete dates — never a
placeholder — because a row only lands here at the exact instant it's superseded (closed by
`revoke_codes()`, opened by the next `approve_codes()`). See
openspec/changes/historize-reference-codes/design.md for the full D1-D8 decision log.

Existing `reference_code` rows are backfilled with `valid_from` = the business-effective
sentinel (1800-01-01) — onboarding a codeset into ADM is not the same event as the code coming
into existence in the real world, so no true origin date is claimed. Zero `reference_code_history`
rows are created by the backfill — there is no prior version to close.

No backend flag (see design.md D8): this is additive capability on an already-live table, not a
system swap — nothing to toggle back to.
"""
from __future__ import annotations

from alembic import op

revision = "0010_reference_code_history"
down_revision = "0009_data_dictionary_comments"
branch_labels = None
depends_on = None

_SENTINEL = "1800-01-01 00:00:00+00"


def upgrade() -> None:
    op.execute(f"ALTER TABLE reference_code ADD COLUMN valid_from TIMESTAMPTZ NOT NULL DEFAULT '{_SENTINEL}'::timestamptz;")

    op.execute(
        """
        CREATE TABLE reference_code_history (
            id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            reference_code_id BIGINT NOT NULL REFERENCES reference_code(id) ON DELETE CASCADE,
            element_key       TEXT NOT NULL,
            code              TEXT NOT NULL,
            value             TEXT,
            meaning           TEXT,
            origin            TEXT NOT NULL,
            status            TEXT NOT NULL,
            submitted_at      TIMESTAMPTZ,
            submitted_by      TEXT,
            approved_at       TIMESTAMPTZ,
            approved_by       TEXT,
            valid_from        TIMESTAMPTZ NOT NULL,
            valid_to          TIMESTAMPTZ NOT NULL,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT reference_code_history_origin_check CHECK (origin IN ('profiled','declared')),
            CONSTRAINT reference_code_history_status_check CHECK (
                status IN ('empty','draft','in_review','approved','returned','rejected')
            ),
            CONSTRAINT reference_code_history_window_check CHECK (valid_to > valid_from)
        );
        """
    )
    op.execute(
        "CREATE INDEX ix_reference_code_history_element_code_window "
        "ON reference_code_history (element_key, code, valid_from);"
    )
    op.execute(
        "CREATE INDEX ix_reference_code_history_reference_code_id "
        "ON reference_code_history (reference_code_id);"
    )

    op.execute(
        """
        COMMENT ON COLUMN reference_code.valid_from IS
          'The business-effective date this code''s CURRENT value/meaning took effect. Pre-existing rows are backfilled to a far-past sentinel (this code''s true origin predates ADM tracking it); real, dated values only appear from the first approved change onward. No valid_to or is_current needed here — every row in this table is current by construction.';

        COMMENT ON TABLE reference_code_history IS
          'Retired versions of a reference code''s value/meaning, one row per version that was ever superseded. valid_from/valid_to are ALWAYS two real, concrete dates (never a placeholder) since a row only lands here the instant it stops being the officially approved value. Replaces nothing — this is new, additive point-in-time history alongside the already-live reference_code table.';
        COMMENT ON COLUMN reference_code_history.id IS
          'Internal identifier for this historical version.';
        COMMENT ON COLUMN reference_code_history.reference_code_id IS
          'The current reference_code row this historical version used to be.';
        COMMENT ON COLUMN reference_code_history.element_key IS
          'Which column this code belonged to, as text: "source|schema|table|column".';
        COMMENT ON COLUMN reference_code_history.code IS
          'The code value, e.g. "EUR". Copied from reference_code at the moment this version was retired.';
        COMMENT ON COLUMN reference_code_history.value IS
          'The code''s expanded/full-word form, as it was during this version''s window.';
        COMMENT ON COLUMN reference_code_history.meaning IS
          'The code''s business meaning, as it was during this version''s window.';
        COMMENT ON COLUMN reference_code_history.origin IS
          'Whether this code was profiled or manually declared, as it was during this version''s window.';
        COMMENT ON COLUMN reference_code_history.status IS
          'This code''s review status at the moment this version was retired (always ''approved'' in practice, since only an approved version is ever historized).';
        COMMENT ON COLUMN reference_code_history.submitted_at IS
          'When this version was submitted for review, if recorded.';
        COMMENT ON COLUMN reference_code_history.submitted_by IS
          'Who submitted this version for review, if recorded.';
        COMMENT ON COLUMN reference_code_history.approved_at IS
          'When this version was approved.';
        COMMENT ON COLUMN reference_code_history.approved_by IS
          'Who approved this version.';
        COMMENT ON COLUMN reference_code_history.valid_from IS
          'The real, business-effective date this version became the officially approved value. Never a placeholder.';
        COMMENT ON COLUMN reference_code_history.valid_to IS
          'The real date this version stopped being the officially approved value (the moment it was revoked). Never a placeholder — always known, since a row is only created once this date is known.';
        COMMENT ON COLUMN reference_code_history.created_at IS
          'When this historical row itself was written (system timestamp, not a business date).';
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS reference_code_history;")
    op.execute("ALTER TABLE reference_code DROP COLUMN IF EXISTS valid_from;")
