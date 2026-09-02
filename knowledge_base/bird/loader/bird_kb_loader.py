"""
BIRD Knowledge Base — DuckDB Loader (complete, 30 tables)
ADIRRA Project · ALM Partners · BIRD v6.7

Loads every sheet from the multi-framework SMCube export into DuckDB.
All reference material for the full LDM → IL → EIL → ROL journey included.

File location:  knowledge_base/bird/loader/bird_kb_loader.py
Source file:    knowledge_base/bird/source/BIRDv6.7_DM_Reg_ANC.xlsx
Output DB:      knowledge_base/bird/data/bird_kb.duckdb  (gitignored)

Performance: ~30s total (parse 16s + load 14s).
Strategy: pandas reads all sheets once; DuckDB registers each DataFrame
          and inserts via CTAS — no Python row-iteration.

Run rule: once after clone, and re-run when a new BIRD release is available
          and explicitly prompted to do so. Never run automatically on app start.

Usage (from repo root):
    python knowledge_base/bird/loader/bird_kb_loader.py \\
        --multi-framework knowledge_base/bird/source/BIRDv6.7_DM_Reg_ANC.xlsx \\
        --db knowledge_base/bird/data/bird_kb.duckdb

Dependencies (already in requirements.txt): duckdb, pandas, openpyxl

Navigation context:
    This loader serves the BIRD KB module, accessible in the app under:
    Knowledge Base → BIRD
    The generated bird_kb.duckdb is consumed by the FastAPI backend endpoints
    that power the BIRD KB page (entity browser, graph view, mapping lookup,
    forward chain display) and the Regulatory Workspace → BIRD Mapping module.
    When the AnaCredit Regulatory KB loader is built, it follows the same pattern:
    knowledge_base/anacredit/loader/anacredit_kb_loader.py
"""

import argparse
import logging
import sys
import time
from pathlib import Path

import duckdb
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# Table spec: (table_name, sheet_name, [(dest_col, source_expr), ...])
# source_expr is a SQL expression referencing the registered DataFrame view.
# ═══════════════════════════════════════════════════════════════════════

