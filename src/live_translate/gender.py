"""Gender-neutral English for Turkish sources.

Turkish has no grammatical gender: "o" means he, she or it, and subjects are often dropped
("Çok iyidir." = "(It/he/she) is very good."). Opus-MT has to pick and usually picks "he".
When the Turkish sentence itself has no gender cue, third-person he/she in the English
is rewritten to singular "they", with the verb agreement that comes with it.
This is a rule-based post-edit; it does not guess "it" for objects.
"""

from __future__ import annotations

import re

from .streaming import fold

# Turkish words that do carry gender; if one is present the translation is left as is.
TR_GENDER_CUES = {
    "kadın",
    "adam",
    "erkek",
    "kız",
    "kızı",
    "kızım",
    "oğlan",
    "oğul",
    "oğlu",
    "oğlum",
    "bayan",
    "bay",
    "bey",
    "beyefendi",
    "hanım",
    "hanımefendi",
    "anne",
    "annem",
    "annesi",
    "baba",
    "babam",
    "babası",
    "abla",
    "ablam",
    "ablası",
    "abi",
    "abim",
    "abisi",
    "ağabey",
    "teyze",
    "amca",
    "dayı",
    "hala",
    "karı",
    "karısı",
    "koca",
    "kocası",
    "eşi",
    "kral",
    "kraliçe",
    "kardeşi",
    "dede",
    "nine",
    "babaanne",
    "anneanne",
}

ADVERBS = {
    "always",
    "never",
    "often",
    "also",
    "just",
    "really",
    "still",
    "usually",
    "sometimes",
    "only",
    "even",
    "already",
    "actually",
    "probably",
    "certainly",
    "rarely",
    "now",
    "then",
}

# Contractions and irregular verbs after he/she.
FIXED = [
    (r"\b(he|she)'s\b", "they're"),
    (r"\b(he|she) is\b", "they are"),
    (r"\b(he|she) isn't\b", "they aren't"),
    (r"\b(he|she) was\b", "they were"),
    (r"\b(he|she) wasn't\b", "they weren't"),
    (r"\b(he|she) has\b", "they have"),
    (r"\b(he|she) hasn't\b", "they haven't"),
    (r"\b(he|she) does\b", "they do"),
    (r"\b(he|she) doesn't\b", "they don't"),
    (r"\b(he|she)'ll\b", "they'll"),
    (r"\b(he|she)'d\b", "they'd"),
    (r"\bhimself\b|\bherself\b", "themselves"),
    (r"\bhis\b", "their"),
    (r"\bhers\b", "theirs"),
    (r"\bhim\b", "them"),
]

# "her" before a noun is possessive (their), otherwise it is an object (them).
HER_OBJECT_NEXT = {
    "",
    "and",
    "or",
    "but",
    "to",
    "for",
    "with",
    "about",
    "from",
    "in",
    "on",
    "at",
    "that",
    "because",
    "so",
    "again",
    "too",
    "very",
    "now",
    "then",
    "here",
    "there",
    "back",
    "up",
    "down",
    "out",
    "off",
    "away",
    "yesterday",
    "today",
    "tomorrow",
    "tonight",
    "last",
    "every",
    "a",
    "an",
    "the",
    "this",
    "my",
    "your",
    "our",
    "their",
    "his",
    "its",
    "some",
    "what",
    "how",
    "if",
    "when",
    "why",
} | ADVERBS


def _match_case(src: str, repl: str) -> str:
    return repl[0].upper() + repl[1:] if src[:1].isupper() else repl


def _base_verb(verb: str) -> str:
    v = verb.lower()
    if v in ("is", "has", "does", "was"):
        return {"is": "are", "has": "have", "does": "do", "was": "were"}[v]
    if v.endswith("ies") and len(v) > 4:
        return verb[:-3] + "y"
    if re.search(r"(ss|sh|ch|x|z|o)es$", v):
        return verb[:-2]
    if v.endswith("s") and not v.endswith("ss") and len(v) > 2:
        return verb[:-1]
    return verb


def has_gender_cue(turkish: str) -> bool:
    words = {re.sub(r"[^\w]", "", w) for w in fold(turkish).split()}
    return bool(words & TR_GENDER_CUES)


def neutralize(english: str, turkish_source: str) -> str:
    if not english or has_gender_cue(turkish_source):
        return english
    out = english
    for pattern, repl in FIXED:
        out = re.sub(pattern, lambda m, r=repl: _match_case(m.group(0), r), out, flags=re.IGNORECASE)

    # "her": possessive before a noun, object otherwise.
    def her(m: re.Match) -> str:
        nxt = (m.group(2) or "").lower()
        return _match_case(m.group(1), "them" if nxt in HER_OBJECT_NEXT else "their") + m.group(0)[len(m.group(1)) :]

    out = re.sub(r"\b(her)\b(?=(?:[\s,.!?;:]+(\w+))?)", lambda m: her(m), out, flags=re.IGNORECASE)

    # he/she + optional adverb + present-tense verb: "he likes" -> "they like".
    def subj(m: re.Match) -> str:
        pron, adv, verb = m.group(1), m.group(2) or "", m.group(3)
        return _match_case(pron, "they") + adv + _base_verb(verb)

    adv_re = "|".join(sorted(ADVERBS))
    out = re.sub(rf"\b(he|she)((?:\s+(?:{adv_re}))?\s+)([a-z]+s)\b", subj, out, flags=re.IGNORECASE)
    # Remaining bare he/she (before modals, past tense, etc.): "he will" -> "they will".
    out = re.sub(r"\b(he|she)\b", lambda m: _match_case(m.group(1), "they"), out, flags=re.IGNORECASE)
    return out
