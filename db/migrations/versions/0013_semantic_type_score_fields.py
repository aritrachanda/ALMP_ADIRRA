"""Add score_breakdown / resolution_reason / nearest_candidates to semantic_type_assignment AND
semantic_type_assignment_history (govern-pg-b2-semantic-types-migrate, D1 option (b))

Slice B1's tables were built from ``SemanticTypeStore.default_record()``'s field list. Enumerating
every field actually present across all 2,290 live records in
``governance/semantic_type_assignments.yaml`` (2026-08-14) turned up four fields the resolver
writes at runtime that the default record never declares, and that therefore have no column:

  * ``score_breakdown``    -- 2,290 records carry the key, 1,703 non-null
  * ``resolution_reason``  -- 443 records
  * ``nearest_candidates`` -- 23 records
  * ``data_fingerprint``   -- 49 records (legacy)

Migrating without them would silently discard 1,703 columns' scoring math. This migration adds
real columns for the three live fields (D1 option (b), user-decided 2026-08-14) to BOTH the
current-row table and the history table, so a future submission snapshot stays complete rather
than dropping these three fields the moment they're captured historically. The fourth,
``data_fingerprint``, is deliberately NOT added: it was the parallel fingerprint field merged
away on 2026-08-12 (commit ``f8876ae``), so those 49 values are stale leftovers of a field this
codebase already retired -- they fall away with the migration rather than being carried into a
new column that nothing reads or writes.

All three are nullable with no default, because absence is meaningful: ``resolution_reason`` and
``nearest_candidates`` are written by the resolver ONLY on the widened unresolved path (see
``_record_from_signal`` in ``core/semantic_resolver.py`` -- the keys are omitted entirely
otherwise), and ``score_breakdown`` is explicitly null whenever nothing scored above zero.

``semantic_type_assignment_history`` stays EMPTY after this migration (D2, unchanged) -- these
columns simply make its schema ready for the first real submission after the flip, same as every
other column B1 already added to it.

Data-migration only in intent -- this migration adds columns to two empty, dormant tables; slice
B2's script then populates the current-row table only. ``semantic_backend`` stays ``yaml``; no
behaviour changes here.
"""
from __future__ import annotations

from alembic import op

revision = "0013_semantic_type_score_fields"
down_revision = "0012_semantic_type_assignment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE semantic_type_assignment
            ADD COLUMN score_breakdown    JSONB,
            ADD COLUMN resolution_reason  TEXT,
            ADD COLUMN nearest_candidates JSONB;
        """
    )
    op.execute(
        """
        ALTER TABLE semantic_type_assignment_history
            ADD COLUMN score_breakdown    JSONB,
            ADD COLUMN resolution_reason  TEXT,
            ADD COLUMN nearest_candidates JSONB;
        """
    )

    op.execute(
        """
        COMMENT ON COLUMN semantic_type_assignment.score_breakdown IS
          'How the resolver arrived at its confidence for this column: the starting score, each named adjustment applied (and whether the total was capped), and the final score and evidence tier. Null when nothing scored above zero.';
        COMMENT ON COLUMN semantic_type_assignment.resolution_reason IS
          'Why this column could not be resolved to a type: no usable signal at all, a near-miss that was corroborated but never initiated, a conflict with the observed values, or a best candidate that fell below the acceptance floor. Null when the column did resolve.';
        COMMENT ON COLUMN semantic_type_assignment.nearest_candidates IS
          'The runner-up types that came closest when nothing cleared the bar, with what blocked each one -- so a steward can see what was nearly chosen. Null when the column resolved or nothing came close.';
        COMMENT ON COLUMN semantic_type_assignment_history.score_breakdown IS
          'The scoring breakdown behind the accepted deduction, as it stood at submission time.';
        COMMENT ON COLUMN semantic_type_assignment_history.resolution_reason IS
          'Why the column was unresolved at submission time, when applicable.';
        COMMENT ON COLUMN semantic_type_assignment_history.nearest_candidates IS
          'The runner-up types recorded at submission time, when the column was unresolved.';
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE semantic_type_assignment_history
            DROP COLUMN IF EXISTS nearest_candidates,
            DROP COLUMN IF EXISTS resolution_reason,
            DROP COLUMN IF EXISTS score_breakdown;
        """
    )
    op.execute(
        """
        ALTER TABLE semantic_type_assignment
            DROP COLUMN IF EXISTS nearest_candidates,
            DROP COLUMN IF EXISTS resolution_reason,
            DROP COLUMN IF EXISTS score_breakdown;
        """
    )
