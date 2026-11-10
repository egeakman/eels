"""Command line: run the app, test with a file, download models, export SRT, update schedule, benchmark."""

from __future__ import annotations

import argparse
import logging
import logging.handlers
import os
import socket
import subprocess
import sys
import threading
import time
from datetime import date

from .config import LOG_DIR, SettingsStore
from .models import expand_models, models_present

PORT = 8000


def setup_logging(verbose: bool = False) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S")
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    fh = logging.handlers.TimedRotatingFileHandler(
        LOG_DIR / "live-translate.log", when="midnight", backupCount=14, encoding="utf-8"
    )
    fh.setFormatter(fmt)
    root.addHandler(fh)
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    sh.setLevel(logging.INFO if verbose else logging.WARNING)
    root.addHandler(sh)
    for noisy in ("httpx", "huggingface_hub", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("0.0.0.0", port))
            return True
        except OSError:
            return False


def print_urls(port: int) -> None:
    from .netinfo import can_connect, lan_addresses

    addrs = lan_addresses()
    print("\n  Live subtitles are running.\n")
    print(f"  Control panel (this Mac only):  http://localhost:{port}/control\n")
    if not addrs:
        print("  No network address found. Connect this Mac to the same network as the OBS computer.")
    else:
        print("  OBS browser source URL (1920 x 180):")
        for a in addrs:
            if a["kind"] == "virtual":
                continue
            reach = "" if can_connect(a["ip"], port) else "   (not reachable from this Mac; check the firewall)"
            print(f"    http://{a['ip']}:{port}/      {a['kind']} via {a['port']} ({a['iface']}){reach}")
        print("\n  Test from the OBS computer:")
        best = next((a for a in addrs if a["kind"] != "virtual"), addrs[0])
        print(f"    curl http://{best['ip']}:{port}/health")
        print("  If that fails but this Mac can reach it, the network blocks device-to-device traffic.")
        print("  Use a cable or our own router.")
    print("\n  Press Ctrl+C to stop.\n", flush=True)


