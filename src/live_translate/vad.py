"""Silero VAD (v5/v6 ONNX) on 16 kHz audio, run with onnxruntime on the CPU (~0.1 ms per frame)."""

from __future__ import annotations

import numpy as np
import onnxruntime

from .config import DATA_DIR

FRAME = 512  # samples per VAD frame at 16 kHz (32 ms)
CONTEXT = 64


class SileroVAD:
    def __init__(self, path=DATA_DIR / "silero_vad.onnx"):
        opts = onnxruntime.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        self.session = onnxruntime.InferenceSession(
            str(path), sess_options=opts, providers=["CPUExecutionProvider"]
        )
        self._sr = np.array(16000, dtype=np.int64)
        self.reset()

    def reset(self) -> None:
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros((1, CONTEXT), dtype=np.float32)
        self._rest = np.zeros(0, dtype=np.float32)

    def frame_prob(self, frame: np.ndarray) -> float:
        x = np.concatenate([self._context, frame.reshape(1, FRAME)], axis=1)
        out, self._state = self.session.run(
            None, {"input": x, "state": self._state, "sr": self._sr}
        )
        self._context = x[:, -CONTEXT:]
        return float(out[0, 0])

    def process(self, audio: np.ndarray) -> list[tuple[np.ndarray, float]]:
        """Split audio into 512-sample frames (carrying the remainder) and return (frame, prob) pairs."""
        buf = np.concatenate([self._rest, audio.astype(np.float32, copy=False)])
        n = len(buf) // FRAME
        out = []
        for i in range(n):
            frame = buf[i * FRAME : (i + 1) * FRAME]
            out.append((frame, self.frame_prob(frame)))
        self._rest = buf[n * FRAME :]
        return out


class SpeechGate:
    """Hysteresis on top of per-frame probabilities.

    Reports speech start, short pauses (for clause flushing) and utterance end.
    """

    def __init__(self, on: float = 0.5, off: float = 0.35, pre_roll_frames: int = 10):
        self.on = on
        self.off = off
        self.pre_roll_frames = pre_roll_frames
        self.in_speech = False
        self.silence_s = 0.0
        self.pre_roll: list[np.ndarray] = []

    def update(self, frame: np.ndarray, prob: float) -> tuple[str | None, list[np.ndarray]]:
        """Returns (event, audio_to_feed). Event is 'start', 'silence' or None."""
        dur = FRAME / 16000
        if not self.in_speech:
            if prob >= self.on:
                self.in_speech = True
                self.silence_s = 0.0
                feed = self.pre_roll + [frame]
                self.pre_roll = []
                return "start", feed
            self.pre_roll.append(frame)
            if len(self.pre_roll) > self.pre_roll_frames:
                self.pre_roll.pop(0)
            return None, []
        if prob < self.off:
            self.silence_s += dur
        else:
            self.silence_s = 0.0
        return None, [frame]

    def end(self) -> None:
        self.in_speech = False
        self.silence_s = 0.0
        self.pre_roll = []


class AutoGain:
    """Slow automatic gain so quiet inputs still trigger the VAD.

    Estimates the level of the loud part of the last ~10 s (90th percentile of 32 ms frame
    RMS) and moves the gain toward target/level, between 1x and max_gain. Near-silence
    (below floor) is never boosted, so breaks do not amplify room noise.
    """

    def __init__(self, target_db: float = -24.0, max_gain_db: float = 26.0, floor_db: float = -62.0):
        self.target = 10 ** (target_db / 20)
        self.max_gain = 10 ** (max_gain_db / 20)
        self.floor = 10 ** (floor_db / 20)
        self.gain = 1.0
        self._levels = np.zeros(310, dtype=np.float32)
        self._i = 0
        self._n = 0

    @property
    def gain_db(self) -> float:
        return float(20 * np.log10(self.gain))

    def process(self, x: np.ndarray) -> np.ndarray:
        for start in range(0, len(x), FRAME):
            frame = x[start : start + FRAME]
            if len(frame) == 0:
                break
            self._levels[self._i] = float(np.sqrt(np.mean(frame * frame)))
            self._i = (self._i + 1) % len(self._levels)
            self._n = min(self._n + 1, len(self._levels))
        level = float(np.percentile(self._levels[: self._n], 90)) if self._n else 0.0
        want = 1.0 if level < self.floor else min(self.max_gain, max(1.0, self.target / level))
        # Smooth: about 1 s to settle, a bit faster when lowering to avoid clipping.
        rate = 0.25 if want < self.gain else 0.05
        self.gain += (want - self.gain) * rate
        if self.gain <= 1.001:
            return x
        return np.clip(x * self.gain, -1.0, 1.0)
