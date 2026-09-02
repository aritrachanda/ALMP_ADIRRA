"""Add reference_set (+entry) and element_reference_binding (govern-pg-d-reference-sets)

Slice D of the governance YAML->Postgres migration: builds the Postgres home for the shared
"master" reference code lists (e.g. ISO 4217 Currency Codes) a column can optionally bind to,
plus the column-to-set binding itself (moved out of element_states.yaml's metadata). Fully
dormant behind the `database.refset_backend` flag (default `yaml`); no data is migrated here.

Deliberately NOT included (user-confirmed 2026-08-16, scope finalised before any code written):
  * learned-pattern tables (candidate/decision/pattern) -- the whole subsystem they would have
    served was already deleted from the codebase 2026-08-13 (commit a74802b), so Slice D is now
    just "reference sets".
  * an editing surface for a set's own contents -- the master lists stay hand-edited-file-only
    for this slice, same as they already are today; only the BINDING (column -> set) becomes a
    real write path here, mirroring what already exists in YAML.

`reference_set.parent_set_id` is new (no YAML equivalent): a set may optionally point to another
set (self-referential), per the user's explicit requirement -- same safe self-FK shape already
used for `term.parent_term_id` (ON DELETE SET NULL, so removing a parent never deletes its
children). Building on top of this later ("Reference Codeset Harmonization" -- grouping codes
from different sets into a new custom set) is tracked as its own separate, not-yet-scoped
tech-debt item; this schema does not assume a code entry belongs to only one set's *concept*,
even though today each stored entry row still belongs to exactly one set (harmonization would
add a new table on top, not change this one).

`element_reference_binding.bound_set_id` (user feedback 2026-08-16, revised before this
migration was ever applied with real data): a plain `reference_set_id` FK-style name reads as
generic ownership, not as "the set THIS column is bound to" -- renamed for clarity, matching the
concept's own vocabulary (`bind`/`unbind`/`binding`) used everywhere else in the code.
"""
from __future__ import annotations

from alembic import op

