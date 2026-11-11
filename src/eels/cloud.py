"""Gemini Live Translate: speech in, translated text out, over the network.

GeminiLive streams the talk audio to one live session per target language and reports the
transcripts it gets back. Sentencer turns the streamed translation into subtitles. Failover
decides when the local pipeline has to take over. Docs: aistudio.google.com/docs/live-api/live-translate.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from .status import GeminiSession, GeminiStatus
from .streaming import SAMPLE_RATE, SENTENCE_END, ambiguous_period, has_content

log = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-3.5-live-translate-preview"
# Paid tier, USD per minute of audio (aistudio.google.com/docs/pricing, 2026-11).
PRICE_IN_PER_MIN = 0.0053
PRICE_OUT_PER_MIN = 0.0315
FRAME_SAMPLES = SAMPLE_RATE // 10  # the docs recommend 100 ms chunks
OUTPUT_BYTES_PER_S = 24000 * 2  # translated speech comes back as 24 kHz 16-bit mono
MAX_QUEUED_FRAMES = 10  # while (re)connecting keep at most 1 s; older audio is stale for live subtitles


KEYCHAIN_SERVICE = "eels-gemini"
_keychain: tuple[float, str | None] = (0.0, None)  # (checked at, key)


KEY_PATTERN = re.compile(r"[A-Za-z0-9._\-]{20,300}")


def key_source() -> str | None:
    """Where the key comes from: "environment", "keychain" or None."""
    if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
        return "environment"
    return "keychain" if api_key() else None


def store_key(key: str) -> None:
    """Save the key in the macOS Keychain (item eels-gemini). Sent to `security` on stdin, so it
    never appears in a process list or a log."""
    global _keychain
    key = key.strip()
    if not KEY_PATTERN.fullmatch(key):
        raise ValueError("That does not look like a Gemini API key.")
    account = os.environ.get("USER") or "eels"
    command = f"add-generic-password -U -a {account} -s {KEYCHAIN_SERVICE} -l eels-gemini-key -w {key}\n"
    out = subprocess.run(["security", "-i"], input=command, capture_output=True, text=True, timeout=10, check=False)
    if out.returncode != 0:
        raise RuntimeError("Could not save the key in the Keychain.")
    _keychain = (0.0, None)  # read it again


def api_key() -> str | None:
    """GEMINI_API_KEY from the environment, else the macOS Keychain item "eels-gemini"
    (`security add-generic-password -a "$USER" -s eels-gemini -w` asks for the key)."""
    global _keychain
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if key:
        return key
    checked, cached = _keychain
    if cached or time.monotonic() - checked < 30:  # the status poll calls this twice a second
        return cached
    try:
        out = subprocess.run(
            ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        cached = (out.stdout.strip() or None) if out.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        cached = None
    _keychain = (time.monotonic(), cached)
    return cached


def targets_for(spoken: str) -> list[str]:
    """Target languages for a spoken-language setting. Detect runs one session per direction;
    each stays silent when the speaker already speaks its target language."""
    return {"en": ["tr"], "tr": ["en"]}.get(spoken, ["en", "tr"])


def echo_for(spoken: str) -> bool:
    """With a fixed language, speech already in the target language (an English quote in a Turkish
    talk) is shown as spoken instead of nothing, which would also look like Gemini failing.
    Detect keeps it off: both sessions would show the same speech."""
    return spoken != "auto"


def to_pcm16(audio: np.ndarray) -> bytes:
    return (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2").tobytes()


# Sentences ------------------------------------------------------------------------------


@dataclass
class Sentence:
    text: str
    source: str  # what the speaker said (Gemini's input transcript), roughly aligned
    src_lang: str | None
    start_mono: float
    end_mono: float  # when the source words for it arrived
    reason: str  # sentence, gap, max_words, finished


@dataclass
class Sentencer:
    """Builds subtitles from streamed translation text.

    Gemini streams whole words, so a sentence is final as soon as a word ends it (not ordinals or
    abbreviations), when Gemini marks the transcript finished, after gap_s without new text, or at max_words.
    Thread-safe: text arrives on the network thread, gap checks run on the housekeeping thread.
    """

    max_words: int = 30
    gap_s: float = 1.0
    pending: str = ""
    source: str = ""
    src_lang: str | None = None
    start_mono: float | None = None
    last_text_mono: float = 0.0
    last_source_mono: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add_source(self, text: str, lang: str | None, now: float) -> None:
        with self._lock:
            self.source += text
            self.src_lang = lang or self.src_lang
            self.last_source_mono = now

    def add_text(self, text: str, now: float, finished: bool = False) -> list[Sentence]:
        with self._lock:
            if not self.pending.strip():
                self.start_mono = now
            self.pending += text
            self.last_text_mono = now
            out = self._split(now)
            if finished:
                out += self._flush(now, "finished")
            return out

    def tick(self, now: float) -> list[Sentence]:
        with self._lock:
            if self.pending.strip() and now - self.last_text_mono >= self.gap_s:
                return self._flush(now, "gap")
            return []

    def interim(self) -> str:
        with self._lock:
            return self.pending.strip()

    def reset(self) -> None:
        with self._lock:
            self.pending = self.source = ""
            self.start_mono = None

    def _split(self, now: float) -> list[Sentence]:
        tokens = self.pending.split()
        out: list[Sentence] = []
        cut = 0
        for i, tok in enumerate(tokens):
            if SENTENCE_END.search(tok) and not ambiguous_period(tok):
                out.append(self._make(" ".join(tokens[cut : i + 1]), now, "sentence"))
                cut = i + 1
        rest = tokens[cut:]
        if len(rest) >= self.max_words:
            commas = [i for i, t in enumerate(rest[: self.max_words]) if t.endswith(",") and i >= self.max_words // 2]
            n = commas[-1] + 1 if commas else self.max_words
            out.append(self._make(" ".join(rest[:n]), now, "max_words"))
            rest = rest[n:]
        if out:
            self.pending = " ".join(rest) + (" " if rest and self.pending.endswith(" ") else "")
            self.source = ""  # the source collected so far belongs to the sentences just cut
            self.start_mono = now if rest else None
        return [s for s in out if has_content(s.text)]

    def _flush(self, now: float, reason: str) -> list[Sentence]:
        text = self.pending.strip()
        self.pending = ""
        out = [self._make(text, now, reason)] if has_content(text) else []
        self.source = ""
        self.start_mono = None
        return out

    def _make(self, text: str, now: float, reason: str) -> Sentence:
        return Sentence(
            text=text,
            source=self.source.strip(),
            src_lang=self.src_lang,
            start_mono=self.start_mono or now,
            end_mono=self.last_source_mono or now,
            reason=reason,
        )


# Failover -------------------------------------------------------------------------------


@dataclass
class Failover:
    """Which engine is on screen. Gemini hands over to the local models when it has been
    disconnected for down_s, or when there has been silent_s of speech without any translation;
    it takes over again after recover_s of being connected and producing text."""

    down_s: float = 5.0
    silent_s: float = 12.0
    recover_s: float = 20.0
    active: str = "gemini"
    down_since: float | None = None
    good_since: float | None = None

    def update(
        self, now: float, connected: bool, last_output: float | None, speech_without_output_s: float
    ) -> str | None:
        """Returns the new engine ("local" or "gemini") when it changes, else None."""
        if self.active == "gemini":
            if connected:
                self.down_since = None
            elif self.down_since is None:
                self.down_since = now
            down = self.down_since is not None and now - self.down_since >= self.down_s
            if down or speech_without_output_s >= self.silent_s:
                self.active, self.good_since = "local", None
                return "local"
            return None
        good = connected and last_output is not None and now - last_output < 5.0
        if not good:
            self.good_since = None
        elif self.good_since is None:
            self.good_since = now
        elif now - self.good_since >= self.recover_s:
            self.active, self.down_since = "gemini", None
            return "gemini"
        return None


# Transport ------------------------------------------------------------------------------


@dataclass
class SessionStatus:
    target: str
    state: str = "connecting"  # connecting, connected, reconnecting, stopped
    connects: int = 0
    last_error: str | None = None
    last_output_mono: float | None = None
    audio_in_s: float = 0.0
    audio_out_s: float = 0.0

    def public(self) -> GeminiSession:
        return GeminiSession(
            target=self.target,
            state=self.state,
            connects=self.connects,
            last_error=self.last_error,
            audio_in_min=round(self.audio_in_s / 60, 1),
            audio_out_min=round(self.audio_out_s / 60, 1),
        )


def classify_error(exc: Exception) -> tuple[str, str]:
    """("closed" | "rejected" | "auth" | "network", message). The SDK raises APIError with the
    WebSocket close code when the server closes: 1000/1001 normal, 1007/1008 bad setup or key."""
    msg = f"{type(exc).__name__}: {exc}"[:300]
    code = getattr(exc, "code", None)
    low = msg.lower()
    if any(w in low for w in ("api key", "api_key", "permission", "unauthenticated", "billi", "credits", "quota")):
        return "auth", msg
    if code in (1000, 1001):
        return "closed", msg
    if code in (1007, 1008) or (isinstance(code, int) and 400 <= code < 500):
        return "rejected", msg
    return "network", msg


def _mentions_extended(msg: str) -> bool:
    low = msg.lower()
    return any(w in low for w in ("resumption", "compression", "sliding", "handle"))


# (target, text, finished, lang) for both callbacks; lang is the detected spoken language for input.
TextCallback = Callable[[str, str, bool, "str | None"], None]


class GeminiLive:
    """Live sessions on their own asyncio thread. feed() and set_targets() are thread-safe."""

    def __init__(
        self,
        on_input: TextCallback,
        on_output: TextCallback,
        on_event: Callable[[str, str], None],
        model: str = GEMINI_MODEL,
        key: str | None = None,
        instruction: str | None = None,  # system instruction (hints.gemini_instruction); used from the next connect
        connect: Callable | None = None,  # tests pass a fake; default is the google-genai client
    ):
        self.on_input = on_input
        self.on_output = on_output
        self.on_event = on_event
        self.model = model
        self.key = key or api_key()
        self.instruction = instruction
        self._connect = connect
        self.sessions: dict[str, SessionStatus] = {}
        self._queues: dict[str, asyncio.Queue] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._buf = np.zeros(0, dtype=np.float32)
        # Resumption and compression keep a session going past the 10-minute connection and
        # 15-minute session limits. If this model rejects them, run without (reconnect fresh).
        self.extended = True
        self.echo = False  # echo_target_language for all sessions
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, name="gemini", daemon=True)
        self._thread.start()

    # Thread-safe API ----------------------------------------------------------------------
    def set_targets(self, targets: list[str], echo: bool = False) -> None:
        """Run one session per target language; sessions are restarted if echo changes."""
        asyncio.run_coroutine_threadsafe(self._set_targets(list(targets), echo), self._loop).result(timeout=5)

    def stop(self) -> None:
        self.set_targets([])

    def restart(self) -> None:
        """Reconnect all sessions, e.g. to apply a new instruction (about a second without subtitles)."""
        targets, echo = list(self.sessions), self.echo
        self.set_targets([], echo)
        self.set_targets(targets, echo)

    def shutdown(self) -> None:
        try:
            self.stop()
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)

    def feed(self, audio: np.ndarray) -> None:
        """16 kHz float32 audio from the capture (any chunk size)."""
        self._buf = np.concatenate([self._buf, audio])
        while len(self._buf) >= FRAME_SAMPLES:
            frame, self._buf = self._buf[:FRAME_SAMPLES], self._buf[FRAME_SAMPLES:]
            self._loop.call_soon_threadsafe(self._put, to_pcm16(frame))

    @property
    def connected(self) -> bool:
        """All wanted sessions are connected."""
        return bool(self.sessions) and all(s.state == "connected" for s in self.sessions.values())

    @property
    def last_output(self) -> float | None:
        times = [s.last_output_mono for s in self.sessions.values() if s.last_output_mono]
        return max(times) if times else None

    def status(self) -> GeminiStatus:
        sess = list(self.sessions.values())
        cost = sum(s.audio_in_s / 60 * PRICE_IN_PER_MIN + s.audio_out_s / 60 * PRICE_OUT_PER_MIN for s in sess)
        return GeminiStatus(self.model, self.connected, [s.public() for s in sess], round(cost, 2))

    # Event loop side ----------------------------------------------------------------------
    def _put(self, frame: bytes) -> None:
        for q in self._queues.values():
            if q.qsize() >= MAX_QUEUED_FRAMES:
                q.get_nowait()
            q.put_nowait(frame)

    async def _set_targets(self, targets: list[str], echo: bool = False) -> None:
        if echo != self.echo:
            self.echo = echo
            targets_now, targets = targets, []  # stop everything, then start with the new setting
            await self._set_targets(targets, echo)
            targets = targets_now
        for t in [t for t in self._tasks if t not in targets]:
            self._tasks.pop(t).cancel()
            self._queues.pop(t, None)
            st = self.sessions.pop(t, None)
            if st:
                st.state = "stopped"
        for t in targets:
            if t not in self._tasks:
                self._queues[t] = asyncio.Queue()
                self.sessions[t] = SessionStatus(t)
                self._tasks[t] = asyncio.create_task(self._run(t))

    def _config(self, target: str, handle: str | None):
        from google.genai import types

        extra = {}
        if self.extended:
            extra = {
                "session_resumption": types.SessionResumptionConfig(handle=handle),
                "context_window_compression": types.ContextWindowCompressionConfig(
                    sliding_window=types.SlidingWindow()
                ),
            }
        return types.LiveConnectConfig(
            # Native-audio models only output AUDIO; text comes from output_audio_transcription.
            # Asking for TEXT is accepted but ignored (audio still streams, same token usage).
            response_modalities=[types.Modality.AUDIO],
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            translation_config=types.TranslationConfig(target_language_code=target, echo_target_language=self.echo),
            system_instruction=self.instruction or None,
            **extra,
        )

    def _open(self, config):
        if self._connect is not None:
            return self._connect(model=self.model, config=config)
        from google import genai

        return genai.Client(api_key=self.key).aio.live.connect(model=self.model, config=config)

    async def _run(self, target: str) -> None:
        st = self.sessions[target]
        handle: str | None = None
        backoff = 1.0
        failures = 0
        while True:
            got_message = False
            try:
                async with self._open(self._config(target, handle)) as session:
                    st.state, st.connects = "connected", st.connects + 1
                    if st.connects > 1:
                        self.on_event("info", f"Gemini ({target.upper()}) reconnected")
                    sender = asyncio.create_task(self._send(session, target))
                    try:
                        while True:
                            n = 0
                            async for msg in session.receive():  # ends at each turn_complete
                                n += 1
                                got_message = True
                                handle = self._handle(target, msg) or handle
                            if n == 0:
                                break  # connection closed
                    finally:
                        sender.cancel()
            except asyncio.CancelledError:
                st.state = "stopped"
                raise
            except Exception as exc:
                kind, why = classify_error(exc)
                if not (kind == "closed" and got_message):  # a normal close after go_away is not an error
                    st.last_error = why
                    log.warning("gemini %s: %s", target, why)
                if kind == "rejected" and handle:
                    handle = None  # an expired or unknown resumption handle: start a fresh session
                elif kind == "rejected" and self.extended and _mentions_extended(why):
                    self.extended = False
                    self.on_event("warn", "Gemini does not accept session resumption here; reconnecting without it")
                elif kind != "closed" or not got_message:
                    failures += 1
                    if failures in (1, 5) or failures % 20 == 0:
                        self.on_event("error", f"Gemini ({target.upper()}) connection failed: {why}")
            if got_message:
                failures = 0
            st.state = "reconnecting"
            if got_message:  # a working connection ended (go_away, time limit): resume right away
                backoff = 1.0
                await asyncio.sleep(0.2)
            else:
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 15.0)

    async def _send(self, session, target: str) -> None:
        from google.genai import types

        q = self._queues[target]
        st = self.sessions[target]
        while True:
            frame = await q.get()
            await session.send_realtime_input(audio=types.Blob(data=frame, mime_type="audio/pcm;rate=16000"))
            st.audio_in_s += len(frame) / 2 / SAMPLE_RATE

    def _handle(self, target: str, msg) -> str | None:
        """Process one server message; returns a new resumption handle if there is one."""
        st = self.sessions.get(target)
        if st is None:
            return None
        sc = getattr(msg, "server_content", None)
        if sc is not None:
            if sc.input_transcription and sc.input_transcription.text:
                t = sc.input_transcription
                self.on_input(target, t.text, bool(t.finished), t.language_code)
            if sc.output_transcription and (sc.output_transcription.text or sc.output_transcription.finished):
                t = sc.output_transcription
                st.last_output_mono = time.monotonic()
                self.on_output(target, t.text or "", bool(t.finished), t.language_code)
            if sc.model_turn and sc.model_turn.parts:
                for part in sc.model_turn.parts:
                    if part.inline_data and part.inline_data.data:
                        st.audio_out_s += len(part.inline_data.data) / OUTPUT_BYTES_PER_S
        if getattr(msg, "go_away", None) is not None:
            log.info("gemini %s: go_away, %s left", target, msg.go_away.time_left)
        upd = getattr(msg, "session_resumption_update", None)
        if upd is not None and upd.resumable and upd.new_handle:
            return upd.new_handle
        return None
