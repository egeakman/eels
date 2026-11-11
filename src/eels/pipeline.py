"""The live pipeline: audio -> VAD -> streaming ASR -> clauses -> MT -> overlay + transcript.

Threads:
  audio consumer (audio.py)  -> self._audio_q
  asr-loop                   VAD, gate, LocalAgreement, clause segmentation, ASR worker calls
  mt-loop                    translation worker calls (confirmed clauses first, then latest interim)
  housekeeping               clear-after-silence, schedule auto-switch, status publishing, failover
  gemini (cloud.py)          with engine "gemini": streams audio to Gemini Live Translate and shows its
                             text; the local pipeline takes over while Gemini is down (cloud.Failover)
"""

from __future__ import annotations

import logging
import queue
import statistics
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import ClassVar

import numpy as np

from . import hints, models
from . import schedule as sched
from . import status as st
from .audio import AudioCapture, DeviceWatcher, FilePlayer, list_input_devices, load_audio_file, mic_permission
from .cloud import Failover, GeminiLive, Sentence, Sentencer, api_key, echo_for, key_source, store_key, targets_for
from .config import Settings, SettingsStore, translation_model_for
from .engine import Interim, StreamEngine, other
from .gender import neutralize
from .names import NameCorrector
from .status import Event
from .streaming import SAMPLE_RATE, Clause
from .transcript import TranscriptLog, TranscriptRecord
from .translate import check_translation
from .vad import AutoGain, SileroVAD, SpeechGate
from .workers import WorkerClient, WorkerError

log = logging.getLogger(__name__)

LANG_NAMES = {"en": "English", "tr": "Turkish"}


def _dirs_text(dirs, before: str = "", after: str = "") -> str:
    """("en", "tr") pairs as "English to Turkish and Turkish to English"."""
    text = " and ".join(f"{LANG_NAMES[a]} to {LANG_NAMES[b]}" for a, b in dirs)
    return f"{before}{text}{after}" if text else ""


Publish = Callable[[str, dict], None]  # (channel, message), channel in {"overlay", "control"}

TEST_LINES = {
    "en": "This is a test subtitle in English. It should wrap onto a second line and stay centered.",
    "tr": "Bu bir Türkçe deneme altyazısıdır: İstanbul'da ılık bir gün, şimdi ağır çekimde göçüyor; Ç Ö Ü Ğ Ş İ ı.",
}


class Rolling:
    def __init__(self, n: int = 50):
        self.v: deque[float] = deque(maxlen=n)

    def add(self, x: float) -> None:
        self.v.append(x)

    def p(self, q: float) -> float | None:
        if not self.v:
            return None
        s = sorted(self.v)
        return s[min(len(s) - 1, int(q * len(s)))]

    def mean(self) -> float | None:
        return statistics.fmean(self.v) if self.v else None


@dataclass
class MTJob:
    kind: str  # "confirmed" | "interim"
    text: str
    src: str
    tgt: str
    base: int  # clause counter when created (for interim) or the clause's seq (confirmed)
    start_t: float = 0.0  # stream seconds
    end_t: float = 0.0
    end_mono: float = 0.0  # capture time of the last word (for delay metrics)
    created: float = field(default_factory=time.monotonic)
    session: str | None = None
    reason: str = ""  # why the sentence was cut: sentence, gap, max_words, max_time, language, end
    model: str = ""  # catalog key of the translation model that produced the text
    corrections: list = field(default_factory=list)  # (heard, corrected) name fixes


class Display:
    """What the overlay shows. All mutations go through here and are broadcast as a full snapshot."""

    def __init__(self, publish: Publish, settings: Callable[[], Settings]):
        self.publish = publish
        self.settings = settings
        self.segments: deque[st.Segment] = deque(maxlen=8)
        self.interim: st.Pending | None = None
        self.last_change = time.monotonic()
        self.hold_until = 0.0  # test text stays up until this time
        self._lock = threading.Lock()

    def snapshot(self) -> dict:
        s = self.settings()
        return {
            "type": "state",
            "visible": s.visible,
            "segments": [asdict(x) for x in self.segments],
            "interim": self.interim.text if self.interim else "",
            "style": {
                "font_size": s.font_size,
                "lines": s.lines,
                "line_height": s.line_height,
                "shadow": s.shadow,
                "vertical_offset": s.vertical_offset,
            },
        }

    def push(self) -> None:
        self.publish("overlay", self.snapshot())

    @property
    def empty(self) -> bool:
        return not self.segments and not self.interim

    def add_confirmed(self, seq: int, text: str, lang: str) -> None:
        with self._lock:
            if self.segments and self.segments[-1].lang != lang:
                self.segments.clear()  # direction changed: start fresh
            self.segments.append(st.Segment(seq, text, lang))
            if self.interim and self.interim.base <= seq:
                self.interim = None
            self.last_change = time.monotonic()
        self.push()

    def set_interim(self, base: int, text: str, lang: str, current_base: int) -> bool:
        with self._lock:
            if base != current_base:
                return False  # a clause was cut since this was requested; it would duplicate text
            now = time.monotonic()
            old = self.interim
            if old and old.base == base:
                a, b = old.text.split(), text.split()
                only_last_word = len(a) == len(b) and a[:-1] == b[:-1]
                if text == old.text or (only_last_word and now - old.t < 0.5):
                    return False
            if self.segments and self.segments[-1].lang != lang:
                self.segments.clear()
            self.interim = st.Pending(base, text, lang, now)
            self.last_change = now
        self.push()
        return True

    def drop_interim(self) -> None:
        with self._lock:
            if self.interim is None:
                return
            self.interim = None
        self.push()

    def clear(self) -> None:
        with self._lock:
            self.segments.clear()
            self.interim = None
            self.last_change = time.monotonic()
            self.hold_until = 0.0
        self.push()

    def show_test(self, hold_s: float = 20.0) -> None:
        with self._lock:
            self.segments.clear()
            self.segments.append(st.Segment(-2, TEST_LINES["en"], "en"))
            self.segments.append(st.Segment(-1, TEST_LINES["tr"], "tr"))
            self.interim = None
            self.last_change = time.monotonic()
            self.hold_until = self.last_change + hold_s
        self.push()


