"""StreamEngine behaviour with a fake Whisper (no models, no VAD speech needed)."""
import numpy as np

from live_translate.config import Settings
from live_translate.engine import StreamEngine
from live_translate.streaming import clean_prompt_text, looks_turkish, has_content


def make_engine(script, spoken="en"):
    """script: list of outputs, one per ASR call; each output is a list of words (text) spread over the buffer."""
    calls = {"n": 0, "prompts": []}
    clauses = []

    def asr_fn(audio, lang, prompt):
        calls["prompts"].append(prompt)
        out = script[min(calls["n"], len(script) - 1)]
        calls["n"] += 1
        dur = len(audio) / 16000
        step = dur / max(1, len(out))
        words = [[i * step, (i + 1) * step - 0.05, " " + w, 0.9] for i, w in enumerate(out)]
        return {"words": words, "language": lang or "en", "language_prob": 1.0, "ms": 100}

    settings = Settings(spoken_language=spoken, interim=False)
    clock = {"t": 0.0}
    eng = StreamEngine(lambda: settings, asr_fn, lambda c, src, seq: clauses.append((c.text, src)), clock=lambda: clock["t"])
    eng.test_clock = clock
    eng.online.reset(0.0)
    eng.gate.in_speech = True
    return eng, calls, clauses


def speaker_stops(eng):
    """Pause, then the sentence gap passes with no new words."""
    eng.pause()
    eng.test_clock["t"] += 2.0
    eng.check_age()


def feed(eng, seconds):
    eng.online.append(np.zeros(int(16000 * seconds), dtype=np.float32))
    eng.stream_samples += int(16000 * seconds)


def test_ellipsis_spiral_does_not_reach_screen_or_prompt():
    script = [["So...", "me", "being", "myself."]] * 2 + [["..."]] * 6 + [["...", "..."]] * 4
    eng, calls, clauses = make_engine(script)
    for _ in range(12):
        feed(eng, 1.0)
        eng.run_asr()
    speaker_stops(eng)
    assert clauses, "the real words should still come through"
    assert all(has_content(text) for text, _ in clauses), clauses  # no "..."-only subtitles
    assert any(text.startswith("So...") for text, _ in clauses), "hesitation ellipses stay on screen"
    assert all("..." not in p for p in calls["prompts"]), "ellipses must never be fed back to Whisper"


def test_engine_recovers_after_long_silence_of_words():
    # Whisper returns nothing for a long time (stuck), then real words again.
    script = [[]] * 20 + [["We", "are", "back."]] * 3
    eng, calls, clauses = make_engine(script)
    eng.history.extend([])  # start with no context
    for _ in range(23):
        feed(eng, 1.0)
        eng.run_asr()
    speaker_stops(eng)
    assert eng.online.duration < 20, "buffer must not grow without limit"
    assert any("back" in text for text, _ in clauses)


def test_detect_switches_to_turkish_when_words_are_clearly_turkish():
    eng, calls, clauses = make_engine([["Uzun", "ince", "bir", "yoldayım,", "gidiyorum", "gündüz", "gece."]] * 3, spoken="auto")
    eng.last_lang = "en"
    for _ in range(3):
        feed(eng, 1.0)
        eng.run_asr()
    speaker_stops(eng)
    assert clauses and all(src == "tr" for _, src in clauses)


def test_helpers():
    assert clean_prompt_text("So... me being myself. And… this") == "So me being myself. And this"
    assert not has_content(" ... ") and has_content("ok")
    assert looks_turkish("Uzun ince bir yoldayım gidiyorum") and not looks_turkish("Today I will talk about Python")


def test_looks_turkish_does_not_fire_on_english():
    for t in ("Today I will talk about Python and Rust.", "Here is my shopping list with coffee and milk.",
              "Thanks for coming to my talk, see you in Prague."):
        assert not looks_turkish(t), t
    for t in ("Merhaba arkadaşlar, nasılsınız?", "Bu bir test.", "Nasıl gidiyor gününüz?"):
        assert looks_turkish(t), t


def test_prompt_echo_at_utterance_start_is_dropped():
    from live_translate.engine import drop_prompt_echo
    from live_translate.streaming import Word

    ws = [Word(i, i + 0.4, " " + t) for i, t in enumerate("Python Pizza Istanbul. Python, Django, the little girl".split())]
    out = drop_prompt_echo(ws, "Today's speakers are X. Python Pizza Istanbul. Python, Django, FastAPI.")
    assert [w.text.strip() for w in out] == ["the", "little", "girl"]
    ws2 = [Word(i, i + 0.4, " " + t) for i, t in enumerate("I love Python and Django".split())]
    assert drop_prompt_echo(ws2, "Python Pizza Istanbul. Python, Django.") == ws2  # real speech is kept


def test_prompt_fragments_are_dropped_but_full_names_kept():
    from live_translate.engine import is_prompt_fragment

    prompt = "Terms: PyIstanbul, PyPI, Django, Ultralytics. Today's speakers are Lysandros Nikolaou."
    assert is_prompt_fragment("PyI", prompt)
    assert not is_prompt_fragment("PyPI", prompt)
    assert is_prompt_fragment("Ultra Lysan", prompt)
    assert not is_prompt_fragment("Django.", prompt)          # a full name said on its own
    assert not is_prompt_fragment("PyIstanbul", prompt)
    assert not is_prompt_fragment("Yes.", prompt)             # not part of any name
    assert not is_prompt_fragment("PyI is great", prompt)     # more than two words: real speech
