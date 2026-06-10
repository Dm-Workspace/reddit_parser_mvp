from fastapi import APIRouter

router = APIRouter()

SOURCES = {
    "reddit": {
        "id": "reddit",
        "label": "Reddit",
        "status": "active",
        "supports_presets": True,
        "supports_comments": True,
        "supports_schedule": True,
        "description": "Reddit posts and comments via Playwright headless browser",
    },
    "youtube": {
        "id": "youtube",
        "label": "YouTube",
        "status": "coming_soon",
        "supports_presets": False,
        "supports_comments": True,
        "supports_schedule": False,
        "description": "YouTube trending videos and comments (coming soon)",
    },
}


@router.get("/sources")
async def list_sources():
    return list(SOURCES.values())
