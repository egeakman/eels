"""Streaming policy: LocalAgreement-2 over a growing audio buffer, plus clause segmentation.

All times are in stream seconds (seconds of 16 kHz audio since the pipeline started).
This module has no model or I/O dependencies so it can be unit tested.
"""

from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass, field

import numpy as np

SAMPLE_RATE = 16000
SENTENCE_END = re.compile(r"[.!?…][\"'”)\]]*$")
CLAUSE_END = re.compile(r"[,;:][\"'”)\]]*$")
# A period that usually does not end a sentence: Turkish ordinals ("30." = "30th") and abbreviations.
ABBREVIATIONS = {"m.ö.", "m.s.", "dr.", "prof.", "doç.", "vb.", "vs.", "örn.", "yy.", "mr.", "mrs.", "ms.",
                 "e.g.", "i.e.", "st.", "no.", "vol.", "fig.", "approx."}


def ambiguous_period(token: str) -> bool:
    t = token.strip().lower()
    return bool(re.fullmatch(r"\d+\.", t)) or t in ABBREVIATIONS


@dataclass
class Word:
    start: float
    end: float
    text: str  # includes leading space as Whisper emits it
    prob: float = 1.0
    # True if this was the last word Whisper saw in its audio. Whisper tends to end its output
    # with a period when the audio stops, so sentence punctuation on such a word is unreliable.
    soft_end: bool = False

    @property
    def norm(self) -> str:
        return normalize_token(self.text)


def fold(text: str) -> str:
    """casefold() that maps Turkish dotted capital I to plain i (casefold gives i + combining dot)."""
    return unicodedata.normalize("NFC", text).casefold().replace("i\u0307", "i")


def normalize_token(text: str) -> str:
    return re.sub(r"[^\w']+", "", fold(text.strip()))


def join_words(words: list[Word]) -> str:
    return "".join(w.text for w in words).strip()


def has_content(text: str) -> bool:
    """True if the text has at least one letter or digit ("..." or "♪" alone do not count)."""
    return any(ch.isalnum() for ch in text)


_ELLIPSIS = re.compile(r"\s*(\.{2,}|\u2026)\s*")


def clean_prompt_text(text: str) -> str:
    """Text safe to feed back to Whisper as context: no ellipses (Whisper imitates them and
    can spiral into producing nothing but "..."), no runs of punctuation."""
    text = _ELLIPSIS.sub(" ", text)
    return re.sub(r"\s{2,}", " ", text).strip()


TURKISH_LETTERS = set("ğışçöüĞİŞÇÖÜ")
TURKISH_WORDS = {
    "bir", "ve", "bu", "şu", "için", "ile", "çok", "ne", "de", "da", "mı", "mi", "değil", "var", "yok",
    "gibi", "ama", "şey", "olarak", "daha", "ben", "sen", "biz", "siz", "evet", "hayır", "tamam", "yani",
}


def looks_turkish(text: str) -> bool:
    """Cheap check on a transcript: Turkish letters plus common Turkish function words."""
    words = [normalize_token(w) for w in text.split()]
    if sum(len(w) for w in words) < 8:
        return False
    score = sum(ch in TURKISH_LETTERS for ch in text) + sum(w in TURKISH_WORDS for w in words)
    return score >= 2


# Phrases Whisper is known to produce on silence or noise (subtitle credits, YouTube outros).
HALLUCINATION_PHRASES = [
    "altyazı m.k",
    "altyazı m k",
    "altyazi m.k",
    "izlediğiniz için teşekkürler",
    "izlediğiniz için teşekkür ederim",
    "abone olmayı unutmayın",
    "abone ol",
    "beğenmeyi unutmayın",
    "thanks for watching",
    "thank you for watching",
    "please subscribe",
    "subtitles by",
    "amara.org",
    "transcribed by",
    "www.",
]


