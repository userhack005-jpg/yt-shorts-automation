"""
Upgraded Script Generator with Fuzzy Topic Deduplication & Strict Length Control.
"""

import os
import json
import difflib
import urllib.error
import urllib.request
from pathlib import Path

from config import END_CTA, TARGET_DURATION_SECONDS

CHANNEL_MODE = os.environ.get("CHANNEL_MODE", "facts").strip().lower()
USED_TOPICS_PATH = (
    Path(__file__).resolve().parent.parent
    / "reports"
    / ("used_topics_trading.json" if CHANNEL_MODE == "trading" else "used_topics.json")
)
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

GROQ_MODELS = (
    "llama-3.3-70b-versatile",
    "openai/gpt-oss-120b",
    "qwen/qwen3.6-27b",
)

MIN_SCRIPT_WORDS = 95
MAX_SCRIPT_WORDS = 120
SCRIPT_ATTEMPTS = 6


def _load_used_topics() -> list[str]:
    if USED_TOPICS_PATH.exists():
        try:
            data = json.loads(USED_TOPICS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [str(x).strip().lower() for x in data if x]
        except Exception:
            pass
    return []


def _is_duplicate_topic(new_key: str, new_title: str, used_list: list[str]) -> bool:
    """Checks if the generated topic or title is too similar to any previously posted topic."""
    candidates = [new_key.lower().strip(), new_title.lower().strip()]
    for cand in candidates:
        if not cand:
            continue
        for old in used_list:
            if cand == old or cand in old or old in cand:
                return True
            ratio = difflib.SequenceMatcher(None, cand, old).ratio()
            if ratio >= 0.58:  # 58% similarity threshold blocks repetitive topics
                return True
    return False


def record_used_topic(topic_key: str) -> None:
    key = (topic_key or "").strip().lower()
    if not key:
        return
    used = _load_used_topics()
    if key not in used:
        used.append(key)
        USED_TOPICS_PATH.parent.mkdir(parents=True, exist_ok=True)
        USED_TOPICS_PATH.write_text(json.dumps(used, indent=2), encoding="utf-8")


def _with_cta(script: str) -> str:
    text = (script or "").strip()
    lowered = text.lower()
    if "follow" in lowered or "subscribe" in lowered:
        return text
    if text and text[-1] not in ".!?":
        text += "."
    return f"{text} {END_CTA}".strip()


def generate_script(topic: dict, length_hint: str = "") -> dict:
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Missing GROQ_API_KEY environment variable.")

    used = _load_used_topics()
    # FIXED BUG: Always take the latest 120 topics from the end, not used[:40]
    recent_avoid = "; ".join(used[-120:]) if used else "none yet"

    system_prompt = (
        "You write high-retention YouTube Shorts scripts. "
        "Structure strictly: "
        "1) HOOK (first 8-12 words): A shocking contradiction or impossible-sounding scientific fact. "
        "Never start with 'Did you know', 'Imagine', or 'What if'. "
        "2) PAYOFF: Explain the real mechanism clearly in simple, vivid words. "
        "3) TWIST: One deeper, mind-blowing detail. "
        "Write 110-130 spoken words before the CTA. No emojis, no stage directions. "
        "Output ONLY valid JSON matching this schema: "
        '{"title": "<under 65 chars, catchy, no hashtags>", '
        '"script": "<spoken narration>", '
        '"keywords": ["<4 concrete 2-word visual search terms for Pexels>"], '
        '"topic_key": "<3-4 word lowercase identifier of the exact subject>"}'
    )

    rejected_in_session = []

    for attempt in range(SCRIPT_ATTEMPTS):
        model = GROQ_MODELS[attempt % len(GROQ_MODELS)]
        avoid_str = recent_avoid
        if rejected_in_session:
            avoid_str += "; ALSO DO NOT USE: " + ", ".join(rejected_in_session)

        user_prompt = (
            f"Write {topic['prompt_hint']}\n"
            f"Target spoken duration: {TARGET_DURATION_SECONDS} seconds ({MIN_SCRIPT_WORDS}-{MAX_SCRIPT_WORDS} words).\n"
            f"STRICTLY AVOID these already-covered subjects: {avoid_str}\n"
            f"{length_hint}"
        )

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.75,
            "response_format": {"type": "json_object"},
        }

        req = urllib.request.Request(
            GROQ_API_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "yt-automation/2.0",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            content = (result["choices"][0]["message"]["content"] or "").strip()
            candidate = json.loads(content)
        except Exception as exc:
            print(f"Attempt {attempt + 1} ({model}) failed: {exc}")
            continue

        t_key = str(candidate.get("topic_key") or "").strip()
        t_title = str(candidate.get("title") or "").strip()

        if _is_duplicate_topic(t_key, t_title, used):
            print(f"Rejected duplicate topic: '{t_key}' / '{t_title}'. Retrying...")
            rejected_in_session.append(t_key or t_title)
            continue

        candidate["script"] = _with_cta(candidate.get("script") or "")
        words = len(candidate["script"].split())

        if MIN_SCRIPT_WORDS <= words <= MAX_SCRIPT_WORDS and t_title:
            if not candidate.get("keywords"):
                candidate["keywords"] = topic["visual_keywords"]
            return candidate
        else:
            length_hint = f"Previous draft had {words} words. Adjust strictly to {MIN_SCRIPT_WORDS}-{MAX_SCRIPT_WORDS} words."

    raise RuntimeError("Failed to generate a unique, valid-length script after all retries.")