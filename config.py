"""
Multi-Channel Central Config (Channel 1: Facts/Mystery | Channel 2: Trading & Forex)
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

CHANNEL_MODE = os.environ.get("CHANNEL_MODE", "facts").strip().lower()

if CHANNEL_MODE == "trading":
    # ---- दूसरा चैनल (TRADING CHANNEL) ----
    SILENTVISION_CHANNEL_ID = os.environ.get("YT_CHANNEL_ID_TRADING", "").strip()
    SILENTVISION_CHANNEL_TITLE = os.environ.get("YT_CHANNEL_TITLE_TRADING", "Trading Channel").strip()
    END_CTA = "ऐसे ही स्मार्ट ट्रेडिंग और मार्केट सीक्रेट्स के लिए चैनल को सब्सक्राइब ज़रूर करें।"

    TOPICS = [
        {
            "niche": "gold_and_forex_secrets",
            "prompt_hint": (
                "one shocking, verifiable fact about Gold (XAUUSD), Silver, central bank gold reserves, "
                "or how currency markets and institutional liquidity hunts work behind the scenes."
            ),
            "visual_keywords": [
                "gold bars vault",
                "candlestick chart screen",
                "forex trading desk",
                "us dollar bills",
                "stock market graph",
            ],
            "hashtags": "#trading #forex #goldtrading #xauusd #tradingfacts #shorts",
        },
        {
            "niche": "trading_psychology_secrets",
            "prompt_hint": (
                "one powerful psychological truth about why 90% of retail traders lose money, "
                "such as stop-loss hunting, FOMO traps, smart money concepts, or risk-reward math."
            ),
            "visual_keywords": [
                "trader computer screen",
                "stock chart red",
                "chess strategy board",
                "financial graph monitor",
                "trading setup night",
            ],
            "hashtags": "#tradingpsychology #priceaction #daytrading #smartmoney #shorts",
        },
        {
            "niche": "market_crashes_and_whales",
            "prompt_hint": (
                "one thrilling true story of a historic market crash, a legendary whale trade, "
                "a flash crash, or a bizarre financial market anomaly."
            ),
            "visual_keywords": [
                "wall street building",
                "financial crash chart",
                "stock exchange board",
                "digital numbers screen",
                "money bank vault",
            ],
            "hashtags": "#stockmarket #forextrader #marketcrash #financefacts #shorts",
        },
    ]

else:
    # ---- पहला चैनल (आपका मौजूदा चैनल - यहाँ अपनी पहली चैनल ID और नाम रखें) ----
    SILENTVISION_CHANNEL_ID = "UCsVwhTvFvaHzIC3aZ850fzw"
    SILENTVISION_CHANNEL_TITLE = "BTYS"
    END_CTA = "ऐसे ही रहस्यमयी फैक्ट्स के लिए चैनल को सब्सक्राइब ज़रूर करें।"

    TOPICS = [
        {
            "niche": "rare_animals",
            "prompt_hint": (
                "one surprising, verifiable fact about a rare, weird, or extreme animal "
                "with a shocking survival trick. Make it feel like a dark nature documentary secret."
            ),
            "visual_keywords": [
                "wildlife closeup",
                "jungle animal",
                "deep ocean creature",
                "rainforest nature",
                "predator animal",
            ],
            "hashtags": "#factsinhindi #amazingfacts #wildlife #science #shorts",
        },
        {
            "niche": "human_body",
            "prompt_hint": (
                "one surprising, verifiable fact about the human body, psychology, or brain "
                "that people experience daily but never understood."
            ),
            "visual_keywords": [
                "human eye closeup",
                "brain scan neurons",
                "heartbeat monitor",
                "dna helix",
                "medical science",
            ],
            "hashtags": "#hindifacts #humanbody #psychologyfacts #science #shorts",
        },
        {
            "niche": "space_wow",
            "prompt_hint": (
                "one surprising, verifiable space fact with a concrete image: a planet, black hole, "
                "star, moon, or cosmic anomaly."
            ),
            "visual_keywords": [
                "outer space stars",
                "earth from space",
                "astronaut space",
                "galaxy nebula",
                "planet surface",
            ],
            "hashtags": "#spacefacts #universe #antriksh #sciencehindi #shorts",
        },
    ]


VIDEOS_PER_DAY = 3

POST_WINDOWS = (
    {"name": "morning", "utc_hour": 6},
    {"name": "afternoon", "utc_hour": 12},
    {"name": "night", "utc_hour": 16},
)
SLOT_NAMES = {window["name"]: index for index, window in enumerate(POST_WINDOWS)}


def slot_for_now(name: str | None = None) -> int:
    if name:
        key = name.strip().lower()
        if key.isdigit():
            return max(0, min(VIDEOS_PER_DAY - 1, int(key)))
        if key in SLOT_NAMES:
            return SLOT_NAMES[key]

    from datetime import datetime, timezone

    hour = datetime.now(timezone.utc).hour
    if hour < 11:
        return 0
    if hour < 15:
        return 1
    return 2


def pick_topic_for_slot(slot: int = 0):
    import datetime

    day_index = datetime.date.today().timetuple().tm_yday
    return TOPICS[(day_index + int(slot)) % len(TOPICS)]


def pick_topic_for_today():
    return pick_topic_for_slot(slot_for_now())


# ---- Video & Audio Settings ----
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
TARGET_DURATION_SECONDS = 45
MIN_DURATION_SECONDS = 35
MAX_DURATION_SECONDS = 58
FONT_SIZE = 70
CAPTION_COLOR = "white"
CAPTION_HIGHLIGHT_COLOR = "#FFD700"

TTS_VOICE = "hi-IN-MadhurNeural"
WORKDIR = "workdir"