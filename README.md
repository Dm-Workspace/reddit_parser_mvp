# Reddit Parser MVP

Инструмент для сбора постов и комментариев из Reddit с экспортом в Excel, CSV или JSON.
Работает **без API ключей** — использует Playwright (headless Chrome) для обхода блокировок.

---

## Описание

Reddit Parser MVP — standalone Python-скрипт с CLI-интерфейсом. Позволяет:
- собирать посты из нескольких subreddit одновременно
- фильтровать по ключевым словам, периоду, min_score, min_comments
- собирать top-комментарии к каждому посту
- фильтровать бот-комментарии (AutoModerator и др.)
- определять язык контента (en/ru/uk/mixed)
- дедуплицировать результаты
- экспортировать в Excel (5 листов), CSV (2 файла) или JSON

---

## Установка

```bash
pip install -r requirements.txt
playwright install chromium
```

Файл `.env` не нужен — API ключи не используются.

---

## Примеры запуска

### Базовый — все посты за неделю, экспорт в Excel
```bash
python main.py --subreddits nutrition,Supplements --period last_7d --sort hot --limit 50 --export xlsx
```

### С ключевыми словами
```bash
python main.py --subreddits nutrition,Biohackers --keywords magnesium,vitamin,gut --period last_7d --export xlsx
```

### Готовый keyword preset
```bash
python main.py --subreddits nutrition,Supplements --keyword-preset wellness_en --export xlsx
```

### Run mode shortcuts
```bash
# hot + last 7 days
python main.py --subreddits Supplements --run-mode hot_last_7d --export xlsx

# top posts за неделю
python main.py --subreddits nutrition --run-mode top_week --limit 100 --export xlsx

# rising за последние 24h
python main.py --subreddits Biohackers --run-mode rising_24h --export csv
```

### Только английский контент, без ботов
```bash
python main.py --subreddits nutrition --keyword-preset wellness_en --language-mode en --export xlsx
```

### Без сбора selftext (быстрее)
```bash
python main.py --subreddits nutrition --limit 100 --no-selftext --export xlsx
```

### Полный запуск с комментариями
```bash
python main.py \
  --subreddits nutrition,Supplements,Biohackers \
  --keyword-preset wellness_en \
  --run-mode top_week \
  --limit 100 \
  --comments 20 \
  --min-score 5 \
  --min-comments 10 \
  --language-mode en \
  --export xlsx
```

---

## Аргументы CLI

| Аргумент | По умолчанию | Описание |
|---|---|---|
| `--subreddits` | обязательный | Subreddit через запятую |
| `--keywords` | "" | Ключевые слова через запятую |
| `--keyword-preset` | — | Готовый набор: wellness_en/ru/uk, crm_en, ai_en |
| `--period` | last_7d | last_24h / last_7d / last_30d / all |
| `--sort` | hot | hot / new / top / rising / controversial |
| `--run-mode` | — | hot_last_7d / top_week / rising_24h |
| `--limit` | 50 | Макс. постов на subreddit |
| `--comments` | 20 | Макс. комментариев на пост |
| `--min-score` | **5** | Минимальный score поста |
| `--min-comments` | **10** | Мин. количество комментариев у поста |
| `--language-mode` | mixed | Фильтр языка: en / ru / uk / mixed |
| `--no-bots` | false | Отключить фильтр ботов (по умолчанию боты фильтруются) |
| `--no-selftext` | false | Не загружать текст поста (быстрее) |
| `--export` | xlsx | xlsx / csv / json |
| `--output` | авто | Имя файла без расширения |
| `--verbose` | — | Debug-логи |

---

## Keyword Presets

| Preset | Язык | Охват |
|---|---|---|
| wellness_en | EN | fatigue, magnesium, vitamin, gut, supplement... |
| wellness_ru | RU | усталость, магний, витамин, кишечник... |
| wellness_uk | UK | втома, магній, вітамін, кишківник... |
| crm_en | EN | crm, pipeline, lead, churn, hubspot... |
| ai_en | EN | llm, gpt, claude, prompt, rag, agent... |

