import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)
STATE_FILE = Path("data/orchestrator_state.json")


class OrchestratorState:
    def __init__(self):
        self._likes_since_last_retrain: int = 0
        self._last_retrain_at: Optional[str] = None
        self._last_like_at: Optional[str] = None
        self._total_retrains: int = 0
        self._total_likes_processed: int = 0
        self._last_error: Optional[str] = None
        self._is_retraining: bool = False
        self._load_state()

    def _load_state(self):
        try:
            if STATE_FILE.exists():
                with open(STATE_FILE, "r") as f:
                    data = json.load(f)
                    self._likes_since_last_retrain = data.get("likes_since_last_retrain", 0)
                    self._last_retrain_at = data.get("last_retrain_at")
                    self._last_like_at = data.get("last_like_at")
                    self._total_retrains = data.get("total_retrains", 0)
                    self._total_likes_processed = data.get("total_likes_processed", 0)
        except Exception as e:  # pragma: no cover - defensive logging
            logger.warning(f"Could not load state: {e}")

    def _save_state(self):
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(STATE_FILE, "w") as f:
                json.dump(
                    {
                        "likes_since_last_retrain": self._likes_since_last_retrain,
                        "last_retrain_at": self._last_retrain_at,
                        "last_like_at": self._last_like_at,
                        "total_retrains": self._total_retrains,
                        "total_likes_processed": self._total_likes_processed,
                    },
                    f,
                    indent=2,
                )
        except Exception as e:  # pragma: no cover - defensive logging
            logger.error(f"Could not save state: {e}")

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

    def get_status(self) -> Dict[str, Any]:
        return {
            "likes_since_last_retrain": self._likes_since_last_retrain,
            "last_retrain_at": self._last_retrain_at,
            "last_like_at": self._last_like_at,
            "total_retrains": self._total_retrains,
            "total_likes_processed": self._total_likes_processed,
            "is_retraining": self._is_retraining,
            "last_error": self._last_error,
        }


_state = OrchestratorState()


def get_state() -> OrchestratorState:
    return _state
