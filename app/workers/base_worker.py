"""
Base interface for trend source workers.
All workers must implement run_monitor_sync().
"""
from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseTrendWorker(ABC):
    """
    Abstract base class for trend data workers.
    Extend this to add new sources (YouTube, Google Trends, etc.)
    """

    @abstractmethod
    def run_monitor_sync(self, monitor_id: str) -> Dict[str, Any]:
        """
        Run a monitor synchronously.
        Returns dict with: run_id, status, total_posts, total_comments, message, export_path
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def source_id(self) -> str:
        """Return the source identifier, e.g. 'reddit', 'youtube'"""
        raise NotImplementedError
