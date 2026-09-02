from pathlib import Path

import pytest

from core.semantic_resolver import (
    RESOLVER_VERSION,
    SemanticResolver,
    conflict_finding,
    domain_role_to_legacy_bucket,
)
from core.semantic_type_store import SemanticTypeStore
from tests._pg_semantic_type_isolation import sandbox_semantic_type_tests

_sandbox_db, _sandbox_wipe = sandbox_semantic_type_tests()


def _resolver(tmp_path: Path) -> SemanticResolver:
    return SemanticResolver(store=SemanticTypeStore(tmp_path / "semantic_types.yaml"))


def test_resolver_version_is_ten():
    assert RESOLVER_VERSION == "10"


def test_high_confidence_iban_resolves_without_ai(tmp_path: Path):
    resolver = _resolver(tmp_path)
    record = resolver.resolve_column(
        source="banking",
        schema="src",
        table="accounts",
        column={
            "name": "iban",
            "data_type": "VARCHAR",
            "row_count": 2,
            "distinct_count": 2,
            "sample_values": ["GB82WEST12345698765432", "DE89370400440532013000"],
        },
        table_facts={"table_name": "accounts", "row_count": 2, "primary_key": []},
    )

    assert record["type_id"] == "natural_iban"
    assert record["domain_role"] == "natural_id"
    assert record["confidence"] >= 0.85
    assert record["source"] == "rule"
    assert not record["type_value_conflict"]


def test_ambiguous_numeric_resolves_unresolved_and_queues(tmp_path: Path):
    store = SemanticTypeStore(tmp_path / "semantic_types.yaml")
    resolver = SemanticResolver(store=store)
    record = resolver.resolve_column(
        source="banking",
        schema="src",
        table="accounts",
        column={
            "name": "value",
            "data_type": "DOUBLE",
            "row_count": 10,
            "distinct_count": 10,
            "sample_values": [1.2, 3.4, 5.6],
        },
        table_facts={"table_name": "accounts", "row_count": 10, "primary_key": []},
    )

    assert record["type_id"] == "unresolved"


def test_obvious_balance_resolves_as_monetary_measure(tmp_path: Path):
    resolver = _resolver(tmp_path)
    record = resolver.resolve_column(
        source="banking",
        schema="src",
        table="accounts",
        column={
            "name": "balance",
            "data_type": "DOUBLE",
            "row_count": 3,
            "distinct_count": 3,
            "sample_values": [100.0, 250.5, -10.0],
        },
        table_facts={"table_name": "accounts", "row_count": 3, "primary_key": []},
    )

    # 'balance' type collapsed into 'monetary_amount' in the redesigned vocabulary
    assert record["type_id"] == "monetary_amount"
    assert record["domain_role"] == "measure"
    assert record["confidence"] >= 0.60


def test_date_in_varchar_resolves_with_storage_mismatch(tmp_path: Path):
    resolver = _resolver(tmp_path)
    record = resolver.resolve_column(
        source="banking",
        schema="src",
        table="payments",
        column={
            "name": "datetime",
            "data_type": "VARCHAR",
            "row_count": 2,
            "distinct_count": 2,
            "sample_values": ["05112021", "06112021"],
        },
        table_facts={"table_name": "payments", "row_count": 2, "primary_key": []},
    )

    assert record["type_id"] == "date"
    assert record["domain_role"] == "temporal"
    assert record["confidence"] >= 0.85
    assert record["type_datatype_difference"] is True
    assert record["format"] == "undecided"
    assert record["type_value_conflict"] is False


def test_numeric_date_leading_pair_forces_ddmmyyyy_without_ai(tmp_path: Path):
    resolver = _resolver(tmp_path)
    record = resolver.resolve_column(
        source="banking",
        schema="src",
        table="payments",
        column={
            "name": "value_date",
            "data_type": "VARCHAR",
            "row_count": 2,
            "distinct_count": 2,
            "sample_values": ["25112021", "26112021"],
        },
        table_facts={"table_name": "payments", "row_count": 2, "primary_key": []},
    )

    assert record["type_id"] == "date"
    assert record["format"] == "DDMMYYYY"
    assert record["source"] == "rule"


