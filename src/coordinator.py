import logging
from dataclasses import dataclass
from typing import Dict, Any, Optional

import httpx

from src.config import get_settings, Settings
from src.state import get_state, OrchestratorState

logger = logging.getLogger(__name__)


@dataclass
class BatchSettings:
    """Settings fetched from Airtable Daily Batch Settings table."""
    batch_enabled: bool = True
    default_num_prompts: int = 30
    default_renderer: str = "ImageFX"
    email_notifications: bool = True
    notification_email: str = ""


class LearningCycleCoordinator:
    """
    Coordinates the full autonomous workflow:
    1. Learning cycle (Optimizer train → score → insights → update Generator → update Airtable)
    2. Daily batch (check retrain → get scores → call Strategist → call Generator)
    3. Manual generation (call Generator with parameters)
    """

    def __init__(self):
        self.settings: Settings = get_settings()
        self.state: OrchestratorState = get_state()

    # =========================================================================
    # LEARNING CYCLE (existing, enhanced)
    # =========================================================================

    async def run_learning_cycle(self) -> Dict[str, Any]:
        """
        Execute the full learning cycle.
        Called when like threshold is reached or manually triggered.
        """
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
        }

        try:
            # Step 1: Train optimizer
            logger.info("Step 1/5: Training optimizer...")
            results["train"] = await self._train_optimizer()

            # Step 2: Score structures
            logger.info("Step 2/5: Scoring structures...")
            results["score"] = await self._score_structures()

            # Step 3: Get insights
            logger.info("Step 3/5: Getting insights...")
            results["insights"] = await self._get_structure_insights()

            # Step 4: Update generator
            logger.info("Step 4/5: Updating generator...")
            results["generator_update"] = await self._update_generator(
                results["score"], results["insights"]
            )

            # Step 5: Update Airtable
            logger.info("Step 5/5: Updating Airtable...")
            structures = results["score"].get("structures", [])
            results["airtable_update"] = await self._update_airtable_scores(structures)

            # Cache scores for Strategist use
            self._cache_optimizer_scores(results["score"])

            # Reset counter
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

    def _cache_optimizer_scores(self, score_response: Dict[str, Any]):
        """Cache optimizer scores for Strategist integration."""
        scores = {}
        for struct in score_response.get("structures", []):
            struct_id = struct.get("structure_id")
            score = struct.get("predicted_success_score")
            if struct_id and score is not None:
                scores[str(struct_id)] = score
        self.state.cache_scores(scores)
        logger.info(f"Cached {len(scores)} structure scores")

    # =========================================================================
    # DAILY BATCH (new)
    # =========================================================================

    async def run_daily_batch(
        self,
        force_retrain: bool = False,
    ) -> Dict[str, Any]:
        """
        Execute the daily batch workflow:
        1. Fetch batch settings from Airtable
        2. Check if retrain needed (threshold reached or forced)
        3. Get optimizer scores (fresh or cached)
        4. Call Strategist to generate ideas (with optimizer scores)
        5. Call Generator to create prompts (using Airtable settings)
        6. Return summary for N8n to send email
        """
        logger.info("STARTING DAILY BATCH")

        results = {
            "retrain_triggered": False,
            "retrain_result": None,
            "strategist_result": None,
            "generator_result": None,
            "ideas_generated": 0,
            "prompts_generated": 0,
            "success": False,
            "error": None,
        }

        try:
            # Step 1: Fetch batch settings from Airtable
            batch_settings = await self._fetch_batch_settings()
            logger.info(
                f"Batch settings: {batch_settings.default_num_prompts} prompts, "
                f"renderer={batch_settings.default_renderer}"
            )

            # Step 2: Check if retrain needed
            should_retrain = (
                force_retrain
                or self.state.likes_since_last_retrain >= self.settings.like_threshold
            )

            if should_retrain and not self.state.is_retraining:
                logger.info("Threshold reached or forced - running learning cycle first")
                results["retrain_triggered"] = True
                results["retrain_result"] = await self.run_learning_cycle()

            # Step 3: Get optimizer scores
            optimizer_scores = await self._get_optimizer_scores()

            # Step 4: Call Strategist with optimizer scores
            # (Strategist reads its own batchSize from Airtable)
            logger.info("Calling Strategist for new ideas...")
            results["strategist_result"] = await self._call_strategist(
                optimizer_scores=optimizer_scores,
            )
            results["ideas_generated"] = results["strategist_result"].get("totalGenerated", 0)

            # Step 5: Call Generator for prompts (using Airtable settings)
            logger.info(
                f"Calling Generator for {batch_settings.default_num_prompts} prompts "
                f"with renderer={batch_settings.default_renderer}..."
            )
            results["generator_result"] = await self._call_generator(
                num_prompts=batch_settings.default_num_prompts,
                renderer=batch_settings.default_renderer,
            )
            results["prompts_generated"] = len(
                results["generator_result"].get("prompts", [])
            )

            # Record batch
            self.state.record_batch({
                "ideas": results["ideas_generated"],
                "prompts": results["prompts_generated"],
                "retrain_triggered": results["retrain_triggered"],
            })

            results["success"] = True
            logger.info(
                f"DAILY BATCH COMPLETE: {results['ideas_generated']} ideas, "
                f"{results['prompts_generated']} prompts"
            )

        except Exception as e:
            logger.error(f"Daily batch failed: {e}")
            results["error"] = str(e)
            self.state.set_error(str(e))

        return results

    async def _fetch_batch_settings(self) -> BatchSettings:
        """Fetch batch settings from Airtable Daily Batch Settings table."""
        if not self.settings.airtable_api_key:
            logger.warning("No Airtable API key - using fallback settings")
            return BatchSettings(
                default_num_prompts=self.settings.fallback_num_prompts,
                default_renderer=self.settings.fallback_renderer,
            )

        url = (
            f"https://api.airtable.com/v0/"
            f"{self.settings.airtable_base_id}/"
            f"{self.settings.airtable_batch_settings_table_id}"
        )
        headers = {
            "Authorization": f"Bearer {self.settings.airtable_api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(url, headers=headers, params={"maxRecords": 1})
                response.raise_for_status()
                data = response.json()

                records = data.get("records", [])
                if not records:
                    logger.warning("No batch settings record found - using fallbacks")
                    return BatchSettings(
                        default_num_prompts=self.settings.fallback_num_prompts,
                        default_renderer=self.settings.fallback_renderer,
                    )

                fields = records[0].get("fields", {})
                return BatchSettings(
                    batch_enabled=fields.get("batchEnabled", True),
                    default_num_prompts=fields.get("numPrompts", self.settings.fallback_num_prompts),
                    default_renderer=fields.get("renderer", self.settings.fallback_renderer),
                    email_notifications=fields.get("emailNotifications", True),
                    notification_email=fields.get("notificationEmail", ""),
                )

        except Exception as e:
            logger.error(f"Failed to fetch batch settings: {e} - using fallbacks")
            return BatchSettings(
                default_num_prompts=self.settings.fallback_num_prompts,
                default_renderer=self.settings.fallback_renderer,
            )

    async def _get_optimizer_scores(self) -> Dict[str, float]:
        """Get optimizer scores - fresh if stale, cached otherwise."""
        if self.state.has_fresh_scores(max_age_hours=24):
            logger.info("Using cached optimizer scores")
            return self.state.get_cached_scores()

        logger.info("Fetching fresh optimizer scores")
        try:
            score_response = await self._score_structures()
            self._cache_optimizer_scores(score_response)
            return self.state.get_cached_scores()
        except Exception as e:
            logger.warning(f"Could not fetch fresh scores: {e}, using cached")
            return self.state.get_cached_scores()

    async def _call_strategist(
        self,
        optimizer_scores: Dict[str, float],
    ) -> Dict[str, Any]:
        """
        Call Strategist to generate new structure ideas.
        Passes optimizer scores so ideas are guided by ML predictions.
        Note: Strategist reads its own batchSize from Airtable.
        """
        url = f"{self.settings.strategist_service_url}/api/batch/run"

        # Pass optimizer_scores in the body for Strategist to consider
        # Strategist reads batchSize from its own Airtable settings
        payload = {
            "optimizer_scores": optimizer_scores,
            "exploration_rate": self.settings.exploration_rate,
        }

        async with httpx.AsyncClient(timeout=self.settings.strategist_timeout) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return response.json()

    # =========================================================================
    # MANUAL GENERATION (new)
    # =========================================================================

    async def run_manual_generation(
        self,
        num_prompts: int,
        renderer: Optional[str] = None,
        force_retrain: bool = False,
    ) -> Dict[str, Any]:
        """
        Execute manual prompt generation:
        1. Optionally trigger learning cycle
        2. Call Generator with specified parameters
        """
        logger.info(f"STARTING MANUAL GENERATION: {num_prompts} prompts, renderer={renderer}")

        results = {
            "retrain_triggered": False,
            "retrain_result": None,
            "generator_result": None,
            "prompts_generated": 0,
            "success": False,
            "error": None,
        }

        try:
            # Optional retrain
            if force_retrain and not self.state.is_retraining:
                logger.info("Force retrain requested")
                results["retrain_triggered"] = True
                results["retrain_result"] = await self.run_learning_cycle()

            # Call Generator
            logger.info("Calling Generator...")
            results["generator_result"] = await self._call_generator(
                num_prompts=num_prompts,
                renderer=renderer or self.settings.fallback_renderer,
            )
            results["prompts_generated"] = len(
                results["generator_result"].get("prompts", [])
            )

            # Record generation
            self.state.record_generation({
                "prompts": results["prompts_generated"],
                "renderer": renderer or self.settings.fallback_renderer,
                "manual": True,
            })

            results["success"] = True
            logger.info(f"MANUAL GENERATION COMPLETE: {results['prompts_generated']} prompts")

        except Exception as e:
            logger.error(f"Manual generation failed: {e}")
            results["error"] = str(e)
            self.state.set_error(str(e))

        return results

    async def _call_generator(
        self,
        num_prompts: int,
        renderer: str,
    ) -> Dict[str, Any]:
        """Call Generator to create prompts."""
        url = f"{self.settings.generator_service_url}/generate-prompts"

        payload = {
            "num_prompts": num_prompts,
            "renderer": renderer,
        }

        async with httpx.AsyncClient(timeout=self.settings.generator_timeout) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return response.json()

    # =========================================================================
    # OPTIMIZER INTEGRATION (existing)
    # =========================================================================

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

    async def _update_generator(
        self, score_response: Dict[str, Any], insights_response: Dict[str, Any]
    ) -> Dict[str, Any]:
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
        headers = {
            "Authorization": f"Bearer {self.settings.airtable_api_key}",
            "Content-Type": "application/json",
        }

        updated = 0
        async with httpx.AsyncClient(timeout=30) as client:
            for struct in structures:
                struct_id = struct.get("structure_id")
                score = struct.get("predicted_success_score")
                if struct_id and score is not None:
                    try:
                        response = await client.patch(
                            f"{url}/{struct_id}",
                            headers=headers,
                            json={"fields": {"optimizer_score": score}},
                        )
                        if response.status_code == 200:
                            updated += 1
                    except Exception:
                        pass

        return {"status": "completed", "updated": updated, "total": len(structures)}


_coordinator = LearningCycleCoordinator()


def get_coordinator() -> LearningCycleCoordinator:
    return _coordinator
