"""Audio input: device listing, hot-plug detection, capture with channel pick, file playback.

Everything is delivered to a sink as 16 kHz mono float32 chunks together with the
monotonic time at which the last sample of the chunk was captured.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import logging
import queue
import shutil
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np
import sounddevice as sd
import soxr

log = logging.getLogger(__name__)
TARGET_SR = 16000

Sink = Callable[[np.ndarray, float], None]


# Device listing ---------------------------------------------------------------
def reinit_portaudio() -> None:
    """PortAudio only scans devices at init, so re-init to see plugged/unplugged devices."""
    sd._terminate()
    sd._initialize()


def list_input_devices() -> list[dict]:
    try:
        default_in = sd.default.device[0]
    except Exception:
        default_in = -1
    out = []
    for d in sd.query_devices():
        if d["max_input_channels"] > 0:
            out.append(
                {
                    "index": d["index"],
                    "name": d["name"],
                    "channels": d["max_input_channels"],
                    "samplerate": d["default_samplerate"],
                    "default": d["index"] == default_in,
                }
            )
    return out


class _AudioObjectPropertyAddress(ctypes.Structure):
    _fields_ = [("selector", ctypes.c_uint32), ("scope", ctypes.c_uint32), ("element", ctypes.c_uint32)]


def _fourcc(s: str) -> int:
    return int.from_bytes(s.encode(), "big")


class CoreAudioDeviceIds:
    """Reads the CoreAudio device ID list directly (cheap, sees hot-plug without PortAudio re-init)."""

    def __init__(self) -> None:
        path = ctypes.util.find_library("CoreAudio")
        self.lib = ctypes.CDLL(path) if path else None
        self.addr = _AudioObjectPropertyAddress(_fourcc("dev#"), _fourcc("glob"), 0)

    def ids(self) -> tuple[int, ...] | None:
        if self.lib is None:
            return None
        size = ctypes.c_uint32(0)
        if self.lib.AudioObjectGetPropertyDataSize(1, ctypes.byref(self.addr), 0, None, ctypes.byref(size)):
            return None
        arr = (ctypes.c_uint32 * (size.value // 4))()
        if self.lib.AudioObjectGetPropertyData(1, ctypes.byref(self.addr), 0, None, ctypes.byref(size), arr):
            return None
        return tuple(arr)


class DeviceWatcher(threading.Thread):
    """Polls the CoreAudio device list and calls on_change when it differs."""

    def __init__(self, on_change: Callable[[], None], interval: float = 1.5):
        super().__init__(name="device-watcher", daemon=True)
        self.on_change = on_change
        self.interval = interval
        self.ca = CoreAudioDeviceIds()
        self._stop = threading.Event()

    def run(self) -> None:
        last = self.ca.ids()
        while not self._stop.wait(self.interval):
            try:
                now = self.ca.ids()
                if now is not None and now != last:
                    last = now
                    log.info("audio device list changed")
                    self.on_change()
            except Exception:
                log.exception("device watcher")

    def stop(self) -> None:
        self._stop.set()


# Microphone permission ----------------------------------------------------------
def mic_permission() -> str:
    """Returns 'authorized', 'denied', 'restricted', 'not_determined' or 'unknown'."""
    try:
        import AVFoundation

        status = AVFoundation.AVCaptureDevice.authorizationStatusForMediaType_(AVFoundation.AVMediaTypeAudio)
        return {0: "not_determined", 1: "restricted", 2: "denied", 3: "authorized"}.get(int(status), "unknown")
    except Exception:
        return "unknown"


# Level meter ---------------------------------------------------------------------
class Level:
    def __init__(self) -> None:
        self.rms_db = -120.0
        self.peak_db = -120.0
        self._zero_since: float | None = None
        self.all_zero_s = 0.0

    def update(self, x: np.ndarray) -> None:
        if len(x) == 0:
            return
        peak = float(np.max(np.abs(x)))
        rms = float(np.sqrt(np.mean(x * x)))
        self.peak_db = 20 * np.log10(max(peak, 1e-6))
        db = 20 * np.log10(max(rms, 1e-6))
        # Smooth the RMS a little so the meter is readable.
        self.rms_db = db if db > self.rms_db else 0.7 * self.rms_db + 0.3 * db
        now = time.monotonic()
        if peak == 0.0:
            if self._zero_since is None:
                self._zero_since = now
            self.all_zero_s = now - self._zero_since
        else:
            self._zero_since = None
            self.all_zero_s = 0.0


# Live capture --------------------------------------------------------------------
class AudioCapture:
    """Captures from a named device, picks a channel, resamples to 16 kHz, feeds a sink.

    The PortAudio callback only copies data into a queue; resampling and the sink run on
    a separate thread so the callback never blocks.
    """

    def __init__(self, sink: Sink):
        self.sink = sink
        self.level = Level()
        self.device_name: str | None = None
        self.channel = "mono"
        self.stream: sd.InputStream | None = None
        self.active_device: dict | None = None
        self.error: str | None = None
        self.overflows = 0
        self._q: queue.Queue = queue.Queue(maxsize=500)
        self._lock = threading.RLock()
        self._resampler = None
        self._consumer = threading.Thread(target=self._consume, name="audio-consumer", daemon=True)
        self._consumer.start()

    # Control ----------------------------------------------------------------
    def configure(self, device_name: str | None, channel: str) -> None:
        with self._lock:
            changed = device_name != self.device_name or channel != self.channel
            self.device_name = device_name
            self.channel = channel
            if changed and self.stream is not None:
                self.start()

    def start(self) -> None:
        with self._lock:
            self._close()
            self.error = None
            try:
                dev = self._resolve_device()
                if dev is None:
                    self.error = f"Input device not found: {self.device_name!r}. Plug it in or choose another."
                    self.active_device = None
                    return
                n_ch = dev["channels"]
                sr = int(dev["samplerate"])
                self._native_sr = sr
                self._n_ch = n_ch
                self._resampler = soxr.ResampleStream(sr, TARGET_SR, 1, dtype="float32", quality="HQ")
                self.stream = sd.InputStream(
                    device=dev["index"],
                    channels=n_ch,
                    samplerate=sr,
                    dtype="float32",
                    blocksize=int(sr * 0.02),
                    callback=self._callback,
                )
                self.stream.start()
                self.active_device = dev
                log.info("capturing from %r (%d ch @ %d Hz), channel=%s", dev["name"], n_ch, sr, self.channel)
            except Exception as exc:
                self.error = f"Could not open input device: {exc}"
                log.exception("audio start")
                self._close()

    def stop(self) -> None:
        with self._lock:
            self._close()
            self.active_device = None

    @property
    def running(self) -> bool:
        return self.stream is not None and self.stream.active

    def _close(self) -> None:
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None

    def refresh_devices(self) -> None:
        """Called on hot-plug: re-init PortAudio and reopen the stream if we were running."""
        with self._lock:
            was_running = self.stream is not None or (self.error is not None and "not found" in self.error)
            self._close()
            try:
                reinit_portaudio()
            except Exception:
                log.exception("PortAudio re-init")
            if was_running:
                self.start()

    def _resolve_device(self) -> dict | None:
        devices = list_input_devices()
        if not devices:
            return None
        if self.device_name:
            for d in devices:
                if d["name"] == self.device_name:
                    return d
            return None
        for d in devices:
            if d["default"]:
                return d
        return devices[0]

    # Data path ---------------------------------------------------------------
    def _callback(self, indata, frames, time_info, status) -> None:
        if status.input_overflow:
            self.overflows += 1
        try:
            self._q.put_nowait((indata.copy(), time.monotonic()))
        except queue.Full:
            self.overflows += 1

    def close(self) -> None:
        """Stop capture and the consumer thread, and drop the resampler (clean interpreter exit)."""
        self.stop()
        self._q.put(None)
        self._consumer.join(timeout=2)
        self._resampler = None

    def _consume(self) -> None:
        while True:
            item = self._q.get()
            if item is None:
                return
            data, t = item
            resampler = None
            try:
                if self.channel == "left" or data.shape[1] == 1:
                    mono = data[:, 0]
                elif self.channel == "right":
                    mono = data[:, 1]
                else:
                    mono = data.mean(axis=1)
                self.level.update(mono)
                resampler = self._resampler
                if resampler is None:
                    continue
                out = resampler.resample_chunk(np.ascontiguousarray(mono, dtype=np.float32))
                if len(out):
                    self.sink(out, t)
            except Exception:
                log.exception("audio consumer")
            finally:
                del resampler  # do not keep the resampler alive between chunks


# File playback (test mode) ---------------------------------------------------------
def load_audio_file(path: str | Path) -> np.ndarray:
    """Decode any audio/video file to 16 kHz mono float32."""
    path = Path(path)
    try:
        import soundfile as sf

        data, sr = sf.read(str(path), dtype="float32", always_2d=True)
        mono = data.mean(axis=1)
        if sr != TARGET_SR:
            mono = soxr.resample(mono, sr, TARGET_SR, quality="HQ")
        return mono.astype(np.float32)
    except Exception:
        if not shutil.which("ffmpeg"):
            raise RuntimeError(f"Cannot decode {path}; install ffmpeg (brew install ffmpeg) for this format")
        raw = subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-i",
                str(path),
                "-ac",
                "1",
                "-ar",
                str(TARGET_SR),
                "-f",
                "f32le",
                "-",
            ],
            check=True,
            capture_output=True,
        ).stdout
        return np.frombuffer(raw, dtype=np.float32).copy()


class FilePlayer(threading.Thread):
    """Feeds a decoded file to the sink in 20 ms chunks, paced in real time (or faster)."""

    def __init__(self, audio: np.ndarray, sink: Sink, speed: float = 1.0, on_done: Callable[[], None] | None = None):
        super().__init__(name="file-player", daemon=True)
        self.audio = audio
        self.sink = sink
        self.speed = speed
        self.on_done = on_done
        self.level = Level()
        self._stop = threading.Event()
        self.position_s = 0.0

    def run(self) -> None:
        chunk = int(TARGET_SR * 0.02)
        t_start = time.monotonic()
        for i in range(0, len(self.audio), chunk):
            if self._stop.is_set():
                break
            piece = self.audio[i : i + chunk]
            target = t_start + (i + len(piece)) / TARGET_SR / self.speed
            delay = target - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            self.position_s = (i + len(piece)) / TARGET_SR
            self.level.update(piece)
            self.sink(piece, time.monotonic())
        # Trailing silence so the last utterance gets finalized.
        silence = np.zeros(chunk, dtype=np.float32)
        for _ in range(int(1.5 / 0.02)):
            if self._stop.is_set():
                break
            time.sleep(0.02 / self.speed)
            self.sink(silence, time.monotonic())
        if self.on_done:
            self.on_done()

    def stop(self) -> None:
        self._stop.set()
