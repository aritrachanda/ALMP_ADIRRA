"""govern-pg-b1-semantic-types-build -- SemanticTypeRepo (Postgres) + SemanticTypeStore
backend-branch tests.

Runs against a throwaway ``adm_test`` database on the same container; the whole module is
skipped if Postgres isn't reachable, so the rest of the suite still runs anywhere.
"""
from __future__ import annotations

import os

import pytest

from core.glossary_db import db as gdb

_BASE_DSN = gdb.build_dsn()
_TEST_DSN = _BASE_DSN.rsplit("/", 1)[0] + "/adm_test"


def _pg_available() -> bool:
    try:
        import psycopg  # noqa: F401
        from sqlalchemy import text
        eng = gdb.get_engine(_BASE_DSN)
        with eng.connect() as c:
            c.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


if not _pg_available():
    pytest.skip("PostgreSQL not reachable — start db/docker-compose.yml to run semantic type repo tests",
                allow_module_level=True)


@pytest.fixture(scope="module", autouse=True)
def _adm_test_db():
    import psycopg
    raw = _BASE_DSN.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(raw, autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname='adm_test'").fetchone()
        if not exists:
            conn.execute("CREATE DATABASE adm_test")

    prev_url = os.environ.get("ADM_DATABASE_URL")
    os.environ["ADM_DATABASE_URL"] = _TEST_DSN
    gdb.dispose_all()

    from alembic import command
    from alembic.config import Config
    cfg = Config("db/alembic.ini")
    command.upgrade(cfg, "head")

    yield

    gdb.dispose_all()
    if prev_url is None:
        os.environ.pop("ADM_DATABASE_URL", None)
    else:
        os.environ["ADM_DATABASE_URL"] = prev_url


@pytest.fixture()
def repo():
    from core.semantic_type_repo import SemanticTypeRepo
    return SemanticTypeRepo(dsn=_TEST_DSN)


@pytest.fixture(autouse=True)
def _clean_semantic_type_rows():
    """semantic_type_assignment rows persist in adm_test across runs -- clear test keys first.

    semantic_type_assignment_history rows cascade-delete via the FK.
    """
    from sqlalchemy import delete
    from core.glossary_db.db import session_scope
    from core.shared.models import SemanticTypeAssignment

    def _wipe():
        with session_scope(_TEST_DSN) as s:
            s.execute(delete(SemanticTypeAssignment).where(SemanticTypeAssignment.key.like("semtest_%")))

    _wipe()
    yield
    _wipe()


def _src(name: str) -> str:
    return f"semtest_{name}"


def _history_rows(key: str) -> list[dict]:
    from sqlalchemy import select
    from core.glossary_db.db import session_scope
    from core.shared.models import SemanticTypeAssignmentHistory
    with session_scope(_TEST_DSN) as s:
        rows = s.execute(
            select(SemanticTypeAssignmentHistory)
            .where(SemanticTypeAssignmentHistory.key == key)
            .order_by(SemanticTypeAssignmentHistory.valid_from)
        ).scalars().all()
        return [
            {
                "type_id": r.type_id,
                "deduced_type_id": r.deduced_type_id,
                "valid_from": r.valid_from,
                "valid_to": r.valid_to,
            }
            for r in rows
        ]


# ── basic read/write parity with SemanticTypeStore's contract ──────────────────


def test_get_missing_returns_none(repo):
    assert repo.get(_src("a"), "s", "t", "c") is None


def test_get_or_default_returns_default_record(repo):
    record = repo.get_or_default(_src("a"), "s", "t", "c")
    assert record["type_id"] == "unresolved"
    assert not record.get("accepted_at")
    assert record["column"] == "c"


def test_set_proposed_then_get_round_trips(repo):
    source = _src("proposed")
    repo.set_proposed(
        source=source, schema="s", table="t", column="c",
        type_id="iban", domain_role="account_identifier", confidence=0.9,
        fingerprint="fp1", resolver_version="10",
    )
    record = repo.get(source, "s", "t", "c")
    assert record["type_id"] == "iban"
    assert not record.get("accepted_at")
    assert record["confidence"] == pytest.approx(0.9)
    assert record["fingerprint"] == "fp1"
    assert record["resolver_version"] == "10"


def test_latest_proposal_absent_when_never_parked(repo):
    """Regression (found live 2026-08-14, post-flip crash): a record with no parked proposal
    must have NO latest_proposal key at all -- matching SemanticTypeStore's YAML shape -- not a
    present key with value None. core/semantic_resolver.py calls
    record.get("latest_proposal", {}).get(...), which only falls back to {} when the key is
    MISSING; a present-but-None value crashes with AttributeError."""
    source = _src("no_proposal")
    repo.set_proposed(source=source, schema="s", table="t", column="c",
                       type_id="iban", domain_role="account_identifier", confidence=0.9)
    record = repo.get(source, "s", "t", "c")
    assert "latest_proposal" not in record
    assert record.get("latest_proposal", {}).get("type_value_conflict") is None  # would crash otherwise


def test_domain_roles_for_source_bulk_fetch(repo):
    """One query returns every column's domain_role for a source -- powers the Source
    Profile page's semantic-type chart (previously one repo.get() call per column)."""
    source = _src("bulk")
    other_source = _src("bulk_other")
    repo.set_proposed(source=source, schema="s", table="t", column="a",
                       type_id="iban", domain_role="account_identifier", confidence=0.9)
    repo.set_proposed(source=source, schema="s", table="t", column="b",
                       type_id="currency_code", domain_role="code", confidence=0.9)
    repo.set_proposed(source=other_source, schema="s", table="t", column="a",
                       type_id="rate", domain_role="rate", confidence=0.9)

    result = repo.domain_roles_for_source(source)

    assert result == {
        repo.key(source, "s", "t", "a"): "account_identifier",
        repo.key(source, "s", "t", "b"): "code",
    }
    assert repo.key(other_source, "s", "t", "a") not in result  # never leaks another source's rows


def test_get_by_key_caches_and_invalidates_on_write(repo):
    """The TTL read cache (mirrors element_lifecycle_repo.py's get_status()/all_states())
    must (1) avoid re-querying within the TTL window, (2) never serve stale data across a
    write -- a write must invalidate it immediately, not wait out the TTL."""
    from unittest.mock import patch
    from core.semantic_type_repo import SemanticTypeRepo

    source = _src("cache")
    repo.set_proposed(source=source, schema="s", table="t", column="c",
                       type_id="iban", domain_role="account_identifier", confidence=0.9)

    assert repo.get(source, "s", "t", "c")["type_id"] == "iban"  # populates the cache
    assert repo._records_cache is not None

    with patch.object(SemanticTypeRepo, "_refresh_records_cache") as mock_refresh:
        assert repo.get(source, "s", "t", "c")["type_id"] == "iban"  # served from cache
        mock_refresh.assert_not_called()

    repo.accept(source, "s", "t", "c", accepted_by="alice")  # write invalidates immediately
    assert repo._records_cache is None
    assert repo.get(source, "s", "t", "c")["accepted_at"]  # fresh data, not stale


def test_get_by_key_refreshes_after_ttl_expires(repo, monkeypatch):
    """Past the TTL window, a stale cache is refreshed on the next read even without a write
    (e.g. a change made through a different process/session)."""
    source = _src("ttl")
    repo.set_proposed(source=source, schema="s", table="t", column="c",
                       type_id="iban", domain_role="account_identifier", confidence=0.9)
    repo.get(source, "s", "t", "c")  # populates the cache
    stale_ts = repo._records_ts - repo._records_ttl - 1
    repo._records_ts = stale_ts

    repo.get(source, "s", "t", "c")

    assert repo._records_ts > stale_ts  # cache was refreshed, not served stale



def test_set_record_on_accepted_parks_under_latest_proposal(repo):
    """Sticky disposition (preserve_disposed=True): a fresh machine re-resolve of an already
    accepted record must NOT overwrite the steward's decision -- it nests under latest_proposal,
    refreshing only the top-level fingerprint (mirrors SemanticTypeStore's SD-R4 behavior)."""
    source = _src("sticky")
    repo.set_proposed(source=source, schema="s", table="t", column="c",
                       type_id="iban", domain_role="account_identifier", confidence=0.8)
    repo.accept(source, "s", "t", "c", accepted_by="alice")

    fresh = repo.default_record(source=source, schema="s", table="t", column="c")
    fresh["key"] = repo.key(source, "s", "t", "c")
    fresh["type_id"] = "swift_bic"
    fresh["confidence"] = 0.6
    fresh["fingerprint"] = "fp2"
    result = repo.set_record(fresh, preserve_disposed=True)

    assert result["accepted_at"]
    assert result["type_id"] == "iban"
    assert result["accepted_by"] == "alice"
    assert result["fingerprint"] == "fp2"
    assert result["latest_proposal"]["type_id"] == "swift_bic"


# ── D1 fix: accept() preserves the machine's pre-override suggestion ──────────


def test_accept_replace_captures_system_deduced_type_once(repo):
    source = _src("replace")
    repo.set_proposed(source=source, schema="s", table="t", column="c",
                       type_id="iban", domain_role="account_identifier", confidence=0.7)

    result = repo.accept(source, "s", "t", "c", accepted_by="alice", type_id="swift_bic")
    assert result["type_id"] == "swift_bic"
    assert result["system_deduced_type"] == {
        "type_id": "iban", "domain_role": "account_identifier", "confidence": pytest.approx(0.7),
    }

    # A second override must NOT clobber the original machine suggestion.
    result2 = repo.accept(source, "s", "t", "c", accepted_by="bob", type_id="currency_code")
    assert result2["type_id"] == "currency_code"
    assert result2["system_deduced_type"]["type_id"] == "iban"


def test_accept_as_is_leaves_system_deduced_type_null(repo):
    source = _src("accept")
    repo.set_proposed(source=source, schema="s", table="t", column="c",
                       type_id="iban", domain_role="account_identifier", confidence=0.7)
    result = repo.accept(source, "s", "t", "c", accepted_by="alice")
    assert result["type_id"] == "iban"
    assert result["system_deduced_type"] is None


def test_accept_refuses_unresolved_type(repo):
    """An element can never be accepted while its type_id stays 'unresolved' (2026-08-20) --
    closes a gap the UI only ever enforced by hiding the Accept button."""
    source = _src("never_resolved")
    with pytest.raises(ValueError):
        repo.accept(source, "s", "t", "c", accepted_by="alice")


def test_find_in_source_uses_postgres(repo):
    source = _src("collection")
    repo.set_proposed(source=source, schema="s", table="t", column="a",
                      type_id="iban", domain_role="account_identifier", confidence=0.9)
    repo.set_proposed(source=source, schema="s", table="t", column="b",
                      type_id="swift_bic", domain_role="identifier", confidence=0.9)

    columns = {record["column"] for record in repo.find_in_source(source)}
    assert columns == {"a", "b"}


# ── D1: Interpretation Set submission history (self-contained SCD2) ───────────


def test_record_submission_opens_a_window(repo):
    source = _src("submit1")
    repo.set_proposed(source=source, schema="s", table="t", column="c",
                       type_id="iban", domain_role="account_identifier", confidence=0.9)
    repo.accept(source, "s", "t", "c", accepted_by="alice")
    key = repo.key(source, "s", "t", "c")

    repo.record_submission(
        source, "s", "t", "c",
        deduced_type_id="iban", deduced_confidence=0.9,
        submitted_by="alice",
    )
    rows = _history_rows(key)
    assert len(rows) == 1
    assert rows[0]["valid_to"] is None
    assert rows[0]["type_id"] == "iban"
    assert rows[0]["deduced_type_id"] == "iban"

    # No separate "semantic type's own" submission tracking on the current row (2026-08-13
    # user correction) -- the current record's dict simply has no submitted_at/submitted_by keys.
    record = repo.get(source, "s", "t", "c")
    assert "submitted_at" not in record
    assert "submitted_by" not in record


def test_second_submission_closes_the_first_window(repo):
    source = _src("submit2")
    repo.set_proposed(source=source, schema="s", table="t", column="c",
                       type_id="iban", domain_role="account_identifier", confidence=0.9)
    repo.accept(source, "s", "t", "c", accepted_by="alice")
    key = repo.key(source, "s", "t", "c")

    repo.record_submission(source, "s", "t", "c", deduced_type_id="iban", submitted_by="alice")
    # Steward returns it, reworks it (now Replace-d to swift_bic), resubmits -- must always be
    # a new row (D1), no special-casing by whatever lifecycle reason preceded the resubmission.
    repo.accept(source, "s", "t", "c", accepted_by="bob", type_id="swift_bic")
    repo.record_submission(source, "s", "t", "c", deduced_type_id="iban", submitted_by="bob")

    rows = _history_rows(key)
    assert len(rows) == 2
    assert rows[0]["valid_to"] == rows[1]["valid_from"]
    assert rows[1]["valid_to"] is None
    assert rows[0]["type_id"] == "iban"
    assert rows[1]["type_id"] == "swift_bic"
    # The machine's own independent opinion never changed -- only the accepted snapshot did.
    assert rows[1]["deduced_type_id"] == "iban"


def test_record_submission_without_prior_assignment_raises(repo):
    with pytest.raises(ValueError):
        repo.record_submission(_src("missing"), "s", "t", "c", deduced_type_id="iban")


# ── SemanticTypeStore facade (Postgres-only since Slice F) ─────────────────────


def test_store_facade_delegates_to_postgres(tmp_path, monkeypatch):
    """SemanticTypeStore accepts (and ignores) a path argument for call-site compatibility,
    but every call goes straight through to the real Postgres repository."""
    from core.semantic_type_store import SemanticTypeStore

    monkeypatch.setenv("ADM_DATABASE_URL", _TEST_DSN)
    store = SemanticTypeStore(tmp_path / "unused_semantic_type_assignments.yaml")
    source = _src("store_facade")
    store.set_proposed(source=source, schema="s", table="t", column="parity",
                        type_id="iban", domain_role="account_identifier", confidence=0.85)
    accepted = store.accept(source, "s", "t", "parity", accepted_by="alice", type_id="swift_bic")

    assert accepted["type_id"] == "swift_bic"
    assert accepted["accepted_at"]
    assert accepted["system_deduced_type"]["type_id"] == "iban"
    assert store.get(source, "s", "t", "parity")["type_id"] == "swift_bic"

