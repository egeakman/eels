from datetime import date, datetime

from eels import schedule as sched
from eels.config import Settings, SettingsStore
from eels.hints import gemini_instruction
from eels.transcript import TranscriptLog, TranscriptRecord, export_srt, parse_clock
from eels.translate import check_translation, clean_output

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


def record(day, start, end, source, translation, **kw):
    fields = {
        "src": "en",
        "tgt": "tr",
        "engine": "local",
        "speech_model": "whisper-turbo-15s",
        "translation_model": "opus-mt",
        "mode": "en",
        "session": None,
        "cut": "sentence",
        "delay_s": 1.0,
    }
    return TranscriptRecord(
        parse_clock(day, start), parse_clock(day, end), source=source, translation=translation, **(fields | kw)
    )


def test_transcript_and_srt(tmp_path):
    log = TranscriptLog(tmp_path)
    day = date(2026, 11, 14)
    log.append(record(day, "11:15:02", "11:15:04", "Hello", "Merhaba", corrections=[("PyIstanbul", "PyIstanbul")]))
    log.append(record(day, "11:15:03", "11:15:06", "world", "dünya", engine="gemini"))
    log.append(record(day, "12:00:00", "12:00:02", "x", "y"))
    recs = log.read(day)
    assert recs[0].corrections == [("PyIstanbul", "PyIstanbul")] and recs[1].engine == "gemini"
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
    from eels.translate import protect_terms, restore_terms

    text, found = protect_terms("We use Docker and parquet files with DuckDB, not docker-compose.")
    assert found == ["Docker", "parquet", "DuckDB"]
    assert "XYZ1" in text and "docker-compose" in text
    assert restore_terms("XYZ1 ve XYZ2 dosyaları, XYZ3 ile", found) == "Docker ve parquet dosyaları, DuckDB ile"
    assert restore_terms("XYZ1 ve dosyalar", found) is None


def test_untranslated_code_switching_is_accepted():
    # A speaker switching to English inside a Turkish talk: identical output is correct.
    assert check_translation("This is the main event loop.", "This is the main event loop.", "en") is None


def test_translation_model_per_direction():
    from eels.config import translation_model_for as model_for

    s = Settings(translation_model="opus-mt")
    assert model_for(s, "en", "tr") == "opus-mt" and model_for(s, "tr", "en") == "opus-mt"
    s = Settings(translation_model="opus-mt", translation_model_en_tr="translategemma-12b")
    assert model_for(s, "en", "tr") == "translategemma-12b" and model_for(s, "tr", "en") == "opus-mt"


def test_old_transcript_lines_still_read(tmp_path):
    day = date(2026, 11, 9)
    (tmp_path / "2026-11-09.jsonl").write_text(
        '{"start": "2026-11-09T11:15:02.000+03:00", "end": "2026-11-09T11:15:04.000+03:00", "src": "en", "tgt": "tr",'
        ' "source": "Hi", "translation": "Selam", "asr_model": "mlx-community/whisper-large-v3-turbo", "mt_model": "opus-mt"}\n'
        "{broken line\n"
    )
    (r,) = TranscriptLog(tmp_path).read(day)
    assert r.engine == "local" and r.translation_model == "opus-mt" and r.speech_model.endswith("turbo")


def test_model_catalog_is_consistent():
    from eels import models

    assert models.get(models.DEFAULT_SPEECH).job == "speech"
    assert models.get(models.DEFAULT_TRANSLATION).job == "translation"
    for m in models.CATALOG:
        assert m.name and "(" not in m.name and "(" not in m.variant  # descriptions go in note
        assert m.spec.get("model") and (m.repos or m.conversion)
    assert len(models.BY_KEY) == len(models.CATALOG)  # keys are unique


def test_old_settings_are_migrated(tmp_path):
    import json

    from eels.config import SettingsStore

    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "asr_model": "mlx-community/whisper-large-v3-turbo",
                "asr_audio_ctx": "full",
                "mt_model": "opus-mt",
                "mt_model_en_tr": "/old/place/HY-MT1.5-7B-mlx-4bit",
                "font_size": 50,
            }
        )
    )
    s = SettingsStore(path).value
    assert (s.speech_model, s.translation_model, s.translation_model_en_tr) == (
        "whisper-turbo-30s",
        "opus-mt",
        "hymt-7b",
    )
    assert s.font_size == 50
    path.write_text(json.dumps({"speech_model": "gone-model"}))
    assert SettingsStore(path).value.speech_model == "whisper-turbo-15s"


def test_gemini_instruction_carries_the_program():
    text = gemini_instruction(sched.load())
    assert "Lysandros Nikolaou" in text and "PyIstanbul" in text
    assert "eee" in text  # no filler sounds
    assert "The event's sponsors: EuroPython Society, StartGate" in text and "fal (the company fal.ai)" in text
    assert "The venue is StartGate." in text
    assert "The organizers: Özge Çinko, Kader Miyanyedi, Cemrehan Çavdar, Ege Akman." in text
    assert "call for proposals = konuşma başvuruları" in text and "sprint = sprint" in text and "_comment" not in text


def test_panel_catalog_lists_models_without_network(monkeypatch):
    from eels import models

    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    c = models.panel_catalog()
    assert next(o["key"] for o in c["speech"]) == models.DEFAULT_SPEECH
    assert all(isinstance(o["available"], bool) and o["title"] for o in c["speech"] + c["translation"])
    assert "opus-mt-beam4" not in [o["key"] for o in c["translation"]]  # benchmark-only


def test_sponsors_are_protected_names_but_turkish_fal_is_not():
    from eels.hints import protected_names
    from eels.translate import protect_terms

    names = protected_names(sched.load())
    assert {"StartGate", "Domino's Pizza", "fal.ai", "Bilus Teknoloji"} <= set(names)
    _, found = protect_terms("Kahve falı ve fal bakmak, StartGate'te.", names)
    assert found == ["StartGate"]  # the Turkish word fal is translated as usual


def test_organizer_first_names_stay_ordinary_words():
    from eels.hints import protected_names
    from eels.translate import protect_terms

    names = protected_names(sched.load())
    _, found = protect_terms("Kader böyleymiş; Ege Akman ve Kader Miyanyedi Ege'de.", names)
    assert found == ["Ege Akman", "Kader Miyanyedi"]
