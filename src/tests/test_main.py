import asyncio
import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import src.state as state_module
import src.coordinator as coordinator_module


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    # keep state isolated
    monkeypatch.setenv("LIKE_THRESHOLD", "2")
    monkeypatch.setattr(state_module, "STATE_FILE", tmp_path / "state.json")
    fresh_state = state_module.OrchestratorState()
    state_module._state = fresh_state

    # rewire coordinator to use the new state and stub workflows
    coord = coordinator_module.get_coordinator()
    coord.state = fresh_state

    async def fake_cycle():
        fresh_state.reset_likes()
        return {"success": True}

    async def fake_daily_batch(*args, **kwargs):
        return {
            "success": True,
            "retrain_triggered": False,
            "ideas_generated": 3,
            "prompts_generated": 4,
            "error": None,
        }

    async def fake_manual_generation(*args, **kwargs):
        return {
            "success": True,
            "retrain_triggered": False,
            "prompts_generated": 2,
            "error": None,
        }

    monkeypatch.setattr(coord, "run_learning_cycle", fake_cycle)
    monkeypatch.setattr(coord, "run_daily_batch", fake_daily_batch)
    monkeypatch.setattr(coord, "run_manual_generation", fake_manual_generation)

    # reload main after monkeypatching state so app uses isolated state
    main = importlib.reload(importlib.import_module("src.main"))
    client = TestClient(main.app)
    yield client


def test_health_endpoint_reports_counts(app_client: TestClient):
    response = app_client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["likes_since_last_retrain"] == 0
    assert body["threshold"] == 2
    assert body["total_batches"] == 0


def test_like_event_threshold_triggers_background_cycle(app_client: TestClient):
    first = app_client.post("/events/like", json={"record_id": "one"})
    assert first.status_code == 200
    assert first.json()["threshold_reached"] is False

    second = app_client.post("/events/like", json={"record_id": "two"})
    assert second.status_code == 200
    body = second.json()
    assert body["status"] == "threshold_reached"
    assert body["threshold_reached"] is True
    assert body["retrain_triggered"] is True

    # background task should have reset likes
    health = app_client.get("/health").json()
    assert health["likes_since_last_retrain"] == 0


def test_daily_batch_returns_summary(app_client: TestClient):
    response = app_client.post("/events/daily_batch", json={})
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert "structure ideas generated" in body["summary"]


def test_manual_generate_endpoint(app_client: TestClient):
    response = app_client.post("/events/manual_generate", json={"num_prompts": 2})
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["prompts_generated"] == 2
