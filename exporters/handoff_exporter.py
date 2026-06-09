"""
AI Handoff Exporter
Creates a structured JSON file for future AI agent consumption.
No AI API is called here — this is pure data preparation.
"""
import os
import json
from typing import List, Dict, Any
from loguru import logger

from reddit_models import RedditPost, RedditComment
from storage.models import Run, Monitor, Project


def _top_posts_for_handoff(posts: List[RedditPost], n: int = 30) -> List[dict]:
    sorted_posts = sorted(posts, key=lambda p: p.trend_score, reverse=True)[:n]
    return [
        {
            "post_id": p.post_id,
            "subreddit": p.subreddit,
            "title": p.title,
            "selftext_preview": p.selftext[:500] if p.selftext else "",
            "score": p.score,
            "num_comments": p.num_comments,
            "trend_score": p.trend_score,
            "analysis_priority": p.analysis_priority,
            "pain_signal": p.pain_signal,
            "content_type": p.content_type,
            "matched_keywords": p.matched_keywords,
            "permalink": p.permalink,
            "created_date": p.created_date,
            "language_detected": p.language_detected,
        }
        for p in sorted_posts
    ]


def _selected_comments_for_handoff(
    comments: List[RedditComment], n: int = 100
) -> List[dict]:
    # Prioritise: direct keyword match, longer body, higher score
    scored = []
    for c in comments:
        priority = 0
        if c.comment_match_type == "direct_keyword_match":
            priority += 3
        if c.comment_text_length > 200:
            priority += 2
        if c.comment_text_length > 100:
            priority += 1
        score_val = c.score if c.score is not None else 0
        if score_val > 10:
            priority += 2
        scored.append((priority, c))

    scored.sort(key=lambda x: -x[0])
    selected = [c for _, c in scored[:n]]

    return [
        {
            "comment_id": c.comment_id,
            "post_id": c.post_id,
            "post_title": c.post_title,
            "subreddit": c.subreddit,
            "author": c.author,
            "body": c.body[:1000],
            "score": c.score,
            "depth": c.depth,
            "matched_keywords": c.matched_keywords,
            "comment_match_type": c.comment_match_type,
            "language_detected": c.language_detected,
            "permalink": c.permalink,
        }
        for c in selected
    ]


def _keyword_summary_for_handoff(posts: List[RedditPost], comments: List[RedditComment]) -> List[dict]:
    from collections import Counter, defaultdict
    kw_posts: Counter = Counter()
    kw_comments: Counter = Counter()

    for p in posts:
        for kw in p.matched_keywords.split(", "):
            kw = kw.strip()
            if kw:
                kw_posts[kw] += 1

    for c in comments:
        for kw in c.matched_keywords.split(", "):
            kw = kw.strip()
            if kw:
                kw_comments[kw] += 1

    all_kw = set(kw_posts) | set(kw_comments)
    rows = []
    for kw in sorted(all_kw, key=lambda k: -(kw_posts.get(k, 0) + kw_comments.get(k, 0))):
        rows.append({
            "keyword": kw,
            "posts_count": kw_posts.get(kw, 0),
            "comments_count": kw_comments.get(kw, 0),
            "total_mentions": kw_posts.get(kw, 0) + kw_comments.get(kw, 0),
        })
    return rows


def _recommended_ai_tasks(posts: List[RedditPost], project: Dict) -> List[dict]:
    from collections import Counter
    pain_counts = Counter(p.pain_signal for p in posts)
    top_pains = [s for s, _ in pain_counts.most_common(3)]

    tasks = [
        {
            "task": "sentiment_analysis",
            "description": "Analyse sentiment of post titles and selftext",
            "input": "top_posts[].title + top_posts[].selftext_preview",
            "output_language": project.get("default_output_language", "en"),
        },
        {
            "task": "pain_clustering",
            "description": f"Cluster posts by pain signals. Top signals: {', '.join(top_pains)}",
            "input": "top_posts[].title + top_posts[].pain_signal",
            "output_language": project.get("default_output_language", "en"),
        },
        {
            "task": "content_angles",
            "description": "Extract top 10 content angles and hooks from high-engagement posts",
            "input": "selected_comments[] where comment_match_type=direct_keyword_match",
            "output_language": project.get("default_output_language", "en"),
        },
        {
            "task": "audience_voice",
            "description": "Extract verbatim phrases and language patterns from top comments",
            "input": "selected_comments[] where score > 5",
            "output_language": project.get("default_output_language", "en"),
        },
        {
            "task": "trend_summary",
            "description": f"Write a trend summary for {project.get('market','this market')}",
            "input": "summary + top_posts[:10]",
            "output_language": project.get("default_output_language", "en"),
        },
    ]
    return tasks


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
    output_path = os.path.join(output_dir, "handoff.json")

    from collections import Counter
    pain_dist = dict(Counter(p.pain_signal for p in posts))
    priority_dist = dict(Counter(p.analysis_priority for p in posts))
    lang_dist = dict(Counter(p.language_detected for p in posts))

    project_dict = {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "language": project.language,
        "market": project.market,
        "default_output_language": project.default_output_language,
    }

    monitor_dict = {
        "id": monitor.id,
        "name": monitor.name,
        "subreddit_preset": monitor.subreddit_preset,
        "keyword_preset": monitor.keyword_preset,
        "run_mode": monitor.run_mode,
        "schedule_cron": monitor.schedule_cron,
        "timezone": monitor.timezone,
    }

    run_dict = {
        "id": run.id,
        "status": run.status,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "total_posts": run.total_posts,
        "total_comments": run.total_comments,
    }

    summary = {
        "total_posts": len(posts),
        "total_comments": len(comments),
        "subreddits": run_settings.get("subreddits", ""),
        "keywords": run_settings.get("keywords", ""),
        "period": run_settings.get("period", ""),
        "sort": run_settings.get("sort", ""),
        "run_mode": run_settings.get("run_mode", ""),
        "pain_signal_distribution": pain_dist,
        "analysis_priority_distribution": priority_dist,
        "language_distribution": lang_dist,
        "avg_post_score": round(sum(p.score for p in posts) / len(posts), 1) if posts else 0,
        "avg_comments_per_post": round(sum(p.num_comments for p in posts) / len(posts), 1) if posts else 0,
    }

    payload = {
        "schema_version": "5.0",
        "project": project_dict,
        "monitor": monitor_dict,
        "run": run_dict,
        "summary": summary,
        "top_posts": _top_posts_for_handoff(posts, n=30),
        "keyword_summary": _keyword_summary_for_handoff(posts, comments),
        "selected_comments": _selected_comments_for_handoff(comments, n=100),
        "recommended_ai_tasks": _recommended_ai_tasks(posts, project_dict),
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    logger.success(f"Handoff JSON: {output_path}")
    return output_path
