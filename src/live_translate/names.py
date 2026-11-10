"""Correct misheard names after recognition, using the day's program as the dictionary.

Whisper's prompt holds only ~223 tokens, so most program names cannot be hinted at once. This
matches what Whisper wrote against all of them and fixes near-exact misspellings of names
("Lysandris Nikolaou" -> "Lysandros Nikolaou", "Py İstanbul" -> "PyIstanbul").

Deliberately conservative: only capitalised single words of 6+ letters (names), or runs of 2-3
words, with a very high similarity. Real words that merely resemble a name ("seler", Turkish for
"floods", vs "Celery") stay below the bar. Turkish suffixes after an apostrophe are kept.
"""

from __future__ import annotations

import re

from rapidfuzz.distance import Levenshtein

from .streaming import fold

MULTI_MIN = 0.85  # runs of 2-3 words, or multi-word names: normalised similarity


def single_word_ok(key: str, name_key: str) -> bool:
    """One word against a one-word name: 1 letter off for 7-9 letters, 2 for 10 or more.
    Shorter names are only normalised (case, spacing): too many real words are one letter
    away from them ("Remini" vs "Gemini")."""
    if len(name_key) < 7:
        return key == name_key
    allowed = 1 if len(name_key) < 10 else 2
    return Levenshtein.distance(key, name_key, score_cutoff=allowed) <= allowed


def different_word(key: str, name_key: str) -> bool:
    """One contains the other: a different word, not a misspelling ("istanbul" vs "pyistanbul",
    "adjangogirls" vs "djangogirls")."""
    return key != name_key and (key in name_key or name_key in key)


_TAIL = re.compile(r"^(.*?)((?:['’]\w+)?)([.,!?;:…\"”)]*)$")


def _key(text: str) -> str:
    return re.sub(r"[^\w]", "", fold(text))


class NameCorrector:
    def __init__(self, names: list[str]):
        entries = []
        for name in dict.fromkeys(names):
            entries.append(name)
            parts = name.split()
            if len(parts) > 1 and parts[0][:1].isupper() and parts[-1][:1].isupper():
                entries += [p for p in parts if len(p) >= 6]  # surnames and long first names alone
        self.names = [(n, _key(n), len(n.split())) for n in dict.fromkeys(entries) if len(_key(n)) >= 4]

    def correct(self, text: str) -> tuple[str, list[tuple[str, str]]]:
        """Return (corrected text, [(heard, corrected), ...])."""
        tokens = text.split(" ")
        out: list[str] = []
        changes: list[tuple[str, str]] = []
        i = 0
        while i < len(tokens):
            done = False
            for n in (3, 2, 1):
                if i + n > len(tokens):
                    continue
                chunk = tokens[i : i + n]
                m = _TAIL.match(chunk[-1])
                base_last, suffix, punct = m.group(1), m.group(2), m.group(3)
                surface = " ".join(chunk[:-1] + [base_last])
                key = _key(surface)
                if not key or len(key) < (6 if n == 1 else 8):
                    continue
                if n == 1 and not surface[:1].isupper():
                    continue  # lowercase single words are ordinary words, not names
                best = None
                for name, nkey, words in self.names:
                    if n > 1 and words == 1 and len(nkey) < 8:
                        continue
                    if different_word(key, nkey):
                        continue
                    sim = Levenshtein.normalized_similarity(key, nkey)
                    ok = single_word_ok(key, nkey) if n == 1 and words == 1 else sim >= MULTI_MIN
                    if ok and (best is None or sim > best[0]):
                        best = (sim, name)
                if best is None:
                    continue
                if best[1] != surface:
                    changes.append((surface, best[1]))
                out.append(best[1] + suffix + punct)
                i += n
                done = True
                break
            if not done:
                out.append(tokens[i])
                i += 1
        return " ".join(out), changes
