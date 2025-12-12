import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)
STATE_FILE = Path("data/orchestrator_state.json")


class OrchestratorState:
    def __init__(self):
        # Learning cycle state
        self._likes_since_last_retrain: int = 0
        self._last_retrain_at: Optional[str] = None
        self._last_like_at: Optional[str] = None
        self._total_retrains: int = 0
        self._total_likes_processed: int = 0
        self._is_retraining: bool = False
        self._last_error: Optional[str] = None

        # Batch generation state (NEW)
        self._last_batch_at: Optional[str] = None
        self._total_batches: int = 0
        self._last_batch_result: Optional[Dict[str, Any]] = None

        # Prompt generation state (NEW)
        self._last_generation_at: Optional[str] = None
        self._total_generations: int = 0
        self._last_generation_result: Optional[Dict[str, Any]] = None

        # Cached optimizer scores (NEW)
        self._cached_structure_scores: Dict[str, float] = {}
        self._scores_cached_at: Optional[str] = None

        self._load_state()

    def _load_state(self):
        try:
            if STATE_FILE.exists():
                with open(STATE_FILE, "r") as f:
                    data = json.load(f)
                    # Learning cycle
                    self._likes_since_last_retrain = data.get("likes_since_last_retrain", 0)
                    self._last_retrain_at = data.get("last_retrain_at")
                    self._last_like_at = data.get("last_like_at")
                    self._total_retrains = data.get("total_retrains", 0)
                    self._total_likes_processed = data.get("total_likes_processed", 0)
                    # Batch
                    self._last_batch_at = data.get("last_batch_at")
                    self._total_batches = data.get("total_batches", 0)
                    self._last_batch_result = data.get("last_batch_result")
                    # Generation
                    self._last_generation_at = data.get("last_generation_at")
                    self._total_generations = data.get("total_generations", 0)
                    self._last_generation_result = data.get("last_generation_result")
                    # Cached scores
                    self._cached_structure_scores = data.get("cached_structure_scores", {})
                    self._scores_cached_at = data.get("scores_cached_at")
                    logger.info(f"Loaded state: {self._likes_since_last_retrain} likes, {self._total_batches} batches")
        except Exception as e:
            logger.warning(f"Could not load state: {e}")

    def _save_state(self):
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(STATE_FILE, "w") as f:
                json.dump(
                    {
                        # Learning cycle
                        "likes_since_last_retrain": self._likes_since_last_retrain,
                        "last_retrain_at": self._last_retrain_at,
                        "last_like_at": self._last_like_at,
                        "total_retrains": self._total_retrains,
                        "total_likes_processed": self._total_likes_processed,
                        # Batch
                        "last_batch_at": self._last_batch_at,
                        "total_batches": self._total_batches,
                        "last_batch_result": self._last_batch_result,
                        # Generation
                        "last_generation_at": self._last_generation_at,
                        "total_generations": self._total_generations,
                        "last_generation_result": self._last_generation_result,
                        # Cached scores
                        "cached_structure_scores": self._cached_structure_scores,
                        "scores_cached_at": self._scores_cached_at,
                    },
                    f,
                    indent=2,
                )
        except Exception as e:
            logger.error(f"Could not save state: {e}")

    # =========================================================================
    # LEARNING CYCLE (existing)
    # =========================================================================

    def increment_likes(self) -> int:
        self._likes_since_last_retrain += 1
        self._total_likes_processed += 1
        self._last_like_at = datetime.now(timezone.utc).isoformat()
        self._save_state()
        return self._likes_since_last_retrain

    def reset_likes(self):
        self._likes_since_last_retrain = 0
        self._last_retrain_at = datetime.now(timezone.utc).isoformat()
        self._total_retrains += 1
        self._save_state()

    def set_retraining(self, is_retraining: bool):
        self._is_retraining = is_retraining

    def set_error(self, error: Optional[str]):
        self._last_error = error

    @property
    def likes_since_last_retrain(self) -> int:
        return self._likes_since_last_retrain

    @property
    def is_retraining(self) -> bool:
        return self._is_retraining

    # =========================================================================
    # BATCH GENERATION (new)
    # =========================================================================

    def record_batch(self, result: Dict[str, Any]):
        """Record a completed batch generation."""
        self._last_batch_at = datetime.now(timezone.utc).isoformat()
        self._total_batches += 1
        self._last_batch_result = result
        self._save_state()

    @property
    def last_batch_at(self) -> Optional[str]:
        return self._last_batch_at

    @property
    def total_batches(self) -> int:
        return self._total_batches

    # =========================================================================
    # PROMPT GENERATION (new)
    # =========================================================================

    def record_generation(self, result: Dict[str, Any]):
        """Record a completed prompt generation."""
        self._last_generation_at = datetime.now(timezone.utc).isoformat()
        self._total_generations += 1
        self._last_generation_result = result
        self._save_state()

    @property
    def last_generation_at(self) -> Optional[str]:
        return self._last_generation_at

    @property
    def total_generations(self) -> int:
        return self._total_generations

    # =========================================================================
    # CACHED SCORES (new)
    # =========================================================================

    def cache_scores(self, scores: Dict[str, float]):
        """Cache optimizer scores for use by Strategist."""
        self._cached_structure_scores = scores
        self._scores_cached_at = datetime.now(timezone.utc).isoformat()
        self._save_state()

    def get_cached_scores(self) -> Dict[str, float]:
        return self._cached_structure_scores

    @property
    def scores_cached_at(self) -> Optional[str]:
        return self._scores_cached_at

    def has_fresh_scores(self, max_age_hours: int = 24) -> bool:
        """Check if cached scores are fresh enough."""
        if not self._scores_cached_at:
            return False
        cached_time = datetime.fromisoformat(self._scores_cached_at.replace("Z", "+00:00"))
        age = datetime.now(timezone.utc) - cached_time
        return age.total_seconds() < (max_age_hours * 3600)

    # =========================================================================
    # STATUS
    # =========================================================================

    def get_status(self) -> Dict[str, Any]:
        return {
            # Learning cycle
            "likes_since_last_retrain": self._likes_since_last_retrain,
            "last_retrain_at": self._last_retrain_at,
            "last_like_at": self._last_like_at,
            "total_retrains": self._total_retrains,
            "total_likes_processed": self._total_likes_processed,
            "is_retraining": self._is_retraining,
            "last_error": self._last_error,
            # Batch
            "last_batch_at": self._last_batch_at,
            "total_batches": self._total_batches,
            "last_batch_result": self._last_batch_result,
            # Generation
            "last_generation_at": self._last_generation_at,
            "total_generations": self._total_generations,
            "last_generation_result": self._last_generation_result,
            # Scores
            "scores_cached_at": self._scores_cached_at,
            "cached_scores_count": len(self._cached_structure_scores),
        }


_state = OrchestratorState()


def get_state() -> OrchestratorState:
    return _state
