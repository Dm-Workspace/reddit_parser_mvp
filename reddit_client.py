from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page
from loguru import logger


def create_reddit_client() -> dict:
    """Returns a dict with playwright context. Caller must close it."""
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
    )
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        viewport={"width": 1280, "height": 800},
        locale="en-US",
    )
    context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    logger.info("Browser client created (Playwright, no API keys required)")
    return {"playwright": playwright, "browser": browser, "context": context}


def close_reddit_client(client: dict) -> None:
    try:
        client["context"].close()
        client["browser"].close()
        client["playwright"].stop()
    except Exception:
        pass
