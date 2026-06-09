"""
AI Handoff Exporter — pure data preparation, no AI API called.

selected_comments:
- only from top posts (top 50 by trend_score)
- top 200 by quality score
- no bot comments, min body 50 chars
"""
import json
import os
from collections import Counter
from typing import List, Dict, Any, Optional
from loguru import logger

from reddit_models import RedditPost, RedditComment
from storage.models import Run, Monitor, Project


def _top_posts(posts: List[RedditPost], n: int = 30) -> List[dict]:
    return [
        {
            "post_id":           p.post_id,
            "subreddit":         p.subreddit,
            "title":             p.title,
            "selftext_preview":  (p.selftext or "")[:600],
            "score":             p.score,
            "num_comments":      p.num_comments,
            "trend_score":       p.trend_score,
            "analysis_priority": p.analysis_priority,
            "pain_signal":       p.pain_signal,
            "content_type":      p.content_type,
            "matched_keywords":  p.matched_keywords,
            "permalink":         p.permalink,
            "created_date":      p.created_date,
            "language_detected": p.language_detected,
        }
        for p in sorted(posts, key=lambda p: p.trend_score, reverse=True)[:n]
    ]


def _selected_comments(
    posts: List[RedditPost],
    comments: List[RedditComment],
    n: int = 200,
    min_body: int = 50,
) -> List[dict]:
    top_ids = {p.post_id for p in sorted(posts, key=lambda p: p.trend_score, reverse=True)[:50]}
    scored = []
    for c in comments:
        if c.post_id not in top_ids:
            continue
        if getattr(c, "is_bot_comment", False):
            continue
        body_len = len(c.body or "")
        if body_len < min_body:
            continue
        prio = 0
        if c.comment_match_type == "direct_keyword_match":
            prio += 4
        elif c.comment_match_type == "context_comment":
            prio += 2
        if body_len > 300:
            prio += 3
        elif body_len > 150:
            prio += 1
        s = c.score or 0
        if s > 20:
            prio += 3
        elif s > 5:
            prio += 1
        scored.append((prio, c))
    scored.sort(key=lambda x: -x[0])
    return [
        {
            "comment_id":         c.comment_id,
            "post_id":            c.post_id,
            "post_title":         c.post_title,
            "subreddit":          c.subreddit,
            "author":             c.author,
            "body":               (c.body or "")[:1200],
            "score":              c.score,
            "depth":              c.depth,
            "matched_keywords":   c.matched_keywords,
            "comment_match_type": c.comment_match_type,
            "language_detected":  c.language_detected,
            "permalink":          c.permalink,
        }
        for _, c in scored[:n]
    ]


def _keyword_summary(posts: List[RedditPost], comments: List[RedditComment]) -> List[dict]:
    kp: Counter = Counter()
    kc: Counter = Counter()
    for p in posts:
        for kw in (p.matched_keywords or "").split(", "):
            kw = kw.strip()
            if kw:
                kp[kw] += 1
    for c in comments:
        for kw in (c.matched_keywords or "").split(", "):
            kw = kw.strip()
            if kw:
                kc[kw] += 1
    all_kw = set(kp) | set(kc)
    return sorted(
        [{"keyword": kw, "posts_count": kp.get(kw, 0), "comments_count": kc.get(kw, 0),
          "total_mentions": kp.get(kw, 0) + kc.get(kw, 0)}
         for kw in all_kw],
        key=lambda x: -x["total_mentions"],
    )


_AI_TASKS = [
    "extract_trends",
    "extract_pains",
    "extract_questions",
    "extract_language_patterns",
    "generate_content_angles",
    "prepare_channel_mapping",
]


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

    # Resolve custom subreddits/keywords for display
    custom_subs = json.loads(getattr(monitor, "custom_subreddits", "[]") or "[]")
    custom_kws  = json.loads(getattr(monitor, "custom_keywords",   "[]") or "[]")

    payload = {
        "schema_version": "5.3",
        "owner": {
            "telegram_id": str(monitor.owner_telegram_id),
        },
        "project": {
            "id":              project.id,
            "name":            project.name,
            "description":     project.description,
            "niche":           getattr(project, "niche", ""),
            "target_market":   getattr(project, "target_market", ""),
            "output_language": getattr(project, "output_language", "en"),
        },
        "monitor": {
            "id":               monitor.id,
            "name":             monitor.name,
            "description":      monitor.description,
            "source":           monitor.source,
            "subreddit_preset": monitor.subreddit_preset_id or "custom",
            "keyword_preset":   monitor.keyword_preset_id or "custom",
            "custom_subreddits": custom_subs,
            "custom_keywords":   custom_kws,
            "run_mode":          monitor.run_mode,
        },
        "run": {
            "id":              run.id,
            "status":          run.status,
            "started_at":      run.started_at,
            "finished_at":     run.finished_at,
            "total_posts":     run.total_posts,
            "total_comments":  run.total_comments,
            "quality_status":  run.quality_status,
            "warning_message": run.warning_message,
        },
        "summary": {
            "total_posts":    len(posts),
            "total_comments": len(comments),
            "subreddits":     run_settings.get("subreddits", ""),
            "keywords":       run_settings.get("keywords", ""),
            "period":         run_settings.get("period", ""),
            "sort":           run_settings.get("sort", ""),
            "run_mode":       run_settings.get("run_mode", ""),
            "pain_signal_distribution":       pain_dist,
            "analysis_priority_distribution": priority_dist,
            "language_distribution":          lang_dist,
            "avg_post_score":        round(sum(p.score for p in posts) / max(len(posts), 1), 1),
            "avg_comments_per_post": round(sum(p.num_comments for p in posts) / max(len(posts), 1), 1),
        },
        "top_posts":           _top_posts(posts, n=30),
        "keyword_summary":     _keyword_summary(posts, comments),
        "selected_comments":   _selected_comments(posts, comments, n=200),
        "recommended_ai_tasks": _AI_TASKS,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    logger.success(f"Handoff JSON: {output_path}")
    return output_path


def get_top_keywords_for_db(posts: List[RedditPost], n: int = 10) -> str:
    kw: Counter = Counter()
    for p in posts:
        for w in (p.matched_keywords or "").split(", "):
            w = w.strip()
            if w:
                kw[w] += 1
    top = [{"keyword": k, "total_mentions": v} for k, v in kw.most_common(n)]
    return json.dumps(top, ensure_ascii=False)
