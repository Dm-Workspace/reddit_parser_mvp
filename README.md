# Trend Intelligence Hub — Multi-Monitor System v5.4

Universal Reddit trend parser with Telegram management, Railway cloud deployment,
PostgreSQL metadata store, Google Drive file storage, and AI-ready Handoff JSON.

**No Reddit API keys required** — default mode uses public Reddit JSON endpoints.  
**No hardcoded projects** — users create their own projects and monitors via Telegram.

Repository: **https://github.com/Dm-Workspace/reddit_parser_mvp**  
*(Do not create a new repo — use this one)*

---

## Key Design Principles

| Principle | Detail |
|-----------|--------|
| **User-driven** | Projects and monitors created through Telegram, not config files |
| **Manual-first** | All new monitors default to `schedule_mode=manual` — nothing runs automatically until you enable it |
| **Metadata-only DB** | PostgreSQL stores only compact metadata; full export files live on Google Drive |
| **Per-user isolation** | Each user owns their projects, monitors, and Drive subfolder |
| **Limits** | Max 3 active projects / user, max 5 active monitors / project |
| **Railway cron = checker** | Cron only runs monitors explicitly set to `schedule_mode=scheduled` |
| **Drive failure = warning** | Drive upload failure sets run to `completed_with_warning`, never `failed` |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Telegram Bot  ←→  You                                       │
│  /start /create_project /create_monitor /run /status        │
└────────────┬────────────────────────────────────────────────┘
             │
┌────────────▼──────────────┐   ┌──────────────────────────────┐
│  Railway — telegram-bot   │   │  Railway — cron-runner        │
│  python main_bot.py       │   │  python main_runner.py        │
│                           │   │  --run-due-monitors           │
│  • 5-step project flow    │   │  --run-queued                 │
│  • 7-step monitor flow    │   │                               │
│  • InlineKeyboard nav     │   │  schedule: 0 */6 * * *        │
│  • run protection         │   │  only schedule_mode=scheduled │
│  • queues runs in DB      │   │  manual monitors: never       │
└────────────┬──────────────┘   └──────────────────────────────┘
             │                             │
             └───────────┬─────────────────┘
                         │
          ┌──────────────▼──────────────┐
          │  Railway — PostgreSQL        │  ← metadata only
          │  users / projects / monitors │
          │  runs / exports              │  ← no raw post/comment text
          │  subreddit_presets           │
          │  keyword_presets             │
          └──────────────┬──────────────┘
                         │ drive_file_id / drive_web_view_link
          ┌──────────────▼──────────────┐
          │  Google Drive               │  ← all export files
          │  {owner_id}/                │
          │    {project_id}/            │  .xlsx  .json
          │      {monitor_id}/          │  _handoff.json
          │        YYYY-MM-DD/          │
          └─────────────────────────────┘
```

---

## Railway Deployment (Step-by-Step)

### Prerequisites
- GitHub repo: `Dm-Workspace/reddit_parser_mvp`
- Railway account at railway.app
- Google Cloud service account with Drive API enabled
- Telegram bot token from @BotFather

### Step 1 — Create Railway Project

1. Go to railway.app → New Project → Deploy from GitHub repo
2. Connect `Dm-Workspace/reddit_parser_mvp`
3. This creates the first service (telegram-bot)

### Step 2 — Add PostgreSQL

In your Railway Project dashboard:
1. Click **New** → **Database** → **PostgreSQL**
2. Wait for it to provision (~30 seconds)
3. Note the service name (usually `Postgres` or `PostgreSQL`)

### Step 3 — Configure telegram-bot service

In the `telegram-bot` service → **Settings** → **Start Command**:
```
python main_bot.py
```

In **Variables** tab, add all ENV vars (see below).  
For DATABASE_URL use a **reference variable**:
```
DATABASE_URL=${{Postgres.DATABASE_URL}}
```
*(Replace `Postgres` with your actual PostgreSQL service name)*

### Step 4 — Add cron-runner service

1. In Railway Project → **New** → **GitHub Repo** (same repo)
2. Set **Start Command**:
   ```
   python main_runner.py --run-due-monitors --run-queued
   ```
3. Set **Cron Schedule**: `0 */6 * * *` (every 6 hours)
4. Add same ENV vars as telegram-bot service
5. Add same `DATABASE_URL=${{Postgres.DATABASE_URL}}` reference

### Step 5 — Add all ENV vars (both services)

```
REDDIT_CLIENT_ID=<your reddit app client id>
REDDIT_CLIENT_SECRET=<your reddit app client secret>
REDDIT_USER_AGENT=TrendIntelligenceHub/1.0

