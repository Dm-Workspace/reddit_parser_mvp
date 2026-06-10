"""
Reddit worker — wraps the existing monitor_runner.py logic.
Does NOT rewrite the parser; just delegates to the existing pipeline.
"""
from typing import Dict, Any
from loguru import logger
from app.workers.base_worker import BaseTrendWorker


class RedditWorker(BaseTrendWorker):
    """
    Wraps the existing Reddit Playwright parser.
    Delegates to monitor_runner.run_monitor() which handles:
      - reddit_client (playwright/requests_json/oauth/auto)
      - reddit_parser
      - exporters (xlsx, json, handoff_json)
      - Google Drive upload
      - DB run record management
    """

    @property
    def source_id(self) -> str:
        return "reddit"

    def run_monitor_sync(self, monitor_id: str) -> Dict[str, Any]:
        """
        Run the Reddit monitor pipeline synchronously.
        Returns summary dict.
        """
        try:
            from monitor_runner import run_monitor
            run = run_monitor(monitor_id)
            if run is None:
                return {
                    "run_id": None,
                    "status": "failed",
                    "message": "Monitor runner returned None — check logs",
                    "total_posts": 0,
                    "total_comments": 0,
                }
            return {
                "run_id": run.id,
                "status": run.status,
                "message": run.warning_message or run.error_message or "",
                "total_posts": run.total_posts or 0,
                "total_comments": run.total_comments or 0,
                "export_path": run.export_path or "",
                "quality_status": run.quality_status or "",
            }
        except Exception as e:
            logger.exception(f"RedditWorker.run_monitor_sync failed for {monitor_id}: {e}")
            return {
                "run_id": None,
                "status": "failed",
                "message": str(e)[:300],
                "total_posts": 0,
                "total_comments": 0,
            }
