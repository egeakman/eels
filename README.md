# eels

*"My hovercraft is full of eels."*

The name comes from Monty Python's "Dirty Hungarian Phrasebook" sketch (1970), where a tourist's deliberately mistranslated phrasebook makes him say that line instead of what he meant. eels tries to be the opposite of that phrasebook.

Live subtitles for Python Pizza Istanbul (14 November 2026): English talks get Turkish subtitles, Turkish talks get English ones. Shown by OBS as a transparent 1920 x 180 web page. Runs on one Apple Silicon Mac, two engines:

- **Local** (offline): Whisper large-v3-turbo (MLX, GPU) + Opus-MT (CPU); TranslateGemma or Tencent HY-MT (GPU) selectable per direction.
- **Gemini Live Translate** (cloud): speech in, translation out. The local models stay loaded and take over if it fails.

## Setup (once, with internet)

Needs macOS on Apple Silicon, [uv](https://docs.astral.sh/uv/) and `ffmpeg` (`brew install uv ffmpeg`).

```sh
uv sync
uv run eels download-models   # ~3 GB; --all adds the models worth comparing (~19 GB)
```

## Run

```sh
uv run eels                   # waits for Start in the control panel; --autostart starts right away
```

It prints the control panel URL (`http://localhost:8000/control`) and the OBS URL (`http://<mac-ip>:8000/`). On first run, allow microphone access for the terminal and incoming connections for Python. A denied microphone shows as a red message in the control panel.

## Gemini engine

1. Use a Gemini API key from a project with billing enabled (on the free tier Google may use the talk audio to improve its products).
2. In the control panel: Setup, **Gemini**, Key. It is saved in this Mac's Keychain. (`GEMINI_API_KEY` in the environment also works and wins.)
3. Control panel, Schedule and models, Engine: **Gemini Live Translate**.

- Needs internet (wired). About $0.04 per minute of speech; the panel shows a running estimate.
- Failover: if Gemini is disconnected for 5 s, or 12 s of speech get no translation, the local models take over (red banner). Gemini takes over again after 20 s of working normally.
- **Keep local models loaded** (Engine card, shown with Gemini; on by default): about 3 GB for an instant fallback. Off: they are unloaded while Gemini runs and load in about 3 s when it fails.
- In a talk with a fixed language, speech already in the subtitle language (an English quote in a Turkish talk) is shown as spoken. Detect mode leaves it out.
- Gemini gets the day's program as its instruction (names to keep, talks, no filler sounds, they for unknown gender, Turkish conference terms such as sprint and keynote); it is not billed and fixes name spelling. Glossary: `glossary_tr` in `src/eels/data/program_terms.json`.
- Kept: schedule, name correction, gender-neutral, live preview, transcripts and SRT.
- See what Gemini returns: `uv run python -m eels.bench.gemini_probe talk.mp3 --target tr`.

## OBS

- Browser source URL: the printed `http://<mac-ip>:8000/` (prefer the wired one). Size 1920 x 180. Keep the existing custom CSS.
- Leave "Refresh browser when scene becomes active" off; the page reconnects by itself.
- Network check: open `http://<mac-ip>:8000/health` from the OBS computer. If only the Mac can open it, the network blocks device-to-device traffic: use a cable or our own router.
- Look check: **Show test text** in the control panel.

## Control panel

One screen, no scrolling:

- Top: run state, current and next talk, Start / Stop.
- The projector's view, with everything that changes the subtitles under it: show/hide, clear, test text, live preview, size, lines, clear after silence, position, shadow.
- Left: keeping up (status, delays, Gemini cost or local timings) and recent events.
- Middle: spoken language (English, Turkish, Detect; follow schedule; gender-neutral English) and engine (**Local** or **Gemini**; with Gemini the local models are its backup: changeable while kept loaded, locked while unloaded).
- Right: audio input (device, channel, level, speech, lift quiet input).
- Setup bar, each opens a panel: Gemini (key, your instructions; Apply asks to confirm and reconnects Gemini), local models, captions for recordings (SRT), schedule, test with a file.

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
uv run python -m eels.bench.captioned run --gemini [--asr whisper-turbo-15s --mt opus-mt]   # real time, ~$1.30
```

Reports are copied to `docs/findings/benchmarks/`. Models are named by their key in `src/eels/models.py` (the catalog: name, variant, notes, what to download).

## Pre-event checklist

### On the M4 Pro (pick models by measuring; Air results are only a starting point)

1. `git pull`, `uv sync`, `uv run pytest`.
2. `uv run eels download-models --all`, `uv run eels fetch-bench-audio`, `uv run python -m eels.bench.captioned fetch`.
3. Quality, judged per direction:
   ```sh
   uv run python -m eels.bench.captioned run \
     --asr whisper-turbo-15s whisper-turbo-30s whisper-large-v3-15s whisper-large-v3-30s \
     --mt opus-mt opus-mt-gpu opus-mt-beam4 hymt-1.8b hymt-7b translategemma-12b
   ```
4. Speed (preview within ~1-2 s, final within ~1-2 s of a sentence end, no skipped audio):
   ```sh
   uv run eels benchmark --quick --asr whisper-turbo-15s whisper-turbo-30s whisper-large-v3-15s \
     --mt opus-mt opus-mt-gpu hymt-1.8b hymt-7b translategemma-12b \
     --pipeline whisper-turbo-15s+opus-mt whisper-turbo-30s+opus-mt whisper-turbo-15s+hymt-7b
   ```
   Also try `asr_step_s: 0.3` in `var/settings.json`.
5. Set the choice in the control panel, then a 60-minute soak: `uv run eels benchmark --pipeline <asr>+<mt> --soak 60`.
6. Gemini: store the key (see "Gemini engine"), run the probe on one clip, then
   `uv run python -m eels.bench.captioned run --gemini --asr whisper-turbo-15s --mt opus-mt` and compare the side by side.
   With engine Gemini, `play` a 30-minute file (crosses Gemini's 10- and 15-minute session limits); subtitles must not stop.
7. Network off: the app must start and `play` a file; with engine Gemini, the local models take over.
8. Commit `docs/findings/`.

### On the day

- [ ] Mac plugged in, Low Power Mode off, display sleep off, Focus mode on.
- [ ] Wired network; note the printed URL; `http://<ip>:8000/health` works from the OBS computer.
- [ ] OBS source set, test text visible in all three scenes.
- [ ] Control panel: right device and channel, meter moves, speech dot lights up, no red messages.
- [ ] Follow schedule on; check the first talk's language.
- [ ] Press **Start** in the control panel (eels waits for it).
- [ ] With Gemini: key in the Keychain, Engine shows "On screen", internet works.
- [ ] Afterwards: export SRTs, keep `var/transcripts/`.

## Development

`uv run pytest` (no models needed). Code in `src/eels/`; agent notes in `CLAUDE.md`.

Licenses: Open Sans (OFL 1.1), Silero VAD (MIT), Whisper (MIT), Opus-MT (CC-BY 4.0: credit "Translations by Opus-MT, University of Helsinki" when publishing captions), TranslateGemma (Gemma Terms), HY-MT (Tencent HY Community License, excludes EU/UK/South Korea), Gemini (Gemini API Terms of Service).
