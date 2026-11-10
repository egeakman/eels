"""Download short sections of public tech talks (EN and TR) for benchmarking.

Uses yt-dlp through uvx, so it is not a project dependency. Files go to var/bench-audio/
(git-ignored) as 16 kHz mono WAV.
"""

from __future__ import annotations

import shutil
import subprocess

from ..config import VAR_DIR

AUDIO_DIR = VAR_DIR / "bench-audio"

# (name, language, YouTube id, section start, section end, description)
SOURCES = [
    ("tr_meetup72", "tr", "PgWe6qsfx4I", "08:00", "13:00", "Python Istanbul MeetUp 72 (Turkish, room audio)"),
    ("tr_meetup66", "tr", "IOKtAMFrkoQ", "12:00", "17:00", "Python Istanbul MeetUp, Python Saati #66 (Turkish)"),
    (
        "en_pizza_music",
        "en",
        "qJraRfZoXjI",
        "01:00",
        "06:00",
        "Python Pizza Hamburg 2021, GPT and music (non-native English)",
    ),
    (
        "en_pycon_shaw",
        "en",
        "Mp5wKOL4L2Q",
        "05:00",
        "10:00",
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
    for name, lang, vid, start, end, desc in SOURCES:
        out = AUDIO_DIR / f"{name}.wav"
        if out.exists():
            print(f"have {out.name}")
            ok += 1
            continue
        print(f"fetching {name}: {desc} [{start}-{end}]", flush=True)
        cmd = [
            "uvx",
            "yt-dlp",
            f"https://www.youtube.com/watch?v={vid}",
            "-f",
            "bestaudio",
            "--download-sections",
            f"*{start}-{end}",
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
