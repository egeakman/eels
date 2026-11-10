import numpy as np

from live_translate.streaming import (
    ASRResult,
    ClauseSegmenter,
    HypothesisBuffer,
    OnlineASR,
    Word,
    is_hallucination,
    join_words,
)


def words(*items, start=0.0, dur=0.4):
    out = []
    t = start
    for text in items:
        out.append(Word(t, t + dur, " " + text))
        t += dur + 0.1
    return out


def test_local_agreement_commits_common_prefix_only():
    hb = HypothesisBuffer()
    hb.insert(words("hello", "world", "this"))
    assert hb.flush() == []  # first hypothesis: nothing to agree with
    hb.insert(words("hello", "world", "is"))
    committed = hb.flush()
    assert [w.text.strip() for w in committed] == ["hello", "world"]
    assert [w.text.strip() for w in hb.tentative()] == ["is"]


def test_agreement_ignores_case_and_punctuation():
    hb = HypothesisBuffer()
    hb.insert(words("Hello,", "world"))
    hb.flush()
    hb.insert(words("hello", "world."))
    assert len(hb.flush()) == 2


def test_already_committed_words_are_not_repeated():
    hb = HypothesisBuffer()
    hb.insert(words("one", "two", "three"))
    hb.flush()
    hb.insert(words("one", "two", "three"))
    first = hb.flush()
    assert [w.text.strip() for w in first] == ["one", "two", "three"]
    # A new hypothesis re-transcribes the start of the buffer: the overlap must be dropped.
    hb.insert(words("one", "two", "three", "four") )
    hb.flush()
    hb.insert(words("one", "two", "three", "four"))
    again = hb.flush()
    assert [w.text.strip() for w in again] == ["four"]


def test_online_asr_offsets_and_finish():
    o = OnlineASR()
    o.reset(10.0)
    o.append(np.zeros(16000 * 2, dtype=np.float32))
    o.apply(ASRResult(words("a", "b", "c")))
    committed, tentative = o.apply(ASRResult(words("a", "b", "d")))
    assert [w.text.strip() for w in committed] == ["a", "b"]
    assert committed[0].start == 10.0  # buffer offset added
    tail = o.finish()
    assert [w.text.strip() for w in tail] == ["d"]
    assert join_words(o.committed) == "a b d"


def test_online_asr_trims_at_sentence_end():
    o = OnlineASR(trim_sentence_s=1.0, trim_hard_s=5.0)
    o.reset(0.0)
    o.append(np.zeros(16000 * 3, dtype=np.float32))
    ws = words("Hello", "there.", "Next")
    o.apply(ASRResult(ws))
    o.apply(ASRResult(ws))
    assert o.buffer_offset > 0.0  # trimmed after "there."
    assert abs(o.buffer_offset - ws[1].end) < 1e-3


def test_segmenter_keeps_whole_sentences():
    seg = ClauseSegmenter(max_words=30, max_s=12.0, gap_s=1.0)
    # The Kahoot case: a pause after "Kahoot" must not cut the sentence.
    assert seg.add(words("So", "now", "we", "are", "gonna", "do", "the", "Kahoot"), now=0.0) == []
    assert seg.check_age(now=0.6) is None  # a short pause is not the end of the sentence
    out = seg.add(words("quiz."), now=0.8)
    assert [c.text for c in out] == ["So now we are gonna do the Kahoot quiz."]
    # Commas no longer cut.
    assert seg.add(words("First,", "we", "wrote", "a", "prototype,"), now=1.0) == []
    # No punctuation: the sentence ends after a gap with no new words.
    assert seg.check_age(now=1.5) is None
    assert seg.check_age(now=2.1).reason == "gap"


def test_segmenter_safety_cap_cuts_at_comma():
    seg = ClauseSegmenter(max_words=12, max_s=12.0, gap_s=5.0)
    ws = words("one", "two", "three", "four", "five,", "six", "seven", "eight", "nine", "ten", "eleven", "twelve")
    out = seg.add(ws, now=0.0)
    assert [c.text for c in out] == ["one two three four five,"]
    assert [w.text.strip() for w in seg.pending] == ["six", "seven", "eight", "nine", "ten", "eleven", "twelve"]
    seg2 = ClauseSegmenter(max_words=30, max_s=3.0, gap_s=5.0)
    seg2.add(words("a", "b", "c"), now=0.0)
    assert seg2.check_age(now=3.1).reason == "max_time"


def test_hallucination_filter():
    assert is_hallucination("Altyazı M.K.")
    assert is_hallucination(" İzlediğiniz için teşekkürler.")
    assert is_hallucination("Thanks for watching!")
    assert is_hallucination("you you you you you you you")
    assert not is_hallucination("Thank you for coming to my talk.")
    assert not is_hallucination("Bugün size FastAPI anlatacağım.")


def test_period_at_a_pause_does_not_end_the_sentence_if_speaker_continues():
    seg = ClauseSegmenter(max_words=30, max_s=12.0, gap_s=1.0)
    first = words("So", "now", "we", "do", "the", "Kahoot.")
    first[-1].soft_end = True  # Whisper added the period because the audio ended at the pause
    assert seg.add(first, now=0.0) == []
    out = seg.add(words("Quiz."), now=0.7)
    assert [c.text for c in out] == ["So now we do the Kahoot Quiz."]


def test_period_at_a_real_end_still_closes_the_sentence_after_the_gap():
    seg = ClauseSegmenter(max_words=30, max_s=12.0, gap_s=1.0)
    ws = words("Thank", "you.")
    ws[-1].soft_end = True
    assert seg.add(ws, now=0.0) == []
    assert seg.check_age(now=1.1).text == "Thank you."


def test_turkish_ordinals_and_abbreviations_do_not_end_sentences():
    seg = ClauseSegmenter(max_words=30, max_s=12.0, gap_s=1.0)
    assert seg.add(words("Kanuni'nin", "tahta", "çıkışının", "30."), now=0.0) == []
    out = seg.add(words("yılında", "yapılmış."), now=0.5)
    assert [c.text for c in out] == ["Kanuni'nin tahta çıkışının 30. yılında yapılmış."]
    assert seg.add(words("Plan", "M.Ö."), now=1.0) == []
    assert seg.check_age(now=2.5).text == "Plan M.Ö."  # if the speaker really stops, the gap still ends it


def test_split_sentences_for_sentence_level_translators():
    from live_translate.streaming import split_sentences

    assert split_sentences("Did you tell her? I had to.") == ["Did you tell her?", "I had to."]
    assert split_sentences("Are you driving, Mr. Barnes?") == ["Are you driving, Mr. Barnes?"]
    assert split_sentences("Kanuni'nin 30. yılında yapıldı. Çok güzel.") == ["Kanuni'nin 30. yılında yapıldı.", "Çok güzel."]
    assert split_sentences("It costs 3.5 dollars") == ["It costs 3.5 dollars"]
    assert split_sentences("Running mate Oh, not just running mate") == ["Running mate Oh, not just running mate"]