TELEGRAM_BOT_TOKEN=<your bot token>
ADMIN_TELEGRAM_IDS=<your telegram user id>

DATABASE_URL=${{Postgres.DATABASE_URL}}

GOOGLE_DRIVE_FOLDER_ID=<your drive root folder id>
GOOGLE_SERVICE_ACCOUNT_JSON_BASE64=<base64-encoded service account json>

APP_TIMEZONE=Europe/Podgorica
CLEANUP_LOCAL_FILES=true
MAX_POSTS_TOTAL=500
MAX_COMMENTS_TOTAL=5000
```

### Step 6 — Initialise database

After first deploy, open **Railway shell** on cron-runner service and run:
```bash
python main_runner.py --db-check
python main_runner.py --init-db
```

Expected output from `--db-check`:
```
DATABASE_URL set : YES
Database type    : postgres
Connection       : OK

Table counts:
  users                      0
  projects                   0
  monitors                   0
  subreddit_presets          8
  keyword_presets            6
  runs                       0
  exports                    0
```

### Step 7 — Verify via Telegram

Send `/status` to your bot. Expected response:
```
✅ POSTGRES — подключено
✅ Google Drive — Настроен
✅ Reddit API — Настроен
```

---

## Creating Your First Project

### Via Telegram

**Step 1 — Create project** (`/create_project`):
1. Project name
2. Description
3. Niche (e.g. "health & wellness")
4. Language (RU / EN / UK)
5. Confirm

**Step 2 — Create monitor** (`/create_monitor <project_id>`):
1. Monitor name
2. Description
3. Subreddit preset (choose from list or enter custom)
4. Keyword preset (choose from list, skip, or enter custom)
5. Run mode (hot_last_7d / rising_24h / top_week / top_month)
6. Schedule (manual / weekly / biweekly / monthly / disabled)
7. Confirm

**Step 3 — Run** (`/run <monitor_id>` or tap ▶️ button):
- Bot queues the run
- Playwright scrapes Reddit (5–10 min)
- Files uploaded to Drive
- Bot sends summary with links

---

## Limits

| Entity | Default | ENV override |
|--------|---------|-------------|
| Active projects / user | **3** | `MAX_ACTIVE_PROJECTS_PER_USER` |
| Active monitors / project | **5** | `MAX_ACTIVE_MONITORS_PER_PROJECT` |
| Manual runs / day | **5** | `MAX_MANUAL_RUNS_PER_DAY` |
| Total runs / month | **30** | `MAX_TOTAL_RUNS_PER_MONTH` |
| Default min days between runs | **7** | per-monitor setting |

---

## Schedule Modes

| Mode | Behaviour |
|------|-----------|
| `manual` | **Default.** Runs only when you explicitly trigger it. Cron never touches it. |
| `scheduled` | Railway cron checks `next_run_at <= NOW()` every 6 hours and runs automatically. |
| `disabled` | No runs of any kind. |

To change via bot: open monitor menu → 🕒 Расписание  
To change via CLI:
```bash
/schedule_manual <monitor_id>
/schedule_weekly <monitor_id> <weekday> <HH:MM>
/schedule_biweekly <monitor_id>
/schedule_monthly <monitor_id> <day> <HH:MM>
/schedule_disable <monitor_id>
```

---

## PostgreSQL Policy

**What is stored in PostgreSQL:**
- User records (telegram_id, username, role)
- Projects (metadata: name, niche, language, owner)
- Monitors (metadata: presets, schedule config, last/next run)
- Subreddit/keyword presets
- Run records (status, counts, quality, keywords summary)
- Export records (file metadata, Drive links)

**What is NOT stored in PostgreSQL:**
- Full text of Reddit posts
- Full text of Reddit comments
- Excel/CSV/JSON export content
- Handoff JSON content
- Any large blob data

All full export files live on **Google Drive** only.  
PostgreSQL stores only `drive_file_id`, `drive_web_view_link`, `drive_download_link`.

---

## Google Drive Setup

1. **Create a Google Cloud Project** at console.cloud.google.com
2. **Enable Google Drive API** (APIs & Services → Library)
3. **Create a service account** (IAM → Service Accounts → Create)
4. **Download JSON key** (Keys tab → Add Key → JSON)
5. **Encode as base64**:
   ```bash
   python -c "import base64; print(base64.b64encode(open('key.json','rb').read()).decode())"
   ```
6. **Set `GOOGLE_SERVICE_ACCOUNT_JSON_BASE64`** to the output
7. **Create a Drive folder** named "Trend Intelligence Hub" (or any name)
8. **Share the folder** with the service account email as **Editor**
9. **Copy the folder ID** from the URL and set `GOOGLE_DRIVE_FOLDER_ID`

Drive folder structure:
```
Trend Intelligence Hub/
  {owner_telegram_id}/
    {project_id}/
      {monitor_id}/
        YYYY-MM-DD/
          {run_id}.xlsx
          {run_id}.json
          {run_id}_handoff.json