def test_account_entity_profile_resolves_without_ai(tmp_path: Path):
    resolver = _resolver(tmp_path)
    result = resolver.resolve_table(
        source="banking",
        schema="src",
        table={
            "schema_name": "src",
            "table_name": "accounts",
            "row_count": 3,
            "primary_key": ["account_id"],
            "columns": [
                {"name": "account_id", "data_type": "VARCHAR", "row_count": 3, "distinct_count": 3, "sample_values": ["A1", "A2", "A3"]},
                {"name": "balance", "data_type": "DOUBLE", "row_count": 3, "distinct_count": 3, "sample_values": [1, 2, 3]},
                {"name": "currency", "data_type": "VARCHAR", "row_count": 3, "distinct_count": 2, "sample_values": ["EUR", "USD"]},
                {"name": "account_type", "data_type": "VARCHAR", "row_count": 3, "distinct_count": 2, "sample_values": ["CURRENT", "SAVINGS"]},
            ],
        },
        include_ai=False,
    )

    assert result["entity"]["entity"] == "Account"
    assert result["entity"]["source"] == "rule"


def test_counterparty_entity_context_boosts_counterparty_identifier(tmp_path: Path):
    resolver = _resolver(tmp_path)
    record = resolver.resolve_column(
        source="banking",
        schema="src",
        table="counterparties",
        column={"name": "cpty_ref", "data_type": "VARCHAR", "row_count": 3, "distinct_count": 3, "sample_values": ["C1", "C2", "C3"]},
        table_facts={"table_name": "counterparties", "row_count": 3, "primary_key": []},
        entity_context="Counterparty",
    )

    # generic identifier now defaults to 'surrogate_systemid' (Natural/Surrogate split)
    assert record["type_id"] == "surrogate_systemid"
    # T3 tier (name-only): 0.45 base + entity adjustment → below the 0.60 floor
    assert record["confidence"] >= 0.45
    assert record["confidence"] < 0.60


def test_accepted_sibling_does_not_influence_later_resolve(tmp_path: Path):
    """Learned naming priors were removed (2026-08-13) — an accepted sibling no longer
    nudges a same-named column's confidence, and emits no 'prior' evidence."""
    store = SemanticTypeStore(tmp_path / "semantic_types.yaml")
    resolver = SemanticResolver(store=store)
    store.set_proposed(
        source="banking",
        schema="src",
        table="counterparties",
        column="counterparty_id",
        type_id="surrogate_systemid",
        domain_role="surrogate_id",
        confidence=0.86,
    )
    store.accept("banking", "src", "counterparties", "counterparty_id", accepted_by="tester")

    record = resolver.resolve_column(
        source="banking",
        schema="src",
        table="counterparties",
        column={"name": "counterparty_ref", "data_type": "VARCHAR", "row_count": 3, "distinct_count": 3, "sample_values": ["C1", "C2", "C3"]},
        table_facts={"table_name": "counterparties", "row_count": 3, "primary_key": []},
    )

    assert record["type_id"] == "surrogate_systemid"
    assert not any(evidence["kind"] == "prior" for evidence in record["evidence"])


def _shape_evidence(record: dict):
    return [
        e for e in record["evidence"]
        if e.get("kind") == "shape"
        and "consistent length and character pattern" in (e.get("signal") or "")
    ]


def test_identifier_pk_gets_shape_consistency_evidence(tmp_path: Path):
    resolver = _resolver(tmp_path)
    record = resolver.resolve_column(
        source="banking",
        schema="src",
        table="accounts",
        column={
            "name": "account_id",
            "data_type": "VARCHAR",
            "row_count": 5,
            "distinct_count": 5,
            "sample_values": ["ACC0000001", "ACC0000002", "ACC0000003", "ACC0000004", "ACC0000005"],
        },
        table_facts={"table_name": "accounts", "row_count": 5, "primary_key": ["account_id"]},
    )

    assert record["domain_role"] in {"key", "surrogate_id", "natural_id"}
    shape = _shape_evidence(record)
    assert shape, record["evidence"]
    # Corroboration only — weak weight, and never surfaced as a scoring adjustment.
    assert shape[0]["weight"] == "weak"
    adj_labels = [a.get("label", "") for a in record.get("score_breakdown", {}).get("adjustments", [])]
    assert all("consistent length" not in lbl.lower() and "shape" not in lbl.lower() for lbl in adj_labels)


