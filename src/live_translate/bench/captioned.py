"""Accuracy on real talks by Turkish speakers, scored against human-made captions.

  uv run python -m live_translate.bench.captioned fetch     # audio excerpts + captions (yt-dlp via uvx)
  uv run python -m live_translate.bench.captioned run       # streaming vs offline WER, translations

Unlike the main benchmark (agreement with Whisper large-v3), this measures real accuracy.
"""

from __future__ import annotations

import html
import json
import re
import subprocess
import sys
import time

from ..config import VAR_DIR

DIR = VAR_DIR / "bench-captioned"

# name, spoken language, YouTube id, excerpt start, end (s), description
SOURCES = [
    (
        "en_shafak",
        "en",
        "Zq7QPnqLoUk",
        120,
        360,
        "Elif Shafak, TED: English by a Turkish speaker (human EN + TR captions)",
    ),
    (
        "en_ozkan",
        "en",
        "7TacjjISZgs",
        90,
        330,
        "Umit Ozkan, TEDx Ohio State: English by a Turkish-born engineer (human EN captions)",
    ),
    (
        "tr_llm",
        "tr",
        "fnxX-1J6Z24",
        30,
        270,
        "Sifirdan LLM Gelistirme course intro: technical Turkish (human TR captions)",
    ),
    (
        "tr_turer",
        "tr",
        "eEbQ70pHxHE",
        120,
        360,
        "Ahmet Turer, TEDxMETUAnkara: Turkish engineering talk (human TR captions)",
    ),
    ("tr_tonguc", "tr", "AbbEtiZbnac", 120, 360, "Saffet Emre Tonguc, TEDxIstanbul: Turkish talk (human TR captions)"),
]

# Realistic event-like talks chosen by the organiser; no human captions, so they are judged by
# reading the timestamped side by side (and listening to the video at those times).
UNCAPTIONED = [
    ("en_gunduz", "en", "Q9pIcLXcjMU", 60, 300, "Ayse Bilge Gunduz, WomenTech: English by a Turkey-based developer"),
    (
        "en_ayci",
        "en",
        "ZhN1s9sVUWw",
        0,
        105,
        "Gonul Ayci, PyCon DE lightning talk: English by a Turkey-based developer",
    ),
    ("tr_saati85", "tr", "UVrpwJ2jhZU", 1080, 1320, "Python Saati #85 (pyistanbul), from 18:00: Turkish tech talk"),
    (
        "tr_saati102",
        "tr",
        "dBY1f3tj3mM",
        0,
        240,
        "Python Saati #102 (pyistanbul), Celery: regular Turkish tech presentation",
    ),
]
ALL = SOURCES + UNCAPTIONED


def _ts(t: str) -> float:
    h, m, s = t.replace(",", ".").split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def parse_vtt(text: str) -> list[tuple[float, float, str]]:
    cues = []
    for block in re.split(r"\n\s*\n", text):
        m = re.search(r"(\d+:\d+:\d+[.,]\d+)\s*-->\s*(\d+:\d+:\d+[.,]\d+)", block)
        if not m:
            continue
        body = block[m.end() :].strip()
        body = re.sub(r"<[^>]+>", "", body)
        body = html.unescape(" ".join(line.strip() for line in body.splitlines()))
        if body:
            cues.append((_ts(m.group(1)), _ts(m.group(2)), body))
    return cues


def window_text(cues, start: float, end: float) -> str:
    """Caption text for cues that lie mostly inside [start, end]."""
    out = [c for s, e, c in cues if (s + e) / 2 >= start and (s + e) / 2 <= end]
    return re.sub(r"\s+", " ", " ".join(out)).strip()


def fetch() -> int:
    DIR.mkdir(parents=True, exist_ok=True)
    for name, lang, vid, start, end, desc in ALL:
        wav = DIR / f"{name}.wav"
        if not wav.exists():
            print(f"audio {name}: {desc}", flush=True)
            subprocess.run(
                [
                    "uvx",
                    "yt-dlp",
                    f"https://www.youtube.com/watch?v={vid}",
                    "-f",
                    "bestaudio",
                    "--download-sections",
                    f"*{start}-{end}",
                    "-x",
                    "--audio-format",
                    "wav",
                    "--postprocessor-args",
                    "ffmpeg:-ac 1 -ar 16000",
                    "-o",
                    str(DIR / f"{name}.%(ext)s"),
                    "--no-playlist",
                    "--quiet",
                    "--no-warnings",
                ],
                check=False,
            )
            time.sleep(5)
        if (name, lang, vid, start, end, desc) in SOURCES and not list(DIR.glob(f"{name}.*.vtt")):
            print(f"captions {name}", flush=True)
            subprocess.run(
                [
                    "uvx",
                    "yt-dlp",
                    f"https://www.youtube.com/watch?v={vid}",
                    "--skip-download",
                    "--write-subs",
                    "--sub-langs",
                    "en,tr",
                    "--sub-format",
                    "vtt",
                    "-o",
                    str(DIR / f"{name}.%(ext)s"),
                    "--no-playlist",
                    "--quiet",
                    "--no-warnings",
                ],
                check=False,
            )
            time.sleep(8)  # YouTube rate-limits caption downloads
    for name, lang, vid, start, end, _ in ALL:
        subs = sorted(p.name for p in DIR.glob(f"{name}.*.vtt"))
        print(f"{name}: audio {'ok' if (DIR / f'{name}.wav').exists() else 'MISSING'}, captions {subs or 'MISSING'}")
    return 0


