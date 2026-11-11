# eels: notes for agents

Live EN<->TR subtitles for Python Pizza Istanbul (Sat 14 Nov 2026), a 1920x180 transparent OBS browser source, offline on one Mac. Usage: `README.md`. Measurements, decisions, open questions: `docs/findings/FINDINGS.md`.

## Where things stand

- Developed on a MacBook Air M4 (16 GB, fanless). **The event machine is an M4 Pro (24 GB).** Final model and parameter choices are made there (README, "Pre-event checklist"); Air numbers may not hold.
- Defaults: Whisper large-v3-turbo (MLX, 15 s window) + Opus-MT (CTranslate2, CPU), whole sentences, live preview on, gender-neutral TR->EN.
- Engine "gemini" (`cloud.py`): Gemini Live Translate (`gemini-3.5-live-translate-preview`, google-genai pinned <3). One live session per target language; the local pipeline stays loaded and `Failover` switches to it when Gemini is down. Gemini must never block or slow the local fallback. Its system instruction (`hints.gemini_instruction`, the day's program) is accepted and not billed (measured); it fixes name spelling and follows a glossary of real Turkish terms (`glossary_tr` in program_terms.json), not made-up words.

## Commands

```sh
uv sync                       # Python 3.13 pinned
uv run pytest                 # no models needed
uv run eels                   # control panel: http://localhost:8000/control
uv run eels play FILE
uv run eels download-models [--all]
uv run eels fetch-bench-audio
uv run eels benchmark ...     # reports copied to docs/findings/benchmarks/
uv run python -m eels.bench.captioned fetch|run --asr ... --mt ... [--gemini]
uv run python -m eels.bench.gemini_probe FILE    # raw Gemini replies (key: Keychain item eels-gemini or GEMINI_API_KEY)
```

## Data models

- `models.py`: the model catalog (`ModelInfo`: key, job, name, variant, runs on, approx size, note, worker spec, downloads). Settings, CLI and benchmarks use the keys; old settings files are migrated (`config.migrate_settings`).
- `status.py`: everything the control panel receives (`Status` in sections), events, overlay subtitles.
- `transcript.py`: `TranscriptRecord`, the same fields for both engines; older lines still load.
- `bench/clips.py`: benchmark audio excerpts.

## Do not undo

- **MLX buffer cache** grows up to ~RAM per process (swapped a 16 GB Mac to 48 GB). Workers cap it at 512 MB (`EELS_MLX_CACHE_MB`); no speed cost.
- **Whisper copies its prompt's style.** Ellipses spiralled into "..." subtitles; a bare name list dropped periods and Title-Cased Turkish. Prompts are punctuated sentences, ellipses stripped, context cleared after ~8 s of speech with no words.
- **Whisper puts a period at every pause.** Those words are `soft_end` and don't end a sentence if speech continues.
- **Timing uses audio capture time**, not processing time.
- **Translate whole sentences** (Turkish is verb-final). Live preview re-translates the growing sentence.
- Workers are spawned processes: scripts that create them need `if __name__ == "__main__":`. They exit with the parent and ignore Ctrl+C.
- `asr.py` runs one encoder pass; mlx-whisper's `transcribe()` runs two.
- The agent sandbox blocks running downloaded scripts; write the equivalent code.

## Conventions

- uv only. No em dashes in code files. The user makes their own commits.
- `var/` is git-ignored. Keep findings in `docs/findings/`.
- Never commit audio, models or the user's test transcripts.
