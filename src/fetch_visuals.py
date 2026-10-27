"""
Multi-Source Visual Fetcher:
1. Tries Pexels Video API (if PEXELS_API_KEY is a Pexels key)
2. Tries Pixabay Video API (if PIXABAY_API_KEY is set, or if PEXELS_API_KEY looks like a Pixabay key)
3. Keyless Fallback: Generates custom 9:16 AI visuals via Pollinations.ai (NO API KEY NEEDED)
   and converts them into dynamic zoom-in video clips using FFmpeg.
"""

import os
import json
import random
import subprocess
import urllib.request
import urllib.parse

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) yt-automation/2.0"


def _get_json(url: str, headers: dict) -> dict:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _download(url: str, dest: str, headers: dict | None = None) -> None:
    req = urllib.request.Request(url, headers=headers or {"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp, open(dest, "wb") as out:
        out.write(resp.read())


def _fetch_from_pixabay(keyword: str, api_key: str, dest: str) -> bool:
    """Downloads a vertical/HD video clip from Pixabay API."""
    url = (
        f"https://pixabay.com/api/videos/?key={urllib.parse.quote(api_key)}"
        f"&q={urllib.parse.quote(keyword)}&per_page=10&safesearch=true"
    )
    try:
        data = _get_json(url, {"User-Agent": USER_AGENT})
        hits = data.get("hits") or []
        random.shuffle(hits)
        for hit in hits:
            videos = hit.get("videos") or {}
            # Prefer medium or small HD stream for fast CI download
            for quality in ("medium", "large", "small"):
                v_info = videos.get(quality) or {}
                v_url = v_info.get("url")
                if v_url:
                    _download(v_url, dest)
                    if os.path.exists(dest) and os.path.getsize(dest) > 100_000:
                        return True
    except Exception as e:
        print(f"Pixabay search failed for '{keyword}': {e}")
    return False


def _fetch_from_pexels(keyword: str, api_key: str, dest: str) -> bool:
    """Downloads a vertical video clip from Pexels API."""
    url = (
        f"https://api.pexels.com/videos/search?query={urllib.parse.quote(keyword)}"
        f"&orientation=portrait&per_page=5"
    )
    try:
        data = _get_json(url, {"User-Agent": USER_AGENT, "Authorization": api_key})
        for video in data.get("videos", []):
            files = sorted(video.get("video_files", []), key=lambda f: f.get("width") or 0)
            candidate = next((f for f in files if (f.get("width") or 0) >= 720), None)
            if candidate and candidate.get("link"):
                _download(candidate["link"], dest)
                if os.path.exists(dest) and os.path.getsize(dest) > 100_000:
                    return True
    except Exception as e:
        print(f"Pexels search failed for '{keyword}': {e}")
    return False


def _generate_ai_motion_clip(keyword: str, dest: str, index: int) -> bool:
    """
    100% FREE & KEYLESS FALLBACK:
    Generates a custom 9:16 AI image for the exact keyword using Pollinations.ai
    and turns it into a 5-second cinematic slow-zoom MP4 clip via FFmpeg.
    """
    prompt = f"cinematic photorealistic vertical shot of {keyword}, dramatic lighting, 8k, high detail, no text"
    seed = random.randint(1000, 999999) + index
    img_url = (
        f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt)}"
        f"?width=720&height=1280&seed={seed}&nologo=true"
    )
    img_path = dest.replace(".mp4", ".jpg")
    try:
        print(f"Generating Keyless AI visual for: '{keyword}'...")
        _download(img_url, img_path)
        if not os.path.exists(img_path) or os.path.getsize(img_path) < 10_000:
            return False

        # Convert static AI image into a smooth 5-second zoompan video clip
        vf = (
            "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
            "zoompan=z='min(zoom+0.0015,1.22)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            ":d=150:s=1080x1920:fps=30,format=yuv420p"
        )
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", img_path,
            "-vf", vf,
            "-t", "5",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            dest,
        ]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return os.path.exists(dest) and os.path.getsize(dest) > 50_000
    except Exception as e:
        print(f"AI visual generation failed for '{keyword}': {e}")
        return False


def fetch_clips(keywords: list, out_dir: str, clips_needed: int = 5) -> list:
    """
    Fetches video clips using Pixabay, Pexels, or Keyless AI Generation.
    Never fails even if you have ZERO stock API keys!
    """
    os.makedirs(out_dir, exist_ok=True)
    raw_key = (os.environ.get("PIXABAY_API_KEY") or os.environ.get("PEXELS_API_KEY") or "").strip()

    # Pixabay keys always contain numbers and a hyphen (e.g., "45678912-abcdef...")
    is_pixabay_key = "-" in raw_key and raw_key.split("-")[0].isdigit()

    saved_paths = []
    kw_index = 0

    while len(saved_paths) < clips_needed and kw_index < max(len(keywords) * 3, 10):
        keyword = keywords[kw_index % len(keywords)]
        kw_index += 1
        dest = os.path.join(out_dir, f"clip_{len(saved_paths)}.mp4")

        success = False
        if raw_key:
            if is_pixabay_key:
                success = _fetch_from_pixabay(keyword, raw_key, dest)
            else:
                success = _fetch_from_pexels(keyword, raw_key, dest)

        # If no key is provided OR stock search didn't find a match, use Keyless AI!
        if not success:
            success = _generate_ai_motion_clip(keyword, dest, kw_index)

        if success:
            saved_paths.append(dest)

    return saved_paths