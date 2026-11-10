# Benchmark 2026-11-09 17:14

MacBook Air (Apple M4, 10 GPU cores, 16 GB), macOS 27.2, on AC.

## Full pipeline in real time (ASR and MT sharing the GPU, 90 s excerpts)

| Pair | Clip | First text s (p50/p95) | Final text s (p50/p95) | ASR ms / step s | MT ms | Skips |
|---|---|---|---|---|---|---|
| turbo-750+tg4b | en_pizza_music | 2.12 / 2.92 | 3.64 / 6.64 | 992.0 / 1.85 | 888.0 | 0 |
| turbo-750+tg4b | en_pycon_shaw | 2.83 / 5.99 | 6.0 / 10.46 | 1530.0 / 2.79 | 1101.0 | 0 |
| turbo-750+tg4b | tr_meetup66 | 1.75 / 2.26 | 5.01 / 9.18 | 815.0 / 1.35 | 634.0 | 0 |
| turbo-750+tg4b | tr_meetup72 | 1.58 / 3.25 | 3.7 / 7.13 | 974.0 / 2.02 | 942.0 | 0 |
