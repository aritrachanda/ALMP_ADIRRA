"""Add element_definition (+history), dataset_story, element_assessment_scope
(govern-pg-c1-element-content-build)

Slice C1 of the governance YAML->Postgres migration: builds the Postgres home for the CONTENT
people author about their data -- the definition and business name of a field, the narrative and
data grain of a dataset, and a field's assessment scope. Fully dormant behind the
`database.element_content_backend` flag (default `yaml`); no data is migrated here (that is C2).

Deliberately NOT included (user-confirmed 2026-08-15, all already superseded by earlier slices):
  * the legacy `states` section          -> `review_subject` owns lifecycle since element_backend flipped
  * `refdata_meanings` / `refdata_status`-> `reference_code` owns code meanings since refdata_backend flipped
  * `business_name_state`                -> Business Name has no lifecycle of its own; it is reviewed
                                            as one component of the whole Interpretation Set
  * `refdata_bound_set_id`               -> belongs to slice D (reference sets), stays in YAML for now

HISTORY (user decision 2026-08-15): element content is versioned, not overwritten. Today's YAML
keeps no history at all -- editing a definition destroys the previous wording permanently. A new
`element_definition_history` window opens when the Interpretation Set is SUBMITTED, not on every
intermediate save -- deliberately mirroring `semantic_type_assignment_history`'s already-shipped
rule (B1), so the two components of the same Interpretation Set version in lockstep rather than
one of them cutting a version on every keystroke.

The current-row tables keep saving immediately on Save, exactly as the YAML store does today --
this migration changes where content lives, never when a steward's action takes effect.
"""
from __future__ import annotations

from alembic import op

