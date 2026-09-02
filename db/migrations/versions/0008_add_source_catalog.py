"""add source catalog tables (source-catalog YAML -> Postgres migration, Phase 2 schema)

Replaces sources/generated/*.yaml and mappings/target_catalogs/*.yaml as the eventual live
store for source/target schema + profiling metadata, behind the catalog_backend flag
(default yaml — this migration is purely additive, nothing reads/writes these tables yet).

Three "current" tables mirror the canonical schemas -> tables -> columns shape the extraction
layer already produces (catalog_source -> catalog_dataset -> catalog_element), plus a
refresh-event log and two append-only snapshot tables for history (D8: snapshot pattern,
mirroring core/dq_score_store.py's retention convention, not SCD2 — confirmed 2026-08-05).

Field lists mirror core/extractors/profiler.py's real table- and column-level output exactly
(see openspec/changes/migrate-source-catalog-yaml-to-postgres/design.md D1-D10 for the full
per-decision rationale). PK/FK/relations and sample/top values stay JSONB (D2, confirmed
2026-08-05 — not normalized into their own tables for now).

One refinement vs. the tasks.md wording: catalog_element is uniquely keyed by (dataset_id,
qualified_column_name) rather than (dataset_id, column_name) — qualified_column_name is always
unique per dataset even once nesting exists (D7), whereas a bare column_name can repeat across
different parents once nested sources are onboarded (e.g. "address.id" vs "customer.id"). For
today's flat sources qualified_column_name == column_name, so this changes nothing yet;
(dataset_id, column_name) is kept as a plain (non-unique) index instead, for fast lookup by
leaf name.

catalog_element_snapshot's parent_element_id is a plain frozen value (no FK constraint) since
a historical snapshot should not depend on the live identity of a possibly-since-changed
parent row.

Both snapshot tables also carry a UNIQUE(dataset_id/element_id, captured_at) constraint
alongside their surrogate `id` PK — matching the surrogate-PK-plus-natural-unique-constraint
pattern already used by catalog_source/catalog_dataset/catalog_element, rather than leaving
the "one snapshot per instant" assumption unenforced.
"""
from __future__ import annotations

from alembic import op

