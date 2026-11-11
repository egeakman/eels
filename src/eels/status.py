"""What the control panel is told, twice a second: one typed message in named sections.

Built by Pipeline.status(); sent as JSON (dataclasses.asdict). Also the shapes of events and
of the talks on the schedule as the panel shows them.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Literal

Level = Literal["info", "warn", "error"]
WorkerState = Literal["stopped", "loading", "ready", "busy", "error", "restarting", "unloaded"]
Role = Literal["in use", "backup", "unloaded", "idle"]
Engine = Literal["local", "gemini"]


@dataclass
class Event:
    """A line in Recent events."""

    level: Level
    msg: str
    t: str = field(default_factory=lambda: time.strftime("%H:%M:%S"))


@dataclass
class Segment:
    """A final subtitle on the overlay."""

    id: int  # sentence number (negative for the test text)
    text: str
    lang: str


@dataclass
class Pending:
    """The sentence in progress (live preview)."""

    base: int  # the sentence number it will become
    text: str
    lang: str
    t: float  # monotonic time it was set


@dataclass
class Run:
    running: bool
    source: Literal["live", "file"]
    file: str | None  # test file being played
    file_pos_s: float | None
    uptime_s: int


@dataclass
class Audio:
    device: str | None  # active input device
    error: str | None  # what is wrong with the input, in words for the operator
    mic_permission: str
    overflows: int
    gain_db: float  # current boost by Lift quiet input
    speech: bool


@dataclass
class EngineState:
    chosen: Engine  # the operator's choice
    on_screen: Engine  # differs from chosen while the local models stand in for Gemini
    keeping_up: bool
    gemini_key: Literal["environment", "keychain"] | None


@dataclass
class Delays:
    """Seconds from speech to text on screen (median and 95th percentile of recent subtitles)."""

    first_p50: float | None
    first_p95: float | None
    final_p50: float | None
    final_p95: float | None


@dataclass
class LocalTiming:
    speech_ms: float | None  # per Whisper pass
    step_s: float  # how often Whisper runs
    translation_ms: float | None  # per sentence
    translation_queue: int
    backlog_s: float  # audio waiting to be processed
    skips: int  # times eels jumped ahead to live audio


@dataclass
class ModelStatus:
    """One loaded (or unloaded) local model."""

    job: Literal["speech", "translation"]
    key: str  # catalog key
    name: str
    variant: str
    directions: list[str]  # translation: ["en>tr", "tr>en"]; empty for speech
    state: WorkerState
    role: Role
    loading_s: int | None  # while loading
    memory_gb: float | None  # measured, while loaded
    restarts: int
    last_error: Event | None


@dataclass
class GeminiSession:
    target: str
    state: str  # connecting, connected, reconnecting, stopped
    connects: int
    last_error: str | None
    audio_in_min: float
    audio_out_min: float


@dataclass
class GeminiStatus:
    model: str
    connected: bool
    sessions: list[GeminiSession]
    cost_usd: float


@dataclass
class Talk:
    start: str  # HH:MM
    end: str
    title: str
    speaker: str | None
    lang: str | None  # None: Detect


@dataclass
class Status:
    run: Run
    audio: Audio
    engine: EngineState
    delays: Delays
    local: LocalTiming
    models: list[ModelStatus]
    switching: dict[str, str]  # kind -> model key being loaded
    gemini: GeminiStatus | None
    talk_now: Talk | None
    talk_next: Talk | None
    events: list[Event]
    settings: dict
    type: str = "status"

    def to_json(self) -> dict:
        return asdict(self)