def test_hex_hash_identifier_reports_fixed_length_not_pattern(tmp_path: Path):
    # 16-char hex ids (like the real account_id): length is perfectly consistent
    # but the letter/digit mask varies per value. We should surface the LENGTH
    # signal, not claim a shared character pattern.
    resolver = _resolver(tmp_path)
    record = resolver.resolve_column(
        source="banking",
        schema="src",
        table="accounts",
        column={
            "name": "account_id",
            "data_type": "VARCHAR",
            "row_count": 5,
            "distinct_count": 5,
            "sample_values": [
                "D393709EF0254B3C", "B17D7C8BCC054E48", "41E2F0EFDF8E4C60",
                "4AD4447522764004", "7C5D4EF02EDB48C0",
            ],
        },
        table_facts={"table_name": "accounts", "row_count": 5, "primary_key": ["account_id"]},
    )

    assert record["domain_role"] in {"key", "surrogate_id", "natural_id"}
    shape = [e for e in record["evidence"] if e.get("kind") == "shape"]
    assert shape, record["evidence"]
    assert "fixed value length" in shape[0]["signal"]
    assert "16" in shape[0]["signal"]
    # Must NOT overclaim a shared character pattern when the mask varies.
    assert "character pattern" not in shape[0]["signal"]


def test_shape_evidence_attaches_when_uniqueness_is_low(tmp_path: Path):
    # A foreign-key-like identifier: consistent shape but NOT unique and not a PK.
    # This is exactly where shape consistency earns its keep — uniqueness can't help.
    resolver = _resolver(tmp_path)
    record = resolver.resolve_column(
        source="banking",
        schema="src",
        table="transactions",
        column={
            "name": "counterparty_id",
            "data_type": "VARCHAR",
            "row_count": 6,
            "distinct_count": 2,
            "sample_values": ["CP0001", "CP0002", "CP0001", "CP0002", "CP0001", "CP0002"],
        },
        table_facts={"table_name": "transactions", "row_count": 6, "primary_key": []},
    )

    assert record["domain_role"] in {"surrogate_id", "natural_id", "key"}
    assert _shape_evidence(record), record["evidence"]


def test_free_text_column_gets_no_shape_consistency_evidence(tmp_path: Path):
    resolver = _resolver(tmp_path)
    record = resolver.resolve_column(
        source="banking",
        schema="src",
        table="accounts",
        column={
            "name": "account_holder_name",
            "data_type": "VARCHAR",
            "row_count": 4,
            "distinct_count": 4,
            "sample_values": ["Jane Doe", "Christopher Alexander", "Li Wei", "Ana"],
        },
        table_facts={"table_name": "accounts", "row_count": 4, "primary_key": []},
    )

    assert not _shape_evidence(record)


def test_name_value_conflict_emits_assessment_shape(tmp_path: Path):
    resolver = _resolver(tmp_path)
    record = resolver.resolve_column(
        source="banking",
        schema="src",
        table="accounts",
        column={
            "name": "iban",
            "data_type": "VARCHAR",
            "row_count": 2,
            "distinct_count": 2,
            "sample_values": ["GB82WEST12345698765433", "DE89370400440532013001"],
        },
        table_facts={"table_name": "accounts", "row_count": 2, "primary_key": []},
    )
    finding = conflict_finding(record, column="iban")

    assert record["type_value_conflict"] is True
    assert record["confidence"] < 0.85
    assert finding["scope"] == "column"
    assert finding["target"] == "iban"
    assert finding["severity"] == "attention"
    assert finding["category"] == "validity"
    assert finding["title"] == "Type/value conflict"
    assert finding["source"] == "rule"


