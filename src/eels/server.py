"""HTTP + WebSocket server: overlay (/), control panel (/control, localhost only), health."""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from . import schedule as sched
from .audio import list_input_devices
from .config import STATIC_DIR
from .pipeline import Pipeline
from .transcript import TranscriptLog, export_srt, parse_clock

log = logging.getLogger(__name__)
LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}


class Hub:
    """Fan-out of messages to WebSocket clients. Each client has its own queue so a slow
    client never blocks the others; overlay state messages are coalesced to the latest."""

    def __init__(self) -> None:
        self.loop: asyncio.AbstractEventLoop | None = None
        self.clients: dict[str, set[asyncio.Queue]] = {"overlay": set(), "control": set()}

    def publish(self, channel: str, msg: dict) -> None:
        """Thread-safe: called from pipeline threads."""
        if self.loop is None or self.loop.is_closed():
            return
        data = json.dumps(msg, ensure_ascii=False)
        self.loop.call_soon_threadsafe(self._fanout, channel, data)

    def _fanout(self, channel: str, data: str) -> None:
        for q in list(self.clients.get(channel, ())):
            if q.full():
                try:
                    q.get_nowait()  # drop the oldest; the newest state matters most
                except asyncio.QueueEmpty:
                    pass
            q.put_nowait(data)


def is_local(host: str | None) -> bool:
    return host in LOCAL_HOSTS


def create_app(hub: Hub, pipeline: Pipeline) -> FastAPI:
    transcripts = TranscriptLog()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        hub.loop = asyncio.get_running_loop()
        yield
        hub.loop = None

    app = FastAPI(title="eels", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    def require_local(request: Request) -> None:
        if not is_local(request.client.host if request.client else None):
            raise HTTPException(403, "The control panel is only available on this Mac (http://localhost:8000/control).")

    @app.get("/")
    async def overlay():
        return FileResponse(STATIC_DIR / "overlay.html", headers={"Cache-Control": "no-store"})

    @app.get("/control")
    async def control(request: Request):
        require_local(request)
        return FileResponse(STATIC_DIR / "control.html", headers={"Cache-Control": "no-store"})

    @app.get("/health")
    async def health():
        return JSONResponse(pipeline.health())

    @app.get("/api/transcript/days")
    async def transcript_days(request: Request):
        require_local(request)
        return transcripts.days()

    @app.get("/api/srt")
    async def srt(
        request: Request,
        day: str,
        start: str = "00:00",
        end: str = "23:59:59",
        text: str = "translation",
        offset: float = 0.0,
    ):
        require_local(request)
        try:
            d = date.fromisoformat(day)
            a, b = parse_clock(d, start), parse_clock(d, end)
        except ValueError as exc:
            raise HTTPException(400, f"bad date or time: {exc}")
        if text not in ("translation", "source", "both"):
            raise HTTPException(400, "text must be translation, source or both")
        body = export_srt(transcripts.read(d), a, b, text=text, offset_s=offset)
        name = f"subtitles_{day}_{start.replace(':', '')}-{end.replace(':', '')}_{text}.srt"
        return PlainTextResponse(
            body, media_type="application/x-subrip", headers={"Content-Disposition": f'attachment; filename="{name}"'}
        )

    async def pump(ws: WebSocket, q: asyncio.Queue) -> None:
        while True:
            await ws.send_text(await q.get())

    @app.websocket("/ws/overlay")
    async def ws_overlay(ws: WebSocket):
        await ws.accept()
        q: asyncio.Queue = asyncio.Queue(maxsize=4)
        hub.clients["overlay"].add(q)
        q.put_nowait(json.dumps(pipeline.display.snapshot(), ensure_ascii=False))
        sender = asyncio.create_task(pump(ws, q))
        try:
            while True:
                await ws.receive_text()  # only to notice disconnects (and client pings)
        except WebSocketDisconnect:
            pass
        finally:
            sender.cancel()
            hub.clients["overlay"].discard(q)

    @app.websocket("/ws/control")
    async def ws_control(ws: WebSocket):
        if not is_local(ws.client.host if ws.client else None):
            await ws.close(code=1008)
            return
        await ws.accept()
        q: asyncio.Queue = asyncio.Queue(maxsize=50)
        hub.clients["control"].add(q)
        q.put_nowait(json.dumps(pipeline.status(), ensure_ascii=False))
        q.put_nowait(json.dumps({"type": "devices", "devices": list_input_devices()}))
        q.put_nowait(
            json.dumps({"type": "schedule", "sessions": [s.__dict__ for s in pipeline.sessions]}, ensure_ascii=False)
        )
        sender = asyncio.create_task(pump(ws, q))
        try:
            while True:
                msg = await ws.receive_json()
                try:
                    reply = await asyncio.to_thread(handle_command, msg)
                except Exception as exc:
                    log.exception("control command %s", msg)
                    reply = {"type": "error", "msg": str(exc)}
                if reply:
                    await ws.send_text(json.dumps(reply, ensure_ascii=False))
        except WebSocketDisconnect:
            pass
        finally:
            sender.cancel()
            hub.clients["control"].discard(q)

    def handle_command(msg: dict) -> dict | None:
        cmd = msg.get("cmd")
        if cmd == "start":
            pipeline.start()
        elif cmd == "stop":
            pipeline.stop()
        elif cmd == "settings":
            pipeline.apply_settings(msg.get("values", {}))
        elif cmd == "clear":
            pipeline.display.clear()
        elif cmd == "test":
            pipeline.display.show_test()
        elif cmd == "devices":
            from .audio import reinit_portaudio

            if not pipeline.capture.stream:
                reinit_portaudio()
            return {"type": "devices", "devices": list_input_devices()}
        elif cmd == "play":
            pipeline.play_file(msg["path"], float(msg.get("speed", 1.0)))
        elif cmd == "live":
            pipeline.use_live()
        elif cmd == "models":
            from .models import catalog

            return {"type": "models", **catalog()}
        elif cmd == "switch_model":
            pipeline.switch_model(msg["kind"], msg["model"], msg.get("audio_ctx"))
        elif cmd == "update_schedule":
            sessions = sched.fetch_agenda()
            sched.save(sessions, sched.OVERRIDE)
            pipeline.reload_schedule()
            return {
                "type": "schedule",
                "sessions": [s.__dict__ for s in pipeline.sessions],
                "msg": f"{len(sessions)} sessions loaded",
            }
        else:
            return {"type": "error", "msg": f"unknown command {cmd!r}"}
        return {"type": "ok", "cmd": cmd}

    return app
