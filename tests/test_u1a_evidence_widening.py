"""Evidence widening (flag-ON paths) + U1b flip/version-bump coverage.

As of U1b, ``semantic_type_resolver.evidence_widening.default`` is ON in
``project.yaml`` and ``RESOLVER_VERSION`` is ``"6"``. These tests exercise the
widened resolver path (shape initiation, datetime validator, structured
unresolved), the per-source flag, the dry-run diff endpoint, the AI
sample-masking policy, and the U1b additions: the version-bump re-resolution
path and the explicit per-source OFF escape hatch (byte-identical to flag-off).
The widened path is forced on explicitly via ``evidence_widening_override``;
the flag-off byte-identical guarantee is proven here for an explicitly-off
source.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from agents.semantic_type_agent import _apply_sample_policy
from core.semantic_resolver import RESOLVER_VERSION, ResolverConfig, SemanticResolver
from core.semantic_type_store import SemanticTypeStore
from tests._pg_semantic_type_isolation import sandbox_semantic_type_tests

_sandbox_db, _sandbox_wipe = sandbox_semantic_type_tests()


def _resolver(tmp_path: Path, *, widen: bool | None = None) -> SemanticResolver:
    return SemanticResolver(
        store=SemanticTypeStore(tmp_path / "semantic_types.yaml"),
        evidence_widening_override=widen,
    )


_CURRENCY_SIBLING_TABLE = {
    "table_name": "facility",
    "row_count": 1000,
    "primary_key": [],
    "columns": [{"name": "currency"}, {"name": "col_x"}],
}


# ── Task 3: shape initiation (flag ON) ───────────────────────────────────────

def test_widening_monetary_from_shape_without_name_token(tmp_path: Path):
    """A 2-decimal numeric with a currency sibling and no monetary name token
    reaches a monetary_amount candidate under widening (was 'Unknown' before)."""
    resolver = _resolver(tmp_path, widen=True)
    record = resolver.resolve_column(
        source="banking",
        schema="src",
        table="facility",
        column={
            "name": "col_x",
            "data_type": "DECIMAL",
            "row_count": 1000,
            "distinct_count": 100,
            "sample_values": ["100.00", "250.50", "1000.25"],
        },
        table_facts=_CURRENCY_SIBLING_TABLE,
    )
    assert record["type_id"] == "monetary_amount"
    assert record["domain_role"] == "measure"
    assert record["confidence"] >= 0.70
    assert any(ev.get("kind") == "shape" for ev in record["evidence"])


def test_widening_off_same_column_stays_unresolved(tmp_path: Path):
    """The same shape-only monetary column resolves to Unknown with the flag off."""
    resolver = _resolver(tmp_path, widen=False)
    record = resolver.resolve_column(
        source="banking",
        schema="src",
        table="facility",
        column={
            "name": "col_x",
            "data_type": "DECIMAL",
            "row_count": 1000,
            "distinct_count": 100,
            "sample_values": ["100.00", "250.50", "1000.25"],
        },
        table_facts=_CURRENCY_SIBLING_TABLE,
    )
    assert record["type_id"] == "unresolved"
    assert "resolution_reason" not in record  # structured fields are widen-only


def test_widening_total_limit_reaches_monetary(tmp_path: Path):
    """total_limit — the motivating column — resolves monetary under widening."""
    resolver = _resolver(tmp_path, widen=True)
    record = resolver.resolve_column(
        source="banking",
        schema="src",
        table="limits",
        column={
            "name": "total_limit",
            "data_type": "DECIMAL",
            "row_count": 1000,
            "distinct_count": 400,
            "sample_values": ["5000.00", "12000.50", "300.25"],
        },
        table_facts={"table_name": "limits", "row_count": 1000, "primary_key": []},
    )
    assert record["type_id"] == "monetary_amount"


def test_widening_negative_gate_sequential_ids_not_monetary(tmp_path: Path):
    """Sequential unique integers hit the unique_ratio gate → never monetary."""
    resolver = _resolver(tmp_path, widen=True)
    record = resolver.resolve_column(
        source="banking",
        schema="src",
        table="events",
        column={
            "name": "foo",
            "data_type": "BIGINT",
            "row_count": 100,
            "distinct_count": 100,
            "uniqueness_pct": 1.0,
            "sample_values": [1, 2, 3, 4, 5],
        },
        table_facts={"table_name": "events", "row_count": 100, "primary_key": []},
    )
    assert record["type_id"] not in {"monetary_amount", "rate"}
    assert record["type_id"] == "surrogate_systemid"


def test_widening_bounded_unit_interval_is_rate_not_monetary(tmp_path: Path):
    """[0,1]-bounded decimals route to rate; monetary is suppressed by its gate."""
    resolver = _resolver(tmp_path, widen=True)
    record = resolver.resolve_column(
        source="banking",
        schema="src",
        table="ratios",
        column={
            "name": "foo2",
            "data_type": "DECIMAL",
            "row_count": 1000,
            "distinct_count": 100,
            "sample_values": ["0.12", "0.45", "0.98"],
        },
        table_facts={"table_name": "ratios", "row_count": 1000, "primary_key": []},
    )
    assert record["type_id"] == "rate"


def test_widening_year_like_range_is_suppressed(tmp_path: Path):
    """1900–2100 integers are temporally suspicious → not a monetary/rate measure."""
    resolver = _resolver(tmp_path, widen=True)
    record = resolver.resolve_column(
        source="banking",
        schema="src",
        table="years",
        column={
            "name": "foo3",
            "data_type": "INTEGER",
            "row_count": 1000,
            "distinct_count": 60,
            "sample_values": [1990, 2000, 2010, 2020, 2015],
        },
        table_facts={"table_name": "years", "row_count": 1000, "primary_key": []},
    )
    assert record["type_id"] not in {"monetary_amount", "rate"}


# ── Task 3: datetime validator gating ────────────────────────────────────────

_EPOCH_COLUMN = {
    "name": "event_epoch",
    "data_type": "VARCHAR",
    "row_count": 1000,
    "distinct_count": 200,
    "sample_values": ["1620727200", "1622000000", "1625000000"],
}
_EPOCH_TABLE = {"table_name": "events", "row_count": 1000, "primary_key": []}


def test_widening_datetime_validator_fires(tmp_path: Path):
    resolver = _resolver(tmp_path, widen=True)
    record = resolver.resolve_column(
        source="banking", schema="src", table="events",
        column=dict(_EPOCH_COLUMN), table_facts=_EPOCH_TABLE,
    )
    assert record["type_id"] == "datetime"
    assert record["tier"] == 1


def test_datetime_validator_inert_with_flag_off(tmp_path: Path):
    resolver = _resolver(tmp_path, widen=False)
    record = resolver.resolve_column(
        source="banking", schema="src", table="events",
        column=dict(_EPOCH_COLUMN), table_facts=_EPOCH_TABLE,
    )
    assert record["type_id"] != "datetime"


# ── Task 4: per-source flag config ───────────────────────────────────────────

def test_resolver_config_evidence_widening_per_source():
    cfg = ResolverConfig.from_project({
        "semantic_type_resolver": {
            "evidence_widening": {"default": False, "sources": {"banking": True}},
        }
    })
    assert cfg.evidence_widening_for("banking") is True
    assert cfg.evidence_widening_for("other") is False
    assert cfg.evidence_widening_for(None) is False


def test_resolver_config_evidence_widening_default_off():
    cfg = ResolverConfig.from_project({})
    assert cfg.evidence_widening_for("banking") is False


# ── U1b Task 3: default-ON flip escape hatch + version-bump re-resolution ─────

def test_resolver_config_source_forced_off_while_default_on():
    """With widening default ON (the U1b flip), a source pinned False in the
    per-source map is still OFF — the explicit-off escape hatch is preserved."""
    cfg = ResolverConfig.from_project({
        "semantic_type_resolver": {
            "evidence_widening": {"default": True, "sources": {"banking": False}},
        }
    })
    assert cfg.evidence_widening_for("banking") is False
    assert cfg.evidence_widening_for("other") is True


def test_forced_off_source_stays_byte_identical(tmp_path: Path):
    """A source forced OFF via the per-source map (default ON) produces the same
    unresolved result as the flag-off path — no structured widen-only fields."""
    cfg = ResolverConfig.from_project({
        "semantic_type_resolver": {
            "evidence_widening": {"default": True, "sources": {"banking": False}},
        }
    })
    resolver = SemanticResolver(
        store=SemanticTypeStore(tmp_path / "semantic_types.yaml"),
        config=cfg,
    )
    record = resolver.resolve_column(
        source="banking",
        schema="src",
        table="facility",
        column={
            "name": "col_x",
            "data_type": "DECIMAL",
            "row_count": 1000,
            "distinct_count": 100,
            "sample_values": ["100.00", "250.50", "1000.25"],
        },
        table_facts=_CURRENCY_SIBLING_TABLE,
    )
    assert record["type_id"] == "unresolved"
    assert "resolution_reason" not in record  # widen-only fields never written when off


_IBAN_COLUMN = {
    "name": "iban",
    "data_type": "VARCHAR",
    "row_count": 2,
    "distinct_count": 2,
    "sample_values": ["GB82WEST12345698765432", "DE89370400440532013000"],
}
_IBAN_TABLE = {"table_name": "accounts", "row_count": 2, "primary_key": []}


def test_version_bump_reresolves_cached_proposed(tmp_path: Path):
    """A cached, unaccepted record at an older resolver_version re-resolves under
    the current RESOLVER_VERSION — the U1b 5→6 bump path."""
    store = SemanticTypeStore(tmp_path / "semantic_types.yaml")
    resolver = SemanticResolver(store=store)
    first = resolver.resolve_column(
        source="banking", schema="src", table="accounts",
        column=dict(_IBAN_COLUMN), table_facts=_IBAN_TABLE,
    )
    assert not first.get("accepted_at")
    assert first["resolver_version"] == RESOLVER_VERSION

    # Simulate a record cached under the previous version with a sentinel confidence.
    stale = store.get("banking", "src", "accounts", "iban")
    stale["resolver_version"] = "5"
    stale["confidence"] = 0.111  # sentinel — must be overwritten on recompute
    store.set_record(stale, preserve_disposed=False)

    second = resolver.resolve_column(
        source="banking", schema="src", table="accounts",
        column=dict(_IBAN_COLUMN), table_facts=_IBAN_TABLE,
    )
    assert second["resolver_version"] == RESOLVER_VERSION  # recomputed under "6"
    assert second["confidence"] != 0.111                   # not the stale cached value
    assert second["type_id"] == "natural_iban"


def test_version_bump_accepted_stays_sticky(tmp_path: Path):
    """An ACCEPTED record at an older version is returned unchanged (sticky)."""
    store = SemanticTypeStore(tmp_path / "semantic_types.yaml")
    resolver = SemanticResolver(store=store)
    resolver.resolve_column(
        source="banking", schema="src", table="accounts",
        column=dict(_IBAN_COLUMN), table_facts=_IBAN_TABLE,
    )
    rec = store.get("banking", "src", "accounts", "iban")
    rec["accepted_at"] = "2026-08-20T00:00:00Z"
    rec["resolver_version"] = "5"
    rec["confidence"] = 0.123  # sentinel that must survive
    store.set_record(rec, preserve_disposed=False)

    out = resolver.resolve_column(
        source="banking", schema="src", table="accounts",
        column=dict(_IBAN_COLUMN), table_facts=_IBAN_TABLE,
    )
    assert out["accepted_at"]
    assert out["resolver_version"] == "5"   # untouched despite version mismatch
    assert out["confidence"] == 0.123       # untouched


# ── Task 5: AI sample policy ─────────────────────────────────────────────────

def _residual_fixture() -> list[dict]:
    return [{
        "key": "banking|src|accounts|balance",
        "type_id": "unresolved",
        "sample_values": [100.0, 250.5, -10.0],
        "top_values": [{"value": 100.0, "count": 3}],
        "evidence": [
            {"kind": "validator", "signal": "iban 40%", "passing": ["GB82"], "failing": ["XX00"]},
        ],
    }]


def test_ai_policy_full_keeps_samples():
    out = _apply_sample_policy(_residual_fixture(), "full")
    assert out[0]["sample_values"] == [100.0, 250.5, -10.0]
    assert out[0]["evidence"][0]["passing"] == ["GB82"]


def test_ai_policy_masked_redacts_but_keeps_shape():
    out = _apply_sample_policy(_residual_fixture(), "masked")
    assert isinstance(out[0]["sample_values"], str)
    assert "redacted" in out[0]["sample_values"]
    assert "redacted" in out[0]["evidence"][0]["passing"]
    # non-sample fields survive
    assert out[0]["type_id"] == "unresolved"
    assert out[0]["evidence"][0]["signal"] == "iban 40%"


def test_ai_policy_stats_only_drops_samples():
    out = _apply_sample_policy(_residual_fixture(), "stats_only")
    assert "sample_values" not in out[0]
    assert "top_values" not in out[0]
    assert "passing" not in out[0]["evidence"][0]
    assert out[0]["type_id"] == "unresolved"


def test_ai_policy_unknown_falls_back_to_masked():
    out = _apply_sample_policy(_residual_fixture(), "bogus")
    assert isinstance(out[0]["sample_values"], str)


# ── Task 4: dry-run diff endpoint (no writes) ────────────────────────────────

@pytest.fixture()
def semantic_client(tmp_path, monkeypatch, session_audit_db):
    # This fixture reads the REAL catalog (dry_run=true, never persists -- see the route's
    # own `persist=False` call) -- opt back out of the module's adm_test sandbox so the real
    # `banking` source is visible. Read-only, so no restore fixture is needed here.
    monkeypatch.delenv("ADM_DATABASE_URL", raising=False)
    monkeypatch.setenv("AI_TIMO_SEMANTIC_TYPES", str(tmp_path / "semantic_types.yaml"))
    from fastapi.testclient import TestClient
    from api.main import app

    with TestClient(app) as client:
        yield client


def test_dry_run_resolve_persists_nothing(semantic_client):
    client = semantic_client
    # Snapshot the real, already-governed `banking` source's records before the dry run --
    # this must run against the real catalog (dry_run needs it to exist), so it necessarily
    # sees real, already-governed rows, not an empty store.
    before = client.get("/semantic-types/banking/all").json()["items"]

    resp = client.post("/semantic-types/banking/accounts/resolve?schema=src&dry_run=true")
    assert resp.status_code == 200
    body = resp.json()
    assert body["dry_run"] is True
    assert body["evidence_widening"] is True
    assert "changes" in body and isinstance(body["changes"], list)
    assert "column_count" in body

    # Nothing was persisted: the store's records for this source are byte-identical to before.
    after = client.get("/semantic-types/banking/all").json()["items"]
    assert after == before
