# Anatomie Orchestrator

A FastAPI service that coordinates the learning cycle between the Optimizer, Generator, and Airtable services based on user engagement (likes).

## How It Works

The orchestrator tracks user likes and triggers an automated learning cycle when a threshold is reached (default: 25 likes).

### Learning Cycle Flow

When the like threshold is reached, the orchestrator executes a 5-step learning cycle:

1. **Train Optimizer** → Calls `POST /train` on the Optimizer service
   - Trains the ML model on recent user feedback

2. **Score Structures** → Calls `POST /score_structures` on the Optimizer service
   - Generates predicted success scores for all anatomical structures

3. **Get Insights** → Calls `GET /structure_prompt_insights` on the Optimizer service
   - Retrieves prompt engineering insights for each structure

4. **Update Generator** → Calls `POST /update_preferences` on the Generator service
   - Sends preference vectors, structure scores, and insights to update generation strategy

5. **Update Airtable** → Calls Airtable API
   - Persists optimizer scores back to the database for each structure

### Agent Communication

```
User Like Events → Orchestrator → Counter (25 threshold)
                                     ↓
                           Learning Cycle Triggered
                                     ↓
              ┌──────────────────────┴──────────────────────┐
              ↓                      ↓                       ↓
    Optimizer Service      Generator Service        Airtable API
    (Train, Score, Insights)  (Update Preferences)   (Store Scores)
```

## API Endpoints

- `GET /health` - Health check with current counter status
- `POST /like_event` - Record a like event (triggers cycle at threshold)
- `POST /trigger_retrain` - Manually trigger learning cycle
- `POST /reset_counter` - Reset the like counter
- `GET /status` - Detailed orchestrator status

## Configuration

Environment variables (`.env` file):

```bash
OPTIMIZER_SERVICE_URL=https://optimizer-2ym2.onrender.com
GENERATOR_SERVICE_URL=https://anatomie-prompt-generator.onrender.com
AIRTABLE_API_KEY=your_api_key_here
AIRTABLE_BASE_ID=appW8hvRj3lUrqEH2
AIRTABLE_STRUCTURES_TABLE_ID=tblPPDf9vlTBv2kyl
LIKE_THRESHOLD=25
EXPLORATION_RATE=0.2
```

## Running Locally

```bash
# Activate virtual environment
source .venv/bin/activate

# Start the server
uvicorn orchestrator.main:app --host 0.0.0.0 --port 8001

# Test
curl http://localhost:8001/health
curl -X POST http://localhost:8001/like_event -H "Content-Type: application/json" -d '{}'
```

## Service Dependencies

- **Optimizer Agent** (`https://github.com/edebbyi/optimizer`): ML model training and structure scoring
- **Generator Agent** (`https://github.com/edebbyi/anatomie-prompt-generator`): Prompt generation with adaptive preferences
- **Airtable**: Database for anatomical structures and scores

## Related/Upcoming

- **Prompt Strategist** (`https://github.com/edebbyi/anatomie-prompt-strategist`): planned integration so the orchestrator forwards Optimizer predicted success scores to the strategist to guide new idea generation. Tracking as a future feature.
