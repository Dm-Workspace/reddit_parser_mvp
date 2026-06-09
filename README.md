# Multi-Monitor Trend Intelligence System v5

Reddit trend parser with Telegram management, Railway cloud deployment,
Google Drive storage, and AI-ready handoff JSON.

No Reddit API keys required — uses Playwright (headless Chrome).

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Telegram Bot  ←→  You                                       │
│  /run /monitors /download /drive                             │
└────────────┬────────────────────────────────────────────────┘
             │
┌────────────▼──────────────┐   ┌──────────────────────────────┐
│  Railway — telegram-bot   │   │  Railway — cron-runner        │
│  python main_bot.py       │   │  python main_runner.py        │
│                           │   │  --run-due-monitors           │
│  • reads DB               │   │  --run-queued                 │
│  • queues runs            │   │                               │
│  • sends files / links    │   │  • checks cron schedules      │
└────────────┬──────────────┘   │  • runs Playwright scraper   │
             │                  │  • exports xlsx/json          │
             │                  │  • uploads to Google Drive    │
             └───────┬──────────┘
                     │
          ┌──────────▼──────────┐
          │  Postgres (Railway) │  — metadata only
          │  projects / monitors│  — run history
          │  runs / exports     │  — drive links
          └─────────────────────┘
                     │
          ┌──────────▼──────────┐
          │  Google Drive       │  — full data files
          │  project/monitor/   │  — xlsx, json
          │  YYYY-MM-DD/        │  — handoff.json
          └─────────────────────┘
```

**Key principle:** Postgres stores only metadata. Full post/comment data lives on Google Drive.

---

## Quick Start — Local

```bash
# 1. Install dependencies
pip install -r requirements.txt
playwright install chromium

# 2. Configure
cp .env.example .env
# edit .env with your tokens

# 3. Direct parse (no DB, no monitors)
python main.py parse --subreddit-preset wellness_en --keyword-preset wellness_en --run-mode hot_last_7d

# 4. Run a monitor
python main.py run-monitor --monitor-id wellness_hot

# 5. Start Telegram bot
python main_bot.py

# 6. Start cron runner
python main_runner.py --run-due-monitors
```

---

## Environment Variables

Copy `.env.example` to `.env`:

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes (bot) | From @BotFather |
| `ADMIN_TELEGRAM_IDS` | Yes (bot) | Comma-separated Telegram user IDs |
| `DATABASE_URL` | Railway | Postgres URL. Empty = SQLite fallback |
| `GOOGLE_DRIVE_FOLDER_ID` | Drive | Root folder ID from Drive URL |
| `GOOGLE_SERVICE_ACCOUNT_JSON_BASE64` | Drive | Base64-encoded service account JSON |
| `MAX_POSTS_TOTAL` | No | Max posts per run (default: 500) |
| `MAX_COMMENTS_TOTAL` | No | Max comments per run (default: 5000) |
| `CLEANUP_LOCAL_FILES` | No | `true` = delete local files after Drive upload |

---

## Railway Setup

### Step 1 — Create project on Railway

1. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
2. Select your `reddit_parser_mvp` repo

### Step 2 — Add Postgres

1. In Railway project → New → Database → Add PostgreSQL
2. Copy `DATABASE_URL` from the database service → Connect tab
3. Add as environment variable to your services

### Step 3 — Create two services

**Service 1: telegram-bot**
- Start command: `python main_bot.py`
- Env vars: `TELEGRAM_BOT_TOKEN`, `ADMIN_TELEGRAM_IDS`, `DATABASE_URL`,
  `GOOGLE_DRIVE_FOLDER_ID`, `GOOGLE_SERVICE_ACCOUNT_JSON_BASE64`

**Service 2: cron-runner**
- Type: Cron
- Schedule: `*/30 * * * *` (every 30 min, UTC)
- Command: `python main_runner.py --run-due-monitors --run-queued`
- Same env vars as telegram-bot

> **Note:** Railway cron runs in UTC. Timezone-aware schedule checks are done inside the app using each monitor's `timezone` field from `monitors.yaml`.

### Step 4 — Set environment variables

In each Railway service → Variables tab, add all required ENV vars.

### Step 5 — Deploy

Push to GitHub → Railway auto-deploys.

---

## Telegram Bot Setup

1. Message @BotFather → `/newbot`
2. Follow prompts, copy the token
3. Set `TELEGRAM_BOT_TOKEN=<token>` in Railway env vars
4. Get your Telegram user ID: message @userinfobot
5. Set `ADMIN_TELEGRAM_IDS=<your_id>` (comma-separated for multiple admins)

### Bot Commands

```
/start                   — welcome & command list
/projects                — list projects
/monitors                — monitors with last run status
/run <monitor_id>        — start a monitor run
/latest                  — latest run per monitor
/runs [limit]            — recent run history (default: 10)
/download <run_id>       — get Excel file in chat
/drive <run_id>          — Google Drive links for run
/status                  — system status (DB, Drive, env)
```

Example session:
```
You: /run wellness_hot
Bot: 🚀 Run started! Run ID: abc123
     ⏱ Parsing Reddit... takes 5–10 min. I'll send results when done.

