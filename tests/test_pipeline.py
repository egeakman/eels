"""Construct the pipeline without models or audio, to catch wiring mistakes (missing methods etc.)."""
from live_translate.config import SettingsStore
from live_translate.pipeline import Pipeline


def test_pipeline_constructs_and_reports_status(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    store.update(mt_model="opus-mt", mt_model_en_tr="some/other-model")
    p = Pipeline(store, lambda channel, msg: None)
    try:
        assert p._mt_models_in_use() == ["some/other-model", "opus-mt"]
        assert p._audio_clock() > 0
        assert "Lysandros Nikolaou" in p._asr_hint("en")  # program hint includes the speakers
        st = p.status()
        assert st["type"] == "status" and st["workers"][0]["label"] == "Speech recognition"
        assert p.health()["status"] == "ok"
        # name correction is wired in, with the program's speakers in its dictionary
        assert p._names.correct("welcome Lissandros Nikolaou.")[0] == "welcome Lysandros Nikolaou."
    finally:
        p.capture.close()
