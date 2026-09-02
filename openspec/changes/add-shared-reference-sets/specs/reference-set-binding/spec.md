## ADDED Requirements

### Requirement: Bind a field to a reference set

The system SHALL allow a source field, identified by its composite key
`source|schema|table|column`, to be bound to exactly one reference set. The binding MUST persist
alongside the existing element-state overlays and MUST survive catalog re-profiling. The system
SHALL allow the binding to be cleared (unbound), restoring the field's own inline meanings.

#### Scenario: Binding persists
- **WHEN** an analyst binds a field to a reference set
- **THEN** the binding is stored for that field's composite key and is still present after the
  source catalog is re-profiled

#### Scenario: Unbinding clears the binding
- **WHEN** an analyst removes a field's binding
- **THEN** the field is no longer associated with any reference set and its previously stored inline
  meanings are used again

### Requirement: Aggregate endpoint resolves bound fields

When a field is bound to a reference set, `GET /reference-data` SHALL populate `bound_set_id` with
the set id and `set_kind` with the set's `kind`, and SHALL resolve each `codes[].meaning` from the
bound set's entries. Observed-data reconciliation (`share_pct`, `in_source`, `in_list`, `rogue`,
`unused`) MUST continue to be computed from the source data. Fields that are not bound MUST behave
exactly as before this change.

#### Scenario: Bound field resolves meanings and kind from the set
- **WHEN** a bound field is returned by `GET /reference-data`
- **THEN** its `bound_set_id` and `set_kind` reflect the bound set and its code meanings come from
  the set's entries

#### Scenario: Reconciliation still reflects observed data
- **WHEN** a bound field has an observed code that is absent from the bound set
- **THEN** that code is reported as `rogue`, and a set entry not observed in the source is reported
  as `unused`

#### Scenario: Unbound field is unchanged
- **WHEN** a field has no binding
- **THEN** `GET /reference-data` returns `set_kind` of `local`, a null `bound_set_id`, and meanings
  from the field's own inline data, exactly as before

### Requirement: Semantic-type-driven binding suggestion

The Asset Workspace SHALL suggest a reference set for a field based on the field's `semantic_type`,
mapping `currency_code` to the ISO 4217 set and `country_code` to the ISO 3166 set. The suggestion
MUST be advisory only; the analyst confirms or chooses a different set.

#### Scenario: Suggestion offered for a mapped semantic type
- **WHEN** an analyst opens the bind action on a field whose `semantic_type` is `currency_code`
- **THEN** the ISO 4217 currency set is presented as the suggested binding

#### Scenario: No suggestion for an unmapped semantic type
- **WHEN** an analyst opens the bind action on a field whose `semantic_type` has no mapping
- **THEN** no set is pre-suggested and the analyst may pick any set manually

### Requirement: Binding is an Asset Workspace edit action

The bind and unbind actions SHALL be available only on a field's Reference Data tab in the Asset
Workspace, and MUST NOT appear in the read-only Reference Dataspace.

#### Scenario: Bind action appears in the Asset Workspace
- **WHEN** an analyst views a coded field's Reference Data tab in the Asset Workspace
- **THEN** a "Bind to reference set" action is available

#### Scenario: No binding controls in the Dataspace
- **WHEN** a user views the read-only Reference Dataspace
- **THEN** no bind or unbind controls are shown
