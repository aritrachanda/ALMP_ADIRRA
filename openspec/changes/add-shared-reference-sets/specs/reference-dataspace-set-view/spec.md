## ADDED Requirements

### Requirement: Browse-by-set toggle

The Reference Dataspace SHALL offer a "Browse by set" view that a user can toggle alongside the
default source-tree view, without leaving the page.

#### Scenario: User switches to set view
- **WHEN** a user activates the "Browse by set" toggle
- **THEN** the register regroups to show reference sets instead of the source/schema/table tree

#### Scenario: User switches back to source view
- **WHEN** a user deactivates the "Browse by set" toggle
- **THEN** the register returns to the default source-tree grouping

### Requirement: Set view shows entries once and consuming fields

In set view each reference set SHALL be shown once with its entries, together with the count and
identity of the source fields bound to it ("used by N fields"), so that duplicate or consolidatable
lists are visible.

#### Scenario: Set shows its consuming fields
- **WHEN** a reference set is bound by two fields and shown in set view
- **THEN** the set is displayed once with its entries and reports that it is used by 2 fields

#### Scenario: Set with no bound fields
- **WHEN** a reference set has no fields bound to it
- **THEN** it is shown with a used-by count of zero

### Requirement: Set view is read-only

The "Browse by set" view SHALL be read-only and MUST NOT offer any create, edit, bind, or unbind
controls.

#### Scenario: No edit controls in set view
- **WHEN** a user views the "Browse by set" view
- **THEN** no controls to create, edit, or bind reference sets are present
