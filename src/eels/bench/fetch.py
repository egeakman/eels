"""Download short sections of public tech talks (EN and TR) for benchmarking.

Uses yt-dlp through uvx, so it is not a project dependency. Files go to var/bench-audio/
(git-ignored) as 16 kHz mono WAV.
"""

from __future__ import annotations

import shutil
import subprocess

from ..config import VAR_DIR
from .clips import Clip

AUDIO_DIR = VAR_DIR / "bench-audio"

SOURCES: list[Clip] = [
    Clip("tr_meetup72", "tr", "PgWe6qsfx4I", 480, 780, "Python Istanbul MeetUp 72 (Turkish, room audio)"),
    Clip("tr_meetup66", "tr", "IOKtAMFrkoQ", 720, 1020, "Python Istanbul MeetUp, Python Saati #66 (Turkish)"),
    Clip(
        "en_pizza_music",
        "en",
        "qJraRfZoXjI",
        60,
        360,
        "Python Pizza Hamburg 2021, GPT and music (non-native English)",
    ),
    Clip(
        "en_pycon_shaw",
        "en",
        "Mp5wKOL4L2Q",
        300,
        600,
        "PyCon US 2024, Anthony Shaw, subinterpreters (native English)",
    ),
]


def main(args=None) -> int:
    if not shutil.which("uvx"):
        print("uvx not found (it comes with uv).")
        return 1
    if not shutil.which("ffmpeg"):
        print("ffmpeg is needed to cut and convert audio: brew install ffmpeg")
        return 1
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    ok = 0
    for clip in SOURCES:
        name = clip.name
        out = AUDIO_DIR / f"{name}.wav"
        if out.exists():
            print(f"have {out.name}")
            ok += 1
            continue
        print(f"fetching {name}: {clip.description} [{clip.start}-{clip.end} s]", flush=True)
        cmd = [
            "uvx",
            "yt-dlp",
            f"https://www.youtube.com/watch?v={clip.video}",
            "-f",
            "bestaudio",
            "--download-sections",
            clip.section,
            "-x",
            "--audio-format",
            "wav",
            "--postprocessor-args",
            "ffmpeg:-ac 1 -ar 16000",
            "-o",
            str(AUDIO_DIR / f"{name}.%(ext)s"),
            "--no-playlist",
            "--quiet",
            "--no-warnings",
        ]
        r = subprocess.run(cmd, check=False)
        if r.returncode == 0 and out.exists():
            ok += 1
        else:
            print(f"  failed ({r.returncode})")
    print(f"{ok}/{len(SOURCES)} clips in {AUDIO_DIR}")
    return 0 if ok else 1
