"""
ConversationHandler state constants.
"""

# ── Create / Edit Project ──────────────────────────────────────────────────────
(
    CP_NAME,
    CP_DESC,
    CP_NICHE,
    CP_LANG,
    CP_CONFIRM,
) = range(5)

# ── Create / Edit Monitor ──────────────────────────────────────────────────────
(
    CM_NAME,
    CM_DESC,
    CM_SUBREDDIT_CHOICE,
    CM_SUBREDDIT_CUSTOM,
    CM_KEYWORD_CHOICE,
    CM_KEYWORD_CUSTOM,
    CM_RUN_MODE,
    CM_SCHEDULE,
    CM_CONFIRM,
) = range(9)

# ── Schedule Monitor ───────────────────────────────────────────────────────────
(
    SCH_CHOOSE_FREQ,
    SCH_WEEKDAY,
    SCH_TIME,
    SCH_CONFIRM,
) = range(4)

# ── Create Preset ──────────────────────────────────────────────────────────────
(
    PSR_NAME,
    PSR_LIST,
    PSR_CONFIRM,
) = range(3)
