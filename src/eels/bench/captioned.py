"""Accuracy on real talks by Turkish speakers, scored against human-made captions.

  uv run python -m eels.bench.captioned fetch     # audio excerpts + captions (yt-dlp via uvx)
  uv run python -m eels.bench.captioned run       # streaming vs offline WER, translations
  uv run python -m eels.bench.captioned run --gemini [--asr whisper-turbo-15s --mt opus-mt]   # Gemini Live Translate

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
from .clips import Clip

DIR = VAR_DIR / "bench-captioned"

SOURCES: list[Clip] = [
    Clip(
        "en_shafak",
        "en",
        "Zq7QPnqLoUk",
        120,
        360,
        "Elif Shafak, TED: English by a Turkish speaker (human EN + TR captions)",
    ),
    Clip(
        "en_ozkan",
        "en",
        "7TacjjISZgs",
        90,
        330,
        "Umit Ozkan, TEDx Ohio State: English by a Turkish-born engineer (human EN captions)",
    ),
    Clip(
        "tr_llm",
        "tr",
        "fnxX-1J6Z24",
        30,
        270,
        "Sifirdan LLM Gelistirme course intro: technical Turkish (human TR captions)",
    ),
    Clip(
        "tr_turer",
        "tr",
        "eEbQ70pHxHE",
        120,
        360,
        "Ahmet Turer, TEDxMETUAnkara: Turkish engineering talk (human TR captions)",
    ),
    Clip(
        "tr_tonguc", "tr", "AbbEtiZbnac", 120, 360, "Saffet Emre Tonguc, TEDxIstanbul: Turkish talk (human TR captions)"
    ),
]

# Realistic event-like talks chosen by the organiser; no human captions, so they are judged by
# reading the timestamped side by side (and listening to the video at those times).
UNCAPTIONED: list[Clip] = [
    Clip(
        "en_gunduz", "en", "Q9pIcLXcjMU", 60, 300, "Ayse Bilge Gunduz, WomenTech: English by a Turkey-based developer"
    ),
    Clip(
        "en_ayci",
        "en",
        "ZhN1s9sVUWw",
        0,
        105,
        "Gonul Ayci, PyCon DE lightning talk: English by a Turkey-based developer",
    ),
    Clip("tr_saati85", "tr", "UVrpwJ2jhZU", 1080, 1320, "Python Saati #85 (pyistanbul), from 18:00: Turkish tech talk"),
    Clip(
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


def gemini_clip(audio, lang: str, speed: float = 1.0, settle_s: float = 6.0) -> dict:
    """Stream one clip to Gemini Live Translate in real time, as the app does."""
    from .. import hints
    from .. import schedule as sched
    from ..cloud import FRAME_SAMPLES, GeminiLive, Sentencer
    from ..config import SettingsStore

    target = "tr" if lang == "en" else "en"
    sn = Sentencer()
    sources: list[str] = []
    done = []
    events: list = []
    last_text = [0.0]

    def on_input(_tgt, text, _finished, code):
        sources.append(text)
        sn.add_source(text, code, time.monotonic())

    def on_output(_tgt, text, finished, _code):
        last_text[0] = time.monotonic()
        done.extend((time.monotonic(), s) for s in sn.add_text(text, time.monotonic(), finished))

    g = GeminiLive(
        on_input,
        on_output,
        lambda level, msg: events.append((level, msg)),
        instruction=hints.gemini_instruction(sched.load()),  # as the app does
        backend=SettingsStore().value.gemini_backend,
        vertex_project=SettingsStore().value.gemini_vertex_project,
        vertex_location=SettingsStore().value.gemini_vertex_location,
    )
    try:
        g.set_targets([target], echo=True)  # as the app does for a talk with a fixed language
        t_end = time.monotonic() + 20
        while not g.connected and time.monotonic() < t_end:
            time.sleep(0.1)
        t0 = time.monotonic()
        for i in range(0, len(audio), FRAME_SAMPLES):
            g.feed(audio[i : i + FRAME_SAMPLES])
            wait = t0 + (i + FRAME_SAMPLES) / 16000 / speed - time.monotonic()
            if wait > 0:
                time.sleep(wait)
        audio_end = time.monotonic()
        while time.monotonic() - max(last_text[0], audio_end) < settle_s:
            time.sleep(0.2)
            done.extend((time.monotonic(), s) for s in sn.tick(time.monotonic()))
        done.extend((time.monotonic(), s) for s in sn.tick(float("inf")))
        status = g.status()
    finally:
        g.shutdown()
    joiner = "" if any(s[:1].isspace() for s in sources) else " "
    delays = sorted(at - s.end_mono for at, s in done)
    return {
        "source": joiner.join(sources).strip(),
        "sentences": [(s.start_mono - t0, s.text, s.source) for _, s in done],
        "delay_p50": delays[len(delays) // 2] if delays else None,
        "tail_s": round(last_text[0] - audio_end, 2) if last_text[0] else None,
        "status": status,
        "events": events,
    }


def run(
    asr_names: list[str] | None = None,
    mt_names: list[str] | None = None,
    only: list[str] | None = None,
    gemini: bool = False,
) -> int:
    """Score every ASR candidate (live streaming and offline) against the human captions, then
    translate the best live transcript with every MT candidate (chrF vs the human TR captions).
    With gemini=True, also stream each clip through Gemini Live Translate (in real time)."""
    import os

    import jiwer
    import sacrebleu

    from .. import models
    from ..audio import load_audio_file
    from ..gender import neutralize
    from ..workers import WorkerClient
    from .benchmark import machine_info, norm_text, save_findings, simulate_asr

    os.environ["HF_HUB_OFFLINE"] = "1"
    if gemini and asr_names is None and mt_names is None:
        asr_names, mt_names = [], []  # Gemini only
    asr_names = [models.DEFAULT_SPEECH] if asr_names is None else asr_names
    mt_names = ["opus-mt"] if mt_names is None else mt_names
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

    results = {"machine": machine_info(), "asr": {}, "mt": {}, "gemini": {}}
    run_dir = DIR / f"run-{time.strftime('%Y%m%d-%H%M%S')}"
    run_dir.mkdir(parents=True, exist_ok=True)

    def save() -> None:  # after every Gemini clip too, so an interrupted run keeps what it measured
        (run_dir / "results.json").write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str))
        (run_dir / "report.md").write_text(captioned_report(results, clips))

    if gemini:
        from ..cloud import api_key
        from ..config import SettingsStore

        if not api_key(SettingsStore().value.gemini_backend):
            print("No Gemini key: store it in the Keychain (README, Gemini engine) or set GEMINI_API_KEY.")
            return 1
        for c in clips:
            r = gemini_clip(c["audio"], c["lang"])
            if c["ref"]:
                r["wer"] = jiwer.wer(norm_text(c["ref"]), norm_text(r["source"]))
            if c["ref_tr"]:
                r["chrf_vs_human"] = sacrebleu.corpus_chrf(
                    [" ".join(t for _, t, _ in r["sentences"])], [[c["ref_tr"]]]
                ).score
            results["gemini"][c["name"]] = r
            save()
            wer = f"{r['wer']:6.1%}" if "wer" in r else "   n/a"
            chrf = f", chrF vs human Turkish {r['chrf_vs_human']:.1f}" if "chrf_vs_human" in r else ""
            print(
                f"gemini         {c['name']:12} WER {wer}{chrf}, {len(r['sentences'])} subtitles, "
                f"delay after source text {r['delay_p50']} s, last text {r['tail_s']} s after the audio ended",
                flush=True,
            )
    best_text: dict[str, tuple[float, str]] = {}
    for cand in asr_names:
        spec = models.get(cand).spec
        asr = WorkerClient("asr", "eels.asr:create", spec)
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
        spec = models.get(cand).spec
        mt = WorkerClient("mt", "eels.translate:create", spec)
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

    save()
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
    for name, r in results.get("gemini", {}).items():
        if "wer" in r:
            lines.append(f"| gemini (input transcript) | {desc[name]} | {r['wer']:.1%} | - | - |")
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
    gem = results.get("gemini", {})
    if gem:
        lines += [
            "",
            "| Gemini | Talk | chrF vs human Turkish | delay after source text (p50) | last text after audio end |",
            "|---|---|---|---|---|",
        ]
        for name, r in gem.items():
            chrf_v = f"{r['chrf_vs_human']:.1f}" if "chrf_vs_human" in r else "-"
            lines.append(f"| gemini | {desc[name]} | {chrf_v} | {r['delay_p50']} s | {r['tail_s']} s |")
    lines += ["", "## Subtitles: what was heard live (best speech model) and each translation", ""]
    for c in clips:
        lines += [f"### {c['desc']}", ""]
        if c["name"] in gem:
            lines += ["Gemini Live Translate (its own sentences; source = its input transcript):", ""]
            for t0, text, src in gem[c["name"]]["sentences"][:40]:
                t = c["start"] + t0
                lines.append(f"- [{int(t // 60)}:{int(t % 60):02d}] **{src or '...'}**")
                lines.append(f"  - `gemini`: {text}")
            lines.append("")
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
    ap.add_argument("--asr", nargs="*", help="speech models by key (models.py), default whisper-turbo-15s")
    ap.add_argument("--mt", nargs="*", help="translation candidates, default opus-mt")
    ap.add_argument("--clips", nargs="*", help="only these clips (e.g. en_shafak)")
    ap.add_argument("--gemini", action="store_true", help="Gemini Live Translate (needs the Gemini key; real time)")
    a = ap.parse_args()
    sys.exit(fetch() if a.action == "fetch" else run(a.asr, a.mt, a.clips, a.gemini))
