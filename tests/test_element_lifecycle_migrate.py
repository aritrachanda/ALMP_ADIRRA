"""Phase 5a — element-lifecycle migration + value-preserving parity.

Proves the derived-status load into Postgres is correct and that the Definition
lifecycle-points delta is bounded to the two intended ticks (draft-with-content → saved,
submitted-undecided → in_review). Runs against ``adm_test``; skipped if Postgres is down.
"""
from __future__ import annotations

import os

import pytest
import yaml

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
    pytest.skip("PostgreSQL not reachable — start db/docker-compose.yml to run migration tests",
                allow_module_level=True)


@pytest.fixture(scope="module", autouse=True)
def _adm_test_db():
    import psycopg
    raw = _BASE_DSN.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(raw, autocommit=True) as conn:
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname='adm_test'").fetchone():
            conn.execute("CREATE DATABASE adm_test")
    prev_url = os.environ.get("ADM_DATABASE_URL")
    os.environ["ADM_DATABASE_URL"] = _TEST_DSN
    gdb.dispose_all()
    from alembic import command
    from alembic.config import Config
    command.upgrade(Config("db/alembic.ini"), "head")
    yield
    gdb.dispose_all()
    if prev_url is None:
        os.environ.pop("ADM_DATABASE_URL", None)
    else:
        os.environ["ADM_DATABASE_URL"] = prev_url


# ── synthetic element_states.yaml covering every derivation branch ───────────
_FIXTURE = {
    "states": {
        "s|sc|t|blank": "draft",       # no content        → empty (skipped)
        "s|sc|t|draftc": "draft",      # content            → draft  (+1 tick)
        "s|sc|t|defd": "defined",      # content            → draft  (neutral)
        "s|sc|t|subm": "defined",      # submitted          → in_review (+1 tick)
        "s|sc|t|appr": "approved",     # approved           → approved
        "s|sc|t|rej": "defined",       # rejected           → returned
    },
    "descriptions": {
        "s|sc|t|draftc": "a description",
        "s|sc|t|defd": "a description",
        "s|sc|t|subm": "a description",
        "s|sc|t|appr": "a description",
        "s|sc|t|rej": "a description",
    },
    "business_names": {},
    "submission_overlay": {
        "s|sc|t|subm": {"submitted_at": "2026-07-20T10:00:00", "submitted_by": "ana"},
        "s|sc|t|appr": {"submitted_at": "2026-07-20T10:00:00", "submitted_by": "ana",
                        "decided_at": "2026-07-21T09:00:00", "decided_by": "stew",
                        "decision": "approved"},
        "s|sc|t|rej": {"submitted_at": "2026-07-20T10:00:00", "submitted_by": "ana",
                       "decided_at": "2026-07-21T09:00:00", "decided_by": "stew",
                       "decision": "rejected", "reject_reason": "needs detail"},
    },
}


@pytest.fixture()
def fixture_yaml(tmp_path):
    p = tmp_path / "element_states.yaml"
    with p.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(_FIXTURE, fh)
    return p


def test_migration_derives_and_loads_statuses(fixture_yaml):
    from core.element_lifecycle_migrate import migrate_element_states
    from core.element_lifecycle_repo import ElementLifecycleRepo

    stats = migrate_element_states(yaml_path=fixture_yaml, dsn=_TEST_DSN, force=True)
    assert stats["skipped_empty"] == 1        # the empty draft
    assert stats["written"] == 5

    repo = ElementLifecycleRepo(dsn=_TEST_DSN)
    assert repo.get_status("s|sc|t|blank") == "empty"   # default (no row)
    assert repo.get_status("s|sc|t|draftc") == "draft"
    assert repo.get_status("s|sc|t|defd") == "draft"
    assert repo.get_status("s|sc|t|subm") == "in_review"
    assert repo.get_status("s|sc|t|appr") == "approved"
    assert repo.get_status("s|sc|t|rej") == "returned"


def test_migration_review_tasks_reflect_overlay(fixture_yaml):
    from core.element_lifecycle_migrate import migrate_element_states
    from core.element_lifecycle_repo import ElementLifecycleRepo

    migrate_element_states(yaml_path=fixture_yaml, dsn=_TEST_DSN, force=True)
    repo = ElementLifecycleRepo(dsn=_TEST_DSN)

    # submitted item is pending; decided items carry their decision
    assert "s|sc|t|subm" in {p["key"] for p in repo.pending_review("s")}
    appr = repo.get_review("s|sc|t|appr")
    assert appr["decision"] == "approved" and appr["decided_by"] == "stew"
    rej = repo.get_review("s|sc|t|rej")
    assert rej["decision"] == "returned" and rej["reject_reason"] == "needs detail"


def test_lifecycle_points_parity_only_intended_ticks(fixture_yaml):
    from core.element_lifecycle_migrate import lifecycle_points_summary

    cfg = yaml.safe_load(open("governance/dq_scoring_config.yaml", encoding="utf-8"))
    new_scale = cfg["definition_scales"]["description"]["lifecycle"]
    rows = {r["key"]: r for r in lifecycle_points_summary(yaml_path=fixture_yaml, new_scale=new_scale)}

    # the ONLY two positive deltas, each exactly +1
    assert rows["s|sc|t|draftc"]["delta"] == 1     # draft-with-content 1 → saved 2
    assert rows["s|sc|t|subm"]["delta"] == 1       # submitted 2 → in_review 3
    # everything else neutral
    assert rows["s|sc|t|defd"]["delta"] == 0
    assert rows["s|sc|t|appr"]["delta"] == 0
    assert rows["s|sc|t|rej"]["delta"] == 0
    # no delta anywhere exceeds +1, none negative
    assert all(0 <= r["delta"] <= 1 for r in rows.values())
