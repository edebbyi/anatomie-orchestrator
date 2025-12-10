import asyncio
import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import orchestrator.state as state_module
import orchestrator.coordinator as coordinator_module


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    # keep state isolated
    monkeypatch.setenv("LIKE_THRESHOLD", "2")
    monkeypatch.setattr(state_module, "STATE_FILE", tmp_path / "state.json")
    fresh_state = state_module.OrchestratorState()
    state_module._state = fresh_state

    # rewire coordinator to use the new state and stub the learning cycle
    coord = coordinator_module.get_coordinator()
    coord.state = fresh_state

    async def fake_cycle():
        fresh_state.reset_likes()
        return {"success": True}

    monkeypatch.setattr(coord, "run_learning_cycle", fake_cycle)

    # reload main after monkeypatching state so app uses isolated state
    main = importlib.reload(importlib.import_module("orchestrator.main"))
    client = TestClient(main.app)
    yield client


def test_health_endpoint_reports_counts(app_client: TestClient):
    response = app_client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["likes_since_last_retrain"] == 0
    assert body["threshold"] == 2


def test_like_event_threshold_triggers_background_cycle(app_client: TestClient):
    first = app_client.post("/like_event", json={"record_id": "one"})
    assert first.status_code == 200
    assert first.json()["threshold_reached"] is False

    second = app_client.post("/like_event", json={"record_id": "two"})
    assert second.status_code == 200
    body = second.json()
    assert body["status"] == "threshold_reached"
    assert body["threshold_reached"] is True
    assert body["retrain_triggered"] is True

    # background task should have reset likes
    health = app_client.get("/health").json()
    assert health["likes_since_last_retrain"] == 0
