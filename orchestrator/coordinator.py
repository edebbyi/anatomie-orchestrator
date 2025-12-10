import logging
from typing import Dict, Any

import httpx

from orchestrator.config import get_settings
from orchestrator.state import get_state

logger = logging.getLogger(__name__)


class LearningCycleCoordinator:
    def __init__(self):
        self.settings = get_settings()
        self.state = get_state()

    async def run_learning_cycle(self) -> Dict[str, Any]:
        logger.info("STARTING LEARNING CYCLE")
        self.state.set_retraining(True)
        self.state.set_error(None)

        results = {
            "train": None,
            "score": None,
            "insights": None,
            "generator_update": None,
            "airtable_update": None,
            "success": False,
            "error": None,
        }

        try:
            # Step 1: Train
            logger.info("Step 1/5: Training Optimizer...")
            results["train"] = await self._train_optimizer()
            if results["train"].get("status") == "error":
                raise Exception(f"Training failed: {results['train'].get('error')}")

            # Step 2: Score
            logger.info("Step 2/5: Scoring Structures...")
            results["score"] = await self._score_structures()
            if "error" in results["score"]:
                raise Exception(f"Scoring failed: {results['score'].get('error')}")

            # Step 3: Insights
            logger.info("Step 3/5: Getting Structure Prompt Insights...")
            results["insights"] = await self._get_structure_insights()

            # Step 4: Update Generator
            logger.info("Step 4/5: Updating Generator Preferences...")
            results["generator_update"] = await self._update_generator(results["score"], results["insights"])

            # Step 5: Update Airtable
            logger.info("Step 5/5: Updating Airtable...")
            results["airtable_update"] = await self._update_airtable_scores(results["score"].get("structures", []))

            self.state.reset_likes()
            results["success"] = True
            logger.info("LEARNING CYCLE COMPLETE")

        except Exception as e:
            logger.error(f"Learning cycle failed: {e}")
            results["error"] = str(e)
            self.state.set_error(str(e))
        finally:
            self.state.set_retraining(False)

        return results

    async def _train_optimizer(self) -> Dict[str, Any]:
        url = f"{self.settings.optimizer_service_url}/train"
        async with httpx.AsyncClient(timeout=self.settings.train_timeout) as client:
            response = await client.post(url, json={})
            response.raise_for_status()
            return response.json()

    async def _score_structures(self) -> Dict[str, Any]:
        url = f"{self.settings.optimizer_service_url}/score_structures"
        async with httpx.AsyncClient(timeout=self.settings.score_timeout) as client:
            response = await client.post(url, json={})
            response.raise_for_status()
            return response.json()

    async def _get_structure_insights(self) -> Dict[str, Any]:
        url = f"{self.settings.optimizer_service_url}/structure_prompt_insights"
        try:
            async with httpx.AsyncClient(timeout=self.settings.score_timeout) as client:
                response = await client.get(url)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.warning(f"Could not get structure insights: {e}")
            return {"status": "not_available", "insights": {}}

    async def _update_generator(self, score_response: Dict[str, Any], insights_response: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.settings.generator_service_url}/update_preferences"

        structure_scores = {}
        for struct in score_response.get("structures", []):
            struct_id = struct.get("structure_id")
            if struct_id:
                structure_scores[str(struct_id)] = struct.get("predicted_success_score", 0.5)

        payload = {
            "global_preference_vector": score_response.get("global_preference_vector", {}),
            "exploration_rate": self.settings.exploration_rate,
            "structure_scores": structure_scores,
            "structure_prompt_insights": insights_response.get("insights", {}),
        }

        async with httpx.AsyncClient(timeout=self.settings.update_timeout) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return response.json()

    async def _update_airtable_scores(self, structures: list) -> Dict[str, Any]:
        if not self.settings.airtable_api_key:
            return {"status": "skipped", "reason": "No API key"}

        url = f"https://api.airtable.com/v0/{self.settings.airtable_base_id}/{self.settings.airtable_structures_table_id}"
        headers = {"Authorization": f"Bearer {self.settings.airtable_api_key}", "Content-Type": "application/json"}

        updated = 0
        async with httpx.AsyncClient(timeout=30) as client:
            for struct in structures:
                struct_id = struct.get("structure_id")
                score = struct.get("predicted_success_score")
                if struct_id and score is not None:
                    try:
                        response = await client.patch(
                            f"{url}/{struct_id}", headers=headers, json={"fields": {"optimizer_score": score}}
                        )
                        if response.status_code == 200:
                            updated += 1
                    except Exception:
                        pass

        return {"status": "completed", "updated": updated, "total": len(structures)}


_coordinator = LearningCycleCoordinator()


def get_coordinator() -> LearningCycleCoordinator:
    return _coordinator
