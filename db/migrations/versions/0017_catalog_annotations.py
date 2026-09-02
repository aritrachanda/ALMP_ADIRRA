"""Add catalog_table_annotation and catalog_column_annotation (govern-pg-e-annotations)

Slice E of the governance YAML->Postgres migration: builds the Postgres home for the catalog
annotation overlay (`sources/generated/<dataset>.annotations.yaml` / `targets/generated/...`) --
user- and AI-authored table/column descriptions and mapping instructions kept separate from the
auto-generated catalog so they survive a catalog rebuild. Fully dormant behind the
`database.annotation_backend` flag (default `yaml`); no data is migrated here (that is Slice E's
own follow-up, mirroring every prior build/migrate split).

Split into two tables at two different granularities -- `catalog_table_annotation` keyed on
`dataset_key` (source|schema|table) and `catalog_column_annotation` keyed on `element_key`
(source|schema|table|column) -- deliberately mirroring the exact same split already used for
`dataset_story` (dataset-level) and `element_definition` (column-level) in Slice C1, rather than
inventing a new single-table-with-a-JSON-blob shape. Text keys, not real foreign keys into
`catalog_dataset`/`catalog_element` -- same reasoning as every other governance table (decision
D1): a catalog rebuild deletes and recreates catalog rows, so a cascading FK would silently
destroy an annotation the moment its source is reprofiled.

No history table: annotations have no submission/review workflow of their own today (matching
`dataset_story`'s reasoning) -- an edit simply overwrites in place, exactly like the YAML file
does today.
"""
from __future__ import annotations

from alembic import op

revision = "0017_catalog_annotations"
down_revision = "0016_clarify_content_comments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE catalog_table_annotation (
            id                    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            dataset_key           TEXT NOT NULL UNIQUE,
            user_description      TEXT,
            mapping_instructions  TEXT,
            created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("CREATE INDEX ix_catalog_table_annotation_key ON catalog_table_annotation (dataset_key);")

    op.execute(
        """
        CREATE TABLE catalog_column_annotation (
            id                    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            element_key           TEXT NOT NULL UNIQUE,
            user_description      TEXT,
            mapping_instructions  TEXT,
            created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("CREATE INDEX ix_catalog_column_annotation_key ON catalog_column_annotation (element_key);")

    op.execute(
        """
        COMMENT ON TABLE catalog_table_annotation IS
          'A user- or AI-authored description and mapping note for one whole table/dataset, kept separate from the auto-generated catalog so it survives a profile rebuild.';
        COMMENT ON COLUMN catalog_table_annotation.id IS 'Internal identifier for this table-level annotation.';
        COMMENT ON COLUMN catalog_table_annotation.dataset_key IS 'Which dataset this annotation is about, as "source|schema|table" (schema blank when the source has none). Matches the same key shape used by dataset_story.';
        COMMENT ON COLUMN catalog_table_annotation.user_description IS 'Plain-language description of what this whole table/dataset represents.';
        COMMENT ON COLUMN catalog_table_annotation.mapping_instructions IS 'Free-text guidance for how this table should be mapped to a target data model, read by the mapping agents as extra context.';
        COMMENT ON COLUMN catalog_table_annotation.created_at IS 'When this annotation was first saved.';
        COMMENT ON COLUMN catalog_table_annotation.updated_at IS 'When this annotation was last edited.';

        COMMENT ON TABLE catalog_column_annotation IS
          'A user- or AI-authored description and mapping note for one column, kept separate from the auto-generated catalog so it survives a profile rebuild.';
        COMMENT ON COLUMN catalog_column_annotation.id IS 'Internal identifier for this column-level annotation.';
        COMMENT ON COLUMN catalog_column_annotation.element_key IS 'Which column this annotation is about, as "source|schema|table|column". Matches the same key shape used by element_definition.';
        COMMENT ON COLUMN catalog_column_annotation.user_description IS 'Plain-language description of what this column represents.';
        COMMENT ON COLUMN catalog_column_annotation.mapping_instructions IS 'Free-text guidance for how this column should be mapped to a target data model, read by the mapping agents as extra context.';
        COMMENT ON COLUMN catalog_column_annotation.created_at IS 'When this annotation was first saved.';
        COMMENT ON COLUMN catalog_column_annotation.updated_at IS 'When this annotation was last edited.';
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS catalog_column_annotation;")
    op.execute("DROP TABLE IF EXISTS catalog_table_annotation;")