```

---

## Telegram Commands

| Command | Description |
|---------|-------------|
| `/start` | Main menu |
| `/projects` | List your projects |
| `/create_project` | Create a new project (5-step flow) |
| `/monitors [project_id]` | List monitors |
| `/create_monitor <project_id>` | Create a monitor (7-step flow) |
| `/run <monitor_id>` | Run a monitor (with protection check) |
| `/schedule <monitor_id>` | Change schedule via inline keyboard |
| `/next_runs` | Show upcoming scheduled runs |
| `/runs [n]` | Run history (default 10) |
| `/latest` | Last run per monitor |
| `/download <run_id>` | Download Excel file |
| `/drive <run_id>` | Show Drive links |
| `/presets` | List subreddit/keyword presets |
| `/status` | Full system health check |
| `/archive_project <id>` | Archive a project |
| `/archive_monitor <id>` | Archive a monitor |

---

## CLI Admin Commands

```bash
# Check DB connection and table counts
python main_runner.py --db-check

# Create tables + seed system presets (idempotent)
python main_runner.py --init-db

# Show last 10 runs
python main_runner.py --list-runs

# Show all projects
python main_runner.py --list-projects

# Show all monitors
python main_runner.py --list-monitors

# Force-run a specific monitor
python main_runner.py --run-monitor <monitor_id>

# Parse directly (CLI mode, no DB)
python main.py parse --subreddits fitness yoga --keywords "protein" --sort hot
```

---

## Cron Policy

Railway cron (`0 */6 * * *`) only runs monitors that meet ALL of:
1. `schedule_mode = scheduled`
2. `enabled = true`
3. `archived = false`
4. `next_run_at <= NOW()`
5. No active run (`status IN ('queued','running')`) for this monitor
6. `days_since_last_run >= min_days_between_runs`

**Manual monitors are never executed by cron.**  
A newly created monitor is always `manual` until the user explicitly enables scheduling.

---

## AI Handoff JSON (schema_version: 5.3)

Every run produces `{run_id}_handoff.json` uploaded to Google Drive:

```json
{
  "schema_version": "5.3",
  "owner": { "telegram_id": "..." },
  "project": { "id": "...", "niche": "...", "output_language": "en" },
  "monitor": {
    "subreddit_preset": "...",
    "keyword_preset": "...",
    "custom_subreddits": [],
    "custom_keywords": []
  },
  "run": {
    "quality_status": "ok | small_dataset",
    "warning_message": null
  },
  "summary": {
    "pain_signal_distribution": {},
    "analysis_priority_distribution": {}
  },
  "top_posts": [],
  "keyword_summary": [],
  "selected_comments": [],
  "recommended_ai_tasks": [
    "extract_trends", "extract_pains", "extract_questions",
    "extract_language_patterns", "generate_content_angles", "prepare_channel_mapping"
  ]
}
```

---

## Reddit Access Modes

The parser supports **four Reddit backends** controlled by a single ENV variable.  
**No Reddit API credentials are needed for the default mode.**

### `REDDIT_ACCESS_MODE` values

| Mode | Description | Credentials needed? |
|------|-------------|---------------------|
| `playwright` **(default)** | Headless Chromium scraping of `old.reddit.com`. Reliable on Railway and local. | ❌ None |
| `requests_json` | requests-based client hitting `reddit.com/{sub}.json`. Fast but Reddit often returns HTTP 403 for cloud IPs. Use for local debug only. | ❌ None |
| `oauth` | PRAW / Reddit OAuth API. Higher rate limits, requires app registration. | ✅ `REDDIT_CLIENT_ID` + `REDDIT_CLIENT_SECRET` |
| `auto` | Uses oauth if credentials are present; otherwise playwright. | ⚙️ Optional |

> **Note:** `public_json` is a backward-compatible alias for `requests_json`.

**Minimal `.env` (no Reddit registration needed):**
```env
REDDIT_ACCESS_MODE=playwright
REDDIT_USER_AGENT=TrendIntelligenceHub/1.0
```

### Why Playwright is the default

Reddit blocks plain `requests` from cloud IPs with HTTP 403.  
Playwright uses a real headless browser (Chromium), which passes Reddit's bot detection reliably.  
System Chromium dependencies are already included in `nixpacks.toml` for Railway.

### Checking Reddit connectivity

```bash
python main_runner.py --reddit-check
```

Output example (playwright mode):
```
==============================================================
  Reddit Access Check
