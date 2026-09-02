"""initial glossary v2 schema (PROVISIONAL — pending 01b live verification)

Revision ID: 0001_initial_glossary
Revises:
Create Date: 2026-07-23

Business Glossary v2 backbone. Machinery generalised (lifecycle_transition,
review_subject, review_task), content kept term-shaped (term_version). See
docs/architecture/Glossary Rebuild/reports/01a-schema-design-report.md for the
full rationale, the status-enum mapping, and the linkage-granularity findings that
drove the linkage table shape.

Status columns use TEXT + CHECK (not native ENUM) so the canonical status set can
evolve without ALTER TYPE gymnastics — deliberate, given status is load-bearing for
DQ scoring and expected to grow (in_review) in later phases.
"""
from __future__ import annotations

from alembic import op

revision = "0001_initial_glossary"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")

    # array_to_string(anyarray, text) is STABLE (element output funcs can be
    # non-immutable for arbitrary types), so it can't be used directly in a
    # generated column. For text[] + a constant separator the result is fully
    # deterministic, so we wrap it in an IMMUTABLE SQL function to feed the
    # term_version.search_tsv generated column (keeps synonyms/tags in FTS).
    op.execute(
        """
        CREATE FUNCTION glossary_text_join(text[], text) RETURNS text
        LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT AS
        $$ SELECT array_to_string($1, $2) $$;
        """
    )

    # ── glossary: container (supports >1 glossary later; one row for now) ────────
    op.execute(
        """
        CREATE TABLE glossary (
            id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            key         TEXT NOT NULL UNIQUE,
            name        TEXT NOT NULL,
            description TEXT,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )

    # ── term: stable identity + current governance status ───────────────────────
    op.execute(
        """
        CREATE TABLE term (
            id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            glossary_id BIGINT NOT NULL REFERENCES glossary(id) ON DELETE CASCADE,
            parent_term_id BIGINT REFERENCES term(id) ON DELETE SET NULL,  -- display hierarchy (Phase 4 drag-to-reparent; depth capped in app)
            slug        TEXT NOT NULL,                 -- old string id, e.g. 'credit_quality_step'
            domain      TEXT,
            category    TEXT,
            steward     TEXT,
            status      TEXT NOT NULL DEFAULT 'draft'
                        CHECK (status IN ('draft','in_review','approved','deprecated','rejected')),
            next_review_due DATE,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (glossary_id, slug)
        );
        """
    )
    op.execute("CREATE INDEX ix_term_status ON term(status);")
    op.execute("CREATE INDEX ix_term_domain_category ON term(domain, category);")
    op.execute("CREATE INDEX ix_term_steward ON term(steward);")
    op.execute("CREATE INDEX ix_term_parent ON term(parent_term_id);")

    # ── term_version: term-shaped, effective-dated prose (NOT generalised) ───────
    #  attributes JSONB holds custom regulatory fields (crr3_context, dpm2_context, …)
    #  — chosen over an EAV term_attribute table (see report D4).
    op.execute(
        """
        CREATE TABLE term_version (
            id                   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            term_id              BIGINT NOT NULL REFERENCES term(id) ON DELETE CASCADE,
            version_no           INTEGER NOT NULL,
            title                TEXT NOT NULL,
            business_description TEXT,
            detailed_description TEXT,
            synonyms             TEXT[] NOT NULL DEFAULT '{}',
            tags                 TEXT[] NOT NULL DEFAULT '{}',
            attributes           JSONB  NOT NULL DEFAULT '{}'::jsonb,
            ai_generated_fields  TEXT[] NOT NULL DEFAULT '{}',
            status               TEXT NOT NULL DEFAULT 'draft'
                                 CHECK (status IN ('draft','approved','superseded')),
            is_current_approved  BOOLEAN NOT NULL DEFAULT false,
            valid_from           TIMESTAMPTZ,
            valid_to             TIMESTAMPTZ,
            authored_by          TEXT,
            authored_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            search_tsv           tsvector GENERATED ALWAYS AS (
                to_tsvector('english'::regconfig,
                    coalesce(title,'') || ' ' ||
                    coalesce(business_description,'') || ' ' ||
                    coalesce(detailed_description,'') || ' ' ||
                    glossary_text_join(synonyms,' ') || ' ' ||
                    glossary_text_join(tags,' ')
                )
            ) STORED,
            UNIQUE (term_id, version_no)
        );
        """
    )
    # At most ONE current-approved version per term (effective-dating anchor).
    op.execute(
        "CREATE UNIQUE INDEX uq_term_version_current_approved "
        "ON term_version(term_id) WHERE is_current_approved;"
    )
    op.execute("CREATE INDEX ix_term_version_search ON term_version USING GIN (search_tsv);")
    op.execute("CREATE INDEX ix_term_version_title_trgm ON term_version USING GIN (title gin_trgm_ops);")
    op.execute("CREATE INDEX ix_term_version_synonyms ON term_version USING GIN (synonyms);")
    op.execute("CREATE INDEX ix_term_version_attributes ON term_version USING GIN (attributes);")

    # ── term_relation: term↔term (absorbs the 62 free-text concept refs) ─────────
    #  to_term_id set when the related concept resolves to a real term;
    #  to_label holds the raw free-text ('Residential property', 'ISO 17442', …).
    op.execute(
        """
        CREATE TABLE term_relation (
            id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            from_term_id  BIGINT NOT NULL REFERENCES term(id) ON DELETE CASCADE,
            relation_type TEXT NOT NULL
                          CHECK (relation_type IN ('broader','narrower','related','synonym_of')),
            to_term_id    BIGINT REFERENCES term(id) ON DELETE CASCADE,
            to_label      TEXT,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            CHECK (to_term_id IS NOT NULL OR to_label IS NOT NULL),
            UNIQUE (from_term_id, relation_type, to_term_id, to_label)
        );
        """
    )
    op.execute("CREATE INDEX ix_term_relation_from ON term_relation(from_term_id);")
    op.execute("CREATE INDEX ix_term_relation_to ON term_relation(to_term_id);")

    # ── linkage: term↔data element / target concept, granularity FIRST-CLASS ─────
    #  (D1 finding: segment-count can't infer granularity — CRDM.input.X is a TABLE,
    #   not a column. Store it explicitly.)
    op.execute(
        """
        CREATE TABLE linkage (
            id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            term_id     BIGINT NOT NULL REFERENCES term(id) ON DELETE CASCADE,
            kind        TEXT NOT NULL CHECK (kind IN ('source','target')),
            granularity TEXT NOT NULL CHECK (granularity IN ('dataset','table','column')),
            dataset     TEXT NOT NULL,
            schema_name TEXT,
            table_name  TEXT,
            column_name TEXT,
            raw_ref     TEXT NOT NULL,               -- original 'kind|dataset|path' string
            status      TEXT NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active','needs_revalidation','stale')),
            origin      TEXT NOT NULL DEFAULT 'migrated'
                        CHECK (origin IN ('human','ai','migrated')),
            confidence  NUMERIC(4,3),
            rationale   TEXT,
            resolved    BOOLEAN NOT NULL DEFAULT true,  -- false → points at a missing catalog asset (triage)
            reviewed_by TEXT,
            reviewed_at TIMESTAMPTZ,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (term_id, raw_ref)
        );
        """
    )
    # Reverse lookup (element side): "which term(s) link this column?" — replaces
    # the mtime-cached YAML index in api/routes/element.py. Many-to-many capable.
    op.execute(
        "CREATE INDEX ix_linkage_target "
        "ON linkage(kind, dataset, schema_name, table_name, column_name);"
    )
    op.execute("CREATE INDEX ix_linkage_term ON linkage(term_id);")
    op.execute(
        "CREATE INDEX ix_linkage_needs_reval ON linkage(status) "
        "WHERE status = 'needs_revalidation';"
    )

    # ── lifecycle_transition: generic append-only status history (History tab) ───
    #  subject_ref is TEXT (not a BIGINT id) so this serves subjects that have no
    #  numeric PK — e.g. element_interpretation keyed 'source:schema.table.column'.
    #  For glossary terms, subject_ref = term.id::text. This is the D7 generality test.
    op.execute(
        """
        CREATE TABLE lifecycle_transition (
            id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            subject_type TEXT NOT NULL,               -- 'glossary_term' now; agnostic
            subject_ref  TEXT NOT NULL,               -- natural key of the subject
            from_status  TEXT,
            to_status    TEXT NOT NULL,
            actor        TEXT,
            actor_role   TEXT,
            reason       TEXT,
            occurred_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        "CREATE INDEX ix_transition_subject "
        "ON lifecycle_transition(subject_type, subject_ref, occurred_at DESC);"
    )

    # ── review_subject / review_task: generic review machinery (subject-agnostic) ─
    op.execute(
        """
        CREATE TABLE review_subject (
            id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            subject_type    TEXT NOT NULL,            -- 'glossary_term','element_interpretation',…
            subject_ref     TEXT NOT NULL,            -- natural key of the subject
            current_state   TEXT NOT NULL,
            assigned_to     TEXT,
            next_review_due DATE,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (subject_type, subject_ref)
        );
        """
    )
    op.execute("CREATE INDEX ix_review_subject_state ON review_subject(subject_type, current_state);")
    op.execute("CREATE INDEX ix_review_subject_assignee ON review_subject(assigned_to);")
    op.execute("CREATE INDEX ix_review_subject_due ON review_subject(next_review_due);")

    op.execute(
        """
        CREATE TABLE review_task (
            id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            review_subject_id BIGINT NOT NULL REFERENCES review_subject(id) ON DELETE CASCADE,
            task_type         TEXT NOT NULL,          -- 'definition_review','linkage_revalidation',…
            state             TEXT NOT NULL DEFAULT 'open'
                              CHECK (state IN ('open','in_progress','approved','rejected','cancelled')),
            assigned_to       TEXT,
            decided_by        TEXT,
            decided_by_role   TEXT,
            decision          TEXT,
            reason            TEXT,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            decided_at        TIMESTAMPTZ
        );
        """
    )
    op.execute("CREATE INDEX ix_review_task_state ON review_task(state);")
    op.execute("CREATE INDEX ix_review_task_subject ON review_task(review_subject_id);")


def downgrade() -> None:
    for tbl in (
        "review_task",
        "review_subject",
        "lifecycle_transition",
        "linkage",
        "term_relation",
        "term_version",
        "term",
        "glossary",
    ):
        op.execute(f"DROP TABLE IF EXISTS {tbl} CASCADE;")
    op.execute("DROP FUNCTION IF EXISTS glossary_text_join(text[], text);")
    # pg_trgm left installed intentionally (cheap, may be shared).
