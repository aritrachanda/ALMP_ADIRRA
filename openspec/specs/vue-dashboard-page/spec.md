# Spec — vue-dashboard-page (ADDED)

## ADDED Requirements

### Requirement: Coverage metrics summary

The Dashboard page SHALL display high-level coverage statistics fetched from `GET /api/dashboard/summary`. Metrics SHALL include: number of source datasets and tables, number of target datasets and tables, number of mappings with results, mapped column count, glossary term count, and uncovered concept count.

#### Scenario: Metrics load on page mount

- **WHEN** the user navigates to `/tools/dashboard`
- **THEN** the page SHALL fetch `/api/dashboard/summary`
- **AND** display metric cards for sources, targets, mappings, and glossary coverage

#### Scenario: Loading state is visible

- **WHEN** the summary data is being fetched
- **THEN** the page SHALL display a loading skeleton or spinner

#### Scenario: Error state is handled

- **WHEN** the API call fails
- **THEN** the page SHALL display an error message without crashing

### Requirement: Coverage bar chart

The Dashboard SHALL render a bar chart comparing mapped vs. unmapped columns across the available mappings, using Chart.js (already installed).

#### Scenario: Chart renders when mapping data is available

- **WHEN** the summary contains at least one mapping with results
- **THEN** a bar chart SHALL render showing mapped/unmapped column counts

#### Scenario: Chart is hidden when no mapping data exists

- **WHEN** the summary contains zero mappings with results
- **THEN** the chart SHALL be hidden and a placeholder message displayed

### Requirement: Backend summary endpoint

A `GET /api/dashboard/summary` endpoint SHALL be implemented in `api/routes/dashboard.py`. It SHALL read source catalogs, target catalogs, mapping files, and the glossary YAML using paths from `project.yaml`. It SHALL return a JSON object with keys: `sources`, `targets`, `mappings`, `glossary`.

#### Scenario: Endpoint returns structured summary

- **WHEN** `GET /api/dashboard/summary` is called
- **THEN** the response SHALL be HTTP 200 with JSON matching the summary schema
- **AND** counts SHALL reflect the actual files present on disk
