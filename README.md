# Multi-Monitor Trend Intelligence System v5.2

Universal Reddit trend parser with Telegram management, Railway cloud deployment,
Google Drive storage, and AI-ready handoff JSON.

**No Reddit API keys required** — uses Playwright (headless Chrome).  
**No hardcoded projects** — users create their own projects and monitors via Telegram.

---

## Key Design Principles

| Principle | Detail |
|-----------|--------|
| **User-driven** | Projects and monitors created through Telegram conversation, not config files |
| **Manual-first** | All new monitors default to `schedule_mode=manual` — nothing runs automatically until you enable it |
| **Per-user isolation** | Each user owns their projects, monitors, and Drive folder |
| **Limits** | Max 3 active projects per user, max 5 active monitors per project |
| **Railway cron = technical checker** | Cron only runs monitors explicitly set to `schedule_mode=scheduled` |
| **Run protection** | If last run was < `min_days_between_runs` (default 7) ago, bot shows a force-confirm warning |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Telegram Bot  ←→  You                                       │
│  /projects /create_project /monitors /run /latest /drive     │
└────────────┬────────────────────────────────────────────────┘
             │
┌────────────▼──────────────┐   ┌──────────────────────────────┐
│  Railway — telegram-bot   │   │  Railway — cron-runner        │
│  python main_bot.py       │   │  python main_runner.py        │
│                           │   │  --run-due-monitors           │
│  • conversation flows     │   │  --run-queued                 │
│  • creates projects/      │   │                               │
│    monitors via inline    │   │  • queries next_run_at<=NOW   │
│    keyboard dialogs       │   │  • runs Playwright scraper    │
│  • queues runs on /run    │   │  • exports xlsx/json          │
│  • sends files / links    │   │  • uploads to Google Drive    │
└────────────┬──────────────┘   └──────────────────────────────┘
             │                             │
             └───────────┬─────────────────┘
                         │
              ┌──────────▼──────────┐
              │  Postgres (Railway) │  — metadata only
              │  users / projects   │  — monitors / runs
              │  exports            │  — drive links
              └──────────┬──────────┘
                         │
              ┌──────────▼──────────┐
              │  Google Drive       │  — full data files
              │  {owner_id}/        │
              │    {project_id}/    │  — xlsx, json
              │      {monitor_id}/  │  — handoff.json
              │        YYYY-MM-DD/  │
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
# Edit .env: set TELEGRAM_BOT_TOKEN, ADMIN_TELEGRAM_IDS

# 3. Run bot locally
python main_bot.py

# 4. Or run CLI parser directly
python main.py parse --help
```

---

## Creating Your First Project

All projects and monitors are created through the Telegram bot:

### Step 1 — Create a project

Send `/create_project` to the bot. The bot will ask:

1. **Project name** — e.g. "Wellness Products"
2. **Description** — what you're monitoring
3. **Niche** — e.g. "health & wellness"
4. **Language** — RU / EN / UK
5. **Confirm** — review and create

### Step 2 — Create a monitor

After creating a project, send `/create_monitor <project_id>`. The bot asks:

1. **Monitor name** — e.g. "Hot Posts Weekly"
2. **Description**
3. **Subreddit preset** — choose from system presets or enter custom subreddits
4. **Keyword preset** — choose from system presets or enter custom keywords (optional)
5. **Run mode** — hot_last_7d / rising_24h / top_week / top_month
6. **Schedule** — manual (default) / weekly / biweekly / monthly / disabled
7. **Confirm**

### Step 3 — Run it

After monitor is created: tap **▶️ Запустить** button, or send `/run <monitor_id>`.

---

## Limits

| Entity | Limit |
|--------|-------|
| Active projects per user | **3** (archived don't count) |
| Active monitors per project | **5** (archived don't count) |
| Default schedule | **manual** (cron never touches it) |
| Min days between runs | **7** (configurable per monitor) |
| Max runs per month | **4** (configurable per monitor) |

---

## Schedule Modes

| Mode | Behaviour |
|------|-----------|
| `manual` | Only runs when you explicitly trigger it via bot or CLI. Default for all new monitors. |
| `scheduled` | Railway cron checks `next_run_at <= NOW()` and runs automatically. |
| `disabled` | No runs of any kind. |

To change schedule via bot: open monitor menu → 🕒 Расписание.  
To change via CLI: `/schedule_manual <id>`, `/schedule_weekly <id> <day> <HH:MM>`, etc.

---

## Telegram Commands

| Command | Description |
|---------|-------------|
| `/start` | Main menu |
| `/projects` | List your projects |
| `/create_project` | Create a new project (5-step conversation) |
| `/monitors [project_id]` | List monitors |
| `/create_monitor <project_id>` | Create a monitor (7-step conversation) |
| `/run <monitor_id>` | Run a monitor (with protection check) |
| `/schedule <monitor_id>` | Open schedule menu |
| `/next_runs` | Show upcoming scheduled runs |
| `/runs [monitor_id]` | Run history |
| `/latest [monitor_id]` | Last run summary |
| `/download <run_id>` | Download export file |
| `/drive <run_id>` | Show Drive links for a run |
| `/presets` | List available subreddit/keyword presets |
| `/status` | System status (DB, Drive, scheduler) |
| `/archive_project <id>` | Archive a project |
| `/archive_monitor <id>` | Archive a monitor |

---

## Railway Deployment

### 1. Set environment variables

```
TELEGRAM_BOT_TOKEN=...
ADMIN_TELEGRAM_IDS=123456789,987654321
DATABASE_URL=postgresql://...        # Railway Postgres add-on
GOOGLE_DRIVE_FOLDER_ID=...
GOOGLE_SERVICE_ACCOUNT_JSON_BASE64=...
MAX_POSTS_TOTAL=500
MAX_COMMENTS_TOTAL=5000
CLEANUP_LOCAL_FILES=true
```

### 2. Deploy

```bash
git push railway main
```

Railway uses `railway.json` which starts `python main_bot.py`.

### 3. Add cron service

In Railway dashboard, add a second service from the same repo with start command:

```
python main_runner.py --run-due-monitors --run-queued
```

Set cron schedule: `*/30 * * * *` (every 30 minutes).

The cron **only runs monitors with `schedule_mode=scheduled`** — it never touches manual monitors.

---

## CLI Usage (Local / Advanced)

```bash
# Parse subreddits directly
python main.py parse --subreddits fitness yoga --keywords "protein shake" --sort hot

