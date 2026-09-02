"""Retire semantic_type_assignment(_history).state and the whole rejected/corrected concept;
rename confirmed_* to accepted_* (untangles tech-debt #13/#36/#45)

The persisted `state` column (proposed/suggested/confirmed/rejected/unresolved) turned out to be
redundant with data already captured elsewhere, and inconsistent with how the app actually works:

  * The UI never lets an analyst reject a semantic type (no Reject button/action exists) -- the
    only two real, reachable outcomes are the default `unresolved` `type_id` and an accepted type
    (`Accept`, or `Replace`/`Resolve` -> `Apply`, both of which only ever call the accept path).
    `reject()` had zero UI callers -- confirmed dead code, not a live workflow.
  * "Is this accepted?" is already fully carried by `confirmed_at IS NOT NULL` (renamed here to
    `accepted_at`, matching the wording the UI already uses -- the "Accept"/"Accepted" button and
    tag predate this migration).
  * "How confident was the guess?" is already fully carried by `confidence` (a float) -- the UI
    shows only a High/Medium/Low confidence grade derived from it, never the persisted word.
  * `semantic_type_assignment_history.state` was ALWAYS `'confirmed'` for every row that would
    ever exist in it, by construction -- `record_submission()` only ever runs once a row is
    already accepted (the Interpretation Set submit gate enforces this) -- so the column carried
    zero real variation even before this migration.

Dropped entirely (both tables): `state`, `rejected_by`, `rejected_by_role`, `rejected_at`,
`rejection_reason`, `corrected_type_id` -- the last five only ever existed to serve the now-retired
`reject()` path.
Renamed (both tables): `confirmed_by` -> `accepted_by`, `confirmed_by_role` -> `accepted_by_role`,
`confirmed_at` -> `accepted_at`.

No data-loss concern for `state`/`confirmed_*` on already-migrated rows: `state` is fully
re-derivable from `type_id`/`confidence`/`accepted_at` at read time, and the renamed columns keep
their values (a plain rename, not a drop). Genuinely dropped, not carried anywhere: `rejected_*`/
`rejection_reason`/`corrected_type_id` -- these only had non-null values on rows that went through
the dead `reject()` path (which, per the audit above, has zero real UI-driven callers in the live
app), so no real steward decision is lost.
"""
from __future__ import annotations

from alembic import op

