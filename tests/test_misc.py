from datetime import date, datetime

from live_translate import schedule as sched
from live_translate.config import Settings, SettingsStore
from live_translate.transcript import TranscriptLog, export_srt, parse_clock
from live_translate.translate import check_translation, clean_output

AGENDA = """
<ol id=agenda-list>
<li class="border agenda-item grid" data-index=0 data-until=2026-11-14T11:00:00+03:00 data-when=2026-11-14T10:30:00+03:00>
 <span class="time">10:30</span><div class="content"><span class="title">Registration</span></div><span class="badge"></span></li>
<li class="border agenda-item grid" data-index=2 data-until=2026-11-14T11:40:00+03:00 data-when=2026-11-14T11:15:00+03:00>
 <span class="time">11:15</span><span class="lang" title=English>EN</span>
 <div class="content"><span class="speaker">Ada Lovelace</span><span class="title">Keynote</span></div><span class="badge"></span></li>
<li class="border agenda-item grid" data-index=3 data-until=2026-11-14T12:07:00+03:00 data-when=2026-11-14T11:57:00+03:00>
 <span class="time">11:57</span><span class="lang" title=Turkish>TR</span>
 <div class="content"><span class="speaker">Oğulcan Doğan</span><span class="title">LazyTown: Hızlı ve Tembel</span></div></li>
</ol>"""


def test_parse_agenda_and_current_session():
    sessions = sched.parse_agenda(AGENDA)
    assert [(s.lang, s.title) for s in sessions] == [
        (None, "Registration"),
        ("en", "Keynote"),
        ("tr", "LazyTown: Hızlı ve Tembel"),
    ]
    assert sessions[1].speaker == "Ada Lovelace"
    assert sessions[0].spoken == "auto"
    cur, nxt = sched.current_and_next(sessions, datetime.fromisoformat("2026-11-14T11:20:00+03:00"))
    assert cur.title == "Keynote" and nxt.title.startswith("LazyTown")
    cur, nxt = sched.current_and_next(sessions, datetime.fromisoformat("2026-11-14T11:50:00+03:00"))
    assert cur is None and nxt.lang == "tr"  # gap between sessions


def test_bundled_schedule_loads():
    sessions = sched.load()
    assert len(sessions) >= 20
    assert {"en", "tr"} <= {s.lang for s in sessions}


def test_transcript_and_srt(tmp_path):
    log = TranscriptLog(tmp_path)
    day = date(2026, 11, 14)
    a = parse_clock(day, "11:15:02")
    log.append({"start": a, "end": parse_clock(day, "11:15:04"), "source": "Hello", "translation": "Merhaba"})
    log.append(
        {
            "start": parse_clock(day, "11:15:03"),
            "end": parse_clock(day, "11:15:06"),
            "source": "world",
            "translation": "dünya",
        }
    )
    log.append(
        {"start": parse_clock(day, "12:00:00"), "end": parse_clock(day, "12:00:02"), "source": "x", "translation": "y"}
    )
    recs = log.read(day)
    assert len(recs) == 3
    srt = export_srt(recs, parse_clock(day, "11:15"), parse_clock(day, "11:40"), text="both", offset_s=1.0)
    assert srt.startswith("1\n00:00:03,000 --> 00:00:04,000\nMerhaba\nHello\n")  # clipped to next cue start
    assert "2\n00:00:04,000 --> 00:00:07,000\ndünya\nworld" in srt
    assert "\ny\n" not in srt  # outside the range


def test_translation_guards():
    assert check_translation("Hello everyone, welcome.", "", "tr") == "empty"
    assert check_translation("Hello everyone, welcome to the talk.", "Merhaba", "tr").startswith("length")
    assert (
        check_translation("Merhaba arkadaşlar nasılsınız", "Merhaba arkadaşlar, ışığı açın", "en")
        == "output looks Turkish"
    )
    assert (
        check_translation("email address from a log file.", "电子邮件地址 bir dosyadan.", "tr")
        == "non-Latin script in output"
    )
    assert check_translation("Thank you very much.", "Çok teşekkür ederim.", "tr") is None
    assert check_translation("İstanbul'da çok güzel bir gün.", "A beautiful day in Istanbul.", "en") is None


def test_clean_output_keeps_fragments_open():
    assert clean_output("bir veya daha fazla.", "one or more") == "bir veya daha fazla"
    assert clean_output("Çok teşekkürler.", "Thanks a lot.") == "Çok teşekkürler."
    assert clean_output('"Merhaba"<end_of_turn>', "Hello") == "Merhaba"


def test_settings_store_roundtrip(tmp_path):
    store = SettingsStore(tmp_path / "s.json")
    assert store.value == Settings()
    store.update(font_size=60, spoken_language="tr")
    again = SettingsStore(tmp_path / "s.json")
    assert again.value.font_size == 60 and again.value.spoken_language == "tr"
    (tmp_path / "s.json").write_text("{broken")
    assert SettingsStore(tmp_path / "s.json").value == Settings()  # corrupt file falls back to defaults


def test_term_protection_roundtrip():
    from live_translate.translate import protect_terms, restore_terms

    text, found = protect_terms("We use Docker and parquet files with DuckDB, not docker-compose.")
    assert found == ["Docker", "parquet", "DuckDB"]
    assert "XYZ1" in text and "docker-compose" in text
    assert restore_terms("XYZ1 ve XYZ2 dosyaları, XYZ3 ile", found) == "Docker ve parquet dosyaları, DuckDB ile"
    assert restore_terms("XYZ1 ve dosyalar", found) is None


def test_untranslated_code_switching_is_accepted():
    # A speaker switching to English inside a Turkish talk: identical output is correct.
    assert check_translation("This is the main event loop.", "This is the main event loop.", "en") is None


def test_translation_model_per_direction():
    from live_translate.config import mt_for

    s = Settings(mt_model="opus-mt")
    assert mt_for(s, "en", "tr") == "opus-mt" and mt_for(s, "tr", "en") == "opus-mt"
    s = Settings(mt_model="opus-mt", mt_model_en_tr="tg12b")
    assert mt_for(s, "en", "tr") == "tg12b" and mt_for(s, "tr", "en") == "opus-mt"
    s = Settings(mt_model="opus-mt", mt_model_tr_en="hymt7b")
    assert mt_for(s, "en", "tr") == "opus-mt" and mt_for(s, "tr", "en") == "hymt7b"
