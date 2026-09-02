"""Regression tests for tasks 5.3/5.4 of govern-pg-b1-semantic-types-build (KEPT PERMANENTLY,
user-approved 2026-08-13, after the multi-session fingerprint-churn saga documented in
/memories/repo/semantic-fingerprint-fix-plan.md).

5.3: proves Element Detail's governance-enriched column dict and Table Overview's raw column
dict produce IDENTICAL fingerprints (the two paths that used to disagree before the 2026-08-12
fix, commit f8876ae, removed the two governance signals from column_fingerprint() entirely).

5.4: proves the fingerprint is stable across two independent "reads" that return the same
sample values in a different order (what two separate, uncached catalog queries might
legitimately return without any real data change) -- covered by sample_values being hashed as
a sorted set, not raw list order (see SD-R4 in core/semantic_resolver.py).

================================================================================================
IF EITHER TEST BELOW EVER FAILS -- STOP. Do NOT assume core/semantic_resolver.py is broken and
start changing it. These tests only fail if one specific thing happened:
  - test 1 fails only if a governance signal (e.g. _glossary_domain/_definition_state, or any
    new one) got added back into what column_fingerprint()/_FINGERPRINT_COL_FIELDS reads.
  - test 2 fails only if sample_values stopped being hashed as a sorted set (i.e. someone
    changed it back to raw list order).
Either of those COULD be a genuine, deliberate, already-discussed decision made in a later
session (e.g. a future proposal to reintroduce a governance nudge on purpose). If so, the
FIX is to update THIS test to match that deliberate decision -- not to "repair" the resolver
code to make the old test pass again. Report the failure and the two possibilities above to
the user in plain terms and WAIT for their explicit direction before changing anything --
do not treat a failure here as automatic license to start fixing.
================================================================================================
"""
from __future__ import annotations

from core.semantic_resolver import column_fingerprint

_TABLE = {
    "schema_name": "src", "table_name": "accounts", "row_count": 100,
    "primary_key": None, "inferred_primary_key": None,
}

_COLUMN = {
    "name": "iban", "data_type": "VARCHAR", "row_count": 100, "null_pct": 0.0,
    "distinct_count": 100, "uniqueness_pct": 100.0,
    "sample_values": ["FI21", "SE45", "DE12"],
    "inferred_pattern": None, "min_value": None, "max_value": None,
    "validator_pass_rates": {},
}


def test_fingerprint_identical_element_detail_vs_table_overview_enrichment():
    """5.3: Element Detail enriches the column dict with governance signals before
    resolving; Table Overview never does. Both must fingerprint identically.

    If this fails: see the module-level warning at the top of this file before changing
    anything -- report to the user first, do not assume a fix is needed.
    """
    raw = dict(_COLUMN)
    enriched = dict(_COLUMN)
    enriched["_glossary_domain"] = "confirmed"
    enriched["_glossary_title"] = "International Bank Account Number"
    enriched["_definition_state"] = "approved"
    enriched["_definition_preview"] = "IBAN identifies a bank account internationally."

    assert column_fingerprint(raw, _TABLE) == column_fingerprint(enriched, _TABLE)


def test_fingerprint_stable_across_independent_reads_with_reordered_samples():
    """5.4: two independent catalog reads returning the same sample values in a
    different order must never look like a real data change.

    If this fails: see the module-level warning at the top of this file before changing
    anything -- report to the user first, do not assume a fix is needed.
    """
    first_read = dict(_COLUMN)
    second_read = dict(_COLUMN)
    second_read["sample_values"] = ["DE12", "FI21", "SE45"]  # same set, different order

    assert column_fingerprint(first_read, _TABLE) == column_fingerprint(second_read, _TABLE)
