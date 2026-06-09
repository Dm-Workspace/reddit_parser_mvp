# Multi-Monitor Trend Intelligence System v5

Reddit-парсер с мониторингом, расписанием и AI-готовым экспортом.  
Работает **без API ключей** — использует Playwright (headless Chrome).

---

## Что это?

Система для автоматического сбора трендов из Reddit по нескольким проектам и нишам:

- **Projects** — проекты (energy_reboot, up_level и т.д.)
- **Monitors** — настройки мониторинга (subreddit + keywords + run_mode + cron)
- **Runs** — история запусков в SQLite
- **Exports** — Excel / JSON / AI Handoff JSON

---

## Установка

```bash
pip install -r requirements.txt
playwright install chromium
```

---

## Быстрый старт — прямой парсинг (v4 режим)

```bash
# Wellness — горячие за 7 дней
python main.py parse --subreddit-preset wellness_en --keyword-preset wellness_en --run-mode hot_last_7d --export xlsx

# CRM — rising за 24 часа
python main.py parse --subreddit-preset crm_en --keyword-preset crm_en --run-mode rising_24h --export xlsx

# AI — топ за месяц
python main.py parse --subreddit-preset ai_en --keyword-preset ai_en --run-mode top_month --export xlsx

# Свои сабреддиты + ключевые слова
python main.py parse --subreddits "fitness,nutrition,loseit" --keywords "protein,supplement,diet" --run-mode hot_last_7d
```

---

## CLI — все команды v5

### Список мониторов
```bash
python main.py list-monitors
```

### Запустить один монитор
```bash
python main.py run-monitor --monitor-id wellness_hot
python main.py run-monitor --monitor-id wellness_rising
python main.py run-monitor --monitor-id up_level_crm
```

### Запустить все активные мониторы
```bash
python main.py run-all
```

### История запусков
```bash
python main.py list-runs
python main.py list-runs --limit 50
```

### Запустить планировщик (cron-демон)
```bash
python main.py scheduler
```

---

## monitors.yaml — конфигурация мониторов

Все проекты и мониторы описываются в `monitors.yaml`:

```yaml
timezone: Europe/Podgorica

projects:
  - id: energy_reboot
    name: Energy Reboot
    language: en
    market: US wellness
    default_output_language: en

monitors:
  - id: wellness_hot
    project_id: energy_reboot
    name: Wellness Hot 7d
    subreddit_preset: wellness_en
    keyword_preset: wellness_en
    run_mode: hot_last_7d
    schedule_cron: "0 8 * * *"   # каждый день в 08:00
    timezone: Europe/Podgorica
    enabled: true
    export_formats: [xlsx, json]
```

При запуске `run-monitor` / `run-all` / `scheduler` конфиг автоматически синхронизируется в SQLite.

---

## Режимы запуска (run_mode)

| Mode | Sort | Period | Min Score | Min Comments | Posts/sub |
|------|------|--------|-----------|--------------|-----------|
| `hot_last_7d` | hot | last_7d | 3 | 5 | 50 |
| `top_week` | top | last_7d | 10 | 10 | 25 |
| `top_month` | top | last_30d | 20 | 15 | 25 |
| `rising_24h` | rising | last_24h | 1 | 1 | 30 |

---

## Subreddit Presets

| Preset | Сабреддиты |
|--------|-----------|
| `wellness_en` | 13 EN wellness сабреддитов |
| `wellness_gut` | gut health фокус |
| `wellness_women` | женское здоровье |
| `wellness_energy` | энергия / усталость |
| `crm_en` | CRM / продажи |
| `ai_en` | AI / ML |

---

## Структура экспортов

```
exports/
  {project_id}/
    {monitor_id}/
      {run_id}/
        report_YYYYMMDD_HHMMSS.xlsx
        report_YYYYMMDD_HHMMSS.json
        handoff.json          ← AI Handoff JSON
data/
  tracker.db                  ← SQLite (runs, exports, monitors)
```

---

## AI Handoff JSON

Файл `handoff.json` создаётся автоматически при каждом запуске монитора.  
Содержит готовые данные для передачи в LLM-агент:

```json
{
  "schema_version": "5.0",
  "project": { ... },
  "monitor": { ... },
  "run": { "status": "completed", "total_posts": 91 },
  "summary": {
    "pain_signal_distribution": {"energy_fatigue": 23, "sleep_problem": 17},
    "analysis_priority_distribution": {"high": 12, "medium": 45, "low": 34}
  },
  "top_posts": [ ... ],           // топ 30 постов по trend_score
  "keyword_summary": [ ... ],     // частота ключевых слов
  "selected_comments": [ ... ],   // топ 100 комментариев
  "recommended_ai_tasks": [       // задачи для AI агента
    {"task": "sentiment_analysis", ...},
    {"task": "pain_clustering", ...},
    {"task": "content_angles", ...},
    {"task": "audience_voice", ...},
    {"task": "trend_summary", ...}
  ]
}
```

---

## Планировщик (APScheduler)

```bash
python main.py scheduler
```

- Читает `monitors.yaml`, добавляет cron-джобы
- `max_instances=1` — не запускает монитор параллельно
- `misfire_grace_time=3600` — пропускает пропущенные запуски старше 1 часа
- Timezone задаётся на уровне каждого монитора

---

## Параметры parse-режима

```
python main.py parse [OPTIONS]

Источник (один из):
  --subreddits TEXT           через запятую: "fitness,nutrition"
  --subreddit-preset TEXT     wellness_en | crm_en | ai_en | ...

Ключевые слова (опционально):
  --keywords TEXT             через запятую
  --keyword-preset TEXT       wellness_en | crm_en | ai_en | ...

Настройки:
  --run-mode TEXT             hot_last_7d | top_week | top_month | rising_24h
  --period TEXT               last_24h | last_7d | last_30d | all
  --sort TEXT                 hot | new | top | rising | controversial
  --limit INT                 постов на сабреддит
  --comments INT              комментариев на пост
  --min-score INT
  --min-comments INT
  --min-comment-length INT    (default: 40)
  --language-mode TEXT        en | ru | uk | mixed

Флаги:
  --no-bots                   не фильтровать ботов
  --no-selftext               не загружать тексты постов

Экспорт:
  --export TEXT               xlsx | csv | json (default: xlsx)
  --output TEXT               имя файла без расширения
```

---

## Excel — структура файла

| Лист | Содержимое |
|------|-----------|
| Summary | Сводка по запуску |
| Top Posts | Топ 20 по trend_score с цветовой разметкой |
| Posts | Все посты с полями анализа |
| Comments | Все комментарии |
| Keyword Summary | Частота ключевых слов |
| Quality Check | Диагностика качества данных |
| Run Settings | Параметры запуска |

---

## Версии

- **v5.0** — Multi-Monitor System, SQLite, monitors.yaml, APScheduler, AI Handoff JSON
- **v4.1** — pain_signal, analysis_priority, content_type, text_status, Top Posts sheet
- **v4.0** — subreddit presets, keyword presets, 4 run modes
- **v3.0** — selftext, comment_match_type, min_comment_length
- **v2.0** — Playwright scraping (без API ключей)
- **v1.0** — MVP (PRAW, требовал API ключи)