[5 minutes later]
Bot: ✅ Run COMPLETED
     📊 Posts: 91  💬 Comments: 922
     🔑 Top keywords: energy (23), fatigue (18), supplement (15)
     ☁️ Google Drive:
       📊 XLSX: https://drive.google.com/...
       📄 JSON: https://drive.google.com/...
       🤖 HANDOFF JSON: https://drive.google.com/...
```

---

## Google Drive Setup

### Create Service Account

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create new project (or use existing)
3. Enable **Google Drive API**: APIs & Services → Enable APIs → search "Google Drive API"
4. Go to IAM & Admin → Service Accounts → Create Service Account
5. Name it (e.g. `trend-intelligence-drive`)
6. Click the service account → Keys tab → Add Key → Create new key → JSON
7. Download the JSON file

### Encode as base64

```bash
python -c "import base64; print(base64.b64encode(open('service-account-key.json','rb').read()).decode())"
```

Copy the output → set as `GOOGLE_SERVICE_ACCOUNT_JSON_BASE64`.

### Give service account access to your Drive folder

1. In Google Drive, right-click the root folder → Share
2. Add the service account email (looks like `name@project.iam.gserviceaccount.com`)
3. Give **Editor** access
4. Copy the folder ID from the URL → set as `GOOGLE_DRIVE_FOLDER_ID`

### Drive folder structure

```
Trend Intelligence Hub/           ← your root folder
  energy_reboot/
    wellness_hot/
      2026-06-09/
        report_090215.xlsx
        report_090215.json
        abc123_handoff.json
  up_level/
    up_level_crm/
      2026-06-09/
        ...
```

---

## monitors.yaml

All monitors and projects are defined in `monitors.yaml`:

```yaml
projects:
  - id: energy_reboot
    name: Energy Reboot
    description: "Women wellness market"
    language: en
    market: women wellness
    default_output_language: ru
    enabled: true

monitors:
  - id: wellness_hot
    project_id: energy_reboot
    name: Wellness Hot 7 Days
    source: reddit
    subreddit_preset: wellness_en   # 13 EN wellness subreddits
    keyword_preset: wellness_en
    run_mode: hot_last_7d
    schedule_cron: "0 8 * * *"      # daily at 08:00
    timezone: Europe/Podgorica
    enabled: true
    export_formats:
      - xlsx
      - json
