"""Tests for AuditStore — append-only contract, filters, AI call logging."""
from __future__ import annotations

import json
import pytest

from core.audit import AuditStore
from core.audit import events


@pytest.fixture()
def store(tmp_path):
    s = AuditStore(tmp_path / "audit.duckdb")
    yield s
    s.close()


class TestAppendOnly:
    def test_log_business_returns_id(self, store):
        row_id = store.log_business(events.GLOSSARY_TERM_CREATED, "glossary_term", "term-1", {"title": "Test"})
        assert isinstance(row_id, int)
        assert row_id >= 1

    def test_ids_are_monotonic(self, store):
        ids = [
            store.log_business(events.GLOSSARY_TERM_CREATED, "glossary_term", f"term-{i}", {})
            for i in range(5)
        ]
        assert ids == sorted(ids)
        assert len(set(ids)) == 5

    def test_no_update_delete_methods(self, store):
        assert not hasattr(store, "update_event")
        assert not hasattr(store, "delete_event")


class TestLifecycle:
    def test_close_is_idempotent(self, tmp_path):
        # Both the FastAPI lifespan shutdown and the atexit hook may call close();
        # a second call must be a no-op, not an error.
        s = AuditStore(tmp_path / "audit.duckdb")
        s.log_business(events.GLOSSARY_TERM_CREATED, "glossary_term", "t", {})
        s.close()
        s.close()  # must not raise

    def test_reopen_after_clean_close_releases_lock(self, tmp_path):
        # A cleanly-closed store releases the DuckDB lock so the next start opens
        # the same file without a stale-lock error.
        path = tmp_path / "audit.duckdb"
        first = AuditStore(path)
        first.log_business(events.GLOSSARY_TERM_CREATED, "glossary_term", "t", {})
        first.close()

        second = AuditStore(path)  # must open cleanly
        rows = second.list_events(limit=10)
        assert any(r["subject_id"] == "t" for r in rows)
        second.close()


class TestAiCallLogging:
    def test_log_ai_call_stored(self, store):
        row_id = store.log_ai_call(
            model="gpt-5.4-mini",
            subject_type="mapping",
            subject_id="banking_to_bird",
            prompt_tokens=150,
            completion_tokens=80,
            latency_ms=1230.5,
            confidence=0.92,
            prompt_id="mapping_agent._call_azure",
        )
        event = store.get_event(row_id)
        assert event is not None
        assert event["event_class"] == "ai"
        assert event["event_type"] == "ai.call"
        payload = event["payload"]
        assert payload["model"] == "gpt-5.4-mini"
        assert payload["prompt_tokens"] == 150
        assert payload["completion_tokens"] == 80
        assert payload["total_tokens"] == 230
        assert payload["latency_ms"] == 1230.5
        assert payload["confidence"] == 0.92


class TestFilters:
    @pytest.fixture(autouse=True)
    def seed(self, store):
        store.log_business(events.MAPPING_CANDIDATE_ACCEPTED, "mapping", "banking_to_bird:a→b", {"confidence": 0.9})
        store.log_business(events.MAPPING_CANDIDATE_REJECTED, "mapping", "banking_to_bird:c→d", {"confidence": 0.3})
        store.log_business(events.GLOSSARY_TERM_CREATED, "glossary_term", "term-1", {"title": "Liquidity"})
        store.log_ai_call(model="gpt-5.4-mini", subject_type="mapping", subject_id="banking_to_bird",
                          prompt_tokens=100, completion_tokens=50)

    def test_filter_by_event_class(self, store):
        ai_events = store.list_events(event_class="ai")
        assert all(e["event_class"] == "ai" for e in ai_events)
        assert len(ai_events) == 1

    def test_filter_by_event_type(self, store):
        events_list = store.list_events(event_type=events.GLOSSARY_TERM_CREATED)
        assert len(events_list) == 1
        assert events_list[0]["subject_id"] == "term-1"

    def test_filter_by_subject_type(self, store):
        mapping_events = store.list_events(subject_type="mapping")
        assert all(e["subject_type"] == "mapping" for e in mapping_events)

    def test_filter_by_subject_id_partial(self, store):
        results = store.list_events(subject_id="banking_to_bird")
        assert len(results) >= 2

    def test_list_all_returns_all(self, store):
        all_events = store.list_events(limit=100)
        assert len(all_events) == 4


class TestPayloadRoundTrip:
    def test_nested_payload_survives_roundtrip(self, store):
        original = {"nested": {"key": "value"}, "list": [1, 2, 3], "num": 3.14}
        row_id = store.log_business(events.MAPPING_SAVED, "mapping", "banking_to_bird", original)
        event = store.get_event(row_id)
        assert event["payload"] == original


class TestSummary:
    def test_summary_returns_list(self, store):
        store.log_business(events.GLOSSARY_TERM_CREATED, "glossary_term", "t1", {})
        store.log_ai_call(model="gpt-5.4-mini", subject_type="chat", subject_id="s1")
        result = store.summary(days=1)
        assert isinstance(result, list)
        for row in result:
            assert "day" in row
            assert "event_type" in row
            assert "count" in row
