import time
from datetime import datetime, timezone
from typing import Optional
from config import PERIOD_TO_SECONDS


def get_cutoff_timestamp(period: str) -> Optional[float]:
    seconds = PERIOD_TO_SECONDS.get(period)
    if seconds is None:
        return None
    return time.time() - seconds


def utc_timestamp_to_date(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def now_utc_str() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def now_file_str() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M")