revision = "0018_semantic_type_retire_state"
down_revision = "0017_catalog_annotations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE semantic_type_assignment
            DROP CONSTRAINT IF EXISTS semantic_type_assignment_state_check,
            DROP COLUMN IF EXISTS state,
            DROP COLUMN IF EXISTS rejected_by,
            DROP COLUMN IF EXISTS rejected_by_role,
            DROP COLUMN IF EXISTS rejected_at,
            DROP COLUMN IF EXISTS rejection_reason,
            DROP COLUMN IF EXISTS corrected_type_id;
        ALTER TABLE semantic_type_assignment
            RENAME COLUMN confirmed_by TO accepted_by;
        ALTER TABLE semantic_type_assignment
            RENAME COLUMN confirmed_by_role TO accepted_by_role;
        ALTER TABLE semantic_type_assignment
            RENAME COLUMN confirmed_at TO accepted_at;
        """
    )
    op.execute(
        """
        ALTER TABLE semantic_type_assignment_history
            DROP CONSTRAINT IF EXISTS semantic_type_assignment_history_state_check,
            DROP COLUMN IF EXISTS state,
            DROP COLUMN IF EXISTS rejected_by,
            DROP COLUMN IF EXISTS rejected_by_role,
            DROP COLUMN IF EXISTS rejected_at,
            DROP COLUMN IF EXISTS rejection_reason,
            DROP COLUMN IF EXISTS corrected_type_id;
        ALTER TABLE semantic_type_assignment_history
            RENAME COLUMN confirmed_by TO accepted_by;
        ALTER TABLE semantic_type_assignment_history
            RENAME COLUMN confirmed_by_role TO accepted_by_role;
        ALTER TABLE semantic_type_assignment_history
            RENAME COLUMN confirmed_at TO accepted_at;
        """
    )

    op.execute(
        """
        COMMENT ON COLUMN semantic_type_assignment.accepted_by IS
          'Who accepted this column''s semantic type (the original machine suggestion, or a steward-picked replacement). Null while not yet accepted.';
        COMMENT ON COLUMN semantic_type_assignment.accepted_by_role IS
          'The role of whoever accepted this column''s semantic type.';
        COMMENT ON COLUMN semantic_type_assignment.accepted_at IS
          'When this column''s semantic type was accepted. Null means not yet accepted -- the Interpretation Set submit gate requires this to be set.';
        COMMENT ON COLUMN semantic_type_assignment_history.accepted_by IS
          'Who accepted this column''s semantic type, as it stood at submission time.';
        COMMENT ON COLUMN semantic_type_assignment_history.accepted_by_role IS
          'The role of whoever accepted this column''s semantic type, at submission time.';
        COMMENT ON COLUMN semantic_type_assignment_history.accepted_at IS
          'When this column''s semantic type was accepted, as it stood at submission time (always set -- a submission can only happen once a type is accepted).';
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE semantic_type_assignment_history
            RENAME COLUMN accepted_at TO confirmed_at;
        ALTER TABLE semantic_type_assignment_history
            RENAME COLUMN accepted_by_role TO confirmed_by_role;
        ALTER TABLE semantic_type_assignment_history
            RENAME COLUMN accepted_by TO confirmed_by;
        ALTER TABLE semantic_type_assignment_history
            ADD COLUMN state TEXT,
            ADD COLUMN rejected_by TEXT,
            ADD COLUMN rejected_by_role TEXT,
            ADD COLUMN rejected_at TIMESTAMPTZ,
            ADD COLUMN rejection_reason TEXT,
            ADD COLUMN corrected_type_id TEXT;
        UPDATE semantic_type_assignment_history SET state = 'confirmed' WHERE state IS NULL;
        ALTER TABLE semantic_type_assignment_history
            ALTER COLUMN state SET NOT NULL;
        ALTER TABLE semantic_type_assignment_history
            ADD CONSTRAINT semantic_type_assignment_history_state_check
                CHECK (state IN ('proposed', 'suggested', 'confirmed', 'rejected', 'unresolved'));
        """
    )
    op.execute(
        """
        ALTER TABLE semantic_type_assignment
            RENAME COLUMN accepted_at TO confirmed_at;
        ALTER TABLE semantic_type_assignment
            RENAME COLUMN accepted_by_role TO confirmed_by_role;
        ALTER TABLE semantic_type_assignment
            RENAME COLUMN accepted_by TO confirmed_by;
        ALTER TABLE semantic_type_assignment
            ADD COLUMN state TEXT,
            ADD COLUMN rejected_by TEXT,
            ADD COLUMN rejected_by_role TEXT,
            ADD COLUMN rejected_at TIMESTAMPTZ,
            ADD COLUMN rejection_reason TEXT,
            ADD COLUMN corrected_type_id TEXT;
        UPDATE semantic_type_assignment
            SET state = CASE
                WHEN confirmed_at IS NOT NULL THEN 'confirmed'
                WHEN type_id IS NULL OR type_id = 'unresolved' THEN 'unresolved'
                WHEN confidence >= 0.60 THEN 'proposed'
                ELSE 'suggested'
            END
            WHERE state IS NULL;
        ALTER TABLE semantic_type_assignment
            ALTER COLUMN state SET NOT NULL;
        ALTER TABLE semantic_type_assignment
            ADD CONSTRAINT semantic_type_assignment_state_check
                CHECK (state IN ('proposed', 'suggested', 'confirmed', 'rejected', 'unresolved'));
        """
    )