revision = "0015_reference_sets"
down_revision = "0014_element_content"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE reference_set (
            id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            set_id         TEXT NOT NULL UNIQUE,
            name           TEXT NOT NULL,
            kind           TEXT NOT NULL DEFAULT 'local',
            standard_ref   TEXT,
            status         TEXT NOT NULL DEFAULT 'candidate',
            parent_set_id  BIGINT REFERENCES reference_set(id) ON DELETE SET NULL,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT reference_set_kind_check CHECK (kind IN ('standard', 'local')),
            CONSTRAINT reference_set_status_check CHECK (status IN ('approved', 'candidate', 'under_review'))
        );
        """
    )
    op.execute("CREATE INDEX ix_reference_set_parent ON reference_set (parent_set_id);")

    op.execute(
        """
        CREATE TABLE reference_set_entry (
            id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            reference_set_id  BIGINT NOT NULL REFERENCES reference_set(id) ON DELETE CASCADE,
            code              TEXT NOT NULL,
            value             TEXT,
            meaning           TEXT,
            status            TEXT NOT NULL DEFAULT 'active',
            aliases           JSONB,
            effective_from    DATE,
            effective_to      DATE,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT reference_set_entry_status_check CHECK (status IN ('active', 'deprecated')),
            CONSTRAINT ux_reference_set_entry_code UNIQUE (reference_set_id, code)
        );
        """
    )
    op.execute("CREATE INDEX ix_reference_set_entry_set ON reference_set_entry (reference_set_id);")

    op.execute(
        """
        CREATE TABLE element_reference_binding (
            id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            element_key    TEXT NOT NULL UNIQUE,
            bound_set_id   BIGINT NOT NULL REFERENCES reference_set(id) ON DELETE CASCADE,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        "CREATE INDEX ix_element_reference_binding_set ON element_reference_binding (bound_set_id);"
    )

    op.execute(
        """
        COMMENT ON TABLE reference_set IS
          'A shared, reusable "master" code list (e.g. ISO 4217 Currency Codes) that any column can optionally bind to instead of documenting its own codes. Hand-authored/read-only through the app for now.';
        COMMENT ON COLUMN reference_set.id IS 'Internal identifier for this reference set.';
        COMMENT ON COLUMN reference_set.set_id IS 'Stable short id used as the binding target (e.g. "iso_4217_currency") -- never change once a column is bound to it.';
        COMMENT ON COLUMN reference_set.name IS 'Display name shown in the UI, e.g. "ISO 4217 Currency Codes".';
        COMMENT ON COLUMN reference_set.kind IS 'Whether this is a "standard" (an external published code list) or a "local" (in-house/demo) list.';
        COMMENT ON COLUMN reference_set.standard_ref IS 'Which external standard this list represents, e.g. "ISO 4217", when applicable.';
        COMMENT ON COLUMN reference_set.status IS 'Review state of the list itself: approved, candidate, or under_review.';
        COMMENT ON COLUMN reference_set.parent_set_id IS 'Another reference_set this one is nested under, or NULL for a top-level set. Lets one shared list point to another.';
        COMMENT ON COLUMN reference_set.created_at IS 'When this set was created.';
        COMMENT ON COLUMN reference_set.updated_at IS 'When this set was last changed.';

        COMMENT ON TABLE reference_set_entry IS
          'One code inside a reference_set (e.g. "USD = US Dollar" inside the Currency Codes set).';
        COMMENT ON COLUMN reference_set_entry.id IS 'Internal identifier for this entry.';
        COMMENT ON COLUMN reference_set_entry.reference_set_id IS 'Which reference set this code belongs to (plain ownership -- every entry lives inside exactly one set).';
        COMMENT ON COLUMN reference_set_entry.code IS 'The code itself, e.g. "USD".';
        COMMENT ON COLUMN reference_set_entry.value IS 'The code''s expanded/full-word form, e.g. "US Dollar".';
        COMMENT ON COLUMN reference_set_entry.meaning IS 'Plain-language explanation of what this code means.';
        COMMENT ON COLUMN reference_set_entry.status IS 'Whether this code is still active or has been deprecated/retired from the list.';
        COMMENT ON COLUMN reference_set_entry.aliases IS 'Other known spellings/codes for this same entry, as a JSON list.';
        COMMENT ON COLUMN reference_set_entry.effective_from IS 'When this code became valid, if known (optional, for future use).';
        COMMENT ON COLUMN reference_set_entry.effective_to IS 'When this code stopped being valid, if known (optional, for future use).';
        COMMENT ON COLUMN reference_set_entry.created_at IS 'When this entry was created.';
        COMMENT ON COLUMN reference_set_entry.updated_at IS 'When this entry was last changed.';

        COMMENT ON TABLE element_reference_binding IS
          'Records that a specific column is BOUND to a shared reference_set, instead of documenting its own codes. One row per bound column; a column with no row here is simply unbound.';
        COMMENT ON COLUMN element_reference_binding.id IS 'Internal identifier for this binding.';
        COMMENT ON COLUMN element_reference_binding.element_key IS 'The column this binding applies to, as "source|schema|table|column".';
        COMMENT ON COLUMN element_reference_binding.bound_set_id IS 'Which reference_set this column is currently bound to. Deliberately named for the binding concept, not a generic ownership FK -- this is the field to read/write when checking or changing what a column is bound to.';
        COMMENT ON COLUMN element_reference_binding.created_at IS 'When this column was first ever bound to a set. NOTE: if a column is later re-bound directly to a DIFFERENT set (without being unbound first), this stays at the original bind time -- read updated_at for "when did today''s binding take effect".';
        COMMENT ON COLUMN element_reference_binding.updated_at IS 'When this row last changed -- i.e. when the CURRENT bound_set_id took effect. This is the reliable "bound at" timestamp for whatever a column is bound to right now.';
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS element_reference_binding;")
    op.execute("DROP TABLE IF EXISTS reference_set_entry;")
    op.execute("DROP TABLE IF EXISTS reference_set;")

