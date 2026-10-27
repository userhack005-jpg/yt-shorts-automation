"""
Bulletproof Script Generator:
- Dynamically fetches currently active Groq models (Zero 404 Errors)
- Automatic fallback if response_format=json_object gives 400 Bad Request
- Never crashes on slight word-count mismatch (uses closest valid draft + smart trim)
"""

import os
import re
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
GROQ_MODELS_URL = "https://api.groq.com/openai/v1/models"

# Preferred order of models; the script will automatically filter only LIVE ones
PREFERRED_MODELS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "meta-llama/llama-4-maverick-17b-128e-instruct",
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
]

MIN_SCRIPT_WORDS = 85
MAX_SCRIPT_WORDS = 135
TARGET_WORDS = 110
SCRIPT_ATTEMPTS = 6


def _get_live_groq_models(api_key: str) -> list[str]:
    """Queries Groq API for currently active models so we NEVER hit a 404 Not Found."""
    req = urllib.request.Request(
        GROQ_MODELS_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "yt-automation/3.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        available = {m.get("id", "") for m in data.get("data", []) if m.get("id")}
        # Keep preferred models that are live
        live = [m for m in PREFERRED_MODELS if m in available]
        # Add any other chat/instruct models as backup
        for m in sorted(available):
            if m not in live and not any(x in m.lower() for x in ("whisper", "tts", "guard", "embed", "vision")):
                live.append(m)
        if live:
            print(f"Live Groq models detected: {live[:4]}")
            return live
    except Exception as exc:
        print(f"Model list fetch warning ({exc}), using fallback list.")
    return ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]


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
    candidates = [new_key.lower().strip(), new_title.lower().strip()]
    for cand in candidates:
        if not cand:
            continue
        for old in used_list[-120:]:
            if cand == old:
                return True
            ratio = difflib.SequenceMatcher(None, cand, old).ratio()
            if ratio >= 0.65:
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
    words = text.split()
    # If LLM wrote too many words, trim cleanly at sentence boundary before adding CTA
    if len(words) > 122:
        trimmed = " ".join(words[:118])
        last_dot = max(trimmed.rfind("।"), trimmed.rfind("."), trimmed.rfind("!"))
        if last_dot > 60:
            text = trimmed[: last_dot + 1]
        else:
            text = trimmed + "."

    lowered = text.lower()
    if "follow" in lowered or "subscribe" in lowered or "सब्सक्राइब" in lowered:
        return text
    if text and text[-1] not in ".!?।":
        text += "।"
    return f"{text} {END_CTA}".strip()


def _extract_json(raw_text: str) -> dict:
    """Extracts JSON object reliably even if wrapped in markdown or thoughts."""
    text = (raw_text or "").strip()
    # Remove <think>...</think> blocks if present
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]
    return json.loads(text)


def _call_groq(api_key: str, model: str, messages: list, use_json_mode: bool = True) -> dict:
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
    }
    if use_json_mode:
        payload["response_format"] = {"type": "json_object"}

    req = urllib.request.Request(
        GROQ_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "yt-automation/3.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # If 400 Bad Request happens in json_object mode, immediately retry without json_object
        if exc.code == 400 and use_json_mode:
            print(f"Model {model} rejected json_object mode (400), retrying in plain JSON mode...")
            return _call_groq(api_key, model, messages, use_json_mode=False)
        body = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc


def generate_script(topic: dict, length_hint: str = "") -> dict:
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Missing GROQ_API_KEY environment variable.")

    live_models = _get_live_groq_models(api_key)
    used = _load_used_topics()
    recent_avoid = "; ".join(used[-80:]) if used else "none yet"

    system_prompt = (
        "You write viral, high-retention YouTube Shorts scripts in conversational Hindi (Hinglish tone). "
        "CRITICAL LANGUAGE RULES: "
        "1) Write 'script' in Devanagari Hindi script so the Indian TTS voice pronounces it naturally, "
        "using everyday spoken Hinglish words (e.g., साइंटिस्ट्स, ब्रेन, मार्केट, गोल्ड, सिग्नल). "
        "2) Write 'title' in catchy English/Hinglish (under 65 chars, no hashtags). "
        "3) 'keywords' MUST be in English (4 concrete 2-word search terms for stock videos). "
        "4) 'topic_key' MUST be in English lowercase (3-4 words) for duplicate tracking. "
        "Structure strictly: "
        "- HOOK (first 8-12 words): A shocking statement or impossible fact. "
        "- PAYOFF: Explain the real mechanism in fast-paced, simple language. "
        "- TWIST: One mind-blowing final detail. "
        "Write strictly 90-110 words in the script before CTA. "
        "Output ONLY valid JSON: "
        '{"title": "<Catchy Title>", '
        '"script": "<Devanagari conversational script>", '
        '"keywords": ["<keyword 1>", "<keyword 2>", "<keyword 3>", "<keyword 4>"], '
        '"topic_key": "<english lowercase topic key>"}'
    )

    best_candidate = None
    best_distance = 9999
    rejected_in_session = []

    for attempt in range(SCRIPT_ATTEMPTS):
        model = live_models[attempt % len(live_models)]
        avoid_str = recent_avoid
        if rejected_in_session:
            avoid_str += "; ALSO AVOID: " + ", ".join(rejected_in_session)

        user_prompt = (
            f"Write {topic['prompt_hint']}\n"
            f"Target spoken duration: {TARGET_DURATION_SECONDS} seconds ( strictly 90 to 110 words).\n"
            f"Do not reuse these already-covered topics: {avoid_str}\n"
            f"{length_hint}"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            result = _call_groq(api_key, model, messages, use_json_mode=True)
            content = result["choices"][0]["message"]["content"]
            candidate = _extract_json(content)
        except Exception as exc:
            print(f"Attempt {attempt + 1} ({model}) failed: {exc}")
            continue

        t_key = str(candidate.get("topic_key") or "").strip()
        t_title = str(candidate.get("title") or "").strip()
        raw_script = str(candidate.get("script") or "").strip()

        if not t_title or len(raw_script.split()) < 40:
            print(f"Attempt {attempt + 1} ({model}) returned empty or tiny script.")
            continue

        candidate["script"] = _with_cta(raw_script)
        if not candidate.get("keywords"):
            candidate["keywords"] = topic["visual_keywords"]

        words = len(candidate["script"].split())
        distance = abs(words - TARGET_WORDS)
        print(f"Attempt {attempt + 1} ({model}) -> '{t_title}' ({words} words)")

        # Always save the closest valid candidate so we NEVER fail at the end
        if distance < best_distance:
            best_candidate = candidate
            best_distance = distance

        if _is_duplicate_topic(t_key, t_title, used):
            print(f"Topic '{t_key}' is similar to an older post, trying for a fresher one...")
            rejected_in_session.append(t_key or t_title)
            continue

        if MIN_SCRIPT_WORDS <= words <= MAX_SCRIPT_WORDS:
            return candidate
        else:
            length_hint = f"Previous draft was {words} words. Write strictly 95-110 words."

    # Fallback: If all retries had slight word-count or similarity issues, use the best draft!
    if best_candidate is not None:
        print(f"Using best available script draft: '{best_candidate['title']}'")
        return best_candidate

    raise RuntimeError("All Groq API calls failed. Please check your GROQ_API_KEY.")