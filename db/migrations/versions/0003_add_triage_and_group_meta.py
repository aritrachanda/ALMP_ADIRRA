"""add linkage_triage and glossary_group_meta

Revision ID: 0003_triage_and_group_meta
Revises: 0002_term_last_reviewed
Create Date: 2026-07-23

Phase 3 migration support:
  * linkage_triage    — unresolvable related_objects refs (raw string, owning term, reason);
                        the Phase-4 work queue. The refs are ALSO kept as resolved=false
                        linkage rows so related_objects round-trips exactly (YAML↔PG parity).
  * glossary_group_meta — domain/category descriptions from glossary_meta.yaml (so that file
                        is fully migrated, not left as an un-retired survivor).
"""
from __future__ import annotations

from alembic import op

revision = "0003_triage_and_group_meta"
down_revision = "0002_term_last_reviewed"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE linkage_triage (
            id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            term_slug  TEXT NOT NULL,
            raw_ref    TEXT NOT NULL,
            kind       TEXT,
            dataset    TEXT,
            reason     TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("CREATE INDEX ix_triage_reason ON linkage_triage(reason);")
    op.execute("CREATE INDEX ix_triage_term ON linkage_triage(term_slug);")

    op.execute(
        """
        CREATE TABLE glossary_group_meta (
            id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            glossary_id BIGINT NOT NULL REFERENCES glossary(id) ON DELETE CASCADE,
            group_type  TEXT NOT NULL CHECK (group_type IN ('domain','category')),
            name        TEXT NOT NULL,
            description TEXT,
            UNIQUE (glossary_id, group_type, name)
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS glossary_group_meta CASCADE;")
    op.execute("DROP TABLE IF EXISTS linkage_triage CASCADE;")
