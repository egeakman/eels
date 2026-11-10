# Findings

Measured on the dev MacBook Air M4 (10 GPU cores, 16 GB, fanless), 2026-11-09, unless marked. The event Mac is an M4 Pro (24 GB): speed will differ, accuracy should carry over. Raw reports: `benchmarks/`.

## 1. Accuracy on real talks

4-minute excerpts with human captions (`bench/captioned.py`), Whisper large-v3-turbo, 15 s window. WER after normalising case, punctuation, apostrophes, circumflexes and number words.

| Talk | Language | WER live | WER offline |
|---|---|---|---|
| Elif Shafak, TED | English, Turkish speaker | 6.5% | 7.2% |
| Umit Ozkan, TEDx Ohio State | English, Turkish-born | 7.0% | 5.4% |
| "Sifirdan LLM Gelistirme" intro | Turkish, technical | 7.9% | 8.3% |
| Ahmet Turer, TEDxMETUAnkara | Turkish | 6.8% | 12.6% |
| Saffet Emre Tonguc, TEDxIstanbul | Turkish | 12.1% | 23.6% |

- Live streaming costs little vs offline; ~6-8% WER in both languages.
- Shafak translation (Opus-MT) vs the human Turkish: chrF 57.4 (free literary translation; rough check).
- Both English speakers are long-time English speakers; nervous Turkey-based developers will be harder (section 7).

Review of nine real talks: `review-2026-11-09-real-talks.md`.

**Organiser's 20-minute TV session (English, Opus-MT):** delay after last word median 1.75 s (p90 2.3 s); Detect right 123/123. Opus-MT dropped one of two sentences in 6 of 123 subtitles; input is now split into sentences. Weak on idioms ("running mate", "drug company" -> "uyuşturucu şirketi").

## 2. Speech models

| Model | ms per pass | Turkish | Verdict |
|---|---|---|---|
| large-v3-turbo, 15 s window | 830-870 | 16-20% vs large-v3 | **default** |
| large-v3-turbo, 30 s window | 1520-1910 | same | 2x slower on the Air; re-check on the Pro |
| large-v3, 15 s window | ~2100 | | too slow on the Air; try on the Pro |
| medium | 850-920 | 25.8% vs large-v3 | no faster, worse |
| small | 250-350 | 54.3% vs large-v3 | 3x the errors |
| turbo Turkish fine-tune (selimc) | ~800-900 | worse on exact script | drops spaces after periods |
| Qwen3-ASR | | FLEURS 8.3% vs turbo 5.5% | not tested |
| Parakeet, Canary | | no Turkish | unusable |

"vs large-v3" is agreement, not accuracy; prefer section 1.

## 3. Translation models

48 tech-talk sentences, own references (`bench/mt_sentences.tsv`), chrF:

| Model | EN->TR | TR->EN | ms/sentence | Notes |
|---|---|---|---|---|
| Opus-MT tc-big (CTranslate2 int8, CPU) | 71.3 | 71.9 | ~110 | **default**; faithful; word-sense slips |
| HY-MT1.5 1.8B (MLX 8-bit) | 64.1 | 66.1 | 380-630 | fluent, sometimes pads or changes meaning |
| TranslateGemma 12B (4-bit) | 69.5 | 66.2 | 1800-2800 | fluent, paraphrases |
| TranslateGemma 4B (4-bit) | 59.1 | 62.7 | 600-1000 | outright errors; invents meaning TR->EN |

References lean literal (favours Opus-MT); read `benchmarks/*/mt_review.md`. Opus-MT on MPS: same output, slower than CPU on the Air (GPU busy); re-check on the Pro.

## 4. Live pipeline

Opus-MT: first text 0.8-1.1 s. With TranslateGemma 4B on the GPU, Whisper slows ~2x and final text takes 3.6-6.0 s. Whole sentences: final text arrives at sentence end; live preview fills the gap.

## 5. Fixed problems

- **Memory to 48 GB, then swap:** MLX buffer cache capped at 512 MB per worker (no speed cost); watchdog at 1.6x post-load size. 10 model switches: no leak.
- **Subtitles of only "...":** no ellipses in the prompt, punctuation-only words dropped, context cleared after ~8 s of speech with no words.
- **Sentences cut in half (27%):** whole sentences; Whisper's pause-periods don't end a sentence if speech continues; capture-time clock.
- **Wrong direction in Detect:** stricter detection plus a Turkish-text check; schedule sets EN/TR per talk.
- **Gender:** he/she -> they unless the Turkish has a gender cue.
- **Program hint:** written as sentences (a bare name list dropped periods and Title-Cased Turkish). Fixes names; accuracy unchanged on average.
- **Name correction** (`names.py`): first version 16 of 23 corrections wrong; now 6, all right, over 919 sentences.

Old test sessions (619 subtitles): pauses inside sentences ~0.15 s, after sentences median 0.73 s, so the 1 s gap is safe. Sentences median 13-16 words EN, 5-7 TR, ~90% under 30 words.

## 6. Open for the M4 Pro

1. Accents: English talks by Turkey-based developers (`captioned.py` UNCAPTIONED clips); judge side by side.
2. Better speech model (turbo 30 s window, large-v3) at acceptable delay?
3. Translation per direction: Opus-MT vs HY-MT 1.8B/7B vs TranslateGemma 12B, on real talks. Speed is a requirement: final within ~1-2 s of sentence end.
4. 60-minute soak on the chosen setup.
5. Speech model per language, only if one model is clearly better for one language.
6. Hybrid translation: Opus-MT preview, better model for the final sentence; either prompt for minimal changes or animate only changed words.