def test_domain_role_to_legacy_bucket_mapping_is_explicit():
    assert domain_role_to_legacy_bucket("key") == "identifier"
    assert domain_role_to_legacy_bucket("identifier") == "identifier"
    assert domain_role_to_legacy_bucket("natural_id") == "identifier"
    assert domain_role_to_legacy_bucket("surrogate_id") == "identifier"
    assert domain_role_to_legacy_bucket("code") == "coded"
    assert domain_role_to_legacy_bucket("temporal") == "date"
    assert domain_role_to_legacy_bucket("measure") == "monetary"
    assert domain_role_to_legacy_bucket("dimension") == "other"
    assert domain_role_to_legacy_bucket("descriptive") == "other"
    assert domain_role_to_legacy_bucket("technical") == "other"
    assert domain_role_to_legacy_bucket("unresolved") == "other"


# ── Value-structure signals (Natural/Surrogate split, ST-NS) ───────────────

def test_system_generated_code_suggests_surrogate_identifier(tmp_path: Path):
    """An alphanumeric column with no name token and no known format, but a
    consistent system-id shape (prefix + digits, no whitespace, unique), is
    suggested as surrogate_systemid from value structure."""
    resolver = _resolver(tmp_path)
    record = resolver.resolve_column(
        source="banking",
        schema="src",
        table="events",
        column={
            "name": "marker",
            "data_type": "VARCHAR",
            "row_count": 5,
            "distinct_count": 5,
            "null_count": 0,
            "sample_values": ["SYS236176M", "SYS236177K", "SYS236180P", "SYS236181Q", "SYS236190Z"],
        },
        table_facts={"table_name": "events", "row_count": 5, "primary_key": []},
    )
    assert record["type_id"] == "surrogate_systemid"
    assert record["domain_role"] == "surrogate_id"
    assert record["confidence"] < 0.60
    assert any(e["kind"] == "shape" for e in record["evidence"])


def test_name_column_with_digits_is_not_classified_as_name(tmp_path: Path):
    """A column named like a name but holding alphanumeric/digit values must not
    be classified as a personal/entity Name (char-type guard)."""
    resolver = _resolver(tmp_path)
    record = resolver.resolve_column(
        source="banking",
        schema="src",
        table="parties",
        column={
            "name": "company_name",
            "data_type": "VARCHAR",
            "row_count": 4,
            "distinct_count": 4,
            "null_count": 0,
            "sample_values": ["ORG12", "ORG34", "ORG56", "ORG78"],
        },
        table_facts={"table_name": "parties", "row_count": 4, "primary_key": []},
    )
    assert record["type_id"] != "name"


def test_org_name_with_incidental_digits_stays_name(tmp_path: Path):
    """Organisation names legitimately carry digits ("3M", "A1 Trading",
    "Bank24"). The name-guard must NOT reject them — only uniform code shapes."""
    resolver = _resolver(tmp_path)
    record = resolver.resolve_column(
        source="banking",
        schema="src",
        table="parties",
        column={
            "name": "company_name",
            "data_type": "VARCHAR",
            "row_count": 4,
            "distinct_count": 4,
            "null_count": 0,
            "sample_values": ["3M", "A1 Trading Ltd", "Bank24", "Global Holdings"],
        },
        table_facts={"table_name": "parties", "row_count": 4, "primary_key": []},
    )
    assert record["type_id"] == "name"


def test_uuid_values_resolve_surrogate_uuid(tmp_path: Path):
    """Canonical dashed UUID values validate to surrogate_uuid at high confidence,
    even when the column name carries no uuid/id token."""
    resolver = _resolver(tmp_path)
    record = resolver.resolve_column(
        source="banking",
        schema="src",
        table="events",
        column={
            "name": "external_ref",
            "data_type": "VARCHAR",
            "row_count": 4,
            "distinct_count": 4,
            "null_count": 0,
            "sample_values": [
                "550e8400-e29b-41d4-a716-446655440000",
                "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
                "6ba7b811-9dad-11d1-80b4-00c04fd430c8",
                "123e4567-e89b-12d3-a456-426614174000",
            ],
        },
        table_facts={"table_name": "events", "row_count": 4, "primary_key": []},
    )
    assert record["type_id"] == "surrogate_uuid"
    assert record["domain_role"] == "surrogate_id"
    assert record["confidence"] >= 0.85


