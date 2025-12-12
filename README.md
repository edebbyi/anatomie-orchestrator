# Anatomie Orchestrator v2

FastAPI service that coordinates learning cycles, daily batch idea/prompt generation, and manual prompt requests across Optimizer, Strategist, Generator, and Airtable.

## Key Endpoints
- `POST /events/like` (and legacy `/like_event`) — count likes, trigger learning cycle at threshold.
- `POST /events/daily_batch` — daily idea + prompt batch (used by N8n cron).
- `POST /events/manual_generate` — on-demand prompt generation.
- `GET /scores` — cached optimizer scores.
- `GET /health`, `GET /status`, `POST /trigger_retrain`, `POST /reset_counter`.

## Config (.env)
```bash
OPTIMIZER_SERVICE_URL=https://optimizer-2ym2.onrender.com
GENERATOR_SERVICE_URL=https://anatomie-prompt-generator.onrender.com
STRATEGIST_SERVICE_URL=https://anatomie-prompt-strategist.onrender.com
AIRTABLE_API_KEY=your_api_key_here
AIRTABLE_BASE_ID=appW8hvRj3lUrqEH2
AIRTABLE_STRUCTURES_TABLE_ID=tblPPDf9vlTBv2kyl
LIKE_THRESHOLD=25
EXPLORATION_RATE=0.2
DEFAULT_BATCH_IDEAS=5
DEFAULT_NUM_PROMPTS=30
DEFAULT_RENDERER=ImageFX
```

## Run Locally
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload
```

## Services
- Optimizer (`https://github.com/edebbyi/optimizer`)
- Generator (`https://github.com/edebbyi/anatomie-prompt-generator`)
- Strategist (`https://github.com/edebbyi/anatomie-prompt-strategist`)
- Airtable (structures storage)
