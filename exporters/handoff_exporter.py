"""
AI Handoff Exporter
Creates a structured JSON file for AI agent consumption.
No AI API is called here — pure data preparation.

selected_comments:
- only from top posts (by trend_score)
- top 200 comments
- no bot comments
- min body length 50 chars
"""
import json
import os
from collections import Counter
from typing import List, Dict, Any, Optional
from loguru import logger

from reddit_models import RedditPost, RedditComment
from storage.models import Run, Monitor, Project


# ── Post selection ─────────────────────────────────────────────────────────────

def _top_posts(posts: List[RedditPost], n: int = 30) -> List[dict]:
    sorted_posts = sorted(posts, key=lambda p: p.trend_score, reverse=True)[:n]
    return [
        {
            "post_id":          p.post_id,
            "subreddit":        p.subreddit,
            "title":            p.title,
            "selftext_preview": p.selftext[:600] if p.selftext else "",
            "score":            p.score,
            "num_comments":     p.num_comments,
            "trend_score":      p.trend_score,
            "analysis_priority": p.analysis_priority,
            "pain_signal":      p.pain_signal,
            "content_type":     p.content_type,
            "matched_keywords": p.matched_keywords,
            "permalink":        p.permalink,
            "created_date":     p.created_date,
            "language_detected": p.language_detected,
        }
        for p in sorted_posts
    ]


# ── Comment selection ──────────────────────────────────────────────────────────

def _selected_comments(
    posts: List[RedditPost],
    comments: List[RedditComment],
    n: int = 200,
    min_body_len: int = 50,
) -> List[dict]:
    """
    Select top comments from top posts only.
    Priority: direct keyword match > longer body > higher score.
    """
    top_post_ids = {p.post_id for p in sorted(posts, key=lambda p: p.trend_score, reverse=True)[:50]}

    scored = []
    for c in comments:
        # Only comments from top posts
        if c.post_id not in top_post_ids:
            continue
        # No bots
        if getattr(c, "is_bot_comment", False):
            continue
        # Minimum length
        if len(c.body or "") < min_body_len:
            continue

        priority = 0
        if c.comment_match_type == "direct_keyword_match":
            priority += 4
        elif c.comment_match_type == "context_comment":
            priority += 2
        body_len = len(c.body or "")
        if body_len > 300:
            priority += 3
        elif body_len > 150:
            priority += 1
        score_val = (c.score or 0)
        if score_val > 20:
            priority += 3
        elif score_val > 5:
            priority += 1
        scored.append((priority, c))

    scored.sort(key=lambda x: -x[0])
    selected = [c for _, c in scored[:n]]

    return [
        {
            "comment_id":       c.comment_id,
            "post_id":          c.post_id,
            "post_title":       c.post_title,
            "subreddit":        c.subreddit,
            "author":           c.author,
            "body":             (c.body or "")[:1200],
            "score":            c.score,
            "depth":            c.depth,
            "matched_keywords": c.matched_keywords,
            "comment_match_type": c.comment_match_type,
            "language_detected": c.language_detected,
            "permalink":        c.permalink,
        }
        for c in selected
    ]


# ── Keyword summary ────────────────────────────────────────────────────────────

def _keyword_summary(
    posts: List[RedditPost], comments: List[RedditComment]
) -> List[dict]:
    kw_posts: Counter = Counter()
    kw_comments: Counter = Counter()

    for p in posts:
        for kw in (p.matched_keywords or "").split(", "):
            kw = kw.strip()
            if kw:
                kw_posts[kw] += 1

    for c in comments:
        for kw in (c.matched_keywords or "").split(", "):
            kw = kw.strip()
            if kw:
                kw_comments[kw] += 1

    all_kw = set(kw_posts) | set(kw_comments)
    rows = []
    for kw in sorted(all_kw, key=lambda k: -(kw_posts.get(k, 0) + kw_comments.get(k, 0))):
        rows.append({
            "keyword":        kw,
            "posts_count":    kw_posts.get(kw, 0),
            "comments_count": kw_comments.get(kw, 0),
            "total_mentions": kw_posts.get(kw, 0) + kw_comments.get(kw, 0),
        })
    return rows


# ── AI tasks ───────────────────────────────────────────────────────────────────

_AI_TASKS = [
    "extract_trends",
    "extract_pains",
    "extract_questions",
    "extract_language_patterns",
    "generate_content_angles",
    "prepare_channel_mapping",
]


# ── Main export function ───────────────────────────────────────────────────────

def export_handoff(
    posts: List[RedditPost],
    comments: List[RedditComment],
    run: Run,
    monitor: Monitor,
    project: Project,
    run_settings: Dict[str, Any],
    output_dir: str,
) -> str:
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"{run.id}_handoff.json")

    pain_dist     = dict(Counter(p.pain_signal for p in posts))
    priority_dist = dict(Counter(p.analysis_priority for p in posts))
    lang_dist     = dict(Counter(p.language_detected for p in posts))

    project_dict = {
        "id":                    project.id,
        "name":                  project.name,
        "description":           project.description,
        "language":              project.language,
        "market":                project.market,
        "default_output_language": project.default_output_language,
    }
    monitor_dict = {
        "id":               monitor.id,
        "name":             monitor.name,
        "subreddit_preset": monitor.subreddit_preset,
        "keyword_preset":   monitor.keyword_preset,
        "run_mode":         monitor.run_mode,
        "schedule_cron":    monitor.schedule_cron,
        "timezone":         monitor.timezone,
    }
    run_dict = {
        "id":           run.id,
        "status":       run.status,
        "started_at":   run.started_at,
        "finished_at":  run.finished_at,
        "total_posts":  run.total_posts,
        "total_comments": run.total_comments,
        "quality_status": run.quality_status,
        "warning_message": run.warning_message,
    }

    summary = {
        "total_posts":    len(posts),
        "total_comments": len(comments),
        "subreddits":     run_settings.get("subreddits", ""),
        "keywords":       run_settings.get("keywords", ""),
        "period":         run_settings.get("period", ""),
        "sort":           run_settings.get("sort", ""),
        "run_mode":       run_settings.get("run_mode", ""),
        "pain_signal_distribution":     pain_dist,
        "analysis_priority_distribution": priority_dist,
        "language_distribution":        lang_dist,
        "avg_post_score":      round(sum(p.score for p in posts) / max(len(posts), 1), 1),
        "avg_comments_per_post": round(sum(p.num_comments for p in posts) / max(len(posts), 1), 1),
    }

    top_posts_list     = _top_posts(posts, n=30)
    kw_summary         = _keyword_summary(posts, comments)
    sel_comments       = _selected_comments(posts, comments, n=200)

    payload = {
        "schema_version":      "5.1",
        "project":             project_dict,
        "monitor":             monitor_dict,
        "run":                 run_dict,
        "summary":             summary,
        "top_posts":           top_posts_list,
        "keyword_summary":     kw_summary,
        "selected_comments":   sel_comments,
        "recommended_ai_tasks": _AI_TASKS,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    logger.success(f"Handoff JSON: {output_path}")
    return output_path


def get_top_keywords_for_db(posts: List[RedditPost], n: int = 10) -> str:
    """Return JSON string of top-N keywords for storing in runs.top_keywords_json."""
    kw_counter: Counter = Counter()
    for p in posts:
        for kw in (p.matched_keywords or "").split(", "):
            kw = kw.strip()
            if kw:
                kw_counter[kw] += 1
    top = [{"keyword": k, "total_mentions": v} for k, v in kw_counter.most_common(n)]
    return json.dumps(top, ensure_ascii=False)