def test_fixed_length_hex_suggests_surrogate_hash(tmp_path: Path):
    """A column with no id/hash name token whose values are all fixed-length hex
    (SHA-256, 64 chars) is a SUGGESTION-level surrogate_hash — shape only."""
    resolver = _resolver(tmp_path)
    record = resolver.resolve_column(
        source="banking",
        schema="src",
        table="events",
        column={
            "name": "token",
            "data_type": "VARCHAR",
            "row_count": 3,
            "distinct_count": 3,
            "null_count": 0,
            "sample_values": [
                "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
                "60303ae22b998861bce3b28f33eec1be758a213c86c93c076dbe9f558c11c752",
                "a1fce4363854ff888cff4b8e7875d600c2682390412a8cf79b37d0b11148b0fa",
            ],
        },
        table_facts={"table_name": "events", "row_count": 3, "primary_key": []},
    )
    assert record["type_id"] == "surrogate_hash"
    assert record["domain_role"] == "surrogate_id"
    assert record["confidence"] < 0.60


# ── Distribution-first path ────────────────────────────────────────────────

def test_low_cardinality_no_name_match_resolves_reference_code(tmp_path: Path):
    """accounting_standard_code with ['IFRS','GAAP'] — no name token in vocab."""
    resolver = _resolver(tmp_path)
    record = resolver.resolve_column(
        source="banking",
        schema="src",
        table="accountingsummary",
        column={
            "name": "accounting_standard_code",
            "data_type": "VARCHAR",
            "row_count": 5000,
            "distinct_count": 2,
            "sample_values": ["IFRS", "GAAP"],
        },
        table_facts={"table_name": "accountingsummary", "row_count": 5000, "primary_key": []},
    )
    assert record["type_id"] == "reference_code"
    assert record["domain_role"] == "code"
    assert record["confidence"] >= 0.82


def test_string_rate_index_not_blocked_by_numeric_rate_type(tmp_path: Path):
    """A string column named 'floating_rate_index' name-matches the numeric `rate`
    type, but rate is primitive-incompatible and must NOT block the code path.
    Benchmark indices (EURIBOR_3M, SOFR, …) resolve as reference_code."""
    resolver = _resolver(tmp_path)
    record = resolver.resolve_column(
        source="banking",
        schema="src",
        table="instruments",
        column={
            "name": "floating_rate_index",
            "data_type": "VARCHAR",
            "row_count": 4000,
            "distinct_count": 4,
            "sample_values": ["EURIBOR_3M", "STIBOR_3M", "SOFR", "EURIBOR_6M"],
        },
        table_facts={"table_name": "instruments", "row_count": 4000, "primary_key": []},
    )
    assert record["type_id"] == "reference_code"
    assert record["domain_role"] == "code"


def test_strike_price_resolves_monetary(tmp_path: Path):
    """A numeric column named 'strike_price' resolves to monetary_amount via the
    newly added price/strike name tokens."""
    resolver = _resolver(tmp_path)
    record = resolver.resolve_column(
        source="banking",
        schema="src",
        table="options",
        column={
            "name": "strike_price",
            "data_type": "DOUBLE",
            "row_count": 1000,
            "distinct_count": 800,
            "sample_values": [100.50, 105.25, 98.75, 110.00],
        },
        table_facts={"table_name": "options", "row_count": 1000, "primary_key": []},
    )
    assert record["type_id"] == "monetary_amount"
    """Source_System='Manual' (constant, 1 distinct) — no name token match."""
    resolver = _resolver(tmp_path)
    record = resolver.resolve_column(
        source="banking",
        schema="src",
        table="accountingsummary",
        column={
            "name": "source_system",
            "data_type": "VARCHAR",
            "row_count": 10000,
            "distinct_count": 1,
            "sample_values": ["Manual"],
        },
        table_facts={"table_name": "accountingsummary", "row_count": 10000, "primary_key": []},
    )
    assert record["type_id"] == "reference_code"
    assert record["confidence"] >= 0.88