def run(asr_names: list[str] | None = None, mt_names: list[str] | None = None, only: list[str] | None = None) -> int:
    """Score every ASR candidate (live streaming and offline) against the human captions, then
    translate the best live transcript with every MT candidate (chrF vs the human TR captions)."""
    import os

    import jiwer
    import sacrebleu

    from ..audio import load_audio_file
    from ..gender import neutralize
    from ..workers import WorkerClient
    from . import candidates
    from .benchmark import machine_info, norm_text, save_findings, simulate_asr

    os.environ["HF_HUB_OFFLINE"] = "1"
    asr_names = asr_names or ["turbo-750"]
    mt_names = mt_names or ["opus-mt"]
    clips = []
    for name, lang, vid, start, end, desc in ALL:
        if only and name not in only:
            continue
        wav, vtt = DIR / f"{name}.wav", DIR / f"{name}.{lang}.vtt"
        if not wav.exists():
            print(f"skip {name}: run `fetch` first")
            continue
        ref = window_text(parse_vtt(vtt.read_text(encoding="utf-8")), start, end) if vtt.exists() else None
        human_tr = DIR / f"{name}.tr.vtt"
        ref_tr = (
            window_text(parse_vtt(human_tr.read_text(encoding="utf-8")), start, end)
            if lang == "en" and human_tr.exists()
            else None
        )
        clips.append(
            {
                "name": name,
                "lang": lang,
                "desc": desc,
                "audio": load_audio_file(wav),
                "ref": ref,
                "ref_tr": ref_tr,
                "vid": vid,
                "start": start,
            }
        )

    results = {"machine": machine_info(), "asr": {}, "mt": {}}
    best_text: dict[str, tuple[float, str]] = {}
    for cand in asr_names:
        spec, _note = candidates.ASR[cand]
        asr = WorkerClient("asr", "live_translate.asr:create", spec)
        asr.start()
        if not asr.wait_ready(900):
            print(f"{cand}: failed to load ({list(asr.status.errors)})")
            continue
        for c in clips:
            stream = simulate_asr(asr, c["audio"], c["lang"], step=0.5)
            offline = []
            for i in range(0, len(c["audio"]), 16000 * 28):
                r = asr.call(
                    {
                        "audio": c["audio"][i : i + 16000 * 28],
                        "language": c["lang"],
                        "prompt": " ".join(offline)[-200:],
                    },
                    timeout=300,
                )
                offline.append(" ".join(w[2].strip() for w in r["words"]))
            wer = (
                (lambda hyp, ref=c["ref"]: jiwer.wer(norm_text(ref), norm_text(hyp)))
                if c["ref"]
                else (lambda hyp: None)
            )
            row = {
                "wer_stream": wer(stream["text"]),
                "wer_offline": wer(" ".join(offline)),
                "asr_ms": stream["asr_ms_mean"],
                "final_p50": stream["final_p50"],
                "text": stream["text"],
                "sentences": stream["sentences"],
            }
            results["asr"].setdefault(cand, {})[c["name"]] = row
            score = row["wer_stream"] if row["wer_stream"] is not None else 0.0
            if c["name"] not in best_text or score < best_text[c["name"]][0]:
                best_text[c["name"]] = (score, stream["text"], stream["sentences"])
            fmt = lambda v: "   n/a" if v is None else f"{v:6.1%}"
            print(
                f"{cand:14} {c['name']:12} WER live {fmt(row['wer_stream'])}  offline {fmt(row['wer_offline'])}  "
                f"{row['asr_ms']:.0f} ms/pass | {c['desc']}",
                flush=True,
            )
        asr.stop()

    from .. import hints
    from .. import schedule as sched

    protect = hints.protected_names(sched.load())  # as in the app
    from ..names import NameCorrector

    corrector = NameCorrector(protect)  # the whole program: stricter than live, where only nearby talks count
    for cand in mt_names:
        spec, _note = candidates.MT[cand]
        mt = WorkerClient("mt", "live_translate.translate:create", spec)
        mt.start()
        if not mt.wait_ready(900):
            print(f"{cand}: failed to load ({list(mt.status.errors)})")
            continue
        for c in clips:
            if c["name"] not in best_text:
                continue
            timed = best_text[c["name"]][2]  # the app's own sentence cuts, with times
            sents = [corrector.correct(t)[0] for _, _, t in timed]
            tgt = "tr" if c["lang"] == "en" else "en"
            outs, ms = [], []
            for x in sents:
                r = mt.call({"text": x, "src": c["lang"], "tgt": tgt, "protect": protect}, timeout=120)
                outs.append(neutralize(r["text"], x) if tgt == "en" else r["text"])
                ms.append(r["ms"])
            row = {
                "pairs": list(zip(sents, outs)),
                "times": [(a, b) for a, b, _ in timed],
                "ms_mean": sum(ms) / max(1, len(ms)),
            }
            if c["ref_tr"]:
                row["chrf_vs_human"] = sacrebleu.corpus_chrf([" ".join(outs)], [[c["ref_tr"]]]).score
                print(
                    f"{cand:14} {c['name']:10} translation chrF vs human Turkish {row['chrf_vs_human']:.1f}, "
                    f"{row['ms_mean']:.0f} ms/sentence",
                    flush=True,
                )
            results["mt"].setdefault(cand, {})[c["name"]] = row
        mt.stop()

    run_dir = DIR / f"run-{time.strftime('%Y%m%d-%H%M%S')}"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "results.json").write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str))
    (run_dir / "report.md").write_text(captioned_report(results, clips))
    print(
        f"report: {run_dir / 'report.md'}; copied to {save_findings(run_dir, results['machine'], ('report.md',))} (tracked in git)"
    )
    return 0


