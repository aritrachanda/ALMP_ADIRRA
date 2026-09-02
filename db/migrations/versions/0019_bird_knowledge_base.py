"""BIRD Knowledge Base — full SMCube export loaded into its own `bird` schema.

Replaces the DuckDB knowledge base (`knowledge_base/bird/data/bird_kb.duckdb`) as the home of
the published BIRD dictionary. The KB *is* the target data model for mapping, so it belongs in
the same database as everything else rather than in a side file only one page could read.

Source: `knowledge_base/bird/source/BIRD_all-frameworks_2026-08-25.xlsx` — the full ECB export
covering all data models and all nine frameworks (BIRD, AnaCredit, FINREP, Asset Encumbrance,
Securities Holdings Statistics and the dictionary's own meta-model), 60 sheets.

FAITHFUL PORT. Table and column names are exactly as the ECB publishes them. Nothing is
renamed, reshaped, filtered or invented.

Column types are inferred from the data itself, having scanned every row rather than a sample.
Two deliberate exceptions: a column with no data anywhere defaults to TEXT rather than guessing,
and any column named valid_from/valid_to is DATE by definition -- four tables are empty in this
export, so there is nothing to infer from, yet their validity columns are still dates.

NO PRIMARY KEYS AND NO FOREIGN KEYS, deliberately. The export declares neither, and both would
reject published rows: verification against every row found 9 genuine referential gaps (3,261
of them in member_mapping_item alone) and three tables whose apparent key repeats because the
rows are validity-versioned. The governing rule is that nothing BIRD ships may be dropped
unless BIRD drops it. Indexes are still created for query performance — they reject nothing.

VALIDITY IS FIRST CLASS. Roughly a fifth of `cube` rows and a fifth of `subdomain_enumeration`
rows are no longer current. Every validity-bearing table therefore gets a companion
`<name>_current` view with the date filter built in, so the safe reading is the default one and
history has to be asked for explicitly. Point-in-time questions (what was legal at a reporting
reference date) must filter on that date rather than use these views.
"""
from __future__ import annotations

from alembic import op

