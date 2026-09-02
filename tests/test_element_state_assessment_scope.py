"""Tests for the assessment_scope governance fact on ElementStateStore (D1).

Assessment scope + description are content methods, Postgres-only since Slice F -- they land
wherever ``ADM_DATABASE_URL``/project.yaml already points (this file makes no assumption about
which database that is), so this file cleans up its own test keys before/after each test to
avoid leaving anything behind.
"""
from __future__ import annotations

import pytest

from core.element_state import ElementStateStore


@pytest.fixture(autouse=True)
def _clean_rows():
    from sqlalchemy import delete
    from core.glossary_db.db import session_scope
    from core.shared.models import ElementAssessmentScope, ElementDefinition

    def _wipe():
        try:
            with session_scope() as s:
                s.execute(delete(ElementDefinition).where(ElementDefinition.element_key.like("s|sc|t|%")))
                s.execute(delete(ElementAssessmentScope).where(ElementAssessmentScope.element_key.like("s|sc|t|%")))
        except Exception:
            pass  # Postgres unreachable -- tests below will fail on their own merits

    _wipe()
    yield
    _wipe()


def _store(tmp_path):
    return ElementStateStore(tmp_path / "element_states.yaml")


def test_default_scope_is_in_scope(tmp_path):
    store = _store(tmp_path)
    assert store.get_assessment_scope("s", "sc", "t", "c") == "in_scope"


def test_set_out_of_scope_persists(tmp_path):
    store = _store(tmp_path)
    store.set_assessment_scope("s", "sc", "t", "c", "out_of_scope",
                               scope_reason="technical column", scoped_by="tester")
    assert store.get_assessment_scope("s", "sc", "t", "c") == "out_of_scope"
    record = store.get_assessment_scope_record("s", "sc", "t", "c")
    assert record["scope"] == "out_of_scope"
    assert record["scope_reason"] == "technical column"
    assert record["scoped_by"] == "tester"
    assert record["scoped_at"]


def test_scope_survives_reload(tmp_path):
    path = tmp_path / "element_states.yaml"
    store = ElementStateStore(path)
    store.set_assessment_scope("s", "sc", "t", "c", "out_of_scope")
    reloaded = ElementStateStore(path)
    assert reloaded.get_assessment_scope("s", "sc", "t", "c") == "out_of_scope"


def test_invalid_scope_rejected(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(ValueError):
        store.set_assessment_scope("s", "sc", "t", "c", "banana")


def test_scope_does_not_disturb_other_facts(tmp_path):
    store = _store(tmp_path)
    store.set_description("s", "sc", "t", "c", "hello")
    store.set_assessment_scope("s", "sc", "t", "c", "out_of_scope")
    assert store.get_description("s", "sc", "t", "c") == "hello"
    assert store.get("s", "sc", "t", "c") in ("draft", "defined", "approved")