def captioned_report(results: dict, clips: list[dict]) -> str:
    m = results["machine"]
    lines = [
        "# Real talks by Turkish speakers, scored against human captions",
        "",
        (
            f"{m.get('model')} ({m.get('chip')}, {m.get('memory_gb')} GB). WER = word error rate against the "
            "human captions (lower is better); live = the app's streaming recognition, offline = the same model on "
            "28 s windows. A few words at the edges of each excerpt may not line up with the captions (about 1-2 points)."
        ),
        "",
        "| Speech model | Talk | WER live | WER offline | ms per pass |",
        "|---|---|---|---|---|",
    ]
    desc = {c["name"]: c["desc"] for c in clips}
    for cand, rows in results["asr"].items():
        for name, r in rows.items():
            if r["wer_stream"] is None:
                continue  # no human captions for this clip: see the side by side below
            lines.append(
                f"| {cand} | {desc[name]} | {r['wer_stream']:.1%} | {r['wer_offline']:.1%} | {r['asr_ms']:.0f} |"
            )
    chrf = [
        (cand, name, r["chrf_vs_human"], r["ms_mean"])
        for cand, rows in results["mt"].items()
        for name, r in rows.items()
        if "chrf_vs_human" in r
    ]
    if chrf:
        lines += [
            "",
            "| Translation model | Talk | chrF vs human Turkish translation | ms per sentence |",
            "|---|---|---|---|",
        ]
        lines += [f"| {c} | {desc[n]} | {v:.1f} | {ms:.0f} |" for c, n, v, ms in chrf]
    lines += ["", "## Subtitles: what was heard live (best speech model) and each translation", ""]
    for c in clips:
        lines += [f"### {c['desc']}", ""]
        per_model = {cand: rows[c["name"]]["pairs"] for cand, rows in results["mt"].items() if c["name"] in rows}
        if not per_model:
            continue
        first = next(iter(per_model.values()))
        times = next(iter(rows[c["name"]]["times"] for rows in results["mt"].values() if c["name"] in rows))
        lines.append(f"Video: https://www.youtube.com/watch?v={c['vid']}&t={c['start']}s")
        lines.append("")
        for i, (src, _) in enumerate(first[:40]):
            t = c["start"] + times[i][0]
            lines.append(f"- [{int(t // 60)}:{int(t % 60):02d}] **{src}**")
            for cand, pairs in per_model.items():
                lines.append(f"  - `{cand}`: {pairs[i][1]}")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["fetch", "run"])
    ap.add_argument("--asr", nargs="*", help="speech candidates (bench/candidates.py), default turbo-750")
    ap.add_argument("--mt", nargs="*", help="translation candidates, default opus-mt")
    ap.add_argument("--clips", nargs="*", help="only these clips (e.g. en_shafak)")
    a = ap.parse_args()
    sys.exit(fetch() if a.action == "fetch" else run(a.asr, a.mt, a.clips))
