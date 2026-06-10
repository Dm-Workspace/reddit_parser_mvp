"""
Registry of available trend data sources.
Add new sources here as they become available.
"""
from typing import Optional, Type, Dict, Any
from app.workers.base_worker import BaseTrendWorker


def _get_reddit_worker_class():
    from app.workers.reddit_worker import RedditWorker
    return RedditWorker


SOURCES: Dict[str, Dict[str, Any]] = {
    "reddit": {
        "id": "reddit",
        "label": "Reddit",
        "status": "active",
        "worker_factory": _get_reddit_worker_class,
        "supports_presets": True,
        "supports_comments": True,
        "supports_schedule": True,
    },
    "youtube": {
        "id": "youtube",
        "label": "YouTube",
        "status": "coming_soon",
        "worker_factory": None,
        "supports_presets": False,
        "supports_comments": True,
        "supports_schedule": False,
    },
    # Future:
    # "google_trends": {...},
    # "x_twitter": {...},
    # "tiktok": {...},
}


def get_worker(source_id: str) -> Optional[BaseTrendWorker]:
    """Get an instantiated worker for the given source_id, or None if not available."""
    source = SOURCES.get(source_id)
    if not source:
        return None
    factory = source.get("worker_factory")
    if not factory:
        return None
    try:
        cls = factory()
        return cls()
    except Exception:
        return None


def list_active_sources():
    return [s for s in SOURCES.values() if s["status"] == "active"]