revision = "0008_source_catalog"
down_revision = "0007_audit_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE catalog_source (
            source_id      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            source_name    TEXT NOT NULL,
            kind           TEXT NOT NULL CHECK (kind IN ('source', 'target')),
            connector_type TEXT,
            connection_ref TEXT,
            legal_entity   TEXT,
            version        INT,
            schema_hash    TEXT,
            generated_at   TIMESTAMPTZ
        );
        """
    )

    op.execute(
        """
        CREATE TABLE catalog_dataset (
            dataset_id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            source_id              BIGINT NOT NULL REFERENCES catalog_source(source_id) ON DELETE CASCADE,
            schema_name             TEXT NOT NULL,
            table_name              TEXT NOT NULL,
            description             TEXT,
            row_count               BIGINT,
            row_count_error         TEXT,
            primary_key             JSONB,
            inferred_primary_key    JSONB,
            foreign_keys            JSONB,
            relations               JSONB,
            duplicate_count         BIGINT,
            duplicate_pct           NUMERIC,
            orphan_fk_count         BIGINT,
            completeness_summary    NUMERIC,
            pct_columns_described   NUMERIC,
            profiled_at             TIMESTAMPTZ,
            origin_uri              TEXT,
            ingested_at             TIMESTAMPTZ,
            profiling_status        TEXT CHECK (profiling_status IN ('discovered', 'profiled', 'failed', 'excluded')),
            content_hash            TEXT,
            source_modified_at      TIMESTAMPTZ,
            size_bytes              BIGINT,
            file_count              INT,
            format_hint             JSONB,
            UNIQUE (source_id, schema_name, table_name)
        );
        """
    )

    op.execute(
        """
        CREATE TABLE catalog_element (
            element_id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            dataset_id              BIGINT NOT NULL REFERENCES catalog_dataset(dataset_id) ON DELETE CASCADE,
            parent_element_id       BIGINT REFERENCES catalog_element(element_id) ON DELETE CASCADE,
            qualified_column_name   TEXT NOT NULL,
            column_name             TEXT NOT NULL,
            column_kind             TEXT NOT NULL DEFAULT 'scalar'
                                     CHECK (column_kind IN ('scalar', 'object', 'array', 'array_of_object')),
            nesting_level           INT NOT NULL DEFAULT 0,
            ordinal                 INT,
            data_type               TEXT,
            description             TEXT,
            type_distribution       JSONB,
            array_length_min        INT,
            array_length_max        INT,
            array_length_avg        NUMERIC,
            row_count               BIGINT,
            null_count              BIGINT,
            null_pct                NUMERIC,
            distinct_count          BIGINT,
            duplicate_count         BIGINT,
            uniqueness_pct          NUMERIC,
            empty_string_count      BIGINT,
            placeholder_count       BIGINT,
            min_value               TEXT,
            max_value               TEXT,
            length_min              INT,
            length_max              INT,
            length_avg              NUMERIC,
            inferred_pattern        TEXT,
            pattern_confidence      NUMERIC,
            invalid_format_count    BIGINT,
            code_values             JSONB,
            value_distribution      JSONB,
            numeric_avg             NUMERIC,
            numeric_median          NUMERIC,
            numeric_stddev          NUMERIC,
            numeric_outlier_count   BIGINT,
            outlier_detection       TEXT,
            decimal_scale_distribution JSONB,
            future_date_count       BIGINT,
            suspicious_date_count   BIGINT,
            type_mismatch_count     BIGINT,
            validator_pass_rates    JSONB,
            constant_run_warning    JSONB,
            stats_error             TEXT,
            sample_values           JSONB,
            top_values              JSONB,
            UNIQUE (dataset_id, qualified_column_name)
        );
        """
    )
    op.execute("CREATE INDEX ix_catalog_element_dataset_column ON catalog_element (dataset_id, column_name);")
    op.execute("CREATE INDEX ix_catalog_element_parent ON catalog_element (parent_element_id);")

    op.execute(
        """
        CREATE TABLE catalog_refresh_event (
            id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            dataset_id     BIGINT NOT NULL REFERENCES catalog_dataset(dataset_id) ON DELETE CASCADE,
            refreshed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            triggered_by   TEXT,
            changed        BOOLEAN NOT NULL
        );
        """
    )
    op.execute("CREATE INDEX ix_catalog_refresh_event_dataset ON catalog_refresh_event (dataset_id, refreshed_at DESC);")

    op.execute(
        """
        CREATE TABLE catalog_dataset_snapshot (
            id                      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            dataset_id               BIGINT NOT NULL REFERENCES catalog_dataset(dataset_id) ON DELETE CASCADE,
            captured_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
            fingerprint              TEXT NOT NULL,
            schema_name              TEXT,
            table_name               TEXT,
            description              TEXT,
            row_count                BIGINT,
            row_count_error          TEXT,
            primary_key              JSONB,
            inferred_primary_key     JSONB,
            foreign_keys             JSONB,
            relations                JSONB,
            duplicate_count          BIGINT,
            duplicate_pct            NUMERIC,
            orphan_fk_count          BIGINT,
            completeness_summary     NUMERIC,
            pct_columns_described    NUMERIC,
            profiling_status         TEXT,
            content_hash             TEXT,
            source_modified_at       TIMESTAMPTZ,
            size_bytes               BIGINT,
            file_count               INT,
            format_hint              JSONB,
            UNIQUE (dataset_id, captured_at)
        );
        """
    )
    op.execute("CREATE INDEX ix_catalog_dataset_snapshot_lookup ON catalog_dataset_snapshot (dataset_id, captured_at DESC);")

    op.execute(
        """
        CREATE TABLE catalog_element_snapshot (
            id                      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            element_id               BIGINT NOT NULL REFERENCES catalog_element(element_id) ON DELETE CASCADE,
            captured_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
            fingerprint              TEXT NOT NULL,
            parent_element_id        BIGINT,
            qualified_column_name    TEXT,
            column_name              TEXT,
            column_kind              TEXT,
            nesting_level            INT,
            ordinal                  INT,
            data_type                TEXT,
            description              TEXT,
            type_distribution        JSONB,
            array_length_min         INT,
            array_length_max         INT,
            array_length_avg         NUMERIC,
            row_count                BIGINT,
            null_count               BIGINT,
            null_pct                 NUMERIC,
            distinct_count           BIGINT,
            duplicate_count          BIGINT,
            uniqueness_pct           NUMERIC,
            empty_string_count       BIGINT,
            placeholder_count        BIGINT,
            min_value                TEXT,
            max_value                TEXT,
            length_min               INT,
            length_max               INT,
            length_avg               NUMERIC,
            inferred_pattern         TEXT,
            pattern_confidence       NUMERIC,
            invalid_format_count     BIGINT,
            code_values              JSONB,
            value_distribution       JSONB,
            numeric_avg              NUMERIC,
            numeric_median           NUMERIC,
            numeric_stddev           NUMERIC,
            numeric_outlier_count    BIGINT,
            outlier_detection        TEXT,
            decimal_scale_distribution JSONB,
            future_date_count        BIGINT,
            suspicious_date_count    BIGINT,
            type_mismatch_count      BIGINT,
            validator_pass_rates     JSONB,
            constant_run_warning     JSONB,
            stats_error              TEXT,
            sample_values            JSONB,
            top_values               JSONB,
            UNIQUE (element_id, captured_at)
        );
        """
    )
    op.execute("CREATE INDEX ix_catalog_element_snapshot_lookup ON catalog_element_snapshot (element_id, captured_at DESC);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS catalog_element_snapshot;")
    op.execute("DROP TABLE IF EXISTS catalog_dataset_snapshot;")
    op.execute("DROP TABLE IF EXISTS catalog_refresh_event;")
    op.execute("DROP TABLE IF EXISTS catalog_element;")
    op.execute("DROP TABLE IF EXISTS catalog_dataset;")
    op.execute("DROP TABLE IF EXISTS catalog_source;")
