"""Gemini engine without network: sentence building, failover, and the session loop with a fake server."""

import asyncio
import time

import numpy as np
from google.genai import types

from eels.cloud import FRAME_SAMPLES, Failover, GeminiLive, Sentencer, classify_error, echo_for, targets_for


def test_targets_per_spoken_language():
    assert targets_for("en") == ["tr"]
    assert targets_for("tr") == ["en"]
    assert targets_for("auto") == ["en", "tr"]
    assert echo_for("en") and echo_for("tr") and not echo_for("auto")


def test_sentence_is_final_once_text_follows_it():
    sn = Sentencer()
    sn.add_source("Merhaba arkadaşlar. Bugün", "tr", 1.0)
    assert sn.add_text("Hello", 1.1) == []
    done = sn.add_text(" friends.", 1.2)  # Gemini sends whole words: the period ends it now
    assert [s.text for s in done] == ["Hello friends."]
    assert done[0].source == "Merhaba arkadaşlar. Bugün" and done[0].src_lang == "tr"
    assert sn.add_text(" Today", 1.3) == [] and sn.interim() == "Today"


def test_ordinals_and_abbreviations_do_not_end_sentences():
    sn = Sentencer()
    assert sn.add_text("Kanuni'nin 30. yılında Dr. Ayşe geldi", 1.0) == []
    assert sn.interim() == "Kanuni'nin 30. yılında Dr. Ayşe geldi"


def test_pause_and_finished_close_the_sentence():
    sn = Sentencer(gap_s=1.0)
    sn.add_text("we start now", 1.0)
    assert sn.tick(1.5) == []
    assert [s.reason for s in sn.tick(2.1)] == ["gap"]
    sn.add_text("and we stop", 3.0)
    assert [s.text for s in sn.add_text("", 3.1, finished=True)] == ["and we stop"]
    assert sn.interim() == ""


def test_run_on_text_is_cut_at_a_comma():
    sn = Sentencer(max_words=10)
    done = sn.add_text("one two three four five six, seven eight nine ten eleven", 1.0)
    assert [s.text for s in done] == ["one two three four five six,"]
    assert [s.reason for s in done] == ["max_words"]
    assert sn.interim() == "seven eight nine ten eleven"


def test_failover_on_disconnect_and_silence_then_recovery():
    f = Failover(down_s=5, silent_s=12, recover_s=20)
    assert f.update(0, False, None, 0) is None
    assert f.update(5.1, False, None, 0) == "local"
    # Back only after 20 s of being connected and producing text.
    assert f.update(10, True, 9.5, 0) is None
    assert f.update(29, True, 28.0, 0) is None
    assert f.update(30.5, True, 30.0, 0) == "gemini"
    # Connected but silent while someone speaks.
    assert f.update(40, True, 30.0, 12.5) == "local"
    # Stale output does not count as recovered.
    assert f.update(70, True, 50.0, 0) is None and f.active == "local"


class FakeError(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code = code


def test_error_classification():
    assert classify_error(FakeError(1000, "bye"))[0] == "closed"
    assert classify_error(FakeError(1007, "Unknown name session_resumption"))[0] == "rejected"
    assert classify_error(FakeError(1008, "API key not valid"))[0] == "auth"
    assert classify_error(FakeError(1011, "Your prepayment credits are depleted. Please go to AI Studio"))[0] == "auth"
    assert classify_error(OSError("Network is unreachable"))[0] == "network"


def msg(output=None, source=None, handle=None, finished=False):
    sc = None
    if output is not None or source is not None:
        sc = types.LiveServerContent(
            output_transcription=types.Transcription(text=output, finished=finished) if output is not None else None,
            input_transcription=types.Transcription(text=source, language_code="tr") if source is not None else None,
        )
    upd = types.LiveServerSessionResumptionUpdate(new_handle=handle, resumable=True) if handle else None
    return types.LiveServerMessage(server_content=sc, session_resumption_update=upd)


class FakeServer:
    """Each connection plays one script of messages, then closes normally."""

    def __init__(self, scripts):
        self.scripts = list(scripts)
        self.configs = []
        self.sent = []

    def connect(self, model, config):
        self.configs.append(config)
        server = self
        script = self.scripts.pop(0) if self.scripts else []

        class Session:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def send_realtime_input(self, audio):
                server.sent.append(audio.data)

            async def receive(self):
                await asyncio.sleep(0.05)
                for m in script:
                    yield m
                raise FakeError(1000, "closed")

        return Session()


def wait_for(cond, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


def test_session_streams_audio_reports_text_and_resumes_with_handle():
    server = FakeServer([[msg(source="Merhaba."), msg(output="Hello.", handle="h1")], []])
    inputs, outputs, events = [], [], []
    g = GeminiLive(
        lambda *a: inputs.append(a),
        lambda *a: outputs.append(a),
        lambda *a: events.append(a),
        key="test",
        connect=server.connect,
        instruction="Keep PyIstanbul as written.",
    )
    try:
        g.set_targets(["en"], echo=True)
        g.feed(np.zeros(FRAME_SAMPLES * 2 + 100, dtype=np.float32))  # two full 100 ms frames, a remainder kept
        assert wait_for(lambda: outputs and len(server.configs) >= 2)
        assert inputs[0][:2] == ("en", "Merhaba.") and inputs[0][3] == "tr"
        assert outputs[0][:2] == ("en", "Hello.")
        assert server.configs[0].translation_config.target_language_code == "en"
        assert server.configs[0].translation_config.echo_target_language is True
        assert server.configs[0].system_instruction is not None  # the program goes along
        assert server.configs[1].session_resumption.handle == "h1"  # the reconnect resumes
        assert g.last_output is not None
        assert not [e for e in events if e[0] == "error"]  # a normal close is not an error
    finally:
        g.shutdown()


def test_detect_mode_runs_one_session_per_direction():
    server = FakeServer([])
    g = GeminiLive(lambda *a: None, lambda *a: None, lambda *a: None, key="test", connect=server.connect)
    try:
        g.set_targets(["en", "tr"])
        assert set(g.sessions) == {"en", "tr"}
        before = g.sessions["tr"]
        g.set_targets(["tr"])
        assert set(g.sessions) == {"tr"} and g.sessions["tr"] is before  # kept as is
        g.set_targets(["tr"], echo=True)
        assert g.echo and g.sessions["tr"] is not before  # restarted with the new setting
    finally:
        g.shutdown()


def test_benchmark_clip_with_fake_server(monkeypatch):
    from eels import cloud
    from eels.bench.captioned import gemini_clip

    server = FakeServer([[msg(source=" Merhaba."), msg(output=" Hello."), msg(output=" Bye", finished=True)]])
    real = cloud.GeminiLive
    monkeypatch.setattr(cloud, "GeminiLive", lambda *a, **k: real(*a, key="test", connect=server.connect, **k))
    r = gemini_clip(np.zeros(FRAME_SAMPLES * 3, dtype=np.float32), "tr", speed=20, settle_s=0.3)
    assert r["source"] == "Merhaba."
    assert [t for _, t, _ in r["sentences"]] == ["Hello.", "Bye"]
    assert r["sentences"][0][2] == "Merhaba."


def test_store_key_rejects_text_that_is_not_a_key():
    import pytest

    from eels.cloud import store_key

    for bad in ("", "short", "has spaces in it but is long enough", "x" * 400):
        with pytest.raises(ValueError):
            store_key(bad)
