# Reddit Parser MVP

Инструмент для сбора постов и комментариев из Reddit с экспортом в Excel, CSV или JSON.

---

## Описание

Reddit Parser MVP — standalone Python-скрипт с CLI-интерфейсом. Позволяет:
- собирать посты из нескольких subreddit одновременно
- фильтровать по ключевым словам, периоду, min_score, min_comments
- собирать top-комментарии к каждому посту
- дедуплицировать результаты
- экспортировать в Excel (4 листа), CSV (2 файла) или JSON

---

## Как создать Reddit App

1. Зайди на https://www.reddit.com/prefs/apps
2. Нажми **"Create App"** или **"Create Another App"**
3. Заполни:
   - **Name**: `reddit_parser_mvp` (любое название)
   - **App type**: выбери **script**
   - **Description**: опционально
   - **About URL**: можно оставить пустым
   - **Redirect URI**: `http://localhost:8080`
4. Нажми **"Create app"**
5. Скопируй:
   - `client_id` — строка под названием приложения (под "personal use script")
   - `client_secret` — поле "secret"

---

## Настройка ENV

Скопируй `.env.example` в `.env` и заполни:

```bash
cp .env.example .env
```

```env
REDDIT_CLIENT_ID=your_client_id_here
REDDIT_CLIENT_SECRET=your_client_secret_here
REDDIT_USER_AGENT=reddit_parser_mvp/1.0 by YourUsername
```

`REDDIT_USER_AGENT` — произвольная строка, идентифицирующая твоё приложение. Используй формат: `AppName/Version by Username`.

---

## Установка зависимостей

```bash
pip install -r requirements.txt
```

---

## Примеры запуска

### Базовый запуск — nutrition + ключевые слова, экспорт в Excel
```bash
python main.py \
  --subreddits nutrition,Supplements,Biohackers \
  --keywords fatigue,magnesium,gut-health \
  --period last_7d \
  --sort hot \
  --limit 50 \
  --comments 20 \
  --min-score 0 \
  --min-comments 0 \
  --export xlsx
```

### Собрать все посты без фильтра по словам, экспорт в CSV
```bash
python main.py \
  --subreddits fitness \
  --period last_30d \
  --sort top \
  --limit 100 \
  --export csv
```

### Экспорт в JSON с кастомным именем файла
```bash
python main.py \
  --subreddits keto,carnivore \
  --keywords protein,insulin \
  --export json \
  --output keto_report_june
```

### Verbose-режим (debug логи)
```bash
python main.py --subreddits nutrition --export xlsx --verbose
```

---

## Аргументы CLI

| Аргумент | Тип | По умолчанию | Описание |
|---|---|---|---|
| `--subreddits` | str | обязательный | Subreddit через запятую |
| `--keywords` | str | "" (все посты) | Ключевые слова через запятую |
| `--period` | choice | last_7d | last_24h / last_7d / last_30d / all |
| `--sort` | choice | hot | hot / new / top / rising / controversial |
| `--limit` | int | 50 | Макс. постов на subreddit |
| `--comments` | int | 20 | Макс. комментариев на пост (0 = не собирать) |
| `--min-score` | int | 0 | Минимальный score поста |
| `--min-comments` | int | 0 | Мин. количество комментариев у поста |
| `--export` | choice | xlsx | xlsx / csv / json |
| `--output` | str | авто | Имя файла без расширения |
| `--verbose` | flag | — | Включить debug-логи |

---

## Формат выгрузки

### Excel (`.xlsx`) — 4 листа:

**Summary** — итоговая статистика запуска  
**Posts** — все собранные посты  
**Comments** — все собранные комментарии  
**Run Settings** — параметры запуска

### CSV — 2 файла:
- `exports/reddit_YYYYMMDD_HHMM_posts.csv`
- `exports/reddit_YYYYMMDD_HHMM_comments.csv`

### JSON — 1 файл:
```json
{
  "summary": { ... },
  "posts": [ ... ],
  "comments": [ ... ]
}
```

---

## Поля постов

| Поле | Описание |
|---|---|
| post_id | Уникальный ID поста |
| subreddit | Название subreddit |
| title | Заголовок поста |
| selftext | Текст поста |
| url | URL поста или ссылки |
| permalink | Прямая ссылка на Reddit |
| created_utc | Unix timestamp создания |
| created_date | Дата создания (UTC) |
| score | Количество upvotes |
| upvote_ratio | Доля upvotes (0–1) |
| num_comments | Количество комментариев |
| flair | Flair поста |
| is_self | True если текстовый пост |
| is_video | True если видео |
| domain | Домен ссылки |
| matched_keywords | Совпавшие ключевые слова |
| sort_mode | Режим сортировки при сборе |
| collected_at | Время сбора (UTC) |

## Поля комментариев

| Поле | Описание |
|---|---|
| comment_id | Уникальный ID комментария |
| post_id | ID родительского поста |
| subreddit | Название subreddit |
| post_title | Заголовок поста |
| body | Текст комментария |
| score | Score комментария |
| created_utc | Unix timestamp |
| created_date | Дата создания (UTC) |
| depth | Глубина вложенности |
| permalink | Прямая ссылка |
| matched_keywords | Совпавшие ключевые слова |
| collected_at | Время сбора (UTC) |

---

## Ограничения Reddit API

- **Rate limit**: ~60 запросов в минуту для read-only приложений
- **Максимум постов**: PRAW ограничивает выборку ~1000 постов на subreddit при `new`/`hot`/`top`
- **Комментарии**: глубокие ветки (`MoreComments`) по умолчанию не раскрываются (только top-level и прямые ответы)
- **Период**: фильтрация по дате происходит на стороне парсера, а не API. Reddit возвращает N последних постов по сортировке, из них отфильтровываются нужные по дате

---

## Что НЕ входит в MVP

- AI-анализ текстов (sentiment, clustering, summarization)
- Авторизация под пользователем (только read-only OAuth)
- Мониторинг / периодический запуск
- База данных / история запусков
- Парсинг User-информации (профили авторов)
- Обход rate limit с задержками (реализовано в PRAW автоматически)
- Экспорт в Google Sheets
- Webhook / уведомления

---

## План следующих итераций

### Итерация 2 — Качество данных
- Раскрытие вложенных комментариев (`replace_more(limit=N)`)
- Умная задержка при rate limit
- SQLite для хранения истории запусков и дедупликации между сессиями

### Итерация 3 — AI-анализ
- Sentiment analysis постов и комментариев
- Кластеризация по темам
- Выделение ключевых болей/вопросов аудитории

### Итерация 4 — Автоматизация
- Планировщик задач (cron / schedule)
- Telegram/Email уведомления о новых постах
- Дашборд в Streamlit

---

## Файлы

```
reddit_parser_mvp/
├── main.py              # CLI entry point
├── config.py            # ENV и константы
├── reddit_client.py     # Инициализация PRAW
├── reddit_parser.py     # Основная логика сбора
├── reddit_filters.py    # Фильтрация постов/комментариев
├── reddit_models.py     # Dataclass-модели
├── requirements.txt     # Зависимости
├── .env.example         # Шаблон ENV
├── exporters/
│   ├── excel_exporter.py
│   ├── csv_exporter.py
│   └── json_exporter.py
├── utils/
│   ├── date_utils.py
│   ├── text_cleaner.py
│   ├── deduplication.py
│   └── logger.py
├── storage/
│   └── database.py      # Placeholder для БД
└── exports/             # Файлы выгрузки
```