TABLE_SPECS = [

    # ── GROUP 1: Root reference ───────────────────────────────────────
    ("maintenance_agency", "MAINTENANCE_AGENCY", [
        ("maintenance_agency_id", "MAINTENANCE_AGENCY_ID"),
        ("code",        "CODE"),
        ("name",        "NAME"),
        ("description", "DESCRIPTION"),
        ("deleted",     "DELETED"),
    ]),
    ("framework", "FRAMEWORK", [
        ("maintenance_agency_id", "MAINTENANCE_AGENCY_ID"),
        ("framework_id",     "FRAMEWORK_ID"),
        ("name",             "NAME"),
        ("code",             "CODE"),
        ("description",      "DESCRIPTION"),
        ("framework_type",   "FRAMEWORK_TYPE"),
        ("reporting_population", "REPORTING_POPULATION"),
        ("other_links",      "OTHER_LINKS"),
        ("order_num",        '"ORDER"'),
        ("framework_status", "FRAMEWORK_STATUS"),
    ]),

    # ── GROUP 2: Domain / value ───────────────────────────────────────
    ("facet_collection", "FACET_COLLECTION", [
        ("maintenance_agency_id", "MAINTENANCE_AGENCY_ID"),
        ("facet_id",         "FACET_ID"),
        ("code",             "CODE"),
        ("name",             "NAME"),
        ("facet_value_type", "FACET_VALUE_TYPE"),
    ]),
    ("facet_enumeration", "FACET_ENUMERATION", [
        ("facet_id",          "FACET_ID"),
        ("facet_type",        "FACET_TYPE"),
        ("observation_value", "OBSERVATION_VALUE"),
    ]),
    ("domain", "DOMAIN", [
        ("maintenance_agency_id", "MAINTENANCE_AGENCY_ID"),
        ("domain_id",      "DOMAIN_ID"),
        ("name",           "NAME"),
        ("is_enumerated",  "IS_ENUMERATED"),
        ("description",    "DESCRIPTION"),
        ("data_type",      "DATA_TYPE"),
        ("code",           "CODE"),
        ("facet_id",       "FACET_ID"),
        ("is_reference",   "IS_REFERENCE"),
    ]),
    ("member", "MEMBER", [
        ("maintenance_agency_id", "MAINTENANCE_AGENCY_ID"),
        ("member_id",    "MEMBER_ID"),
        ("code",         "CODE"),
        ("name",         "NAME"),
        ("domain_id",    "DOMAIN_ID"),
        ("description",  "DESCRIPTION"),
    ]),
    ("member_hierarchy", "MEMBER_HIERARCHY", [
        ("maintenance_agency_id",  "MAINTENANCE_AGENCY_ID"),
        ("member_hierarchy_id",    "MEMBER_HIERARCHY_ID"),
        ("code",                   "CODE"),
        ("domain_id",              "DOMAIN_ID"),
        ("name",                   "NAME"),
        ("description",            "DESCRIPTION"),
        ("is_main_hierarchy",      "IS_MAIN_HIERARCHY"),
    ]),
    ("member_hierarchy_node", "MEMBER_HIERARCHY_NODE", [
        ("member_hierarchy_id", "MEMBER_HIERARCHY_ID"),
        ("member_id",           "MEMBER_ID"),
        ("level",               "LEVEL"),
        ("parent_member_id",    "PARENT_MEMBER_ID"),
        ("comparator",          "COMPARATOR"),
        ("operator",            "OPERATOR"),
        ("valid_from",          "VALID_FROM"),
        ("valid_to",            "VALID_TO"),
    ]),
    ("subdomain", "SUBDOMAIN", [
        ("maintenance_agency_id", "MAINTENANCE_AGENCY_ID"),
        ("subdomain_id",   "SUBDOMAIN_ID"),
        ("name",           "NAME"),
        ("domain_id",      "DOMAIN_ID"),
        ("is_listed",      "IS_LISTED"),
        ("code",           "CODE"),
        ("facet_id",       "FACET_ID"),
        ("description",    "DESCRIPTION"),
        ("is_natural",     "IS_NATURAL"),
    ]),
    ("subdomain_enumeration", "SUBDOMAIN_ENUMERATION", [
        ("member_id",    "MEMBER_ID"),
        ("subdomain_id", "SUBDOMAIN_ID"),
        ("valid_from",   "VALID_FROM"),
        ("valid_to",     "VALID_TO"),
        ("order_num",    '"ORDER"'),
    ]),

    # ── GROUP 3: Variable / variable set ─────────────────────────────
    ("variable", "VARIABLE", [
        ("maintenance_agency_id", "MAINTENANCE_AGENCY_ID"),
        ("variable_id",    "VARIABLE_ID"),
        ("code",           "CODE"),
        ("name",           "NAME"),
        ("domain_id",      "DOMAIN_ID"),
        ("description",    "DESCRIPTION"),
        ("primary_concept","PRIMARY_CONCEPT"),
        ("is_decomposed",  "IS_DECOMPOSED"),
    ]),
    ("variable_set", "VARIABLE_SET", [
        ("maintenance_agency_id", "MAINTENANCE_AGENCY_ID"),
        ("variable_set_id", "VARIABLE_SET_ID"),
        ("name",            "NAME"),
        ("code",            "CODE"),
        ("description",     "DESCRIPTION"),
    ]),
    ("variable_set_enumeration", "VARIABLE_SET_ENUMERATION", [
        ("variable_set_id", "VARIABLE_SET_ID"),
        ("variable_id",     "VARIABLE_ID"),
        ("valid_from",      "VALID_FROM"),
        ("valid_to",        "VALID_TO"),
        ("subdomain_id",    "SUBDOMAIN_ID"),
        ("is_flow",         "IS_FLOW"),
        ("order_num",       '"ORDER"'),
    ]),
    ("framework_variable_set", "FRAMEWORK_VARIABLE_SET", [
        ("framework_id",    "FRAMEWORK_ID"),
        ("variable_set_id", "VARIABLE_SET_ID"),
    ]),

    # ── GROUP 4: Cube / entity ────────────────────────────────────────
    ("cube_structure", "CUBE_STRUCTURE", [
        ("maintenance_agency_id", "MAINTENANCE_AGENCY_ID"),
        ("cube_structure_id", "CUBE_STRUCTURE_ID"),
        ("name",              "NAME"),
        ("code",              "CODE"),
        ("description",       "DESCRIPTION"),
        ("valid_from",        "VALID_FROM"),
        ("valid_to",          "VALID_TO"),
        ("version",           "VERSION"),
    ]),
    ("cube", "CUBE", [
        ("maintenance_agency_id", "MAINTENANCE_AGENCY_ID"),
        ("cube_id",           "CUBE_ID"),
        ("name",              "NAME"),
        ("code",              "CODE"),
        ("framework_id",      "FRAMEWORK_ID"),
        ("cube_structure_id", "CUBE_STRUCTURE_ID"),
        ("cube_type",         "CUBE_TYPE"),
        ("is_allowed",        "IS_ALLOWED"),
        ("valid_from",        "VALID_FROM"),
        ("valid_to",          "VALID_TO"),
        ("version",           "VERSION"),
        ("description",       "DESCRIPTION"),
        ("published",         "PUBLISHED"),
        ("dataset_url",       "DATASET_URL"),
        ("filters",           "FILTERS"),
        ("di_export",         "DI_EXPORT"),
        ("cube_group_id",     "CAST_NULL"),   # denormalised below
    ]),
    ("cube_group", "CUBE_GROUP", [
        ("maintenance_agency_id", "MAINTENANCE_AGENCY_ID"),
        ("cube_group_id", "CUBE_GROUP_ID"),
        ("name",          "NAME"),
        ("code",          "CODE"),
        ("description",   "DESCRIPTION"),
    ]),
    ("cube_group_enumeration", "CUBE_GROUP_ENUMERATION", [
        ("order_num",     '"ORDER"'),
        ("cube_group_id", "CUBE_GROUP_ID"),
        ("cube_id",       "CUBE_ID"),
        ("valid_from",    "VALID_FROM"),
        ("valid_to",      "VALID_TO"),
    ]),
    ("cube_hierarchy", "CUBE_HIERARCHY", [
        ("cube_hierarchy_id",   "CUBE_HIERARCHY_ID"),
        ("maintenance_agency_id", "MAINTENANCE_AGENCY_ID"),
        ("name",                "NAME"),
        ("code",                "CODE"),
        ("description",         "DESCRIPTION"),
        ("cube_hierarchy_type", "CUBE_HIERARCHY_TYPE"),
        ("framework_id",        "FRAMEWORK_ID"),
    ]),
    ("cube_hierarchy_node", "CUBE_HIERARCHY_NODE", [
        ("cube_hierarchy_id",  "CUBE_HIERARCHY_ID"),
        ("node_code",          "NODE_CODE"),
        ("node_name",          "NODE_NAME"),
        ("level",              "LEVEL"),
        ("parent_node_code",   "PARENT_NODE_CODE"),
        ("cube_group_id",      "CUBE_GROUP_ID"),
        ("valid_from",         "VALID_FROM"),
        ("valid_to",           "VALID_TO"),
        ("order_num",          '"ORDER"'),
        ("colour",             "COLOUR"),
    ]),
    ("cube_structure_item", "CUBE_STRUCTURE_ITEM", [
        ("cube_structure_item_id",        "CUBE_STRUCTURE_ITEM_ID"),
        ("cube_structure_id",             "CUBE_STRUCTURE_ID"),
        ("cube_variable_code",            "CUBE_VARIABLE_CODE"),
        ("variable_id",                   "VARIABLE_ID"),
        ("role",                          "ROLE"),
        ("order_num",                     '"ORDER"'),
        ("subdomain_id",                  "SUBDOMAIN_ID"),
        ("variable_set_id",               "VARIABLE_SET_ID"),
        ("member_id",                     "MEMBER_ID"),
        ("dimension_type",                "DIMENSION_TYPE"),
        ("attribute_associated_variable", "ATTRIBUTE_ASSOCIATED_VARIABLE"),
        ("is_flow",                       "IS_FLOW"),
        ("is_mandatory",                  "IS_MANDATORY"),
        ("description",                   "DESCRIPTION"),
        ("is_implemented",                "IS_IMPLEMENTED"),
    ]),

    # ── GROUP 5: Relationship / link ──────────────────────────────────
    ("cube_relationship", "CUBE_RELATIONSHIP", [
        ("maintenance_agency_id",       "MAINTENANCE_AGENCY_ID"),
        ("cube_relationship_id",        "CUBE_RELATIONSHIP_ID"),
        ("code",                        "CODE"),
        ("name",                        "NAME"),
        ("description",                 "DESCRIPTION"),
        ("type_of_relationship",        "TYPE_OF_RELATIONSHIP"),
        ("valid_from",                  "VALID_FROM"),
        ("valid_to",                    "VALID_TO"),
        ("version",                     "VERSION"),
        ("primary_cube_id",             "PRIMARY_CUBE_ID"),
        ("primary_cube_variable_code",  "PRIMARY_CUBE_VARIABLE_CODE"),
        ("foreign_cube_id",             "FOREIGN_CUBE_ID"),
        ("foreign_cube_variable_code",  "FOREIGN_CUBE_VARIABLE_CODE"),
        ("primary_cube_cardinality",    "PRIMARY_CUBE_CARDINALITY"),
        ("foreign_cube_cardinality",    "FOREIGN_CUBE_CARDINALITY"),
        ("primary_cube_mandatoriness",  "PRIMARY_CUBE_MANDATORINESS"),
        ("foreign_cube_mandatoriness",  "FOREIGN_CUBE_MANDATORINESS"),
    ]),
    ("cube_link", "CUBE_LINK", [
        ("maintenance_agency_id",           "MAINTENANCE_AGENCY_ID"),
        ("cube_link_id",                    "CUBE_LINK_ID"),
        ("code",                            "CODE"),
        ("name",                            "NAME"),
        ("description",                     "DESCRIPTION"),
        ("valid_from",                      "VALID_FROM"),
        ("valid_to",                        "VALID_TO"),
        ("version",                         "VERSION"),
        ("order_relevance",                 "ORDER_RELEVANCE"),
        ("primary_cube_id",                 "PRIMARY_CUBE_ID"),
        ("foreign_cube_id",                 "FOREIGN_CUBE_ID"),
        ("cube_link_type",                  "CUBE_LINK_TYPE"),
        ("logical_transformation_rule_id",  "LOGICAL_TRANSFORMATION_RULE_ID"),
    ]),
    ("cube_structure_item_link", "CUBE_STRUCTURE_ITEM_LINK", [
        ("cube_structure_item_link_id",  "CUBE_STRUCTURE_ITEM_LINK_ID"),
        ("cube_link_id",                 "CUBE_LINK_ID"),
        ("foreign_cube_variable_code",   "FOREIGN_CUBE_VARIABLE_CODE"),
        ("primary_cube_variable_code",   "PRIMARY_CUBE_VARIABLE_CODE"),
        ("comparator",                   "COMPARATOR"),
        ("aggregation_function",         "AGGREGATION_FUNCTION"),
    ]),
    ("member_link", "MEMBER_LINK", [
        ("cube_structure_item_link_id", "CUBE_STRUCTURE_ITEM_LINK_ID"),
        ("foreign_member_id",           "FOREIGN_MEMBER_ID"),
        ("primary_member_id",           "PRIMARY_MEMBER_ID"),
        ("valid_from",                  "VALID_FROM"),
        ("valid_to",                    "VALID_TO"),
        ("is_linked",                   "IS_LINKED"),
    ]),

    # ── GROUP 6: Transformation ───────────────────────────────────────
    ("semantic_transformation_rule", "SEMANTIC_TRANSFORMATION_RULE", [
        ("semantic_transformation_rule_id", "SEMANTIC_TRANSFORMATION_RULE_ID"),
        ("transformation_url",   "TRANSFORMATION_URL"),
        ("type_of_transformation","TYPE_OF_TRANSFORMATION"),
        ("maintenance_agency_id","MAINTENANCE_AGENCY_ID"),
        ("name",        "NAME"),
        ("code",        "CODE"),
        ("description", "DESCRIPTION"),
        ("algorithm",   "ALGORITHM"),
        ("valid_from",  "VALID_FROM"),
        ("valid_to",    "VALID_TO"),
    ]),
    ("transformation_to_variable", "TRANSFORMATION_TO_VARIABLE", [
        ("semantic_transformation_rule_id", "SEMANTIC_TRANSFORMATION_RULE_ID"),
        ("variable_id", "VARIABLE_ID"),
        ("is_source",   "IS_SOURCE"),
    ]),
    ("transformation_to_cube", "TRANSFORMATION_TO_CUBE", [
        ("semantic_transformation_rule_id", "SEMANTIC_TRANSFORMATION_RULE_ID"),
        ("cube_id",   "CUBE_ID"),
        ("is_source", "IS_SOURCE"),
    ]),
    ("logical_transformation_rule", "LOGICAL_TRANSFORMATION_RULE", [
        ("logical_transformation_rule_id",  "LOGICAL_TRANSFORMATION_RULE_ID"),
        ("semantic_transformation_rule_id", "SEMANTIC_TRANSFORMATION_RULE_ID"),
        ("algorithm",           "ALGORITHM"),
        ("additional_filters",  "ADDITIONAL_FILTERS"),
        ("source_layer",        "SOURCE_LAYER"),
        ("destination_layer",   "DESTINATION_LAYER"),
        ("transformation_type", "TRANSFORMATION_TYPE"),
        ("valid_from",          "VALID_FROM"),
        ("valid_to",            "VALID_TO"),
    ]),

    # ── GROUP 7: Legal ────────────────────────────────────────────────
    ("legal_text", "LEGAL_TEXT", [
        ("legal_text_id",        "LEGAL_TEXT_ID"),
        ("legal_code",           "LEGAL_CODE"),
        ("legal_description",    "LEGAL_DESCRIPTION"),
        ("business_description", "BUSINESS_DESCRIPTION"),
        ("hyperlink",            "HYPERLINK"),
    ]),
    # legal_reference is handled separately (needs synthesised PK)
]


