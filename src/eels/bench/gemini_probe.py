"""Stream audio to Gemini Live Translate the way eels does and print what comes back.

  uv run python -m eels.bench.gemini_probe --mic                 # speak; Ctrl+C when done
  uv run python -m eels.bench.gemini_probe FILE [--seconds 60]   # a file, in real time
  options: --target tr|en  --echo  --bare (no program instruction)  --extra "text" (append to it)
           --verbose (every message with timestamps)

At the end it prints the whole input transcript and the whole translation.
"""

from __future__ import annotations

import argparse
import asyncio
import signal
import time

import numpy as np

from ..cloud import FRAME_SAMPLES, GEMINI_MODEL, api_key, to_pcm16
from ..streaming import SAMPLE_RATE


async def mic_frames(frame_samples: int, stop: asyncio.Event):
    """Default input device at 16 kHz mono, in frame_samples blocks, until stop is set."""
    import sounddevice as sd

    loop = asyncio.get_running_loop()
    q: asyncio.Queue = asyncio.Queue()

    def cb(indata, frames, t, status):
        loop.call_soon_threadsafe(q.put_nowait, indata[:, 0].copy())

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32", blocksize=frame_samples, callback=cb):
        print("Listening. Speak now; press Ctrl+C when done.", flush=True)
        while not stop.is_set():
            yield await q.get()


async def file_frames(path: str, seconds: float, frame_samples: int):
    from ..audio import load_audio_file

    audio = load_audio_file(path)[: int(seconds * SAMPLE_RATE)]
    t0 = time.monotonic()
    for i in range(0, len(audio), frame_samples):
        yield audio[i : i + frame_samples]
        wait = t0 + (i + frame_samples) / SAMPLE_RATE - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)


async def probe(args) -> None:
    from google import genai
    from google.genai import types

    config = types.LiveConnectConfig(
        response_modalities=[types.Modality.AUDIO],
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        translation_config=types.TranslationConfig(target_language_code=args.target, echo_target_language=args.echo),
    )
    if not args.bare:
        from .. import hints
        from .. import schedule as sched

        config.system_instruction = hints.gemini_instruction(sched.load()) + (" " + args.extra if args.extra else "")
    config.session_resumption = types.SessionResumptionConfig()
    config.context_window_compression = types.ContextWindowCompressionConfig(sliding_window=types.SlidingWindow())
    t0 = time.monotonic()
    ins: list[str] = []
    outs: list[str] = []
    mic_off = asyncio.Event()  # Ctrl+C in mic mode: stop listening, still collect the last replies
    done = asyncio.Event()
    asyncio.get_running_loop().add_signal_handler(signal.SIGINT, mic_off.set)

    def log(*parts) -> None:
        if args.verbose:
            print(f"{time.monotonic() - t0:6.2f}s", *parts, flush=True)

    from ..cloud import model_path
    from ..config import SettingsStore

    s = SettingsStore().value
    backend = "ai_studio" if args.ai_studio else "vertex"
    client = genai.Client(vertexai=backend == "vertex", api_key=api_key(backend))
    model = model_path(args.model, backend, s.gemini_vertex_project, s.gemini_vertex_location)
    log(f"account: {backend}, model: {model}")
    async with client.aio.live.connect(model=model, config=config) as session:
        log("connected")

        async def send():
            frames = (
                mic_frames(FRAME_SAMPLES, mic_off) if args.mic else file_frames(args.file, args.seconds, FRAME_SAMPLES)
            )
            async for f in frames:
                if mic_off.is_set():
                    break
                await session.send_realtime_input(
                    audio=types.Blob(data=to_pcm16(np.asarray(f)), mime_type="audio/pcm;rate=16000")
                )
            log("audio done")
            print("Waiting a few seconds for the last translation...", flush=True)
            await asyncio.sleep(6)
            done.set()

        async def receive():
            while not done.is_set():
                async for msg in session.receive():
                    sc = msg.server_content
                    if sc and sc.input_transcription and sc.input_transcription.text:
                        ins.append(sc.input_transcription.text)
                        log("IN ", repr(sc.input_transcription.text), sc.input_transcription.language_code)
                    if sc and sc.output_transcription and sc.output_transcription.text:
                        outs.append(sc.output_transcription.text)
                        log("OUT", repr(sc.output_transcription.text))
                    if msg.go_away:
                        log("go_away", msg.go_away.time_left)
                    if done.is_set():
                        break

        receiver = asyncio.create_task(receive())
        await send()
        receiver.cancel()
    print("\nINPUT: ", "".join(ins).strip())
    print("\nOUTPUT:", "".join(outs).strip())


def main() -> int:
    ap = argparse.ArgumentParser(description="Stream audio to Gemini Live Translate and print the replies.")
    ap.add_argument("file", nargs="?")
    ap.add_argument("--mic", action="store_true", help="stream from the default microphone instead of a file")
    ap.add_argument("--target", default="tr", help="target language code (default tr)")
    ap.add_argument("--seconds", type=float, default=60.0, help="file mode: how much of the file")
    ap.add_argument("--model", default=GEMINI_MODEL)
    ap.add_argument("--echo", action="store_true", help="echo_target_language on (eels with a fixed language)")
    ap.add_argument(
        "--ai-studio", action="store_true", help="use the AI Studio key instead of Google Cloud (Vertex AI)"
    )
    ap.add_argument("--extra", help="text appended to the program instruction (to try glossary lines)")
    ap.add_argument("--bare", action="store_true", help="without the program as system instruction")
    ap.add_argument("--verbose", action="store_true", help="print every message with timestamps")
    args = ap.parse_args()
    if not args.mic and not args.file:
        ap.error("give a FILE or --mic")
    if not api_key("ai_studio" if args.ai_studio else "vertex"):
        print("No Gemini key: store it in the Keychain (README, Gemini engine) or set GEMINI_API_KEY.")
        return 1
    asyncio.run(probe(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
