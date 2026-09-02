"""Clarify element_definition_history's valid_from/valid_to data-dictionary comments
(comments-only, no schema/data change)

User feedback 2026-08-16, while reviewing Slice D: the data dictionary is the crucial place a
reader learns hidden mapping rules like "this SCD2 window column IS the submission timestamp" --
the original 0014 comments described valid_from/valid_to correctly but never said so explicitly.
Rewords them to spell out the mapping, and adds a note to element_definition's own created_at/
updated_at making clear those are NOT submission timestamps (a natural, reasonable thing to
assume otherwise).

Also documents, in the comment itself, why there is no "withdrawn" timestamp here: withdrawing a
submission is a LIFECYCLE action (recorded in lifecycle_transition, joinable by matching
element_key == subject_ref), not a content-history event -- a withdrawn Interpretation Set's
prior submitted wording simply stays as the latest history row until a real re-submission
happens. This is a deliberate design point (confirmed with the user), not an oversight, and is
now written down so a future reader doesn't have to rediscover it from code.

No CREATE/ALTER/DROP of any table or column -- COMMENT ON statements only. Reversible
(downgrade restores the original 0014 wording). Zero risk either direction, matches the
established precedent of migration 0009.
"""
from __future__ import annotations

from alembic import op

revision = "0016_clarify_content_comments"
down_revision = "0015_reference_sets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        COMMENT ON COLUMN element_definition.created_at IS
          'When content was first written for this field (system timestamp, not a business date). NOT a submission timestamp -- this table has no submission concept of its own; see element_definition_history.valid_from for that.';
        COMMENT ON COLUMN element_definition.updated_at IS
          'When this field''s content was last changed by an ordinary save (system timestamp, not a business date). NOT a submission timestamp -- see element_definition_history.valid_from for that.';

        COMMENT ON COLUMN element_definition_history.valid_from IS
          'This row''s SUBMITTED-AT timestamp -- a history row is only ever created at the moment its Interpretation Set was submitted, so valid_from IS that submission moment, just named to match the valid_from/valid_to window pattern shared by every other history table in this database (dq_score_history, semantic_type_assignment_history, reference_code_history).';
        COMMENT ON COLUMN element_definition_history.valid_to IS
          'The valid_from (submitted-at) of whichever LATER submission superseded this wording; NULL while this is still the most recently submitted wording. Deliberately does NOT close when a submission is withdrawn -- withdrawing is a lifecycle action, not a content event, so a withdrawn submission''s wording simply remains the latest history row until a real re-submission happens. Find the withdrawal itself (who, when) by joining lifecycle_transition on subject_ref = element_key, looking for to_status = ''withdrawn''.';
        """
    )


def downgrade() -> None:
    op.execute(
        """
        COMMENT ON COLUMN element_definition.created_at IS
          'When content was first written for this field (system timestamp, not a business date).';
        COMMENT ON COLUMN element_definition.updated_at IS
          'When this field''s content was last changed (system timestamp, not a business date).';

        COMMENT ON COLUMN element_definition_history.valid_from IS
          'The real moment this wording took effect -- this period opens here.';
        COMMENT ON COLUMN element_definition_history.valid_to IS
          'The real moment a later submission replaced this wording; empty while this is still the most recent submitted wording.';
        """
    )
