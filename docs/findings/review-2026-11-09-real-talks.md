# Review of real talks (2026-11-09)

Every subtitle read by hand (no listening). Sources: `benchmarks/run-20261109-214552-*` (four talks picked by the organiser; Opus-MT and TranslateGemma 4B) and `benchmarks/captioned-20261109-212103-*` (five captioned talks, Opus-MT). "Major" = wrong meaning or nonsense.

## Recognition (Whisper turbo)

| Talk | Clearly misheard | Pattern |
|---|---|---|
| Ayse Bilge Gunduz (EN, mild accent) | ~6 / 30 | short tokens: "C" -> "see", "Python 3" -> "Python tree", "array" -> "area" |
| Gonul Ayci (EN, stronger accent) | ~2-3 / 15 | "May 2nd and 3rd" -> "May 2nd and July"; accent hurt less than expected |
| Python Saati #85 (TR, meetup) | ~8 / 41 | loanwords: "uranyum" -> "urayim", "A Space Odyssey" -> "espresso Odyssey" |
| Python Saati #102 (TR, tech) | ~8 / 35 | tool names: "Celery" -> "seler", "PyIstanbul" -> "Pay Istanbul" |

Found and fixed: prompt leakage ("We use Python ..." never said), Turkish ordinals and abbreviations ("30.", "M.Ö.") ending sentences, tool names missing from the hint (now `data/program_terms.json`).

## Translation (major errors)

| Talk | Opus-MT | TranslateGemma 4B |
|---|---|---|
| Gunduz EN->TR (30) | ~7 ("print" -> "baskı", broken run-ons) | ~5 ("float" -> "Yüzer") |
| Ayci EN->TR (15) | ~3 ("call for papers" -> "gazete çağrısı") | ~1 |
| Saati #85 TR->EN (41) | ~6 ("araç" -> "vehicle") | ~12 (invents meaning) |
| Saati #102 TR->EN (35) | ~5 (mostly misheard input) | ~9 (reverses meaning) |
| Tonguc TR->EN | translates place names ("Fikirtepe" -> "Ideatepe") | |

- TR->EN: Opus-MT is safer; TranslateGemma 4B is fluent but wrong.
- EN->TR: TranslateGemma 4B reads better on broken English; decide per direction on the Pro.
- Opus-MT drops content from inputs over ~40 words; keep inputs to one sentence.
- Many translation errors start as recognition errors.
