import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.config import get_settings
from src.coordinator import get_coordinator
from src.state import get_state

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Orchestrator Service v2.0...")
    yield
    logger.info("Shutting down...")


app = FastAPI(title="Anatomie Orchestrator", version="2.0.0", lifespan=lifespan)
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


class DailyBatchRequest(BaseModel):
    force_retrain: bool = False
    num_ideas: Optional[int] = None
    num_prompts: Optional[int] = None
    renderer: Optional[str] = None


class DailyBatchResponse(BaseModel):
    success: bool
    retrain_triggered: bool
    ideas_generated: int
    prompts_generated: int
    summary: str
    error: Optional[str] = None


class ManualGenerateRequest(BaseModel):
    num_prompts: int = 12
    renderer: Optional[str] = None
    force_retrain: bool = False


class ManualGenerateResponse(BaseModel):
    success: bool
    retrain_triggered: bool
    prompts_generated: int
    renderer: str
    error: Optional[str] = None


@app.get("/")
async def root():
    return {"service": "anatomie-orchestrator", "version": "2.0.0", "status": "running"}


@app.get("/health")
async def health():
    state = get_state()
    settings = get_settings()
    return {
        "status": "healthy",
        "likes_since_last_retrain": state.likes_since_last_retrain,
        "threshold": settings.like_threshold,
        "is_retraining": state.is_retraining,
        "total_batches": state.total_batches,
        "total_generations": state.total_generations,
    }


@app.get("/status")
async def get_status():
    state = get_state()
    settings = get_settings()
    return {
        "service": "anatomie-orchestrator",
        "version": "2.0.0",
        "threshold": settings.like_threshold,
        "exploration_rate": settings.exploration_rate,
        **state.get_status(),
    }


@app.post("/events/daily_batch", response_model=DailyBatchResponse)
async def handle_daily_batch(request: DailyBatchRequest):
    state = get_state()

    if state.is_retraining:
        return DailyBatchResponse(
            success=False,
            retrain_triggered=False,
            ideas_generated=0,
            prompts_generated=0,
            summary="Retrain in progress. Try again later.",
            error="retrain_in_progress",
        )

    coordinator = get_coordinator()
    result = await coordinator.run_daily_batch(
        force_retrain=request.force_retrain,
        num_ideas=request.num_ideas,
        num_prompts=request.num_prompts,
        renderer=request.renderer,
    )

    parts = []
    if result["retrain_triggered"]:
        parts.append("Learning cycle completed")
    parts.append(f"{result['ideas_generated']} new structure ideas generated")
    parts.append(f"{result['prompts_generated']} prompts created")
    summary = ". ".join(parts) + "."

    return DailyBatchResponse(
        success=result["success"],
        retrain_triggered=result["retrain_triggered"],
        ideas_generated=result["ideas_generated"],
        prompts_generated=result["prompts_generated"],
        summary=summary,
        error=result.get("error"),
    )


@app.post("/events/manual_generate", response_model=ManualGenerateResponse)
async def handle_manual_generate(request: ManualGenerateRequest):
    state = get_state()
    settings = get_settings()

    if state.is_retraining:
        return ManualGenerateResponse(
            success=False,
            retrain_triggered=False,
            prompts_generated=0,
            renderer=request.renderer or settings.default_renderer,
            error="retrain_in_progress",
        )

    coordinator = get_coordinator()
    result = await coordinator.run_manual_generation(
        num_prompts=request.num_prompts,
        renderer=request.renderer,
        force_retrain=request.force_retrain,
    )

    return ManualGenerateResponse(
        success=result["success"],
        retrain_triggered=result["retrain_triggered"],
        prompts_generated=result["prompts_generated"],
        renderer=request.renderer or settings.default_renderer,
        error=result.get("error"),
    )


@app.post("/events/like", response_model=LikeEventResponse)
async def handle_like_event(request: LikeEventRequest, background_tasks: BackgroundTasks):
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
        status="recorded",
        likes_since_last_retrain=new_count,
        threshold=settings.like_threshold,
        threshold_reached=False,
        retrain_triggered=False,
        message=f"Like recorded. {settings.like_threshold - new_count} until next learning cycle.",
    )


@app.post("/like_event", response_model=LikeEventResponse)
async def receive_like_event(request: LikeEventRequest, background_tasks: BackgroundTasks):
    return await handle_like_event(request, background_tasks)


@app.post("/trigger_retrain")
async def trigger_retrain(background_tasks: BackgroundTasks):
    state = get_state()

    if state.is_retraining:
        raise HTTPException(status_code=409, detail="Retrain already in progress")

    background_tasks.add_task(get_coordinator().run_learning_cycle)
    return {
        "status": "triggered",
        "message": "Learning cycle started in background",
    }


@app.post("/reset_counter")
async def reset_counter():
    state = get_state()
    state.reset_likes()
    return {"status": "reset", "likes_since_last_retrain": 0}


@app.get("/scores")
async def get_cached_scores():
    state = get_state()
    return {
        "scores": state.get_cached_scores(),
        "cached_at": state.scores_cached_at,
        "is_fresh": state.has_fresh_scores(),
        "count": len(state.get_cached_scores()),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
