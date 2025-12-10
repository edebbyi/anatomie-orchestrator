import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from orchestrator.config import get_settings
from orchestrator.coordinator import get_coordinator
from orchestrator.state import get_state

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Orchestrator Service...")
    yield
    logger.info("Shutting down...")


app = FastAPI(title="Anatomie Orchestrator", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LikeEventRequest(BaseModel):
    record_id: Optional[str] = None
    structure_id: Optional[str] = None
    image_url: Optional[str] = None


class LikeEventResponse(BaseModel):
    status: str
    likes_since_last_retrain: int
    threshold: int
    threshold_reached: bool
    retrain_triggered: bool
    message: str


@app.get("/")
async def root():
    return {"service": "anatomie-orchestrator", "status": "running"}


@app.get("/health")
async def health():
    state = get_state()
    settings = get_settings()
    return {
        "status": "healthy",
        "likes_since_last_retrain": state.likes_since_last_retrain,
        "threshold": settings.like_threshold,
        "is_retraining": state.is_retraining,
    }


@app.get("/status")
async def get_status():
    state = get_state()
    settings = get_settings()
    return {"service": "anatomie-orchestrator", "threshold": settings.like_threshold, **state.get_status()}


@app.post("/like_event", response_model=LikeEventResponse)
async def receive_like_event(request: LikeEventRequest, background_tasks: BackgroundTasks):
    state = get_state()
    settings = get_settings()

    if state.is_retraining:
        return LikeEventResponse(
            status="queued",
            likes_since_last_retrain=state.likes_since_last_retrain,
            threshold=settings.like_threshold,
            threshold_reached=False,
            retrain_triggered=False,
            message="Retrain in progress",
        )

    new_count = state.increment_likes()
    threshold_reached = new_count >= settings.like_threshold

    if threshold_reached:
        background_tasks.add_task(get_coordinator().run_learning_cycle)
        return LikeEventResponse(
            status="threshold_reached",
            likes_since_last_retrain=new_count,
            threshold=settings.like_threshold,
            threshold_reached=True,
            retrain_triggered=True,
            message="Threshold reached. Learning cycle triggered.",
        )

    return LikeEventResponse(
        status="counted",
        likes_since_last_retrain=new_count,
        threshold=settings.like_threshold,
        threshold_reached=False,
        retrain_triggered=False,
        message=f"{settings.like_threshold - new_count} more until retrain.",
    )


@app.post("/trigger_retrain")
async def trigger_retrain(background_tasks: BackgroundTasks):
    state = get_state()
    if state.is_retraining:
        raise HTTPException(status_code=409, detail="Retrain already in progress")
    background_tasks.add_task(get_coordinator().run_learning_cycle)
    return {"status": "triggered"}


@app.post("/reset_counter")
async def reset_counter():
    state = get_state()
    old_count = state.likes_since_last_retrain
    state.reset_likes()
    return {"status": "reset", "previous_count": old_count}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
