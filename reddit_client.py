import requests
from loguru import logger

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; reddit_parser_mvp/1.0)",
    "Accept": "application/json",
}

SESSION = None


def create_reddit_client() -> requests.Session:
    global SESSION
    session = requests.Session()
    session.headers.update(HEADERS)
    logger.info("Reddit HTTP client created (no API keys required)")
    SESSION = session
    return session
