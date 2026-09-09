import asyncio
import json
import sys
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from .checkpoints import list_candidates, load_candidate
from .limits import (IDLE_SECONDS, MAX_CONNECTIONS, MAX_MESSAGE_BYTES, MAX_TRAIN_SECONDS,
                     MESSAGE_RATE, ORIGIN, PROCESSED, ROOT)
from .neural import Controller, Graph, TOPOLOGIES
from .protocol import Load, Observation, Reset, Train, parse_message
from .storage import safe_path

graph = None
connections = 0
training = None


class RateLimiter:
    def __init__(self, rate=MESSAGE_RATE):
        self.rate, self.tokens, self.last = rate, float(rate), time.monotonic()

    def allow(self, now=None):
        now = time.monotonic() if now is None else now
        self.tokens = min(self.rate, self.tokens + (now-self.last)*self.rate)
        self.last = now
        if self.tokens < 1:
            return False
        self.tokens -= 1
        return True


@asynccontextmanager
async def lifespan(_app):
    global graph
    if not (PROCESSED / "flywire.json").exists() and not (PROCESSED / "synthetic.json").exists():
        from .preprocess import synthetic
        synthetic()
    graph = Graph(synthetic=not (PROCESSED / "flywire.json").exists())
    # Cache bounded control matrices once; messages cannot launch repeated rewiring.
    for topology in TOPOLOGIES:
        graph.matrix(topology)
    yield
    if training:
        await training.stop()


app = FastAPI(title="Flyweight local brain", version="0.1.0", lifespan=lifespan, docs_url=None, redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=[ORIGIN], allow_methods=["GET"], allow_headers=[])
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "testserver"])


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.get("/health")
async def health():
    return {"v": 1, "type": "health", "status": "ready", "training": training is not None,
            "neurons": graph.n, "edges": graph.e, "synthetic": graph.manifest["synthetic"]}


class TrainingJob:
    def __init__(self, message, send):
        self.message, self.send = message, send
        self.process = None
        self.task = None
        self.cancel_id = "cancel_" + uuid.uuid4().hex
        runtime = ROOT / ".runtime"
        runtime.mkdir(exist_ok=True)
        self.cancel_path = safe_path(runtime, self.cancel_id)

    async def run(self):
        global training
        m = self.message
        try:
            self.process = await asyncio.create_subprocess_exec(
                sys.executable, "-u", "-m", "services.brain.trainer", "train",
                "--seed", str(m.seed), "--generations", str(m.generations),
                "--population", str(m.population), "--seconds", str(m.episode_seconds),
                "--cancel-id", self.cancel_id, cwd=str(ROOT),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                limit=16_384)
            started = time.monotonic()
            while True:
                remaining = MAX_TRAIN_SECONDS - (time.monotonic() - started)
                if remaining <= 0:
                    raise TimeoutError
                line = await asyncio.wait_for(self.process.stdout.readline(), timeout=min(remaining, 120))
                if not line:
                    break
                if len(line) > 8192:
                    raise ValueError("Training output limit")
                data = json.loads(line)
                if data.get("type") == "train_progress":
                    await self.send(data)
            code = await self.process.wait()
            if code:
                await self.send({"v": 1, "type": "error", "code": "training_failed"})
        except (OSError, ValueError, TimeoutError, RuntimeError):
            await self.send({"v": 1, "type": "error", "code": "training_stopped"})
        finally:
            if self.process and self.process.returncode is None:
                self.process.terminate()
                await self.process.wait()
            if self.cancel_path.exists():
                self.cancel_path.unlink()
            if training is self:
                training = None

    async def stop(self):
        self.cancel_path.touch(exist_ok=True)
        if self.process and self.process.returncode is None:
            try:
                await asyncio.wait_for(asyncio.shield(self.process.wait()), timeout=5)
            except TimeoutError:
                self.process.terminate()
                await self.process.wait()


@app.websocket("/ws")
async def websocket(ws: WebSocket):
    global connections, training
    if ws.headers.get("origin") != ORIGIN or connections >= MAX_CONNECTIONS:
        await ws.close(code=1008)
        return
    connections += 1
    await ws.accept()
    send_lock = asyncio.Lock()
    alive = True
    async def send(value):
        if alive:
            async with send_lock:
                await asyncio.wait_for(ws.send_json(value), timeout=2)
    limiter = RateLimiter()
    controller = Controller(graph)
    checkpoint = "seed-initialized"
    owned_job = None
    last_seq = -1

    async def status():
        await send({"v": 1, "type": "status", "controller": "approximate recurrent" if controller.topology not in {"rule", "random"} else controller.topology,
                    "topology": controller.topology, "checkpoint": checkpoint, **graph.view(controller.topology)})
    try:
        await status()
        while True:
            packet = await asyncio.wait_for(ws.receive(), timeout=IDLE_SECONDS)
            if packet["type"] == "websocket.disconnect":
                break
            raw = packet.get("text")
            if raw is None or len(raw.encode("utf-8")) > MAX_MESSAGE_BYTES:
                await ws.close(code=1009)
                break
            if not limiter.allow():
                await ws.close(code=1008)
                break
            try:
                message = parse_message(raw)
            except (ValueError, TypeError):
                await ws.close(code=1008)
                break
            if isinstance(message, Reset):
                controller = Controller(graph, message.seed, message.topology)
                last_seq, checkpoint = -1, "seed-initialized"
                await status()
            elif isinstance(message, Observation):
                if message.seq <= last_seq:
                    await ws.close(code=1008)
                    break
                last_seq = message.seq
                action, tick_ms = controller.act(message.values)
                await send({"v": 1, "type": "action", "seq": message.seq, "action": action, "tick_ms": tick_ms})
                await send({"v": 1, "type": "neural_activity", "seq": message.seq, "values": controller.activity(),
                            "aggregate": float(abs(controller.state).mean()), "tick_ms": tick_ms})
            elif isinstance(message, Train):
                if training is not None:
                    await send({"v": 1, "type": "error", "code": "training_busy"})
                else:
                    owned_job = TrainingJob(message, send)
                    training = owned_job
                    owned_job.task = asyncio.create_task(owned_job.run())
            elif isinstance(message, Load):
                arrays, _ = load_candidate(graph, message.id)
                controller = Controller(graph, 783, controller.topology, arrays)
                checkpoint = message.id
                await send({"v": 1, "type": "checkpoint_load", "id": checkpoint})
                await status()
            elif message.type == "health":
                await send({"v": 1, "type": "health", "status": "ready", "training": training is not None})
            elif message.type == "checkpoint_list":
                await send({"v": 1, "type": "checkpoint_list", "items": list_candidates(graph)})
            elif message.type == "train_stop":
                if owned_job:
                    await owned_job.stop()
                await send({"v": 1, "type": "health", "status": "training_cancelled", "training": False})
    except (WebSocketDisconnect, TimeoutError, RuntimeError, ValueError, OSError):
        try:
            await ws.close(code=1008)
        except RuntimeError:
            pass
    finally:
        alive = False
        connections -= 1
        if owned_job:
            await owned_job.stop()
            if owned_job.task:
                await owned_job.task

