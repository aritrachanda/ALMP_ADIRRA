"""Add data-dictionary comments for every existing table/column (S0 foundations slice)

Comments-only migration — no data, no constraint, no behavior change of any kind.
Backfills COMMENT ON TABLE / COMMENT ON COLUMN for all 18 tables and 281 columns that existed
before this change (migrations 0001-0008), in plain, non-jargon language describing what each
table/column MEANS and its PURPOSE, not a restatement of its physical SQL type. This closes the
"zero comments in the database" gap found during S0 planning (see
openspec/changes/govern-pg-s0-foundations/, docs/governance-postgres-migration.md §4.2) and
establishes the wording style every future migration's own COMMENT ON statements should follow
going forward (the standing rule — not enforced by tooling, followed by convention/review).

Reversible: downgrade() sets every comment back to NULL. Zero risk either direction.
"""
from __future__ import annotations

from alembic import op

revision = "0009_data_dictionary_comments"
down_revision = "0008_source_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        -- ── glossary ──────────────────────────────────────────────────────────────
        COMMENT ON TABLE glossary IS
          'The single Business Glossary container for this engagement. Today there is always exactly one row — the root the whole glossary hangs off.';
        COMMENT ON COLUMN glossary.id IS 'Internal identifier for this glossary.';
        COMMENT ON COLUMN glossary.key IS 'Stable short code identifying this glossary (e.g. "default").';
        COMMENT ON COLUMN glossary.name IS 'Display name shown in the UI, e.g. "Business Glossary".';
        COMMENT ON COLUMN glossary.description IS 'Optional longer description of what this glossary covers.';
        COMMENT ON COLUMN glossary.created_at IS 'When this glossary was created.';

        -- ── term ──────────────────────────────────────────────────────────────────
        COMMENT ON TABLE term IS
          'One governed business term (e.g. "Collateral Value"). Holds identity, classification and lifecycle status; the term''s actual wording (definition, synonyms, tags) lives in term_version, since a term can be edited/re-versioned over time.';
        COMMENT ON COLUMN term.id IS 'Internal identifier for this term.';
        COMMENT ON COLUMN term.glossary_id IS 'Which glossary this term belongs to.';
        COMMENT ON COLUMN term.parent_term_id IS 'The term one level up in the display hierarchy (for drag-to-reparent browsing), or NULL for a top-level term. Independent of term_relation''s broader/narrower semantic links.';
        COMMENT ON COLUMN term.slug IS 'URL-safe, human-readable identifier for this term, unique within its glossary.';
        COMMENT ON COLUMN term.domain IS 'The business domain this term belongs to, e.g. "Financial" or "Operational".';
        COMMENT ON COLUMN term.category IS 'Finer-grained grouping within a domain.';
        COMMENT ON COLUMN term.steward IS 'The person or role accountable for keeping this term accurate.';
        COMMENT ON COLUMN term.status IS 'Where this term sits in its review lifecycle: empty/draft/in_review/approved/deprecated/rejected.';
        COMMENT ON COLUMN term.next_review_due IS 'When this term is next due for a periodic review.';
        COMMENT ON COLUMN term.last_reviewed IS 'When this term was last reviewed by a steward.';
        COMMENT ON COLUMN term.is_cde IS 'Whether this term is flagged as a Critical Data Element, i.e. one that warrants stricter/more frequent governance attention.';
        COMMENT ON COLUMN term.created_at IS 'When this term was first created.';
        COMMENT ON COLUMN term.updated_at IS 'When this term''s own row (not its content) was last touched.';

        -- ── term_version ──────────────────────────────────────────────────────────
        COMMENT ON TABLE term_version IS
          'The actual wording of a term at a point in time: its title, descriptions, synonyms and tags. A term can have several versions over its life; only one is ever the current approved one.';
        COMMENT ON COLUMN term_version.id IS 'Internal identifier for this version.';
        COMMENT ON COLUMN term_version.term_id IS 'Which term this version belongs to.';
        COMMENT ON COLUMN term_version.version_no IS 'Sequential version number for this term, starting at 1.';
        COMMENT ON COLUMN term_version.title IS 'The term''s display name as of this version.';
        COMMENT ON COLUMN term_version.business_description IS 'Plain-language explanation of what this term means in the business.';
        COMMENT ON COLUMN term_version.detailed_description IS 'Longer, more technical explanation, when the business description alone is not enough.';
        COMMENT ON COLUMN term_version.synonyms IS 'Other names this term is also known by.';
        COMMENT ON COLUMN term_version.tags IS 'Free-text labels used for grouping/filtering terms in the UI.';
        COMMENT ON COLUMN term_version.attributes IS 'Regulatory/reference attributes attached to this term as JSON (e.g. CRR3/DPM context), not user-facing prose.';
        COMMENT ON COLUMN term_version.ai_generated_fields IS 'Which of this version''s fields are still exactly as the AI drafted them (used to show/hide the AI-generated badge per field).';
        COMMENT ON COLUMN term_version.ai_provenance IS 'For each AI-generated field, which model/prompt produced it and when, as JSON. Deliberately carries no confidence score for generated prose.';
        COMMENT ON COLUMN term_version.status IS 'This version''s own lifecycle: draft/approved/superseded.';
        COMMENT ON COLUMN term_version.is_current_approved IS 'True for the one version that is the term''s live, approved content right now.';
        COMMENT ON COLUMN term_version.valid_from IS 'When this version became the current approved content (if it ever was).';
        COMMENT ON COLUMN term_version.valid_to IS 'When this version stopped being the current approved content (if it since was replaced).';
        COMMENT ON COLUMN term_version.authored_by IS 'Who wrote/edited this version.';
        COMMENT ON COLUMN term_version.authored_at IS 'When this version was written.';
        COMMENT ON COLUMN term_version.search_tsv IS 'Auto-generated full-text search index over this version''s title/descriptions/synonyms/tags, used by the glossary search box.';

        -- ── term_relation ─────────────────────────────────────────────────────────
        COMMENT ON TABLE term_relation IS
          'A semantic link between two terms (e.g. "narrower than") or between a term and a free-text concept that has no term of its own yet.';
        COMMENT ON COLUMN term_relation.id IS 'Internal identifier for this relation.';
        COMMENT ON COLUMN term_relation.from_term_id IS 'The term this relation starts from.';
        COMMENT ON COLUMN term_relation.relation_type IS 'The kind of relationship: broader, narrower, related, or synonym_of.';
        COMMENT ON COLUMN term_relation.to_term_id IS 'The other term this relates to, when the target is itself a governed term.';
        COMMENT ON COLUMN term_relation.to_label IS 'A free-text label for the related concept, used when there is no governed term on the other end yet.';
        COMMENT ON COLUMN term_relation.created_at IS 'When this relation was recorded.';

        -- ── linkage ───────────────────────────────────────────────────────────────
        COMMENT ON TABLE linkage IS
          'A connection between a glossary term and a real column/table/dataset it applies to, in either a source or a target data model.';
        COMMENT ON COLUMN linkage.id IS 'Internal identifier for this linkage.';
        COMMENT ON COLUMN linkage.term_id IS 'The glossary term this linkage belongs to.';
        COMMENT ON COLUMN linkage.kind IS 'Whether this linkage points at a source dataset or a target (regulatory) data model.';
        COMMENT ON COLUMN linkage.granularity IS 'The level the linkage points at: dataset, table, or column.';
        COMMENT ON COLUMN linkage.dataset IS 'Which source or target the linkage points into.';
        COMMENT ON COLUMN linkage.schema_name IS 'Schema of the linked object, when applicable.';
        COMMENT ON COLUMN linkage.table_name IS 'Table of the linked object, when applicable.';
        COMMENT ON COLUMN linkage.column_name IS 'Column of the linked object, when the linkage is column-level.';
        COMMENT ON COLUMN linkage.raw_ref IS 'The original, as-written reference string this linkage was parsed from (kept for round-tripping and auditability).';
        COMMENT ON COLUMN linkage.status IS 'Whether this linkage is still active, needs a person to re-check it, or is considered stale.';
        COMMENT ON COLUMN linkage.origin IS 'How this linkage was created: typed by a person, suggested by AI, or carried over from the original migration.';
        COMMENT ON COLUMN linkage.confidence IS 'How confident an AI-suggested linkage is, 0 to 1. Not applicable to human-entered linkages.';
        COMMENT ON COLUMN linkage.rationale IS 'Short explanation of why this linkage was made, when available.';
        COMMENT ON COLUMN linkage.resolved IS 'Whether this linkage could actually be matched to a real column/table in the catalog.';
        COMMENT ON COLUMN linkage.reviewed_by IS 'Who last reviewed this linkage, if anyone.';
        COMMENT ON COLUMN linkage.reviewed_at IS 'When this linkage was last reviewed.';
        COMMENT ON COLUMN linkage.created_at IS 'When this linkage was created.';
        COMMENT ON COLUMN linkage.updated_at IS 'When this linkage was last changed.';
        """
    )

    op.execute(
        """
        -- ── lifecycle_transition ──────────────────────────────────────────────────
        COMMENT ON TABLE lifecycle_transition IS
          'Append-only audit trail of every status change for any governed object (a term, an element''s interpretation, a reference code, etc). One row per transition, never edited or deleted.';
        COMMENT ON COLUMN lifecycle_transition.id IS 'Internal identifier for this transition record.';
        COMMENT ON COLUMN lifecycle_transition.subject_type IS 'What kind of object changed status, e.g. "reference_code" or "element_interpretation".';
        COMMENT ON COLUMN lifecycle_transition.subject_ref IS 'Which specific object changed status, as a text key (shape depends on subject_type).';
        COMMENT ON COLUMN lifecycle_transition.from_status IS 'The status the object was in before this transition. NULL if it had no prior status.';
        COMMENT ON COLUMN lifecycle_transition.to_status IS 'The status the object moved into.';
        COMMENT ON COLUMN lifecycle_transition.actor IS 'Who made this change.';
        COMMENT ON COLUMN lifecycle_transition.actor_role IS 'What role that person held when making the change (e.g. analyst, steward).';
        COMMENT ON COLUMN lifecycle_transition.reason IS 'Free-text reason given for the change, when one was provided.';
        COMMENT ON COLUMN lifecycle_transition.occurred_at IS 'Exactly when this transition happened.';

        -- ── review_subject ────────────────────────────────────────────────────────
        COMMENT ON TABLE review_subject IS
          'The current review state of one governed object (one row per object), independent of the append-only transition history in lifecycle_transition. Drives review-queue listings and due-date tracking.';
        COMMENT ON COLUMN review_subject.id IS 'Internal identifier for this review subject.';
        COMMENT ON COLUMN review_subject.subject_type IS 'What kind of object this is, e.g. "element_interpretation".';
        COMMENT ON COLUMN review_subject.subject_ref IS 'Which specific object this is, as a text key (shape depends on subject_type).';
        COMMENT ON COLUMN review_subject.current_state IS 'The object''s current lifecycle status right now.';
        COMMENT ON COLUMN review_subject.assigned_to IS 'Who this object is currently assigned to for review, if anyone.';
        COMMENT ON COLUMN review_subject.next_review_due IS 'When this object is next due for a periodic re-review.';
        COMMENT ON COLUMN review_subject.created_at IS 'When this review subject was first tracked.';
        COMMENT ON COLUMN review_subject.updated_at IS 'When this review subject''s state was last changed.';

        -- ── linkage_triage ────────────────────────────────────────────────────────
        COMMENT ON TABLE linkage_triage IS
          'A glossary linkage reference that could not be resolved to a real column/table during migration or parsing, kept here for a steward to investigate and fix.';
        COMMENT ON COLUMN linkage_triage.id IS 'Internal identifier for this triage record.';
        COMMENT ON COLUMN linkage_triage.term_slug IS 'The glossary term whose linkage reference failed to resolve.';
        COMMENT ON COLUMN linkage_triage.raw_ref IS 'The original, unresolved reference string.';
        COMMENT ON COLUMN linkage_triage.kind IS 'Whether the failed reference was meant to be a source or target linkage.';
        COMMENT ON COLUMN linkage_triage.dataset IS 'The dataset the reference appeared to point at, if identifiable.';
        COMMENT ON COLUMN linkage_triage.reason IS 'Why this reference could not be resolved, e.g. "table not found".';
        COMMENT ON COLUMN linkage_triage.created_at IS 'When this triage record was created.';

        -- ── glossary_group_meta ───────────────────────────────────────────────────
        COMMENT ON TABLE glossary_group_meta IS
          'A description for a Domain or Category heading shown when browsing the glossary grouped that way (e.g. what "Financial" means as a domain).';
        COMMENT ON COLUMN glossary_group_meta.id IS 'Internal identifier for this group description.';
        COMMENT ON COLUMN glossary_group_meta.glossary_id IS 'Which glossary this group belongs to.';
        COMMENT ON COLUMN glossary_group_meta.group_type IS 'Whether this describes a domain or a category.';
        COMMENT ON COLUMN glossary_group_meta.name IS 'The domain or category name this description is for.';
        COMMENT ON COLUMN glossary_group_meta.description IS 'The description text shown under the group heading.';

        -- ── review_task ───────────────────────────────────────────────────────────
        COMMENT ON TABLE review_task IS
          'One concrete piece of review work queued against a review_subject (e.g. "review this definition"), with its own state and decision, separate from the subject''s overall current_state.';
        COMMENT ON COLUMN review_task.id IS 'Internal identifier for this task.';
        COMMENT ON COLUMN review_task.review_subject_id IS 'Which review subject this task belongs to.';
        COMMENT ON COLUMN review_task.task_type IS 'What kind of review action this task represents.';
        COMMENT ON COLUMN review_task.state IS 'This task''s own progress: open, in_progress, approved, rejected, or cancelled.';
        COMMENT ON COLUMN review_task.assigned_to IS 'Who this task is assigned to.';
        COMMENT ON COLUMN review_task.decided_by IS 'Who made the final decision on this task.';
        COMMENT ON COLUMN review_task.decided_by_role IS 'What role that person held when deciding.';
        COMMENT ON COLUMN review_task.decision IS 'The decision made, e.g. approved or rejected.';
        COMMENT ON COLUMN review_task.reason IS 'Free-text reason for the decision.';
        COMMENT ON COLUMN review_task.created_at IS 'When this task was created.';
        COMMENT ON COLUMN review_task.decided_at IS 'When this task was decided.';

        -- ── reference_code ────────────────────────────────────────────────────────
        COMMENT ON TABLE reference_code IS
          'One distinct code value within a coded column''s code list (e.g. one currency code), with its steward-entered value/meaning and its own review status. One row per code per column.';
        COMMENT ON COLUMN reference_code.id IS 'Internal identifier for this code row.';
        COMMENT ON COLUMN reference_code.element_key IS 'Which column this code belongs to, as text: "source|schema|table|column".';
        COMMENT ON COLUMN reference_code.code IS 'The code value as it appears in the data, e.g. "EUR".';
        COMMENT ON COLUMN reference_code.value IS 'The code''s expanded/full-word form, entered by a steward.';
        COMMENT ON COLUMN reference_code.meaning IS 'The code''s business meaning, entered by a steward.';
        COMMENT ON COLUMN reference_code.origin IS 'Whether this code was observed in the profiled data or was manually declared by a steward.';
        COMMENT ON COLUMN reference_code.status IS 'This code''s own review status: empty/draft/in_review/approved/returned/rejected. Approved rows are frozen.';
        COMMENT ON COLUMN reference_code.submitted_at IS 'When this code was submitted for review.';
        COMMENT ON COLUMN reference_code.submitted_by IS 'Who submitted this code for review.';
        COMMENT ON COLUMN reference_code.approved_at IS 'When this code was approved.';
        COMMENT ON COLUMN reference_code.approved_by IS 'Who approved this code.';
        COMMENT ON COLUMN reference_code.created_at IS 'When this code row was first created.';
        COMMENT ON COLUMN reference_code.updated_at IS 'When this code row was last changed.';

        -- ── audit_events ──────────────────────────────────────────────────────────
        COMMENT ON TABLE audit_events IS
          'Append-only log of every business action and AI call in the system (who did what, to what, and when). Never edited or deleted.';
        COMMENT ON COLUMN audit_events.id IS 'Internal identifier for this event, in occurrence order.';
        COMMENT ON COLUMN audit_events.occurred_at IS 'Exactly when this event happened.';
        COMMENT ON COLUMN audit_events.event_class IS 'Broad category of event, e.g. a business action versus an AI call.';
        COMMENT ON COLUMN audit_events.event_type IS 'The specific kind of event, e.g. "glossary.term.created".';
        COMMENT ON COLUMN audit_events.actor_user_id IS 'Who (or what) performed the action.';
        COMMENT ON COLUMN audit_events.actor_role IS 'What role that actor held at the time.';
        COMMENT ON COLUMN audit_events.legal_entity IS 'Which legal entity/business unit this event relates to, when applicable.';
        COMMENT ON COLUMN audit_events.subject_type IS 'What kind of thing this event was about, e.g. "glossary_term".';
        COMMENT ON COLUMN audit_events.subject_id IS 'Which specific thing this event was about.';
        COMMENT ON COLUMN audit_events.payload IS 'The event''s full detail as JSON (varies by event_type).';
        COMMENT ON COLUMN audit_events.request_id IS 'Correlation id linking this event back to the API request that caused it.';
        """
    )

    op.execute(
        """
        -- ── catalog_source ────────────────────────────────────────────────────────
        COMMENT ON TABLE catalog_source IS
          'A connected source or target system (e.g. a bank''s core system, or a regulatory target model) at the root of the catalog. One row per source/target.';
        COMMENT ON COLUMN catalog_source.source_id IS 'Internal identifier for this source/target.';
        COMMENT ON COLUMN catalog_source.source_name IS 'Display name of the source or target, e.g. "ALM Bank".';
        COMMENT ON COLUMN catalog_source.kind IS 'Whether this is a data source or a target (regulatory) model.';
        COMMENT ON COLUMN catalog_source.connector_type IS 'What kind of connection this is (e.g. database type), when known.';
        COMMENT ON COLUMN catalog_source.connection_ref IS 'Reference to the connection details used to reach this source (see connections.yaml).';
        COMMENT ON COLUMN catalog_source.legal_entity IS 'Which legal entity/business unit this source belongs to, when applicable.';
        COMMENT ON COLUMN catalog_source.version IS 'Version marker for this source''s catalog, when the source itself is versioned.';
        COMMENT ON COLUMN catalog_source.schema_hash IS 'Hash of the source''s schema shape, used to detect structural changes.';
        COMMENT ON COLUMN catalog_source.generated_at IS 'When this source''s catalog was last (re)generated.';

        -- ── catalog_dataset ───────────────────────────────────────────────────────
        COMMENT ON TABLE catalog_dataset IS
          'One table or dataset within a source, with its profiling summary (row counts, keys, completeness). One row per dataset.';
        COMMENT ON COLUMN catalog_dataset.dataset_id IS 'Internal identifier for this dataset.';
        COMMENT ON COLUMN catalog_dataset.source_id IS 'Which source/target this dataset belongs to.';
        COMMENT ON COLUMN catalog_dataset.schema_name IS 'Schema this dataset lives in.';
        COMMENT ON COLUMN catalog_dataset.table_name IS 'The table/dataset name.';
        COMMENT ON COLUMN catalog_dataset.description IS 'Description of what this dataset contains (may be overlaid by a user-authored annotation at read time).';
        COMMENT ON COLUMN catalog_dataset.row_count IS 'Number of rows in this dataset as of the last profile.';
        COMMENT ON COLUMN catalog_dataset.row_count_error IS 'Error message if the row count could not be determined.';
        COMMENT ON COLUMN catalog_dataset.primary_key IS 'The dataset''s declared primary key column(s), as JSON.';
        COMMENT ON COLUMN catalog_dataset.inferred_primary_key IS 'A primary key the profiler inferred from the data, when none was declared, as JSON.';
        COMMENT ON COLUMN catalog_dataset.foreign_keys IS 'The dataset''s declared foreign key relationships, as JSON.';
        COMMENT ON COLUMN catalog_dataset.relations IS 'Other relationships detected between this dataset and others, as JSON.';
        COMMENT ON COLUMN catalog_dataset.duplicate_count IS 'Number of duplicate rows found in this dataset.';
        COMMENT ON COLUMN catalog_dataset.duplicate_pct IS 'Percentage of rows that are duplicates.';
        COMMENT ON COLUMN catalog_dataset.orphan_fk_count IS 'Number of rows whose foreign key does not match any row in the referenced table.';
        COMMENT ON COLUMN catalog_dataset.completeness_summary IS 'Overall completeness score for this dataset (how filled-in its columns are).';
        COMMENT ON COLUMN catalog_dataset.pct_columns_described IS 'Percentage of this dataset''s columns that have a governed description.';
        COMMENT ON COLUMN catalog_dataset.profiled_at IS 'When this dataset was last profiled.';
        COMMENT ON COLUMN catalog_dataset.origin_uri IS 'Where this dataset''s underlying data came from (file path, URI, etc.), for non-database sources.';
        COMMENT ON COLUMN catalog_dataset.ingested_at IS 'When this dataset was first onboarded into the catalog.';
        COMMENT ON COLUMN catalog_dataset.profiling_status IS 'Where this dataset is in the profiling lifecycle: discovered, profiled, failed, or excluded.';
        COMMENT ON COLUMN catalog_dataset.content_hash IS 'Hash of the dataset''s underlying content/file, used to detect real data changes.';
        COMMENT ON COLUMN catalog_dataset.source_modified_at IS 'When the underlying source data was last modified, if known.';
        COMMENT ON COLUMN catalog_dataset.size_bytes IS 'Size of the underlying data, in bytes, for file-based sources.';
        COMMENT ON COLUMN catalog_dataset.file_count IS 'Number of files making up this dataset, for file-based sources.';
        COMMENT ON COLUMN catalog_dataset.format_hint IS 'File-format-specific details (e.g. delimiter, encoding), as JSON, for file-based sources.';

        -- ── catalog_element ───────────────────────────────────────────────────────
        COMMENT ON TABLE catalog_element IS
          'One column (or nested field) within a dataset, with its full profiling statistics. One row per column.';
        COMMENT ON COLUMN catalog_element.element_id IS 'Internal identifier for this column.';
        COMMENT ON COLUMN catalog_element.dataset_id IS 'Which dataset this column belongs to.';
        COMMENT ON COLUMN catalog_element.parent_element_id IS 'The parent field this column is nested under, for semi-structured data. NULL for a top-level column.';
        COMMENT ON COLUMN catalog_element.qualified_column_name IS 'The column''s fully-qualified name including any nesting path, unique within its dataset.';
        COMMENT ON COLUMN catalog_element.column_name IS 'The column''s own (leaf) name.';
        COMMENT ON COLUMN catalog_element.column_kind IS 'Whether this is a plain scalar column or a structured/nested field.';
        COMMENT ON COLUMN catalog_element.nesting_level IS 'How many levels deep this field is nested; 0 for a top-level column.';
        COMMENT ON COLUMN catalog_element.ordinal IS 'The column''s position within its dataset.';
        COMMENT ON COLUMN catalog_element.data_type IS 'The column''s physical data type as seen in the source.';
        COMMENT ON COLUMN catalog_element.description IS 'Description of what this column holds (may be overlaid by a user-authored annotation at read time).';
        COMMENT ON COLUMN catalog_element.type_distribution IS 'Breakdown of the different physical types observed in this column''s values, as JSON (relevant for loosely-typed sources).';
        COMMENT ON COLUMN catalog_element.array_length_min IS 'Shortest array length observed, for array-typed columns.';
        COMMENT ON COLUMN catalog_element.array_length_max IS 'Longest array length observed, for array-typed columns.';
        COMMENT ON COLUMN catalog_element.array_length_avg IS 'Average array length observed, for array-typed columns.';
        COMMENT ON COLUMN catalog_element.row_count IS 'Number of rows considered when profiling this column.';
        COMMENT ON COLUMN catalog_element.null_count IS 'Number of null values in this column.';
        COMMENT ON COLUMN catalog_element.null_pct IS 'Percentage of values that are null.';
        COMMENT ON COLUMN catalog_element.distinct_count IS 'Number of distinct values observed.';
        COMMENT ON COLUMN catalog_element.duplicate_count IS 'Number of duplicate (non-distinct) values observed.';
        COMMENT ON COLUMN catalog_element.uniqueness_pct IS 'Percentage of values that are unique.';
        COMMENT ON COLUMN catalog_element.empty_string_count IS 'Number of empty-string values observed.';
        COMMENT ON COLUMN catalog_element.placeholder_count IS 'Number of placeholder-like values observed (e.g. "N/A", "unknown").';
        COMMENT ON COLUMN catalog_element.min_value IS 'Smallest value observed, as text.';
        COMMENT ON COLUMN catalog_element.max_value IS 'Largest value observed, as text.';
        COMMENT ON COLUMN catalog_element.length_min IS 'Shortest text length observed.';
        COMMENT ON COLUMN catalog_element.length_max IS 'Longest text length observed.';
        COMMENT ON COLUMN catalog_element.length_avg IS 'Average text length observed.';
        COMMENT ON COLUMN catalog_element.inferred_pattern IS 'The value-shape pattern the profiler detected for this column (e.g. looks like an IBAN), independent of any governed semantic type.';
        COMMENT ON COLUMN catalog_element.pattern_confidence IS 'How confident the profiler is in the inferred_pattern, 0 to 1.';
        COMMENT ON COLUMN catalog_element.invalid_format_count IS 'Number of values that do not match the expected format for this column''s pattern/type.';
        COMMENT ON COLUMN catalog_element.code_values IS 'The distinct code values observed in this column, as JSON, when it looks like a coded/enumerated field.';
        COMMENT ON COLUMN catalog_element.value_distribution IS 'Frequency breakdown of the values observed, as JSON.';
        COMMENT ON COLUMN catalog_element.numeric_avg IS 'Average value, for numeric columns.';
        COMMENT ON COLUMN catalog_element.numeric_median IS 'Median value, for numeric columns.';
        COMMENT ON COLUMN catalog_element.numeric_stddev IS 'Standard deviation, for numeric columns.';
        COMMENT ON COLUMN catalog_element.numeric_outlier_count IS 'Number of statistical outlier values detected, for numeric columns.';
        COMMENT ON COLUMN catalog_element.outlier_detection IS 'Which method was used to detect numeric outliers.';
        COMMENT ON COLUMN catalog_element.decimal_scale_distribution IS 'Breakdown of how many decimal places values actually use, as JSON, for numeric columns.';
        COMMENT ON COLUMN catalog_element.future_date_count IS 'Number of date values found to be in the future, for date columns.';
        COMMENT ON COLUMN catalog_element.suspicious_date_count IS 'Number of date values that look implausible (e.g. far past/future), for date columns.';
        COMMENT ON COLUMN catalog_element.type_mismatch_count IS 'Number of values that do not match this column''s declared/expected data type.';
        COMMENT ON COLUMN catalog_element.validator_pass_rates IS 'Pass-rate results, as JSON, from running known format validators (e.g. IBAN, BIC checks) against this column''s values — consumed directly by semantic-type deduction and quality scoring.';
        COMMENT ON COLUMN catalog_element.constant_run_warning IS 'Flag/details, as JSON, if this column looks suspiciously constant over a run of rows (placeholder for a not-yet-fully-implemented check).';
        COMMENT ON COLUMN catalog_element.stats_error IS 'Error message if statistics could not be computed for this column.';
        COMMENT ON COLUMN catalog_element.sample_values IS 'A small sample of real values from this column, as JSON, shown in the UI.';
        COMMENT ON COLUMN catalog_element.top_values IS 'The most frequently occurring values in this column, as JSON, shown in the UI.';

        -- ── catalog_refresh_event ─────────────────────────────────────────────────
        COMMENT ON TABLE catalog_refresh_event IS
          'A log entry for every time a dataset''s profile was refreshed, whether or not anything actually changed.';
        COMMENT ON COLUMN catalog_refresh_event.id IS 'Internal identifier for this refresh event.';
        COMMENT ON COLUMN catalog_refresh_event.dataset_id IS 'Which dataset was refreshed.';
        COMMENT ON COLUMN catalog_refresh_event.refreshed_at IS 'When the refresh happened.';
        COMMENT ON COLUMN catalog_refresh_event.triggered_by IS 'What triggered this refresh (e.g. a single-table refresh, or a bulk "rebuild all").';
        COMMENT ON COLUMN catalog_refresh_event.changed IS 'Whether this refresh actually found a change worth recording a new snapshot for.';
        """
    )

    op.execute(
        """
        -- ── catalog_dataset_snapshot ──────────────────────────────────────────────
        COMMENT ON TABLE catalog_dataset_snapshot IS
          'Historical copy of a catalog_dataset row, one per profile refresh that actually changed something. Lets a dataset''s stats be looked back on over time; pruned to a bounded retention, always keeping the first.';
        COMMENT ON COLUMN catalog_dataset_snapshot.id IS 'Internal identifier for this snapshot.';
        COMMENT ON COLUMN catalog_dataset_snapshot.dataset_id IS 'Which dataset this snapshot is a historical copy of.';
        COMMENT ON COLUMN catalog_dataset_snapshot.captured_at IS 'When this snapshot was taken.';
        COMMENT ON COLUMN catalog_dataset_snapshot.fingerprint IS 'Hash of this snapshot''s values, used to detect whether a refresh actually changed anything.';
        COMMENT ON COLUMN catalog_dataset_snapshot.schema_name IS 'Schema the dataset lived in at the time of this snapshot.';
        COMMENT ON COLUMN catalog_dataset_snapshot.table_name IS 'Table/dataset name at the time of this snapshot.';
        COMMENT ON COLUMN catalog_dataset_snapshot.description IS 'Description as it was at the time of this snapshot.';
        COMMENT ON COLUMN catalog_dataset_snapshot.row_count IS 'Row count as it was at the time of this snapshot.';
        COMMENT ON COLUMN catalog_dataset_snapshot.row_count_error IS 'Row-count error, if any, at the time of this snapshot.';
        COMMENT ON COLUMN catalog_dataset_snapshot.primary_key IS 'Declared primary key, as JSON, at the time of this snapshot.';
        COMMENT ON COLUMN catalog_dataset_snapshot.inferred_primary_key IS 'Inferred primary key, as JSON, at the time of this snapshot.';
        COMMENT ON COLUMN catalog_dataset_snapshot.foreign_keys IS 'Declared foreign keys, as JSON, at the time of this snapshot.';
        COMMENT ON COLUMN catalog_dataset_snapshot.relations IS 'Detected relations, as JSON, at the time of this snapshot.';
        COMMENT ON COLUMN catalog_dataset_snapshot.duplicate_count IS 'Duplicate row count at the time of this snapshot.';
        COMMENT ON COLUMN catalog_dataset_snapshot.duplicate_pct IS 'Duplicate row percentage at the time of this snapshot.';
        COMMENT ON COLUMN catalog_dataset_snapshot.orphan_fk_count IS 'Orphan foreign-key count at the time of this snapshot.';
        COMMENT ON COLUMN catalog_dataset_snapshot.completeness_summary IS 'Completeness score at the time of this snapshot.';
        COMMENT ON COLUMN catalog_dataset_snapshot.pct_columns_described IS 'Percentage of described columns at the time of this snapshot.';
        COMMENT ON COLUMN catalog_dataset_snapshot.profiling_status IS 'Profiling status at the time of this snapshot.';
        COMMENT ON COLUMN catalog_dataset_snapshot.content_hash IS 'Content hash at the time of this snapshot.';
        COMMENT ON COLUMN catalog_dataset_snapshot.source_modified_at IS 'Source-modified timestamp at the time of this snapshot.';
        COMMENT ON COLUMN catalog_dataset_snapshot.size_bytes IS 'Data size in bytes at the time of this snapshot.';
        COMMENT ON COLUMN catalog_dataset_snapshot.file_count IS 'File count at the time of this snapshot.';
        COMMENT ON COLUMN catalog_dataset_snapshot.format_hint IS 'File-format details, as JSON, at the time of this snapshot.';

        -- ── catalog_element_snapshot ──────────────────────────────────────────────
        COMMENT ON TABLE catalog_element_snapshot IS
          'Historical copy of a catalog_element row, one per profile refresh that actually changed something. parent_element_id is a frozen plain value here (not a live foreign key), since a historical snapshot must not depend on a possibly-since-changed parent row''s identity.';
        COMMENT ON COLUMN catalog_element_snapshot.id IS 'Internal identifier for this snapshot.';
        COMMENT ON COLUMN catalog_element_snapshot.element_id IS 'Which column this snapshot is a historical copy of.';
        COMMENT ON COLUMN catalog_element_snapshot.captured_at IS 'When this snapshot was taken.';
        COMMENT ON COLUMN catalog_element_snapshot.fingerprint IS 'Hash of this snapshot''s values, used to detect whether a refresh actually changed anything.';
        COMMENT ON COLUMN catalog_element_snapshot.parent_element_id IS 'The parent field''s id as it was at the time of this snapshot (a frozen value, not a live reference).';
        COMMENT ON COLUMN catalog_element_snapshot.qualified_column_name IS 'Fully-qualified column name at the time of this snapshot.';
        COMMENT ON COLUMN catalog_element_snapshot.column_name IS 'Column name at the time of this snapshot.';
        COMMENT ON COLUMN catalog_element_snapshot.column_kind IS 'Scalar/nested kind at the time of this snapshot.';
        COMMENT ON COLUMN catalog_element_snapshot.nesting_level IS 'Nesting depth at the time of this snapshot.';
        COMMENT ON COLUMN catalog_element_snapshot.ordinal IS 'Column position at the time of this snapshot.';
        COMMENT ON COLUMN catalog_element_snapshot.data_type IS 'Physical data type at the time of this snapshot.';
        COMMENT ON COLUMN catalog_element_snapshot.description IS 'Description at the time of this snapshot.';
        COMMENT ON COLUMN catalog_element_snapshot.type_distribution IS 'Type-distribution breakdown, as JSON, at the time of this snapshot.';
        COMMENT ON COLUMN catalog_element_snapshot.array_length_min IS 'Minimum array length at the time of this snapshot.';
        COMMENT ON COLUMN catalog_element_snapshot.array_length_max IS 'Maximum array length at the time of this snapshot.';
        COMMENT ON COLUMN catalog_element_snapshot.array_length_avg IS 'Average array length at the time of this snapshot.';
        COMMENT ON COLUMN catalog_element_snapshot.row_count IS 'Row count considered at the time of this snapshot.';
        COMMENT ON COLUMN catalog_element_snapshot.null_count IS 'Null count at the time of this snapshot.';
        COMMENT ON COLUMN catalog_element_snapshot.null_pct IS 'Null percentage at the time of this snapshot.';
        COMMENT ON COLUMN catalog_element_snapshot.distinct_count IS 'Distinct value count at the time of this snapshot.';
        COMMENT ON COLUMN catalog_element_snapshot.duplicate_count IS 'Duplicate value count at the time of this snapshot.';
        COMMENT ON COLUMN catalog_element_snapshot.uniqueness_pct IS 'Uniqueness percentage at the time of this snapshot.';
        COMMENT ON COLUMN catalog_element_snapshot.empty_string_count IS 'Empty-string count at the time of this snapshot.';
        COMMENT ON COLUMN catalog_element_snapshot.placeholder_count IS 'Placeholder-value count at the time of this snapshot.';
        COMMENT ON COLUMN catalog_element_snapshot.min_value IS 'Minimum value at the time of this snapshot.';
        COMMENT ON COLUMN catalog_element_snapshot.max_value IS 'Maximum value at the time of this snapshot.';
        COMMENT ON COLUMN catalog_element_snapshot.length_min IS 'Minimum text length at the time of this snapshot.';
        COMMENT ON COLUMN catalog_element_snapshot.length_max IS 'Maximum text length at the time of this snapshot.';
        COMMENT ON COLUMN catalog_element_snapshot.length_avg IS 'Average text length at the time of this snapshot.';
        COMMENT ON COLUMN catalog_element_snapshot.inferred_pattern IS 'Inferred value pattern at the time of this snapshot.';
        COMMENT ON COLUMN catalog_element_snapshot.pattern_confidence IS 'Pattern-confidence score at the time of this snapshot.';
        COMMENT ON COLUMN catalog_element_snapshot.invalid_format_count IS 'Invalid-format count at the time of this snapshot.';
        COMMENT ON COLUMN catalog_element_snapshot.code_values IS 'Distinct code values, as JSON, at the time of this snapshot.';
        COMMENT ON COLUMN catalog_element_snapshot.value_distribution IS 'Value-frequency breakdown, as JSON, at the time of this snapshot.';
        COMMENT ON COLUMN catalog_element_snapshot.numeric_avg IS 'Average numeric value at the time of this snapshot.';
        COMMENT ON COLUMN catalog_element_snapshot.numeric_median IS 'Median numeric value at the time of this snapshot.';
        COMMENT ON COLUMN catalog_element_snapshot.numeric_stddev IS 'Numeric standard deviation at the time of this snapshot.';
        COMMENT ON COLUMN catalog_element_snapshot.numeric_outlier_count IS 'Numeric outlier count at the time of this snapshot.';
        COMMENT ON COLUMN catalog_element_snapshot.outlier_detection IS 'Outlier detection method used at the time of this snapshot.';
        COMMENT ON COLUMN catalog_element_snapshot.decimal_scale_distribution IS 'Decimal-scale breakdown, as JSON, at the time of this snapshot.';
        COMMENT ON COLUMN catalog_element_snapshot.future_date_count IS 'Future-date count at the time of this snapshot.';
        COMMENT ON COLUMN catalog_element_snapshot.suspicious_date_count IS 'Suspicious-date count at the time of this snapshot.';
        COMMENT ON COLUMN catalog_element_snapshot.type_mismatch_count IS 'Type-mismatch count at the time of this snapshot.';
        COMMENT ON COLUMN catalog_element_snapshot.validator_pass_rates IS 'Validator pass-rate results, as JSON, at the time of this snapshot.';
        COMMENT ON COLUMN catalog_element_snapshot.constant_run_warning IS 'Constant-run warning, as JSON, at the time of this snapshot.';
        COMMENT ON COLUMN catalog_element_snapshot.stats_error IS 'Statistics error, if any, at the time of this snapshot.';
        COMMENT ON COLUMN catalog_element_snapshot.sample_values IS 'Sample values, as JSON, at the time of this snapshot.';
        COMMENT ON COLUMN catalog_element_snapshot.top_values IS 'Top values, as JSON, at the time of this snapshot.';
        """
    )


def downgrade() -> None:
    for table in (
        "glossary", "term", "term_version", "term_relation", "linkage",
        "lifecycle_transition", "review_subject", "linkage_triage", "glossary_group_meta",
        "review_task", "reference_code", "audit_events",
        "catalog_source", "catalog_dataset", "catalog_element", "catalog_refresh_event",
        "catalog_dataset_snapshot", "catalog_element_snapshot",
    ):
        op.execute(f"COMMENT ON TABLE {table} IS NULL;")
    op.execute(
        """
        DO $$
        DECLARE
            r RECORD;
        BEGIN
            FOR r IN
                SELECT c.table_name, c.column_name
                FROM information_schema.columns c
                WHERE c.table_schema = 'public'
                  AND c.table_name IN (
                    'glossary','term','term_version','term_relation','linkage',
                    'lifecycle_transition','review_subject','linkage_triage','glossary_group_meta',
                    'review_task','reference_code','audit_events',
                    'catalog_source','catalog_dataset','catalog_element','catalog_refresh_event',
                    'catalog_dataset_snapshot','catalog_element_snapshot'
                  )
            LOOP
                EXECUTE format('COMMENT ON COLUMN %I.%I IS NULL;', r.table_name, r.column_name);
            END LOOP;
        END $$;
        """
    )
