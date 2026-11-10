"""Benchmark speech recognition and translation candidates on this Mac.

  uv run live-translate benchmark                 # everything with defaults
  uv run live-translate benchmark --mt            # all MT candidates only
  uv run live-translate benchmark --asr turbo-750 turbo-full
  uv run live-translate benchmark --pipeline turbo-750+tg4b --soak 30

Results go to var/bench/<timestamp>/ (report.md, results.json, mt_review.md).
"""

from __future__ import annotations

import csv
import json
import os
import platform
import re
import statistics
import subprocess
import time
import unicodedata
from pathlib import Path

import numpy as np

from ..config import VAR_DIR, Settings, SettingsStore
from ..streaming import SAMPLE_RATE, Word
from ..workers import WorkerClient
from . import candidates
from .fetch import AUDIO_DIR

BENCH_DIR = VAR_DIR / "bench"
SENTENCES = Path(__file__).with_name("mt_sentences.tsv")


# Helpers --------------------------------------------------------------------------
def machine_info() -> dict:
    def sh(*cmd):
        try:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout.strip()
        except Exception:
            return ""

    displays = sh("system_profiler", "SPDisplaysDataType")
    hardware = sh("system_profiler", "SPHardwareDataType")
    gpu = re.search(r"Total Number of Cores: (\d+)", displays)
    model = re.search(r"Model Name: (.+)", hardware)
    return {
        "chip": sh("sysctl", "-n", "machdep.cpu.brand_string"),
        "memory_gb": round(int(sh("sysctl", "-n", "hw.memsize") or 0) / 2**30),
        "gpu_cores": gpu.group(1) if gpu else None,
        "model": model.group(1).strip() if model else None,
        "macos": sh("sw_vers", "-productVersion"),
        "python": platform.python_version(),
        "power": "AC" if "AC Power" in sh("pmset", "-g", "batt") else "battery",
    }


def pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    return s[min(len(s) - 1, int(q * len(s)))]


def r(x, n=2):
    return None if x is None else round(x, n)


_TR_UNITS = {"sıfır": 0, "bir": 1, "iki": 2, "üç": 3, "dört": 4, "beş": 5, "altı": 6, "yedi": 7, "sekiz": 8, "dokuz": 9}
_TR_TENS = {"on": 10, "yirmi": 20, "otuz": 30, "kırk": 40, "elli": 50, "altmış": 60, "yetmiş": 70, "seksen": 80, "doksan": 90}
_TR_ORD = {"birinci": 1, "ikinci": 2, "üçüncü": 3, "dördüncü": 4, "beşinci": 5, "altıncı": 6, "yedinci": 7, "sekizinci": 8,
           "dokuzuncu": 9, "onuncu": 10, "yirminci": 20, "otuzuncu": 30, "kırkıncı": 40, "ellinci": 50, "yüzüncü": 100}
_EN_UNITS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
             "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
             "seventeen": 17, "eighteen": 18, "nineteen": 19}
_EN_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_EN_ORD = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8,
           "ninth": 9, "tenth": 10, "twentieth": 20, "thirtieth": 30, "hundredth": 100}
# Only unambiguous number words: "bir" (a/one) and "one" are too often not numbers, so they stay words.
_NUM = {**{k: v for k, v in _TR_UNITS.items() if k != "bir"}, **_TR_ORD,
        **{k: v for k, v in _EN_UNITS.items() if k != "one"}, **_EN_ORD}
_TENS = {**_TR_TENS, **_EN_TENS}


def _numbers_to_digits(words: list[str]) -> list[str]:
    out, i = [], 0
    while i < len(words):
        w = words[i]
        if w in _TENS:
            n = _TENS[w]
            nxt = words[i + 1] if i + 1 < len(words) else ""
            if nxt in _TR_UNITS or nxt in _EN_UNITS and _EN_UNITS[nxt] < 10:
                n += _TR_UNITS.get(nxt, _EN_UNITS.get(nxt, 0))
                i += 1
            out.append(str(n))
        elif w in _NUM:
            out.append(str(_NUM[w]))
        else:
            out.append(re.sub(r"^(\d+)(?:st|nd|rd|th|\.)$", r"\1", w))
        i += 1
    return out


