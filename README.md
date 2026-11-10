# eels

*"My hovercraft is full of eels."*

The name comes from Monty Python's "Dirty Hungarian Phrasebook" sketch (1970), where a tourist's deliberately mistranslated phrasebook makes him say that line instead of what he meant. eels tries to be the opposite of that phrasebook.

Live subtitles for Python Pizza Istanbul (14 November 2026): English talks get Turkish subtitles, Turkish talks get English ones. Shown by OBS as a transparent 1920 x 180 web page. Runs offline on one Apple Silicon Mac.

- Speech recognition: Whisper large-v3-turbo (MLX, GPU).
- Translation: Opus-MT (CPU) by default; TranslateGemma or Tencent HY-MT (GPU) selectable per direction.

## Setup (once, with internet)

Needs macOS on Apple Silicon, [uv](https://docs.astral.sh/uv/) and `ffmpeg` (`brew install uv ffmpeg`).

```sh
uv sync
uv run eels download-models   # ~3 GB; --all adds the benchmark candidates (~19 GB)
```

## Run

```sh
uv run eels                   # --no-autostart to wait for the Start button
```

It prints the control panel URL (`http://localhost:8000/control`) and the OBS URL (`http://<mac-ip>:8000/`). On first run, allow microphone access for the terminal and incoming connections for Python. A denied microphone shows as a red message in the control panel.

## OBS

- Browser source URL: the printed `http://<mac-ip>:8000/` (prefer the wired one). Size 1920 x 180. Keep the existing custom CSS.
- Leave "Refresh browser when scene becomes active" off; the page reconnects by itself.
- Network check: open `http://<mac-ip>:8000/health` from the OBS computer. If only the Mac can open it, the network blocks device-to-device traffic: use a cable or our own router.
- Look check: **Show test text** in the control panel.

## Control panel

- Start / stop.
- Audio input: device (updates on plug/unplug), channel, level meter, speech indicator, **Lift quiet input** (up to +26 dB).
- Spoken language: English, Turkish or Detect. **Follow schedule** sets it per session; a manual change holds until the next session. **Gender-neutral**: "they" in English unless the Turkish names a gender.
- On screen: show/hide, clear, test text, font size, lines, clear after silence, shadow, offset, **Live preview text** (dimmed sentence-in-progress; off = final sentences only, a few seconds later).
- Keeping up: delays, model timings, worker status and errors. More than 6 s behind skips to live audio.
- Captions for recordings: SRT download for a time range.
- Models: speech model and translation model per direction, switched while running without pausing subtitles.

Settings persist in `var/settings.json`.

## Test with a file

```sh
uv run eels play talk.mp3 [--speed 2]
```

## Transcripts and SRT

Final subtitles go to `var/transcripts/YYYY-MM-DD.jsonl` (Istanbul date), with times, source, translation, models, why the sentence was cut, delay and name corrections.

```sh
uv run eels export-srt --date 2026-11-14 --from 11:15 --to 11:40 -o keynote1.srt   # --text source|translation|both, --offset S
```

## Schedule and vocabulary

- Agenda: `src/eels/data/schedule.json`; refresh with `uv run eels update-schedule`.
- Names per talk (libraries, tools): `src/eels/data/program_terms.json`. Used as Whisper's hint, protected from translation, and for correcting misheard names.

## How it works

```
mic -> 16 kHz -> auto gain -> Silero VAD -> Whisper every ~0.5 s (LocalAgreement-2)
    -> whole sentences -> name correction -> translation -> WebSocket -> overlay
```

- Speech and translation run in supervised worker processes; a crash restarts the worker, the rest keeps running.
- Whole sentences are translated (Turkish is verb-final); a pause-period from Whisper does not end a sentence if the speaker continues.
- Memory: MLX cache capped at 512 MB per worker; a watchdog restarts a worker that grows past 1.6x its post-load size.
- Details and measurements: `docs/findings/FINDINGS.md`.

## Benchmarks

```sh
uv run eels fetch-bench-audio                 # public talk excerpts
uv run eels benchmark --quick --asr ... --mt ... --pipeline ASR+MT [--soak 60]
uv run python -m eels.bench.captioned fetch   # talks by Turkish speakers, some with human captions
uv run python -m eels.bench.captioned run --asr ... --mt ...
```

Reports are copied to `docs/findings/benchmarks/`. Candidate names: `src/eels/bench/candidates.py`.

## Pre-event checklist

### On the M4 Pro (pick models by measuring; Air results are only a starting point)

1. `git pull`, `uv sync`, `uv run pytest`.
2. `uv run eels download-models --all`, `uv run eels fetch-bench-audio`, `uv run python -m eels.bench.captioned fetch`.
3. Quality, judged per direction:
   ```sh
   uv run python -m eels.bench.captioned run \
     --asr turbo-750 turbo-full large-v3-750 large-v3-full \
     --mt opus-mt opus-mt-gpu opus-mt-beam4 hymt1.8b hymt7b tg12b
   ```
4. Speed (preview within ~1-2 s, final within ~1-2 s of a sentence end, no skipped audio):
   ```sh
   uv run eels benchmark --quick --asr turbo-750 turbo-full large-v3-750 \
     --mt opus-mt opus-mt-gpu hymt1.8b hymt7b tg12b \
     --pipeline turbo-750+opus-mt turbo-full+opus-mt turbo-750+hymt7b large-v3-750+opus-mt
   ```
   Also try `asr_step_s: 0.3` and `asr_audio_ctx: "full"` in `var/settings.json`.
5. Set the choice in the control panel, then a 60-minute soak: `uv run eels benchmark --pipeline <asr>+<mt> --soak 60`.
6. Wi-Fi off: the app must start and `play` a file.
7. Commit `docs/findings/`.

### On the day

- [ ] Mac plugged in, Low Power Mode off, display sleep off, Focus mode on.
- [ ] Wired network; note the printed URL; `http://<ip>:8000/health` works from the OBS computer.
- [ ] OBS source set, test text visible in all three scenes.
- [ ] Control panel: right device and channel, meter moves, speech dot lights up, no red messages.
- [ ] Follow schedule on; check the first talk's language.
- [ ] Afterwards: export SRTs, keep `var/transcripts/`.

## Development

`uv run pytest` (no models needed). Code in `src/eels/`; agent notes in `CLAUDE.md`.

Licenses: Open Sans (OFL 1.1), Silero VAD (MIT), Whisper (MIT), Opus-MT (CC-BY 4.0: credit "Translations by Opus-MT, University of Helsinki" when publishing captions), TranslateGemma (Gemma Terms), HY-MT (Tencent HY Community License, excludes EU/UK/South Korea).
