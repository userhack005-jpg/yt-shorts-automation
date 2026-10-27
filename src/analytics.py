"""
Pulls channel progress from YouTube Data API + Analytics API
and writes a markdown report plus a JSON snapshot for week-over-week diffs.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from src.youtube_auth import USER_AGENT, get_access_token, require_expected_channel

DATA_API = "https://www.googleapis.com/youtube/v3"
ANALYTICS_API = "https://youtubeanalytics.googleapis.com/v2/reports"
REPORTS_DIR = Path("reports")


def _get(url: str, token: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _analytics(token: str, params: dict) -> dict:
    url = ANALYTICS_API + "?" + urllib.parse.urlencode(params)
    try:
        return _get(url, token)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"YouTube Analytics {exc.code}: {body}") from exc


def _channel(token: str) -> dict:
    url = (
        f"{DATA_API}/channels"
        "?part=snippet,statistics,contentDetails"
        "&mine=true"
    )
    items = _get(url, token).get("items") or []
    if not items:
        raise RuntimeError("No YouTube channel found for this login.")
    return items[0]


def _recent_videos(token: str, uploads_playlist: str, limit: int = 12) -> list:
    if not uploads_playlist:
        return []
    url = (
        f"{DATA_API}/playlistItems"
        f"?part=contentDetails&playlistId={urllib.parse.quote(uploads_playlist)}"
        f"&maxResults={limit}"
    )
    items = _get(url, token).get("items") or []
    ids = [
        item.get("contentDetails", {}).get("videoId")
        for item in items
        if item.get("contentDetails", {}).get("videoId")
    ]
    if not ids:
        return []
    url = (
        f"{DATA_API}/videos"
        f"?part=snippet,statistics,contentDetails&id={','.join(ids)}"
    )
    return _get(url, token).get("items") or []


def _row_map(report: dict) -> list[dict]:
    headers = [h.get("name") for h in report.get("columnHeaders", [])]
    rows = []
    for row in report.get("rows") or []:
        rows.append(dict(zip(headers, row)))
    return rows


def _safe_int(value, default=0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _safe_float(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _iso_duration_seconds(value: str) -> int:
    match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", value or "")
    if not match:
        return 0
    hours, minutes, seconds = (int(part) if part else 0 for part in match.groups())
    return hours * 3600 + minutes * 60 + seconds


def collect_snapshot() -> dict:
    token = get_access_token()
    channel = require_expected_channel(token)
    stats = channel.get("statistics", {})
    snippet = channel.get("snippet", {})
    uploads = (
        channel.get("contentDetails", {})
        .get("relatedPlaylists", {})
        .get("uploads", "")
    )
    videos = _recent_videos(token, uploads)

    today = date.today()
    end = today - timedelta(days=1)
    week_start = end - timedelta(days=6)
    month_start = end - timedelta(days=27)

    analytics_error = None
    week_row = {}
    month_row = {}
    top_rows = []
    try:
        week = _analytics(
            token,
            {
                "ids": "channel==MINE",
                "startDate": week_start.isoformat(),
                "endDate": end.isoformat(),
                "metrics": (
                    "views,estimatedMinutesWatched,subscribersGained,"
                    "subscribersLost,likes,comments,shares,"
                    "averageViewDuration,averageViewPercentage"
                ),
            },
        )
        month = _analytics(
            token,
            {
                "ids": "channel==MINE",
                "startDate": month_start.isoformat(),
                "endDate": end.isoformat(),
                "metrics": "views,estimatedMinutesWatched,subscribersGained,subscribersLost",
            },
        )
        top = _analytics(
            token,
            {
                "ids": "channel==MINE",
                "startDate": week_start.isoformat(),
                "endDate": end.isoformat(),
                "metrics": "views,estimatedMinutesWatched,averageViewPercentage,likes",
                "dimensions": "video",
                "sort": "-views",
                "maxResults": 8,
            },
        )
        week_row = (_row_map(week) or [{}])[0]
        month_row = (_row_map(month) or [{}])[0]
        top_rows = _row_map(top)
    except RuntimeError as exc:
        analytics_error = str(exc)
        print("YouTube Analytics not available yet, using public video stats.")
        print(analytics_error[:300])
    titles = {
        v["id"]: v.get("snippet", {}).get("title", v["id"])
        for v in videos
    }

    # Hydrate any top-video IDs we do not already have titles for
    missing = [r.get("video") for r in top_rows if r.get("video") and r.get("video") not in titles]
    if missing:
        url = f"{DATA_API}/videos?part=snippet&id={','.join(missing)}"
        for item in _get(url, token).get("items") or []:
            titles[item["id"]] = item.get("snippet", {}).get("title", item["id"])

    snapshot = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "period": {
            "week_start": week_start.isoformat(),
            "month_start": month_start.isoformat(),
            "end": end.isoformat(),
        },
        "channel": {
            "id": channel.get("id"),
            "title": snippet.get("title", "My channel"),
            "subscribers": _safe_int(stats.get("subscriberCount")),
            "hidden_subscribers": stats.get("hiddenSubscriberCount", False),
            "total_views": _safe_int(stats.get("viewCount")),
            "video_count": _safe_int(stats.get("videoCount")),
        },
        "last_7_days": {
            "views": _safe_int(week_row.get("views")),
            "watch_minutes": _safe_int(week_row.get("estimatedMinutesWatched")),
            "subs_gained": _safe_int(week_row.get("subscribersGained")),
            "subs_lost": _safe_int(week_row.get("subscribersLost")),
            "likes": _safe_int(week_row.get("likes")),
            "comments": _safe_int(week_row.get("comments")),
            "shares": _safe_int(week_row.get("shares")),
            "avg_view_seconds": _safe_int(week_row.get("averageViewDuration")),
            "avg_view_percent": round(_safe_float(week_row.get("averageViewPercentage")), 1),
        },
        "last_28_days": {
            "views": _safe_int(month_row.get("views")),
            "watch_minutes": _safe_int(month_row.get("estimatedMinutesWatched")),
            "subs_gained": _safe_int(month_row.get("subscribersGained")),
            "subs_lost": _safe_int(month_row.get("subscribersLost")),
        },
        "top_videos": [
            {
                "id": row.get("video"),
                "title": titles.get(row.get("video"), row.get("video")),
                "views": _safe_int(row.get("views")),
                "watch_minutes": _safe_int(row.get("estimatedMinutesWatched")),
                "avg_view_percent": round(_safe_float(row.get("averageViewPercentage")), 1),
                "likes": _safe_int(row.get("likes")),
                "url": f"https://www.youtube.com/watch?v={row.get('video')}",
            }
            for row in top_rows
            if row.get("video")
        ],
        "analytics_error": analytics_error,
        "recent_uploads": [
            {
                "id": item.get("id"),
                "title": item.get("snippet", {}).get("title"),
                "published_at": item.get("snippet", {}).get("publishedAt"),
                "duration_seconds": _iso_duration_seconds(
                    item.get("contentDetails", {}).get("duration", "")
                ),
                "views": _safe_int(item.get("statistics", {}).get("viewCount")),
                "likes": _safe_int(item.get("statistics", {}).get("likeCount")),
                "comments": _safe_int(item.get("statistics", {}).get("commentCount")),
                "url": f"https://www.youtube.com/watch?v={item.get('id')}",
            }
            for item in videos
        ],
    }
    return snapshot


def _delta(current: int, previous: int | None) -> str:
    if previous is None:
        return ""
    change = current - previous
    if change == 0:
        return " (no change)"
    sign = "+" if change > 0 else ""
    return f" ({sign}{change} vs last report)"


def render_markdown(snapshot: dict, previous: dict | None = None) -> str:
    ch = snapshot["channel"]
    week = snapshot["last_7_days"]
    month = snapshot["last_28_days"]
    prev_ch = (previous or {}).get("channel") or {}
    period = snapshot["period"]
    generated = snapshot["generated_at"][:19].replace("T", " ") + " UTC"

    lines = [
        f"# Channel progress: {ch['title']}",
        "",
        f"Generated {generated}. Analytics window ends {period['end']} (YouTube lags about a day).",
        "",
    ]
    if snapshot.get("analytics_error"):
        lines.extend(
            [
                "Watch-time and subscriber-change numbers need the YouTube Analytics API enabled:",
                "https://console.developers.google.com/apis/api/youtubeanalytics.googleapis.com/overview?project=247566853752",
                "",
            ]
        )
    lines.extend(
        [
        "## Lifetime totals",
        "",
        f"- Subscribers: **{ch['subscribers']}**{_delta(ch['subscribers'], prev_ch.get('subscribers'))}",
        f"- Total views: **{ch['total_views']}**{_delta(ch['total_views'], prev_ch.get('total_views'))}",
        f"- Videos: **{ch['video_count']}**{_delta(ch['video_count'], prev_ch.get('video_count'))}",
        "",
        ]
    )
    if not snapshot.get("analytics_error"):
        lines.extend(
            [
                f"## Last 7 days ({period['week_start']} to {period['end']})",
                "",
                f"- Views: **{week['views']}**",
                f"- Watch time: **{week['watch_minutes']} minutes**",
                f"- Subscribers: **+{week['subs_gained']} / -{week['subs_lost']}**",
                f"- Likes: {week['likes']}  |  Comments: {week['comments']}  |  Shares: {week['shares']}",
                f"- Avg view: {week['avg_view_seconds']}s ({week['avg_view_percent']}% of the video)",
                "",
                f"## Last 28 days ({period['month_start']} to {period['end']})",
                "",
                f"- Views: **{month['views']}**",
                f"- Watch time: **{month['watch_minutes']} minutes**",
                f"- Subscribers: **+{month['subs_gained']} / -{month['subs_lost']}**",
                "",
                "## Top videos this week",
                "",
            ]
        )

    if snapshot["top_videos"]:
        lines.append("| Video | Views | Watch min | Avg % | Likes |")
        lines.append("| --- | ---: | ---: | ---: | ---: |")
        for video in snapshot["top_videos"]:
            title = (video["title"] or video["id"]).replace("|", "/")
            lines.append(
                f"| [{title}]({video['url']}) | {video['views']} | "
                f"{video['watch_minutes']} | {video['avg_view_percent']} | {video['likes']} |"
            )
    elif not snapshot.get("analytics_error"):
        lines.append("No video-level analytics yet. New uploads usually show up after a day.")

    lines.extend(["", "## Recent uploads", ""])
    if snapshot["recent_uploads"]:
        lines.append("| Video | Published | Length | Views | Likes | Comments |")
        lines.append("| --- | --- | ---: | ---: | ---: | ---: |")
        for video in snapshot["recent_uploads"]:
            title = (video["title"] or video["id"]).replace("|", "/")
            published = (video.get("published_at") or "")[:10]
            length = video.get("duration_seconds") or 0
            lines.append(
                f"| [{title}]({video['url']}) | {published} | {length}s | "
                f"{video['views']} | {video['likes']} | {video['comments']} |"
            )
    else:
        lines.append("No uploads found on this channel yet.")

    lines.append("")
    return "\n".join(lines)


def write_report(snapshot: dict) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    latest_path = REPORTS_DIR / "latest.json"
    previous = None
    if latest_path.exists():
        try:
            previous = json.loads(latest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            previous = None

    markdown = render_markdown(snapshot, previous)
    day = date.today().isoformat()
    md_path = REPORTS_DIR / f"{day}.md"
    md_path.write_text(markdown, encoding="utf-8")
    (REPORTS_DIR / "latest.md").write_text(markdown, encoding="utf-8")
    latest_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")

    history = REPORTS_DIR / "history.jsonl"
    with history.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(snapshot, separators=(",", ":")) + "\n")

    return md_path


def run_report() -> Path:
    snapshot = collect_snapshot()
    path = write_report(snapshot)
    print(render_markdown(snapshot))
    print(f"Saved report to {path}")
    return path
