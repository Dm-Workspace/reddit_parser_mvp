"""
Preset packs — niche-level preset bundles with source-specific configs.
Each pack bundles Reddit and YouTube settings for a given topic/niche.
"""
from typing import Optional
from fastapi import APIRouter

router = APIRouter()

# ── Preset packs data ──────────────────────────────────────────────────────────

PRESET_PACKS = [
    {
        "id": "nutrition_health",
        "label": "Нутрициология и здоровье",
        "description": "Питание, дефициты, энергия, сон, ЖКТ, добавки, гормоны, профилактика.",
        "sources": ["reddit", "youtube"],
        "reddit": {
            "subreddits": [
                "nutrition", "Supplements", "Biohackers", "GutHealth", "Microbiome",
                "IBS", "SIBO", "Menopause", "Sleep", "Anxiety", "Nootropics",
                "loseit", "xxfitness", "AskWomenOver30",
            ],
            "keywords": [
                "nutrition", "supplements", "vitamin D", "magnesium", "iron", "ferritin",
                "gut health", "bloating", "IBS", "SIBO", "microbiome", "sleep", "fatigue",
                "brain fog", "energy", "hormones", "menopause", "weight loss", "anxiety",
                "stress", "cortisol", "inflammation",
            ],
            "default_run_mode": "hot_last_7d",
            "default_language_mode": "en",
        },
        "youtube": {
            "search_queries": [
                "gut health nutrition tips",
                "how to fix bloating naturally",
                "vitamin D deficiency symptoms",
                "magnesium for sleep and anxiety",
                "nutrition for fatigue and brain fog",
                "hormone balance women nutrition",
                "microbiome health explained",
                "anti inflammatory diet explained",
                "best supplements for energy",
                "how to improve sleep naturally",
            ],
            "channels": [],
            "published_period": "last_90d",
            "min_views": 1000,
            "max_results": 50,
            "include_shorts": False,
            "include_comments": True,
            "max_comments_per_video": 20,
            "language": "en",
            "region": "US",
        },
        "analysis": {
            "focus": ["audience_pains", "questions", "objections", "content_angles", "offer_insights"],
        },
    },
    {
        "id": "psychology_therapy",
        "label": "Психология и терапия",
        "description": "Тревога, выгорание, отношения, самооценка, границы, терапия, эмоциональная регуляция.",
        "sources": ["reddit", "youtube"],
        "reddit": {
            "subreddits": [
                "psychology", "therapy", "AskTherapists", "mentalhealth", "Anxiety",
                "depression", "DecidingToBeBetter", "selfimprovement", "relationships",
                "attachment_theory", "CPTSD", "socialskills",
            ],
            "keywords": [
                "anxiety", "burnout", "therapy", "trauma", "boundaries", "self esteem",
                "attachment", "emotional regulation", "relationships", "stress",
                "overthinking", "avoidance", "people pleasing", "inner critic",
                "shame", "confidence", "self worth",
            ],
            "default_run_mode": "hot_last_7d",
            "default_language_mode": "en",
        },
        "youtube": {
            "search_queries": [
                "how to deal with anxiety",
                "therapy for burnout",
                "emotional regulation techniques",
                "how to set boundaries",
                "overthinking and anxiety help",
                "attachment styles explained",
                "people pleasing recovery",
                "self esteem exercises",
                "inner critic therapy",
                "trauma healing explained",
            ],
            "channels": [],
            "published_period": "last_90d",
            "min_views": 500,
            "max_results": 50,
            "include_shorts": False,
            "include_comments": True,
            "max_comments_per_video": 20,
            "language": "en",
            "region": "US",
        },
        "analysis": {
            "focus": ["audience_pains", "questions", "objections", "language_patterns", "content_angles"],
        },
    },
    {
        "id": "coaching_growth",
        "label": "Коучинг и личное развитие",
        "description": "Цели, привычки, прокрастинация, личная эффективность, изменения и самодисциплина.",
        "sources": ["reddit", "youtube"],
        "reddit": {
            "subreddits": [
                "selfimprovement", "getdisciplined", "productivity", "DecidingToBeBetter",
                "habits", "NonZeroDay", "LifeProTips", "careerguidance", "findapath",
            ],
            "keywords": [
                "goals", "motivation", "habits", "discipline", "procrastination",
                "focus", "productivity", "routine", "mindset", "consistency",
                "life change", "personal growth", "accountability", "planning", "overwhelm",
            ],
            "default_run_mode": "hot_last_7d",
            "default_language_mode": "en",
        },
        "youtube": {
            "search_queries": [
                "how to build discipline",
                "how to stop procrastinating",
                "goal setting system",
                "personal growth habits",
                "productivity routine",
                "how to stay consistent",
                "morning routine productivity",
                "how to change your life",
                "accountability for goals",
                "focus and deep work tips",
            ],
            "channels": [],
            "published_period": "last_90d",
            "min_views": 500,
            "max_results": 50,
            "include_shorts": False,
            "include_comments": True,
            "max_comments_per_video": 20,
            "language": "en",
            "region": "US",
        },
        "analysis": {
            "focus": ["audience_pains", "questions", "hooks", "content_angles", "format_patterns"],
        },
    },
    {
        "id": "expert_business",
        "label": "Экспертная деятельность",
        "description": "Консультанты, эксперты, фрилансеры, упаковка опыта, продажа услуг и масштабирование.",
        "sources": ["reddit", "youtube"],
        "reddit": {
            "subreddits": [
                "Entrepreneur", "smallbusiness", "freelance", "consulting", "coaching",
                "marketing", "sales", "solopreneur", "SaaS",
            ],
            "keywords": [
                "consulting", "expert", "coach", "client", "service business",
                "positioning", "personal brand", "offer", "pricing", "sales",
                "lead generation", "boundaries", "burnout", "scale", "audience",
                "authority", "content", "community",
            ],
            "default_run_mode": "hot_last_7d",
            "default_language_mode": "en",
        },
        "youtube": {
            "search_queries": [
                "how to sell consulting services",
                "how to get coaching clients",
                "how to price consulting services",
                "personal brand for consultants",
                "how to package your expertise",
                "how to create a coaching offer",
                "how to scale service business",
                "how to set boundaries with clients",
                "how to sell expert services",
                "content strategy for consultants",
            ],
            "channels": [],
            "published_period": "last_90d",
            "min_views": 500,
            "max_results": 50,
            "include_shorts": False,
            "include_comments": True,
            "max_comments_per_video": 20,
            "language": "en",
            "region": "US",
        },
        "analysis": {
            "focus": ["audience_pains", "offer_insights", "objections", "content_angles", "hooks"],
        },
    },
    {
        "id": "service_marketing",
        "label": "Маркетинг услуг",
        "description": "Продвижение консультаций, услуг, агентств, воронки, лидогенерация, CRM.",
        "sources": ["reddit", "youtube"],
        "reddit": {
            "subreddits": [
                "marketing", "sales", "Entrepreneur", "smallbusiness", "SaaS",
                "CRM", "advertising", "socialmedia", "copywriting", "agency",
            ],
            "keywords": [
                "marketing", "sales funnel", "lead generation", "content marketing",
                "CRM", "pipeline", "conversion", "retention", "onboarding",
                "customer acquisition", "offer", "copywriting", "positioning",
                "service business", "agency", "automation", "email marketing", "social media",
            ],
            "default_run_mode": "hot_last_7d",
            "default_language_mode": "en",
        },
        "youtube": {
            "search_queries": [
                "lead generation for service business",
                "marketing for consultants",
                "how to get clients for agency",
                "sales funnel for services",
                "CRM for small business",
                "how to sell high ticket services",
                "content marketing for service business",
                "client acquisition strategy",
                "how to improve conversion rate",
                "service business marketing strategy",
            ],
            "channels": [],
            "published_period": "last_90d",
            "min_views": 500,
            "max_results": 50,
            "include_shorts": False,
            "include_comments": True,
            "max_comments_per_video": 20,
            "language": "en",
            "region": "US",
        },
        "analysis": {
            "focus": ["audience_pains", "objections", "offer_insights", "content_angles", "hooks"],
        },
    },
    {
        "id": "online_courses",
        "label": "Онлайн-курсы и инфопродукты",
        "description": "Создание, упаковка, запуск и продажа онлайн-курсов, программ и образовательных продуктов.",
        "sources": ["reddit", "youtube"],
        "reddit": {
            "subreddits": [
                "Entrepreneur", "instructionaldesign", "elearning", "marketing",
                "sales", "smallbusiness", "SaaS",
            ],
            "keywords": [
                "online course", "course launch", "info product", "digital product",
                "coaching program", "cohort", "webinar", "funnel", "curriculum",
                "students", "pricing", "conversion", "completion rate",
                "learning platform", "community",
            ],
            "default_run_mode": "hot_last_7d",
            "default_language_mode": "en",
        },
        "youtube": {
            "search_queries": [
                "how to create an online course",
                "how to launch an online course",
                "course creator marketing",
                "how to sell digital products",
                "webinar funnel for online course",
                "how to price online course",
                "cohort based course strategy",
                "how to create curriculum",
                "online course platform comparison",
                "how to increase course completion",
            ],
            "channels": [],
            "published_period": "last_90d",
            "min_views": 500,
            "max_results": 50,
            "include_shorts": False,
            "include_comments": True,
            "max_comments_per_video": 20,
            "language": "en",
            "region": "US",
        },
        "analysis": {
            "focus": ["audience_pains", "offer_insights", "objections", "content_angles", "format_patterns"],
        },
    },
    {
        "id": "ai_business_tools",
        "label": "AI-инструменты для бизнеса",
        "description": "AI-автоматизация, агенты, CRM, контент, маркетинг, продажи и бизнес-процессы.",
        "sources": ["reddit", "youtube"],
        "reddit": {
            "subreddits": [
                "ArtificialIntelligence", "ChatGPT", "ClaudeAI", "OpenAI", "AI_Agents",
                "automation", "SaaS", "Entrepreneur", "marketing", "smallbusiness",
            ],
            "keywords": [
                "AI tools", "AI agents", "automation", "ChatGPT", "Claude", "OpenAI",
                "workflow", "CRM automation", "content automation", "sales automation",
                "marketing automation", "no-code", "agents", "business process", "productivity",
            ],
            "default_run_mode": "rising_24h",
            "default_language_mode": "en",
        },
        "youtube": {
            "search_queries": [
                "best AI tools for business",
                "AI agents for automation",
                "ChatGPT for business workflows",
                "Claude AI for content creation",
                "AI automation for small business",
                "CRM automation with AI",
                "AI tools for marketing",
                "AI tools for sales",
                "no code AI automation",
                "AI agents tutorial",
            ],
            "channels": [],
            "published_period": "last_30d",
            "min_views": 500,
            "max_results": 50,
            "include_shorts": False,
            "include_comments": True,
            "max_comments_per_video": 20,
            "language": "en",
            "region": "US",
        },
        "analysis": {
            "focus": ["audience_pains", "questions", "hooks", "format_patterns", "content_angles"],
        },
    },
    {
        "id": "crm_automation",
        "label": "CRM и автоматизация",
        "description": "CRM, воронки, клиентские базы, автоматизация продаж, онбординг и удержание клиентов.",
        "sources": ["reddit", "youtube"],
        "reddit": {
            "subreddits": [
                "CRM", "sales", "smallbusiness", "SaaS", "Entrepreneur",
                "marketing", "automation", "CustomerSuccess",
            ],
            "keywords": [
                "CRM", "pipeline", "lead", "customer", "follow up", "onboarding",
                "retention", "churn", "sales process", "automation", "workflow",
                "HubSpot", "Salesforce", "Zoho", "client database", "customer support",
            ],
            "default_run_mode": "hot_last_7d",
            "default_language_mode": "en",
        },
        "youtube": {
            "search_queries": [
                "best CRM for small business",
                "CRM automation tutorial",
                "how to organize client database",
                "sales pipeline management",
                "HubSpot CRM tutorial",
                "Zoho CRM review",
                "Salesforce vs HubSpot",
                "client onboarding automation",
                "customer retention strategy",
                "CRM for consultants",
            ],
            "channels": [],
            "published_period": "last_90d",
            "min_views": 500,
            "max_results": 50,
            "include_shorts": False,
            "include_comments": True,
            "max_comments_per_video": 20,
            "language": "en",
            "region": "US",
        },
        "analysis": {
            "focus": ["audience_pains", "objections", "offer_insights", "content_angles"],
        },
    },
    {
        "id": "wellness_women",
        "label": "Женская ресурсность / wellness",
        "description": "Энергия, стресс, гормоны, сон, ресурсность, забота о себе, здоровье женщин 30–55.",
        "sources": ["reddit", "youtube"],
        "reddit": {
            "subreddits": [
                "AskWomenOver30", "Menopause", "TwoXChromosomes", "xxfitness",
                "nutrition", "Supplements", "Sleep", "Anxiety", "Biohackers",
            ],
            "keywords": [
                "women health", "fatigue", "hormones", "menopause", "perimenopause",
                "stress", "sleep", "energy", "burnout", "self care", "weight gain",
                "anxiety", "brain fog", "cortisol", "magnesium", "vitamin D", "iron", "ferritin",
            ],
            "default_run_mode": "hot_last_7d",
            "default_language_mode": "en",
        },
        "youtube": {
            "search_queries": [
                "women over 40 health tips",
                "perimenopause symptoms explained",
                "how to restore energy women",
                "hormone balance women",
                "stress and cortisol women",
                "sleep tips for women",
                "fatigue and brain fog women",
                "self care for busy women",
                "magnesium for women",
                "vitamin D deficiency women",
            ],
            "channels": [],
            "published_period": "last_90d",
            "min_views": 500,
            "max_results": 50,
            "include_shorts": False,
            "include_comments": True,
            "max_comments_per_video": 20,
            "language": "en",
            "region": "US",
        },
        "analysis": {
            "focus": ["audience_pains", "questions", "objections", "content_angles", "offer_insights"],
        },
    },
    {
        "id": "custom_manual",
        "label": "Ручная настройка",
        "description": "Пользователь сам задаёт настройки под выбранный источник.",
        "sources": ["reddit", "youtube"],
        "reddit": {
            "subreddits": [],
            "keywords": [],
            "default_run_mode": "hot_last_7d",
            "default_language_mode": "en",
        },
        "youtube": {
            "search_queries": [],
            "channels": [],
            "published_period": "last_90d",
            "min_views": 500,
            "max_results": 50,
            "include_shorts": False,
            "include_comments": True,
            "max_comments_per_video": 20,
            "language": "en",
            "region": "US",
        },
        "analysis": {
            "focus": ["audience_pains", "questions", "content_angles"],
        },
    },
]