def is_hallucination(text: str) -> bool:
    t = fold(text).strip()
    if not t:
        return True
    if any(p in t for p in HALLUCINATION_PHRASES):
        return True
    # Same short phrase repeated many times ("you you you you")
    toks = t.split()
    if len(toks) >= 6 and len(set(toks)) <= max(1, len(toks) // 5):
        return True
    return False


class HypothesisBuffer:
    """LocalAgreement-2: commit the longest common prefix of two consecutive hypotheses."""

    def __init__(self) -> None:
        self.committed_in_buffer: list[Word] = []
        self.buffer: list[Word] = []  # previous hypothesis, uncommitted part
        self.new: list[Word] = []
        self.last_committed_time = 0.0

    def insert(self, words: list[Word]) -> None:
        # Drop words that end before what we already committed.
        new = [w for w in words if w.start > self.last_committed_time - 0.1]
        # Remove n-gram overlap between the end of committed text and the start of new.
        if new and abs(new[0].start - self.last_committed_time) < 1.0 and self.committed_in_buffer:
            cn = len(self.committed_in_buffer)
            nn = len(new)
            for i in range(1, min(cn, nn, 5) + 1):
                tail = [w.norm for w in self.committed_in_buffer[-i:]]
                head = [w.norm for w in new[:i]]
                if tail == head:
                    new = new[i:]
                    break
        self.new = new

    def flush(self) -> list[Word]:
        commit: list[Word] = []
        while self.new and self.buffer:
            if self.new[0].norm != self.buffer[0].norm:
                break
            if len(self.new) == 1:  # last word of this hypothesis: its punctuation may be a buffer-end artefact
                self.new[0].soft_end = True
            commit.append(self.new[0])
            self.last_committed_time = self.new[0].end
            self.buffer.pop(0)
            self.new.pop(0)
        self.buffer = self.new
        self.new = []
        self.committed_in_buffer.extend(commit)
        return commit

    def pop_committed(self, before: float) -> None:
        while self.committed_in_buffer and self.committed_in_buffer[0].end <= before:
            self.committed_in_buffer.pop(0)

    def tentative(self) -> list[Word]:
        return list(self.buffer)


@dataclass
class ASRResult:
    words: list[Word]  # times relative to the start of the audio passed in
    language: str | None = None
    language_prob: float | None = None


class OnlineASR:
    """Holds the audio buffer for the current utterance and applies LocalAgreement."""

    def __init__(self, trim_sentence_s: float = 10.0, trim_hard_s: float = 15.0) -> None:
        self.trim_sentence_s = trim_sentence_s
        self.trim_hard_s = trim_hard_s
        self.reset(0.0)

    def reset(self, offset: float) -> None:
        self.audio = np.zeros(0, dtype=np.float32)
        self.buffer_offset = offset  # stream time of audio[0]
        self.hyp = HypothesisBuffer()
        self.hyp.last_committed_time = offset
        self.committed: list[Word] = []

    @property
    def buffer_end(self) -> float:
        return self.buffer_offset + len(self.audio) / SAMPLE_RATE

    @property
    def duration(self) -> float:
        return len(self.audio) / SAMPLE_RATE

    def append(self, chunk: np.ndarray) -> None:
        self.audio = np.concatenate([self.audio, chunk.astype(np.float32, copy=False)])

    def apply(self, result: ASRResult) -> tuple[list[Word], list[Word]]:
        """Feed one ASR hypothesis for the current buffer. Returns (newly committed, tentative)."""
        words = [
            Word(w.start + self.buffer_offset, w.end + self.buffer_offset, w.text, w.prob)
            for w in result.words
        ]
        self.hyp.insert(words)
        commit = self.hyp.flush()
        self.committed.extend(commit)
        self._maybe_trim()
        return commit, self.hyp.tentative()

    def finish(self) -> list[Word]:
        """Pause or end of utterance: commit everything still tentative."""
        tail = self.hyp.tentative()
        if tail:
            tail[-1].soft_end = True  # committed at a pause: Whisper saw the audio end here
            self.committed.extend(tail)
            self.hyp.committed_in_buffer.extend(tail)
            self.hyp.last_committed_time = tail[-1].end
        self.hyp.buffer = []
        return tail

    def _maybe_trim(self) -> None:
        if self.duration >= self.trim_hard_s + 2.0 and not self.hyp.committed_in_buffer:
            # Nothing has been agreed on for a long time (noise, music, or Whisper stuck):
            # drop the oldest audio so the buffer cannot grow without limit.
            self.trim_to(self.buffer_end - self.trim_sentence_s / 2)
            self.hyp.buffer = []
            self.hyp.last_committed_time = self.buffer_offset
            return
        if self.duration < self.trim_sentence_s or not self.hyp.committed_in_buffer:
            return
        cut = None
        for w in reversed(self.hyp.committed_in_buffer):
            if SENTENCE_END.search(w.text.strip()):
                cut = w.end
                break
        if cut is None and self.duration >= self.trim_hard_s:
            cut = self.hyp.committed_in_buffer[-1].end
        if cut is not None and cut > self.buffer_offset:
            self.trim_to(cut)

    def trim_to(self, t: float) -> None:
        n = int(round((t - self.buffer_offset) * SAMPLE_RATE))
        n = max(0, min(n, len(self.audio)))
        self.audio = self.audio[n:]
        self.buffer_offset += n / SAMPLE_RATE
        self.hyp.pop_committed(self.buffer_offset)

    def prompt_text(self, max_chars: int = 200) -> str:
        """Committed text from before the current buffer, for Whisper's initial prompt."""
        prev = [w for w in self.committed if w.end <= self.buffer_offset]
        return join_words(prev)[-max_chars:]


@dataclass
class Clause:
    words: list[Word]
    reason: str

    @property
    def text(self) -> str:
        # Hesitation ellipses attached to words ("So...") stay; punctuation-only words were
        # already dropped, so a clause of only "..." never gets here with content.
        return join_words(self.words)

    @property
    def start(self) -> float:
        return self.words[0].start

    @property
    def end(self) -> float:
        return self.words[-1].end


@dataclass
class ClauseSegmenter:
    """Groups committed words into whole sentences for translation.

    Translating fragments loses the context a sentence needs (Turkish puts the verb last,
    and "the Kahoot" / "Quiz." translate badly apart), so the final text is cut only at:
    sentence-ending punctuation from Whisper, a gap of gap_s with no new words, or a safety
    cap of max_words / max_s, where it cuts at the last comma if there is one.
    The live preview shows the sentence so far while it grows.
    """

    max_words: int = 30
    max_s: float = 12.0
    gap_s: float = 1.0
    pending: list[Word] = field(default_factory=list)
    pending_since: float | None = None  # clock time the first pending word arrived
    last_add: float | None = None  # clock time the last word arrived

    def add(self, words: list[Word], now: float | None = None) -> list[Clause]:
        now = time.monotonic() if now is None else now
        out: list[Clause] = []
        for w in words:
            if not self.pending:
                self.pending_since = now
            elif self.pending[-1].soft_end and SENTENCE_END.search(self.pending[-1].text.strip()):
                # The speaker continued after a period Whisper added at a pause: not a sentence end.
                prev = self.pending[-1]
                prev.text = re.sub(r"[.\u2026]+([\"'\u201d)\]]*)$", r"\1", prev.text.rstrip())
            self.pending.append(w)
            self.last_add = now
            if SENTENCE_END.search(w.text.strip()) and not w.soft_end and not ambiguous_period(w.text):
                out.append(self._take("sentence"))
            elif len(self.pending) >= self.max_words:
                out.append(self._take_at_comma("max_words"))
        return out

    def check_age(self, now: float | None = None, quiet_from: float | None = None) -> Clause | None:
        """quiet_from: when speech stopped (the engine knows; defaults to the last word's arrival)."""
        now = time.monotonic() if now is None else now
        if not self.pending:
            return None
        quiet = quiet_from if quiet_from is not None else (self.last_add or 0.0)
        if now - quiet >= self.gap_s:
            return self._take("gap")
        if self.pending_since is not None and now - self.pending_since >= self.max_s:
            return self._take_at_comma("max_time")
        return None

    def flush(self, reason: str = "flush") -> Clause | None:
        if not self.pending:
            return None
        return self._take(reason)

    def _take_at_comma(self, reason: str) -> Clause:
        """Cut after the last comma if that leaves at least 4 words on each side."""
        for i in range(len(self.pending) - 4, 3, -1):
            if CLAUSE_END.search(self.pending[i - 1].text.strip()):
                head, tail = self.pending[:i], self.pending[i:]
                self.pending = head
                clause = self._take(reason)
                self.pending = tail
                self.pending_since = self.last_add
                return clause
        return self._take(reason)

    def _take(self, reason: str) -> Clause:
        clause = Clause(self.pending, reason)
        self.pending = []
        self.pending_since = None
        return clause


def split_sentences(text: str) -> list[str]:
    """Split a subtitle into sentences at . ! ? (and ellipses), but not after abbreviations or
    Turkish ordinals ("Mr. Barnes", "30. yılında"). For sentence-level translators (Opus-MT),
    which silently drop all but one sentence when given several."""
    pieces: list[str] = []
    current: list[str] = []
    for token in text.split():
        current.append(token)
        if SENTENCE_END.search(token) and not ambiguous_period(token):
            pieces.append(" ".join(current))
            current = []
    if current:
        pieces.append(" ".join(current))
    return pieces
