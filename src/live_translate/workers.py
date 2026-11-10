"""Supervised model worker processes.

Each model (ASR, MT) runs in its own spawned process so a crash or hang in Metal code
cannot take down the server or the audio capture. The parent restarts the worker on
crash or timeout, with backoff, and keeps a short list of recent errors for the panel.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import importlib
import logging
import os
import multiprocessing as mp
import queue
import threading
import time
import traceback
from collections import deque
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)


class WorkerError(RuntimeError):
    pass


class _RUsageInfoV2(ctypes.Structure):
    _fields_ = [("ri_uuid", ctypes.c_uint8 * 16)] + [
        (name, ctypes.c_uint64)
        for name in (
            "ri_user_time", "ri_system_time", "ri_pkg_idle_wkups", "ri_interrupt_wkups", "ri_pageins",
            "ri_wired_size", "ri_resident_size", "ri_phys_footprint", "ri_proc_start_abstime",
            "ri_proc_exit_abstime", "ri_child_user_time", "ri_child_system_time", "ri_child_pkg_idle_wkups",
            "ri_child_interrupt_wkups", "ri_child_pageins", "ri_child_elapsed_abstime",
            "ri_diskio_bytesread", "ri_diskio_byteswritten",
        )
    ]


_libproc = ctypes.CDLL(ctypes.util.find_library("proc") or "libproc.dylib")


def footprint_mb(pid: int) -> float | None:
    """Physical footprint in MB via proc_pid_rusage. Unlike ps RSS it counts compressed
    memory, so it does not drop misleadingly when macOS is under memory pressure."""
    info = _RUsageInfoV2()
    if _libproc.proc_pid_rusage(pid, 2, ctypes.byref(info)) != 0:
        return None
    return info.ri_phys_footprint / 2**20


MLX_CACHE_LIMIT = 512 * 2**20  # MLX keeps freed GPU buffers up to the memory limit (~RAM) by default


def _exit_with_parent(parent_pid: int) -> None:
    """Exit if the app process dies, so a killed app never leaves workers holding gigabytes."""
    import os

    def watch():
        while True:
            time.sleep(1.0)
            if os.getppid() != parent_pid:
                os._exit(0)

    threading.Thread(target=watch, name="parent-watch", daemon=True).start()


def _worker_main(factory: str, spec: dict, req_q, resp_q, parent_pid: int = 0) -> None:
    """Entry point in the child process. factory is 'module:function'."""
    import os

    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    # Ctrl+C in the terminal reaches every process in the group; the app stops the workers itself.
    import signal

    signal.signal(signal.SIGINT, signal.SIG_IGN)
    if parent_pid:
        _exit_with_parent(parent_pid)
    # LIVE_TRANSLATE_MLX_CACHE_MB overrides the cap; 0 keeps MLX's default (the memory limit).
    cache_mb = int(os.environ.get("LIVE_TRANSLATE_MLX_CACHE_MB", MLX_CACHE_LIMIT // 2**20))
    if cache_mb > 0:
        try:
            import mlx.core as mx

            mx.set_cache_limit(cache_mb * 2**20)
        except Exception:
            pass
    try:
        mod_name, fn_name = factory.split(":")
        backend = getattr(importlib.import_module(mod_name), fn_name)(**spec)
        resp_q.put(("__ready__", "ok", getattr(backend, "info", {})))
    except BaseException:
        resp_q.put(("__fatal__", "error", traceback.format_exc()))
        return
    while True:
        item = req_q.get()
        if item is None:
            return
        req_id, payload = item
        try:
            resp_q.put((req_id, "ok", backend.handle(payload)))
        except Exception:
            resp_q.put((req_id, "error", traceback.format_exc()))


@dataclass
class WorkerStatus:
    name: str
    state: str = "stopped"  # stopped | loading | ready | busy | error | restarting
    info: dict = field(default_factory=dict)
    restarts: int = 0
    last_call_ms: float = 0.0
    rss_mb: float | None = None
    baseline_mb: float | None = None  # footprint right after the model loaded
    errors: deque = field(default_factory=lambda: deque(maxlen=10))

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "state": self.state,
            "info": self.info,
            "restarts": self.restarts,
            "last_call_ms": round(self.last_call_ms, 1),
            "rss_mb": None if self.rss_mb is None else round(self.rss_mb),
            "baseline_mb": None if self.baseline_mb is None else round(self.baseline_mb),
            "errors": list(self.errors),
        }


class WorkerClient:
    """Synchronous client for one worker process. Use from a single thread."""

    def __init__(
        self,
        name: str,
        factory: str,
        spec: dict,
        load_timeout: float = 600.0,
    ) -> None:
        self.name = name
        self.factory = factory
        self.spec = spec
        self.load_timeout = load_timeout
        self.status = WorkerStatus(name)
        self._ctx = mp.get_context("spawn")
        self._proc: Any = None
        self._req_q: Any = None
        self._resp_q: Any = None
        self._next_id = 0
        self._ready = False
        self._backoff = 0.0
        self._lock = threading.Lock()

    # Lifecycle ------------------------------------------------------------
    def start(self) -> None:
        with self._lock:
            self._spawn()

    def _spawn(self) -> None:
        self._req_q = self._ctx.Queue()
        self._resp_q = self._ctx.Queue()
        self._proc = self._ctx.Process(
            target=_worker_main,
            args=(self.factory, self.spec, self._req_q, self._resp_q, os.getpid()),
            name=f"live-translate-{self.name}",
            daemon=True,
        )
        self._ready = False
        self.status.state = "loading"
        self._spawned_at = time.monotonic()
        self._proc.start()
        log.info("%s worker started (pid %s, %s)", self.name, self._proc.pid, self.spec)

    def stop(self) -> None:
        with self._lock:
            self._kill()
            self.status.state = "stopped"

    def _kill(self) -> None:
        if self._proc is None:
            return
        try:
            if self._proc.is_alive():
                self._req_q.put(None)
                self._proc.join(timeout=2)
            if self._proc.is_alive():
                self._proc.kill()
                self._proc.join(timeout=2)
        except Exception:
            pass
        # Close this worker's queues now (pipes and feeder threads) instead of waiting for the GC.
        for q in (self._req_q, self._resp_q):
            try:
                q.cancel_join_thread()
                q.close()
            except Exception:
                pass
        self._proc = None
        self._ready = False

    def restart(self, reason: str) -> None:
        with self._lock:
            self._record_error(reason)
            self.status.restarts += 1
            self.status.state = "restarting"
            self._kill()
            # Back off a bit if it keeps failing so we do not spin.
            self._backoff = min(10.0, self._backoff * 2 + 1.0)
            time.sleep(self._backoff)
            self._spawn()

    def reconfigure(self, spec: dict) -> None:
        """Change model (or other options) and restart the worker."""
        with self._lock:
            self.spec = spec
            self._kill()
            self._spawn()

    def _record_error(self, msg: str) -> None:
        line = msg.strip().splitlines()[-1] if msg.strip() else msg
        self.status.errors.append({"t": time.strftime("%H:%M:%S"), "msg": line[:300]})
        log.error("%s worker: %s", self.name, msg.strip())

    def rss_mb(self) -> float | None:
        """Physical footprint of the worker (what Activity Monitor shows, incl. GPU and compressed memory)."""
        if not self.alive:
            return None
        return footprint_mb(self._proc.pid)

    @property
    def alive(self) -> bool:
        return self._proc is not None and self._proc.is_alive()

    @property
    def ready(self) -> bool:
        return self._ready and self.alive

    # Calls ----------------------------------------------------------------
    def wait_ready(self, timeout: float | None = None) -> bool:
        if self._proc is None:
            self.start()
        if self._ready:
            return True
        deadline = time.monotonic() + (timeout if timeout is not None else self.load_timeout)
        while time.monotonic() < deadline:
            if not self.alive:
                self.restart(f"process exited during load (code {self._proc.exitcode if self._proc else '?'})")
                return False
            try:
                msg = self._resp_q.get(timeout=0.2)
            except queue.Empty:
                continue
            if msg[0] == "__ready__":
                self._ready = True
                self._backoff = 0.0
                self.status.state = "ready"
                self.status.info = msg[2] or {}
                # Memory right after loading and warm-up: the watchdog limit is relative to this,
                # so bigger models (a 7B or 27B translator) are not mistaken for a leak.
                self.status.baseline_mb = self.rss_mb()
                log.info("%s worker ready in %.1fs (%s MB)", self.name, time.monotonic() - self._spawned_at,
                         None if self.status.baseline_mb is None else round(self.status.baseline_mb))
                return True
            if msg[0] == "__fatal__":
                self.status.state = "error"
                self._record_error(msg[2])
                self._kill()
                return False
        return False

    def poll(self) -> bool:
        """Non-blocking readiness check. Respawns a worker whose model failed to load, every 15 s."""
        if self.ready:
            return True
        now = time.monotonic()
        if self._proc is None:
            if now - self._last_spawn_try > 15.0:
                self._last_spawn_try = now
                with self._lock:
                    self._spawn()
            return False
        return self.wait_ready(timeout=0.02)

    _last_spawn_try = 0.0

    def call(self, payload: dict, timeout: float) -> dict:
        """Send one request and wait for its reply. Restarts the worker on crash or timeout."""
        if not self.ready:
            raise WorkerError(f"{self.name} worker not ready ({self.status.state})")
        self._next_id += 1
        req_id = self._next_id
        t0 = time.perf_counter()
        self.status.state = "busy"
        self._req_q.put((req_id, payload))
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self.restart(f"timeout after {timeout:.1f}s")
                raise WorkerError(f"{self.name} worker timed out")
            try:
                rid, kind, result = self._resp_q.get(timeout=min(remaining, 0.5))
            except queue.Empty:
                if not self.alive:
                    code = self._proc.exitcode if self._proc else "?"
                    self.restart(f"process died (exit code {code})")
                    raise WorkerError(f"{self.name} worker died")
                continue
            if rid != req_id:
                continue  # stale reply from an earlier timed-out request
            self.status.last_call_ms = (time.perf_counter() - t0) * 1000
            self.status.state = "ready"
            if kind == "error":
                self._record_error(result)
                raise WorkerError(f"{self.name} worker error: {result.strip().splitlines()[-1]}")
            return result
