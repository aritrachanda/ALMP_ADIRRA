"""add term.is_cde and term_version.ai_provenance

Revision ID: 0004_cde_and_provenance
Revises: 0003_triage_and_group_meta
Create Date: 2026-07-23

Phase 4a:
  * term.is_cde              — nullable boolean; critical-data-element designation. No UI yet;
                              Phase 5's review scheduler keys review cadence on it (annual for
                              CDE, longer otherwise). Adding the column now is one migration;
                              retrofitting it into a scheduler design later is not.
  * term_version.ai_provenance — dedicated JSONB for per-field AI provenance
                              {field: {model, prompt_id, generated_at}}. Kept SEPARATE from
                              term_version.attributes (regulatory attributes rendered from
                              config) so system metadata never leaks into the attribute UI.
                              NO confidence field — a fabricated % on generated prose invites
                              false trust. Absence is the majority launch state (178/181 terms
                              were generated before provenance existed) -> "provenance not
                              recorded".
"""
from __future__ import annotations

from alembic import op

revision = "0004_cde_and_provenance"
down_revision = "0003_triage_and_group_meta"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE term ADD COLUMN is_cde BOOLEAN;")
    op.execute("ALTER TABLE term_version ADD COLUMN ai_provenance JSONB NOT NULL DEFAULT '{}'::jsonb;")


def downgrade() -> None:
    op.execute("ALTER TABLE term_version DROP COLUMN IF EXISTS ai_provenance;")
    op.execute("ALTER TABLE term DROP COLUMN IF EXISTS is_cde;")