# Index by id for O(1) lookup
_PACKS_BY_ID = {p["id"]: p for p in PRESET_PACKS}


@router.get("/preset-packs")
async def list_preset_packs(source: str = None):
    """
    List all preset packs. Filter by ?source=reddit or ?source=youtube.
    Returns summary (id, label, description, sources) without full config.
    """
    packs = PRESET_PACKS
    if source:
        packs = [p for p in packs if source in p.get("sources", [])]
    return [_pack_summary(p) for p in packs]


@router.get("/preset-packs/{preset_id}")
async def get_preset_pack(preset_id: str):
    """Return full preset pack config including reddit/youtube/analysis sections."""
    from fastapi import HTTPException
    pack = _PACKS_BY_ID.get(preset_id)
    if not pack:
        raise HTTPException(status_code=404, detail=f"Preset pack '{preset_id}' not found")
    return pack


def _pack_summary(p: dict) -> dict:
    return {
        "id": p["id"],
        "label": p["label"],
        "description": p["description"],
        "sources": p["sources"],
    }


def get_pack_reddit_config(preset_id: str) -> dict:
    """Return Reddit config dict for a preset pack (for use by worker)."""
    pack = _PACKS_BY_ID.get(preset_id, {})
    return pack.get("reddit", {})


def get_pack_youtube_config(preset_id: str) -> dict:
    """Return YouTube config dict for a preset pack (for use by future worker)."""
    pack = _PACKS_BY_ID.get(preset_id, {})
    return pack.get("youtube", {})
