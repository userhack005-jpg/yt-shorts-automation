"""Create or update .env from Jarvis + client_secret.json. Never prints secrets."""

from pathlib import Path

from dotenv import dotenv_values, set_key
import json

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
JARVIS_ENV = Path.home() / "jarvis" / ".env"
SECRET_PATH = ROOT / "client_secret.json"


def main():
    ENV_PATH.touch(exist_ok=True)
    current = dotenv_values(ENV_PATH)
    jarvis = dotenv_values(JARVIS_ENV) if JARVIS_ENV.exists() else {}
    secret = json.loads(SECRET_PATH.read_text(encoding="utf-8"))["installed"]

    if jarvis.get("GROQ_API_KEY") and not current.get("GROQ_API_KEY"):
        set_key(ENV_PATH, "GROQ_API_KEY", jarvis["GROQ_API_KEY"])
        print("GROQ_API_KEY: copied from jarvis")
    else:
        print("GROQ_API_KEY:", "SET" if (current.get("GROQ_API_KEY") or jarvis.get("GROQ_API_KEY")) else "MISSING")

    if not current.get("YT_CLIENT_ID"):
        set_key(ENV_PATH, "YT_CLIENT_ID", secret["client_id"])
        print("YT_CLIENT_ID: filled from client_secret.json")
    else:
        print("YT_CLIENT_ID: already set")

    if not current.get("YT_CLIENT_SECRET"):
        set_key(ENV_PATH, "YT_CLIENT_SECRET", secret["client_secret"])
        print("YT_CLIENT_SECRET: filled from client_secret.json")
    else:
        print("YT_CLIENT_SECRET: already set")

    if not current.get("PEXELS_API_KEY"):
        if "PEXELS_API_KEY" not in current:
            set_key(ENV_PATH, "PEXELS_API_KEY", "")
        print("PEXELS_API_KEY: MISSING")
    else:
        print("PEXELS_API_KEY: SET")

    print("YT_REFRESH_TOKEN:", "SET" if current.get("YT_REFRESH_TOKEN") else "MISSING")


if __name__ == "__main__":
    main()