def cmd_run(args) -> int:
    setup_logging(args.verbose)
    if not args.online:
        os.environ["HF_HUB_OFFLINE"] = "1"
    store = SettingsStore()
    s = store.value
    missing = models_present([s.asr_model, s.mt_model])
    if missing:
        print("These models are not downloaded yet:\n  " + "\n  ".join(missing))
        print("Run `uv run live-translate download-models` while online, then start again.")
        return 1
    if not port_free(PORT):
        print(f"Port {PORT} is already in use. Is another copy of live-translate running? (lsof -i :{PORT})")
        return 1

    import uvicorn

    from .pipeline import Pipeline
    from .server import Hub, create_app

    # Keep the Mac awake (display, idle and system sleep) for as long as we run.
    try:
        subprocess.Popen(
            ["caffeinate", "-dimsu", "-w", str(os.getpid())], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except Exception:
        print("Warning: could not start caffeinate; disable sleep in System Settings.")

    hub = Hub()
    pipeline = Pipeline(store, hub.publish)
    app = create_app(hub, pipeline)
    pipeline.boot()

    if args.play:

        def play_when_ready():
            print("Loading models before playing the file...", flush=True)
            while not (pipeline.asr.ready and pipeline.mt_ready):
                time.sleep(0.5)
            pipeline.play_file(args.play, speed=args.speed)

        threading.Thread(target=play_when_ready, daemon=True).start()
    elif not args.no_autostart:
        pipeline.start()

    config = uvicorn.Config(
        app, host="0.0.0.0", port=PORT, log_level="warning", ws_ping_interval=20, ws_ping_timeout=20
    )
    server = uvicorn.Server(config)

    def announce():
        while not server.started:
            time.sleep(0.1)
        print_urls(PORT)

    threading.Thread(target=announce, daemon=True).start()
    try:
        server.run()
    except KeyboardInterrupt:
        pass  # uvicorn shuts down gracefully, then re-raises Ctrl+C
    finally:
        # `uv run` forwards Ctrl+C and the terminal also sends it to the process group, so a
        # second one can arrive mid-shutdown. Ignore it so cleanup always completes.
        import signal

        signal.signal(signal.SIGINT, signal.SIG_IGN)
        print("\nStopping...", flush=True)
        pipeline.shutdown()
    print("Stopped.")
    return 0


def cmd_download_models(args) -> int:
    from huggingface_hub import snapshot_download

    from .translate import OpusMtTranslator

    store = SettingsStore()
    s = store.value
    repos = expand_models([s.asr_model, s.mt_model, "opus-mt"])  # Opus-MT is small and always kept as a fallback
    hymt_sizes: list[str] = []
    if args.all or args.include:
        from .bench import candidates as c

        asr = c.LEAN_ASR if args.all else []
        mt = c.LEAN_MT if args.all else []
        for name in args.include or []:
            if name in c.ASR:
                asr.append(name)
            elif name in c.MT:
                mt.append(name)
            else:
                print(f"Unknown candidate {name!r}. Speech: {', '.join(c.ASR)}. Translation: {', '.join(c.MT)}.")
                return 1
        repos += c.model_repos(asr, mt)
        hymt_sizes = [n for n in ("hymt1.8b", "hymt7b") if n in mt]
    for repo in dict.fromkeys(repos):
        print(f"Downloading {repo} ...", flush=True)
        snapshot_download(repo, allow_patterns=OpusMtTranslator.FILES if repo.startswith("Helsinki-NLP/") else None)
    print("Preparing Opus-MT (CTranslate2 conversion) ...", flush=True)
    OpusMtTranslator()
    if hymt_sizes:
        prepare_hymt(hymt_sizes)
    print("Done. The app can now run without internet.")
    return 0


def prepare_hymt(names: list[str]) -> None:
    """Tencent HY-MT has no MLX build on Hugging Face: download, convert to MLX into
    ~/.cache/live-translate/, then delete the original download (4 GB for 1.8B, 15 GB for 7B).
    1.8B is converted to 8-bit; 7B to 4-bit (about twice as fast, half the size)."""
    import shutil

    from huggingface_hub import scan_cache_dir, snapshot_download

    from .config import MODEL_DIR

    for size, bits in (("1.8B", 8), ("7B", 4)):
        if f"hymt{size.lower()}" not in names:
            continue
        out = MODEL_DIR / f"HY-MT1.5-{size}-mlx-{bits}bit"
        if (out / "config.json").exists():
            continue
        repo = f"tencent/HY-MT1.5-{size}"
        print(f"Downloading and converting {repo} to MLX {bits}-bit ...", flush=True)
        snapshot_download(repo)
        subprocess.run(
            [
                sys.executable,
                "-m",
                "mlx_lm",
                "convert",
                "--hf-path",
                repo,
                "--mlx-path",
                str(out),
                "-q",
                "--q-bits",
                str(bits),
            ],
            check=True,
        )
        for r in scan_cache_dir().repos:
            if r.repo_id == repo:
                shutil.rmtree(r.repo_path, ignore_errors=True)  # the converted copy is all we use


def cmd_export_srt(args) -> int:
    from .transcript import TranscriptLog, export_srt, parse_clock

    day = date.fromisoformat(args.date) if args.date else date.today()
    records = TranscriptLog().read(day)
    if not records:
        print(f"No transcript for {day}.")
        return 1
    srt = export_srt(
        records, parse_clock(day, args.start), parse_clock(day, args.end), text=args.text, offset_s=args.offset
    )
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(srt)
        print(f"Wrote {args.output}")
    else:
        sys.stdout.write(srt)
    return 0


def cmd_update_schedule(args) -> int:
    from . import schedule as sched

    sessions = sched.fetch_agenda(args.url)
    sched.save(sessions, sched.OVERRIDE)
    for x in sessions:
        print(f"{x.start[11:16]}  {(x.lang or 'auto'):4}  {x.title}")
    print(f"\nSaved {len(sessions)} sessions to {sched.OVERRIDE}")
    return 0


def cmd_benchmark(args) -> int:
    from .bench.benchmark import main as bench_main

    return bench_main(args)


def cmd_fetch_bench_audio(args) -> int:
    from .bench.fetch import main as fetch_main

    return fetch_main(args)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="live-translate", description="Live EN<->TR subtitles for OBS.")
    sub = p.add_subparsers(dest="command")

    def add_run_args(sp):
        sp.add_argument("--no-autostart", action="store_true", help="wait for Start in the control panel")
        sp.add_argument("--online", action="store_true", help="allow Hugging Face network access")
        sp.add_argument("-v", "--verbose", action="store_true")

    r = sub.add_parser("run", help="run the app (default)")
    add_run_args(r)
    r.set_defaults(func=cmd_run, play=None, speed=1.0)

    pl = sub.add_parser("play", help="test mode: play an audio/video file through the pipeline")
    pl.add_argument("file")
    pl.add_argument("--speed", type=float, default=1.0, help="playback speed (1 = real time)")
    add_run_args(pl)
    pl.set_defaults(func=lambda a: cmd_run(argparse.Namespace(**{**vars(a), "play": a.file})))

    d = sub.add_parser("download-models", help="download models so the app works offline")
    d.add_argument(
        "--all", action="store_true", help="also get the candidates worth comparing on the event Mac (about 19 GB)"
    )
    d.add_argument(
        "--include",
        nargs="*",
        metavar="CANDIDATE",
        help="extra benchmark candidates, e.g. tg27b medium-750 (see bench/candidates.py)",
    )
    d.set_defaults(func=cmd_download_models)

    e = sub.add_parser("export-srt", help="export subtitles for a time range as SRT")
    e.add_argument("--date", help="YYYY-MM-DD (default today)")
    e.add_argument("--from", dest="start", default="00:00", help="HH:MM[:SS], also the time 00:00:00 in the SRT")
    e.add_argument("--to", dest="end", default="23:59:59")
    e.add_argument("--text", choices=["translation", "source", "both"], default="translation")
    e.add_argument("--offset", type=float, default=0.0, help="seconds added to every cue")
    e.add_argument("-o", "--output")
    e.set_defaults(func=cmd_export_srt)

    u = sub.add_parser("update-schedule", help="fetch the agenda from the website")
    u.add_argument("--url", default="https://istanbul.python.pizza/compact-agenda/")
    u.set_defaults(func=cmd_update_schedule)

    b = sub.add_parser("benchmark", help="measure models on this Mac")
    b.add_argument("--asr", nargs="*", help="ASR candidates (names from bench/candidates.py)")
    b.add_argument("--mt", nargs="*", help="MT candidates")
    b.add_argument("--pipeline", nargs="*", help="end-to-end runs: ASR_NAME+MT_NAME")
    b.add_argument("--soak", type=float, default=0, help="minutes of full-pipeline soak test")
    b.add_argument("--quick", action="store_true", help="short clips only")
    b.set_defaults(func=cmd_benchmark)

    f = sub.add_parser("fetch-bench-audio", help="download public EN/TR talk audio for the benchmark")
    f.set_defaults(func=cmd_fetch_bench_audio)

    argv = list(sys.argv[1:] if argv is None else argv)
    commands = set(sub.choices)
    if not argv or (argv[0] not in commands and argv[0] not in ("-h", "--help")):
        argv = ["run", *argv]  # `live-translate [options]` means `live-translate run [options]`
    args = p.parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
