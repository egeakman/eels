# Benchmark 2026-11-09 16:57

MacBook Air (Apple M4, 10 GPU cores, 16 GB), macOS 27.2, on AC.

## Speech recognition (streaming simulation, one model on the GPU)

| Candidate | Clip | ms per run (p95) | Step s | First text s (p50/p95) | Final text s (p50/p95) | Rewrites | WER vs large-v3 |
|---|---|---|---|---|---|---|---|
| turbo-750 | en_pizza_music | 952 (1160) | 1.72 | 1.6 / 3.44 | 3.71 / 5.95 | 6% | 1.8% |
| turbo-750 | en_pycon_shaw | 907 (1105) | 1.63 | 1.66 / 2.77 | 3.82 / 5.63 | 14% | 2.7% |
| turbo-750 | tr_meetup66 | 869 (1024) | 1.47 | 2.19 / 5.48 | 5.73 / 9.93 | 37% | 67.2% |
| turbo-750 | tr_meetup72 | 905 (1149) | 1.46 | 1.77 / 4.35 | 3.46 / 7.45 | 18% | 21.9% |

WER is measured against an offline large-v3 transcript, not a human one: it shows agreement, not accuracy.

## Full pipeline in real time (ASR and MT sharing the GPU, 90 s excerpts)

| Pair | Clip | First text s (p50/p95) | Final text s (p50/p95) | ASR ms / step s | MT ms | Skips |
|---|---|---|---|---|---|---|
| turbo-750+opus-mt | en_pizza_music | 1.03 / 1.35 | 2.49 / 3.3 | 763.0 / 1.15 | 83.0 | 0 |
| turbo-750+opus-mt | en_pycon_shaw | 0.9 / 1.62 | 2.23 / 4.74 | 734.0 / 1.07 | 89.0 | 0 |
| turbo-750+opus-mt | tr_meetup66 | 1.05 / 3.49 | 4.12 / 8.39 | 689.0 / 1.32 | 149.0 | 0 |
| turbo-750+opus-mt | tr_meetup72 | 0.77 / 1.29 | 1.58 / 4.45 | 550.0 / 0.87 | 95.0 | 0 |
| turbo-750+tg4b | en_pizza_music | 3.74 / 4.68 | 6.96 / 8.31 | 1504.0 / 2.76 | 1138.0 | 0 |
| turbo-750+tg4b | en_pycon_shaw | 2.34 / 3.84 | 5.43 / 9.38 | 1292.0 / 2.47 | 1130.0 | 0 |
| turbo-750+tg4b | tr_meetup66 | 2.03 / 3.28 | 5.52 / 10.54 | 977.0 / 1.65 | 826.0 | 0 |
| turbo-750+tg4b | tr_meetup72 | 1.44 / 2.84 | 3.73 / 7.96 | 850.0 / 1.68 | 904.0 | 0 |
