"""Transcript log (one JSONL file per day) and SRT export."""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time
from pathlib import Path
from typing import Literal

from .config import TRANSCRIPT_DIR
from .schedule import TZ


@dataclass
class TranscriptRecord:
    """One subtitle as it went on screen. Same fields whichever engine made it."""

    start: datetime  # when the speech started (timezone-aware)
    end: datetime  # when the subtitle was final
    src: str  # spoken language: "en" | "tr"
    tgt: str  # subtitle language
    source: str  # what was said
    translation: str  # what was shown
    engine: Literal["local", "gemini"]
    speech_model: str  # catalog key (local) or Gemini model id
    translation_model: str
    mode: str  # spoken-language setting at the time: "en" | "tr" | "auto"
    session: str | None  # the talk
    cut: str  # why the sentence ended: sentence, gap, max_words, max_time, language, end, finished
    delay_s: float  # from the end of the speech to the final subtitle
    fallback: bool = False  # the source text was shown because translation failed
    corrections: list[tuple[str, str]] = field(default_factory=list)  # (heard, corrected) names

    def to_json(self) -> dict:
        d = asdict(self)
        d["start"] = self.start.isoformat(timespec="milliseconds")
        d["end"] = self.end.isoformat(timespec="milliseconds")
        return d

    @classmethod
    def from_json(cls, d: dict) -> TranscriptRecord:
        """Also reads lines written by older versions (asr_model/mt_model, no engine)."""
        return cls(
            start=datetime.fromisoformat(d["start"]),
            end=datetime.fromisoformat(d["end"]),
            src=d.get("src", ""),
            tgt=d.get("tgt", ""),
            source=d.get("source", ""),
            translation=d.get("translation", ""),
            engine=d.get("engine", "local"),
            speech_model=d.get("speech_model", d.get("asr_model", "")),
            translation_model=d.get("translation_model", d.get("mt_model", "")),
            mode=d.get("mode", ""),
            session=d.get("session"),
            cut=d.get("cut", ""),
            delay_s=float(d.get("delay_s") or 0.0),
            fallback=bool(d.get("fallback", False)),
            corrections=[tuple(c) for c in d.get("corrections", [])],
        )


class TranscriptLog:
    def __init__(self, directory: Path = TRANSCRIPT_DIR):
        self.dir = directory
        self._lock = threading.Lock()

    def path_for(self, day: date) -> Path:
        return self.dir / f"{day.isoformat()}.jsonl"

    def append(self, record: TranscriptRecord) -> None:
        line = json.dumps(record.to_json(), ensure_ascii=False)
        with self._lock:
            self.dir.mkdir(parents=True, exist_ok=True)
            with self.path_for(record.start.date()).open("a", encoding="utf-8") as f:
                f.write(line + "\n")

    def read(self, day: date) -> list[TranscriptRecord]:
        path = self.path_for(day)
        if not path.exists():
            return []
        out = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                out.append(TranscriptRecord.from_json(json.loads(line)))
            except (json.JSONDecodeError, KeyError, ValueError):
                continue  # a line cut short by a crash
        return out

    def days(self) -> list[str]:
        if not self.dir.exists():
            return []
        return sorted(p.stem for p in self.dir.glob("*.jsonl"))


def _srt_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    ms = round(seconds * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def parse_clock(day: date, hhmm: str) -> datetime:
    parts = [int(p) for p in hhmm.split(":")]
    while len(parts) < 3:
        parts.append(0)
    return datetime.combine(day, time(parts[0], parts[1], parts[2]), tzinfo=TZ)


def export_srt(
    records: list[TranscriptRecord],
    start: datetime,
    end: datetime,
    text: str = "translation",
    offset_s: float = 0.0,
    min_duration_s: float = 1.2,
) -> str:
    """Build an SRT for records between start and end.

    Times are relative to `start` (the recording start), plus offset_s.
    text: "translation", "source" or "both" (translation on top, source below).
    """
    rows = []
    for r in records:
        rs, re_ = r.start, r.end
        if re_ < start or rs > end:
            continue
        if text == "source":
            body = r.source
        elif text == "both":
            body = f"{r.translation}\n{r.source}"
        else:
            body = r.translation
        if not body.strip():
            continue
        a = (rs - start).total_seconds() + offset_s
        b = (re_ - start).total_seconds() + offset_s
        rows.append([a, max(b, a + min_duration_s), body.strip()])
    # Avoid overlaps: each cue ends no later than the next one starts.
    for i in range(len(rows) - 1):
        rows[i][1] = min(rows[i][1], rows[i + 1][0]) if rows[i + 1][0] > rows[i][0] else rows[i][1]
    out = []
    for i, (a, b, body) in enumerate(rows, 1):
        out.append(f"{i}\n{_srt_time(a)} --> {_srt_time(b)}\n{body}\n")
    return "\n".join(out)