def norm_text(text: str) -> str:
    """Normalise for WER: case, punctuation, apostrophes (Turkish suffixes are written both
    "Sinan'ın" and "Sinanın"), circumflexes (mekân/mekan) and number words vs digits."""
    t = unicodedata.normalize("NFC", text).casefold().replace("i\u0307", "i")
    t = t.translate(str.maketrans({"\u2019": "", "\u2018": "", "\u02bc": "", "'": "", "\u00e2": "a", "\u00ee": "i", "\u00fb": "u"}))
    t = re.sub(r"[^\w\s]", " ", t)
    return " ".join(_numbers_to_digits(t.split()))


def rss_mb(pid: int | None) -> float | None:
    """Physical footprint (Activity Monitor's memory figure) of a process."""
    from ..workers import footprint_mb

    mb = footprint_mb(pid) if pid else None
    return None if mb is None else round(mb)


def clips(quick: bool) -> list[tuple[str, str, np.ndarray]]:
    from ..audio import load_audio_file

    out = []
    for p in sorted(AUDIO_DIR.glob("*.wav")):
        lang = p.name[:2]
        if lang not in ("en", "tr"):
            continue
        audio = load_audio_file(p)
        if quick:
            audio = audio[: 90 * SAMPLE_RATE]
        out.append((p.stem, lang, audio))
    return out


def start_worker(name: str, factory: str, spec: dict) -> WorkerClient:
    w = WorkerClient(name, factory, spec)
    w.start()
    if not w.wait_ready(timeout=900):
        raise RuntimeError(f"{name} failed to load: {list(w.status.errors)}")
    return w


# Reference transcripts ---------------------------------------------------------------
def reference_text(name: str, lang: str, audio: np.ndarray, quick: bool) -> str:
    """Offline transcript with the full large-v3 model (30 s windows), cached per clip."""
    ref_dir = BENCH_DIR / "refs"
    ref_dir.mkdir(parents=True, exist_ok=True)
    path = ref_dir / f"{name}{'_quick' if quick else ''}.txt"
    if path.exists():
        return path.read_text()
    code = (
        "import sys, numpy as np, mlx.core as mx, mlx_whisper\n"
        "mx.set_cache_limit(512 * 2**20)\n"
        "a = np.load(sys.argv[1])\n"
        f"r = mlx_whisper.transcribe(a, path_or_hf_repo='{candidates.REFERENCE_ASR}', language='{lang}', "
        "condition_on_previous_text=False, verbose=None)\n"
        "sys.stdout.write(r['text'].strip())\n"
    )
    tmp = ref_dir / f"{name}.npy"
    np.save(tmp, audio)
    print(f"  reference transcript for {name} (large-v3, offline)...", flush=True)
    out = subprocess.run([os.sys.executable, "-c", code, str(tmp)], capture_output=True, text=True, check=True).stdout
    tmp.unlink(missing_ok=True)
    path.write_text(out)
    return out


