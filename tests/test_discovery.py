"""Tests for Discovery API."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from api.main import app
from tests._pg_semantic_type_isolation import restore_real_semantic_type_rows

_restore_banking_semantic_types = restore_real_semantic_type_rows("banking|")


def _parse_sse(body: str) -> list[tuple[str, dict]]:
    frames: list[tuple[str, dict]] = []
    for block in body.strip().split("\n\n"):
        event = data = None
        for line in block.splitlines():
            if line.startswith("event: "):
                event = line[len("event: "):].strip()
            elif line.startswith("data: "):
                data = line[len("data: "):]
        if event and data:
            frames.append((event, json.loads(data)))
    return frames


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def test_table_stats(client: TestClient):
    resp = client.get("/discovery/banking/accounts/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["table_name"] == "accounts"
    assert "columns" in body


def test_stats_missing_dataset(client: TestClient):
    resp = client.get("/discovery/nonexistent/foo/stats")
    assert resp.status_code == 404


def test_stats_missing_table(client: TestClient):
    resp = client.get("/discovery/banking/nonexistent/stats")
    assert resp.status_code == 404


def test_refresh_triggers_full_dq_rescore(client: TestClient, monkeypatch):
    """A profile refresh re-scores every column + re-rolls the dataset (so
    "Last evaluated" can sync with "Last profiled at" for this instance) —
    proven by spying on the DQ service rather than requiring the profiling
    stats to actually change (the store dedups unchanged signals, DQ §16.2)."""
    service = client.app.state.dq_service
    assert service is not None

    column_calls: list[tuple] = []
    dataset_calls: list[tuple] = []
    orig_persist = service.score_and_persist
    orig_persist_dataset = service.score_and_persist_dataset

    def spy_persist(*args, **kwargs):
        column_calls.append(args)
        return orig_persist(*args, **kwargs)

    def spy_persist_dataset(*args, **kwargs):
        dataset_calls.append(args)
        return orig_persist_dataset(*args, **kwargs)

    monkeypatch.setattr(service, "score_and_persist", spy_persist)
    monkeypatch.setattr(service, "score_and_persist_dataset", spy_persist_dataset)

    resp = client.post("/discovery/banking/accounts/refresh")
    assert resp.status_code == 200

    assert len(column_calls) > 0  # every column got re-scored
    assert len(dataset_calls) == 1  # the dataset roll-up re-rolled once


def test_refresh_also_triggers_semantic_resolve(client: TestClient, monkeypatch):
    """SD-R5 (2026-08-12): a profile refresh always re-derives semantic types
    too — the same forced pairing this endpoint already gives DQ, so semantic
    types can never silently lag a fresh profile either."""
    import core.semantic_resolver as semantic_resolver

    calls: list[tuple] = []
    orig_resolve_table = semantic_resolver.SemanticResolver.resolve_table

    def spy_resolve_table(self, **kwargs):
        calls.append((kwargs.get("source"), (kwargs.get("table") or {}).get("table_name")))
        return orig_resolve_table(self, **kwargs)

    monkeypatch.setattr(semantic_resolver.SemanticResolver, "resolve_table", spy_resolve_table)

    resp = client.post("/discovery/banking/accounts/refresh")
    assert resp.status_code == 200
    assert len(calls) == 1
    assert calls[0][0] == "banking"


def test_rebuild_all_defaults_include_semantic_and_dq(client: TestClient, monkeypatch):
    """SD-R5: bulk rebuild defaults BOTH steps on — opt-out, not opt-in — and
    runs them per table via the SAME helpers the single-table endpoint uses."""
    import core.semantic_resolver as semantic_resolver

    service = client.app.state.dq_service
    assert service is not None
    dq_calls: list[tuple] = []
    orig_persist = service.score_and_persist
    monkeypatch.setattr(
        service, "score_and_persist",
        lambda *a, **k: (dq_calls.append(a), orig_persist(*a, **k))[1],
    )

    sem_calls: list[tuple] = []
    orig_resolve_table = semantic_resolver.SemanticResolver.resolve_table

    def spy_resolve_table(self, **kwargs):
        sem_calls.append((kwargs.get("source"), (kwargs.get("table") or {}).get("table_name")))
        return orig_resolve_table(self, **kwargs)

    monkeypatch.setattr(semantic_resolver.SemanticResolver, "resolve_table", spy_resolve_table)

    resp = client.post("/discovery/banking/rebuild-all")
    assert resp.status_code == 200
    frames = _parse_sse(resp.text)
    assert frames[0][0] == "started"
    assert frames[0][1]["include_semantic"] is True
    assert frames[0][1]["include_dq"] is True
    assert frames[-1][0] == "done"
    assert len(dq_calls) > 0
    assert len(sem_calls) > 0


def test_rebuild_all_can_skip_semantic_and_dq(client: TestClient, monkeypatch):
    """SD-R5: include_semantic=false/include_dq=false skips both steps entirely
    — profiling itself still runs and completes normally."""
    import core.semantic_resolver as semantic_resolver

    service = client.app.state.dq_service
    assert service is not None
    dq_calls: list[tuple] = []
    monkeypatch.setattr(
        service, "score_and_persist", lambda *a, **k: dq_calls.append(a),
    )
    sem_calls: list[tuple] = []
    monkeypatch.setattr(
        semantic_resolver.SemanticResolver, "resolve_table",
        lambda self, **k: sem_calls.append(k) or {"entity": {}, "columns": [], "findings": []},
    )

    resp = client.post("/discovery/banking/rebuild-all?include_semantic=false&include_dq=false")
    assert resp.status_code == 200
    frames = _parse_sse(resp.text)
    assert frames[0][1]["include_semantic"] is False
    assert frames[0][1]["include_dq"] is False
    done = frames[-1][1]
    assert done["completed"] > 0
    assert len(dq_calls) == 0
    assert len(sem_calls) == 0
