"""Shared YouTube OAuth token helper."""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

TOKEN_URL = "https://oauth2.googleapis.com/token"
CHANNELS_URL = (
    "https://www.googleapis.com/youtube/v3/channels"
    "?part=snippet,statistics,contentDetails&mine=true"
)
USER_AGENT = "yt-automation/1.0"


def get_access_token() -> str:
    payload = {
        "client_id": os.environ["YT_CLIENT_ID"],
        "client_secret": os.environ["YT_CLIENT_SECRET"],
        "refresh_token": os.environ["YT_REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    }
    data = urllib.parse.urlencode(payload).encode()
    req = urllib.request.Request(
        TOKEN_URL,
        data=data,
        method="POST",
        headers={"User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())["access_token"]
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:800]
        raise RuntimeError(
            f"YouTube token refresh failed ({exc.code}): {body}. "
            "If this is invalid_grant, the Testing-mode refresh token expired. "
            "Run python src/get_refresh_token.py locally, then update the "
            "YT_REFRESH_TOKEN GitHub secret."
        ) from exc


def fetch_channel(access_token: str) -> dict:
    req = urllib.request.Request(
        CHANNELS_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        items = json.loads(resp.read().decode("utf-8")).get("items") or []
    if not items:
        raise RuntimeError("No YouTube channel found for this login.")
    return items[0]


def require_expected_channel(access_token: str | None = None) -> dict:
    from config import SILENTVISION_CHANNEL_ID, SILENTVISION_CHANNEL_TITLE

    token = access_token or get_access_token()
    channel = fetch_channel(token)
    channel_id = channel.get("id") or ""
    title = (channel.get("snippet") or {}).get("title", "").strip()
    print(f"YouTube login: {title} ({channel_id})")
    if channel_id != SILENTVISION_CHANNEL_ID:
        raise RuntimeError(
            f"Logged into {title or 'unknown'} ({channel_id}), not "
            f"{SILENTVISION_CHANNEL_TITLE} ({SILENTVISION_CHANNEL_ID}). "
            "Run python src/get_refresh_token.py and pick the SilentVision "
            "channel in the Google/YouTube picker, then update the "
            "YT_REFRESH_TOKEN GitHub secret."
        )
    return channel