# ASR -------------------------------------------------------------------------------
def simulate_asr(worker: WorkerClient, audio: np.ndarray, lang: str, step: float, interim: bool = True, title=None) -> dict:
    """Run the real StreamEngine over a clip with a simulated clock.

    The clock is the audio position; each ASR call starts when both the audio is there
    and the previous call has finished, and its result is available `ms` later.
    """
    from ..engine import StreamEngine

    settings = Settings(spoken_language=lang, asr_step_s=step, interim=interim)
    state = {"now": 0.0, "busy_until": 0.0, "result_t": 0.0}
    asr_ms: list[float] = []
    commit_lat: list[float] = []
    first_seen: dict[tuple[str, int], float] = {}
    shown_tentative: list[Word] = []
    clauses: list[tuple[float, float, str]] = []
    all_committed: list[Word] = []

    def asr_fn(a, language, prompt):
        res = worker.call({"op": "transcribe", "audio": a, "language": language, "prompt": prompt}, timeout=60)
        start = max(state["now"], state["busy_until"])
        state["result_t"] = start + res["ms"] / 1000
        state["busy_until"] = state["result_t"]
        asr_ms.append(res["ms"])
        return res

    def on_clause(clause, src, seq):
        all_committed.extend(clause.words)
        for w in clause.words:
            commit_lat.append(state["result_t"] - w.end)
        clauses.append((clause.start, clause.end, clause.text))

    def on_interim(it):
        pass

    if title is None:  # the same program hint the app uses (no talk "current" in a benchmark)
        from .. import hints
        from .. import schedule as sched

        sessions = sched.load()
        title = lambda lang: hints.asr_hint(lang, sessions)  # noqa: E731
    engine = StreamEngine(lambda: settings, asr_fn, on_clause, on_interim, clock=lambda: state["now"], title=title)
    # Record when each word first appears (tentative or committed) for "first text" delay.
    orig_apply = engine.online.apply

    def apply(result):
        committed, tentative = orig_apply(result)
        for w in committed + tentative:
            key = (w.norm, int(round(w.start * 5)))
            first_seen.setdefault(key, state["result_t"] - w.end)
        shown_tentative.extend(tentative)
        return committed, tentative

    engine.online.apply = apply
    chunk = int(0.02 * SAMPLE_RATE)
    for i in range(0, len(audio), chunk):
        state["now"] = (i + chunk) / SAMPLE_RATE
        engine.process_chunk(audio[i : i + chunk])
        if state["now"] >= state["busy_until"]:
            engine.maybe_run_asr()
        engine.check_age()
    state["now"] += 2.0
    engine.end_utterance(flush=True)

    committed_text = " ".join(c[2] for c in clauses)
    # Rewrite rate: distinct tentative words shown that never made it into the final text
    # (same word within about a second of the same place).
    final_by_word: dict[str, list[float]] = {}
    for w in all_committed:
        final_by_word.setdefault(w.norm, []).append(w.start)
    shown = {(w.norm, round(w.start, 1)) for w in shown_tentative}
    rewrites = sum(1 for n, st in shown if not any(abs(st - f) < 1.0 for f in final_by_word.get(n, ())))
    shown_tentative = list(shown)
    step_used = engine.step
    return {
        "text": committed_text,
        "runs": len(asr_ms),
        "asr_ms_mean": statistics.fmean(asr_ms) if asr_ms else None,
        "asr_ms_p95": pct(asr_ms, 0.95),
        "step_s": step_used,
        "first_p50": pct(list(first_seen.values()), 0.5),
        "first_p95": pct(list(first_seen.values()), 0.95),
        "final_p50": pct(commit_lat, 0.5),
        "final_p95": pct(commit_lat, 0.95),
        "rewrite_rate": rewrites / len(shown_tentative) if shown_tentative else 0.0,
        "clauses": len(clauses),
        "sentences": clauses,  # (start s, end s, text) of each final subtitle
    }


def run_asr(names: list[str], quick: bool, out: dict) -> None:
    import jiwer

    data = clips(quick)
    if not data:
        print("No benchmark audio. Run `uv run live-translate fetch-bench-audio` first.")
        return
    refs = {name: reference_text(name, lang, audio, quick) for name, lang, audio in data}
    results = out.setdefault("asr", {})
    for cand in names:
        spec, note = candidates.ASR[cand]
        print(f"ASR {cand}: {note}", flush=True)
        worker = start_worker("asr", "live_translate.asr:create", spec)
        load = worker.status.info.get("load_s")
        per_clip = {}
        for name, lang, audio in data:
            t0 = time.perf_counter()
            res = simulate_asr(worker, audio, lang, step=Settings().asr_step_s)
            res["wall_s"] = time.perf_counter() - t0
            res["audio_s"] = len(audio) / SAMPLE_RATE
            res["wer_vs_ref"] = jiwer.wer(norm_text(refs[name]), norm_text(res["text"])) if res["text"] else 1.0
            res["rss_mb"] = rss_mb(worker._proc.pid if worker._proc else None)
            per_clip[name] = res
            print(f"  {name}: {res['asr_ms_mean']:.0f} ms/run, step {res['step_s']:.2f} s, first {r(res['first_p50'])} s, "
                  f"final {r(res['final_p50'])}/{r(res['final_p95'])} s, rewrites {res['rewrite_rate']:.0%}, "
                  f"WER vs large-v3 {res['wer_vs_ref']:.1%}", flush=True)
        worker.stop()
        results[cand] = {"note": note, "spec": spec, "load_s": load, "clips": per_clip}


