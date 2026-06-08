import os
from dotenv import load_dotenv

load_dotenv()

EXPORTS_DIR = os.path.join(os.path.dirname(__file__), "exports")

SUPPORTED_PERIODS = ["last_24h", "last_7d", "last_30d", "all"]
SUPPORTED_SORTS = ["hot", "new", "top", "rising", "controversial"]
SUPPORTED_EXPORTS = ["xlsx", "csv", "json"]
SUPPORTED_LANGUAGE_MODES = ["en", "ru", "uk", "mixed"]

PERIOD_TO_SECONDS = {
    "last_24h": 86400,
    "last_7d": 604800,
    "last_30d": 2592000,
    "all": None,
}

# Run mode presets: (sort, period)
RUN_MODES = {
    "hot_last_7d": ("hot", "last_7d"),
    "top_week": ("top", "last_7d"),
    "rising_24h": ("rising", "last_24h"),
}

# Keyword presets
KEYWORD_PRESETS = {
    "wellness_en": [
        "fatigue", "energy", "sleep", "magnesium", "vitamin", "supplement",
        "gut", "digestion", "inflammation", "immunity", "stress", "cortisol",
        "protein", "omega", "probiotic", "zinc", "iron", "deficiency",
    ],
    "wellness_ru": [
        "усталость", "энергия", "сон", "магний", "витамин", "добавка",
        "кишечник", "пищеварение", "воспаление", "иммунитет", "стресс",
        "белок", "омега", "пробиотик", "цинк", "железо", "дефицит",
    ],
    "wellness_uk": [
        "втома", "енергія", "сон", "магній", "вітамін", "добавка",
        "кишківник", "травлення", "запалення", "імунітет", "стрес",
        "білок", "омега", "пробіотик", "цинк", "залізо", "дефіцит",
    ],
    "crm_en": [
        "crm", "customer", "pipeline", "lead", "sales", "churn",
        "retention", "onboarding", "hubspot", "salesforce", "automation",
        "funnel", "conversion", "revenue", "subscription",
    ],
    "ai_en": [
        "llm", "gpt", "claude", "gemini", "openai", "anthropic",
        "prompt", "fine-tuning", "rag", "embedding", "inference",
        "agent", "chatbot", "ai tool", "machine learning",
    ],
}

BOT_AUTHORS = {"automoderator", "bot", "reddit"}
BOT_PHRASES = [
    "i am a bot",
    "this action was performed automatically",
    "i'm a bot",
    "beep boop",
    "*i am a bot*",
]
