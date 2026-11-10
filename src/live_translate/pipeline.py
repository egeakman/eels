"""The live pipeline: audio -> VAD -> streaming ASR -> clauses -> MT -> overlay + transcript.

Threads:
  audio consumer (audio.py)  -> self._audio_q
  asr-loop                   VAD, gate, LocalAgreement, clause segmentation, ASR worker calls
  mt-loop                    translation worker calls (confirmed clauses first, then latest interim)
  housekeeping               clear-after-silence, schedule auto-switch, status publishing
"""

from __future__ import annotations

import logging
import queue
import statistics
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np

from . import hints
from . import schedule as sched
from .audio import AudioCapture, DeviceWatcher, FilePlayer, list_input_devices, load_audio_file, mic_permission
from .config import Settings, SettingsStore, mt_for
from .engine import Interim, StreamEngine, other
from .streaming import SAMPLE_RATE, Clause
from .transcript import TranscriptLog
from .gender import neutralize
from .names import NameCorrector
from .translate import check_translation
from .workers import WorkerClient, WorkerError

log = logging.getLogger(__name__)

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
    model: str = ""  # translation model that produced the text
    corrections: list = field(default_factory=list)  # (heard, corrected) name fixes


class Display:
    """What the overlay shows. All mutations go through here and are broadcast as a full snapshot."""

    def __init__(self, publish: Publish, settings: Callable[[], Settings]):
        self.publish = publish
        self.settings = settings
        self.segments: deque[dict] = deque(maxlen=8)
        self.interim: dict | None = None
        self.last_change = time.monotonic()
        self.hold_until = 0.0  # test text stays up until this time
        self._lock = threading.Lock()

    def snapshot(self) -> dict:
        s = self.settings()
        return {
            "type": "state",
            "visible": s.visible,
            "segments": list(self.segments),
            "interim": self.interim["text"] if self.interim else "",
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
            if self.segments and self.segments[-1]["lang"] != lang:
                self.segments.clear()  # direction changed: start fresh
            self.segments.append({"id": seq, "text": text, "lang": lang})
            if self.interim and self.interim["base"] <= seq:
                self.interim = None
            self.last_change = time.monotonic()
        self.push()

    def set_interim(self, base: int, text: str, lang: str, current_base: int) -> bool:
        with self._lock:
            if base != current_base:
                return False  # a clause was cut since this was requested; it would duplicate text
            now = time.monotonic()
            old = self.interim
            if old and old["base"] == base:
                a, b = old["text"].split(), text.split()
                only_last_word = len(a) == len(b) and a[:-1] == b[:-1]
                if text == old["text"] or (only_last_word and now - old["t"] < 0.5):
                    return False
            if self.segments and self.segments[-1]["lang"] != lang:
                self.segments.clear()
            self.interim = {"base": base, "text": text, "t": now, "lang": lang}
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
            self.segments.append({"id": -2, "text": TEST_LINES["en"], "lang": "en"})
            self.segments.append({"id": -1, "text": TEST_LINES["tr"], "lang": "tr"})
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

        self.asr = WorkerClient("asr", "live_translate.asr:create", self._asr_spec(s))
        # One translation worker per distinct model; each direction uses mt_for(settings, src, tgt).
        self.mt_pool: dict[str, WorkerClient] = {}
        self.mt_extra: dict = {}  # extra translator options (the benchmark sets beam_size etc.)

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
        self.switching: dict[str, str] = {}  # kind -> model being loaded for a hot swap
        self._engine_lock = threading.RLock()
        self._shutdown = threading.Event()

        self.m_asr_ms = Rolling()
        self.m_mt_ms = Rolling()
        self.m_delay_interim = Rolling()
        self.m_delay_confirmed = Rolling()
        self.started_at = time.monotonic()
        self.events: deque[dict] = deque(maxlen=30)

        self._threads = [
            threading.Thread(target=self._asr_loop, name="asr-loop", daemon=True),
            threading.Thread(target=self._mt_loop, name="mt-loop", daemon=True),
            threading.Thread(target=self._housekeeping, name="housekeeping", daemon=True),
        ]

    # Lifecycle ------------------------------------------------------------------
    def boot(self) -> None:
        """Start workers (model loading) and background threads. Audio starts with start()."""
        self.asr.start()
        for model in self._mt_models_in_use():
            self._mt_add(model).start()
        self.watcher.start()
        for t in self._threads:
            t.start()

    def shutdown(self) -> None:
        self._shutdown.set()  # threads exit and must not respawn workers afterwards
        self.stop()
        self.capture.close()
        self.watcher.stop()
        self.asr.stop()
        for w in list(self.mt_pool.values()):
            w.stop()

    def start(self) -> None:
        if self.source == "live":
            self.capture.start()
        self.running = True
        self.event("info", "started")

    def stop(self) -> None:
        self.running = False
        self.capture.stop()
        if self.player:
            self.player.stop()
            self.player = None
        self._engine_call(lambda: self.engine.end_utterance(flush=True))
        self.event("info", "stopped")

    def play_file(self, path: str, speed: float = 1.0) -> None:
        audio = load_audio_file(path)
        self.capture.stop()
        if self.player:
            self.player.stop()
        self.source = "file"
        self.file_name = str(path)
        self.player = FilePlayer(audio, self._on_audio, speed=speed, on_done=lambda: self.event("info", f"file finished: {path}"))
        self.running = True
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
        self.events.append({"t": time.strftime("%H:%M:%S"), "level": level, "msg": msg})
        getattr(log, "warning" if level == "warn" else level if level in ("info", "error") else "info")(msg)

    # Settings -------------------------------------------------------------------
    @staticmethod
    def _asr_spec(s: Settings) -> dict:
        return {"model": s.asr_model, "audio_ctx": s.asr_audio_ctx}

    def apply_settings(self, changes: dict) -> Settings:
        changes = dict(changes)
        asr_change = {k: changes.pop(k) for k in ("asr_model", "asr_audio_ctx") if k in changes}
        mt_changes = {k: changes.pop(k) for k in ("mt_model", "mt_model_en_tr", "mt_model_tr_en") if k in changes}
        if asr_change:
            cur = self.store.value
            self.switch_model("asr", asr_change.get("asr_model", cur.asr_model), asr_change.get("asr_audio_ctx", cur.asr_audio_ctx))
        for key, model in mt_changes.items():
            if model:
                self.switch_model({"mt_model": "mt", "mt_model_en_tr": "mt_en_tr", "mt_model_tr_en": "mt_tr_en"}[key], model)
        old = self.store.value
        s = self.store.update(**changes)
        if "device_name" in changes or "channel" in changes:
            self.capture.configure(s.device_name, s.channel)
        if s.spoken_language != old.spoken_language:
            self.engine.language_changed(s.spoken_language)
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
        return list(dict.fromkeys(mt_for(s, a, b) for a, b in self.DIRECTIONS))

    def _mt_add(self, model: str) -> WorkerClient:
        w = WorkerClient("mt", "live_translate.translate:create", {**self.mt_extra, "model": model})
        self.mt_pool[model] = w
        return w

    def _mt_prune(self) -> None:
        """Stop workers no direction uses any more."""
        used = set(self._mt_models_in_use())
        for model in [m for m in self.mt_pool if m not in used]:
            self.mt_pool.pop(model).stop()

    @property
    def mt_ready(self) -> bool:
        return bool(self.mt_pool) and all(w.ready for w in self.mt_pool.values())

    def _mt_dirs(self, model: str) -> str:
        s = self.store.value
        return ", ".join(f"{a.upper()}→{b.upper()}" for a, b in self.DIRECTIONS if mt_for(s, a, b) == model)

    # Hot swap -----------------------------------------------------------------------
    MT_KINDS = {"mt": DIRECTIONS, "mt_en_tr": (("en", "tr"),), "mt_tr_en": (("tr", "en"),)}

    def switch_model(self, kind: str, model: str, audio_ctx: str | None = None) -> None:
        """Load a new model in a fresh worker while the current one keeps working, then swap.

        kind: "asr", "mt" (both translation directions), "mt_en_tr" or "mt_tr_en".
        Subtitles do not pause. If the new model fails to load, the current one stays.
        The setting is saved only after the swap succeeded.
        """
        if kind in self.switching:
            self.event("warn", f"already switching the {kind} model; wait for it to finish")
            return
        if kind == "asr":
            spec = {"model": model, "audio_ctx": audio_ctx or "750"}
            if self.asr.spec == spec:
                return
        else:
            s = self.store.value
            if all(mt_for(s, a, b) == model for a, b in self.MT_KINDS[kind]):
                return
            spec = {**self.mt_extra, "model": model}
            if model in self.mt_pool and self.mt_pool[model].ready:
                self._mt_assign(kind, model)  # already loaded for the other direction
                return
        self.switching[kind] = model
        what = "speech recognition" if kind == "asr" else "translation" + ("" if kind == "mt" else f" ({kind[3:5].upper()}→{kind[6:].upper()})")
        self.event("info", f"loading {model} for {what}; the current model keeps running until it is ready")
        threading.Thread(target=self._switch_worker, args=(kind, spec), name=f"switch-{kind}", daemon=True).start()

    def _mt_assign(self, kind: str, model: str) -> None:
        with self._mt_client_lock:
            if kind == "mt":
                self.store.update(mt_model=model, mt_model_en_tr=None, mt_model_tr_en=None)
            else:
                self.store.update(**{f"mt_model_{kind[3:]}": model})
            self._mt_prune()
        self.m_mt_ms.v.clear()
        self.event("info", f"now using {model} for translation ({self._mt_dirs(model)})")

    def _switch_worker(self, kind: str, spec: dict) -> None:
        factory = "live_translate.asr:create" if kind == "asr" else "live_translate.translate:create"
        new = WorkerClient("asr" if kind == "asr" else "mt", factory, spec)
        try:
            new.start()
            ok = new.wait_ready(timeout=900)
            if not ok or self._shutdown.is_set():
                err = new.status.errors[-1]["msg"] if new.status.errors else "did not load"
                new.stop()
                self.event("error", f"could not load {spec['model']} ({err}); keeping the current model")
                return
            new.status.restarts = 0
            if kind == "asr":
                with self._engine_lock:  # no call is in flight on the old worker while we swap
                    old, self.asr = self.asr, new
                    self.engine.asr_ms.clear()  # step timing belongs to the old model
                    self.m_asr_ms.v.clear()
                old.stop()
                self.store.update(asr_model=spec["model"], asr_audio_ctx=spec["audio_ctx"])
                self.event("info", f"now using {spec['model']} (window {spec['audio_ctx']})")
            else:
                with self._mt_client_lock:
                    previous = self.mt_pool.get(spec["model"])
                    self.mt_pool[spec["model"]] = new
                if previous is not None:
                    previous.stop()
                self._mt_assign(kind, spec["model"])
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
            res = self.asr.call({"op": "transcribe", "audio": audio, "language": lang, "prompt": prompt},
                                timeout=max(8.0, 2 * len(audio) / SAMPLE_RATE))
        except WorkerError as exc:
            self.event("error", str(exc))
            return None
        self.m_asr_ms.add(res["ms"])
        return res

    def _on_interim(self, it: Interim) -> None:
        text, _ = self._names.correct(it.text)
        job = MTJob("interim", text, it.lang, other(it.lang), it.base,
                    end_mono=self.stream_to_mono(it.end_t), session=self._session_title())
        with self._mt_lock:
            self._mt_interim = job
            self._mt_lock.notify()

    def _session_title(self) -> str | None:
        return self.current_session.title if self.current_session else None

    def _on_clause(self, clause: Clause, src: str, seq: int) -> None:
        text, corrections = self._names.correct(clause.text)  # misheard program names
        job = MTJob("confirmed", text, src, other(src), seq, clause.start, clause.end,
                    self.stream_to_mono(clause.end), session=self._session_title(), reason=clause.reason,
                    corrections=corrections)
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
        worker = self.mt_pool.get(mt_for(self.store.value, job.src, job.tgt))
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
        model = mt_for(self.store.value, job.src, job.tgt)
        worker = self.mt_pool.get(model)
        if worker is None:
            return None
        job.model = model
        req = {"text": job.text, "src": job.src, "tgt": job.tgt,
               "protect": hints.protected_names(self.sessions)}  # program names stay untranslated
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
            self.transcript.append({
                "start": self.mono_to_wall(self.stream_to_mono(job.start_t)),
                "end": self.mono_to_wall(job.end_mono),
                "src": job.src,
                "tgt": job.tgt,
                "mode": s.spoken_language,
                "session": job.session,
                "source": job.text,
                "translation": text,
                "fallback": fallback,
                "corrections": job.corrections,
                "cut": job.reason,
                "delay_s": round(time.monotonic() - job.end_mono, 2),
                "asr_model": s.asr_model,
                "mt_model": job.model or mt_for(s, job.src, job.tgt),
            })
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
                    quiet = now - max(self.display.last_change, self.engine.last_speech)
                    if quiet >= s.clear_after_s and not self._mt_confirmed:
                        self.display.clear()
                if now - last_sched >= 5.0:
                    last_sched = now
                    self._schedule_tick()
                if now - last_mem >= 30.0:
                    last_mem = now
                    self._memory_check()
                level = self.player.level if (self.source == "file" and self.player) else self.capture.level
                self.publish("control", {"type": "level", "rms_db": round(level.rms_db, 1), "peak_db": round(level.peak_db, 1),
                                         "speech": self.engine.gate.in_speech})
                if now - last_status >= 0.5:
                    last_status = now
                    self.publish("control", self.status())
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
                self.event("warn", f"{w.name} worker uses {w.status.rss_mb:.0f} MB (limit {limit:.0f}, "
                                   f"{w.status.baseline_mb or 0:.0f} MB after loading); restarting it")
                self._reload.add(key)

    def reload_schedule(self) -> None:
        self.sessions = sched.load()
        self._schedule_tick()

    # Status ---------------------------------------------------------------------
    def keeping_up(self) -> bool:
        recent_skip = self.last_skip is not None and time.monotonic() - self.last_skip < 60
        mean = self.m_asr_ms.mean() or 0
        return not recent_skip and self.backlog_s < 2.0 and mean / 1000 < 0.9 * max(self.engine.step, 0.2) and len(self._mt_confirmed) < 3

    def status(self) -> dict:
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
            elif self.engine.agc.gain_db > 18:
                audio_error = f"The input is very quiet (boosted by {self.engine.agc.gain_db:.0f} dB). Raise the level on the mixer or audio interface."
        s = self.store.value
        return {
            "type": "status",
            "running": self.running,
            "source": self.source,
            "file": self.file_name,
            "file_pos": r(self.player.position_s, 1) if self.player else None,
            "device": self.capture.active_device["name"] if self.capture.active_device else None,
            "audio_error": audio_error,
            "mic_permission": mic,
            "overflows": self.capture.overflows,
            "gain_db": round(self.engine.agc.gain_db, 1),
            "speech": self.engine.gate.in_speech,
            "utt_lang": self.engine.utt_lang,
            "last_lang": self.engine.last_lang,
            "keeping_up": self.keeping_up(),
            "backlog_s": r(self.backlog_s),
            "skips": self.falling_behind_events,
            "asr_ms": r(self.m_asr_ms.mean(), 0),
            "asr_step_s": r(self.engine.step),
            "mt_ms": r(self.m_mt_ms.mean(), 0),
            "mt_queue": len(self._mt_confirmed),
            "delay_interim_p50": r(self.m_delay_interim.p(0.5)),
            "delay_interim_p95": r(self.m_delay_interim.p(0.95)),
            "delay_confirmed_p50": r(self.m_delay_confirmed.p(0.5)),
            "delay_confirmed_p95": r(self.m_delay_confirmed.p(0.95)),
            "workers": [{**self.asr.status.as_dict(), "label": "Speech recognition"}] + [
                {**w.status.as_dict(), "label": f"Translation {self._mt_dirs(m)}", "model": m}
                for m, w in list(self.mt_pool.items())],
            "switching": dict(self.switching),
            "session": self._session_dict(self.current_session),
            "next_session": self._session_dict(self.next_session),
            "events": list(self.events)[-12:],
            "uptime_s": round(time.monotonic() - self.started_at),
            "settings": s.model_dump(),
        }

    @staticmethod
    def _session_dict(x: sched.Session | None) -> dict | None:
        if not x:
            return None
        return {"start": x.start[11:16], "end": (x.end or "")[11:16], "title": x.title, "speaker": x.speaker, "lang": x.lang}

    def health(self) -> dict:
        return {
            "status": "ok",
            "running": self.running,
            "uptime_s": round(time.monotonic() - self.started_at),
            "keeping_up": self.keeping_up(),
            "asr": self.asr.status.state,
            "mt": "ready" if self.mt_ready else ", ".join(w.status.state for w in self.mt_pool.values()),
            "delay_confirmed_p50": self.m_delay_confirmed.p(0.5),
        }

