"""Event type constants for the audit log."""

# ── Business events ─────────────────────────────────────────────────────────
MAPPING_CANDIDATE_ACCEPTED  = "mapping.candidate.accepted"
MAPPING_CANDIDATE_REJECTED  = "mapping.candidate.rejected"
MAPPING_RUN_STARTED         = "mapping.run.started"
MAPPING_SAVED               = "mapping.saved"

GLOSSARY_TERM_CREATED       = "glossary.term.created"
GLOSSARY_TERM_UPDATED       = "glossary.term.updated"
GLOSSARY_TERM_DELETED       = "glossary.term.deleted"

CATALOG_DESCRIPTION_UPDATED  = "catalog.description.updated"

ELEMENT_STATE_CHANGED        = "element.state_changed"
ELEMENT_DESCRIPTION_UPDATED  = "element.description_updated"
ELEMENT_DEFINITION_SUBMITTED = "element.definition.submitted"
ELEMENT_DEFINITION_APPROVED  = "element.definition.approved"
ELEMENT_DEFINITION_REJECTED  = "element.definition.rejected"

# ── Interpretation-set lifecycle events (Phase 5b.1 — canonical vocabulary) ───
# Set-level actions on the whole Data Element Interpretation Set. Emitted by the
# canonical endpoints; the legacy element.definition.* events above stay for the
# pre-5b flows still wired to them.
ELEMENT_SAVED       = "element.saved"        # Empty/withdrawn → Draft (holistic save)
ELEMENT_WITHDRAWN   = "element.withdrawn"    # analyst pulls a submission back → Draft
ELEMENT_RETURNED    = "element.returned"     # steward returns for rework → Returned
ELEMENT_REJECTED    = "element.rejected"     # steward outright rejects → Rejected
ELEMENT_REVOKED     = "element.revoked"      # analyst pulls a prior approval back → Draft

ASSESSMENT_SCOPE_CHANGED     = "assessment_scope.changed"

# ── AI events ────────────────────────────────────────────────────────────────
AI_CALL                  = "ai.call"
INSIGHTS_GENERATED       = "insights.generated"
SEMANTIC_TYPES_RESOLVED  = "semantic_types.resolved"
SEMANTIC_TYPE_ACCEPTED   = "semantic_type.accepted"

