"""Phase 5b.2 — Postgres-backed per-code Reference Data repo + migration.

Runs against a throwaway ``adm_test`` database on the same container; the whole module is
skipped if Postgres isn't reachable, so the rest of the suite still runs anywhere.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

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
    pytest.skip("PostgreSQL not reachable — start db/docker-compose.yml to run reference-code tests",
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
    prev_backend = os.environ.get("ADIRRA_GLOSSARY_BACKEND")
    os.environ["ADM_DATABASE_URL"] = _TEST_DSN
    os.environ["ADIRRA_GLOSSARY_BACKEND"] = "postgres"
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
    if prev_backend is None:
        os.environ.pop("ADIRRA_GLOSSARY_BACKEND", None)
    else:
        os.environ["ADIRRA_GLOSSARY_BACKEND"] = prev_backend


@pytest.fixture()
def repo():
    from core.reference_code_repo import ReferenceCodeRepo
    return ReferenceCodeRepo(dsn=_TEST_DSN)


@pytest.fixture(autouse=True)
def _clean_reference_rows():
    """Reference-code rows persist in adm_test across runs — clear the test keys before
    each test so save/submit start from a known-empty state (idempotent across suite runs).
    """
    from sqlalchemy import delete
    from core.glossary_db.db import session_scope
    from core.glossary_db.models import LifecycleTransition, ReferenceCode

    def _wipe():
        with session_scope(_TEST_DSN) as s:
            s.execute(delete(ReferenceCode).where(
                ReferenceCode.element_key.like("rctest_%")
                | ReferenceCode.element_key.like("mig_%")))
            s.execute(delete(LifecycleTransition).where(
                LifecycleTransition.subject_type == "reference_code",
                LifecycleTransition.subject_ref.like("rctest_%")
                | LifecycleTransition.subject_ref.like("mig_%")))

    _wipe()
    yield
    _wipe()


def _key(name: str) -> str:
    return f"rctest_{name}|s|t|c"


# ── repo behaviour ──────────────────────────────────────────────────────────

def test_save_blank_to_draft_and_origin(repo):
    key = _key("save")
    rows = repo.save_codes(key, [
        {"code": "A", "meaning": "Active", "origin": "declared"},
        {"code": "B", "meaning": "", "origin": "profiled"},
    ])
    by = {r["code"]: r for r in rows}
    assert by["A"]["status"] == "draft"       # gained content
    assert by["A"]["origin"] == "declared"
    assert by["B"]["status"] == "empty"       # no content → stays empty
    assert by["B"]["origin"] == "profiled"


def test_partial_submit_only_filled_drafts(repo):
    key = _key("submit")
    repo.save_codes(key, [
        {"code": "A", "meaning": "Active"},
        {"code": "B", "meaning": "Blocked"},
        {"code": "C", "meaning": ""},          # unfilled → not submittable
    ])
    outcome = repo.submit_codes(key, ["A", "C"])
    assert outcome["submitted"] == 1           # only A (filled draft in the selection)
    assert outcome["codes"] == ["A"]
    by = {r["code"]: r for r in repo.get_codes(key)}
    assert by["A"]["status"] == "in_review"
    assert by["B"]["status"] == "draft"        # not in the submit selection
    assert by["C"]["status"] == "empty"


def test_in_review_and_approved_codes_are_locked(repo):
    key = _key("locked")
    repo.save_codes(key, [{"code": "A", "meaning": "Active"}])
    repo.submit_codes(key, ["A"])
    # A save on an in-review code must not overwrite it.
    rows = repo.save_codes(key, [{"code": "A", "meaning": "TAMPERED"}])
    by = {r["code"]: r for r in rows}
    assert by["A"]["status"] == "in_review"
    assert by["A"]["meaning"] == "Active"


def test_summary_derives_set_status(repo):
    key = _key("summary")
    repo.save_codes(key, [{"code": "A", "meaning": "Active"}])
    repo.submit_codes(key, ["A"])
    summary = repo.summary(key)
    assert summary["codes_documented"] == 1
    assert summary["status"] == "under_review"


def test_published_register_lists_only_in_review_and_approved(repo):
    key = _key("register")
    repo.save_codes(key, [
        {"code": "A", "meaning": "Active"},
        {"code": "B", "meaning": "Blocked"},
        {"code": "C", "meaning": ""},          # empty → never published
    ])
    repo.submit_codes(key, ["A", "B"])          # A, B → in_review; C stays empty
    _seed_approved(_key("register2"), "X", "Approved code")

    by_key = {e["element_key"]: e["codes"] for e in repo.published_register()}
    assert key in by_key
    codes = {c["code"]: c for c in by_key[key]}
    assert set(codes) == {"A", "B"}            # draft/empty C excluded
    assert codes["A"]["status"] == "in_review"
    assert _key("register2") in by_key         # approved codesets included


def test_published_register_source_filter(repo):
    key = _key("srcfilter")
    repo.save_codes(key, [{"code": "A", "meaning": "Active"}])
    repo.submit_codes(key, ["A"])
    scoped = repo.published_register(source="rctest_srcfilter")
    assert [e["element_key"] for e in scoped] == [key]
    assert repo.published_register(source="rctest_nomatch") == []


# ── analyst bulk pull-backs / delete (5b.3.1) ────────────────────────────────

def _transitions(key: str, code: str) -> list[str]:
    """Ordered audit ``to_status`` labels for one code (for auditability assertions)."""
    from sqlalchemy import select
    from core.glossary_db.db import session_scope
    from core.glossary_db.models import LifecycleTransition
    with session_scope(_TEST_DSN) as s:
        rows = s.execute(
            select(LifecycleTransition.to_status)
            .where(LifecycleTransition.subject_type == "reference_code",
                   LifecycleTransition.subject_ref == f"{key}|{code}")
            .order_by(LifecycleTransition.occurred_at, LifecycleTransition.id)
        ).scalars().all()
    return list(rows)


def _seed_approved(key: str, code: str, meaning: str) -> None:
    """Insert an already-approved code (Approve lives in the Review Workspace, 5b.3.2)."""
    from sqlalchemy import func
    from core.glossary_db.db import session_scope
    from core.glossary_db.models import ReferenceCode
    with session_scope(_TEST_DSN) as s:
        s.add(ReferenceCode(
            element_key=key, code=code, value=None, meaning=meaning,
            origin="profiled", status="approved",
            approved_at=func.now(), approved_by="steward",
        ))


def test_withdraw_in_review_back_to_draft(repo):
    key = _key("withdraw")
    repo.save_codes(key, [{"code": "A", "meaning": "Active"}, {"code": "B", "meaning": "Blocked"}])
    repo.submit_codes(key)  # both → in_review
    outcome = repo.withdraw_codes(key, ["A"], actor="ana", actor_role="analyst")
    assert outcome == {"withdrawn": 1, "codes": ["A"]}
    by = {r["code"]: r for r in repo.get_codes(key)}
    assert by["A"]["status"] == "draft"
    assert by["A"]["submitted_at"] is None and by["A"]["submitted_by"] is None
    assert by["B"]["status"] == "in_review"          # untouched
    assert _transitions(key, "A")[-1] == "withdrawn"  # audit persisted


def test_withdraw_ignores_non_in_review(repo):
    key = _key("withdraw_noop")
    repo.save_codes(key, [{"code": "A", "meaning": "Active"}])  # draft, not submitted
    outcome = repo.withdraw_codes(key, ["A"])
    assert outcome == {"withdrawn": 0, "codes": []}
    assert repo.get_codes(key)[0]["status"] == "draft"


def test_revoke_approved_back_to_draft(repo):
    key = _key("revoke")
    _seed_approved(key, "A", "Active")
    outcome = repo.revoke_codes(key, ["A"], actor="ana", actor_role="analyst")
    assert outcome == {"revoked": 1, "codes": ["A"]}
    row = repo.get_codes(key)[0]
    assert row["status"] == "draft"
    assert row["approved_at"] is None and row["approved_by"] is None
    assert _transitions(key, "A")[-1] == "revoked"


def test_remove_deletes_editable_only(repo):
    key = _key("remove")
    repo.save_codes(key, [{"code": "A", "meaning": "Active"}, {"code": "B", "meaning": ""}])
    repo.submit_codes(key)  # only A is filled → A in_review, B stays empty
    outcome = repo.remove_codes(key, ["A", "B"], actor="ana", actor_role="analyst")
    assert outcome == {"removed": 1, "codes": ["B"]}   # A (in_review) is frozen, skipped
    by = {r["code"]: r for r in repo.get_codes(key)}
    assert "B" not in by and by["A"]["status"] == "in_review"
    assert _transitions(key, "B")[-1] == "removed"     # deletion audited before drop


# ── steward approve + tombstone + queue (5b.3.2) ─────────────────────────────

def test_approve_in_review_to_approved(repo):
    key = _key("approve")
    repo.save_codes(key, [{"code": "A", "meaning": "Active"}, {"code": "B", "meaning": "Blocked"}])
    repo.submit_codes(key)  # both → in_review
    outcome = repo.approve_codes(key, ["A"], actor="stw", actor_role="steward")
    assert outcome == {"approved": 1, "codes": ["A"]}
    by = {r["code"]: r for r in repo.get_codes(key)}
    assert by["A"]["status"] == "approved"
    assert by["A"]["approved_at"] and by["A"]["approved_by"] == "stw"
    assert by["B"]["status"] == "in_review"           # untouched
    assert _transitions(key, "A")[-1] == "approved"


def test_approve_ignores_non_in_review(repo):
    key = _key("approve_noop")
    repo.save_codes(key, [{"code": "A", "meaning": "Active"}])  # draft, not submitted
    assert repo.approve_codes(key, ["A"]) == {"approved": 0, "codes": []}
    assert repo.get_codes(key)[0]["status"] == "draft"


def test_tombstones_track_latest_pullback(repo):
    key = _key("tomb")
    repo.save_codes(key, [{"code": "A", "meaning": "Active"}])
    repo.submit_codes(key)
    repo.withdraw_codes(key, ["A"])                    # A now a tombstone
    assert repo.tombstones(key) == {"A": {"action": "withdrawn", "at": repo.tombstones(key)["A"]["at"]}}
    assert repo.tombstones(key)["A"]["action"] == "withdrawn"
    # Resubmitting clears the tombstone (latest transition becomes in_review).
    repo.submit_codes(key)
    assert "A" not in repo.tombstones(key)


def test_pending_codesets_lists_in_review_and_tombstones(repo):
    src = "rctest_pend"
    live = f"{src}|s|t|c"
    tomb = f"{src}|s|t|d"
    draft_only = f"{src}|s|t|e"
    repo.save_codes(live, [{"code": "A", "meaning": "Active"}])
    repo.submit_codes(live)                            # live: 1 in_review
    repo.save_codes(tomb, [{"code": "X", "meaning": "X-ray"}])
    repo.submit_codes(tomb)
    repo.withdraw_codes(tomb, ["X"])                   # tomb: 1 tombstone, 0 in_review
    repo.save_codes(draft_only, [{"code": "Z", "meaning": "Zeta"}])  # never submitted → excluded

    by_key = {cs["key"]: cs for cs in repo.pending_codesets(src)}
    assert set(by_key) == {live, tomb}                 # draft_only excluded
    assert by_key[live]["in_review_count"] == 1 and by_key[live]["tombstone_count"] == 0
    assert by_key[tomb]["in_review_count"] == 0 and by_key[tomb]["tombstone_count"] == 1


# ── migration + parity ──────────────────────────────────────────────────────

def test_migration_parity_and_skips_bound(tmp_path: Path):
    from core.reference_code_migrate import migrate_reference_codes, parity_rows
    yaml_path = tmp_path / "element_states.yaml"
    yaml_path.write_text(yaml.safe_dump({
        "metadata": {
            "mig_a|s|t|c": {
                "refdata_meanings": {"O": "Open", "C": "Closed"},
                "refdata_status": "approved",
            },
            "mig_b|s|t|c": {
                "refdata_meanings": {"X": "X-ray"},
                "refdata_status": "under_review",
            },
            "mig_bound|s|t|c": {
                "refdata_bound_set_id": "iso_4217_currency",
                "refdata_meanings": {"EUR": "Euro"},
            },
        }
    }), encoding="utf-8")

    stats = migrate_reference_codes(yaml_path=yaml_path, dsn=_TEST_DSN, force=True)
    assert stats["fields"] == 2                 # bound field skipped
    assert stats["codes_written"] == 3          # 2 + 1
    assert stats["parity_mismatches"] == []

    rows = {r["key"]: r for r in parity_rows(yaml_path=yaml_path)}
    assert rows["mig_a|s|t|c"]["new_status"] == "approved"
    assert rows["mig_b|s|t|c"]["new_status"] == "under_review"
    assert all(r["match"] for r in rows.values())

    from core.reference_code_repo import ReferenceCodeRepo
    repo = ReferenceCodeRepo(dsn=_TEST_DSN)
    assert repo.summary("mig_a|s|t|c")["status"] == "approved"
    assert repo.get_codes("mig_bound|s|t|c") == []   # bound → no rows


# ── point-in-time historization (historize-reference-codes) ─────────────────

def _history_rows(key: str, code: str) -> list[dict]:
    """Raw reference_code_history rows for one code, oldest first."""
    from sqlalchemy import select
    from core.glossary_db.db import session_scope
    from core.shared.models import ReferenceCodeHistory
    with session_scope(_TEST_DSN) as s:
        rows = s.execute(
            select(ReferenceCodeHistory)
            .where(ReferenceCodeHistory.element_key == key, ReferenceCodeHistory.code == code)
            .order_by(ReferenceCodeHistory.valid_from)
        ).scalars().all()
        return [
            {"value": r.value, "meaning": r.meaning, "status": r.status,
             "valid_from": r.valid_from, "valid_to": r.valid_to}
            for r in rows
        ]


def _current_valid_from(key: str, code: str):
    from sqlalchemy import select
    from core.glossary_db.db import session_scope
    from core.shared.models import ReferenceCode
    with session_scope(_TEST_DSN) as s:
        return s.execute(
            select(ReferenceCode.valid_from)
            .where(ReferenceCode.element_key == key, ReferenceCode.code == code)
        ).scalar_one()


def test_new_code_defaults_to_sentinel_with_no_history(repo):
    """A freshly created row (never through approve_codes) gets the DB-default sentinel
    valid_from and creates zero history rows — the mechanism the real migration's backfill
    of pre-existing rows relies on (verified separately, live, against the real adm database:
    16/16 existing rows backfilled to the sentinel, 0 history rows created by the backfill)."""
    key = _key("sentinel_default")
    repo.save_codes(key, [{"code": "A", "meaning": "Active"}])
    assert _current_valid_from(key, "A").year == 1800
    assert _history_rows(key, "A") == []


def test_first_approval_uses_sentinel_not_now(repo):
    key = _key("first_approve")
    repo.save_codes(key, [{"code": "A", "meaning": "Active"}])
    repo.submit_codes(key, ["A"])
    repo.approve_codes(key, ["A"], actor="stw", actor_role="steward")
    assert _current_valid_from(key, "A").year == 1800   # first-ever approval -> sentinel
    assert _history_rows(key, "A") == []                # nothing to close yet


def test_revoke_closes_history_with_real_valid_to(repo):
    key = _key("revoke_hist")
    _seed_approved(key, "A", "Active")
    before_revoke = datetime.now(timezone.utc)
    repo.revoke_codes(key, ["A"], actor="ana", actor_role="analyst")
    history = _history_rows(key, "A")
    assert len(history) == 1
    assert history[0]["meaning"] == "Active"            # snapshot of the outgoing value
    assert history[0]["status"] == "approved"            # status at the moment of closing
    assert history[0]["valid_to"] >= before_revoke        # a real timestamp, not a placeholder
    assert history[0]["valid_to"].year != 1800


def test_second_approval_after_revoke_uses_real_date_even_if_unchanged(repo):
    """A gap is meaningful even when the re-approved content round-trips to the same words —
    this is NOT a no-op, per the design decision (D6)."""
    key = _key("reapprove")
    _seed_approved(key, "A", "Active")            # pre-existing approved value: "Active"
    repo.revoke_codes(key, ["A"], actor="ana", actor_role="analyst")
    repo.save_codes(key, [{"code": "A", "meaning": "Active"}])  # re-typed, byte-identical
    repo.submit_codes(key, ["A"])
    repo.approve_codes(key, ["A"], actor="stw", actor_role="steward")

    assert _current_valid_from(key, "A").year != 1800   # real date, NOT the sentinel
    history = _history_rows(key, "A")
    assert len(history) == 1                            # the pre-revoke version, closed
    assert history[0]["meaning"] == "Active"


def test_as_of_returns_current_row_for_recent_date(repo):
    key = _key("asof_current")
    _seed_approved(key, "A", "Active")
    result = repo.as_of(key, "A", datetime.now(timezone.utc))
    assert result == {"value": None, "meaning": "Active",
                       "valid_from": result["valid_from"], "valid_to": None}


def test_as_of_returns_historical_row_for_older_date(repo):
    key = _key("asof_history")
    _seed_approved(key, "A", "Original meaning")
    mid_point = datetime.now(timezone.utc)
    repo.revoke_codes(key, ["A"], actor="ana", actor_role="analyst")
    repo.save_codes(key, [{"code": "A", "meaning": "Updated meaning"}])
    repo.submit_codes(key, ["A"])
    repo.approve_codes(key, ["A"], actor="stw", actor_role="steward")

    # A date from BEFORE the revoke must still resolve to the original (now-historical) meaning.
    result = repo.as_of(key, "A", mid_point)
    assert result is not None
    assert result["meaning"] == "Original meaning"
    # "Now" must resolve to the current (updated) meaning.
    now_result = repo.as_of(key, "A", datetime.now(timezone.utc))
    assert now_result["meaning"] == "Updated meaning"


def test_as_of_returns_not_found_inside_revoked_gap(repo):
    key = _key("asof_gap")
    _seed_approved(key, "A", "Active")
    repo.revoke_codes(key, ["A"], actor="ana", actor_role="analyst")
    # Code now sits in draft — no approved value exists right now.
    assert repo.as_of(key, "A", datetime.now(timezone.utc)) is None


def test_as_of_unknown_code_returns_not_found(repo):
    assert repo.as_of(_key("asof_missing"), "ZZZ", datetime.now(timezone.utc)) is None
