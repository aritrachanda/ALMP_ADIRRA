"""canonical lifecycle vocabulary (Phase 5b.3.0)

Unifies the lifecycle status vocabulary across the three governed items so the stored
backend value equals the UI label's slug (core/lifecycle_vocab.py):

    empty → draft → in_review → approved   (+ returned / rejected / deprecated off-ramps;
                                             withdrawn / revoked are audit-only actions)

Renames of stored values:
  * Interpretation (review_subject.current_state):  initiated → empty, saved → draft
  * Reference code (reference_code.status):          blank → empty
  * Business Glossary (term.status):                 no rows change; the CHECK gains ``empty``

CHECK constraints are widened first (so the UPDATEs are legal), the live resting states and
the append-only lifecycle_transition trail are relabelled to the new vocabulary (a pure
rename — the recorded events themselves are unchanged), then the constraints are re-added.
"""
from __future__ import annotations

from alembic import op

revision = "0006_canonical_lifecycle"
down_revision = "0005_reference_code"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Widen the CHECK constraints first so the value renames below are legal.
    op.execute("ALTER TABLE reference_code DROP CONSTRAINT IF EXISTS reference_code_status_check;")
    op.execute("ALTER TABLE term DROP CONSTRAINT IF EXISTS term_status_check;")

    # 2. Relabel the live resting states to the canonical vocabulary.
    op.execute(
        "UPDATE review_subject SET current_state = 'empty' WHERE current_state = 'initiated';"
    )
    op.execute(
        "UPDATE review_subject SET current_state = 'draft' WHERE current_state = 'saved';"
    )
    op.execute("UPDATE reference_code SET status = 'empty' WHERE status = 'blank';")

    # 3. Relabel the append-only audit trail (pure vocabulary rename; events unchanged).
    for col in ("from_status", "to_status"):
        op.execute(f"UPDATE lifecycle_transition SET {col} = 'empty' WHERE {col} = 'initiated';")
        op.execute(f"UPDATE lifecycle_transition SET {col} = 'draft' WHERE {col} = 'saved';")
        op.execute(f"UPDATE lifecycle_transition SET {col} = 'empty' WHERE {col} = 'blank';")

    # 4. Move the reference_code column default off the old value.
    op.execute("ALTER TABLE reference_code ALTER COLUMN status SET DEFAULT 'empty';")

    # 5. Re-add the CHECK constraints with the canonical vocabulary (DC1: reference_code
    #    pre-adds returned/rejected so the 5b.3.2 queue needs no further schema migration).
    op.execute(
        "ALTER TABLE reference_code ADD CONSTRAINT reference_code_status_check "
        "CHECK (status IN ('empty','draft','in_review','approved','returned','rejected'));"
    )
    op.execute(
        "ALTER TABLE term ADD CONSTRAINT term_status_check "
        "CHECK (status IN ('empty','draft','in_review','approved','deprecated','rejected'));"
    )


def downgrade() -> None:
    # Best-effort inverse (lossy: 'empty'/'draft' cannot be perfectly disambiguated back to
    # the two source vocabularies, but no legacy rows use the pre-rename spellings).
    op.execute("ALTER TABLE reference_code DROP CONSTRAINT IF EXISTS reference_code_status_check;")
    op.execute("ALTER TABLE term DROP CONSTRAINT IF EXISTS term_status_check;")

    op.execute(
        "UPDATE review_subject SET current_state = 'initiated' WHERE current_state = 'empty';"
    )
    op.execute(
        "UPDATE review_subject SET current_state = 'saved' WHERE current_state = 'draft';"
    )
    op.execute("UPDATE reference_code SET status = 'blank' WHERE status = 'empty';")

    for col in ("from_status", "to_status"):
        op.execute(f"UPDATE lifecycle_transition SET {col} = 'initiated' WHERE {col} = 'empty';")
        op.execute(f"UPDATE lifecycle_transition SET {col} = 'saved' WHERE {col} = 'draft';")

    op.execute("ALTER TABLE reference_code ALTER COLUMN status SET DEFAULT 'blank';")
    op.execute(
        "ALTER TABLE reference_code ADD CONSTRAINT reference_code_status_check "
        "CHECK (status IN ('blank','draft','in_review','approved'));"
    )
    op.execute(
        "ALTER TABLE term ADD CONSTRAINT term_status_check "
        "CHECK (status IN ('draft','in_review','approved','deprecated','rejected'));"
    )