==============================================================
  REDDIT_ACCESS_MODE   : playwright
  selected_client      : playwright
  user_agent_detected  : YES — TrendIntelligenceHub/1.0
  credentials_detected : NO (not needed for playwright/requests_json)
  playwright_available : YES
  test_subreddit       : Supplements

  browser_launch       : ok
  raw_posts_fetched    : 3
  test_result          : ok

  sample_titles (3):
    1. Best magnesium glycinate dosage for sleep?
    2. Ashwagandha — 6 week update
    3. Anyone tried NMN stacking with resveratrol?
==============================================================
```

---

## Parser QA / Smoke Tests

These commands test the **parser core** only — no Telegram, no Railway, no full DB required.  
Google Drive upload is opt-in with `--upload-drive`.  
SQLite fallback works locally out of the box.

> **No OAuth credentials needed** in `playwright` or `requests_json` mode.  
> Credentials (`REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET`) are required only for `REDDIT_ACCESS_MODE=oauth`.

---

### `--parser-smoke-test`

Runs a small live parse against known public subreddits:

```bash
python main_runner.py --parser-smoke-test
```

Configuration:
- **Subreddits:** `Supplements`, `Biohackers`
- **Keywords:** `magnesium`, `sleep`, `fatigue`
- **Period:** `last_7d` | **Sort:** `hot` | **Limit:** 10 posts/sub | **Comments:** 5/post
- **min_score / min_comments:** 0 (collect everything)
- **Exports:** xlsx + json + handoff_json
- **Output dir:** `exports/smoke_test/{timestamp}/`

Sample output:
```
Running parser smoke test (subreddits: Supplements, Biohackers)...

=======================================================
  Parser Smoke Test
=======================================================
  STATUS           : ok
  posts_count      : 18
  comments_count   : 74

  Data quality:
    bot_comments        : 0
    empty_title         : 0
    empty_permalink     : 0
    empty_selftext      : 4
    duplicate_posts_rm  : 2

  top_keywords     : magnesium (11), sleep (8), fatigue (6)

  Export dir       : exports/smoke_test/20260609_183000
  xlsx_path        : exports/smoke_test/20260609_183000/smoke_20260609_183000.xlsx
  json_path        : exports/smoke_test/20260609_183000/smoke_20260609_183000.json
  handoff_json     : exports/smoke_test/20260609_183000/smoke_20260609_183000_handoff.json
=======================================================
```

---

### `--parser-smoke-test --upload-drive`

Same as above, but also uploads the xlsx to Google Drive:

```bash
python main_runner.py --parser-smoke-test --upload-drive
```

Requires `GOOGLE_DRIVE_FOLDER_ID` and `GOOGLE_SERVICE_ACCOUNT_JSON_BASE64` to be set.  
If Drive is not configured, prints `drive_upload_status: skipped (Drive not configured)` and continues.

Additional output:
```
  Drive upload     : ok
  drive_file_id    : 1ABC...XYZ
  drive_view_link  : https://drive.google.com/file/d/1ABC.../view
```

---

### `--parser-qa-file <path>`

Validates a finished export Excel file without any network calls:

```bash
python main_runner.py --parser-qa-file exports/smoke_test/20260609_183000/smoke_20260609_183000.xlsx
```

**Status rules:**

| Status | Conditions |
|--------|-----------|
| **PASS** | All required sheets present, `total_posts > 0`, `total_comments > 0`, `empty_titles = 0`, `empty_permalinks = 0`, `bot_comments = 0` |
| **WARNING** | PASS criteria met but: `total_posts < 20`, or `total_comments < 100`, or `empty_selftext > 30%`, or `trend_score_zero > 50%` |
| **FAIL** | Missing required sheets (`Posts`, `Comments`, `Summary`), or `total_posts = 0`, or `total_comments = 0`, or any PASS criterion violated |

Required sheets: **Posts**, **Comments**, **Summary**

Sample output:
```
=======================================================
  Parser QA Report
