"""Event schedule: parse the compact agenda page and find the session running now."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import DATA_DIR, TIMEZONE, VAR_DIR

AGENDA_URL = "https://istanbul.python.pizza/compact-agenda/"
BUNDLED = DATA_DIR / "schedule.json"
OVERRIDE = VAR_DIR / "schedule.json"  # written by `update-schedule`, preferred when present
TZ = ZoneInfo(TIMEZONE)


@dataclass
class Session:
    start: str  # ISO 8601 with offset
    end: str | None
    title: str
    speaker: str | None
    lang: str | None  # "en", "tr" or None (untagged: auto-detect)

    @property
    def start_dt(self) -> datetime:
        return datetime.fromisoformat(self.start)

    @property
    def end_dt(self) -> datetime | None:
        return datetime.fromisoformat(self.end) if self.end else None

    @property
    def spoken(self) -> str:
        return self.lang or "auto"


class _AgendaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.items: list[dict] = []
        self._cur: dict | None = None
        self._field: str | None = None
        self._spans: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = (a.get("class") or "").split()
        if tag == "li" and "agenda-item" in cls:
            self._cur = {"when": a.get("data-when"), "until": a.get("data-until"), "lang": None, "content": []}
        elif self._cur is not None and tag == "span":
            if "lang" in cls:
                self._field = "lang"
            elif "time" in cls or "badge" in cls:
                self._field = "skip"
            else:
                self._field = "content"
                self._cur["content"].append("")

    def handle_endtag(self, tag):
        if tag == "span":
            self._field = None
        elif tag == "li" and self._cur is not None:
            self.items.append(self._cur)
            self._cur = None

    def handle_data(self, data):
        if self._cur is None or self._field in (None, "skip"):
            return
        if self._field == "lang":
            self._cur["lang"] = (self._cur["lang"] or "") + data.strip()
        else:
            self._cur["content"][-1] += data


def parse_agenda(html: str) -> list[Session]:
    p = _AgendaParser()
    p.feed(html)
    sessions = []
    for it in p.items:
        content = [c.strip() for c in it["content"] if c.strip()]
        title = content[-1] if content else ""
        speaker = content[0] if len(content) > 1 else None
        lang = (it["lang"] or "").strip().lower() or None
        if lang not in ("en", "tr"):
            lang = None
        if not it["when"]:
            continue
        sessions.append(Session(it["when"], it["until"], title, speaker, lang))
    sessions.sort(key=lambda s: s.start_dt)
    return sessions


def fetch_agenda(url: str = AGENDA_URL) -> list[Session]:
    import httpx

    r = httpx.get(url, timeout=15, follow_redirects=True)
    r.raise_for_status()
    sessions = parse_agenda(r.text)
    if not sessions:
        raise RuntimeError("no sessions found on the agenda page (layout changed?)")
    return sessions


def save(sessions: list[Session], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([asdict(s) for s in sessions], indent=2, ensure_ascii=False))


def load() -> list[Session]:
    for path in (OVERRIDE, BUNDLED):
        if path.exists():
            try:
                return [Session(**d) for d in json.loads(path.read_text())]
            except Exception:
                continue
    return []


def current_and_next(sessions: list[Session], now: datetime | None = None) -> tuple[Session | None, Session | None]:
    now = now or datetime.now(TZ)
    cur = nxt = None
    for s in sessions:
        if s.start_dt <= now and (s.end_dt is None or now < s.end_dt):
            cur = s
        elif s.start_dt > now and nxt is None:
            nxt = s
    return cur, nxt
