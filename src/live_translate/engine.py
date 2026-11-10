"""Speech-side state machine shared by the live pipeline and the benchmark.

Feeds 16 kHz audio through VAD, decides when to run ASR, applies LocalAgreement,
handles pauses and utterance ends, picks the language, and cuts clauses.
It does not know about threads, workers or wall-clock time: the caller passes an
ASR function and a clock, so the benchmark can drive it with simulated time.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from .config import Settings
from .streaming import (
    SAMPLE_RATE,
    ASRResult,
    Clause,
    ClauseSegmenter,
    OnlineASR,
    Word,
    clean_prompt_text,
    has_content,
    is_hallucination,
    join_words,
    looks_turkish,
    normalize_token,
)
from .vad import AutoGain, SileroVAD, SpeechGate

# The program hint (hints.py) carries the vocabulary; this is the minimal fallback for runs
# without a schedule. A term list, not a sentence: Whisper treats its prompt as the preceding
# transcript, and a sentence like "We use Python, ..." got continued as if spoken.
ASR_PROMPT_VOCAB_BY_LANG = {"en": "Python Pizza Istanbul.", "tr": "Python Pizza İstanbul."}

# asr_fn(audio, language or None, prompt) -> {"words": [[start, end, text, prob]], "language", "language_prob", "ms"}
AsrFn = Callable[[np.ndarray, "str | None", str], "dict | None"]


def is_prompt_fragment(text: str, prompt: str) -> bool:
    """A subtitle that is only 1-2 pieces of names from the prompt ("PyI" from "PyIstanbul"):
    Whisper writes these in quiet moments. Full names said on their own ("Django.") are kept."""
    words = [normalize_token(t) for t in text.split()]
    words = [w for w in words if w]
    if not words or len(words) > 2:
        return False
    names = {normalize_token(t) for t in prompt.split()}
    names = {n for n in names if len(n) >= 6}
    for w in words:
        if w in names or len(w) < 3 or not any(n.startswith(w) for n in names):
            return False
    return True


def drop_prompt_echo(words: list[Word], prompt: str) -> list[Word]:
    """At the start of an utterance Whisper sometimes "continues" its prompt, writing words from
    it that were never spoken. Drop a leading run of 3+ words that appears verbatim in the prompt."""
    if len(words) < 3 or not prompt:
        return words
    folded_prompt = " ".join(normalize_token(t) for t in prompt.split())
    n = 0
    for k in range(3, min(len(words), 12) + 1):
        if " ".join(w.norm for w in words[:k]) in folded_prompt:
            n = k
        else:
            break
    return words[n:]


def other(lang: str) -> str:
    return "tr" if lang == "en" else "en"


@dataclass
class Interim:
    text: str
    lang: str
    end_t: float  # stream seconds of the last word
    base: int  # clause counter when produced


class StreamEngine:
    def __init__(
        self,
        settings: Callable[[], Settings],
        asr_fn: AsrFn,
        on_clause: Callable[[Clause, str, int], None],
        on_interim: Callable[[Interim], None] | None = None,
        clock: Callable[[], float] | None = None,
        title: Callable[[str], str] = lambda lang: "",
    ):
        import time

        self.settings = settings
        self.asr_fn = asr_fn
        self.on_clause = on_clause
        self.on_interim = on_interim
        self.clock = clock or time.monotonic
        self.title = title
        s = settings()
        self.vad = SileroVAD()
        self.agc = AutoGain()
        self.gate = SpeechGate()
        self.online = OnlineASR(trim_sentence_s=9.0, trim_hard_s=13.5)
        self.segmenter = ClauseSegmenter(s.sentence_max_words, s.sentence_max_s, s.sentence_gap_s)
        self.pending_lang: str | None = None  # language of the words waiting in the segmenter
        self._last_dispatched: tuple[str, float] = ("", -1e9)
        self._last_prompt = ""
        self.stream_samples = 0
        self.utt_lang: str | None = None
        self.last_lang = s.spoken_language if s.spoken_language != "auto" else "en"
        self.last_asr_end = 0.0
        self.pause_done = False
        self.history: deque[Word] = deque(maxlen=80)
        self.clause_seq = 0
        self.step = s.asr_step_s
        self.asr_ms: deque[float] = deque(maxlen=20)
        self.last_speech = 0.0  # clock time of the last speech frame
        self.empty_speech_s = 0.0  # audio seconds of speech with no recognized words in a row

    @property
    def stream_t(self) -> float:
        return self.stream_samples / SAMPLE_RATE

    def sync_settings(self) -> None:
        s = self.settings()
        self.segmenter.max_words = s.sentence_max_words
        self.segmenter.max_s = s.sentence_max_s
        self.segmenter.gap_s = s.sentence_gap_s

    def language_changed(self, spoken: str) -> None:
        self.utt_lang = None
        if spoken != "auto":
            self.last_lang = spoken

    # Audio ------------------------------------------------------------------------
    def process_chunk(self, chunk: np.ndarray) -> None:
        """VAD and gate only; ASR runs from maybe_run_asr() so callers can drain a backlog first."""
        self.stream_samples += len(chunk)
        s = self.settings()
        if s.auto_gain:
            chunk = self.agc.process(chunk)
        for frame, prob in self.vad.process(chunk):
            was_in_speech = self.gate.in_speech
            ev, feed = self.gate.update(frame, prob)
            if ev == "start":
                start_t = self.stream_t - sum(len(f) for f in feed) / SAMPLE_RATE
                if not self.online.duration:
                    self.online.reset(max(0.0, start_t))
                    self.last_asr_end = self.online.buffer_offset
                self.pause_done = False
            for f in feed:
                self.online.append(f)
            if self.gate.in_speech:
                if self.gate.silence_s == 0.0:
                    self.last_speech = self.clock()
                    self.pause_done = False
                if was_in_speech and self.gate.silence_s >= s.pause_flush_s and not self.pause_done:
                    self.pause()
                if self.gate.silence_s >= s.utterance_end_s:
                    self.end_utterance()

    def maybe_run_asr(self) -> None:
        if not self.gate.in_speech or self.online.duration < 0.3:
            return
        s = self.settings()
        mean_ms = sum(self.asr_ms) / len(self.asr_ms) if self.asr_ms else 0.0
        # Run at most every asr_step_s, and never let one run take more than ~60% of a step.
        self.step = max(s.asr_step_s, mean_ms / 1000 / 0.6)
        if self.online.buffer_end - self.last_asr_end >= self.step:
            self.run_asr()

    def check_age(self) -> None:
        if self.gate.in_speech and not self.pause_done:
            # Still speaking, or the words before this pause are not confirmed yet: never cut now.
            clause = self.segmenter.check_age(self.clock(), quiet_from=self.clock())
        else:
            # The sentence gap counts from when speech stopped (not from when words were confirmed).
            clause = self.segmenter.check_age(self.clock(), quiet_from=self.last_speech or None)
        if clause:
            self._dispatch(clause)

    # ASR ----------------------------------------------------------------------------
    # Whisper keeps only the last ~223 prompt tokens (it drops the start). About 3.5 characters
    # per token for this mix of English, Turkish and names, so stay under ~700 characters.
    PROMPT_HINT_CHARS = 1000  # the hint is already cut to a token budget (hints.py); this is a backstop
    PROMPT_HISTORY_CHARS = 120

    def _prompt(self) -> str:
        prev = [w for w in self.history if w.end <= self.online.buffer_offset + 0.01]
        hist = clean_prompt_text(join_words(prev))[-self.PROMPT_HISTORY_CHARS :]
        lang = self.utt_lang or self.last_lang
        hint = self.title(lang)[: self.PROMPT_HINT_CHARS]
        vocab = ASR_PROMPT_VOCAB_BY_LANG.get(lang, ASR_PROMPT_VOCAB_BY_LANG["en"])
        # Recent speech goes last: it is closest to the audio and Whisper weighs it most.
        return " ".join(p for p in (hint, vocab, hist) if p)

    def run_asr(self) -> list[Word] | None:
        spoken = self.settings().spoken_language
        lang = spoken if spoken != "auto" else self.utt_lang
        if spoken == "auto" and lang is None and self.online.duration < 1.5:
            return None  # need a bit of audio to detect the language
        new_audio_s = self.online.buffer_end - self.last_asr_end
        self._last_prompt = self._prompt()
        res = self.asr_fn(self.online.audio, lang, self._last_prompt)
        if res is None:
            return None
        self.last_asr_end = self.online.buffer_end
        self.asr_ms.append(res.get("ms", 0.0))
        if spoken == "auto" and lang is None:
            detected, prob = res.get("language") or self.last_lang, res.get("language_prob") or 1.0
            if detected != self.last_lang and prob < 0.6:
                detected = self.last_lang  # not sure enough to switch direction
            self.utt_lang = self.last_lang = detected
        elif lang:
            self.utt_lang = lang
        # Punctuation-only "words" ("...", "♪") never become subtitles or context.
        words = [Word(*w) for w in res["words"] if has_content(w[2])]
        if not self.online.committed and not self.online.hyp.buffer:
            words = drop_prompt_echo(words, self._last_prompt)  # start of an utterance
        if words and is_hallucination(join_words(words)):
            words = []
        if spoken == "auto" and self.utt_lang == "en" and looks_turkish(join_words(words)):
            # Detection said English but the words are clearly Turkish: switch for this utterance.
            self.utt_lang = self.last_lang = "tr"
        if self.segmenter.pending and self.pending_lang and self.utt_lang and self.utt_lang != self.pending_lang:
            self.flush_sentence("language")  # never mix two languages in one subtitle
        # Self-healing: a long stretch of speech with no words at all usually means Whisper is
        # stuck on its own context. Clear the context so the next pass starts fresh.
        self.empty_speech_s = 0.0 if words else self.empty_speech_s + new_audio_s
        if self.empty_speech_s >= 8.0:
            self.history.clear()
            self.empty_speech_s = 0.0
        committed, tentative = self.online.apply(ASRResult(words))
        self._after_commit(committed, tentative)
        return committed

    def pause(self) -> None:
        """Short pause: the words before it are final; cut a clause."""
        self.pause_done = True
        if self.online.buffer_end - self.last_asr_end > 0.05:
            self.run_asr()
        tail = self.online.finish()
        self._after_commit(tail, [])
        # The sentence is not cut here: it ends at punctuation or after sentence_gap_s (check_age).

    def flush_sentence(self, reason: str = "flush") -> None:
        clause = self.segmenter.flush(reason)
        if clause:
            self._dispatch(clause)

    def end_utterance(self, flush: bool = False) -> None:
        """Speech stopped: commit what we have. flush=True also closes the sentence (stop, skip)."""
        if self.gate.in_speech and not self.pause_done and self.online.duration > 0.3:
            self.pause()
        if flush:
            self.flush_sentence("end")
        self.gate.end()
        self.online.reset(self.stream_t)
        self.last_asr_end = self.online.buffer_end
        self.utt_lang = None
        self.pause_done = False

    def _after_commit(self, committed: list[Word], tentative: list[Word]) -> None:
        self.history.extend(committed)
        if committed and not self.segmenter.pending:
            self.pending_lang = self.utt_lang or self.last_lang
        for clause in self.segmenter.add(committed, self.clock()):
            self._dispatch(clause)
        if self.on_interim and self.settings().interim:
            words = self.segmenter.pending + tentative
            text = join_words(words)
            if has_content(text) and self.utt_lang and not is_prompt_fragment(text, self._last_prompt):
                self.on_interim(Interim(text, self.utt_lang, words[-1].end, self.clause_seq))

    def _dispatch(self, clause: Clause) -> None:
        if not has_content(clause.text) or is_hallucination(clause.text):
            return
        if is_prompt_fragment(clause.text, self._last_prompt):
            return
        key = normalize_token(clause.text.replace(" ", "_"))
        if key and key == self._last_dispatched[0] and clause.start - self._last_dispatched[1] < 15.0:
            return  # Whisper repeated the previous sentence (a known prompt-induced artefact)
        self._last_dispatched = (key, clause.end)
        self.clause_seq += 1
        self.on_clause(clause, self.pending_lang or self.utt_lang or self.last_lang, self.clause_seq)