=======================================================
  File             : exports/smoke_test/.../smoke_....xlsx
  STATUS           : [WARNING]

  Sheets found     : Posts, Comments, Summary, Top Posts
  total_posts      : 18
  total_comments   : 74

  Data quality:
    empty_titles          : 0
    empty_permalinks      : 0
    bot_comments_count    : 0
    duplicated_post_ids   : 0
    trend_score_zero      : 2
    empty_selftext        : 4

  Pain signals:
    no_signal              : 10
    stress                 : 5
    fatigue                : 3

  Warnings:
    - total_posts < 20 (18)
    - total_comments < 100 (74)
=======================================================
```

Exit codes: `0` = PASS or WARNING, `1` = FAIL.

---

### Typical QA workflow

```bash
# 1. Check DB is ready
python main_runner.py --db-check

# 2. Run smoke test (verifies full parser + export pipeline)
python main_runner.py --parser-smoke-test

# 3. QA check the generated Excel
python main_runner.py --parser-qa-file exports/smoke_test/<timestamp>/smoke_<timestamp>.xlsx

# 4. Optional: also verify Drive upload
python main_runner.py --parser-smoke-test --upload-drive
```

---

## Troubleshooting

### Bot starts but `/status` shows "database error"
- Check that `DATABASE_URL` is set correctly in Railway ENV
- Verify reference variable: `${{Postgres.DATABASE_URL}}`
- Run `python main_runner.py --db-check` in Railway shell
- Check that Postgres service is running in Railway dashboard

### Drive upload fails
- Verify `GOOGLE_DRIVE_FOLDER_ID` is correct
- Verify service account has **Editor** access to the root folder
- Check `GOOGLE_SERVICE_ACCOUNT_JSON_BASE64` — decode and verify it's valid JSON:
  ```bash
  echo "$GOOGLE_SERVICE_ACCOUNT_JSON_BASE64" | base64 -d | python -m json.tool
  ```
- Drive failure is non-fatal: run gets `completed_with_warning`, local file kept

### Reddit API not configured
- Create a script app at reddit.com/prefs/apps
- Set `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET`
- `/status` will show ✅ after variables are set

### Run stuck in "running" status
- Happens if Railway restarted the bot during a Playwright run
- Run `python main_runner.py --list-runs` to see stuck runs
- They will be skipped by future bot runs (active run guard)
- Manually reset: connect to DB and `UPDATE runs SET status='failed' WHERE status='running'`

### Cron does not run
- Verify cron schedule format: `0 */6 * * *`
- Verify all monitors that should auto-run have `schedule_mode=scheduled`
- Check `next_run_at` is set: `python main_runner.py --list-monitors`
- Run `python main_runner.py --run-due-monitors` manually to test

### DATABASE_URL missing
- Without `DATABASE_URL` the system falls back to SQLite at `data/tracker.db`
- On Railway with ephemeral filesystem, SQLite data is lost on restart
- Always set `DATABASE_URL` for Railway production deployments

### Service account has no Drive permission
- Open your Google Drive root folder
- Click Share
- Add the service account email (found in the JSON key file under `client_email`)
- Role: **Editor**

---

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Configure (SQLite mode — no DATABASE_URL needed)
cp .env.example .env
# Edit .env: add TELEGRAM_BOT_TOKEN, ADMIN_TELEGRAM_IDS

# Init DB (creates SQLite + seeds presets)
python main_runner.py --init-db

# Check DB
python main_runner.py --db-check

# Start bot
python main_bot.py

# CLI parse mode (no bot required)
python main.py parse --subreddits fitness --keywords "protein shake" --sort hot
```

---

## Version History

| Version | Description |
|---------|-------------|
| **v5.3** | Cloud Deploy Polish: PostgreSQL readiness, Railway deployment guide, `--db-check`/`--init-db` CLI, improved `/status`, graceful Drive failure, `owner_telegram_id` in runs/exports, `file_size` tracking |
| v5.2 | Universal multi-user system: user-created projects/monitors via Telegram, manual-first scheduling, per-user Drive isolation |
| v5.1 | Cloud MVP: Railway + Telegram bot + Google Drive + Postgres dual backend |
| v5.0 | Multi-Monitor Trend Intelligence System (local only) |
| v4.1 | Reddit Parser with quality scoring and AI Handoff JSON |
| v4.0 | Multi-subreddit parser with Playwright (no Reddit API keys) |