---

## Run Modes

| Mode | Sort | Period |
|---|---|---|
| hot_last_7d | hot | last_7d |
| top_week | top | last_7d |
| rising_24h | rising | last_24h |

---

## Формат выгрузки Excel (5 листов)

| Лист | Содержимое |
|---|---|
| **Summary** | Итоговая статистика запуска |
| **Posts** | Все посты со всеми полями |
| **Comments** | Все комментарии со всеми полями |
| **Run Settings** | Все параметры запуска |
| **Quality Check** | Метрики качества данных |

### Поля постов

| Поле | Описание |
|---|---|
| post_id | ID поста |
| subreddit | Subreddit |
| title | Заголовок |
| selftext | Текст поста (только для self-постов) |
| url | URL |
| permalink | Ссылка на Reddit |
| created_utc / created_date | Дата создания |
| score | Upvotes |
| upvote_ratio | Доля upvotes |
| num_comments | Кол-во комментариев |
| flair | Flair поста |
| is_self | True если текстовый пост |
| is_video | True если видео |
| domain | Домен |
| matched_keywords | Совпавшие ключевые слова |
| sort_mode | Режим сортировки |
| post_text_length | Длина текста поста |
| language_detected | Определённый язык (en/ru/uk/mixed) |
| trend_score | score + num_comments×2 |
| collected_at | Время сбора |

### Поля комментариев

| Поле | Описание |
|---|---|
| comment_id | ID комментария |
| post_id / post_title | Родительский пост |
| subreddit | Subreddit |
| author | Автор комментария |
| body | Текст |
| score | Score |
| created_utc / created_date | Дата |
| depth | Уровень вложенности |
| permalink | Ссылка |
| matched_keywords | Ключевые слова |
| comment_text_length | Длина текста |
| language_detected | Язык |
| is_bot_comment | True если бот |
| collected_at | Время сбора |

### Quality Check — метрики

- total_posts / total_comments
- empty_selftext_count — постов без текста
- bot_comments_count — отфильтровано бот-комментариев
- low_score_posts_count — постов с score < 5
- duplicate_posts_removed — удалено дублей
- comments_without_keywords — комментариев без совпадения по keywords
- language distribution — распределение языков

---

## Ограничения

- Парсинг медленнее чем через API (~2–5 сек на страницу) — Playwright запускает реальный браузер
- Reddit может временно показывать капчу — в таком случае подожди 5–10 минут и повтори
- Selftext доступен только для текстовых постов (is_self=True)
- Для постов с is_self=False selftext пустой — это нормально

---

## Структура проекта

```
reddit_parser_mvp/
├── main.py
├── config.py
├── reddit_client.py
├── reddit_parser.py
├── reddit_filters.py
├── reddit_models.py
├── requirements.txt
├── .env.example
├── exporters/
│   ├── excel_exporter.py
│   ├── csv_exporter.py
│   └── json_exporter.py
├── utils/
│   ├── date_utils.py
│   ├── text_cleaner.py
│   ├── deduplication.py
│   ├── language_utils.py
│   └── logger.py
├── storage/
│   └── database.py
└── exports/
```

---

## Что не входит в MVP

- AI-анализ (sentiment, кластеризация)
- Авторизация пользователя Reddit
- База данных / история запусков
- Экспорт в Google Sheets
- Webhook / уведомления

## Следующие итерации

### Итерация 2
- SQLite для хранения истории и межсессионной дедупликации
- Расширенная фильтрация по автору, flair, upvote_ratio

### Итерация 3 — AI
- Sentiment analysis постов и комментариев
- Кластеризация по темам
- Выделение болей и вопросов аудитории

### Итерация 4 — Автоматизация
- Планировщик (cron / schedule)
- Telegram/Email уведомления
- Streamlit-дашборд
