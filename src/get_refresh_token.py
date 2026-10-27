"""
Upgraded Token Generator:
- Run `python src/get_refresh_token.py` for primary channel (Channel 1)
- Run `python src/get_refresh_token.py trading` for 2nd channel (does NOT overwrite Channel 1)
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import set_key
from google_auth_oauthlib.flow import InstalledAppFlow
from src.youtube_auth import fetch_channel, require_expected_channel

SECRET_FILE = ROOT / "client_secret.json"
ENV_FILE = ROOT / ".env"
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


def main():
    if not SECRET_FILE.exists():
        raise FileNotFoundError(f"Missing {SECRET_FILE} in project root.")

    ENV_FILE.touch(exist_ok=True)
    mode = sys.argv[1].strip().lower() if len(sys.argv) > 1 else "default"

    print(f"Opening browser for mode: [{mode.upper()}]...")
    print("Please select your target YouTube channel in the Google login popup.")

    flow = InstalledAppFlow.from_client_secrets_file(str(SECRET_FILE), SCOPES)
    creds = flow.run_local_server(
        port=0,
        access_type="offline",
        prompt="consent",
        open_browser=True,
    )

    if not creds.refresh_token:
        raise RuntimeError("Google did not return a refresh token. Try again and click Allow.")

    if mode == "trading":
        # Fetch 2nd channel info automatically without blocking
        channel = fetch_channel(creds.token)
        ch_id = channel.get("id") or ""
        ch_title = (channel.get("snippet") or {}).get("title", "TradingChannel").strip()

        set_key(ENV_FILE, "YT_CHANNEL_ID_TRADING", ch_id)
        set_key(ENV_FILE, "YT_CHANNEL_TITLE_TRADING", ch_title)
        set_key(ENV_FILE, "YT_REFRESH_TOKEN_TRADING", creds.refresh_token)

        print("\n==========================================")
        print("SUCCESS! 2nd Channel (Trading) Saved to .env (Channel 1 untouched!)")
        print(f"Channel Title : {ch_title}")
        print(f"YT_CHANNEL_ID_TRADING    : {ch_id}")
        print(f"YT_REFRESH_TOKEN_TRADING : {creds.refresh_token}")
        print("==========================================\n")
    else:
        channel = require_expected_channel(creds.token)
        title = (channel.get("snippet") or {}).get("title", "PrimaryChannel")
        set_key(ENV_FILE, "YT_CLIENT_ID", creds.client_id)
        set_key(ENV_FILE, "YT_CLIENT_SECRET", creds.client_secret)
        set_key(ENV_FILE, "YT_REFRESH_TOKEN", creds.refresh_token)
        print(f"Saved Primary Channel OAuth to .env for {title} ({channel.get('id')})")


if __name__ == "__main__":
    main()