revision = "0014_element_content"
down_revision = "0013_semantic_type_score_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE element_definition (
            id                   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            element_key          TEXT NOT NULL UNIQUE,
            definition           TEXT,
            definition_is_ai     BOOLEAN NOT NULL DEFAULT false,
            business_name        TEXT,
            business_name_is_ai  BOOLEAN NOT NULL DEFAULT false,
            criticality          TEXT,
            created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT element_definition_criticality_check
                CHECK (criticality IS NULL OR criticality IN ('standard', 'critical'))
        );
        """
    )
    op.execute("CREATE INDEX ix_element_definition_key ON element_definition (element_key);")

    op.execute(
        """
        CREATE TABLE element_definition_history (
            id                     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            element_definition_id  BIGINT NOT NULL
                REFERENCES element_definition(id) ON DELETE CASCADE,
            element_key            TEXT NOT NULL,
            definition             TEXT,
            definition_is_ai       BOOLEAN NOT NULL DEFAULT false,
            business_name          TEXT,
            business_name_is_ai    BOOLEAN NOT NULL DEFAULT false,
            submitted_by           TEXT,
            valid_from             TIMESTAMPTZ NOT NULL,
            valid_to               TIMESTAMPTZ,
            created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT element_definition_history_window_check
                CHECK (valid_to IS NULL OR valid_to > valid_from)
        );
        """
    )
    op.execute(
        "CREATE INDEX ix_element_definition_history_key_window "
        "ON element_definition_history (element_key, valid_from);"
    )
    op.execute(
        "CREATE INDEX ix_element_definition_history_definition_id "
        "ON element_definition_history (element_definition_id);"
    )
    op.execute(
        "CREATE UNIQUE INDEX ux_element_definition_history_open "
        "ON element_definition_history (element_key) WHERE valid_to IS NULL;"
    )

    op.execute(
        """
        CREATE TABLE dataset_story (
            id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            dataset_key       TEXT NOT NULL UNIQUE,
            narrative         TEXT,
            data_grain        TEXT,
            is_ai_generated   BOOLEAN NOT NULL DEFAULT false,
            generated_at      TIMESTAMPTZ,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("CREATE INDEX ix_dataset_story_key ON dataset_story (dataset_key);")

    op.execute(
        """
        CREATE TABLE element_assessment_scope (
            id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            element_key   TEXT NOT NULL UNIQUE,
            scope         TEXT NOT NULL DEFAULT 'in_scope',
            scope_reason  TEXT,
            scoped_by     TEXT,
            scoped_at     TIMESTAMPTZ,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT element_assessment_scope_scope_check
                CHECK (scope IN ('in_scope', 'out_of_scope'))
        );
        """
    )
    op.execute("CREATE INDEX ix_element_assessment_scope_key ON element_assessment_scope (element_key);")

    op.execute(
        """
        COMMENT ON TABLE element_definition IS
          'What a person has written about one field: its definition and its business name, as they stand right now. One row per field.';
        COMMENT ON COLUMN element_definition.id IS
          'Internal identifier for this field''s content row.';
        COMMENT ON COLUMN element_definition.element_key IS
          '"source|schema|table|column" -- which field this content describes.';
        COMMENT ON COLUMN element_definition.definition IS
          'The agreed explanation of what this field holds and means, in the organisation''s own words.';
        COMMENT ON COLUMN element_definition.definition_is_ai IS
          'True when the definition currently shown was written by AI and not since edited by a person.';
        COMMENT ON COLUMN element_definition.business_name IS
          'The readable, human-friendly name for this field, as opposed to its technical column name.';
        COMMENT ON COLUMN element_definition.business_name_is_ai IS
          'True when the business name currently shown was written by AI and not since edited by a person.';
        COMMENT ON COLUMN element_definition.criticality IS
          'How much this field matters to the organisation -- a critical field can be made to count double when a dataset''s overall quality score is worked out. Not yet in active use.';
        COMMENT ON COLUMN element_definition.created_at IS
          'When content was first written for this field (system timestamp, not a business date).';
        COMMENT ON COLUMN element_definition.updated_at IS
          'When this field''s content was last changed (system timestamp, not a business date).';

        COMMENT ON TABLE element_definition_history IS
          'What a field''s definition and business name said during a past period. A new row opens each time the field''s Interpretation Set is submitted for review, so you can answer "what did this say back then".';
        COMMENT ON COLUMN element_definition_history.id IS
          'Internal identifier for this historical row.';
        COMMENT ON COLUMN element_definition_history.element_definition_id IS
          'The field''s current content row that this piece of history belongs to.';
        COMMENT ON COLUMN element_definition_history.element_key IS
          '"source|schema|table|column" this history is about, copied here so it can be queried without a join.';
        COMMENT ON COLUMN element_definition_history.definition IS
          'The definition as it stood during this period.';
        COMMENT ON COLUMN element_definition_history.definition_is_ai IS
          'Whether that definition had been written by AI rather than a person, at that time.';
        COMMENT ON COLUMN element_definition_history.business_name IS
          'The business name as it stood during this period.';
        COMMENT ON COLUMN element_definition_history.business_name_is_ai IS
          'Whether that business name had been written by AI rather than a person, at that time.';
        COMMENT ON COLUMN element_definition_history.submitted_by IS
          'Who submitted the Interpretation Set that opened this period.';
        COMMENT ON COLUMN element_definition_history.valid_from IS
          'The real moment this wording took effect -- this period opens here.';
        COMMENT ON COLUMN element_definition_history.valid_to IS
          'The real moment a later submission replaced this wording; empty while this is still the most recent submitted wording.';
        COMMENT ON COLUMN element_definition_history.created_at IS
          'When this historical row itself was written (system timestamp, not a business date).';

        COMMENT ON TABLE dataset_story IS
          'The plain-language story of one dataset: what it is about, and what a single row in it represents. One row per dataset.';
        COMMENT ON COLUMN dataset_story.id IS
          'Internal identifier for this dataset''s story row.';
        COMMENT ON COLUMN dataset_story.dataset_key IS
          '"source|schema|table" -- which dataset this story describes.';
        COMMENT ON COLUMN dataset_story.narrative IS
          'The descriptive story of what this dataset contains and what it is used for.';
        COMMENT ON COLUMN dataset_story.data_grain IS
          'What one single row of this dataset actually represents -- for example "one loan per reporting date". Its own field rather than an afterthought of the narrative.';
        COMMENT ON COLUMN dataset_story.is_ai_generated IS
          'True when this story (narrative and data grain together) was written by AI and not since edited by a person.';
        COMMENT ON COLUMN dataset_story.generated_at IS
          'When this story was last produced or rewritten.';
        COMMENT ON COLUMN dataset_story.created_at IS
          'When a story was first written for this dataset (system timestamp, not a business date).';
        COMMENT ON COLUMN dataset_story.updated_at IS
          'When this story was last changed (system timestamp, not a business date).';

        COMMENT ON TABLE element_assessment_scope IS
          'Whether a field is inside or outside the scope of quality assessment. Kept as its own table so the whole idea can be redesigned later without disturbing the field''s other content.';
        COMMENT ON COLUMN element_assessment_scope.id IS
          'Internal identifier for this scope decision.';
        COMMENT ON COLUMN element_assessment_scope.element_key IS
          '"source|schema|table|column" -- which field this scope decision applies to.';
        COMMENT ON COLUMN element_assessment_scope.scope IS
          'Whether this field is assessed for quality at all: in scope, or deliberately excluded.';
        COMMENT ON COLUMN element_assessment_scope.scope_reason IS
          'The stated reason a field was put outside the scope of assessment.';
        COMMENT ON COLUMN element_assessment_scope.scoped_by IS
          'Who made this scope decision.';
        COMMENT ON COLUMN element_assessment_scope.scoped_at IS
          'When this scope decision was made.';
        COMMENT ON COLUMN element_assessment_scope.created_at IS
          'When this row was first written (system timestamp, not a business date).';
        COMMENT ON COLUMN element_assessment_scope.updated_at IS
          'When this row was last changed (system timestamp, not a business date).';
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS element_assessment_scope;")
    op.execute("DROP TABLE IF EXISTS dataset_story;")
    op.execute("DROP TABLE IF EXISTS element_definition_history;")
    op.execute("DROP TABLE IF EXISTS element_definition;")