# ═══════════════════════════════════════════════════════════════════════
# DDL — 30 tables
# ═══════════════════════════════════════════════════════════════════════

DDL = """
CREATE TABLE IF NOT EXISTS maintenance_agency (
    maintenance_agency_id TEXT PRIMARY KEY, code TEXT, name TEXT, description TEXT, deleted BOOLEAN);

CREATE TABLE IF NOT EXISTS framework (
    maintenance_agency_id TEXT, framework_id TEXT PRIMARY KEY, name TEXT, code TEXT,
    description TEXT, framework_type TEXT, reporting_population TEXT, other_links TEXT,
    order_num INTEGER, framework_status TEXT);

CREATE TABLE IF NOT EXISTS facet_collection (
    maintenance_agency_id TEXT, facet_id TEXT PRIMARY KEY, code TEXT, name TEXT, facet_value_type TEXT);

CREATE TABLE IF NOT EXISTS facet_enumeration (
    facet_id TEXT, facet_type TEXT, observation_value TEXT,
    PRIMARY KEY (facet_id, facet_type, observation_value));
CREATE INDEX IF NOT EXISTS idx_fe ON facet_enumeration(facet_id);

CREATE TABLE IF NOT EXISTS domain (
    maintenance_agency_id TEXT, domain_id TEXT PRIMARY KEY, name TEXT, is_enumerated BOOLEAN,
    description TEXT, data_type TEXT, code TEXT, facet_id TEXT, is_reference BOOLEAN);
CREATE INDEX IF NOT EXISTS idx_dom_facet ON domain(facet_id);

CREATE TABLE IF NOT EXISTS member (
    maintenance_agency_id TEXT, member_id TEXT PRIMARY KEY, code TEXT, name TEXT,
    domain_id TEXT, description TEXT);
CREATE INDEX IF NOT EXISTS idx_mem_dom ON member(domain_id);

CREATE TABLE IF NOT EXISTS member_hierarchy (
    maintenance_agency_id TEXT, member_hierarchy_id TEXT PRIMARY KEY, code TEXT,
    domain_id TEXT, name TEXT, description TEXT, is_main_hierarchy BOOLEAN);
CREATE INDEX IF NOT EXISTS idx_mh_dom ON member_hierarchy(domain_id);

CREATE TABLE IF NOT EXISTS member_hierarchy_node (
    member_hierarchy_id TEXT, member_id TEXT, level INTEGER, parent_member_id TEXT,
    comparator TEXT, operator TEXT, valid_from TEXT, valid_to TEXT,
    PRIMARY KEY (member_hierarchy_id, member_id));
CREATE INDEX IF NOT EXISTS idx_mhn_h ON member_hierarchy_node(member_hierarchy_id);

CREATE TABLE IF NOT EXISTS subdomain (
    maintenance_agency_id TEXT, subdomain_id TEXT PRIMARY KEY, name TEXT, domain_id TEXT,
    is_listed BOOLEAN, code TEXT, facet_id TEXT, description TEXT, is_natural BOOLEAN);
CREATE INDEX IF NOT EXISTS idx_sd_dom ON subdomain(domain_id);

CREATE TABLE IF NOT EXISTS subdomain_enumeration (
    member_id TEXT, subdomain_id TEXT, valid_from TEXT, valid_to TEXT, order_num INTEGER,
    PRIMARY KEY (member_id, subdomain_id));
CREATE INDEX IF NOT EXISTS idx_se_sd ON subdomain_enumeration(subdomain_id);
CREATE INDEX IF NOT EXISTS idx_se_m  ON subdomain_enumeration(member_id);

CREATE TABLE IF NOT EXISTS variable (
    maintenance_agency_id TEXT, variable_id TEXT PRIMARY KEY, code TEXT, name TEXT,
    domain_id TEXT, description TEXT, primary_concept TEXT, is_decomposed BOOLEAN);
CREATE INDEX IF NOT EXISTS idx_var_dom ON variable(domain_id);

CREATE TABLE IF NOT EXISTS variable_set (
    maintenance_agency_id TEXT, variable_set_id TEXT PRIMARY KEY, name TEXT, code TEXT, description TEXT);

CREATE TABLE IF NOT EXISTS variable_set_enumeration (
    variable_set_id TEXT, variable_id TEXT, valid_from TEXT, valid_to TEXT,
    subdomain_id TEXT, is_flow BOOLEAN, order_num INTEGER,
    PRIMARY KEY (variable_set_id, variable_id));
CREATE INDEX IF NOT EXISTS idx_vse_s ON variable_set_enumeration(variable_set_id);
CREATE INDEX IF NOT EXISTS idx_vse_v ON variable_set_enumeration(variable_id);

CREATE TABLE IF NOT EXISTS framework_variable_set (
    framework_id TEXT, variable_set_id TEXT, PRIMARY KEY (framework_id, variable_set_id));

CREATE TABLE IF NOT EXISTS cube_structure (
    maintenance_agency_id TEXT, cube_structure_id TEXT PRIMARY KEY, name TEXT, code TEXT,
    description TEXT, valid_from TEXT, valid_to TEXT, version TEXT);

CREATE TABLE IF NOT EXISTS cube (
    maintenance_agency_id TEXT, cube_id TEXT PRIMARY KEY, name TEXT, code TEXT,
    framework_id TEXT, cube_structure_id TEXT, cube_type TEXT, is_allowed BOOLEAN,
    valid_from TEXT, valid_to TEXT, version TEXT, description TEXT, published TEXT,
    dataset_url TEXT, filters TEXT, di_export TEXT, cube_group_id TEXT);
CREATE INDEX IF NOT EXISTS idx_cube_type  ON cube(cube_type);
CREATE INDEX IF NOT EXISTS idx_cube_fw    ON cube(framework_id);
CREATE INDEX IF NOT EXISTS idx_cube_grp   ON cube(cube_group_id);
CREATE INDEX IF NOT EXISTS idx_cube_str   ON cube(cube_structure_id);

CREATE TABLE IF NOT EXISTS cube_group (
    maintenance_agency_id TEXT, cube_group_id TEXT PRIMARY KEY, name TEXT, code TEXT, description TEXT);

CREATE TABLE IF NOT EXISTS cube_group_enumeration (
    order_num INTEGER, cube_group_id TEXT, cube_id TEXT, valid_from TEXT, valid_to TEXT,
    PRIMARY KEY (cube_group_id, cube_id));
CREATE INDEX IF NOT EXISTS idx_cge_g ON cube_group_enumeration(cube_group_id);
CREATE INDEX IF NOT EXISTS idx_cge_c ON cube_group_enumeration(cube_id);

CREATE TABLE IF NOT EXISTS cube_hierarchy (
    cube_hierarchy_id TEXT PRIMARY KEY, maintenance_agency_id TEXT, name TEXT, code TEXT,
    description TEXT, cube_hierarchy_type TEXT, framework_id TEXT);

CREATE TABLE IF NOT EXISTS cube_hierarchy_node (
    cube_hierarchy_id TEXT, node_code TEXT, node_name TEXT, level INTEGER,
    parent_node_code TEXT, cube_group_id TEXT, valid_from TEXT, valid_to TEXT,
    order_num INTEGER, colour TEXT, PRIMARY KEY (cube_hierarchy_id, node_code));
CREATE INDEX IF NOT EXISTS idx_chn_g ON cube_hierarchy_node(cube_group_id);

CREATE TABLE IF NOT EXISTS cube_structure_item (
    cube_structure_item_id TEXT PRIMARY KEY, cube_structure_id TEXT,
    cube_variable_code TEXT, variable_id TEXT, role TEXT, order_num INTEGER,
    subdomain_id TEXT, variable_set_id TEXT, member_id TEXT, dimension_type TEXT,
    attribute_associated_variable TEXT, is_flow BOOLEAN, is_mandatory BOOLEAN,
    description TEXT, is_implemented BOOLEAN);
CREATE INDEX IF NOT EXISTS idx_csi_str ON cube_structure_item(cube_structure_id);
CREATE INDEX IF NOT EXISTS idx_csi_rol ON cube_structure_item(role);
CREATE INDEX IF NOT EXISTS idx_csi_var ON cube_structure_item(variable_id);
CREATE INDEX IF NOT EXISTS idx_csi_sd  ON cube_structure_item(subdomain_id);

CREATE TABLE IF NOT EXISTS cube_relationship (
    maintenance_agency_id TEXT, cube_relationship_id TEXT PRIMARY KEY,
    code TEXT, name TEXT, description TEXT, type_of_relationship TEXT,
    valid_from TEXT, valid_to TEXT, version TEXT,
    primary_cube_id TEXT, primary_cube_variable_code TEXT,
    foreign_cube_id TEXT, foreign_cube_variable_code TEXT,
    primary_cube_cardinality TEXT, foreign_cube_cardinality TEXT,
    primary_cube_mandatoriness TEXT, foreign_cube_mandatoriness TEXT);
CREATE INDEX IF NOT EXISTS idx_cr_p ON cube_relationship(primary_cube_id);
CREATE INDEX IF NOT EXISTS idx_cr_f ON cube_relationship(foreign_cube_id);

CREATE TABLE IF NOT EXISTS cube_link (
    maintenance_agency_id TEXT, cube_link_id TEXT PRIMARY KEY,
    code TEXT, name TEXT, description TEXT, valid_from TEXT, valid_to TEXT, version TEXT,
    order_relevance TEXT, primary_cube_id TEXT, foreign_cube_id TEXT,
    cube_link_type TEXT, logical_transformation_rule_id TEXT);
CREATE INDEX IF NOT EXISTS idx_cl_p ON cube_link(primary_cube_id);
CREATE INDEX IF NOT EXISTS idx_cl_f ON cube_link(foreign_cube_id);
CREATE INDEX IF NOT EXISTS idx_cl_l ON cube_link(logical_transformation_rule_id);

CREATE TABLE IF NOT EXISTS cube_structure_item_link (
    cube_structure_item_link_id TEXT PRIMARY KEY, cube_link_id TEXT,
    foreign_cube_variable_code TEXT, primary_cube_variable_code TEXT,
    comparator TEXT, aggregation_function TEXT);
CREATE INDEX IF NOT EXISTS idx_csil_l ON cube_structure_item_link(cube_link_id);

CREATE TABLE IF NOT EXISTS member_link (
    cube_structure_item_link_id TEXT, foreign_member_id TEXT, primary_member_id TEXT,
    valid_from TEXT, valid_to TEXT, is_linked BOOLEAN,
    PRIMARY KEY (cube_structure_item_link_id, foreign_member_id, primary_member_id));
CREATE INDEX IF NOT EXISTS idx_ml_l  ON member_link(cube_structure_item_link_id);
CREATE INDEX IF NOT EXISTS idx_ml_fm ON member_link(foreign_member_id);
CREATE INDEX IF NOT EXISTS idx_ml_pm ON member_link(primary_member_id);

CREATE TABLE IF NOT EXISTS semantic_transformation_rule (
    semantic_transformation_rule_id TEXT PRIMARY KEY, transformation_url TEXT,
    type_of_transformation TEXT, maintenance_agency_id TEXT, name TEXT, code TEXT,
    description TEXT, algorithm TEXT, valid_from TEXT, valid_to TEXT);

CREATE TABLE IF NOT EXISTS transformation_to_variable (
    semantic_transformation_rule_id TEXT, variable_id TEXT, is_source BOOLEAN,
    PRIMARY KEY (semantic_transformation_rule_id, variable_id));
CREATE INDEX IF NOT EXISTS idx_ttv_r ON transformation_to_variable(semantic_transformation_rule_id);

CREATE TABLE IF NOT EXISTS transformation_to_cube (
    semantic_transformation_rule_id TEXT, cube_id TEXT, is_source BOOLEAN,
    PRIMARY KEY (semantic_transformation_rule_id, cube_id));
CREATE INDEX IF NOT EXISTS idx_ttc_r ON transformation_to_cube(semantic_transformation_rule_id);

CREATE TABLE IF NOT EXISTS logical_transformation_rule (
    logical_transformation_rule_id TEXT PRIMARY KEY,
    semantic_transformation_rule_id TEXT, algorithm TEXT, additional_filters TEXT,
    source_layer TEXT, destination_layer TEXT, transformation_type TEXT,
    valid_from TEXT, valid_to TEXT);
CREATE INDEX IF NOT EXISTS idx_ltr_sem ON logical_transformation_rule(semantic_transformation_rule_id);
CREATE INDEX IF NOT EXISTS idx_ltr_typ ON logical_transformation_rule(transformation_type);
CREATE INDEX IF NOT EXISTS idx_ltr_lay ON logical_transformation_rule(source_layer, destination_layer);

CREATE TABLE IF NOT EXISTS legal_text (
    legal_text_id TEXT PRIMARY KEY, legal_code TEXT, legal_description TEXT,
    business_description TEXT, hyperlink TEXT);

CREATE TABLE IF NOT EXISTS legal_reference (
    legal_reference_id TEXT PRIMARY KEY, object_type TEXT, object_id TEXT,
    legal_text_id TEXT, article TEXT, valid_from TEXT, valid_to TEXT);
CREATE INDEX IF NOT EXISTS idx_lr_obj ON legal_reference(object_id);
CREATE INDEX IF NOT EXISTS idx_lr_txt ON legal_reference(legal_text_id);
"""

