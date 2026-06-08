# Reddit Parser MVP

Инструмент для сбора постов и комментариев из Reddit с экспортом в Excel.  
Работает **без API ключей** — использует Playwright (headless Chrome).

---

## Быстрый старт

```bash
pip install -r requirements.txt
playwright install chromium

# Основной режим — анализ трендов за неделю (91+ постов)
python main.py --subreddit-preset wellness_en --keyword-preset wellness_en --run-mode hot_last_7d --export xlsx

# Ранние сигналы — что набирает популярность прямо сейчас
python main.py --subreddit-preset wellness_en --keyword-preset wellness_en --run-mode rising_24h --export xlsx

# Подтверждённые темы за месяц
python main.py --subreddit-preset wellness_en --keyword-preset wellness_en --run-mode top_month --export xlsx
```

---

## Run Modes

| Mode | Sort | Period | min_score | min_cmts | Назначение |
|---|---|---|---|---|---|
| **hot_last_7d** | hot | last_7d | 3 | 5 | ✅ Основной режим анализа (91+ постов) |
| **rising_24h** | rising | last_24h | 0 | 2 | ✅ Ранние сигналы, новые темы (41+ постов) |
| **top_month** | top | last_30d | 10 | 10 | ✅ Подтверждённые темы, высокое качество |
| **top_week** | top | last_7d | 5 | 10 | ⚠ Может давать маленькую выборку (14 постов) |

> **top_week** выдаёт мало результатов — используй top_month для ретроспективного анализа.

---

## Subreddit Presets

| Preset | Subreddits |
|---|---|
| wellness_en | nutrition, Supplements, Biohackers, GutHealth, Microbiome, IBS, SIBO, Menopause, AskWomenOver30, Sleep, Anxiety, Nootropics, loseit |
| wellness_gut | GutHealth, Microbiome, IBS, SIBO, CrohnsDisease, UlcerativeColitis, nutrition, Supplements |
| wellness_women | Menopause, AskWomenOver30, PCOS, TwoXChromosomes, WomensHealth, xxfitness, loseit |
| wellness_energy | Biohackers, Nootropics, Supplements, Sleep, nutrition, Anxiety, cfs, ChronicFatigue |
| crm_en | sales, entrepreneur, startups, marketing, smallbusiness, SaaS, CRM |
| ai_en | artificial, MachineLearning, LocalLLaMA, ChatGPT, ClaudeAI, singularity, PromptEngineering |

---

## Keyword Presets

| Preset | Примеры |
|---|---|
| wellness_en | fatigue, energy, sleep, magnesium, vitamin, gut, probiotic, anxiety... |
| wellness_ru | усталость, энергия, магний, витамин, кишечник... |
| wellness_uk | втома, енергія, магній, вітамін... |
| crm_en | crm, pipeline, lead, churn, hubspot, salesforce... |
| ai_en | llm, gpt, claude, prompt, rag, agent... |

---

## Все аргументы CLI

| Аргумент | По умолчанию | Описание |
|---|---|---|
| `--subreddits` | — | Subreddit через запятую (или `--subreddit-preset`) |
| `--subreddit-preset` | — | Готовый список subreddit |
| `--keywords` | "" | Ключевые слова (или `--keyword-preset`) |
| `--keyword-preset` | — | Готовый набор ключевых слов |
| `--run-mode` | — | hot_last_7d / top_week / top_month / rising_24h |
| `--period` | last_7d | Если run-mode не задан |
| `--sort` | hot | Если run-mode не задан |
| `--limit` | 50 | Переопределяет лимит run-mode |
| `--comments` | 20 | Макс. комментариев на пост |
| `--min-score` | 5 | Переопределяет порог run-mode |
| `--min-comments` | 10 | Переопределяет порог run-mode |
| `--min-comment-length` | 40 | Мин. длина комментария (игнорируется если score > 10) |
| `--language-mode` | mixed | en / ru / uk / mixed |
| `--no-bots` | — | Оставить бот-комментарии (по умолчанию фильтруются) |
| `--no-selftext` | — | Не загружать текст поста (быстрее) |
| `--export` | xlsx | xlsx / csv / json |
| `--output` | авто | Имя файла без расширения |
| `--verbose` | — | Debug-логи |

