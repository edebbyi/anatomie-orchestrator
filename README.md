# Anatomie Orchestrator v2.0

The autonomous brain of the ANATOMIE AI system. Coordinates learning cycles, daily batch generation, and manual prompt requests across all agents.

## Architecture

```
N8n (dumb triggers)
  ├─ 6 AM Schedule ────────→ POST /events/daily_batch
  ├─ Airtable Webhook ─────→ POST /events/like  
  └─ Manual Button ────────→ POST /events/manual_generate
                                    │
                            ┌───────┴───────┐
                            │  ORCHESTRATOR │
                            │  (the brain)  │
                            └───────┬───────┘
                                    │
            ┌───────────────────────┼───────────────────────┐
            ▼                       ▼                       ▼
       Optimizer              Strategist               Generator
       (ML scores)            (new ideas)              (prompts)
```

## What Changed in v2.0

| Aspect | v1.0 | v2.0 |
|--------|------|------|
| Daily batch | N8n calls Strategist directly | Orchestrator decides when/how |
| Prompt generation | N8n calls Generator directly | Orchestrator coordinates |
| Optimizer scores | Only sent to Generator | Also sent to Strategist |
| State tracking | Likes only | Likes + batches + generations + cached scores |

## API Endpoints

### Event Endpoints (new)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/events/daily_batch` | POST | Daily batch generation (ideas + prompts) |
| `/events/manual_generate` | POST | Manual prompt generation |
| `/events/like` | POST | Like event (triggers learning cycle) |

### Utility Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check with status |
| `/status` | GET | Detailed orchestrator state |
| `/scores` | GET | Cached optimizer scores |
| `/trigger_retrain` | POST | Manual learning cycle trigger |
| `/reset_counter` | POST | Reset like counter (admin) |

### Legacy Endpoints (preserved)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/like_event` | POST | Redirects to `/events/like` |

## Workflows

### Daily Batch (`POST /events/daily_batch`)

```json
// Request
{
  "force_retrain": false,
  "num_ideas": 5,
  "num_prompts": 12,
  "renderer": "ImageFX"
}

// Response (for N8n email)
{
  "success": true,
  "retrain_triggered": false,
  "ideas_generated": 5,
  "prompts_generated": 12,
  "summary": "5 new structure ideas generated. 12 prompts created.",
  "error": null
}
```

**Flow:**
1. Check if retrain needed (threshold reached?)
2. Get optimizer scores (fresh or cached)
3. Call Strategist with optimizer scores → generates ideas
4. Call Generator → creates prompts
5. Return summary for N8n to send email

### Manual Generate (`POST /events/manual_generate`)

```json
// Request
{
  "num_prompts": 24,
  "renderer": "Recraft",
  "force_retrain": false
}

// Response
{
  "success": true,
  "retrain_triggered": false,
  "prompts_generated": 24,
  "renderer": "Recraft",
  "error": null
}
```

### Like Event (`POST /events/like`)

```json
// Request
{
  "record_id": "recXXX",
  "structure_id": "42",
  "image_url": "https://..."
}

// Response
{
  "status": "recorded",
  "likes_since_last_retrain": 15,
  "threshold": 25,
  "threshold_reached": false,
  "retrain_triggered": false,
  "message": "Like recorded. 10 until next learning cycle."
}
```

## State Management

The orchestrator tracks:

```json
{
  "likes_since_last_retrain": 15,
  "last_retrain_at": "2025-01-15T06:00:00Z",
  "total_retrains": 12,
  "total_likes_processed": 342,
  
  "last_batch_at": "2025-01-15T06:00:00Z",
  "total_batches": 45,
  
  "last_generation_at": "2025-01-15T14:30:00Z",
  "total_generations": 89,
  
  "cached_structure_scores": {"42": 0.87, "67": 0.72, ...},
  "scores_cached_at": "2025-01-15T06:00:00Z"
}
```

## Environment Variables

```bash
# Service URLs
OPTIMIZER_SERVICE_URL=https://optimizer-2ym2.onrender.com
GENERATOR_SERVICE_URL=https://anatomie-prompt-generator.onrender.com
STRATEGIST_SERVICE_URL=https://anatomie-prompt-strategist.onrender.com

# Airtable
AIRTABLE_API_KEY=your_key
AIRTABLE_BASE_ID=appW8hvRj3lUrqEH2
AIRTABLE_STRUCTURES_TABLE_ID=tblPPDf9vlTBv2kyl

# Learning cycle
LIKE_THRESHOLD=25
EXPLORATION_RATE=0.2

# Batch defaults
DEFAULT_BATCH_IDEAS=5
DEFAULT_NUM_PROMPTS=12
DEFAULT_RENDERER=ImageFX
```

## Running Locally

```bash
# Setup
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run
uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload

# Test
curl http://localhost:8001/health
curl -X POST http://localhost:8001/events/daily_batch -H "Content-Type: application/json" -d '{}'
```

## Service Dependencies

| Service | URL | Purpose |
|---------|-----|---------|
| Optimizer | https://optimizer-2ym2.onrender.com | ML training & scoring |
| Generator | https://anatomie-prompt-generator.onrender.com | Prompt generation |
| Strategist | https://anatomie-prompt-strategist.onrender.com | Idea generation |
| Airtable | API | Structure storage |

## N8n Integration

After deploying, update N8n workflows:

1. **Daily Batch Settings** → Change to `POST /events/daily_batch`
2. **Manual Generate** → Change to `POST /events/manual_generate`
3. **Outlier** → Change to `POST /events/like` (or keep `/like_event`)

The response from `/events/daily_batch` contains everything needed for the email notification.