def test_currency_column_with_low_cardinality_still_reaches_currency_code(tmp_path: Path):
    """currency (name token matches) should reach currency_code, not reference_code."""
    resolver = _resolver(tmp_path)
    record = resolver.resolve_column(
        source="banking",
        schema="src",
        table="accounts",
        column={
            "name": "currency",
            "data_type": "VARCHAR",
            "row_count": 800,
            "distinct_count": 5,
            "sample_values": ["EUR", "USD", "CHF"],
        },
        table_facts={"table_name": "accounts", "row_count": 800, "primary_key": []},
    )
    # Name token "currency" matches currency_code in vocab → distribution path must yield
    assert record["type_id"] == "currency_code"


def test_numeric_low_cardinality_does_not_trigger_distribution_path(tmp_path: Path):
    """A DOUBLE column with few distinct values should NOT become reference_code."""
    resolver = _resolver(tmp_path)
    record = resolver.resolve_column(
        source="banking",
        schema="src",
        table="accounts",
        column={
            "name": "risk_weight",
            "data_type": "DOUBLE",
            "row_count": 1000,
            "distinct_count": 4,
            "sample_values": [0.0, 0.2, 0.5, 1.0],
        },
        table_facts={"table_name": "accounts", "row_count": 1000, "primary_key": []},
    )
    assert record["type_id"] != "reference_code"


# ── SD-R1: one field of truth (B1) ──────────────────────────────────────────

def _tier_matches_breakdown(record: dict) -> bool:
    """Invariant: when a record carries a score_breakdown, the top-level `tier`
    equals `score_breakdown.tier`. Guards against a future path dropping `tier`."""
    breakdown = record.get("score_breakdown")
    if not breakdown:
        return True
    return record.get("tier") == breakdown.get("tier")


def test_field_of_truth_tier_matches_score_breakdown_all_paths(tmp_path: Path):
    """Every record-producing path must persist a top-level `tier` equal to
    `score_breakdown.tier` — main scorer, distribution-first, and varchar-date."""
    resolver = _resolver(tmp_path)
    columns = [
        # T1 validator (main scorer)
        {"name": "iban", "data_type": "VARCHAR", "row_count": 2, "distinct_count": 2,
         "sample_values": ["GB82WEST12345698765432", "DE89370400440532013000"]},
        # Distribution-first shortcut → reference_code (previously persisted tier 0)
        {"name": "accounting_standard_code", "data_type": "VARCHAR", "row_count": 5000,
         "distinct_count": 2, "sample_values": ["IFRS", "GAAP"]},
        # varchar-date shortcut (previously persisted tier 0)
        {"name": "value_date", "data_type": "VARCHAR", "row_count": 2, "distinct_count": 2,
         "sample_values": ["25112021", "26112021"]},
        # Monetary (main scorer, shape/structural)
        {"name": "balance", "data_type": "DOUBLE", "row_count": 3, "distinct_count": 3,
         "sample_values": [100.0, 250.5, -10.0]},
    ]
    for column in columns:
        record = resolver.resolve_column(
            source="banking", schema="src", table="t", column=column,
            table_facts={"table_name": "t", "row_count": column["row_count"], "primary_key": []},
        )
        assert _tier_matches_breakdown(record), (
            f"{column['name']}: tier {record.get('tier')} != "
            f"score_breakdown.tier {(record.get('score_breakdown') or {}).get('tier')}"
        )


def test_distribution_first_description_persists_tier_two(tmp_path: Path):
    """Regression for the §0 forcing case: a low-cardinality `description` column
    resolves via distribution-first to reference_code at confidence 0.929, and
    must now persist a top-level `tier == 2` (not the buggy 0) so the badge and
    the receipt agree. No confidence change — only the stored tier is corrected."""
    resolver = _resolver(tmp_path)
    record = resolver.resolve_column(
        source="banking",
        schema="src",
        table="collateral",
        column={
            "name": "description",
            "data_type": "VARCHAR",
            "row_count": 110,
            "distinct_count": 1,
            "sample_values": ["active"],
        },
        table_facts={"table_name": "collateral", "row_count": 110, "primary_key": []},
    )
    assert record["type_id"] == "reference_code"
    assert record["confidence"] == pytest.approx(0.929, abs=1e-3)
    assert record["tier"] == 2
    assert record["score_breakdown"]["tier"] == 2
    assert _tier_matches_breakdown(record)


