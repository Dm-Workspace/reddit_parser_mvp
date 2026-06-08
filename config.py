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

# Run mode presets: sort, period, min_score, min_comments, limit, comments
RUN_MODES = {
    "hot_last_7d": {
        "sort": "hot",
        "period": "last_7d",
        "min_score": 3,
        "min_comments": 5,
        "limit": 100,
        "comments": 20,
    },
    "top_week": {
        "sort": "top",
        "period": "last_7d",
        "min_score": 5,
        "min_comments": 10,
        "limit": 100,
        "comments": 20,
    },
    "top_month": {
        "sort": "top",
        "period": "last_30d",
        "min_score": 10,
        "min_comments": 10,
        "limit": 100,
        "comments": 20,
    },
    "rising_24h": {
        "sort": "rising",
        "period": "last_24h",
        "min_score": 0,
        "min_comments": 2,
        "limit": 100,
        "comments": 10,
    },
}

# Subreddit presets
SUBREDDIT_PRESETS = {
    "wellness_en": [
        "nutrition", "Supplements", "Biohackers", "GutHealth", "Microbiome",
        "IBS", "SIBO", "Menopause", "AskWomenOver30", "Sleep", "Anxiety",
        "Nootropics", "loseit",
    ],
    "wellness_gut": [
        "GutHealth", "Microbiome", "IBS", "SIBO", "CrohnsDisease",
        "UlcerativeColitis", "nutrition", "Supplements",
    ],
    "wellness_women": [
        "Menopause", "AskWomenOver30", "PCOS", "TwoXChromosomes",
        "WomensHealth", "xxfitness", "loseit",
    ],
    "wellness_energy": [
        "Biohackers", "Nootropics", "Supplements", "Sleep", "nutrition",
        "Anxiety", "cfs", "ChronicFatigue",
    ],
    "crm_en": [
        "sales", "entrepreneur", "startups", "marketing",
        "smallbusiness", "SaaS", "CRM",
    ],
    "ai_en": [
        "artificial", "MachineLearning", "LocalLLaMA", "ChatGPT",
        "ClaudeAI", "singularity", "PromptEngineering",
    ],
    "ru_uk_mixed": [
        "russia", "ukraine", "ukraina", "rf", "podslushano",
    ],
}

# Keyword presets
KEYWORD_PRESETS = {
    "wellness_en": [
        "fatigue", "energy", "sleep", "magnesium", "vitamin", "supplement",
        "gut", "digestion", "inflammation", "immunity", "stress", "cortisol",
        "protein", "omega", "probiotic", "zinc", "iron", "deficiency",
        "bloating", "brain fog", "anxiety", "mood", "thyroid",
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

SMALL_DATASET_MIN_POSTS = 20
SMALL_DATASET_MIN_COMMENTS = 100
SMALL_DATASET_WARNING = (
    "WARNING: Dataset is too small for trend analysis. "
    "Try broader subreddit preset, lower thresholds, or longer period."
)
