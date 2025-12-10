import json
import pytest
import respx
import httpx

from orchestrator.coordinator import LearningCycleCoordinator
import orchestrator.state as state_module


@pytest.fixture()
def coordinator(tmp_path, monkeypatch):
    # set fake URLs and config overrides before coordinator initialization
    monkeypatch.setenv("OPTIMIZER_SERVICE_URL", "http://optimizer.test")
    monkeypatch.setenv("GENERATOR_SERVICE_URL", "http://generator.test")
    monkeypatch.setenv("EXPLORATION_RATE", "0.3")

    # isolate state persistence
    monkeypatch.setattr(state_module, "STATE_FILE", tmp_path / "state.json")
    state_module._state = state_module.OrchestratorState()
    coord = LearningCycleCoordinator()
    return coord


@pytest.mark.asyncio
@respx.mock
async def test_update_generator_sends_scores(monkeypatch, coordinator: LearningCycleCoordinator):
    update_route = respx.post("http://generator.test/update_preferences").mock(
        return_value=httpx.Response(200, json={"status": "ok"})
    )

    score_response = {
        "global_preference_vector": {"a": 1},
        "structures": [
            {"structure_id": "s1", "predicted_success_score": 0.8},
            {"structure_id": "s2", "predicted_success_score": 0.6},
        ],
    }
    insights_response = {"insights": {"s1": {"text": "good"}}}

    result = await coordinator._update_generator(score_response, insights_response)  # noqa: SLF001
    assert result["status"] == "ok"

    assert update_route.called
    sent_json = json.loads(update_route.calls[0].request.content)
    assert sent_json["exploration_rate"] == 0.3
    assert sent_json["structure_scores"] == {"s1": 0.8, "s2": 0.6}
    assert sent_json["structure_prompt_insights"] == {"s1": {"text": "good"}}
