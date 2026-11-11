"""Construct the pipeline without models or audio, to catch wiring mistakes (missing methods etc.)."""

from eels.config import SettingsStore
from eels.pipeline import Pipeline


def test_pipeline_constructs_and_reports_status(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    store.update(translation_model="opus-mt", translation_model_en_tr="translategemma-12b")
    p = Pipeline(store, lambda channel, msg: None)
    try:
        assert p._mt_models_in_use() == ["translategemma-12b", "opus-mt"]
        assert p.asr.model_key == "whisper-turbo-15s" and p.asr.spec["audio_ctx"] == "750"
        assert p._audio_clock() > 0
        assert "Lysandros Nikolaou" in p._asr_hint("en")  # program hint includes the speakers
        for key in p._mt_models_in_use():
            p._mt_add(key)  # boot() does this (and starts them)
        st = p.status()
        speech, *translation = st.models
        assert (speech.job, speech.key, speech.state) == ("speech", "whisper-turbo-15s", "stopped")
        assert {m.key for m in translation} == {"translategemma-12b", "opus-mt"}
        assert next(m for m in translation if m.key == "opus-mt").directions == ["tr>en"]
        assert st.to_json()["engine"]["chosen"] == "local"  # serialisable for the panel
        assert p.health()["status"] == "ok"
        # name correction is wired in, with the program's speakers in its dictionary
        assert p._names.correct("welcome Lissandros Nikolaou.")[0] == "welcome Lysandros Nikolaou."
    finally:
        p.capture.close()


def test_gemini_engine_shows_sentences_and_falls_back(tmp_path, monkeypatch):
    import numpy as np
    from test_cloud import FakeServer

    import eels.pipeline as pl
    from eels.transcript import TranscriptLog

    server = FakeServer([])
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    real = pl.GeminiLive
    monkeypatch.setattr(pl, "GeminiLive", lambda *a, **k: real(*a, connect=server.connect, **k))
    store = SettingsStore(tmp_path / "settings.json")
    store.update(engine="gemini", spoken_language="tr")
    p = Pipeline(store, lambda channel, msg: None)
    p.transcript = TranscriptLog(tmp_path / "transcripts")
    try:
        p.running = True
        p._cloud_enable()
        assert p.active == "gemini" and set(p.cloud.sessions) == {"en"}
        p._cloud_input("en", "Merhaba arkadaşlar.", False, "tr")
        p._cloud_output("en", "Hello friends.", False, None)
        p._cloud_output("en", " He said", False, None)
        assert [s.text for s in p.display.segments] == ["Hello friends."]
        assert p.display.interim and p.display.interim.text == "He said"
        assert p.display.snapshot()["segments"][0]["text"] == "Hello friends."  # what the overlay receives
        from datetime import date

        rec = p.transcript.read(date.fromisoformat(p.transcript.days()[-1]))[-1]
        assert rec.engine == "gemini" and rec.source == "Merhaba arkadaşlar." and rec.src == "tr"
        # Gemini goes down: the local engine starts from the recent audio.
        p._cloud_audio(np.zeros(16000, dtype=np.float32), 1.0)
        p.failover.active = "local"
        p._to_local(p.cloud)
        assert p.active == "local" and p.engine.stream_samples >= 0
        before = p.cloud.sessions["en"]
        full = p.set_gemini_extra("  Do not translate the word sprint.  ")
        assert full.endswith("Additional instructions from the organisers: Do not translate the word sprint.")
        assert p.cloud.instruction == full and p.cloud.sessions["en"] is not before  # reconnected
        assert store.value.gemini_extra_instruction == "Do not translate the word sprint."
        p.apply_settings({"engine": "local"})
        assert p.cloud is None
    finally:
        p.capture.close()


def test_local_models_unload_while_gemini_runs_and_return_on_failover(tmp_path, monkeypatch):
    from test_cloud import FakeServer

    import eels.pipeline as pl
    from eels.workers import WorkerClient

    spawned = []
    monkeypatch.setattr(WorkerClient, "_spawn", lambda self: spawned.append(self.name))  # no real model loading
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    server = FakeServer([])
    real = pl.GeminiLive
    monkeypatch.setattr(pl, "GeminiLive", lambda *a, **k: real(*a, connect=server.connect, **k))
    store = SettingsStore(tmp_path / "settings.json")
    store.update(engine="gemini", gemini_standby=False)
    p = Pipeline(store, lambda channel, msg: None)
    try:
        p.running = True
        p._cloud_enable()
        p._apply_standby()
        assert p.local_parked and all(w.parked for w in p._local_workers())
        assert not p.asr.poll() and spawned == []  # the health check does not bring them back
        p.failover.active = "local"
        p._to_local(p.cloud)  # Gemini failed: load them
        assert not p.local_parked and "asr" in spawned
        p.apply_settings({"gemini_standby": True})
        assert not p.local_parked

        saved = []
        monkeypatch.setattr(pl, "store_key", saved.append)
        monkeypatch.setattr(pl, "key_source", lambda: "keychain")
        before = p.cloud
        assert p.set_gemini_key("new-key-0123456789abcdef") == "Saved in the Keychain."
        assert saved == ["new-key-0123456789abcdef"] and p.cloud is not before  # reconnected with it
        p.apply_settings({"engine": "local"})
    finally:
        p.capture.close()


def test_no_model_switch_while_local_models_are_unloaded(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    p = Pipeline(store, lambda channel, msg: None)
    try:
        p.asr.parked = True
        p.switch_model("speech", "whisper-small")
        assert "asr" not in p.switching and "unloaded" in p.events[-1].msg
    finally:
        p.capture.close()