class Pipeline:
    def __init__(self, store: SettingsStore, publish: Publish):
        self.store = store
        self.publish = publish
        s = store.value
        self.display = Display(publish, lambda: self.store.value)
        self.transcript = TranscriptLog()
        self.sessions = sched.load()
        self._names_for = None
        self._refresh_names()
        self.current_session: sched.Session | None = None
        self.next_session: sched.Session | None = None

        self.asr = self._new_worker(s.speech_model)
        # One translation worker per distinct model key; each direction uses translation_model_for().
        self.mt_pool: dict[str, WorkerClient] = {}

        self.engine = StreamEngine(
            lambda: self.store.value,
            self._asr_call,
            self._on_clause,
            self._on_interim,
            clock=self._audio_clock,
            title=self._asr_hint,
        )

        self._audio_q: queue.Queue = queue.Queue()
        self.capture = AudioCapture(self._on_audio)
        self.capture.configure(s.device_name, s.channel)
        self.watcher = DeviceWatcher(self._on_devices_changed)
        self.player: FilePlayer | None = None
        self.source = "live"
        self.file_name: str | None = None

        self.running = False
        self.clock = (0.0, time.monotonic())  # (stream seconds, capture monotonic) of the last chunk
        self.backlog_s = 0.0
        self.falling_behind_events = 0
        self.last_skip: float | None = None

        self._mt_lock = threading.Condition()
        self._mt_confirmed: deque[MTJob] = deque()
        self._mt_interim: MTJob | None = None
        self._reload: set[str] = set()  # workers to restart with the same model (memory watchdog)
        self._mt_client_lock = threading.Lock()  # held while the MT loop uses self.mt
        self.switching: dict[str, str] = {}  # kind -> model key being loaded for a hot swap
        self._engine_lock = threading.RLock()
        self._shutdown = threading.Event()

        # Gemini engine (cloud.py). The local pipeline stays loaded as the fallback.
        self.cloud: GeminiLive | None = None
        self.failover = Failover()
        self.sentencers: dict[str, Sentencer] = {}
        self.cloud_agc = AutoGain()
        self.cloud_vad = SileroVAD()
        self.cloud_gate = SpeechGate()
        self.cloud_last_speech = 0.0  # capture time of the last speech frame (clear-after-silence)
        self.cloud_speech_s = 0.0  # seconds of speech since Gemini last produced text
        self.ring: deque[tuple[np.ndarray, float]] = deque()  # recent audio, replayed into the local engine on failover
        self.cloud_seq = 1_000_000  # subtitle ids, apart from the local engine's clause numbers

        self.m_asr_ms = Rolling()
        self.m_mt_ms = Rolling()
        self.m_delay_interim = Rolling()
        self.m_delay_confirmed = Rolling()
        self.started_at = time.monotonic()
        self.events: deque[Event] = deque(maxlen=30)

        self._threads = [
            threading.Thread(target=self._asr_loop, name="asr-loop", daemon=True),
            threading.Thread(target=self._mt_loop, name="mt-loop", daemon=True),
            threading.Thread(target=self._housekeeping, name="housekeeping", daemon=True),
        ]

    # Lifecycle ------------------------------------------------------------------
    def boot(self) -> None:
        """Start workers (model loading) and background threads. Audio starts with start()."""
        s = self.store.value
        for model in self._mt_models_in_use():
            self._mt_add(model)
        if s.engine == "gemini" and not s.gemini_standby and api_key():
            for w in self._local_workers():  # not needed until Gemini fails
                w.parked, w.status.state = True, "unloaded"
        else:
            for w in self._local_workers():
                w.start()
        self.watcher.start()
        if s.engine == "gemini":
            self._cloud_enable()
        for t in self._threads:
            t.start()

    def shutdown(self) -> None:
        self._shutdown.set()  # threads exit and must not respawn workers afterwards
        self.stop()
        if self.cloud:
            self.cloud.shutdown()
        self.capture.close()
        self.watcher.stop()
        self.asr.stop()
        for w in list(self.mt_pool.values()):
            w.stop()

    def start(self) -> None:
        if self.source == "live":
            self.capture.start()
        self.running = True
        self._cloud_open()
        self.event("info", "started")

    def stop(self) -> None:
        self.running = False
        self.capture.stop()
        if self.player:
            self.player.stop()
            self.player = None
        self._engine_call(lambda: self.engine.end_utterance(flush=True))
        if self.cloud:
            self.cloud.stop()
            for target, sn in list(self.sentencers.items()):
                for sent in sn.tick(float("inf")):  # show what was still pending
                    self._cloud_show(target, sent)
        self.event("info", "stopped")

    def play_file(self, path: str, speed: float = 1.0) -> None:
        audio = load_audio_file(path)
        self.capture.stop()
        if self.player:
            self.player.stop()
        self.source = "file"
        self.file_name = str(path)
        self.player = FilePlayer(
            audio, self._on_audio, speed=speed, on_done=lambda: self.event("info", f"file finished: {path}")
        )
        self.running = True
        self._cloud_open()
        self.player.start()
        self.event("info", f"playing {path} ({len(audio) / SAMPLE_RATE:.0f} s, speed {speed}x)")

    def use_live(self) -> None:
        if self.player:
            self.player.stop()
            self.player = None
        self.source = "live"
        self.file_name = None
        if self.running:
            self.capture.start()

    def event(self, level: str, msg: str) -> None:
        self.events.append(Event(level, msg))
        getattr(log, "warning" if level == "warn" else level if level in ("info", "error") else "info")(msg)

    # Settings -------------------------------------------------------------------
    @staticmethod
    def _new_worker(key: str) -> WorkerClient:
        """A worker for a catalog model (not started)."""
        m = models.get(key)
        if m.job == "speech":
            w = WorkerClient("asr", "eels.asr:create", dict(m.spec))
        else:
            w = WorkerClient("mt", "eels.translate:create", dict(m.spec))
        w.model_key = key
        return w

    def apply_settings(self, changes: dict) -> Settings:
        changes = dict(changes)
        # Model changes load the new model first (switch_model); the setting follows when it is ready.
        for kind, field_name in self.MODEL_FIELDS.items():
            key = changes.pop(field_name, None)
            if key:
                self.switch_model(kind, key)
        old = self.store.value
        s = self.store.update(**changes)
        if "device_name" in changes or "channel" in changes:
            self.capture.configure(s.device_name, s.channel)
        if s.spoken_language != old.spoken_language:
            self.engine.language_changed(s.spoken_language)
        if (s.engine, s.gemini_model) != (old.engine, old.gemini_model):
            self._cloud_disable()
            if s.engine == "gemini":
                self._cloud_enable()
            self._apply_standby()
        elif s.gemini_standby != old.gemini_standby:
            self._apply_standby()
        elif s.spoken_language != old.spoken_language:
            self._cloud_open()
        if not s.interim and old.interim:
            self.display.drop_interim()
        self.engine.sync_settings()
        self.display.push()
        return s

    def _audio_clock(self) -> float:
        """Capture time of the audio being processed (monotonic seconds).

        Audio queues up while Whisper runs, then gets processed in a burst. Timing pauses and
        sentence gaps by processing time would stretch them by up to a pass; capture time does not.
        Falls back to the wall clock when no audio has arrived for a while (stopped, unplugged).
        """
        captured = self.clock[1]
        now = time.monotonic()
        return captured if now - captured < 0.5 else now

    def _refresh_names(self, cur=None, nxt=None) -> None:
        """Dictionary for name correction: speakers, all-day names, the current and next talks' terms."""
        names = hints.speakers(self.sessions) + hints.always_names()
        for sess in (cur, nxt):
            if sess:
                names += hints.talk_terms(sess.title)
        self._names = NameCorrector(names)
        self._names_for = (cur, nxt)

    def _asr_hint(self, lang: str = "en") -> str:
        """The day's program for Whisper (see hints.py)."""
        return hints.asr_hint(lang, self.sessions, self.current_session, self.next_session)

    # Translation workers ----------------------------------------------------------
    DIRECTIONS = (("en", "tr"), ("tr", "en"))

    def _mt_models_in_use(self, s: Settings | None = None) -> list[str]:
        s = s or self.store.value
        return list(dict.fromkeys(translation_model_for(s, a, b) for a, b in self.DIRECTIONS))

    def _mt_add(self, key: str) -> WorkerClient:
        w = self._new_worker(key)
        self.mt_pool[key] = w
        return w

    def _mt_prune(self) -> None:
        """Stop workers no direction uses any more."""
        used = set(self._mt_models_in_use())
        for model in [m for m in self.mt_pool if m not in used]:
            self.mt_pool.pop(model).stop()

    @property
    def mt_ready(self) -> bool:
        return bool(self.mt_pool) and all(w.ready for w in self.mt_pool.values())

    def _mt_dirs(self, key: str) -> list[tuple[str, str]]:
        """The directions a translation model serves."""
        s = self.store.value
        return [(a, b) for a, b in self.DIRECTIONS if translation_model_for(s, a, b) == key]

    # Hot swap -----------------------------------------------------------------------
    # kind -> the setting it changes, and the translation directions it covers
    MODEL_FIELDS: ClassVar[dict[str, str]] = {
        "speech": "speech_model",
        "translation": "translation_model",
        "translation_en_tr": "translation_model_en_tr",
        "translation_tr_en": "translation_model_tr_en",
    }
    MT_KINDS: ClassVar[dict[str, tuple[tuple[str, str], ...]]] = {
        "translation": DIRECTIONS,
        "translation_en_tr": (("en", "tr"),),
        "translation_tr_en": (("tr", "en"),),
    }

    def switch_model(self, kind: str, key: str) -> None:
        """Load a new model in a fresh worker while the current one keeps working, then swap.

        kind: "speech", "translation" (both directions), "translation_en_tr" or "translation_tr_en";
        key: a model from the catalog. Subtitles do not pause. If the new model fails to load,
        the current one stays. The setting is saved only after the swap succeeded.
        """
        m = models.get(key)
        if m.job != ("speech" if kind == "speech" else "translation"):
            raise ValueError(f"{m.title} is not a {kind} model")
        if kind in self.switching:
            self.event("warn", f"already switching the {kind} model; wait for it to finish")
            return
        if self.local_parked:
            self.event(
                "warn",
                "the local models are unloaded while Gemini runs; turn on Keep local models loaded (Engine) to change them",
            )
            return
        if kind == "speech":
            if self.asr.model_key == key:
                return
        else:
            s = self.store.value
            if all(translation_model_for(s, a, b) == key for a, b in self.MT_KINDS[kind]):
                return
            if key in self.mt_pool and self.mt_pool[key].ready:
                self._mt_assign(kind, key)  # already loaded for the other direction
                return
        self.switching[kind] = key
        what = "speech recognition" if kind == "speech" else "translation" + _dirs_text(self.MT_KINDS[kind], " (", ")")
        self.event("info", f"loading {m.title} for {what}; the current model keeps running until it is ready")
        threading.Thread(target=self._switch_worker, args=(kind, key), name=f"switch-{kind}", daemon=True).start()

    def _mt_assign(self, kind: str, key: str) -> None:
        with self._mt_client_lock:
            if kind == "translation":
                self.store.update(translation_model=key, translation_model_en_tr=None, translation_model_tr_en=None)
            else:
                self.store.update(**{self.MODEL_FIELDS[kind]: key})
            self._mt_prune()
        self.m_mt_ms.v.clear()
        self.event(
            "info", f"now using {models.get(key).title} for translation{_dirs_text(self._mt_dirs(key), ' (', ')')}"
        )

    def _switch_worker(self, kind: str, key: str) -> None:
        new = self._new_worker(key)
        title = models.get(key).title
        try:
            new.start()
            ok = new.wait_ready(timeout=900)
            if not ok or self._shutdown.is_set():
                err = new.status.errors[-1].msg if new.status.errors else "did not load"
                new.stop()
                self.event("error", f"could not load {title} ({err}); keeping the current model")
                return
            new.status.restarts = 0
            if kind == "speech":
                with self._engine_lock:  # no call is in flight on the old worker while we swap
                    old, self.asr = self.asr, new
                    self.engine.asr_ms.clear()  # step timing belongs to the old model
                    self.m_asr_ms.v.clear()
                old.stop()
                self.store.update(speech_model=key)
                self.event("info", f"now using {title} for speech recognition")
            else:
                with self._mt_client_lock:
                    previous = self.mt_pool.get(key)
                    self.mt_pool[key] = new
                if previous is not None:
                    previous.stop()
                self._mt_assign(kind, key)
        except Exception as exc:
            log.exception("model switch")
            self.event("error", f"model switch failed: {exc}")
        finally:
            self.switching.pop(kind, None)

    def _on_devices_changed(self) -> None:
        if self.source == "live":
            self.capture.refresh_devices()
        else:
            from .audio import reinit_portaudio

            if not self.capture.stream:
                reinit_portaudio()
        self.publish("control", {"type": "devices", "devices": list_input_devices()})

    # Audio in -------------------------------------------------------------------
    def _on_audio(self, chunk: np.ndarray, t_mono: float) -> None:
        if self.running:
            self._audio_q.put((chunk, t_mono))

    def stream_to_mono(self, t: float) -> float:
        cs, cm = self.clock
        return cm - (cs - t)

    def mono_to_wall(self, m: float) -> datetime:
        return datetime.now(sched.TZ) - timedelta(seconds=time.monotonic() - m)

    # ASR loop -------------------------------------------------------------------
    def _engine_call(self, fn) -> None:
        """Engine methods are only called from the asr-loop thread, except stop() via this lock."""
        with self._engine_lock:
            fn()

    def _asr_loop(self) -> None:
        while not self._shutdown.is_set():
            try:
                with self._engine_lock:  # the worker client is not thread-safe; stop() also uses it
                    if "asr" in self._reload:
                        self._reload.discard("asr")
                        self.asr.reconfigure(self.asr.spec)
                    if not self.asr.ready:
                        self.asr.poll()  # keeps the status current while loading, respawns after a failed load
                try:
                    chunk, t_mono = self._audio_q.get(timeout=0.05)
                except queue.Empty:
                    chunk = None
                with self._engine_lock:
                    if chunk is not None and self.cloud is not None:
                        self._cloud_audio(chunk, t_mono)
                    if self.active == "gemini":
                        if chunk is not None:  # the local engine idles but keeps its timeline
                            self.engine.stream_samples += len(chunk)
                            self.clock = (self.engine.stream_t, t_mono)
                        self.backlog_s = 0.0
                        continue
                    if chunk is not None:
                        self.clock = (self.engine.stream_t + len(chunk) / SAMPLE_RATE, t_mono)
                        self.engine.process_chunk(chunk)
                        if not self._audio_q.empty():
                            self._check_backlog()
                            continue  # drain the queue before running ASR
                    self.backlog_s = 0.0 if chunk is None else max(0.0, time.monotonic() - t_mono)
                    self.engine.maybe_run_asr()
                    self.engine.check_age()
            except Exception:
                log.exception("asr loop")
                self.event("error", "ASR loop error (recovered)")
                time.sleep(0.2)

    def _check_backlog(self) -> None:
        try:
            _, oldest = self._audio_q.queue[0]
        except IndexError:
            return
        self.backlog_s = time.monotonic() - oldest
        if self.backlog_s <= self.store.value.max_backlog_s:
            return
        # Too far behind: drop queued audio, finalize what we have, continue from live audio.
        dropped = 0
        keep_from = time.monotonic() - 0.3
        while True:
            try:
                c, t = self._audio_q.queue[0]
            except IndexError:
                break
            if t >= keep_from:
                break
            self._audio_q.get_nowait()
            self.engine.stream_samples += len(c)
            self.clock = (self.engine.stream_t, t)
            dropped += len(c)
        self.engine.end_utterance(flush=True)
        self.engine.vad.reset()
        self.falling_behind_events += 1
        self.last_skip = time.monotonic()
        self.event("warn", f"falling behind: skipped {dropped / SAMPLE_RATE:.1f} s of audio")

    def _asr_call(self, audio: np.ndarray, lang: str | None, prompt: str) -> dict | None:
        if not self.asr.poll():
            return None
        try:
            res = self.asr.call(
                {"op": "transcribe", "audio": audio, "language": lang, "prompt": prompt},
                timeout=max(8.0, 2 * len(audio) / SAMPLE_RATE),
            )
        except WorkerError as exc:
            self.event("error", str(exc))
            return None
        self.m_asr_ms.add(res["ms"])
        return res

    def _on_interim(self, it: Interim) -> None:
        text, _ = self._names.correct(it.text)
        job = MTJob(
            "interim",
            text,
            it.lang,
            other(it.lang),
            it.base,
            end_mono=self.stream_to_mono(it.end_t),
            session=self._session_title(),
        )
        with self._mt_lock:
            self._mt_interim = job
            self._mt_lock.notify()

    def _session_title(self) -> str | None:
        return self.current_session.title if self.current_session else None

    def _on_clause(self, clause: Clause, src: str, seq: int) -> None:
        text, corrections = self._names.correct(clause.text)  # misheard program names
        job = MTJob(
            "confirmed",
            text,
            src,
            other(src),
            seq,
            clause.start,
            clause.end,
            self.stream_to_mono(clause.end),
            session=self._session_title(),
            reason=clause.reason,
            corrections=corrections,
        )
        with self._mt_lock:
            self._mt_confirmed.append(job)
            self._mt_lock.notify()

    # MT loop --------------------------------------------------------------------
    def _mt_loop(self) -> None:
        while not self._shutdown.is_set():
            try:
                with self._mt_client_lock:
                    self._mt_step()
            except Exception:
                log.exception("mt loop")
                self.event("error", "MT loop error (recovered)")
                time.sleep(0.2)

    def _mt_step(self) -> None:
        """One iteration of the MT loop; runs with _mt_client_lock held so a hot swap waits."""
        for key in [k for k in self._reload if k.startswith("mt|")]:
            self._reload.discard(key)
            w = self.mt_pool.get(key[3:])
            if w is not None:
                w.reconfigure(w.spec)
        for w in self.mt_pool.values():
            if not w.ready:
                w.poll()  # keeps the status current while loading, respawns after a failed load
        with self._mt_lock:
            if not self._mt_confirmed and self._mt_interim is None:
                self._mt_lock.wait(timeout=0.2)
            if self._mt_confirmed:
                job = self._mt_confirmed.popleft()
            elif self._mt_interim is not None:
                job, self._mt_interim = self._mt_interim, None
            else:
                return
        worker = self.mt_pool.get(translation_model_for(self.store.value, job.src, job.tgt))
        if worker is None or not worker.ready:
            # The model for this direction is not loaded (yet): show the source text rather than nothing.
            if job.kind == "confirmed":
                self._show_confirmed(job, job.text, fallback=True)
            return
        if job.kind == "confirmed":
            self._translate_confirmed(job)
        else:
            self._translate_interim(job)

    def _call_mt(self, job: MTJob, timeout: float) -> str | None:
        model = translation_model_for(self.store.value, job.src, job.tgt)
        worker = self.mt_pool.get(model)
        if worker is None:
            return None
        job.model = model
        req = {
            "text": job.text,
            "src": job.src,
            "tgt": job.tgt,
            "protect": hints.protected_names(self.sessions),
        }  # program names stay untranslated
        try:
            res = worker.call(req, timeout=timeout)
        except WorkerError as exc:
            self.event("error", str(exc))
            return None
        self.m_mt_ms.add(res["ms"])
        text = res["text"]
        if job.src == "tr" and job.tgt == "en" and self.store.value.gender_neutral:
            text = neutralize(text, job.text)  # Turkish has no gender; do not guess he/she
        return text

    def _translate_confirmed(self, job: MTJob) -> None:
        out = self._call_mt(job, timeout=10.0)
        problem = check_translation(job.text, out or "", job.tgt) if out is not None else "worker failed"
        if problem:
            out2 = self._call_mt(job, timeout=10.0)
            problem2 = check_translation(job.text, out2 or "", job.tgt) if out2 is not None else "worker failed"
            if problem2:
                self.event("warn", f"translation rejected ({problem2}); showing source text")
                self._show_confirmed(job, job.text, fallback=True)
                return
            out = out2
        assert out is not None
        self._show_confirmed(job, out, fallback=False)

    def _show_confirmed(self, job: MTJob, text: str, fallback: bool) -> None:
        self.display.add_confirmed(job.base, text, job.src if fallback else job.tgt)
        self.m_delay_confirmed.add(time.monotonic() - job.end_mono)
        s = self.store.value
        try:
            self.transcript.append(
                TranscriptRecord(
                    start=self.mono_to_wall(self.stream_to_mono(job.start_t)),
                    end=self.mono_to_wall(job.end_mono),
                    src=job.src,
                    tgt=job.tgt,
                    source=job.text,
                    translation=text,
                    engine="local",
                    speech_model=self.asr.model_key or s.speech_model,
                    translation_model=job.model or translation_model_for(s, job.src, job.tgt),
                    mode=s.spoken_language,
                    session=job.session,
                    cut=job.reason,
                    delay_s=round(time.monotonic() - job.end_mono, 2),
                    fallback=fallback,
                    corrections=job.corrections,
                )
            )
        except Exception:
            log.exception("transcript write")

    def _translate_interim(self, job: MTJob) -> None:
        if job.base != self.engine.clause_seq:
            return  # stale
        out = self._call_mt(job, timeout=5.0)
        if not out or check_translation(job.text, out, job.tgt):
            return
        if self.store.value.interim and self.display.set_interim(job.base, out, job.tgt, self.engine.clause_seq):
            self.m_delay_interim.add(time.monotonic() - job.end_mono)

    # Gemini ---------------------------------------------------------------------
    @property
    def active(self) -> str:
        """The engine whose subtitles are on screen."""
        return "gemini" if self.cloud is not None and self.failover.active == "gemini" else "local"

    def _agc(self) -> AutoGain:
        return self.cloud_agc if self.active == "gemini" else self.engine.agc

    def _in_speech(self) -> bool:
        return self.cloud_gate.in_speech if self.active == "gemini" else self.engine.gate.in_speech

    def _last_speech(self) -> float:
        return self.cloud_last_speech if self.active == "gemini" else self.engine.last_speech

    def _cloud_enable(self) -> None:
        s = self.store.value
        if not api_key():
            self.event("error", "no Gemini key (Keychain item eels-gemini or GEMINI_API_KEY); using the local models")
            return
        self.cloud = GeminiLive(
            self._cloud_input,
            self._cloud_output,
            self.event,
            model=s.gemini_model,
            instruction=self._gemini_instruction(),
        )
        self.failover = Failover()
        self.sentencers = {}
        self._cloud_open()
        self.event("info", f"engine: {s.gemini_model} (local models on standby)")

    def _local_workers(self) -> list[WorkerClient]:
        return [self.asr, *self.mt_pool.values()]

    @property
    def local_parked(self) -> bool:
        return self.asr.parked

    def _apply_standby(self) -> None:
        """Local models: loaded unless Gemini is on screen and the operator chose not to keep them."""
        unload = self.active == "gemini" and not self.store.value.gemini_standby
        changed = False
        for w in self._local_workers():
            if unload and not w.parked:
                w.park()
                changed = True
            elif not unload and w.parked:
                w.start()
                changed = True
        if changed:
            self.event(
                "info",
                "local models unloaded; they load again if Gemini fails" if unload else "loading the local models",
            )

    def set_gemini_key(self, key: str) -> str:
        """Save the Gemini key from the control panel and reconnect with it."""
        store_key(key)
        self.event("info", "Gemini key saved in the Keychain")
        if key_source() == "environment":
            return "Saved, but GEMINI_API_KEY in the environment is used instead while it is set."
        if self.store.value.engine == "gemini":
            self._cloud_disable()
            self._cloud_enable()
            self._apply_standby()
        return "Saved in the Keychain."

    def _gemini_instruction(self) -> str:
        return hints.gemini_instruction(self.sessions, self.store.value.gemini_extra_instruction)

    def set_gemini_extra(self, text: str) -> str:
        """Operator's addition to Gemini's instruction (control panel). Applied by reconnecting
        the sessions, about a second without subtitles. Returns the full instruction."""
        text = text.strip()
        if text != self.store.value.gemini_extra_instruction:
            self.store.update(gemini_extra_instruction=text)
            if self.cloud is not None:
                self.cloud.instruction = self._gemini_instruction()
                self.cloud.restart()
            self.event("info", "Gemini instructions " + ("updated" if text else "reset") + "; Gemini reconnected")
        return self._gemini_instruction()

    def _cloud_disable(self) -> None:
        if self.cloud is None:
            return
        with self._engine_lock:
            cloud, self.cloud = self.cloud, None
        cloud.shutdown()
        self.display.drop_interim()
        self.event("info", "engine: local models")

    def _cloud_open(self) -> None:
        """Open (or retarget) the live sessions for the current spoken language while running."""
        if self.cloud is None or not self.running:
            return
        spoken = self.store.value.spoken_language
        targets = targets_for(spoken)
        for t in [t for t in self.sentencers if t not in targets]:
            self.sentencers.pop(t)
        self.cloud.set_targets(targets, echo=echo_for(spoken))

    def _sentencer(self, target: str) -> Sentencer:
        s = self.store.value
        sn = self.sentencers.get(target)
        if sn is None:
            sn = self.sentencers[target] = Sentencer()
        sn.max_words, sn.gap_s = s.sentence_max_words, s.sentence_gap_s
        return sn

    def _cloud_audio(self, chunk: np.ndarray, t_mono: float) -> None:
        """Audio to Gemini, plus speech detection (failover, clear-after-silence) and a short
        history the local engine can start from if it has to take over."""
        assert self.cloud is not None
        s = self.store.value
        x = self.cloud_agc.process(chunk) if s.auto_gain else chunk
        self.cloud.feed(x)
        for frame, prob in self.cloud_vad.process(x):
            self.cloud_gate.update(frame, prob)
        dur = len(chunk) / SAMPLE_RATE
        if self.cloud_gate.in_speech:
            if self.cloud_gate.silence_s == 0.0:
                self.cloud_last_speech = t_mono
            if self.cloud_gate.silence_s < 0.5 and self.running:
                self.cloud_speech_s += dur
            if self.cloud_gate.silence_s >= s.utterance_end_s:
                self.cloud_gate.end()
        self.ring.append((chunk, t_mono))
        while self.ring and t_mono - self.ring[0][1] > 4.0:
            self.ring.popleft()

    def _cloud_input(self, target: str, text: str, finished: bool, lang: str | None) -> None:
        self._sentencer(target).add_source(text, (lang or "")[:2] or None, time.monotonic())

    def _cloud_output(self, target: str, text: str, finished: bool, lang: str | None) -> None:
        self.cloud_speech_s = 0.0
        sn = self._sentencer(target)
        done = sn.add_text(text, time.monotonic(), finished)
        if self.active != "gemini":
            return
        for sent in done:
            self._cloud_show(target, sent)
        if self.store.value.interim:
            tail = sn.interim()
            if tail:
                tail = self._names.correct(tail)[0]
                base = self.cloud_seq + 1
                if self.display.set_interim(base, tail, target, base):
                    self.m_delay_interim.add(time.monotonic() - (sn.last_source_mono or time.monotonic()))

    def _cloud_show(self, target: str, sent: Sentence) -> None:
        s = self.store.value
        src = sent.src_lang if sent.src_lang in ("en", "tr") else other(target)
        text, corrections = self._names.correct(sent.text)
        if src == "tr" and target == "en" and s.gender_neutral and sent.source:
            text = neutralize(text, sent.source)
        self.cloud_seq += 1
        self.display.add_confirmed(self.cloud_seq, text, target)
        now = time.monotonic()
        self.m_delay_confirmed.add(now - sent.end_mono)
        try:
            self.transcript.append(
                TranscriptRecord(
                    start=self.mono_to_wall(sent.start_mono),
                    end=self.mono_to_wall(now),
                    src=src,
                    tgt=target,
                    source=sent.source,
                    translation=text,
                    engine="gemini",
                    speech_model=s.gemini_model,
                    translation_model=s.gemini_model,
                    mode=s.spoken_language,
                    session=self._session_title(),
                    cut=sent.reason,
                    delay_s=round(now - sent.end_mono, 2),
                    corrections=corrections,
                )
            )
        except Exception:
            log.exception("transcript write")

    def _cloud_tick(self, now: float) -> None:
        """Housekeeping: close sentences after a pause, and switch engines when Gemini fails or recovers."""
        for target, sn in list(self.sentencers.items()):
            for sent in sn.tick(now):
                if self.active == "gemini":
                    self._cloud_show(target, sent)
        if not self.running or self.cloud is None:
            return
        with self._engine_lock:  # the asr loop sees the switch and the replayed audio in order
            cloud = self.cloud
            if cloud is None:
                return
            change = self.failover.update(now, cloud.connected, cloud.last_output, self.cloud_speech_s)
            if change == "local":
                self._to_local(cloud)
            elif change == "gemini":
                self._to_gemini()

    def _to_local(self, cloud: GeminiLive) -> None:
        why = "disconnected" if not cloud.connected else f"no translation for {self.cloud_speech_s:.0f} s of speech"
        self.event("warn", f"Gemini {why}; subtitles continue from the local models")
        for w in self._local_workers():
            if w.parked:
                w.start()  # unloaded to save memory: about 3 s until they are ready
        self.display.drop_interim()
        for sn in self.sentencers.values():
            sn.reset()
        # Start the local engine a few seconds back so the sentence in progress is not lost.
        eng = self.engine
        eng.stream_samples = max(0, eng.stream_samples - sum(len(c) for c, _ in self.ring))
        eng.vad.reset()
        eng.gate.end()
        eng.online.reset(eng.stream_t)
        eng.last_asr_end = eng.online.buffer_end
        eng.utt_lang = None
        for c, t in list(self.ring):
            self.clock = (eng.stream_t + len(c) / SAMPLE_RATE, t)
            eng.process_chunk(c)
        self.cloud_speech_s = 0.0

    def _to_gemini(self) -> None:
        self.engine.end_utterance(flush=True)  # the local sentence in progress still gets shown
        for sn in self.sentencers.values():
            sn.reset()  # Gemini's half sentence would repeat what the local engine showed
        self.display.drop_interim()
        self.event("info", "Gemini is back; subtitles from Gemini again")
        if not self.store.value.gemini_standby:  # unloading waits for the processes: not under the lock
            threading.Thread(target=self._apply_standby, name="standby", daemon=True).start()

    # Housekeeping ---------------------------------------------------------------
    def _housekeeping(self) -> None:
        last_status = 0.0
        last_sched = 0.0
        last_mem = 0.0
        while not self._shutdown.is_set():
            try:
                now = time.monotonic()
                s = self.store.value
                # Clear after silence.
                if not self.display.empty and now > self.display.hold_until:
                    quiet = now - max(self.display.last_change, self._last_speech())
                    if quiet >= s.clear_after_s and not self._mt_confirmed:
                        self.display.clear()
                if self.cloud is not None:
                    self._cloud_tick(now)
                if now - last_sched >= 5.0:
                    last_sched = now
                    self._schedule_tick()
                if now - last_mem >= 30.0:
                    last_mem = now
                    self._memory_check()
                level = self.player.level if (self.source == "file" and self.player) else self.capture.level
                self.publish(
                    "control",
                    {
                        "type": "level",
                        "rms_db": round(level.rms_db, 1),
                        "peak_db": round(level.peak_db, 1),
                        "speech": self._in_speech(),
                    },
                )
                if now - last_status >= 0.5:
                    last_status = now
                    self.publish("control", self.status().to_json())
            except Exception:
                log.exception("housekeeping")
            time.sleep(0.1)

    def _schedule_tick(self) -> None:
        if not self.sessions:
            return
        cur, nxt = sched.current_and_next(self.sessions)
        if (cur, nxt) != (self.current_session, self.next_session) or self._names_for is None:
            self._refresh_names(cur, nxt)
        self.current_session, self.next_session = cur, nxt
        s = self.store.value
        if cur and s.auto_from_schedule and s.schedule_applied_start != cur.start:
            self.store.update(schedule_applied_start=cur.start)
            if cur.spoken != s.spoken_language:
                self.apply_settings({"spoken_language": cur.spoken})
                self.event("info", f"schedule: '{cur.title}' -> spoken language {cur.spoken}")

    def _memory_limit_mb(self, w: WorkerClient) -> float:
        """Restart threshold: the worker's own footprint after loading plus generous headroom,
        so any model size works (no fixed cap); it only catches growth such as a runaway cache."""
        base = w.status.baseline_mb or 2000.0
        return max(base * 1.6, base + 2500.0)

    def _memory_check(self) -> None:
        workers = [("asr", self.asr)] + [(f"mt|{m}", w) for m, w in list(self.mt_pool.items())]
        for key, w in workers:
            w.status.rss_mb = w.rss_mb()
            limit = self._memory_limit_mb(w)
            if w.status.rss_mb and w.status.rss_mb > limit and key not in self._reload:
                self.event(
                    "warn",
                    f"{w.name} worker uses {w.status.rss_mb:.0f} MB (limit {limit:.0f}, "
                    f"{w.status.baseline_mb or 0:.0f} MB after loading); restarting it",
                )
                self._reload.add(key)

    def reload_schedule(self) -> None:
        self.sessions = sched.load()
        if self.cloud is not None:
            self.cloud.instruction = self._gemini_instruction()  # from the next connection
        self._schedule_tick()

    # Status ---------------------------------------------------------------------
    def keeping_up(self) -> bool:
        if self.active == "gemini":
            return self.cloud is not None and self.cloud.connected
        recent_skip = self.last_skip is not None and time.monotonic() - self.last_skip < 60
        mean = self.m_asr_ms.mean() or 0
        return (
            not recent_skip
            and self.backlog_s < 2.0
            and mean / 1000 < 0.9 * max(self.engine.step, 0.2)
            and len(self._mt_confirmed) < 3
        )

    def status(self) -> st.Status:
        def r(x, n=2):
            return None if x is None else round(x, n)

        level = self.player.level if (self.source == "file" and self.player) else self.capture.level
        mic = mic_permission()
        audio_error = self.capture.error
        if self.source == "live" and self.running:
            if mic == "denied":
                audio_error = "Microphone access is denied for this terminal app. Open System Settings > Privacy & Security > Microphone and enable it, then restart."
            elif level.all_zero_s > 3:
                audio_error = "The input delivers pure silence (all zeros). Check microphone permission and the selected device/channel."
            elif self._agc().gain_db > 18:
                audio_error = f"The input is very quiet (boosted by {self._agc().gain_db:.0f} dB). Raise the level on the mixer or audio interface."
        s = self.store.value
        return st.Status(
            run=st.Run(
                running=self.running,
                source="file" if self.source == "file" else "live",
                file=self.file_name,
                file_pos_s=r(self.player.position_s, 1) if self.player else None,
                uptime_s=round(time.monotonic() - self.started_at),
            ),
            audio=st.Audio(
                device=self.capture.active_device["name"] if self.capture.active_device else None,
                error=audio_error,
                mic_permission=mic,
                overflows=self.capture.overflows,
                gain_db=round(self._agc().gain_db, 1),
                speech=self._in_speech(),
            ),
            engine=st.EngineState(
                chosen=s.engine, on_screen=self.active, keeping_up=self.keeping_up(), gemini_key=key_source()
            ),
            delays=st.Delays(
                first_p50=r(self.m_delay_interim.p(0.5)),
                first_p95=r(self.m_delay_interim.p(0.95)),
                final_p50=r(self.m_delay_confirmed.p(0.5)),
                final_p95=r(self.m_delay_confirmed.p(0.95)),
            ),
            local=st.LocalTiming(
                speech_ms=r(self.m_asr_ms.mean(), 0),
                step_s=round(self.engine.step, 2),
                translation_ms=r(self.m_mt_ms.mean(), 0),
                translation_queue=len(self._mt_confirmed),
                backlog_s=round(self.backlog_s, 2),
                skips=self.falling_behind_events,
            ),
            models=[self._model_status(self.asr)] + [self._model_status(w) for w in list(self.mt_pool.values())],
            switching=dict(self.switching),
            gemini=self.cloud.status() if self.cloud else None,
            talk_now=self._talk(self.current_session),
            talk_next=self._talk(self.next_session),
            events=list(self.events)[-12:],
            settings=s.model_dump(),
        )

    def _model_status(self, w: WorkerClient) -> st.ModelStatus:
        """One local model for the panel: which model, what it is doing, measured memory."""
        m = models.get(w.model_key or "")
        if w.parked:
            role: st.Role = "unloaded"
        elif self.active == "gemini":
            role = "backup"
        else:
            role = "in use" if self.running else "idle"
        loading = w.loading_s
        rss = w.rss_mb() if w.alive else None
        directions = [f"{a}>{b}" for a, b in self._mt_dirs(m.key)] if m.job == "translation" else []
        return st.ModelStatus(
            job=m.job,
            key=m.key,
            name=m.name,
            variant=m.variant,
            directions=directions,
            state=w.status.state,
            role=role,
            loading_s=None if loading is None else round(loading),
            memory_gb=None if rss is None else round(rss / 1024, 1),
            restarts=w.status.restarts,
            last_error=w.status.errors[-1] if w.status.errors else None,
        )

    @staticmethod
    def _talk(x: sched.Session | None) -> st.Talk | None:
        if not x:
            return None
        return st.Talk(start=x.start[11:16], end=(x.end or "")[11:16], title=x.title, speaker=x.speaker, lang=x.lang)

    def health(self) -> dict:
        return {
            "status": "ok",
            "running": self.running,
            "uptime_s": round(time.monotonic() - self.started_at),
            "keeping_up": self.keeping_up(),
            "engine": self.active,
            "gemini": "connected" if self.cloud and self.cloud.connected else ("off" if not self.cloud else "down"),
            "models": {w.model_key: w.status.state for w in [self.asr, *self.mt_pool.values()]},
            "delay_confirmed_p50": self.m_delay_confirmed.p(0.5),
        }
