"""
RUN THIS ONCE, LOCALLY ON YOUR OWN COMPUTER (not in GitHub Actions).

Opens a browser. Pick the SilentVision YouTube channel (not Facelessclipper
or any other brand account), then this writes YT_CLIENT_ID / YT_CLIENT_SECRET
/ YT_REFRESH_TOKEN into the project .env file. It refuses to save if the
login is not SilentVision.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import set_key
from google_auth_oauthlib.flow import InstalledAppFlow

from src.youtube_auth import require_expected_channel

SECRET_FILE = ROOT / "client_secret.json"
ENV_FILE = ROOT / ".env"
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


def main():
    if not SECRET_FILE.exists():
        raise FileNotFoundError(
            f"Missing {SECRET_FILE}. Put your Google Desktop-app "
            "client_secret.json in the project root."
        )

    ENV_FILE.touch(exist_ok=True)

    print("A browser will open. Pick the SilentVision channel.")
    print("Do not pick Facelessclipper or any other brand account.")

    flow = InstalledAppFlow.from_client_secrets_file(str(SECRET_FILE), SCOPES)
    creds = flow.run_local_server(
        port=0,
        access_type="offline",
        prompt="consent",
        open_browser=True,
    )

    if not creds.refresh_token:
        raise RuntimeError(
            "Google did not return a refresh token. Remove old app access "
            "at https://myaccount.google.com/permissions and run this again."
        )

    print("Confirming this login is SilentVision...")
    channel = require_expected_channel(creds.token)
    title = (channel.get("snippet") or {}).get("title", "SilentVision")

    set_key(ENV_FILE, "YT_CLIENT_ID", creds.client_id)
    set_key(ENV_FILE, "YT_CLIENT_SECRET", creds.client_secret)
    set_key(ENV_FILE, "YT_REFRESH_TOKEN", creds.refresh_token)

    print(f"Saved YouTube OAuth values to .env for {title} ({channel.get('id')})")
    print("Do not commit .env or client_secret.json")


if __name__ == "__main__":
    main()
