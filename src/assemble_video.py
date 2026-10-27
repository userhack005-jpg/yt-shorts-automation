"""
Zero-MoviePy, Direct FFmpeg Video Assembler:
- Fast-paced 3.5s scene cuts with dark cinematic vignette
- Karaoke-style word-by-word yellow highlight (.ass subtitles)
- Auto-generated ambient background audio mixed at 10% volume
- Pre-upload ffprobe Quality Gate verification
"""

import json
import subprocess
from pathlib import Path
from config import VIDEO_WIDTH, VIDEO_HEIGHT


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg command failed:\n{' '.join(cmd)}\nError:\n{proc.stderr[-800:]}")


def _ probe_duration(media_path: str) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(media_path),
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
    return float(proc.stdout.strip())


def _fmt_ass_time(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    if cs >= 100:
        cs = 99
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _write_ass_subtitles(word_timings: list, title: str, ass_path: Path) -> None:
    """Builds an ASS subtitle file with active word highlighting in Yellow (#FFD700)."""
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {VIDEO_WIDTH}
PlayResY: {VIDEO_HEIGHT}
WrapStyle: 1

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,DejaVu Sans,78,&H00FFFFFF,&H0000D7FF,&H00000000,&H80000000,-1,0,0,0,100,100,1,0,1,5,2,5,70,70,0,1
Style: TitleBanner,DejaVu Sans,64,&H0000D7FF,&H00FFFFFF,&H00000000,&HAA000000,-1,0,0,0,100,100,1,0,3,4,0,8,80,80,220,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]

    # Top Title Hook for first 2.8 seconds
    clean_title = (title or "").replace("{", "").replace("}", "").strip()
    if clean_title:
        lines.append(f"Dialogue: 2,0:00:00.00,0:00:02.80,TitleBanner,,0,0,0,,{clean_title}")

    # Group into 3 words per screen, highlight the currently spoken word in Gold/Yellow
    group_size = 3
    for i in range(0, len(word_timings), group_size):
        group = word_timings[i : i + group_size]
        if not group:
            continue

        for active_idx, active_word in enumerate(group):
            w_start = active_word["start"]
            if active_idx + 1 < len(group):
                w_end = group[active_idx + 1]["start"]
            else:
                w_end = active_word["start"] + max(active_word["duration"], 0.18)

            if w_end <= w_start:
                w_end = w_start + 0.15

            parts = []
            for idx, w in enumerate(group):
                safe_w = w["word"].replace("{", "").replace("}", "").upper()
                if idx == active_idx:
                    # Active word: Gold/Yellow (#FFD700 -> BGR &H00D7FF&) + slight scale pop
                    parts.append(r"{\c&H00D7FF&\fscx110\fscy110}" + safe_w + r"{\c&HFFFFFF&\fscx100\fscy100}")
                else:
                    parts.append(safe_w)

            text_line = " ".join(parts)
            lines.append(
                f"Dialogue: 1,{_fmt_ass_time(w_start)},{_fmt_ass_time(w_end)},Default,,0,0,0,,{text_line}"
            )

    ass_path.write_text("\n".join(lines), encoding="utf-8")


def verify_final_video(video_path: str, expected_duration: float) -> None:
    """Quality Gate: Ensures the rendered video is not corrupted, silent, or blank."""
    p = Path(video_path)
    if not p.exists() or p.stat().st_size < 1_500_000:
        raise RuntimeError(f"Quality Gate Failed: Video file missing or too small ({p.stat().st_size if p.exists() else 0} bytes)")

    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "stream=codec_type",
        "-show_entries", "format=duration",
        "-of", "json",
        str(p),
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
    info = json.loads(proc.stdout)
    streams = [s.get("codec_type") for s in info.get("streams", [])]
    dur = float(info.get("format", {}).get("duration", 0))

    if "video" not in streams or "audio" not in streams:
        raise RuntimeError(f"Quality Gate Failed: Missing video or audio stream ({streams})")
    if abs(dur - expected_duration) > 3.0 or dur < 35.0 or dur > 59.0:
        raise RuntimeError(f"Quality Gate Failed: Invalid final duration ({dur:.1f}s)")
    print(f"Quality Gate Passed: {dur:.1f}s, {p.stat().st_size / (1024*1024):.1f} MB, Video+Audio verified.")


def assemble_video(
    clip_paths: list,
    audio_path: str,
    word_timings: list,
    out_path: str,
    title: str = "",
):
    workdir = Path(out_path).resolve().parent
    duration = _probe_duration(audio_path)
    print(f"Direct FFmpeg Assembly: target {duration:.1f}s")

    # Step 1: Normalize each stock clip into 3.5-second vertical 1080x1920 segments
    seg_dir = workdir / "norm_segs"
    seg_dir.mkdir(parents=True, exist_ok=True)
    seg_duration = 3.5
    norm_paths = []

    for idx, cpath in enumerate(clip_paths):
        out_seg = seg_dir / f"seg_{idx:02d}.mp4"
        vf = (
            f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={VIDEO_WIDTH}:{VIDEO_HEIGHT},"
            f"eq=brightness=-0.06:contrast=1.08:saturation=1.12,"
            f"fps=30,format=yuv420p"
        )
        _run([
            "ffmpeg", "-y", "-ss", "0", "-t", str(seg_duration),
            "-i", str(cpath),
            "-an", "-vf", vf,
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            str(out_seg),
        ])
        norm_paths.append(out_seg)

    # Step 2: Create concat list to cover full audio duration
    concat_file = workdir / "concat.txt"
    concat_lines = []
    total_t = 0.0
    i = 0
    while total_t < duration + 1.0:
        seg = norm_paths[i % len(norm_paths)]
        concat_lines.append(f"file '{seg.as_posix()}'")
        total_t += seg_duration
        i += 1
    concat_file.write_text("\n".join(concat_lines), encoding="utf-8")

    # Step 3: Write ASS karaoke subtitles
    ass_path = workdir / "captions.ass"
    _write_ass_subtitles(word_timings, title, ass_path)

    # Step 4: Final Render (Burn Subtitles + Mix Voiceover with Generated Ambient BGM)
    # Using relative path inside workdir so Windows/Linux FFmpeg subtitle filter never chokes on colons
    filter_complex = (
        f"[0:v]trim=0:{duration:.2f},setpts=PTS-STARTPTS,ass=captions.ass[v];"
        f"anoisesrc=color=brown:amplitude=0.035:duration={duration:.2f},"
        f"lowpass=f=240,aecho=0.8:0.88:60:0.4[bgm];"
        f"[1:a]volume=1.05[vo];"
        f"[vo][bgm]amix=inputs=2:duration=first:dropout_transition=2[a]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_file.name),
        "-i", str(Path(audio_path).resolve()),
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "[a]",
        "-t", f"{duration:.2f}",
        "-c:v", "libx264", "-preset", "faster", "-crf", "21",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(Path(out_path).resolve()),
    ]
    subprocess.run(cmd, cwd=str(workdir), check=True)

    # Step 5: Run strict pre-upload verification
    verify_final_video(out_path, duration)
    return out_path