# Run a specific monitor
python main.py run-monitor <monitor_id>

# Run all enabled monitors
python main.py run-all

# List monitors
python main.py list-monitors

# List recent runs
python main.py list-runs

# Start local scheduler (APScheduler)
python main.py scheduler
```

---

## Google Drive Structure

```
{root_folder}/
  {owner_telegram_id}/
    {project_id}/
      {monitor_id}/
        YYYY-MM-DD/
          {run_id}.xlsx
          {run_id}.json
          {run_id}_handoff.json
```

Each user's data is isolated under their Telegram ID.

---

## AI Handoff JSON

Every run produces `{run_id}_handoff.json` with:

```json
{
  "schema_version": "5.2",
  "owner": { "telegram_id": "..." },
  "project": { "id": "...", "niche": "...", "output_language": "en" },
  "monitor": {
    "subreddit_preset": "...", "keyword_preset": "...",
    "custom_subreddits": [], "custom_keywords": []
  },
  "run": { "quality_status": "ok|small_dataset", ... },
  "summary": { "pain_signal_distribution": {}, ... },
  "top_posts": [ ... ],          // top 30 by trend_score
  "keyword_summary": [ ... ],
  "selected_comments": [ ... ],  // top 200 from top-50 posts, min 50 chars
  "recommended_ai_tasks": [
    "extract_trends", "extract_pains", "extract_questions",
    "extract_language_patterns", "generate_content_angles", "prepare_channel_mapping"
  ]
}
```

---

## System Presets

System subreddit and keyword presets are seeded from `config.py` to DB on startup.  
Users can browse them with `/presets` and choose them when creating a monitor.  
Users can also enter custom subreddits/keywords instead.

---

## monitors.yaml (Optional / Backward Compat)

If `monitors.yaml` exists, it is loaded on startup and synced to DB.  
These "yaml monitors" get `owner_telegram_id=0` (system-owned).  
This is for power users / migration from v4. For new setups, use the Telegram bot.

---

## Local Development

```bash
# SQLite mode (default — no DATABASE_URL needed)
python main_bot.py

# Check DB contents
python -c "from storage import database as db; db.init_db(); print(db.list_monitors())"

# Seed presets manually
python -c "from config_loader import seed_system_presets; seed_system_presets()"
```

---

## Version History

| Version | Description |
|---------|-------------|
| v5.2 | Universal multi-user system: user-created projects/monitors, manual-first scheduling, per-user Drive isolation |
| v5.1 | Cloud MVP: Railway + Telegram bot + Google Drive + Postgres |
| v5.0 | Multi-Monitor Trend Intelligence System (local) |
| v4.1 | Reddit Parser with quality scoring, AI handoff JSON |
| v4.0 | Multi-subreddit parser with Playwright |