def test_varchar_date_shortcut_persists_tier_one(tmp_path: Path):
    """The numeric-varchar-date shortcut must also lift its tier to the top level."""
    resolver = _resolver(tmp_path)
    record = resolver.resolve_column(
        source="banking",
        schema="src",
        table="payments",
        column={
            "name": "value_date",
            "data_type": "VARCHAR",
            "row_count": 2,
            "distinct_count": 2,
            "sample_values": ["25112021", "26112021"],
        },
        table_facts={"table_name": "payments", "row_count": 2, "primary_key": []},
    )
    assert record["type_id"] == "date"
    assert record["tier"] == 1
    assert record["score_breakdown"]["tier"] == 1
    assert _tier_matches_breakdown(record)


def test_version_bump_reresolves_proposed_and_keeps_accepted_sticky(tmp_path: Path):
    """A cached, unaccepted record at an older resolver_version re-resolves and
    heals to RESOLVER_VERSION; an ACCEPTED record stays sticky (untouched)."""
    store = SemanticTypeStore(tmp_path / "semantic_types.yaml")
    resolver = SemanticResolver(store=store)
    column = {
        "name": "iban", "data_type": "VARCHAR", "row_count": 2, "distinct_count": 2,
        "sample_values": ["GB82WEST12345698765432", "DE89370400440532013000"],
    }
    table_facts = {"table_name": "accounts", "row_count": 2, "primary_key": []}

    first = resolver.resolve_column(source="banking", schema="src", table="accounts",
                                    column=column, table_facts=table_facts)
    assert first["resolver_version"] == RESOLVER_VERSION == "10"

    # Simulate the same record cached under the previous version (fingerprint kept).
    stale = store.get("banking", "src", "accounts", "iban")
    stale["resolver_version"] = "7"
    store.set_record(stale, preserve_disposed=False)

    healed = resolver.resolve_column(source="banking", schema="src", table="accounts",
                                     column=column, table_facts=table_facts)
    assert healed["resolver_version"] == "10"  # re-scored despite matching fingerprint

    # Accepted decisions are sticky and survive the version bump.
    store.accept("banking", "src", "accounts", "iban", accepted_by="tester")
    after = resolver.resolve_column(source="banking", schema="src", table="accounts",
                                    column=column, table_facts=table_facts)
    assert after["accepted_at"]


# ── SD-R3a: entity-context pre-pass landmine guard ───────────────────────────

def test_entity_context_adjustment_survives_subject_removal(tmp_path: Path):
    """The entity-context adjustment (+0.03) is produced by the hardcoded names-only
    entity pre-pass (`resolve_entity` / `_ENTITY_PROFILES`), NOT by Semantic Subject.
    Deleting Subject must leave it firing byte-identically. A currency_code column in
    an Account-entity table earns exactly the +0.03 'Account entity context' bonus."""
    resolver = _resolver(tmp_path)
    record = resolver.resolve_column(
        source="banking",
        schema="src",
        table="accounts",
        column={
            "name": "currency",
            "data_type": "VARCHAR",
            "row_count": 3,
            "distinct_count": 2,
            "sample_values": ["EUR", "USD"],
        },
        table_facts={"table_name": "accounts", "row_count": 3, "primary_key": []},
        entity_context="Account",
    )
    adjustments = record["score_breakdown"]["adjustments"]
    account_adj = [a for a in adjustments if a["label"] == "Account entity context"]
    assert account_adj, f"entity-context adjustment missing: {adjustments}"
    assert account_adj[0]["points"] == 0.03


def test_resolve_entity_prepass_still_resolves_account(tmp_path: Path):
    """The entity pre-pass itself is intact after Subject removal — an Account-shaped
    table still resolves to the Account entity that feeds entity_context."""
    resolver = _resolver(tmp_path)
    entity = resolver.resolve_entity({
        "table_name": "accounts",
        "columns": [
            {"name": "account_id"}, {"name": "balance"},
            {"name": "currency"}, {"name": "account_type"},
        ],
    })
    assert entity["entity"] == "Account"

