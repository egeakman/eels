# Benchmark 2026-11-09 17:24

MacBook Air (Apple M4, 10 GPU cores, 16 GB), macOS 27.2, on AC.

## Speech recognition (streaming simulation, one model on the GPU)

| Candidate | Clip | ms per run (p95) | Step s | First text s (p50/p95) | Final text s (p50/p95) | Rewrites | WER vs large-v3 |
|---|---|---|---|---|---|---|---|
| small-750 | en_pizza_music | 275 (389) | 0.50 | 0.5 / 1.22 | 1.58 / 3.12 | 11% | 4.0% |
| small-750 | en_pycon_shaw | 272 (363) | 0.50 | 0.56 / 1.41 | 1.7 / 3.46 | 16% | 10.4% |
| small-750 | tr_meetup66 | 349 (1263) | 0.86 | 1.23 / 5.35 | 4.77 / 8.47 | 58% | 83.6% |
| small-750 | tr_meetup72 | 250 (346) | 0.50 | 0.78 / 3.65 | 1.9 / 4.18 | 46% | 54.3% |
| medium-750 | en_pizza_music | 919 (1228) | 1.61 | 1.56 / 2.79 | 3.56 / 5.28 | 3% | 1.8% |
| medium-750 | en_pycon_shaw | 851 (1108) | 1.52 | 1.44 / 3.04 | 3.24 / 5.24 | 5% | 3.2% |
| medium-750 | tr_meetup66 | 858 (1300) | 1.57 | 2.1 / 4.44 | 4.8 / 7.36 | 38% | 64.2% |
| medium-750 | tr_meetup72 | 902 (1400) | 1.74 | 1.77 / 4.37 | 3.54 / 6.57 | 19% | 25.8% |
| turbo-750 | en_pizza_music | 870 (995) | 1.39 | 1.58 / 2.83 | 3.7 / 5.62 | 3% | 2.2% |
| turbo-750 | en_pycon_shaw | 832 (918) | 1.47 | 1.37 / 2.44 | 3.46 / 5.48 | 15% | 3.6% |
| turbo-750 | tr_meetup66 | 856 (946) | 1.43 | 1.91 / 4.92 | 4.67 / 6.56 | 34% | 68.7% |
| turbo-750 | tr_meetup72 | 843 (986) | 1.51 | 1.68 / 4.01 | 3.57 / 6.15 | 18% | 15.9% |

WER is measured against an offline large-v3 transcript, not a human one: it shows agreement, not accuracy.
