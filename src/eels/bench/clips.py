"""An excerpt of a public talk used by the benchmarks."""

from __future__ import annotations

from typing import NamedTuple


class Clip(NamedTuple):
    name: str  # file name in the benchmark folder
    lang: str  # spoken language: "en" | "tr"
    video: str  # YouTube id
    start: int  # excerpt, in seconds into the video
    end: int
    description: str

    @property
    def section(self) -> str:
        """yt-dlp --download-sections value."""
        return f"*{self.start}-{self.end}"