revision = "0019_bird_knowledge_base"
down_revision = "0018_semantic_type_retire_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS bird;")
    op.execute("""
        COMMENT ON SCHEMA bird IS
          'The published BIRD dictionary from the ECB, loaded exactly as exported. This is the target data model that source data is mapped to.';
    """)

    # ---- bird.maintenance_agency  (5 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.maintenance_agency (
            maintenance_agency_id   TEXT,
            code                    TEXT,
            name                    TEXT,
            description             TEXT,
            deleted                 BOOLEAN
        );
    """)

    # ---- bird.framework  (9 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.framework (
            maintenance_agency_id   TEXT,
            framework_id            TEXT,
            name                    TEXT,
            code                    TEXT,
            description             TEXT,
            framework_type          TEXT,
            reporting_population    TEXT,
            other_links             TEXT,
            "order"                 NUMERIC,
            framework_status        TEXT
        );
    """)

    # ---- bird.domain  (307 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.domain (
            maintenance_agency_id   TEXT,
            domain_id               TEXT,
            name                    TEXT,
            is_enumerated           BOOLEAN,
            description             TEXT,
            data_type               TEXT,
            code                    TEXT,
            facet_id                TEXT,
            is_reference            BOOLEAN
        );
    """)

    # ---- bird.facet_collection  (117 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.facet_collection (
            maintenance_agency_id   TEXT,
            facet_id                TEXT,
            code                    TEXT,
            name                    TEXT,
            facet_value_type        TEXT
        );
    """)

    # ---- bird.facet_enumeration  (131 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.facet_enumeration (
            facet_id            TEXT,
            facet_type          TEXT,
            observation_value   TEXT
        );
    """)

    # ---- bird.member  (22137 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.member (
            maintenance_agency_id   TEXT,
            member_id               TEXT,
            code                    TEXT,
            name                    TEXT,
            domain_id               TEXT,
            description             TEXT
        );
    """)

    # ---- bird.member_hierarchy  (1481 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.member_hierarchy (
            maintenance_agency_id   TEXT,
            member_hierarchy_id     TEXT,
            code                    TEXT,
            domain_id               TEXT,
            name                    TEXT,
            description             TEXT,
            is_main_hierarchy       BOOLEAN
        );
    """)

    # ---- bird.member_hierarchy_node  (44773 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.member_hierarchy_node (
            member_hierarchy_id   TEXT,
            member_id             TEXT,
            level                 NUMERIC,
            parent_member_id      TEXT,
            comparator            TEXT,
            operator              TEXT,
            valid_from            DATE,
            valid_to              DATE
        );
    """)

    # ---- bird.subdomain  (2522 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.subdomain (
            maintenance_agency_id   TEXT,
            subdomain_id            TEXT,
            name                    TEXT,
            domain_id               TEXT,
            is_listed               BOOLEAN,
            code                    TEXT,
            facet_id                TEXT,
            description             TEXT,
            is_natural              BOOLEAN
        );
    """)

    # ---- bird.subdomain_enumeration  (43501 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.subdomain_enumeration (
            member_id      TEXT,
            subdomain_id   TEXT,
            valid_from     DATE,
            valid_to       DATE,
            "order"        NUMERIC
        );
    """)

    # ---- bird.variable  (2144 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.variable (
            maintenance_agency_id   TEXT,
            variable_id             TEXT,
            code                    TEXT,
            name                    TEXT,
            domain_id               TEXT,
            description             TEXT,
            primary_concept         TEXT,
            is_decomposed           BOOLEAN
        );
    """)

    # ---- bird.variable_set  (2557 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.variable_set (
            maintenance_agency_id   TEXT,
            variable_set_id         TEXT,
            name                    TEXT,
            code                    TEXT,
            description             TEXT
        );
    """)

    # ---- bird.variable_set_enumeration  (3616 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.variable_set_enumeration (
            variable_set_id   TEXT,
            variable_id       TEXT,
            valid_from        DATE,
            valid_to          DATE,
            subdomain_id      TEXT,
            is_flow           BOOLEAN,
            "order"           NUMERIC
        );
    """)

    # ---- bird.combination  (34709 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.combination (
            combination_id          TEXT,
            code                    TEXT,
            name                    TEXT,
            maintenance_agency_id   TEXT,
            version                 TEXT,
            valid_from              DATE,
            valid_to                DATE
        );
    """)

    # ---- bird.combination_item  (641198 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.combination_item (
            combination_id    TEXT,
            variable_id       TEXT,
            subdomain_id      TEXT,
            variable_set_id   TEXT,
            member_id         TEXT
        );
    """)

    # ---- bird.cube  (2146 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.cube (
            maintenance_agency_id   TEXT,
            cube_id                 TEXT,
            name                    TEXT,
            code                    TEXT,
            framework_id            TEXT,
            cube_structure_id       TEXT,
            cube_type               TEXT,
            is_allowed              TEXT,
            valid_from              DATE,
            valid_to                DATE,
            version                 TEXT,
            description             TEXT,
            published               BOOLEAN,
            dataset_url             TEXT,
            filters                 TEXT,
            di_export               TEXT
        );
    """)

    # ---- bird.cube_group  (81 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.cube_group (
            maintenance_agency_id   TEXT,
            cube_group_id           TEXT,
            name                    TEXT,
            code                    TEXT,
            description             TEXT
        );
    """)

    # ---- bird.cube_group_enumeration  (1454 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.cube_group_enumeration (
            "order"         NUMERIC,
            cube_group_id   TEXT,
            cube_id         TEXT,
            valid_from      DATE,
            valid_to        DATE
        );
    """)

    # ---- bird.cube_hierarchy  (6 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.cube_hierarchy (
            cube_hierarchy_id       TEXT,
            maintenance_agency_id   TEXT,
            name                    TEXT,
            code                    TEXT,
            description             TEXT,
            cube_hierarchy_type     TEXT,
            framework_id            TEXT
        );
    """)

    # ---- bird.cube_hierarchy_node  (81 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.cube_hierarchy_node (
            cube_hierarchy_id   TEXT,
            node_code           TEXT,
            node_name           TEXT,
            level               NUMERIC,
            parent_node_code    TEXT,
            cube_group_id       TEXT,
            valid_from          DATE,
            valid_to            DATE,
            "order"             NUMERIC,
            colour              TEXT
        );
    """)

    # ---- bird.cube_relationship  (6592 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.cube_relationship (
            maintenance_agency_id        TEXT,
            cube_relationship_id         TEXT,
            code                         TEXT,
            name                         TEXT,
            description                  TEXT,
            type_of_relationship         TEXT,
            valid_from                   DATE,
            valid_to                     DATE,
            version                      TEXT,
            primary_cube_id              TEXT,
            primary_cube_variable_code   TEXT,
            foreign_cube_id              TEXT,
            foreign_cube_variable_code   TEXT,
            primary_cube_cardinality     TEXT,
            foreign_cube_cardinality     TEXT,
            primary_cube_mandatoriness   BOOLEAN,
            foreign_cube_mandatoriness   BOOLEAN
        );
    """)

    # ---- bird.cube_link  (2202 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.cube_link (
            maintenance_agency_id            TEXT,
            cube_link_id                     TEXT,
            code                             TEXT,
            name                             TEXT,
            description                      TEXT,
            valid_from                       DATE,
            valid_to                         DATE,
            version                          TEXT,
            order_relevance                  NUMERIC,
            primary_cube_id                  TEXT,
            foreign_cube_id                  TEXT,
            cube_link_type                   TEXT,
            logical_transformation_rule_id   TEXT
        );
    """)

    # ---- bird.cube_structure_item_link  (11851 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.cube_structure_item_link (
            cube_structure_item_link_id   TEXT,
            cube_link_id                  TEXT,
            foreign_cube_variable_code    TEXT,
            primary_cube_variable_code    TEXT,
            comparator                    TEXT,
            aggregation_function          TEXT
        );
    """)

    # ---- bird.member_link  (1000000 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.member_link (
            cube_structure_item_link_id   TEXT,
            foreign_member_id             TEXT,
            primary_member_id             TEXT,
            valid_from                    DATE,
            valid_to                      DATE,
            is_linked                     BOOLEAN
        );
    """)

    # ---- bird.cube_structure  (2146 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.cube_structure (
            maintenance_agency_id   TEXT,
            cube_structure_id       TEXT,
            name                    TEXT,
            code                    TEXT,
            description             TEXT,
            valid_from              DATE,
            valid_to                DATE,
            version                 TEXT
        );
    """)

    # ---- bird.cube_structure_item  (23355 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.cube_structure_item (
            cube_structure_item_id          TEXT,
            cube_structure_id               TEXT,
            cube_variable_code              TEXT,
            variable_id                     TEXT,
            role                            TEXT,
            "order"                         NUMERIC,
            subdomain_id                    TEXT,
            variable_set_id                 TEXT,
            member_id                       TEXT,
            dimension_type                  TEXT,
            attribute_associated_variable   TEXT,
            is_flow                         BOOLEAN,
            is_mandatory                    BOOLEAN,
            description                     TEXT,
            is_implemented                  BOOLEAN
        );
    """)

    # ---- bird.cube_to_combination  (68884 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.cube_to_combination (
            cube_id          TEXT,
            combination_id   TEXT
        );
    """)

    # ---- bird.framework_hierarchy  (0 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.framework_hierarchy (
            framework_id          TEXT,
            member_hierarchy_id   TEXT
        );
    """)

    # ---- bird.framework_subdomain  (0 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.framework_subdomain (
            framework_id   TEXT,
            subdomain_id   TEXT
        );
    """)

    # ---- bird.framework_variable_set  (1 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.framework_variable_set (
            framework_id      TEXT,
            variable_set_id   TEXT
        );
    """)

    # ---- bird.cube_mapping  (175 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.cube_mapping (
            maintenance_agency_id   TEXT,
            cube_mapping_id         TEXT,
            name                    TEXT,
            code                    TEXT,
            source_cube_id          TEXT,
            destination_cube_id     TEXT,
            description             TEXT
        );
    """)

    # ---- bird.combination_mapping  (0 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.combination_mapping (
            source_combination_id        TEXT,
            destination_combination_id   TEXT
        );
    """)

    # ---- bird.mapping_definition  (438 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.mapping_definition (
            maintenance_agency_id   TEXT,
            mapping_id              TEXT,
            name                    TEXT,
            mapping_type            TEXT,
            code                    TEXT,
            algorithm               TEXT,
            member_mapping_id       TEXT,
            variable_mapping_id     TEXT
        );
    """)

    # ---- bird.mapping_to_cube  (1582 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.mapping_to_cube (
            cube_mapping_id   TEXT,
            mapping_id        TEXT,
            valid_from        DATE,
            valid_to          DATE
        );
    """)

    # ---- bird.member_mapping  (220 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.member_mapping (
            maintenance_agency_id   TEXT,
            member_mapping_id       TEXT,
            name                    TEXT,
            code                    TEXT
        );
    """)

    # ---- bird.member_mapping_item  (39190 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.member_mapping_item (
            member_mapping_id    TEXT,
            member_mapping_row   NUMERIC,
            variable_id          TEXT,
            is_source            BOOLEAN,
            member_id            TEXT,
            valid_from           DATE,
            valid_to             DATE
        );
    """)

    # ---- bird.variable_mapping  (438 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.variable_mapping (
            variable_mapping_id     TEXT,
            maintenance_agency_id   TEXT,
            code                    TEXT,
            name                    TEXT
        );
    """)

    # ---- bird.variable_mapping_item  (1509 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.variable_mapping_item (
            variable_mapping_id   TEXT,
            variable_id           TEXT,
            is_source             BOOLEAN,
            valid_from            DATE,
            valid_to              DATE
        );
    """)

    # ---- bird.variable_set_mapping  (151 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.variable_set_mapping (
            source_mapping_id   TEXT,
            target_mapping_id   TEXT
        );
    """)

    # ---- bird.cube_structure_mapping  (0 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.cube_structure_mapping (
            mapping_id          TEXT,
            cube_mapping_id     TEXT,
            member_mapping_id   TEXT,
            algorithm           TEXT
        );
    """)

    # ---- bird.cube_structure_mapping_item  (0 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.cube_structure_mapping_item (
            mapping_id           TEXT,
            cube_variable_code   TEXT,
            is_source            TEXT,
            valid_from           DATE,
            valid_to             DATE
        );
    """)

    # ---- bird.axis  (1250 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.axis (
            axis_id        TEXT,
            code           TEXT,
            orientation    TEXT,
            "order"        NUMERIC,
            name           TEXT,
            description    TEXT,
            table_id       TEXT,
            is_open_axis   BOOLEAN
        );
    """)

    # ---- bird.axis_ordinate  (16612 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.axis_ordinate (
            axis_ordinate_id          TEXT,
            is_abstract_header        BOOLEAN,
            code                      TEXT,
            "order"                   NUMERIC,
            level                     NUMERIC,
            path                      TEXT,
            axis_id                   TEXT,
            parent_axis_ordinate_id   TEXT,
            name                      TEXT,
            description               TEXT
        );
    """)

    # ---- bird.cell_position  (163054 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.cell_position (
            cell_id            TEXT,
            axis_ordinate_id   TEXT
        );
    """)

    # ---- bird.ordinate_item  (81877 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.ordinate_item (
            axis_ordinate_id              TEXT,
            variable_id                   TEXT,
            member_id                     TEXT,
            member_hierarchy_id           TEXT,
            member_hierarchy_valid_from   DATE,
            starting_member_id            TEXT,
            is_starting_member_included   BOOLEAN
        );
    """)

    # ---- bird.table  (604 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird."table" (
            table_id                TEXT,
            name                    TEXT,
            code                    TEXT,
            description             TEXT,
            maintenance_agency_id   TEXT,
            version                 TEXT,
            valid_from              DATE,
            valid_to                DATE
        );
    """)

    # ---- bird.table_cell  (80422 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.table_cell (
            cell_id            TEXT,
            is_shaded          BOOLEAN,
            combination_id     TEXT,
            table_id           TEXT,
            system_data_code   TEXT
        );
    """)

    # ---- bird.cube_to_table  (604 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.cube_to_table (
            cube_id    TEXT,
            table_id   TEXT
        );
    """)

    # ---- bird.transformation  (0 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.transformation (
            transformation_id          TEXT,
            transformation_scheme_id   TEXT,
            maintenance_agency_id      TEXT,
            name                       TEXT,
            code                       TEXT,
            description                TEXT,
            expression                 TEXT,
            valid_from                 DATE,
            valid_to                   DATE,
            "order"                    TEXT
        );
    """)

    # ---- bird.transformation_node  (0 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.transformation_node (
            transformation_node_id   TEXT,
            transformation_id        TEXT,
            type_of_node             TEXT,
            expression               TEXT,
            parent_node_id           TEXT,
            level                    TEXT,
            "order"                  TEXT
        );
    """)

    # ---- bird.transformation_scheme  (0 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.transformation_scheme (
            transformation_scheme_id   TEXT,
            maintenance_agency_id      TEXT,
            name                       TEXT,
            code                       TEXT,
            description                TEXT,
            type_of_scheme             TEXT,
            expression                 TEXT,
            phase                      TEXT,
            valid_from                 DATE,
            valid_to                   DATE,
            version                    TEXT
        );
    """)

    # ---- bird.semantic_transformation_rule  (357 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.semantic_transformation_rule (
            semantic_transformation_rule_id   TEXT,
            transformation_url                TEXT,
            type_of_transformation            TEXT,
            maintenance_agency_id             TEXT,
            name                              TEXT,
            code                              TEXT,
            description                       TEXT,
            algorithm                         TEXT,
            valid_from                        DATE,
            valid_to                          DATE
        );
    """)

    # ---- bird.transformation_to_variable  (125 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.transformation_to_variable (
            semantic_transformation_rule_id   TEXT,
            variable_id                       TEXT,
            is_source                         BOOLEAN
        );
    """)

    # ---- bird.transformation_to_cube  (109 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.transformation_to_cube (
            semantic_transformation_rule_id   TEXT,
            cube_id                           TEXT,
            is_source                         BOOLEAN
        );
    """)

    # ---- bird.logical_transformation_rule  (379 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.logical_transformation_rule (
            logical_transformation_rule_id    TEXT,
            semantic_transformation_rule_id   TEXT,
            algorithm                         TEXT,
            additional_filters                TEXT,
            source_layer                      TEXT,
            destination_layer                 TEXT,
            transformation_type               TEXT,
            valid_from                        DATE,
            valid_to                          DATE
        );
    """)

    # ---- bird.legal_reference  (366 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.legal_reference (
            object_type     TEXT,
            object_id       TEXT,
            legal_text_id   TEXT,
            article         TEXT,
            valid_from      DATE,
            valid_to        DATE
        );
    """)

    # ---- bird.legal_text  (38 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.legal_text (
            legal_text_id          TEXT,
            legal_code             TEXT,
            legal_description      TEXT,
            business_description   TEXT,
            hyperlink              TEXT
        );
    """)

    # ---- bird.classification  (0 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.classification (
            classification_id   TEXT,
            code                TEXT,
            name                TEXT,
            description         TEXT
        );
    """)

    # ---- bird.classification_assignment  (0 rows in the 2026-08-25 export) ----
    op.execute("""
        CREATE TABLE bird.classification_assignment (
            object_type         TEXT,
            object_id           TEXT,
            classification_id   TEXT,
            valid_from          DATE,
            valid_to            DATE
        );
    """)

    # ---- what every table and column means ----
    op.execute("""
        COMMENT ON TABLE bird.maintenance_agency IS 'The organisation that publishes and maintains part of the dictionary. For BIRD this is the ECB.';
        COMMENT ON COLUMN bird.maintenance_agency.maintenance_agency_id IS 'Which organisation publishes and maintains this entry.';
        COMMENT ON COLUMN bird.maintenance_agency.code IS 'The publisher''s short code for this entry.';
        COMMENT ON COLUMN bird.maintenance_agency.name IS 'The publisher''s readable name for this entry.';
        COMMENT ON COLUMN bird.maintenance_agency.description IS 'The publisher''s explanation of what this entry means.';
        COMMENT ON COLUMN bird.maintenance_agency.deleted IS 'The publisher''s deleted value for this entry.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.framework IS 'A regulatory reporting collection the dictionary supports, such as AnaCredit, FINREP or Asset Encumbrance.';
        COMMENT ON COLUMN bird.framework.maintenance_agency_id IS 'Which organisation publishes and maintains this entry.';
        COMMENT ON COLUMN bird.framework.framework_id IS 'Which regulatory framework this belongs to.';
        COMMENT ON COLUMN bird.framework.name IS 'The publisher''s readable name for this entry.';
        COMMENT ON COLUMN bird.framework.code IS 'The publisher''s short code for this entry.';
        COMMENT ON COLUMN bird.framework.description IS 'The publisher''s explanation of what this entry means.';
        COMMENT ON COLUMN bird.framework.framework_type IS 'The publisher''s framework type value for this entry.';
        COMMENT ON COLUMN bird.framework.reporting_population IS 'The publisher''s reporting population value for this entry.';
        COMMENT ON COLUMN bird.framework.other_links IS 'The publisher''s other links value for this entry.';
        COMMENT ON COLUMN bird.framework."order" IS 'The publisher''s display ordering for this entry.';
        COMMENT ON COLUMN bird.framework.framework_status IS 'The publisher''s framework status value for this entry.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.domain IS 'A named set of values an attribute is allowed to take, such as Purpose or Currency. Some are fixed code lists, others open value ranges.';
        COMMENT ON COLUMN bird.domain.maintenance_agency_id IS 'Which organisation publishes and maintains this entry.';
        COMMENT ON COLUMN bird.domain.domain_id IS 'Which set of allowed values this belongs to.';
        COMMENT ON COLUMN bird.domain.name IS 'The publisher''s readable name for this entry.';
        COMMENT ON COLUMN bird.domain.is_enumerated IS 'Whether the allowed values are a fixed published list rather than an open range.';
        COMMENT ON COLUMN bird.domain.description IS 'The publisher''s explanation of what this entry means.';
        COMMENT ON COLUMN bird.domain.data_type IS 'The kind of value expected, as published.';
        COMMENT ON COLUMN bird.domain.code IS 'The publisher''s short code for this entry.';
        COMMENT ON COLUMN bird.domain.facet_id IS 'Which set of format constraints applies.';
        COMMENT ON COLUMN bird.domain.is_reference IS 'Whether this belongs to the shared reference dictionary rather than one framework.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.facet_collection IS 'A named set of technical constraints on how a value may be written, such as a length or pattern limit.';
        COMMENT ON COLUMN bird.facet_collection.maintenance_agency_id IS 'Which organisation publishes and maintains this entry.';
        COMMENT ON COLUMN bird.facet_collection.facet_id IS 'Which set of format constraints applies.';
        COMMENT ON COLUMN bird.facet_collection.code IS 'The publisher''s short code for this entry.';
        COMMENT ON COLUMN bird.facet_collection.name IS 'The publisher''s readable name for this entry.';
        COMMENT ON COLUMN bird.facet_collection.facet_value_type IS 'The publisher''s facet value type value for this entry.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.facet_enumeration IS 'One specific constraint belonging to such a set.';
        COMMENT ON COLUMN bird.facet_enumeration.facet_id IS 'Which set of format constraints applies.';
        COMMENT ON COLUMN bird.facet_enumeration.facet_type IS 'The publisher''s facet type value for this entry.';
        COMMENT ON COLUMN bird.facet_enumeration.observation_value IS 'The publisher''s observation value value for this entry.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.member IS 'One allowed value within a domain, with its published code and meaning.';
        COMMENT ON COLUMN bird.member.maintenance_agency_id IS 'Which organisation publishes and maintains this entry.';
        COMMENT ON COLUMN bird.member.member_id IS 'Which allowed value this refers to.';
        COMMENT ON COLUMN bird.member.code IS 'The publisher''s short code for this entry.';
        COMMENT ON COLUMN bird.member.name IS 'The publisher''s readable name for this entry.';
        COMMENT ON COLUMN bird.member.domain_id IS 'Which set of allowed values this belongs to.';
        COMMENT ON COLUMN bird.member.description IS 'The publisher''s explanation of what this entry means.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.member_hierarchy IS 'A named tree that arranges the values of a domain into parent and child groupings.';
        COMMENT ON COLUMN bird.member_hierarchy.maintenance_agency_id IS 'Which organisation publishes and maintains this entry.';
        COMMENT ON COLUMN bird.member_hierarchy.member_hierarchy_id IS 'Which value tree this belongs to.';
        COMMENT ON COLUMN bird.member_hierarchy.code IS 'The publisher''s short code for this entry.';
        COMMENT ON COLUMN bird.member_hierarchy.domain_id IS 'Which set of allowed values this belongs to.';
        COMMENT ON COLUMN bird.member_hierarchy.name IS 'The publisher''s readable name for this entry.';
        COMMENT ON COLUMN bird.member_hierarchy.description IS 'The publisher''s explanation of what this entry means.';
        COMMENT ON COLUMN bird.member_hierarchy.is_main_hierarchy IS 'Whether main hierarchy applies.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.member_hierarchy_node IS 'One value''s position within such a tree, including its parent and the period the placement applies to.';
        COMMENT ON COLUMN bird.member_hierarchy_node.member_hierarchy_id IS 'Which value tree this belongs to.';
        COMMENT ON COLUMN bird.member_hierarchy_node.member_id IS 'Which allowed value this refers to.';
        COMMENT ON COLUMN bird.member_hierarchy_node.level IS 'How deep this sits in the tree.';
        COMMENT ON COLUMN bird.member_hierarchy_node.parent_member_id IS 'The value directly above this one in the tree.';
        COMMENT ON COLUMN bird.member_hierarchy_node.comparator IS 'The publisher''s comparator value for this entry.';
        COMMENT ON COLUMN bird.member_hierarchy_node.operator IS 'The publisher''s operator value for this entry.';
        COMMENT ON COLUMN bird.member_hierarchy_node.valid_from IS 'The date this entry started to apply.';
        COMMENT ON COLUMN bird.member_hierarchy_node.valid_to IS 'The date this entry stopped applying. A far-future date means it is still current.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.subdomain IS 'A narrower slice of a domain used in a particular context, such as the values valid in the Input Layer.';
        COMMENT ON COLUMN bird.subdomain.maintenance_agency_id IS 'Which organisation publishes and maintains this entry.';
        COMMENT ON COLUMN bird.subdomain.subdomain_id IS 'Which narrower slice of allowed values this refers to.';
        COMMENT ON COLUMN bird.subdomain.name IS 'The publisher''s readable name for this entry.';
        COMMENT ON COLUMN bird.subdomain.domain_id IS 'Which set of allowed values this belongs to.';
        COMMENT ON COLUMN bird.subdomain.is_listed IS 'Whether listed applies.';
        COMMENT ON COLUMN bird.subdomain.code IS 'The publisher''s short code for this entry.';
        COMMENT ON COLUMN bird.subdomain.facet_id IS 'Which set of format constraints applies.';
        COMMENT ON COLUMN bird.subdomain.description IS 'The publisher''s explanation of what this entry means.';
        COMMENT ON COLUMN bird.subdomain.is_natural IS 'Whether natural applies.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.subdomain_enumeration IS 'Which values belong to which narrower slice, and the period each one is valid for.';
        COMMENT ON COLUMN bird.subdomain_enumeration.member_id IS 'Which allowed value this refers to.';
        COMMENT ON COLUMN bird.subdomain_enumeration.subdomain_id IS 'Which narrower slice of allowed values this refers to.';
        COMMENT ON COLUMN bird.subdomain_enumeration.valid_from IS 'The date this entry started to apply.';
        COMMENT ON COLUMN bird.subdomain_enumeration.valid_to IS 'The date this entry stopped applying. A far-future date means it is still current.';
        COMMENT ON COLUMN bird.subdomain_enumeration."order" IS 'The publisher''s display ordering for this entry.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.variable IS 'A business concept that can be recorded about something, such as Purpose or Reference date. Defined once here and reused across many reporting structures.';
        COMMENT ON COLUMN bird.variable.maintenance_agency_id IS 'Which organisation publishes and maintains this entry.';
        COMMENT ON COLUMN bird.variable.variable_id IS 'Which business concept this refers to.';
        COMMENT ON COLUMN bird.variable.code IS 'The publisher''s short code for this entry.';
        COMMENT ON COLUMN bird.variable.name IS 'The publisher''s readable name for this entry.';
        COMMENT ON COLUMN bird.variable.domain_id IS 'Which set of allowed values this belongs to.';
        COMMENT ON COLUMN bird.variable.description IS 'The publisher''s explanation of what this entry means.';
        COMMENT ON COLUMN bird.variable.primary_concept IS 'The core idea this concept is built from, where the publisher states one.';
        COMMENT ON COLUMN bird.variable.is_decomposed IS 'Whether decomposed applies.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.variable_set IS 'A named grouping of related concepts, acting as a restriction whose allowed values are themselves concepts.';
        COMMENT ON COLUMN bird.variable_set.maintenance_agency_id IS 'Which organisation publishes and maintains this entry.';
        COMMENT ON COLUMN bird.variable_set.variable_set_id IS 'Which grouping of concepts this refers to.';
        COMMENT ON COLUMN bird.variable_set.name IS 'The publisher''s readable name for this entry.';
        COMMENT ON COLUMN bird.variable_set.code IS 'The publisher''s short code for this entry.';
        COMMENT ON COLUMN bird.variable_set.description IS 'The publisher''s explanation of what this entry means.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.variable_set_enumeration IS 'Which concepts belong to which grouping, and the period each membership applies to.';
        COMMENT ON COLUMN bird.variable_set_enumeration.variable_set_id IS 'Which grouping of concepts this refers to.';
        COMMENT ON COLUMN bird.variable_set_enumeration.variable_id IS 'Which business concept this refers to.';
        COMMENT ON COLUMN bird.variable_set_enumeration.valid_from IS 'The date this entry started to apply.';
        COMMENT ON COLUMN bird.variable_set_enumeration.valid_to IS 'The date this entry stopped applying. A far-future date means it is still current.';
        COMMENT ON COLUMN bird.variable_set_enumeration.subdomain_id IS 'Which narrower slice of allowed values this refers to.';
        COMMENT ON COLUMN bird.variable_set_enumeration.is_flow IS 'Whether the value accumulates over a period rather than being a point-in-time figure.';
        COMMENT ON COLUMN bird.variable_set_enumeration."order" IS 'The publisher''s display ordering for this entry.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.combination IS 'A named set of value choices that together identify what a template cell reports.';
        COMMENT ON COLUMN bird.combination.combination_id IS 'Which set of value choices this refers to.';
        COMMENT ON COLUMN bird.combination.code IS 'The publisher''s short code for this entry.';
        COMMENT ON COLUMN bird.combination.name IS 'The publisher''s readable name for this entry.';
        COMMENT ON COLUMN bird.combination.maintenance_agency_id IS 'Which organisation publishes and maintains this entry.';
        COMMENT ON COLUMN bird.combination.version IS 'The publisher''s version marker for this entry.';
        COMMENT ON COLUMN bird.combination.valid_from IS 'The date this entry started to apply.';
        COMMENT ON COLUMN bird.combination.valid_to IS 'The date this entry stopped applying. A far-future date means it is still current.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.combination_item IS 'One concept-and-value choice within such a set.';
        COMMENT ON COLUMN bird.combination_item.combination_id IS 'Which set of value choices this refers to.';
        COMMENT ON COLUMN bird.combination_item.variable_id IS 'Which business concept this refers to.';
        COMMENT ON COLUMN bird.combination_item.subdomain_id IS 'Which narrower slice of allowed values this refers to.';
        COMMENT ON COLUMN bird.combination_item.variable_set_id IS 'Which grouping of concepts this refers to.';
        COMMENT ON COLUMN bird.combination_item.member_id IS 'Which allowed value this refers to.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.cube IS 'A reporting structure that data is recorded against, the BIRD equivalent of a table. Each belongs to a framework and a layer.';
        COMMENT ON COLUMN bird.cube.maintenance_agency_id IS 'Which organisation publishes and maintains this entry.';
        COMMENT ON COLUMN bird.cube.cube_id IS 'Which reporting structure this refers to.';
        COMMENT ON COLUMN bird.cube.name IS 'The publisher''s readable name for this entry.';
        COMMENT ON COLUMN bird.cube.code IS 'The publisher''s short code for this entry.';
        COMMENT ON COLUMN bird.cube.framework_id IS 'Which regulatory framework this belongs to.';
        COMMENT ON COLUMN bird.cube.cube_structure_id IS 'Which column layout this refers to.';
        COMMENT ON COLUMN bird.cube.cube_type IS 'The publisher''s cube type value for this entry.';
        COMMENT ON COLUMN bird.cube.is_allowed IS 'Whether allowed applies.';
        COMMENT ON COLUMN bird.cube.valid_from IS 'The date this entry started to apply.';
        COMMENT ON COLUMN bird.cube.valid_to IS 'The date this entry stopped applying. A far-future date means it is still current.';
        COMMENT ON COLUMN bird.cube.version IS 'The publisher''s version marker for this entry.';
        COMMENT ON COLUMN bird.cube.description IS 'The publisher''s explanation of what this entry means.';
        COMMENT ON COLUMN bird.cube.published IS 'The publisher''s published value for this entry.';
        COMMENT ON COLUMN bird.cube.dataset_url IS 'The publisher''s dataset url value for this entry.';
        COMMENT ON COLUMN bird.cube.filters IS 'The publisher''s filters value for this entry.';
        COMMENT ON COLUMN bird.cube.di_export IS 'The publisher''s di export value for this entry.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.cube_group IS 'A subject grouping that collects related reporting structures together.';
        COMMENT ON COLUMN bird.cube_group.maintenance_agency_id IS 'Which organisation publishes and maintains this entry.';
        COMMENT ON COLUMN bird.cube_group.cube_group_id IS 'Which subject grouping this refers to.';
        COMMENT ON COLUMN bird.cube_group.name IS 'The publisher''s readable name for this entry.';
        COMMENT ON COLUMN bird.cube_group.code IS 'The publisher''s short code for this entry.';
        COMMENT ON COLUMN bird.cube_group.description IS 'The publisher''s explanation of what this entry means.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.cube_group_enumeration IS 'Which reporting structures belong to which subject grouping.';
        COMMENT ON COLUMN bird.cube_group_enumeration."order" IS 'The publisher''s display ordering for this entry.';
        COMMENT ON COLUMN bird.cube_group_enumeration.cube_group_id IS 'Which subject grouping this refers to.';
        COMMENT ON COLUMN bird.cube_group_enumeration.cube_id IS 'Which reporting structure this refers to.';
        COMMENT ON COLUMN bird.cube_group_enumeration.valid_from IS 'The date this entry started to apply.';
        COMMENT ON COLUMN bird.cube_group_enumeration.valid_to IS 'The date this entry stopped applying. A far-future date means it is still current.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.cube_hierarchy IS 'A named tree that organises subject groupings for browsing.';
        COMMENT ON COLUMN bird.cube_hierarchy.cube_hierarchy_id IS 'The publisher''s identifier for this cube hierarchy.';
        COMMENT ON COLUMN bird.cube_hierarchy.maintenance_agency_id IS 'Which organisation publishes and maintains this entry.';
        COMMENT ON COLUMN bird.cube_hierarchy.name IS 'The publisher''s readable name for this entry.';
        COMMENT ON COLUMN bird.cube_hierarchy.code IS 'The publisher''s short code for this entry.';
        COMMENT ON COLUMN bird.cube_hierarchy.description IS 'The publisher''s explanation of what this entry means.';
        COMMENT ON COLUMN bird.cube_hierarchy.cube_hierarchy_type IS 'The publisher''s cube hierarchy type value for this entry.';
        COMMENT ON COLUMN bird.cube_hierarchy.framework_id IS 'Which regulatory framework this belongs to.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.cube_hierarchy_node IS 'One subject grouping''s position within such a tree.';
        COMMENT ON COLUMN bird.cube_hierarchy_node.cube_hierarchy_id IS 'Which cube hierarchy this refers to.';
        COMMENT ON COLUMN bird.cube_hierarchy_node.node_code IS 'The publisher''s node code value for this entry.';
        COMMENT ON COLUMN bird.cube_hierarchy_node.node_name IS 'The publisher''s node name value for this entry.';
        COMMENT ON COLUMN bird.cube_hierarchy_node.level IS 'How deep this sits in the tree.';
        COMMENT ON COLUMN bird.cube_hierarchy_node.parent_node_code IS 'The publisher''s parent node code value for this entry.';
        COMMENT ON COLUMN bird.cube_hierarchy_node.cube_group_id IS 'Which subject grouping this refers to.';
        COMMENT ON COLUMN bird.cube_hierarchy_node.valid_from IS 'The date this entry started to apply.';
        COMMENT ON COLUMN bird.cube_hierarchy_node.valid_to IS 'The date this entry stopped applying. A far-future date means it is still current.';
        COMMENT ON COLUMN bird.cube_hierarchy_node."order" IS 'The publisher''s display ordering for this entry.';
        COMMENT ON COLUMN bird.cube_hierarchy_node.colour IS 'The publisher''s colour value for this entry.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.cube_relationship IS 'A link between two reporting structures, recording which attributes join them and how many records may match on each side.';
        COMMENT ON COLUMN bird.cube_relationship.maintenance_agency_id IS 'Which organisation publishes and maintains this entry.';
        COMMENT ON COLUMN bird.cube_relationship.cube_relationship_id IS 'The publisher''s identifier for this cube relationship.';
        COMMENT ON COLUMN bird.cube_relationship.code IS 'The publisher''s short code for this entry.';
        COMMENT ON COLUMN bird.cube_relationship.name IS 'The publisher''s readable name for this entry.';
        COMMENT ON COLUMN bird.cube_relationship.description IS 'The publisher''s explanation of what this entry means.';
        COMMENT ON COLUMN bird.cube_relationship.type_of_relationship IS 'The publisher''s type of relationship value for this entry.';
        COMMENT ON COLUMN bird.cube_relationship.valid_from IS 'The date this entry started to apply.';
        COMMENT ON COLUMN bird.cube_relationship.valid_to IS 'The date this entry stopped applying. A far-future date means it is still current.';
        COMMENT ON COLUMN bird.cube_relationship.version IS 'The publisher''s version marker for this entry.';
        COMMENT ON COLUMN bird.cube_relationship.primary_cube_id IS 'Which primary cube this refers to.';
        COMMENT ON COLUMN bird.cube_relationship.primary_cube_variable_code IS 'The publisher''s primary cube variable code value for this entry.';
        COMMENT ON COLUMN bird.cube_relationship.foreign_cube_id IS 'Which foreign cube this refers to.';
        COMMENT ON COLUMN bird.cube_relationship.foreign_cube_variable_code IS 'The publisher''s foreign cube variable code value for this entry.';
        COMMENT ON COLUMN bird.cube_relationship.primary_cube_cardinality IS 'The publisher''s primary cube cardinality value for this entry.';
        COMMENT ON COLUMN bird.cube_relationship.foreign_cube_cardinality IS 'The publisher''s foreign cube cardinality value for this entry.';
        COMMENT ON COLUMN bird.cube_relationship.primary_cube_mandatoriness IS 'The publisher''s primary cube mandatoriness value for this entry.';
        COMMENT ON COLUMN bird.cube_relationship.foreign_cube_mandatoriness IS 'The publisher''s foreign cube mandatoriness value for this entry.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.cube_link IS 'A defined route for moving data from one reporting structure to another, usually between layers.';
        COMMENT ON COLUMN bird.cube_link.maintenance_agency_id IS 'Which organisation publishes and maintains this entry.';
        COMMENT ON COLUMN bird.cube_link.cube_link_id IS 'The publisher''s identifier for this cube link.';
        COMMENT ON COLUMN bird.cube_link.code IS 'The publisher''s short code for this entry.';
        COMMENT ON COLUMN bird.cube_link.name IS 'The publisher''s readable name for this entry.';
        COMMENT ON COLUMN bird.cube_link.description IS 'The publisher''s explanation of what this entry means.';
        COMMENT ON COLUMN bird.cube_link.valid_from IS 'The date this entry started to apply.';
        COMMENT ON COLUMN bird.cube_link.valid_to IS 'The date this entry stopped applying. A far-future date means it is still current.';
        COMMENT ON COLUMN bird.cube_link.version IS 'The publisher''s version marker for this entry.';
        COMMENT ON COLUMN bird.cube_link.order_relevance IS 'The publisher''s order relevance value for this entry.';
        COMMENT ON COLUMN bird.cube_link.primary_cube_id IS 'Which primary cube this refers to.';
        COMMENT ON COLUMN bird.cube_link.foreign_cube_id IS 'Which foreign cube this refers to.';
        COMMENT ON COLUMN bird.cube_link.cube_link_type IS 'The publisher''s cube link type value for this entry.';
        COMMENT ON COLUMN bird.cube_link.logical_transformation_rule_id IS 'Which technical derivation rule this relates to.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.cube_structure_item_link IS 'Which attribute feeds which attribute along such a route.';
        COMMENT ON COLUMN bird.cube_structure_item_link.cube_structure_item_link_id IS 'The publisher''s identifier for this cube structure item link.';
        COMMENT ON COLUMN bird.cube_structure_item_link.cube_link_id IS 'Which cube link this refers to.';
        COMMENT ON COLUMN bird.cube_structure_item_link.foreign_cube_variable_code IS 'The publisher''s foreign cube variable code value for this entry.';
        COMMENT ON COLUMN bird.cube_structure_item_link.primary_cube_variable_code IS 'The publisher''s primary cube variable code value for this entry.';
        COMMENT ON COLUMN bird.cube_structure_item_link.comparator IS 'The publisher''s comparator value for this entry.';
        COMMENT ON COLUMN bird.cube_structure_item_link.aggregation_function IS 'The publisher''s aggregation function value for this entry.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.member_link IS 'Which allowed value corresponds to which allowed value when data moves between structures.';
        COMMENT ON COLUMN bird.member_link.cube_structure_item_link_id IS 'Which cube structure item link this refers to.';
        COMMENT ON COLUMN bird.member_link.foreign_member_id IS 'Which foreign member this refers to.';
        COMMENT ON COLUMN bird.member_link.primary_member_id IS 'Which primary member this refers to.';
        COMMENT ON COLUMN bird.member_link.valid_from IS 'The date this entry started to apply.';
        COMMENT ON COLUMN bird.member_link.valid_to IS 'The date this entry stopped applying. A far-future date means it is still current.';
        COMMENT ON COLUMN bird.member_link.is_linked IS 'Whether linked applies.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.cube_structure IS 'The versioned column layout of a reporting structure.';
        COMMENT ON COLUMN bird.cube_structure.maintenance_agency_id IS 'Which organisation publishes and maintains this entry.';
        COMMENT ON COLUMN bird.cube_structure.cube_structure_id IS 'Which column layout this refers to.';
        COMMENT ON COLUMN bird.cube_structure.name IS 'The publisher''s readable name for this entry.';
        COMMENT ON COLUMN bird.cube_structure.code IS 'The publisher''s short code for this entry.';
        COMMENT ON COLUMN bird.cube_structure.description IS 'The publisher''s explanation of what this entry means.';
        COMMENT ON COLUMN bird.cube_structure.valid_from IS 'The date this entry started to apply.';
        COMMENT ON COLUMN bird.cube_structure.valid_to IS 'The date this entry stopped applying. A far-future date means it is still current.';
        COMMENT ON COLUMN bird.cube_structure.version IS 'The publisher''s version marker for this entry.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.cube_structure_item IS 'One attribute as used within one reporting structure, including whether it forms part of the key, whether it must be filled in, and which set of values it accepts.';
        COMMENT ON COLUMN bird.cube_structure_item.cube_structure_item_id IS 'The publisher''s identifier for this cube structure item.';
        COMMENT ON COLUMN bird.cube_structure_item.cube_structure_id IS 'Which column layout this refers to.';
        COMMENT ON COLUMN bird.cube_structure_item.cube_variable_code IS 'The publisher''s cube variable code value for this entry.';
        COMMENT ON COLUMN bird.cube_structure_item.variable_id IS 'Which business concept this refers to.';
        COMMENT ON COLUMN bird.cube_structure_item.role IS 'Whether the attribute forms part of the key, carries a reported value, or qualifies another attribute.';
        COMMENT ON COLUMN bird.cube_structure_item."order" IS 'The publisher''s display ordering for this entry.';
        COMMENT ON COLUMN bird.cube_structure_item.subdomain_id IS 'Which narrower slice of allowed values this refers to.';
        COMMENT ON COLUMN bird.cube_structure_item.variable_set_id IS 'Which grouping of concepts this refers to.';
        COMMENT ON COLUMN bird.cube_structure_item.member_id IS 'Which allowed value this refers to.';
        COMMENT ON COLUMN bird.cube_structure_item.dimension_type IS 'The publisher''s dimension type value for this entry.';
        COMMENT ON COLUMN bird.cube_structure_item.attribute_associated_variable IS 'The publisher''s attribute associated variable value for this entry.';
        COMMENT ON COLUMN bird.cube_structure_item.is_flow IS 'Whether the value accumulates over a period rather than being a point-in-time figure.';
        COMMENT ON COLUMN bird.cube_structure_item.is_mandatory IS 'Whether this attribute must be filled in.';
        COMMENT ON COLUMN bird.cube_structure_item.description IS 'The publisher''s explanation of what this entry means.';
        COMMENT ON COLUMN bird.cube_structure_item.is_implemented IS 'Whether implemented applies.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.cube_to_combination IS 'Which value combinations a reporting structure can produce.';
        COMMENT ON COLUMN bird.cube_to_combination.cube_id IS 'Which reporting structure this refers to.';
        COMMENT ON COLUMN bird.cube_to_combination.combination_id IS 'Which set of value choices this refers to.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.framework_hierarchy IS 'A tree organising frameworks. Present in the export but not yet populated.';
        COMMENT ON COLUMN bird.framework_hierarchy.framework_id IS 'Which regulatory framework this belongs to.';
        COMMENT ON COLUMN bird.framework_hierarchy.member_hierarchy_id IS 'Which value tree this belongs to.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.framework_subdomain IS 'Which value slices a framework uses. Present in the export but not yet populated.';
        COMMENT ON COLUMN bird.framework_subdomain.framework_id IS 'Which regulatory framework this belongs to.';
        COMMENT ON COLUMN bird.framework_subdomain.subdomain_id IS 'Which narrower slice of allowed values this refers to.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.framework_variable_set IS 'Which concept groupings each regulatory framework uses.';
        COMMENT ON COLUMN bird.framework_variable_set.framework_id IS 'Which regulatory framework this belongs to.';
        COMMENT ON COLUMN bird.framework_variable_set.variable_set_id IS 'Which grouping of concepts this refers to.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.cube_mapping IS 'A named mapping between reporting structures.';
        COMMENT ON COLUMN bird.cube_mapping.maintenance_agency_id IS 'Which organisation publishes and maintains this entry.';
        COMMENT ON COLUMN bird.cube_mapping.cube_mapping_id IS 'The publisher''s identifier for this cube mapping.';
        COMMENT ON COLUMN bird.cube_mapping.name IS 'The publisher''s readable name for this entry.';
        COMMENT ON COLUMN bird.cube_mapping.code IS 'The publisher''s short code for this entry.';
        COMMENT ON COLUMN bird.cube_mapping.source_cube_id IS 'Which source cube this refers to.';
        COMMENT ON COLUMN bird.cube_mapping.destination_cube_id IS 'Which destination cube this refers to.';
        COMMENT ON COLUMN bird.cube_mapping.description IS 'The publisher''s explanation of what this entry means.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.combination_mapping IS 'A mapping between value combinations. Present in the export but not yet populated.';
        COMMENT ON COLUMN bird.combination_mapping.source_combination_id IS 'Which source combination this refers to.';
        COMMENT ON COLUMN bird.combination_mapping.destination_combination_id IS 'Which destination combination this refers to.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.mapping_definition IS 'A published mapping between one part of the dictionary and another.';
        COMMENT ON COLUMN bird.mapping_definition.maintenance_agency_id IS 'Which organisation publishes and maintains this entry.';
        COMMENT ON COLUMN bird.mapping_definition.mapping_id IS 'Which mapping this refers to.';
        COMMENT ON COLUMN bird.mapping_definition.name IS 'The publisher''s readable name for this entry.';
        COMMENT ON COLUMN bird.mapping_definition.mapping_type IS 'The publisher''s mapping type value for this entry.';
        COMMENT ON COLUMN bird.mapping_definition.code IS 'The publisher''s short code for this entry.';
        COMMENT ON COLUMN bird.mapping_definition.algorithm IS 'The derivation expressed as an executable rule, where the publisher provides one.';
        COMMENT ON COLUMN bird.mapping_definition.member_mapping_id IS 'Which member mapping this refers to.';
        COMMENT ON COLUMN bird.mapping_definition.variable_mapping_id IS 'Which variable mapping this refers to.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.mapping_to_cube IS 'Which reporting structures a published mapping applies to.';
        COMMENT ON COLUMN bird.mapping_to_cube.cube_mapping_id IS 'Which cube mapping this refers to.';
        COMMENT ON COLUMN bird.mapping_to_cube.mapping_id IS 'Which mapping this refers to.';
        COMMENT ON COLUMN bird.mapping_to_cube.valid_from IS 'The date this entry started to apply.';
        COMMENT ON COLUMN bird.mapping_to_cube.valid_to IS 'The date this entry stopped applying. A far-future date means it is still current.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.member_mapping IS 'A named mapping between allowed values.';
        COMMENT ON COLUMN bird.member_mapping.maintenance_agency_id IS 'Which organisation publishes and maintains this entry.';
        COMMENT ON COLUMN bird.member_mapping.member_mapping_id IS 'The publisher''s identifier for this member mapping.';
        COMMENT ON COLUMN bird.member_mapping.name IS 'The publisher''s readable name for this entry.';
        COMMENT ON COLUMN bird.member_mapping.code IS 'The publisher''s short code for this entry.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.member_mapping_item IS 'One value-to-value correspondence within such a mapping.';
        COMMENT ON COLUMN bird.member_mapping_item.member_mapping_id IS 'Which member mapping this refers to.';
        COMMENT ON COLUMN bird.member_mapping_item.member_mapping_row IS 'The publisher''s member mapping row value for this entry.';
        COMMENT ON COLUMN bird.member_mapping_item.variable_id IS 'Which business concept this refers to.';
        COMMENT ON COLUMN bird.member_mapping_item.is_source IS 'Whether this side is the input of the rule rather than its output.';
        COMMENT ON COLUMN bird.member_mapping_item.member_id IS 'Which allowed value this refers to.';
        COMMENT ON COLUMN bird.member_mapping_item.valid_from IS 'The date this entry started to apply.';
        COMMENT ON COLUMN bird.member_mapping_item.valid_to IS 'The date this entry stopped applying. A far-future date means it is still current.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.variable_mapping IS 'A named mapping between concepts.';
        COMMENT ON COLUMN bird.variable_mapping.variable_mapping_id IS 'The publisher''s identifier for this variable mapping.';
        COMMENT ON COLUMN bird.variable_mapping.maintenance_agency_id IS 'Which organisation publishes and maintains this entry.';
        COMMENT ON COLUMN bird.variable_mapping.code IS 'The publisher''s short code for this entry.';
        COMMENT ON COLUMN bird.variable_mapping.name IS 'The publisher''s readable name for this entry.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.variable_mapping_item IS 'One concept-to-concept correspondence within such a mapping.';
        COMMENT ON COLUMN bird.variable_mapping_item.variable_mapping_id IS 'Which variable mapping this refers to.';
        COMMENT ON COLUMN bird.variable_mapping_item.variable_id IS 'Which business concept this refers to.';
        COMMENT ON COLUMN bird.variable_mapping_item.is_source IS 'Whether this side is the input of the rule rather than its output.';
        COMMENT ON COLUMN bird.variable_mapping_item.valid_from IS 'The date this entry started to apply.';
        COMMENT ON COLUMN bird.variable_mapping_item.valid_to IS 'The date this entry stopped applying. A far-future date means it is still current.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.variable_set_mapping IS 'A correspondence between two concept groupings.';
        COMMENT ON COLUMN bird.variable_set_mapping.source_mapping_id IS 'Which source mapping this refers to.';
        COMMENT ON COLUMN bird.variable_set_mapping.target_mapping_id IS 'Which target mapping this refers to.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.cube_structure_mapping IS 'A mapping between reporting-structure layouts. Present in the export but not yet populated.';
        COMMENT ON COLUMN bird.cube_structure_mapping.mapping_id IS 'Which mapping this refers to.';
        COMMENT ON COLUMN bird.cube_structure_mapping.cube_mapping_id IS 'Which cube mapping this refers to.';
        COMMENT ON COLUMN bird.cube_structure_mapping.member_mapping_id IS 'Which member mapping this refers to.';
        COMMENT ON COLUMN bird.cube_structure_mapping.algorithm IS 'The derivation expressed as an executable rule, where the publisher provides one.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.cube_structure_mapping_item IS 'One correspondence within a layout mapping. Present in the export but not yet populated.';
        COMMENT ON COLUMN bird.cube_structure_mapping_item.mapping_id IS 'Which mapping this refers to.';
        COMMENT ON COLUMN bird.cube_structure_mapping_item.cube_variable_code IS 'The publisher''s cube variable code value for this entry.';
        COMMENT ON COLUMN bird.cube_structure_mapping_item.is_source IS 'Whether this side is the input of the rule rather than its output.';
        COMMENT ON COLUMN bird.cube_structure_mapping_item.valid_from IS 'The date this entry started to apply.';
        COMMENT ON COLUMN bird.cube_structure_mapping_item.valid_to IS 'The date this entry stopped applying. A far-future date means it is still current.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.axis IS 'One axis of a reporting template, such as its rows or its columns.';
        COMMENT ON COLUMN bird.axis.axis_id IS 'Which template axis this refers to.';
        COMMENT ON COLUMN bird.axis.code IS 'The publisher''s short code for this entry.';
        COMMENT ON COLUMN bird.axis.orientation IS 'The publisher''s orientation value for this entry.';
        COMMENT ON COLUMN bird.axis."order" IS 'The publisher''s display ordering for this entry.';
        COMMENT ON COLUMN bird.axis.name IS 'The publisher''s readable name for this entry.';
        COMMENT ON COLUMN bird.axis.description IS 'The publisher''s explanation of what this entry means.';
        COMMENT ON COLUMN bird.axis.table_id IS 'Which reporting template this refers to.';
        COMMENT ON COLUMN bird.axis.is_open_axis IS 'Whether open axis applies.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.axis_ordinate IS 'One position along an axis, such as a single row or column heading.';
        COMMENT ON COLUMN bird.axis_ordinate.axis_ordinate_id IS 'Which position on a template axis this refers to.';
        COMMENT ON COLUMN bird.axis_ordinate.is_abstract_header IS 'Whether abstract header applies.';
        COMMENT ON COLUMN bird.axis_ordinate.code IS 'The publisher''s short code for this entry.';
        COMMENT ON COLUMN bird.axis_ordinate."order" IS 'The publisher''s display ordering for this entry.';
        COMMENT ON COLUMN bird.axis_ordinate.level IS 'How deep this sits in the tree.';
        COMMENT ON COLUMN bird.axis_ordinate.path IS 'The publisher''s path value for this entry.';
        COMMENT ON COLUMN bird.axis_ordinate.axis_id IS 'Which template axis this refers to.';
        COMMENT ON COLUMN bird.axis_ordinate.parent_axis_ordinate_id IS 'Which parent axis ordinate this refers to.';
        COMMENT ON COLUMN bird.axis_ordinate.name IS 'The publisher''s readable name for this entry.';
        COMMENT ON COLUMN bird.axis_ordinate.description IS 'The publisher''s explanation of what this entry means.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.cell_position IS 'Where a cell sits on a template, by reference to the template''s axes.';
        COMMENT ON COLUMN bird.cell_position.cell_id IS 'Which template cell this refers to.';
        COMMENT ON COLUMN bird.cell_position.axis_ordinate_id IS 'Which position on a template axis this refers to.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.ordinate_item IS 'Which concept and value a position on an axis stands for.';
        COMMENT ON COLUMN bird.ordinate_item.axis_ordinate_id IS 'Which position on a template axis this refers to.';
        COMMENT ON COLUMN bird.ordinate_item.variable_id IS 'Which business concept this refers to.';
        COMMENT ON COLUMN bird.ordinate_item.member_id IS 'Which allowed value this refers to.';
        COMMENT ON COLUMN bird.ordinate_item.member_hierarchy_id IS 'Which value tree this belongs to.';
        COMMENT ON COLUMN bird.ordinate_item.member_hierarchy_valid_from IS 'The publisher''s member hierarchy valid from value for this entry.';
        COMMENT ON COLUMN bird.ordinate_item.starting_member_id IS 'Which starting member this refers to.';
        COMMENT ON COLUMN bird.ordinate_item.is_starting_member_included IS 'Whether starting member included applies.';
    """)
    op.execute("""
        COMMENT ON TABLE bird."table" IS 'A regulatory reporting template, the printed form a framework requires.';
        COMMENT ON COLUMN bird."table".table_id IS 'Which reporting template this refers to.';
        COMMENT ON COLUMN bird."table".name IS 'The publisher''s readable name for this entry.';
        COMMENT ON COLUMN bird."table".code IS 'The publisher''s short code for this entry.';
        COMMENT ON COLUMN bird."table".description IS 'The publisher''s explanation of what this entry means.';
        COMMENT ON COLUMN bird."table".maintenance_agency_id IS 'Which organisation publishes and maintains this entry.';
        COMMENT ON COLUMN bird."table".version IS 'The publisher''s version marker for this entry.';
        COMMENT ON COLUMN bird."table".valid_from IS 'The date this entry started to apply.';
        COMMENT ON COLUMN bird."table".valid_to IS 'The date this entry stopped applying. A far-future date means it is still current.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.table_cell IS 'One cell of a reporting template, and the combination of values it represents.';
        COMMENT ON COLUMN bird.table_cell.cell_id IS 'Which template cell this refers to.';
        COMMENT ON COLUMN bird.table_cell.is_shaded IS 'Whether shaded applies.';
        COMMENT ON COLUMN bird.table_cell.combination_id IS 'Which set of value choices this refers to.';
        COMMENT ON COLUMN bird.table_cell.table_id IS 'Which reporting template this refers to.';
        COMMENT ON COLUMN bird.table_cell.system_data_code IS 'The publisher''s system data code value for this entry.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.cube_to_table IS 'Which reporting structure feeds which reporting template.';
        COMMENT ON COLUMN bird.cube_to_table.cube_id IS 'Which reporting structure this refers to.';
        COMMENT ON COLUMN bird.cube_to_table.table_id IS 'Which reporting template this refers to.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.transformation IS 'A published transformation. Present in the export but not yet populated.';
        COMMENT ON COLUMN bird.transformation.transformation_id IS 'The publisher''s identifier for this transformation.';
        COMMENT ON COLUMN bird.transformation.transformation_scheme_id IS 'Which transformation scheme this refers to.';
        COMMENT ON COLUMN bird.transformation.maintenance_agency_id IS 'Which organisation publishes and maintains this entry.';
        COMMENT ON COLUMN bird.transformation.name IS 'The publisher''s readable name for this entry.';
        COMMENT ON COLUMN bird.transformation.code IS 'The publisher''s short code for this entry.';
        COMMENT ON COLUMN bird.transformation.description IS 'The publisher''s explanation of what this entry means.';
        COMMENT ON COLUMN bird.transformation.expression IS 'The publisher''s expression value for this entry.';
        COMMENT ON COLUMN bird.transformation.valid_from IS 'The date this entry started to apply.';
        COMMENT ON COLUMN bird.transformation.valid_to IS 'The date this entry stopped applying. A far-future date means it is still current.';
        COMMENT ON COLUMN bird.transformation."order" IS 'The publisher''s display ordering for this entry.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.transformation_node IS 'One step within a transformation. Present in the export but not yet populated.';
        COMMENT ON COLUMN bird.transformation_node.transformation_node_id IS 'The publisher''s identifier for this transformation node.';
        COMMENT ON COLUMN bird.transformation_node.transformation_id IS 'Which transformation this refers to.';
        COMMENT ON COLUMN bird.transformation_node.type_of_node IS 'The publisher''s type of node value for this entry.';
        COMMENT ON COLUMN bird.transformation_node.expression IS 'The publisher''s expression value for this entry.';
        COMMENT ON COLUMN bird.transformation_node.parent_node_id IS 'Which parent node this refers to.';
        COMMENT ON COLUMN bird.transformation_node.level IS 'How deep this sits in the tree.';
        COMMENT ON COLUMN bird.transformation_node."order" IS 'The publisher''s display ordering for this entry.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.transformation_scheme IS 'A named collection of transformations. Present in the export but not yet populated.';
        COMMENT ON COLUMN bird.transformation_scheme.transformation_scheme_id IS 'The publisher''s identifier for this transformation scheme.';
        COMMENT ON COLUMN bird.transformation_scheme.maintenance_agency_id IS 'Which organisation publishes and maintains this entry.';
        COMMENT ON COLUMN bird.transformation_scheme.name IS 'The publisher''s readable name for this entry.';
        COMMENT ON COLUMN bird.transformation_scheme.code IS 'The publisher''s short code for this entry.';
        COMMENT ON COLUMN bird.transformation_scheme.description IS 'The publisher''s explanation of what this entry means.';
        COMMENT ON COLUMN bird.transformation_scheme.type_of_scheme IS 'The publisher''s type of scheme value for this entry.';
        COMMENT ON COLUMN bird.transformation_scheme.expression IS 'The publisher''s expression value for this entry.';
        COMMENT ON COLUMN bird.transformation_scheme.phase IS 'The publisher''s phase value for this entry.';
        COMMENT ON COLUMN bird.transformation_scheme.valid_from IS 'The date this entry started to apply.';
        COMMENT ON COLUMN bird.transformation_scheme.valid_to IS 'The date this entry stopped applying. A far-future date means it is still current.';
        COMMENT ON COLUMN bird.transformation_scheme.version IS 'The publisher''s version marker for this entry.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.semantic_transformation_rule IS 'A published rule describing in business terms how a value is derived.';
        COMMENT ON COLUMN bird.semantic_transformation_rule.semantic_transformation_rule_id IS 'Which business-level derivation rule this relates to.';
        COMMENT ON COLUMN bird.semantic_transformation_rule.transformation_url IS 'The publisher''s transformation url value for this entry.';
        COMMENT ON COLUMN bird.semantic_transformation_rule.type_of_transformation IS 'The publisher''s type of transformation value for this entry.';
        COMMENT ON COLUMN bird.semantic_transformation_rule.maintenance_agency_id IS 'Which organisation publishes and maintains this entry.';
        COMMENT ON COLUMN bird.semantic_transformation_rule.name IS 'The publisher''s readable name for this entry.';
        COMMENT ON COLUMN bird.semantic_transformation_rule.code IS 'The publisher''s short code for this entry.';
        COMMENT ON COLUMN bird.semantic_transformation_rule.description IS 'The publisher''s explanation of what this entry means.';
        COMMENT ON COLUMN bird.semantic_transformation_rule.algorithm IS 'The derivation expressed as an executable rule, where the publisher provides one.';
        COMMENT ON COLUMN bird.semantic_transformation_rule.valid_from IS 'The date this entry started to apply.';
        COMMENT ON COLUMN bird.semantic_transformation_rule.valid_to IS 'The date this entry stopped applying. A far-future date means it is still current.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.transformation_to_variable IS 'Which concepts a derivation rule reads from or writes to.';
        COMMENT ON COLUMN bird.transformation_to_variable.semantic_transformation_rule_id IS 'Which business-level derivation rule this relates to.';
        COMMENT ON COLUMN bird.transformation_to_variable.variable_id IS 'Which business concept this refers to.';
        COMMENT ON COLUMN bird.transformation_to_variable.is_source IS 'Whether this side is the input of the rule rather than its output.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.transformation_to_cube IS 'Which reporting structures a derivation rule reads from or writes to.';
        COMMENT ON COLUMN bird.transformation_to_cube.semantic_transformation_rule_id IS 'Which business-level derivation rule this relates to.';
        COMMENT ON COLUMN bird.transformation_to_cube.cube_id IS 'Which reporting structure this refers to.';
        COMMENT ON COLUMN bird.transformation_to_cube.is_source IS 'Whether this side is the input of the rule rather than its output.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.logical_transformation_rule IS 'The technical form of a derivation rule, including which layer it reads from and writes to.';
        COMMENT ON COLUMN bird.logical_transformation_rule.logical_transformation_rule_id IS 'Which technical derivation rule this relates to.';
        COMMENT ON COLUMN bird.logical_transformation_rule.semantic_transformation_rule_id IS 'Which business-level derivation rule this relates to.';
        COMMENT ON COLUMN bird.logical_transformation_rule.algorithm IS 'The derivation expressed as an executable rule, where the publisher provides one.';
        COMMENT ON COLUMN bird.logical_transformation_rule.additional_filters IS 'The publisher''s additional filters value for this entry.';
        COMMENT ON COLUMN bird.logical_transformation_rule.source_layer IS 'The layer the rule reads from.';
        COMMENT ON COLUMN bird.logical_transformation_rule.destination_layer IS 'The layer the rule writes to.';
        COMMENT ON COLUMN bird.logical_transformation_rule.transformation_type IS 'The publisher''s transformation type value for this entry.';
        COMMENT ON COLUMN bird.logical_transformation_rule.valid_from IS 'The date this entry started to apply.';
        COMMENT ON COLUMN bird.logical_transformation_rule.valid_to IS 'The date this entry stopped applying. A far-future date means it is still current.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.legal_reference IS 'Which article of a regulation gives a definition or an allowed value its legal basis.';
        COMMENT ON COLUMN bird.legal_reference.object_type IS 'What kind of dictionary item the legal basis applies to.';
        COMMENT ON COLUMN bird.legal_reference.object_id IS 'Which dictionary item the legal basis applies to. Read together with the item type, as it may point at different kinds of thing.';
        COMMENT ON COLUMN bird.legal_reference.legal_text_id IS 'Which regulation or standard this refers to.';
        COMMENT ON COLUMN bird.legal_reference.article IS 'The specific article or paragraph relied on.';
        COMMENT ON COLUMN bird.legal_reference.valid_from IS 'The date this entry started to apply.';
        COMMENT ON COLUMN bird.legal_reference.valid_to IS 'The date this entry stopped applying. A far-future date means it is still current.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.legal_text IS 'A regulation or accounting standard that dictionary definitions refer to, with a link to the published text.';
        COMMENT ON COLUMN bird.legal_text.legal_text_id IS 'Which regulation or standard this refers to.';
        COMMENT ON COLUMN bird.legal_text.legal_code IS 'The publisher''s legal code value for this entry.';
        COMMENT ON COLUMN bird.legal_text.legal_description IS 'The publisher''s legal description value for this entry.';
        COMMENT ON COLUMN bird.legal_text.business_description IS 'The publisher''s business description value for this entry.';
        COMMENT ON COLUMN bird.legal_text.hyperlink IS 'The publisher''s hyperlink value for this entry.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.classification IS 'A published classification scheme. Present in the export but not yet populated.';
        COMMENT ON COLUMN bird.classification.classification_id IS 'The publisher''s identifier for this classification.';
        COMMENT ON COLUMN bird.classification.code IS 'The publisher''s short code for this entry.';
        COMMENT ON COLUMN bird.classification.name IS 'The publisher''s readable name for this entry.';
        COMMENT ON COLUMN bird.classification.description IS 'The publisher''s explanation of what this entry means.';
    """)
    op.execute("""
        COMMENT ON TABLE bird.classification_assignment IS 'Which items belong to a classification scheme. Present in the export but not yet populated.';
        COMMENT ON COLUMN bird.classification_assignment.object_type IS 'What kind of dictionary item the legal basis applies to.';
        COMMENT ON COLUMN bird.classification_assignment.object_id IS 'Which dictionary item the legal basis applies to. Read together with the item type, as it may point at different kinds of thing.';
        COMMENT ON COLUMN bird.classification_assignment.classification_id IS 'Which classification this refers to.';
        COMMENT ON COLUMN bird.classification_assignment.valid_from IS 'The date this entry started to apply.';
        COMMENT ON COLUMN bird.classification_assignment.valid_to IS 'The date this entry stopped applying. A far-future date means it is still current.';
    """)

    # ---- indexes: query performance only, no constraint on what may be loaded ----
    op.execute('CREATE INDEX ix_bird_maintenance_agency_maintenance_agency_id ON bird.maintenance_agency (maintenance_agency_id);')
    op.execute('CREATE INDEX ix_bird_framework_maintenance_agency_id ON bird.framework (maintenance_agency_id);')
    op.execute('CREATE INDEX ix_bird_framework_framework_id ON bird.framework (framework_id);')
    op.execute('CREATE INDEX ix_bird_domain_maintenance_agency_id ON bird.domain (maintenance_agency_id);')
    op.execute('CREATE INDEX ix_bird_domain_domain_id ON bird.domain (domain_id);')
    op.execute('CREATE INDEX ix_bird_domain_facet_id ON bird.domain (facet_id);')
    op.execute('CREATE INDEX ix_bird_facet_collection_maintenance_agency_id ON bird.facet_collection (maintenance_agency_id);')
    op.execute('CREATE INDEX ix_bird_facet_collection_facet_id ON bird.facet_collection (facet_id);')
    op.execute('CREATE INDEX ix_bird_facet_enumeration_facet_id ON bird.facet_enumeration (facet_id);')
    op.execute('CREATE INDEX ix_bird_member_maintenance_agency_id ON bird.member (maintenance_agency_id);')
    op.execute('CREATE INDEX ix_bird_member_member_id ON bird.member (member_id);')
    op.execute('CREATE INDEX ix_bird_member_domain_id ON bird.member (domain_id);')
    op.execute('CREATE INDEX ix_bird_member_hierarchy_maintenance_agency_id ON bird.member_hierarchy (maintenance_agency_id);')
    op.execute('CREATE INDEX ix_bird_member_hierarchy_member_hierarchy_id ON bird.member_hierarchy (member_hierarchy_id);')
    op.execute('CREATE INDEX ix_bird_member_hierarchy_domain_id ON bird.member_hierarchy (domain_id);')
    op.execute('CREATE INDEX ix_bird_member_hierarchy_node_member_hierarchy_id ON bird.member_hierarchy_node (member_hierarchy_id);')
    op.execute('CREATE INDEX ix_bird_member_hierarchy_node_member_id ON bird.member_hierarchy_node (member_id);')
    op.execute('CREATE INDEX ix_bird_member_hierarchy_node_parent_member_id ON bird.member_hierarchy_node (parent_member_id);')
    op.execute('CREATE INDEX ix_bird_subdomain_maintenance_agency_id ON bird.subdomain (maintenance_agency_id);')
    op.execute('CREATE INDEX ix_bird_subdomain_subdomain_id ON bird.subdomain (subdomain_id);')
    op.execute('CREATE INDEX ix_bird_subdomain_domain_id ON bird.subdomain (domain_id);')
    op.execute('CREATE INDEX ix_bird_subdomain_facet_id ON bird.subdomain (facet_id);')
    op.execute('CREATE INDEX ix_bird_subdomain_enumeration_member_id ON bird.subdomain_enumeration (member_id);')
    op.execute('CREATE INDEX ix_bird_subdomain_enumeration_subdomain_id ON bird.subdomain_enumeration (subdomain_id);')
    op.execute('CREATE INDEX ix_bird_variable_maintenance_agency_id ON bird.variable (maintenance_agency_id);')
    op.execute('CREATE INDEX ix_bird_variable_variable_id ON bird.variable (variable_id);')
    op.execute('CREATE INDEX ix_bird_variable_domain_id ON bird.variable (domain_id);')
    op.execute('CREATE INDEX ix_bird_variable_set_maintenance_agency_id ON bird.variable_set (maintenance_agency_id);')
    op.execute('CREATE INDEX ix_bird_variable_set_variable_set_id ON bird.variable_set (variable_set_id);')
    op.execute('CREATE INDEX ix_bird_variable_set_enumeration_variable_set_id ON bird.variable_set_enumeration (variable_set_id);')
    op.execute('CREATE INDEX ix_bird_variable_set_enumeration_variable_id ON bird.variable_set_enumeration (variable_id);')
    op.execute('CREATE INDEX ix_bird_variable_set_enumeration_subdomain_id ON bird.variable_set_enumeration (subdomain_id);')
    op.execute('CREATE INDEX ix_bird_combination_combination_id ON bird.combination (combination_id);')
    op.execute('CREATE INDEX ix_bird_combination_maintenance_agency_id ON bird.combination (maintenance_agency_id);')
    op.execute('CREATE INDEX ix_bird_combination_item_combination_id ON bird.combination_item (combination_id);')
    op.execute('CREATE INDEX ix_bird_combination_item_variable_id ON bird.combination_item (variable_id);')
    op.execute('CREATE INDEX ix_bird_combination_item_subdomain_id ON bird.combination_item (subdomain_id);')
    op.execute('CREATE INDEX ix_bird_combination_item_variable_set_id ON bird.combination_item (variable_set_id);')
    op.execute('CREATE INDEX ix_bird_combination_item_member_id ON bird.combination_item (member_id);')
    op.execute('CREATE INDEX ix_bird_cube_maintenance_agency_id ON bird.cube (maintenance_agency_id);')
    op.execute('CREATE INDEX ix_bird_cube_cube_id ON bird.cube (cube_id);')
    op.execute('CREATE INDEX ix_bird_cube_framework_id ON bird.cube (framework_id);')
    op.execute('CREATE INDEX ix_bird_cube_cube_structure_id ON bird.cube (cube_structure_id);')
    op.execute('CREATE INDEX ix_bird_cube_cube_type ON bird.cube (cube_type);')
    op.execute('CREATE INDEX ix_bird_cube_group_maintenance_agency_id ON bird.cube_group (maintenance_agency_id);')
    op.execute('CREATE INDEX ix_bird_cube_group_cube_group_id ON bird.cube_group (cube_group_id);')
    op.execute('CREATE INDEX ix_bird_cube_group_enumeration_cube_group_id ON bird.cube_group_enumeration (cube_group_id);')
    op.execute('CREATE INDEX ix_bird_cube_group_enumeration_cube_id ON bird.cube_group_enumeration (cube_id);')
    op.execute('CREATE INDEX ix_bird_cube_hierarchy_cube_hierarchy_id ON bird.cube_hierarchy (cube_hierarchy_id);')
    op.execute('CREATE INDEX ix_bird_cube_hierarchy_maintenance_agency_id ON bird.cube_hierarchy (maintenance_agency_id);')
    op.execute('CREATE INDEX ix_bird_cube_hierarchy_framework_id ON bird.cube_hierarchy (framework_id);')
    op.execute('CREATE INDEX ix_bird_cube_hierarchy_node_cube_hierarchy_id ON bird.cube_hierarchy_node (cube_hierarchy_id);')
    op.execute('CREATE INDEX ix_bird_cube_hierarchy_node_cube_group_id ON bird.cube_hierarchy_node (cube_group_id);')
    op.execute('CREATE INDEX ix_bird_cube_relationship_maintenance_agency_id ON bird.cube_relationship (maintenance_agency_id);')
    op.execute('CREATE INDEX ix_bird_cube_relationship_cube_relationship_id ON bird.cube_relationship (cube_relationship_id);')
    op.execute('CREATE INDEX ix_bird_cube_relationship_primary_cube_id ON bird.cube_relationship (primary_cube_id);')
    op.execute('CREATE INDEX ix_bird_cube_relationship_foreign_cube_id ON bird.cube_relationship (foreign_cube_id);')
    op.execute('CREATE INDEX ix_bird_cube_link_maintenance_agency_id ON bird.cube_link (maintenance_agency_id);')
    op.execute('CREATE INDEX ix_bird_cube_link_cube_link_id ON bird.cube_link (cube_link_id);')
    op.execute('CREATE INDEX ix_bird_cube_link_primary_cube_id ON bird.cube_link (primary_cube_id);')
    op.execute('CREATE INDEX ix_bird_cube_link_foreign_cube_id ON bird.cube_link (foreign_cube_id);')
    op.execute('CREATE INDEX ix_bird_cube_link_logical_transformation_rule_id ON bird.cube_link (logical_transformation_rule_id);')
    op.execute('CREATE INDEX ix_bird_cube_structure_item_link_cube_structure_item_link_id ON bird.cube_structure_item_link (cube_structure_item_link_id);')
    op.execute('CREATE INDEX ix_bird_cube_structure_item_link_cube_link_id ON bird.cube_structure_item_link (cube_link_id);')
    op.execute('CREATE INDEX ix_bird_member_link_cube_structure_item_link_id ON bird.member_link (cube_structure_item_link_id);')
    op.execute('CREATE INDEX ix_bird_member_link_foreign_member_id ON bird.member_link (foreign_member_id);')
    op.execute('CREATE INDEX ix_bird_member_link_primary_member_id ON bird.member_link (primary_member_id);')
    op.execute('CREATE INDEX ix_bird_cube_structure_maintenance_agency_id ON bird.cube_structure (maintenance_agency_id);')
    op.execute('CREATE INDEX ix_bird_cube_structure_cube_structure_id ON bird.cube_structure (cube_structure_id);')
    op.execute('CREATE INDEX ix_bird_cube_structure_item_cube_structure_item_id ON bird.cube_structure_item (cube_structure_item_id);')
    op.execute('CREATE INDEX ix_bird_cube_structure_item_cube_structure_id ON bird.cube_structure_item (cube_structure_id);')
    op.execute('CREATE INDEX ix_bird_cube_structure_item_variable_id ON bird.cube_structure_item (variable_id);')
    op.execute('CREATE INDEX ix_bird_cube_structure_item_role ON bird.cube_structure_item (role);')
    op.execute('CREATE INDEX ix_bird_cube_structure_item_subdomain_id ON bird.cube_structure_item (subdomain_id);')
    op.execute('CREATE INDEX ix_bird_cube_structure_item_variable_set_id ON bird.cube_structure_item (variable_set_id);')
    op.execute('CREATE INDEX ix_bird_cube_structure_item_member_id ON bird.cube_structure_item (member_id);')
    op.execute('CREATE INDEX ix_bird_cube_to_combination_cube_id ON bird.cube_to_combination (cube_id);')
    op.execute('CREATE INDEX ix_bird_cube_to_combination_combination_id ON bird.cube_to_combination (combination_id);')
    op.execute('CREATE INDEX ix_bird_framework_hierarchy_framework_id ON bird.framework_hierarchy (framework_id);')
    op.execute('CREATE INDEX ix_bird_framework_hierarchy_member_hierarchy_id ON bird.framework_hierarchy (member_hierarchy_id);')
    op.execute('CREATE INDEX ix_bird_framework_subdomain_framework_id ON bird.framework_subdomain (framework_id);')
    op.execute('CREATE INDEX ix_bird_framework_subdomain_subdomain_id ON bird.framework_subdomain (subdomain_id);')
    op.execute('CREATE INDEX ix_bird_framework_variable_set_framework_id ON bird.framework_variable_set (framework_id);')
    op.execute('CREATE INDEX ix_bird_framework_variable_set_variable_set_id ON bird.framework_variable_set (variable_set_id);')
    op.execute('CREATE INDEX ix_bird_cube_mapping_maintenance_agency_id ON bird.cube_mapping (maintenance_agency_id);')
    op.execute('CREATE INDEX ix_bird_cube_mapping_cube_mapping_id ON bird.cube_mapping (cube_mapping_id);')
    op.execute('CREATE INDEX ix_bird_cube_mapping_source_cube_id ON bird.cube_mapping (source_cube_id);')
    op.execute('CREATE INDEX ix_bird_cube_mapping_destination_cube_id ON bird.cube_mapping (destination_cube_id);')
    op.execute('CREATE INDEX ix_bird_combination_mapping_source_combination_id ON bird.combination_mapping (source_combination_id);')
    op.execute('CREATE INDEX ix_bird_combination_mapping_destination_combination_id ON bird.combination_mapping (destination_combination_id);')
    op.execute('CREATE INDEX ix_bird_mapping_definition_maintenance_agency_id ON bird.mapping_definition (maintenance_agency_id);')
    op.execute('CREATE INDEX ix_bird_mapping_definition_mapping_id ON bird.mapping_definition (mapping_id);')
    op.execute('CREATE INDEX ix_bird_mapping_definition_member_mapping_id ON bird.mapping_definition (member_mapping_id);')
    op.execute('CREATE INDEX ix_bird_mapping_definition_variable_mapping_id ON bird.mapping_definition (variable_mapping_id);')
    op.execute('CREATE INDEX ix_bird_mapping_to_cube_cube_mapping_id ON bird.mapping_to_cube (cube_mapping_id);')
    op.execute('CREATE INDEX ix_bird_mapping_to_cube_mapping_id ON bird.mapping_to_cube (mapping_id);')
    op.execute('CREATE INDEX ix_bird_member_mapping_maintenance_agency_id ON bird.member_mapping (maintenance_agency_id);')
    op.execute('CREATE INDEX ix_bird_member_mapping_member_mapping_id ON bird.member_mapping (member_mapping_id);')
    op.execute('CREATE INDEX ix_bird_member_mapping_item_member_mapping_id ON bird.member_mapping_item (member_mapping_id);')
    op.execute('CREATE INDEX ix_bird_member_mapping_item_variable_id ON bird.member_mapping_item (variable_id);')
    op.execute('CREATE INDEX ix_bird_member_mapping_item_member_id ON bird.member_mapping_item (member_id);')
    op.execute('CREATE INDEX ix_bird_variable_mapping_variable_mapping_id ON bird.variable_mapping (variable_mapping_id);')
    op.execute('CREATE INDEX ix_bird_variable_mapping_maintenance_agency_id ON bird.variable_mapping (maintenance_agency_id);')
    op.execute('CREATE INDEX ix_bird_variable_mapping_item_variable_mapping_id ON bird.variable_mapping_item (variable_mapping_id);')
    op.execute('CREATE INDEX ix_bird_variable_mapping_item_variable_id ON bird.variable_mapping_item (variable_id);')
    op.execute('CREATE INDEX ix_bird_variable_set_mapping_source_mapping_id ON bird.variable_set_mapping (source_mapping_id);')
    op.execute('CREATE INDEX ix_bird_variable_set_mapping_target_mapping_id ON bird.variable_set_mapping (target_mapping_id);')
    op.execute('CREATE INDEX ix_bird_cube_structure_mapping_mapping_id ON bird.cube_structure_mapping (mapping_id);')
    op.execute('CREATE INDEX ix_bird_cube_structure_mapping_cube_mapping_id ON bird.cube_structure_mapping (cube_mapping_id);')
    op.execute('CREATE INDEX ix_bird_cube_structure_mapping_member_mapping_id ON bird.cube_structure_mapping (member_mapping_id);')
    op.execute('CREATE INDEX ix_bird_cube_structure_mapping_item_mapping_id ON bird.cube_structure_mapping_item (mapping_id);')
    op.execute('CREATE INDEX ix_bird_axis_axis_id ON bird.axis (axis_id);')
    op.execute('CREATE INDEX ix_bird_axis_table_id ON bird.axis (table_id);')
    op.execute('CREATE INDEX ix_bird_axis_ordinate_axis_ordinate_id ON bird.axis_ordinate (axis_ordinate_id);')
    op.execute('CREATE INDEX ix_bird_axis_ordinate_axis_id ON bird.axis_ordinate (axis_id);')
    op.execute('CREATE INDEX ix_bird_axis_ordinate_parent_axis_ordinate_id ON bird.axis_ordinate (parent_axis_ordinate_id);')
    op.execute('CREATE INDEX ix_bird_cell_position_cell_id ON bird.cell_position (cell_id);')
    op.execute('CREATE INDEX ix_bird_cell_position_axis_ordinate_id ON bird.cell_position (axis_ordinate_id);')
    op.execute('CREATE INDEX ix_bird_ordinate_item_axis_ordinate_id ON bird.ordinate_item (axis_ordinate_id);')
    op.execute('CREATE INDEX ix_bird_ordinate_item_variable_id ON bird.ordinate_item (variable_id);')
    op.execute('CREATE INDEX ix_bird_ordinate_item_member_id ON bird.ordinate_item (member_id);')
    op.execute('CREATE INDEX ix_bird_ordinate_item_member_hierarchy_id ON bird.ordinate_item (member_hierarchy_id);')
    op.execute('CREATE INDEX ix_bird_ordinate_item_starting_member_id ON bird.ordinate_item (starting_member_id);')
    op.execute('CREATE INDEX ix_bird_table_table_id ON bird."table" (table_id);')
    op.execute('CREATE INDEX ix_bird_table_maintenance_agency_id ON bird."table" (maintenance_agency_id);')
    op.execute('CREATE INDEX ix_bird_table_cell_cell_id ON bird.table_cell (cell_id);')
    op.execute('CREATE INDEX ix_bird_table_cell_combination_id ON bird.table_cell (combination_id);')
    op.execute('CREATE INDEX ix_bird_table_cell_table_id ON bird.table_cell (table_id);')
    op.execute('CREATE INDEX ix_bird_cube_to_table_cube_id ON bird.cube_to_table (cube_id);')
    op.execute('CREATE INDEX ix_bird_cube_to_table_table_id ON bird.cube_to_table (table_id);')
    op.execute('CREATE INDEX ix_bird_transformation_transformation_id ON bird.transformation (transformation_id);')
    op.execute('CREATE INDEX ix_bird_transformation_transformation_scheme_id ON bird.transformation (transformation_scheme_id);')
    op.execute('CREATE INDEX ix_bird_transformation_maintenance_agency_id ON bird.transformation (maintenance_agency_id);')
    op.execute('CREATE INDEX ix_bird_transformation_node_transformation_node_id ON bird.transformation_node (transformation_node_id);')
    op.execute('CREATE INDEX ix_bird_transformation_node_transformation_id ON bird.transformation_node (transformation_id);')
    op.execute('CREATE INDEX ix_bird_transformation_node_parent_node_id ON bird.transformation_node (parent_node_id);')
    op.execute('CREATE INDEX ix_bird_transformation_scheme_transformation_scheme_id ON bird.transformation_scheme (transformation_scheme_id);')
    op.execute('CREATE INDEX ix_bird_transformation_scheme_maintenance_agency_id ON bird.transformation_scheme (maintenance_agency_id);')
    op.execute('CREATE INDEX ix_bird_semantic_transformation_rule_semantic_transformation_rule_id ON bird.semantic_transformation_rule (semantic_transformation_rule_id);')
    op.execute('CREATE INDEX ix_bird_semantic_transformation_rule_maintenance_agency_id ON bird.semantic_transformation_rule (maintenance_agency_id);')
    op.execute('CREATE INDEX ix_bird_transformation_to_variable_semantic_transformation_rule_id ON bird.transformation_to_variable (semantic_transformation_rule_id);')
    op.execute('CREATE INDEX ix_bird_transformation_to_variable_variable_id ON bird.transformation_to_variable (variable_id);')
    op.execute('CREATE INDEX ix_bird_transformation_to_cube_semantic_transformation_rule_id ON bird.transformation_to_cube (semantic_transformation_rule_id);')
    op.execute('CREATE INDEX ix_bird_transformation_to_cube_cube_id ON bird.transformation_to_cube (cube_id);')
    op.execute('CREATE INDEX ix_bird_logical_transformation_rule_logical_transformation_rule_id ON bird.logical_transformation_rule (logical_transformation_rule_id);')
    op.execute('CREATE INDEX ix_bird_logical_transformation_rule_semantic_transformation_rule_id ON bird.logical_transformation_rule (semantic_transformation_rule_id);')
    op.execute('CREATE INDEX ix_bird_logical_transformation_rule_source_layer ON bird.logical_transformation_rule (source_layer);')
    op.execute('CREATE INDEX ix_bird_logical_transformation_rule_destination_layer ON bird.logical_transformation_rule (destination_layer);')
    op.execute('CREATE INDEX ix_bird_legal_reference_object_id ON bird.legal_reference (object_id);')
    op.execute('CREATE INDEX ix_bird_legal_reference_legal_text_id ON bird.legal_reference (legal_text_id);')
    op.execute('CREATE INDEX ix_bird_legal_text_legal_text_id ON bird.legal_text (legal_text_id);')
    op.execute('CREATE INDEX ix_bird_classification_classification_id ON bird.classification (classification_id);')
    op.execute('CREATE INDEX ix_bird_classification_assignment_object_id ON bird.classification_assignment (object_id);')
    op.execute('CREATE INDEX ix_bird_classification_assignment_classification_id ON bird.classification_assignment (classification_id);')

    # ---- current-version views: validity filter built in ----
    op.execute("""
        CREATE VIEW bird.member_hierarchy_node_current AS
        SELECT * FROM bird.member_hierarchy_node
         WHERE (valid_from IS NULL OR valid_from <= CURRENT_DATE) AND (valid_to IS NULL OR valid_to >= CURRENT_DATE);
    """)
    op.execute("""
        COMMENT ON VIEW bird.member_hierarchy_node_current IS
          'Only the rows of bird.member_hierarchy_node that apply today. Use this unless you specifically need historical entries; for a past reporting date, filter the base table on that date instead.';
    """)
    op.execute("""
        CREATE VIEW bird.subdomain_enumeration_current AS
        SELECT * FROM bird.subdomain_enumeration
         WHERE (valid_from IS NULL OR valid_from <= CURRENT_DATE) AND (valid_to IS NULL OR valid_to >= CURRENT_DATE);
    """)
    op.execute("""
        COMMENT ON VIEW bird.subdomain_enumeration_current IS
          'Only the rows of bird.subdomain_enumeration that apply today. Use this unless you specifically need historical entries; for a past reporting date, filter the base table on that date instead.';
    """)
    op.execute("""
        CREATE VIEW bird.variable_set_enumeration_current AS
        SELECT * FROM bird.variable_set_enumeration
         WHERE (valid_from IS NULL OR valid_from <= CURRENT_DATE) AND (valid_to IS NULL OR valid_to >= CURRENT_DATE);
    """)
    op.execute("""
        COMMENT ON VIEW bird.variable_set_enumeration_current IS
          'Only the rows of bird.variable_set_enumeration that apply today. Use this unless you specifically need historical entries; for a past reporting date, filter the base table on that date instead.';
    """)
    op.execute("""
        CREATE VIEW bird.combination_current AS
        SELECT * FROM bird.combination
         WHERE (valid_from IS NULL OR valid_from <= CURRENT_DATE) AND (valid_to IS NULL OR valid_to >= CURRENT_DATE);
    """)
    op.execute("""
        COMMENT ON VIEW bird.combination_current IS
          'Only the rows of bird.combination that apply today. Use this unless you specifically need historical entries; for a past reporting date, filter the base table on that date instead.';
    """)
    op.execute("""
        CREATE VIEW bird.cube_current AS
        SELECT * FROM bird.cube
         WHERE (valid_from IS NULL OR valid_from <= CURRENT_DATE) AND (valid_to IS NULL OR valid_to >= CURRENT_DATE);
    """)
    op.execute("""
        COMMENT ON VIEW bird.cube_current IS
          'Only the rows of bird.cube that apply today. Use this unless you specifically need historical entries; for a past reporting date, filter the base table on that date instead.';
    """)
    op.execute("""
        CREATE VIEW bird.cube_group_enumeration_current AS
        SELECT * FROM bird.cube_group_enumeration
         WHERE (valid_from IS NULL OR valid_from <= CURRENT_DATE) AND (valid_to IS NULL OR valid_to >= CURRENT_DATE);
    """)
    op.execute("""
        COMMENT ON VIEW bird.cube_group_enumeration_current IS
          'Only the rows of bird.cube_group_enumeration that apply today. Use this unless you specifically need historical entries; for a past reporting date, filter the base table on that date instead.';
    """)
    op.execute("""
        CREATE VIEW bird.cube_hierarchy_node_current AS
        SELECT * FROM bird.cube_hierarchy_node
         WHERE (valid_from IS NULL OR valid_from <= CURRENT_DATE) AND (valid_to IS NULL OR valid_to >= CURRENT_DATE);
    """)
    op.execute("""
        COMMENT ON VIEW bird.cube_hierarchy_node_current IS
          'Only the rows of bird.cube_hierarchy_node that apply today. Use this unless you specifically need historical entries; for a past reporting date, filter the base table on that date instead.';
    """)
    op.execute("""
        CREATE VIEW bird.cube_relationship_current AS
        SELECT * FROM bird.cube_relationship
         WHERE (valid_from IS NULL OR valid_from <= CURRENT_DATE) AND (valid_to IS NULL OR valid_to >= CURRENT_DATE);
    """)
    op.execute("""
        COMMENT ON VIEW bird.cube_relationship_current IS
          'Only the rows of bird.cube_relationship that apply today. Use this unless you specifically need historical entries; for a past reporting date, filter the base table on that date instead.';
    """)
    op.execute("""
        CREATE VIEW bird.cube_link_current AS
        SELECT * FROM bird.cube_link
         WHERE (valid_from IS NULL OR valid_from <= CURRENT_DATE) AND (valid_to IS NULL OR valid_to >= CURRENT_DATE);
    """)
    op.execute("""
        COMMENT ON VIEW bird.cube_link_current IS
          'Only the rows of bird.cube_link that apply today. Use this unless you specifically need historical entries; for a past reporting date, filter the base table on that date instead.';
    """)
    op.execute("""
        CREATE VIEW bird.member_link_current AS
        SELECT * FROM bird.member_link
         WHERE (valid_from IS NULL OR valid_from <= CURRENT_DATE) AND (valid_to IS NULL OR valid_to >= CURRENT_DATE);
    """)
    op.execute("""
        COMMENT ON VIEW bird.member_link_current IS
          'Only the rows of bird.member_link that apply today. Use this unless you specifically need historical entries; for a past reporting date, filter the base table on that date instead.';
    """)
    op.execute("""
        CREATE VIEW bird.cube_structure_current AS
        SELECT * FROM bird.cube_structure
         WHERE (valid_from IS NULL OR valid_from <= CURRENT_DATE) AND (valid_to IS NULL OR valid_to >= CURRENT_DATE);
    """)
    op.execute("""
        COMMENT ON VIEW bird.cube_structure_current IS
          'Only the rows of bird.cube_structure that apply today. Use this unless you specifically need historical entries; for a past reporting date, filter the base table on that date instead.';
    """)
    op.execute("""
        CREATE VIEW bird.mapping_to_cube_current AS
        SELECT * FROM bird.mapping_to_cube
         WHERE (valid_from IS NULL OR valid_from <= CURRENT_DATE) AND (valid_to IS NULL OR valid_to >= CURRENT_DATE);
    """)
    op.execute("""
        COMMENT ON VIEW bird.mapping_to_cube_current IS
          'Only the rows of bird.mapping_to_cube that apply today. Use this unless you specifically need historical entries; for a past reporting date, filter the base table on that date instead.';
    """)
    op.execute("""
        CREATE VIEW bird.member_mapping_item_current AS
        SELECT * FROM bird.member_mapping_item
         WHERE (valid_from IS NULL OR valid_from <= CURRENT_DATE) AND (valid_to IS NULL OR valid_to >= CURRENT_DATE);
    """)
    op.execute("""
        COMMENT ON VIEW bird.member_mapping_item_current IS
          'Only the rows of bird.member_mapping_item that apply today. Use this unless you specifically need historical entries; for a past reporting date, filter the base table on that date instead.';
    """)
    op.execute("""
        CREATE VIEW bird.variable_mapping_item_current AS
        SELECT * FROM bird.variable_mapping_item
         WHERE (valid_from IS NULL OR valid_from <= CURRENT_DATE) AND (valid_to IS NULL OR valid_to >= CURRENT_DATE);
    """)
    op.execute("""
        COMMENT ON VIEW bird.variable_mapping_item_current IS
          'Only the rows of bird.variable_mapping_item that apply today. Use this unless you specifically need historical entries; for a past reporting date, filter the base table on that date instead.';
    """)
    op.execute("""
        CREATE VIEW bird.cube_structure_mapping_item_current AS
        SELECT * FROM bird.cube_structure_mapping_item
         WHERE (valid_from IS NULL OR valid_from <= CURRENT_DATE) AND (valid_to IS NULL OR valid_to >= CURRENT_DATE);
    """)
    op.execute("""
        COMMENT ON VIEW bird.cube_structure_mapping_item_current IS
          'Only the rows of bird.cube_structure_mapping_item that apply today. Use this unless you specifically need historical entries; for a past reporting date, filter the base table on that date instead.';
    """)
    op.execute("""
        CREATE VIEW bird.table_current AS
        SELECT * FROM bird."table"
         WHERE (valid_from IS NULL OR valid_from <= CURRENT_DATE) AND (valid_to IS NULL OR valid_to >= CURRENT_DATE);
    """)
    op.execute("""
        COMMENT ON VIEW bird.table_current IS
          'Only the rows of bird.table that apply today. Use this unless you specifically need historical entries; for a past reporting date, filter the base table on that date instead.';
    """)
    op.execute("""
        CREATE VIEW bird.transformation_current AS
        SELECT * FROM bird.transformation
         WHERE (valid_from IS NULL OR valid_from <= CURRENT_DATE) AND (valid_to IS NULL OR valid_to >= CURRENT_DATE);
    """)
    op.execute("""
        COMMENT ON VIEW bird.transformation_current IS
          'Only the rows of bird.transformation that apply today. Use this unless you specifically need historical entries; for a past reporting date, filter the base table on that date instead.';
    """)
    op.execute("""
        CREATE VIEW bird.transformation_scheme_current AS
        SELECT * FROM bird.transformation_scheme
         WHERE (valid_from IS NULL OR valid_from <= CURRENT_DATE) AND (valid_to IS NULL OR valid_to >= CURRENT_DATE);
    """)
    op.execute("""
        COMMENT ON VIEW bird.transformation_scheme_current IS
          'Only the rows of bird.transformation_scheme that apply today. Use this unless you specifically need historical entries; for a past reporting date, filter the base table on that date instead.';
    """)
    op.execute("""
        CREATE VIEW bird.semantic_transformation_rule_current AS
        SELECT * FROM bird.semantic_transformation_rule
         WHERE (valid_from IS NULL OR valid_from <= CURRENT_DATE) AND (valid_to IS NULL OR valid_to >= CURRENT_DATE);
    """)
    op.execute("""
        COMMENT ON VIEW bird.semantic_transformation_rule_current IS
          'Only the rows of bird.semantic_transformation_rule that apply today. Use this unless you specifically need historical entries; for a past reporting date, filter the base table on that date instead.';
    """)
    op.execute("""
        CREATE VIEW bird.logical_transformation_rule_current AS
        SELECT * FROM bird.logical_transformation_rule
         WHERE (valid_from IS NULL OR valid_from <= CURRENT_DATE) AND (valid_to IS NULL OR valid_to >= CURRENT_DATE);
    """)
    op.execute("""
        COMMENT ON VIEW bird.logical_transformation_rule_current IS
          'Only the rows of bird.logical_transformation_rule that apply today. Use this unless you specifically need historical entries; for a past reporting date, filter the base table on that date instead.';
    """)
    op.execute("""
        CREATE VIEW bird.legal_reference_current AS
        SELECT * FROM bird.legal_reference
         WHERE (valid_from IS NULL OR valid_from <= CURRENT_DATE) AND (valid_to IS NULL OR valid_to >= CURRENT_DATE);
    """)
    op.execute("""
        COMMENT ON VIEW bird.legal_reference_current IS
          'Only the rows of bird.legal_reference that apply today. Use this unless you specifically need historical entries; for a past reporting date, filter the base table on that date instead.';
    """)
    op.execute("""
        CREATE VIEW bird.classification_assignment_current AS
        SELECT * FROM bird.classification_assignment
         WHERE (valid_from IS NULL OR valid_from <= CURRENT_DATE) AND (valid_to IS NULL OR valid_to >= CURRENT_DATE);
    """)
    op.execute("""
        COMMENT ON VIEW bird.classification_assignment_current IS
          'Only the rows of bird.classification_assignment that apply today. Use this unless you specifically need historical entries; for a past reporting date, filter the base table on that date instead.';
    """)

    # ---- which export produced the contents of this schema ----
    op.execute("""
        CREATE TABLE bird.bird_load (
            load_id      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            source_file  TEXT        NOT NULL,
            file_sha256  TEXT        NOT NULL,
            sheet_count  INTEGER     NOT NULL,
            row_count    BIGINT      NOT NULL,
            loaded_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            notes        TEXT
        );
    """)
    op.execute("""
        COMMENT ON TABLE bird.bird_load IS
          'One row per load of the BIRD dictionary, recording which published file the contents came from so a mapping can state which export it was made against.';
        COMMENT ON COLUMN bird.bird_load.load_id IS 'Internal identifier for this load.';
        COMMENT ON COLUMN bird.bird_load.source_file IS 'Name of the published export file that was loaded.';
        COMMENT ON COLUMN bird.bird_load.file_sha256 IS 'Checksum of that file, so the exact contents can be confirmed later.';
        COMMENT ON COLUMN bird.bird_load.sheet_count IS 'How many sheets the file contained.';
        COMMENT ON COLUMN bird.bird_load.row_count IS 'How many rows were loaded in total across every table.';
        COMMENT ON COLUMN bird.bird_load.loaded_at IS 'When the load ran.';
        COMMENT ON COLUMN bird.bird_load.notes IS 'Anything worth recording about this particular load.';
    """)


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS bird CASCADE;")
