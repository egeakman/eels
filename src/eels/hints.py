"""Program-derived vocabulary: the Whisper hint and the names protected from translation.

Whisper keeps only ~223 prompt tokens, so the hint is ordered by importance (the engine cuts the
end): the current and next talk with their speakers and terms, names that come up all day, then
all speakers. It is written as short sentences in the spoken language, because Whisper copies the
style of its prompt (a long bare list of capitalised names made it Title-Case Turkish).
"""

from __future__ import annotations

import json
from functools import lru_cache

from .config import DATA_DIR


@lru_cache(maxsize=1)
def _terms() -> dict:
    return json.loads((DATA_DIR / "program_terms.json").read_text(encoding="utf-8"))


def talk_terms(title: str | None) -> list[str]:
    title = (title or "").lower()
    out: list[str] = []
    for key, names in _terms()["talks"].items():
        if key.lower() in title:
            out += names
    return list(dict.fromkeys(out))


def organizers() -> list[str]:
    return list(_terms().get("organizers", {}).get("names", []))


def sponsors() -> list[str]:
    return list(_terms().get("sponsors", {}).get("names", []))


def always_names() -> list[str]:
    """Names that can come up in any talk: tools, the community, the sponsors."""
    return list(dict.fromkeys(_terms()["always"] + sponsors()))


def speakers(sessions) -> list[str]:
    return list(dict.fromkeys(s.speaker for s in sessions if s.speaker and len(s.speaker) < 60))


def protected_names(sessions) -> list[str]:
    """Every name in the program: never translated ("Celery" is not "kereviz", "Flask" not "şişe")."""
    names = always_names() + organizers()
    for terms in _terms()["talks"].values():
        names += terms
    return list(dict.fromkeys(names + speakers(sessions)))


def glossary_tr() -> dict[str, str]:
    return {k: v for k, v in _terms().get("glossary_tr", {}).items() if not k.startswith("_")}


def gemini_instruction(sessions, extra: str = "") -> str:
    """System instruction for Gemini Live Translate: the whole day's program. Measured 2026-11-10:
    accepted, not billed (usage stays at the audio tokens), and it makes Gemini spell program
    names right ("PyCon" instead of "Pycon" or "Pi günümüzü"). Real Turkish terms in a glossary are
    followed ("call for proposals" -> "konuşma başvuruları"); a made-up word was not."""
    glossary = ", ".join(f"{en} = {tr}" for en, tr in glossary_tr().items())
    info = _terms().get("sponsors", {})
    names = [("fal (the company fal.ai)" if n == "fal.ai" else n) for n in info.get("names", [])]
    sponsor_line = f"The event's sponsors: {', '.join(names)}. " if names else ""
    if organizers():
        sponsor_line += f"The organizers: {', '.join(organizers())}. "
    if info.get("venue"):
        sponsor_line += f"The venue is {info['venue']}. "
    talks = [
        f"{s.title} ({s.speaker})" if s.speaker and len(s.speaker) < 60 else s.title
        for s in sessions
        if s.title and s.lang
    ]
    return (
        "You are subtitling talks at Python Pizza Istanbul, a Python community conference, for the "
        "audience in the room and on the live stream. "
        f"Keep these names exactly as written and never translate them: {', '.join(protected_names(sessions))}. "
        f"Today's talks: {'; '.join(talks)}. "
        f"{sponsor_line}"
        "Leave out filler sounds such as eee, ııı, uh and um. "
        "When the Turkish does not say whether a person is a man or a woman, use they in English. "
        f"Conference terms in Turkish subtitles: {glossary}."
    ) + (f" Additional instructions from the organisers: {extra.strip()}" if extra.strip() else "")


HINT_MAX_TOKENS = 160  # of Whisper's ~223 prompt tokens; recent speech gets most of the rest


@lru_cache(maxsize=1)
def _tokenizer():
    from mlx_whisper.tokenizer import get_tokenizer

    return get_tokenizer(True, num_languages=100)


def fit_tokens(text: str, max_tokens: int = HINT_MAX_TOKENS) -> str:
    """Cut text to max_tokens Whisper tokens at the last ", " or ". " boundary (drops the end)."""
    try:
        tok = _tokenizer()
    except Exception:
        return text[: max_tokens * 3]
    if len(tok.encode(" " + text)) <= max_tokens:
        return text
    lo, hi = 0, len(text)
    while lo < hi:  # longest prefix that fits
        mid = (lo + hi + 1) // 2
        if len(tok.encode(" " + text[:mid])) <= max_tokens:
            lo = mid
        else:
            hi = mid - 1
    cut = text[:lo]
    end = max(cut.rfind(", "), cut.rfind(". "))
    return (cut[:end] + ".") if end > 0 else cut


def asr_hint(lang: str, sessions, current=None, nxt=None) -> str:
    return fit_tokens(_asr_hint(lang, sessions, current, nxt))


def _asr_hint(lang: str, sessions, current=None, nxt=None) -> str:
    tr = lang == "tr"
    parts: list[str] = []
    terms: list[str] = []
    for sess in (current, nxt):
        if sess and sess.lang:
            who = sess.speaker if sess.speaker and len(sess.speaker) < 60 else ""
            parts.append(
                f"{who} anlatıyor: {sess.title}."
                if tr and who
                else f"{sess.title}, by {who}."
                if who
                else f"{sess.title}."
            )
            terms += talk_terms(sess.title)
    terms = list(dict.fromkeys(terms + always_names()))
    parts.append(("Terimler: " if tr else "Terms: ") + ", ".join(terms) + ".")
    names = speakers(sessions)
    if names:
        parts.append(("Bugünkü konuşmacılar " if tr else "Today's speakers are ") + ", ".join(names) + ".")
    return " ".join(parts)
