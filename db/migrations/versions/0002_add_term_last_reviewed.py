"""add term.last_reviewed

Revision ID: 0002_term_last_reviewed
Revises: 0001_initial_glossary
Create Date: 2026-07-23

Phase 2 gap: the v1 GlossaryTerm carries both last_updated and last_reviewed, but the
0001 schema only had term.updated_at (~ last_updated) and next_review_due. last_reviewed is
term-level governance metadata shown in the UI ("Last Reviewed") and stamped on approval, so
it needs its own column to preserve the existing interface. (last_updated maps to updated_at.)
"""
from __future__ import annotations

from alembic import op

revision = "0002_term_last_reviewed"
down_revision = "0001_initial_glossary"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE term ADD COLUMN last_reviewed TIMESTAMPTZ;")


def downgrade() -> None:
    op.execute("ALTER TABLE term DROP COLUMN IF EXISTS last_reviewed;")
