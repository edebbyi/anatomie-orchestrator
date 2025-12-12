# N8n Workflow Updates

## Overview

After deploying Orchestrator v2, update these N8n workflows.

**Key change:** All batch settings (batchSize, defaultNumPrompts, defaultRenderer) are now read from Airtable, not passed in requests.

---

## Airtable Setup Required

Add two new fields to the **Daily Batch Settings** table (`tblLniml0SiVxrvvC`):

| Field Name | Type | Default Value | Description |
|------------|------|---------------|-------------|
| `numPrompts` | Number | 30 | Prompts generated per daily batch |
| `renderer` | Single Select | ImageFX | Renderer for prompt generation |

Existing fields remain unchanged:
- `batchSize` (3) - Used by Strategist for idea count
- `batchEnabled` - Toggle for daily batch
- `emailNotifications` - Toggle for email alerts
- `notificationEmail` - Recipient email

---

## 1. Daily Batch Settings → Daily Batch (Orchestrator v2)

**Option A: Import new workflow**
Import `daily_batch_v2.json` and deactivate the old workflow.

**Option B: Update existing workflow**

| Node | Current | Change To |
|------|---------|-----------|
| HTTP Request | `POST anatomie-prompt-strategist.onrender.com/api/batch/run` | `POST anatomie-orchestrator.onrender.com/events/daily_batch` |
| Request Body | (none) | `{}` (empty - settings from Airtable) |
| Timeout | 60s | 300s (5 min) |

**Request body is now empty:**
```json
{}
```

Or optionally force a retrain:
```json
{"force_retrain": true}
```

**Response fields for email:**
- `success` (boolean)
- `retrain_triggered` (boolean)
- `ideas_generated` (int)
- `prompts_generated` (int)
- `summary` (string) ← Use this in email body
- `error` (string|null)

---

## 2. Make Prompts → Manual Generate (Orchestrator v2)

**Option A: Import new workflow**
Import `manual_generate_v2.json` and deactivate the old workflow.

**Option B: Update existing workflow**

| Node | Current | Change To |
|------|---------|-----------|
| HTTP Request | `POST anatomie-prompt-generator.onrender.com/generate-prompts` | `POST anatomie-orchestrator.onrender.com/events/manual_generate` |

**Request body (manual requests still accept params):**
```json
{
  "num_prompts": 24,
  "renderer": "Recraft",
  "force_retrain": false
}
```

**Benefits of routing through Orchestrator:**
- Optimizer scores applied to generation
- State tracked (generation history)
- Can trigger retrain if needed

---

## 3. Outlier Workflow

**Minimal change required:**

| Node | Current | Change To |
|------|---------|-----------|
| HTTP Request (Orchestrator) | `POST .../like_event` | `POST .../events/like` |

**Note:** The `/like_event` endpoint still works (legacy support), so this change is optional but recommended for consistency.

---

## Workflow Summary After Updates

| Workflow | Trigger | Calls | Settings Source |
|----------|---------|-------|-----------------|
| **Daily Batch v2** | 6 AM Schedule | `POST /events/daily_batch` | Airtable |
| **Manual Generate v2** | Webhook/Button | `POST /events/manual_generate` | Request body |
| **Outlier** | Airtable webhook | `POST /events/like` | N/A |

---

## Testing

1. **Add Airtable fields first:**
   - `numPrompts` = 30
   - `renderer` = "ImageFX"

2. **Health check:**
```bash
curl https://anatomie-orchestrator.onrender.com/health
```

3. **Manual daily batch:**
```bash
curl -X POST https://anatomie-orchestrator.onrender.com/events/daily_batch \
  -H "Content-Type: application/json" \
  -d '{}'
```

4. **Manual generate (with custom params):**
```bash
curl -X POST https://anatomie-orchestrator.onrender.com/events/manual_generate \
  -H "Content-Type: application/json" \
  -d '{"num_prompts": 5, "renderer": "Recraft"}'
```

5. **Check status:**
```bash
curl https://anatomie-orchestrator.onrender.com/status
```
