import json
from pathlib import Path

import pytest

import src.state as state_module


@pytest.fixture()
def isolated_state(tmp_path, monkeypatch):
    # point state to a temp file so tests do not touch real data/
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(state_module, "STATE_FILE", state_path)
    new_state = state_module.OrchestratorState()
    state_module._state = new_state
    return new_state


def test_increment_and_reset_updates_counters(isolated_state: state_module.OrchestratorState):
    assert isolated_state.likes_since_last_retrain == 0

    count_after_first = isolated_state.increment_likes()
    count_after_second = isolated_state.increment_likes()

    assert count_after_first == 1
    assert count_after_second == 2
    assert isolated_state.likes_since_last_retrain == 2

    isolated_state.reset_likes()
    assert isolated_state.likes_since_last_retrain == 0
    assert isolated_state.get_status()["total_retrains"] == 1


def test_state_persists_to_disk(isolated_state: state_module.OrchestratorState):
    isolated_state.increment_likes()
    state_file = state_module.STATE_FILE
    assert state_file.exists()

    persisted = json.loads(Path(state_file).read_text())
    assert persisted["likes_since_last_retrain"] == 1
    assert persisted["total_retrains"] == 0
