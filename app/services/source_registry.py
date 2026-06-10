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
        "description": "Анализ обсуждений, вопросов и комментариев на Reddit.",
        "status": "active",
        "access_mode_env": "REDDIT_ACCESS_MODE",
        "worker_factory": _get_reddit_worker_class,
        "supports_presets": True,
        "supports_comments": True,
        "supports_schedule": True,
        "icon": "🟠",
    },
    "youtube": {
        "id": "youtube",
        "label": "YouTube",
        "description": "Анализ видео, комментариев, форматов и тем на YouTube.",
        "status": "prepared",          # "active" once YouTubeWorker is connected
        "worker_factory": None,         # will be set when YouTubeCore is imported
        "supports_presets": True,
        "supports_comments": True,
        "supports_schedule": False,
        "icon": "🔴",
        "integration_branch": "youtube-core-adapter-for-trend-hub-v1",
        "integration_tag": "youtube-core-v1",
        "integration_api": "run_youtube_monitor(config: YouTubeMonitorConfig) -> YouTubeRunResult",
        "activation_note": "Set YouTubeWorker.worker_factory after importing youtube_core.adapter",
    },
}


def get_worker(source_id: str) -> Optional[BaseTrendWorker]:
    """Get an instantiated worker for the given source_id, or None if not available."""
    source = SOURCES.get(source_id)
    if not source:
        return None
    if source.get("status") != "active":
        return None
    factory = source.get("worker_factory")
    if not factory:
        return None
    try:
        cls = factory()
        return cls()
    except Exception:
        return None


def is_source_active(source_id: str) -> bool:
    return SOURCES.get(source_id, {}).get("status") == "active"


def list_active_sources():
    return [s for s in SOURCES.values() if s["status"] == "active"]


def list_all_sources():
    return list(SOURCES.values())