---

## Формат Excel (7 листов)

| Лист | Описание |
|---|---|
| **Summary** | Итог запуска + предупреждение о маленькой выборке |
| **Top Posts** | Топ-30 постов по trend_score с приоритетом и pain signal. Зелёный = high priority |
| **Posts** | Все посты со всеми полями |
| **Comments** | Все комментарии со всеми полями |
| **Keyword Summary** | Частота каждого keyword в постах и комментариях |
| **Quality Check** | Метрики качества, распределение по subreddit, языкам, pain signals |
| **Run Settings** | Все параметры запуска |

---

## Поля постов

| Поле | Описание |
|---|---|
| post_id / subreddit / title / selftext / url / permalink | Основные данные |
| created_date | Дата создания (UTC) |
| score / upvote_ratio / num_comments | Метрики вовлечённости |
| flair / is_self / is_video / domain | Мета-данные |
| matched_keywords | Совпавшие ключевые слова |
| post_text_length | Длина текста поста |
| language_detected | en / ru / uk / mixed / unknown |
| trend_score | score + num_comments × 2 |
| **content_type** | self_text / image / video / external_link / reddit_gallery |
| **analysis_priority** | high (trend≥250 или cmts≥80) / medium / low |
| **pain_signal** | sleep_problem / anxiety_stress / gut_problem / low_energy / supplement_question / hormone_women / brain_cognition / weight_metabolism / other |

## Поля комментариев

| Поле | Описание |
|---|---|
| comment_id / post_id / post_title / subreddit | Привязка к посту |
| author / body / score | Контент |
| created_date / depth / permalink | Мета-данные |
| comment_text_length / language_detected | Качество |
| is_bot_comment | True если AutoModerator или фраза "i am a bot" |
| **comment_match_type** | direct_keyword_match / context_comment / no_match |

---

## Pain Signals — маппинг

| Signal | Ключевые слова |
|---|---|
| sleep_problem | sleep, insomnia, tired, fatigue, melatonin... |
| anxiety_stress | anxiety, stress, cortisol, burnout, mood... |
| gut_problem | gut, bloating, ibs, probiotic, microbiome... |
| low_energy | energy, brain fog, exhausted, adrenal... |
| supplement_question | supplement, vitamin, magnesium, dosage... |
| hormone_women | menopause, pcos, estrogen, thyroid... |
| brain_cognition | focus, memory, nootropic, adhd... |
| weight_metabolism | weight, keto, insulin, blood sugar... |

---

## Ограничения

- Playwright медленнее API (~2–5 сек/страницу)
- Selftext только для self-постов (is_self=True)
- Reddit может показывать капчу — подожди 5–10 мин

---

## Структура проекта

```
reddit_parser_mvp/
├── main.py              CLI entry point
├── config.py            Presets, run modes, pain signals
├── reddit_client.py     Playwright browser init
├── reddit_parser.py     Сбор постов и комментариев
├── reddit_filters.py    Фильтрация
├── reddit_models.py     Dataclass RedditPost + RedditComment
├── requirements.txt
├── exporters/
│   ├── excel_exporter.py   7 листов Excel
│   ├── csv_exporter.py
│   └── json_exporter.py
├── utils/
│   ├── date_utils.py
│   ├── text_cleaner.py
│   ├── deduplication.py
│   ├── language_utils.py
│   └── logger.py
└── exports/             Файлы выгрузки
```

---

## Следующие итерации

### Итерация 4 — AI-анализ
- Sentiment analysis постов и комментариев
- Кластеризация по pain signals
- Выделение цитат для маркетинговых материалов

### Итерация 5 — Автоматизация
- Планировщик (cron)
- Telegram-уведомления о новых трендах
- SQLite для истории запусков
