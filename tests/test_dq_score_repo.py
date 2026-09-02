"""govern-pg-a1-dq-scores-build — DQScoreRepo (Postgres), the sole backend for DQ scores.

Runs against a throwaway ``adm_test`` database on the same container; the whole module is
skipped if Postgres isn't reachable, so the rest of the suite still runs anywhere.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone

import pytest

from core.dq_config import DQScoringConfig
from core.glossary_db import db as gdb

CONFIG = DQScoringConfig.from_project()

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
    pytest.skip("PostgreSQL not reachable — start db/docker-compose.yml to run DQ score repo tests",
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
    from core.dq_score_repo import DQScoreRepo
    return DQScoreRepo(dsn=_TEST_DSN)


@pytest.fixture(autouse=True)
def _clean_dq_score_rows():
    """dq_score rows persist in adm_test across runs — clear test keys before each test.

    dq_score_history rows cascade-delete via the FK, so only dq_score itself needs clearing.
    """
    from sqlalchemy import delete
    from core.glossary_db.db import session_scope
    from core.shared.models import DqScore

    def _wipe():
        with session_scope(_TEST_DSN) as s:
            s.execute(delete(DqScore).where(DqScore.key.like("dqtest_%")))

    _wipe()
    yield
    _wipe()


def _key(name: str) -> str:
    return f"dqtest_{name}|s|t|c"


def _dataset_key(name: str) -> str:
    return f"dqtest_{name}|s|t"


def _breakdown(score, *, state="scored", breakdown_version=1, extra=None):
    d = {"state": state, "dq_score": score, "grade_label": "Good", "components": [],
         "breakdown_version": breakdown_version}
    if extra:
        d.update(extra)
    return d


def _history_rows(key: str) -> list[dict]:
    from sqlalchemy import select
    from core.glossary_db.db import session_scope
    from core.shared.models import DqScoreHistory
    with session_scope(_TEST_DSN) as s:
        rows = s.execute(
            select(DqScoreHistory).where(DqScoreHistory.key == key).order_by(DqScoreHistory.valid_to)
        ).scalars().all()
        return [
            {"dq_score": r.dq_score, "state": r.state, "valid_from": r.valid_from, "valid_to": r.valid_to}
            for r in rows
        ]


def _current_row(key: str):
    from sqlalchemy import select
    from core.glossary_db.db import session_scope
    from core.shared.models import DqScore
    with session_scope(_TEST_DSN) as s:
        return s.execute(select(DqScore).where(DqScore.key == key)).scalar_one_or_none()


# ── schema + basic record() behavior ─────────────────────────────────────────

def test_first_ever_score_uses_its_own_scored_at_no_history(repo):
    key = _key("first")
    before = datetime.now(timezone.utc)
    repo.record(key, _breakdown(81), signal_snapshot={"a": 1}, config=CONFIG)
    row = _current_row(key)
    assert row.valid_from >= before
    assert row.valid_from == row.scored_at
    assert _history_rows(key) == []


def test_changed_rescore_closes_history_with_real_valid_to(repo):
    key = _key("changed")
    repo.record(key, _breakdown(81), signal_snapshot={"a": 1}, config=CONFIG)
    time.sleep(0.01)
    repo.record(key, _breakdown(73), signal_snapshot={"a": 2}, config=CONFIG)

    history = _history_rows(key)
    assert len(history) == 1
    assert history[0]["dq_score"] == 81                 # the outgoing version
    assert history[0]["valid_to"] is not None
    row = _current_row(key)
    assert row.dq_score == 73
    assert row.valid_from == history[0]["valid_to"]     # new window opens where old one closed


def test_identical_rescore_creates_no_history_and_does_not_advance(repo):
    key = _key("noop")
    repo.record(key, _breakdown(81), signal_snapshot={"a": 1}, config=CONFIG)
    before = _current_row(key)
    time.sleep(0.01)
    repo.record(key, _breakdown(81), signal_snapshot={"a": 1}, config=CONFIG)
    after = _current_row(key)

    assert _history_rows(key) == []
    assert after.scored_at == before.scored_at
    assert after.valid_from == before.valid_from


def test_identical_score_newer_breakdown_version_refreshes_in_place(repo):
    key = _key("shape_refresh")
    stale = _breakdown(81, breakdown_version=1)
    repo.record(key, stale, signal_snapshot={"a": 1}, config=CONFIG)
    before = _current_row(key)

    time.sleep(0.01)
    fresh = _breakdown(81, breakdown_version=2, extra={"components": [{"noted": True}]})
    repo.record(key, fresh, signal_snapshot={"a": 1}, config=CONFIG)
    after = _current_row(key)

    assert _history_rows(key) == []                    # no churn — score unchanged
    assert after.breakdown_version == 2                 # but the newer shape won
    assert after.breakdown["components"] == [{"noted": True}]
    assert after.scored_at == before.scored_at           # no real-world change -> no new window
    assert after.valid_from == before.valid_from


def test_retention_keeps_baseline_and_latest_n_minus_1(repo):
    key = _key("retention")
    for i in range(10):
        repo.record(key, _breakdown(i), signal_snapshot={"i": i}, config=CONFIG, max_records=5)
        time.sleep(0.002)
    history = _history_rows(key)
    assert len(history) == 5                            # baseline + latest 4
    scores = [h["dq_score"] for h in history]
    assert 0 in scores                                   # baseline (very first) preserved
    assert max(scores) == 8                              # latest closed version (9 is current)


def test_column_and_dataset_keys_store_correct_key_kind(repo):
    ckey = _key("kind_col")
    dkey = _dataset_key("kind_ds")
    repo.record(ckey, _breakdown(81), signal_snapshot={"a": 1}, config=CONFIG)
    repo.record(dkey, _breakdown(81), signal_snapshot={"a": 1}, config=CONFIG)
    assert _current_row(ckey).key_kind == "column"
    assert _current_row(dkey).key_kind == "dataset"


# ── scored <-> unscored gap (DQ's own gap-creating transition) ──────────────

def test_scored_to_unscored_closes_history_then_rescope_opens_new_window(repo):
    key = _key("gap")
    repo.record(key, _breakdown(81), signal_snapshot={"a": 1}, config=CONFIG)
    time.sleep(0.01)
    repo.record(key, _breakdown(None, state="unscored"), signal_snapshot={"a": None}, config=CONFIG)

    history = _history_rows(key)
    assert len(history) == 1
    assert history[0]["state"] == "scored"
    row = _current_row(key)
    assert row.state == "unscored"

    time.sleep(0.01)
    repo.record(key, _breakdown(90), signal_snapshot={"a": 2}, config=CONFIG)
    history2 = _history_rows(key)
    assert len(history2) == 2                            # the unscored version also closed
    row2 = _current_row(key)
    assert row2.state == "scored" and row2.dq_score == 90


# ── as_of() point-in-time lookup ─────────────────────────────────────────────

def test_as_of_returns_current_row_for_recent_date(repo):
    key = _key("asof_current")
    repo.record(key, _breakdown(81), signal_snapshot={"a": 1}, config=CONFIG)
    result = repo.as_of(key, datetime.now(timezone.utc))
    assert result is not None
    assert result["dq_score"] == 81
    assert result["valid_to"] is None


def test_as_of_returns_historical_row_for_older_date(repo):
    key = _key("asof_history")
    repo.record(key, _breakdown(81), signal_snapshot={"a": 1}, config=CONFIG)
    mid_point = datetime.now(timezone.utc)
    time.sleep(0.01)
    repo.record(key, _breakdown(73), signal_snapshot={"a": 2}, config=CONFIG)

    result = repo.as_of(key, mid_point)
    assert result is not None
    assert result["dq_score"] == 81

    now_result = repo.as_of(key, datetime.now(timezone.utc))
    assert now_result["dq_score"] == 73


def test_as_of_returns_not_found_inside_unscored_gap(repo):
    key = _key("asof_gap")
    repo.record(key, _breakdown(81), signal_snapshot={"a": 1}, config=CONFIG)
    time.sleep(0.01)
    repo.record(key, _breakdown(None, state="unscored"), signal_snapshot={"a": None}, config=CONFIG)
    # Current row's valid_from predates "now", but its state is unscored — must not answer.
    assert repo.as_of(key, datetime.now(timezone.utc)) is None


def test_as_of_returns_not_found_before_first_score(repo):
    key = _key("asof_before")
    before = datetime.now(timezone.utc) - timedelta(days=1)
    repo.record(key, _breakdown(81), signal_snapshot={"a": 1}, config=CONFIG)
    assert repo.as_of(key, before) is None


# ── DQScoreStore pure-logic helpers (no I/O, folded in from the retired
#    test_dq_score_store.py in Slice F) ─────────────────────────────────────

def test_signal_fingerprint_includes_type_id():
    from core.dq_score_store import DQScoreStore
    fp_a = DQScoreStore.signal_fingerprint("dq-1", {"semantic_type": {"type_id": None}})
    fp_b = DQScoreStore.signal_fingerprint("dq-1", {"semantic_type": {"type_id": "country_code"}})
    assert fp_a != fp_b
