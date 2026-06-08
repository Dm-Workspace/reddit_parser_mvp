import unicodedata


def detect_language(text: str) -> str:
    """
    Simple heuristic language detection based on character script distribution.
    Returns: 'en', 'ru', 'uk', 'mixed', or 'unknown'.
    """
    if not text or len(text.strip()) < 5:
        return "unknown"

    cyrillic = 0
    latin = 0
    total = 0

    for ch in text:
        cat = unicodedata.category(ch)
        if cat.startswith("L"):
            total += 1
            name = unicodedata.name(ch, "")
            if "CYRILLIC" in name:
                cyrillic += 1
            elif "LATIN" in name:
                latin += 1

    if total == 0:
        return "unknown"

    cyr_ratio = cyrillic / total
    lat_ratio = latin / total

    if cyr_ratio >= 0.8:
        # Try to distinguish ru vs uk by characteristic letters
        uk_chars = set("іїєґ")
        text_lower = text.lower()
        uk_hits = sum(1 for ch in text_lower if ch in uk_chars)
        return "uk" if uk_hits > 2 else "ru"
    elif lat_ratio >= 0.8:
        return "en"
    elif cyr_ratio > 0.1 and lat_ratio > 0.1:
        return "mixed"
    elif lat_ratio > 0:
        return "en"
    elif cyr_ratio > 0:
        return "ru"
    return "unknown"


def passes_language_filter(language_detected: str, language_mode: str) -> bool:
    if language_mode == "mixed":
        return True
    return language_detected == language_mode or language_detected == "unknown"
