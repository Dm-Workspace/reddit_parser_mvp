import os
from dotenv import load_dotenv

load_dotenv()

REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "reddit_parser_mvp/1.0")

EXPORTS_DIR = os.path.join(os.path.dirname(__file__), "exports")

SUPPORTED_PERIODS = ["last_24h", "last_7d", "last_30d", "all"]
SUPPORTED_SORTS = ["hot", "new", "top", "rising", "controversial"]
SUPPORTED_EXPORTS = ["xlsx", "csv", "json"]

PERIOD_TO_SECONDS = {
    "last_24h": 86400,
    "last_7d": 604800,
    "last_30d": 2592000,
    "all": None,
}
