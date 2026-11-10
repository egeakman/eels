"""Transcript log (one JSONL file per day) and SRT export."""

from __future__ import annotations

import json
import threading
from datetime import date, datetime, time
from pathlib import Path

from .config import TRANSCRIPT_DIR
from .schedule import TZ


class TranscriptLog:
    def __init__(self, directory: Path = TRANSCRIPT_DIR):
        self.dir = directory
        self._lock = threading.Lock()

    def path_for(self, day: date) -> Path:
        return self.dir / f"{day.isoformat()}.jsonl"

    def append(self, record: dict) -> None:
        """record must contain 'start' and 'end' as timezone-aware datetimes."""
        start: datetime = record["start"]
        rec = dict(record)
        rec["start"] = start.isoformat(timespec="milliseconds")
        rec["end"] = record["end"].isoformat(timespec="milliseconds")
        line = json.dumps(rec, ensure_ascii=False)
        with self._lock:
            self.dir.mkdir(parents=True, exist_ok=True)
            with self.path_for(start.date()).open("a", encoding="utf-8") as f:
                f.write(line + "\n")

    def read(self, day: date) -> list[dict]:
        path = self.path_for(day)
        if not path.exists():
            return []
        out = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
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
    records: list[dict],
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
        rs = datetime.fromisoformat(r["start"])
        re_ = datetime.fromisoformat(r["end"])
        if re_ < start or rs > end:
            continue
        if text == "source":
            body = r.get("source", "")
        elif text == "both":
            body = f"{r.get('translation', '')}\n{r.get('source', '')}"
        else:
            body = r.get("translation", "")
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
