# Benchmark 2026-11-09 20:33

MacBook Air (Apple M4, 10 GPU cores, 16 GB), macOS 27.2, on AC.

## Translation (sentence set in bench/mt_sentences.tsv)

| Candidate | EN→TR chrF | EN→TR ms p50 (p95) | TR→EN chrF | TR→EN ms p50 (p95) | Guard rejections | Memory MB |
|---|---|---|---|---|---|---|
| opus-mt | 71.3 | 109.0 (170.0) | 71.9 | 106.0 (175.0) | 0 | 893 |
| tg4b | 59.1 | 567.0 (701.0) | 62.7 | 454.0 (578.0) | 0 | 2770 |
| hymt1.8b | 64.1 | 634.0 (820.0) | 66.1 | 384.0 (548.0) | 0 | 2198 |

Side-by-side outputs for human review: mt_review.md