DROP_ORDER = [
    "legal_reference","legal_text",
    "logical_transformation_rule","transformation_to_cube","transformation_to_variable",
    "semantic_transformation_rule",
    "member_link","cube_structure_item_link","cube_link","cube_relationship",
    "cube_structure_item","cube_hierarchy_node","cube_hierarchy",
    "cube_group_enumeration","cube_group","cube","cube_structure",
    "framework_variable_set","variable_set_enumeration","variable_set","variable",
    "subdomain_enumeration","subdomain","member_hierarchy_node","member_hierarchy",
    "member","domain","facet_enumeration","facet_collection","framework",
    "maintenance_agency",
]


# ═══════════════════════════════════════════════════════════════════════
# Loader
# ═══════════════════════════════════════════════════════════════════════

def prep_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert bool columns from numpy.bool_ to Python object (True/False/None)
    so DuckDB's DataFrame import doesn't choke on numpy scalar types.
    """
    for col in df.columns:
        if str(df[col].dtype) in ("bool", "boolean"):
            df[col] = df[col].astype(object).where(df[col].notna(), None)
    return df


def ctas(con, table: str, view: str, col_exprs: list[tuple[str, str]]) -> int:
    """CREATE OR REPLACE TABLE table AS SELECT col_exprs FROM view."""
    select_parts = ", ".join(
        f"NULL AS {dest}" if src == "NULL"
        else f'TRY_CAST({src} AS VARCHAR) AS {dest}' if src in ('"ORDER"',)
        else f"{src} AS {dest}"
        for dest, src in col_exprs
    )
    # Use simple column aliasing — avoid CAST for most; bool/int handled by prep_df
    select_parts = ", ".join(
        f"CAST(NULL AS VARCHAR) AS {dest}" if src == "CAST_NULL"
        else f"NULL AS {dest}" if src == "NULL"
        else f"{src} AS {dest}"
        for dest, src in col_exprs
    )
    sql = f"CREATE OR REPLACE TABLE {table} AS SELECT {select_parts} FROM {view}"
    try:
        con.execute(sql)
        n = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        log.info("%-40s  %d rows", table, n)
        return n
    except Exception as e:
        log.error("%-40s  FAILED: %s", table, e)
        return 0


def load_all(con, sheets: dict):
    for table, sheet, col_exprs in TABLE_SPECS:
        if sheet not in sheets:
            log.warning("%-40s  sheet '%s' not found — skipping", table, sheet)
            continue
        df = prep_df(sheets[sheet].copy())
        view = f"_v_{table}"
        con.register(view, df)
        ctas(con, table, view, col_exprs)
        con.unregister(view)

    # cube.cube_group_id — denormalise from cube_group_enumeration
    if "cube_group_enumeration" in [t for t,_,_ in TABLE_SPECS]:
        try:
            con.execute("""
                UPDATE cube SET cube_group_id = (
                    SELECT CAST(cge.cube_group_id AS VARCHAR)
                    FROM cube_group_enumeration cge
                    WHERE cge.cube_id = cube.cube_id LIMIT 1
                )
            """)
            n = con.execute("SELECT count(*) FROM cube WHERE cube_group_id IS NOT NULL").fetchone()[0]
            log.info("%-40s  %d cubes updated", "cube.cube_group_id (denorm)", n)
        except Exception as e:
            log.warning("cube_group_id denorm failed: %s", e)

    # legal_reference — needs synthesised PK
    if "LEGAL_REFERENCE" in sheets:
        df = prep_df(sheets["LEGAL_REFERENCE"].copy())
        df["legal_reference_id"] = (
            df["LEGAL_TEXT_ID"].fillna("").astype(str)
            + "__"
            + df["OBJECT_ID"].fillna("").astype(str)
        )
        con.register("_v_legal_ref", df)
        ctas(con, "legal_reference", "_v_legal_ref", [
            ("legal_reference_id", "legal_reference_id"),
            ("object_type",  "OBJECT_TYPE"),
            ("object_id",    "OBJECT_ID"),
            ("legal_text_id","LEGAL_TEXT_ID"),
            ("article",      "ARTICLE"),
            ("valid_from",   "VALID_FROM"),
            ("valid_to",     "VALID_TO"),
        ])
        con.unregister("_v_legal_ref")


# ═══════════════════════════════════════════════════════════════════════
# Validation
# ═══════════════════════════════════════════════════════════════════════

CHECKS = [
    ("Cube counts by type",
     "SELECT cube_type, count(*) n FROM cube GROUP BY cube_type ORDER BY n DESC"),
    ("CSI role distribution",
     "SELECT role, count(*) n FROM cube_structure_item GROUP BY role ORDER BY n DESC"),
    ("Transformation rules by type + layer",
     """SELECT transformation_type, source_layer, destination_layer, count(*) n
        FROM logical_transformation_rule
        GROUP BY transformation_type, source_layer, destination_layer ORDER BY n DESC"""),
    ("Subdomain + enumeration",
     """SELECT (SELECT count(*) FROM subdomain) subdomains,
               (SELECT count(*) FROM subdomain_enumeration) enum_bindings"""),
    ("Member hierarchy",
     "SELECT count(DISTINCT member_hierarchy_id) hierarchies, count(*) nodes FROM member_hierarchy_node"),
    ("CUBE_LINK → LTR",
     "SELECT count(*) total, count(logical_transformation_rule_id) with_ltr FROM cube_link"),
    ("Column-level link + member translation",
     """SELECT (SELECT count(*) FROM cube_structure_item_link) csil,
               (SELECT count(*) FROM member_link) ml"""),
    ("A-role companion coverage",
     """SELECT count(*) a_total, count(attribute_associated_variable) with_companion
        FROM cube_structure_item WHERE role='A'"""),
    ("Orphan CSI→variable",
     """SELECT count(*) orphan FROM cube_structure_item
        WHERE NOT EXISTS (SELECT 1 FROM variable v WHERE v.variable_id=cube_structure_item.variable_id)"""),
    ("Orphan variable→domain",
     """SELECT count(*) orphan FROM variable
        WHERE domain_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM domain d WHERE d.domain_id=variable.domain_id)"""),
    ("Sample mapping lookup — Collateral + monetary",
     """SELECT c.name entity, csi.role, v.name AS var_name, d.data_type
        FROM cube c
        JOIN cube_structure_item csi ON csi.cube_structure_id = c.cube_structure_id
        JOIN variable v              ON v.variable_id         = csi.variable_id
        JOIN domain d                ON d.domain_id           = v.domain_id
        WHERE c.cube_type='LDM' AND c.name ILIKE '%collateral%'
          AND d.data_type ILIKE '%number%'
        ORDER BY csi.role, v.name LIMIT 5"""),
    ("AnaCredit GEN chain via cube_link",
     """SELECT ltr.transformation_type, ltr.source_layer, ltr.destination_layer,
               cl.primary_cube_id, cl.foreign_cube_id
        FROM logical_transformation_rule ltr
        JOIN cube_link cl ON cl.logical_transformation_rule_id = ltr.logical_transformation_rule_id
        WHERE ltr.transformation_type = 'GEN' LIMIT 5"""),
]


def run_validation(con):
    log.info("─── Validation ─────────────────────────────────────")
    for label, sql in CHECKS:
        try:
            df = con.execute(sql).fetchdf()
            log.info("%s:\n%s", label, df.to_string(index=False))
        except Exception as e:
            log.warning("%s FAILED: %s", label, e)


# ═══════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Load complete BIRD KB into DuckDB")
    parser.add_argument("--db",              required=True)
    parser.add_argument("--multi-framework", required=True)
    parser.add_argument("--no-drop",         action="store_true")
    parser.add_argument("--no-validate",     action="store_true")
    args = parser.parse_args()

    src = Path(args.multi_framework)
    if not src.exists():
        log.error("Not found: %s", src); sys.exit(1)

    t0 = time.time()
    log.info("Reading workbook (single pass)…")
    xl = pd.ExcelFile(str(src), engine="openpyxl")
    sheets = {name: xl.parse(name) for name in xl.sheet_names}
    log.info("Parsed %d sheets in %.1fs", len(sheets), time.time()-t0)

    con = duckdb.connect(args.db)

    if not args.no_drop:
        log.info("Dropping tables…")
        for tbl in DROP_ORDER:
            con.execute(f"DROP TABLE IF EXISTS {tbl}")

    log.info("Creating schema (30 tables)…")
    con.execute(DDL)

    log.info("Loading tables…")
    load_all(con, sheets)

    if not args.no_validate:
        run_validation(con)

    con.close()
    log.info("Completed in %.1fs  →  %s", time.time()-t0, args.db)


if __name__ == "__main__":
    main()