# MT --------------------------------------------------------------------------------
def load_sentences() -> list[dict]:
    with SENTENCES.open(encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def run_mt(names: list[str], out: dict) -> None:
    import sacrebleu

    from ..translate import check_translation

    rows = load_sentences()
    results = out.setdefault("mt", {})
    outputs: dict[str, list[str]] = {}
    for cand in names:
        spec, note = candidates.MT[cand]
        print(f"MT {cand}: {note}", flush=True)
        worker = start_worker("mt", "live_translate.translate:create", spec)
        hyps, times = [], []
        rejected = 0
        for row in rows:
            src = row["src"]
            tgt = "tr" if src == "en" else "en"
            res = worker.call({"text": row["source"], "src": src, "tgt": tgt}, timeout=60)
            hyps.append(res["text"])
            times.append(res["ms"])
            if check_translation(row["source"], res["text"], tgt):
                rejected += 1
        rss = rss_mb(worker._proc.pid if worker._proc else None)
        worker.stop()
        by_dir = {}
        for d in ("en", "tr"):
            idx = [i for i, row in enumerate(rows) if row["src"] == d]
            chrf = sacrebleu.corpus_chrf([hyps[i] for i in idx], [[rows[i]["reference"] for i in idx]]).score
            by_dir[f"{d}->{'tr' if d == 'en' else 'en'}"] = {
                "chrf": round(chrf, 1),
                "ms_p50": r(pct([times[i] for i in idx], 0.5), 0),
                "ms_p95": r(pct([times[i] for i in idx], 0.95), 0),
            }
        results[cand] = {"note": note, "spec": spec, "directions": by_dir, "rejected": rejected, "rss_mb": rss,
                         "load_s": worker.status.info.get("load_s")}
        outputs[cand] = hyps
        print("  " + ", ".join(f"{k}: chrF {v['chrf']}, {v['ms_p50']} ms (p95 {v['ms_p95']})" for k, v in by_dir.items())
              + f", guard rejections {rejected}", flush=True)
    out["_mt_outputs"] = {"rows": rows, "outputs": outputs}


# Full pipeline ----------------------------------------------------------------------
def run_pipeline(pairs: list[str], soak_min: float, out: dict, out_dir: Path) -> None:
    from ..pipeline import Pipeline
    from ..transcript import TranscriptLog

    data = clips(quick=True)  # 90 s excerpts per clip keep this part short
    if not data:
        print("No benchmark audio. Run `uv run live-translate fetch-bench-audio` first.")
        return
    results = out.setdefault("pipeline", {})
    for pair in pairs:
        asr_name, mt_name = pair.split("+")
        aspec, _ = candidates.ASR[asr_name]
        mspec, _ = candidates.MT[mt_name]
        print(f"Pipeline {pair} (real time, ASR and MT sharing the GPU)", flush=True)
        store = SettingsStore(out_dir / f"settings_{pair}.json")
        store.update(asr_model=aspec["model"], asr_audio_ctx=aspec.get("audio_ctx", "750"), mt_model=mspec["model"],
                     auto_from_schedule=False)
        p = Pipeline(store, lambda ch, msg: None)
        p.mt_extra = {k: v for k, v in mspec.items() if k != "model"}
        p.transcript = TranscriptLog(out_dir / f"transcripts_{pair}")
        p.boot()
        while not (p.asr.ready and p.mt_ready):
            time.sleep(0.5)
        per = {}
        for name, lang, audio in data:
            p.apply_settings({"spoken_language": lang})
            for m in (p.m_asr_ms, p.m_mt_ms, p.m_delay_interim, p.m_delay_confirmed):
                m.v.clear()
            done = {"v": False}
            path = out_dir / f"{name}_excerpt.wav"
            import soundfile as sf

            sf.write(path, audio, SAMPLE_RATE)
            p.play_file(str(path))
            p.player.on_done = lambda: done.__setitem__("v", True)
            while not done["v"]:
                time.sleep(0.5)
            time.sleep(4)  # let the last translations land
            st = p.status()
            per[name] = {k: st[k] for k in ("asr_ms", "asr_step_s", "mt_ms", "delay_interim_p50", "delay_interim_p95",
                                            "delay_confirmed_p50", "delay_confirmed_p95", "skips", "keeping_up")}
            per[name]["rss_asr_mb"] = rss_mb(p.asr._proc.pid if p.asr._proc else None)
            per[name]["rss_mt_mb"] = sum(rss_mb(w._proc.pid) or 0 for w in p.mt_pool.values() if w._proc)
            print(f"  {name}: first text {st['delay_interim_p50']}/{st['delay_interim_p95']} s, final text "
                  f"{st['delay_confirmed_p50']}/{st['delay_confirmed_p95']} s, ASR {st['asr_ms']} ms every "
                  f"{st['asr_step_s']} s, MT {st['mt_ms']} ms, skips {st['skips']}", flush=True)
        soak = None
        if soak_min > 0:
            soak = run_soak(p, data, soak_min, out_dir)
        p.shutdown()
        results[pair] = {"clips": per, "soak": soak}


def run_soak(p, data, minutes: float, out_dir: Path) -> dict:
    """Loop the excerpts in real time and sample delay, speed and memory every 30 s."""
    import soundfile as sf

    print(f"  soak test: {minutes:.0f} minutes...", flush=True)
    loop = np.concatenate([audio for _, _, audio in data])
    path = out_dir / "soak.wav"
    sf.write(path, loop, SAMPLE_RATE)
    p.apply_settings({"spoken_language": "auto"})
    samples = []
    t_end = time.monotonic() + minutes * 60
    while time.monotonic() < t_end:
        p.play_file(str(path))
        while p.player and p.player.is_alive() and time.monotonic() < t_end:
            time.sleep(30)
            st = p.status()
            samples.append({
                "t_min": round((minutes * 60 - (t_end - time.monotonic())) / 60, 1),
                "asr_ms": st["asr_ms"], "mt_ms": st["mt_ms"], "final_p50": st["delay_confirmed_p50"],
                "final_p95": st["delay_confirmed_p95"], "skips": st["skips"],
                "rss_asr_mb": rss_mb(p.asr._proc.pid if p.asr._proc else None),
                "rss_mt_mb": sum(rss_mb(w._proc.pid) or 0 for w in p.mt_pool.values() if w._proc),
                "restarts": [w["restarts"] for w in st["workers"]],
            })
            print(f"    {samples[-1]}", flush=True)
    p.player and p.player.stop()
    return {"minutes": minutes, "samples": samples}


# Report ----------------------------------------------------------------------------
def write_report(out: dict, out_dir: Path) -> Path:
    m = out["machine"]
    lines = [f"# Benchmark {out['started']}", "",
             f"{m.get('model')} ({m.get('chip')}, {m.get('gpu_cores')} GPU cores, {m.get('memory_gb')} GB), macOS {m.get('macos')}, on {m.get('power')}.", ""]
    if out.get("asr"):
        lines += ["## Speech recognition (streaming simulation, one model on the GPU)", "",
                  "| Candidate | Clip | ms per run (p95) | Step s | First text s (p50/p95) | Final text s (p50/p95) | Rewrites | WER vs large-v3 |",
                  "|---|---|---|---|---|---|---|---|"]
        for cand, res in out["asr"].items():
            for clip, c in res["clips"].items():
                lines.append(f"| {cand} | {clip} | {c['asr_ms_mean']:.0f} ({c['asr_ms_p95']:.0f}) | {c['step_s']:.2f} | "
                             f"{r(c['first_p50'])} / {r(c['first_p95'])} | {r(c['final_p50'])} / {r(c['final_p95'])} | "
                             f"{c['rewrite_rate']:.0%} | {c['wer_vs_ref']:.1%} |")
        lines += ["", "WER is measured against an offline large-v3 transcript, not a human one: it shows agreement, not accuracy.", ""]
    if out.get("mt"):
        lines += ["## Translation (sentence set in bench/mt_sentences.tsv)", "",
                  "| Candidate | EN→TR chrF | EN→TR ms p50 (p95) | TR→EN chrF | TR→EN ms p50 (p95) | Guard rejections | Memory MB |",
                  "|---|---|---|---|---|---|---|"]
        for cand, res in out["mt"].items():
            a, b = res["directions"]["en->tr"], res["directions"]["tr->en"]
            lines.append(f"| {cand} | {a['chrf']} | {a['ms_p50']} ({a['ms_p95']}) | {b['chrf']} | {b['ms_p50']} ({b['ms_p95']}) | {res['rejected']} | {res['rss_mb']} |")
        lines += ["", "Side-by-side outputs for human review: mt_review.md", ""]
    if out.get("pipeline"):
        lines += ["## Full pipeline in real time (ASR and MT sharing the GPU, 90 s excerpts)", "",
                  "| Pair | Clip | First text s (p50/p95) | Final text s (p50/p95) | ASR ms / step s | MT ms | Skips |",
                  "|---|---|---|---|---|---|---|"]
        for pair, res in out["pipeline"].items():
            for clip, c in res["clips"].items():
                lines.append(f"| {pair} | {clip} | {c['delay_interim_p50']} / {c['delay_interim_p95']} | {c['delay_confirmed_p50']} / "
                             f"{c['delay_confirmed_p95']} | {c['asr_ms']} / {c['asr_step_s']} | {c['mt_ms']} | {c['skips']} |")
            if res.get("soak"):
                s = res["soak"]["samples"]
                if s:
                    lines += ["", f"Soak {res['soak']['minutes']} min, {pair}: first sample ASR {s[0]['asr_ms']} ms / final p50 {s[0]['final_p50']} s, "
                              f"last sample ASR {s[-1]['asr_ms']} ms / final p50 {s[-1]['final_p50']} s, memory ASR {s[-1]['rss_asr_mb']} MB, "
                              f"MT {s[-1]['rss_mt_mb']} MB, skips {s[-1]['skips']}, restarts {s[-1]['restarts']}."]
        lines.append("")
    path = out_dir / "report.md"
    path.write_text("\n".join(lines))
    mt = out.get("_mt_outputs")
    if mt:
        rev = ["# Translation outputs for review", ""]
        for i, row in enumerate(mt["rows"]):
            rev.append(f"**{row['src'].upper()}**: {row['source']}  ")
            rev.append(f"_reference_: {row['reference']}  ")
            for cand, hyps in mt["outputs"].items():
                rev.append(f"`{cand}`: {hyps[i]}  ")
            rev.append("")
        (out_dir / "mt_review.md").write_text("\n".join(rev))
    return path


def main(args) -> int:
    os.environ["HF_HUB_OFFLINE"] = "1"
    out_dir = BENCH_DIR / time.strftime("%Y%m%d-%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)
    explicit = any(x is not None for x in (args.asr, args.mt, args.pipeline)) or args.soak
    out: dict = {"started": time.strftime("%Y-%m-%d %H:%M"), "machine": machine_info()}
    print(f"Benchmark on {out['machine']}", flush=True)
    if args.mt is not None or not explicit:
        run_mt(args.mt or list(candidates.MT), out)
    if args.asr is not None or not explicit:
        run_asr(args.asr or list(candidates.ASR), args.quick, out)
    pairs = args.pipeline if args.pipeline else (["turbo-750+tg4b"] if (not explicit or args.soak) else [])
    if pairs:
        run_pipeline(pairs, args.soak, out, out_dir)
    report = write_report(out, out_dir)
    out.pop("_mt_outputs", None)
    (out_dir / "results.json").write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    print(f"\nReport: {report}")
    print(f"Copied to {save_findings(out_dir, out['machine'])} (tracked in git)")
    return 0


def save_findings(out_dir: Path, machine: dict, files=("report.md", "results.json", "mt_review.md")) -> Path:
    """Copy the text results into docs/findings/benchmarks/ so they are kept in the repository."""
    import shutil

    from ..config import FINDINGS_DIR

    chip = re.sub(r"[^A-Za-z0-9]+", "-", f"{machine.get('chip', '')}-{machine.get('memory_gb', '')}GB").strip("-")
    dest = FINDINGS_DIR / "benchmarks" / f"{out_dir.name}-{chip}"
    dest.mkdir(parents=True, exist_ok=True)
    for name in files:
        if (out_dir / name).exists():
            shutil.copy2(out_dir / name, dest / name)
    return dest