```

Changes to `monitors.yaml` are synced to DB automatically on bot start and each runner invocation.

---

## Run Modes

| Mode | Sort | Period | Posts/sub |
|------|------|--------|-----------|
| `hot_last_7d` | hot | last 7 days | 100 |
| `top_week` | top | last 7 days | 100 |
| `top_month` | top | last 30 days | 100 |
| `rising_24h` | rising | last 24 hours | 100 |

---

## AI Handoff JSON

Every run creates `{run_id}_handoff.json` — structured data for AI processing.

```json
{
  "schema_version": "5.1",
  "project":  { "id": "energy_reboot", "market": "women wellness", ... },
  "monitor":  { "id": "wellness_hot", "run_mode": "hot_last_7d", ... },
  "run":      { "id": "abc123", "status": "completed", "total_posts": 91 },
  "summary": {
    "pain_signal_distribution": { "energy_fatigue": 23, "sleep_problem": 17 },
    "analysis_priority_distribution": { "high": 12, "medium": 45 }
  },
  "top_posts":          [...],   // top 30 by trend_score
  "keyword_summary":    [...],   // keyword frequency
  "selected_comments":  [...],   // top 200 comments from top posts
  "recommended_ai_tasks": [
    "extract_trends",
    "extract_pains",
    "extract_questions",
    "extract_language_patterns",
    "generate_content_angles",
    "prepare_channel_mapping"
  ]
}
```

**How to use manually:**
1. Download handoff JSON via `/download` or `/drive` command
2. Open Claude / ChatGPT
3. Paste the file content or upload it
4. Prompt: "Based on this Reddit data, do: extract_trends — write a trend summary for [market]"

---

## Cron Runner Logic

`main_runner.py --run-due-monitors`:

1. Syncs `monitors.yaml` → DB
2. For each enabled monitor:
   - Gets last completed run time
   - Uses `croniter` to compute when cron last should have fired
   - If expected fire time > last run time: **run it**
   - If no previous run: run if expected fire was within last 35 min
   - Skips if monitor already running (concurrent protection)
3. Also runs any `queued` runs created by the bot (`--run-queued`)

Railway cron fires every 30 min (UTC). The schedule due-check is timezone-aware using each monitor's `timezone` field.

---

## Why Only Metadata in Postgres?

Full Reddit posts and comments can be **hundreds of MB per run**. Storing them in Postgres would:
- Hit Railway Postgres free tier limits fast
- Slow down queries
- Cost money at scale

**Solution:** DB stores only metadata (run status, post counts, Drive links).
Full data lives on Google Drive as structured files (xlsx, json, handoff.json).

The handoff.json includes a curated subset: top 30 posts + top 200 comments — enough for AI analysis.

---

## CLI Commands (v5)

```bash
# Direct parse (no DB, no monitors)
python main.py parse --subreddit-preset wellness_en --keyword-preset wellness_en --run-mode hot_last_7d

# Monitor management
python main.py list-monitors
python main.py run-monitor --monitor-id wellness_hot
python main.py run-all
python main.py list-runs

# Cron runner
python main_runner.py --run-due-monitors
python main_runner.py --run-monitor wellness_hot
python main_runner.py --run-queued

# Telegram bot
python main_bot.py

# APScheduler daemon (alternative to Railway cron)
python main.py scheduler
```

---

## Excel Output Structure

| Sheet | Contents |
|-------|---------|
| Summary | Run overview |
| Top Posts | Top 20 by trend_score, color-coded by priority |
| Posts | All posts with analysis fields |
| Comments | All comments |
| Keyword Summary | Keyword frequency table |
| Quality Check | Data quality diagnostics |
| Run Settings | All run parameters |

---

## Roadmap

### Current: v5 Cloud MVP
- ✅ Telegram bot management
- ✅ Railway cron scheduling
- ✅ Google Drive file storage
- ✅ Postgres metadata DB
- ✅ AI Handoff JSON

### Next: v6 AI Processor
- [ ] Claude/OpenAI API integration
- [ ] Auto-process handoff JSON after each run
- [ ] Send AI summary to Telegram
- [ ] Store analysis results in DB

### Later: v7 Web UI
- [ ] React dashboard
- [ ] Run history visualization
- [ ] Trend charts
- [ ] Project settings UI

---

## Versions

| Version | Key features |
|---------|-------------|
| v5.1 | Cloud MVP: Railway + Telegram + Google Drive + Postgres |
| v5.0 | Multi-Monitor System: SQLite, monitors.yaml, APScheduler |
| v4.1 | pain_signal, analysis_priority, content_type, text_status |
| v4.0 | Subreddit presets, keyword presets, 4 run modes |
| v3.0 | selftext, comment_match_type, min_comment_length |
| v2.0 | Playwright scraping (no API keys needed) |
| v1.0 | MVP with PRAW (required Reddit API keys) |
