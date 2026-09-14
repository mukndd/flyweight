import asyncio
import json
import sys
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, ConfigDict, Field

from .checkpoints import list_candidates, load_candidate
from .config import SETTINGS
from .human_challenge import create_session, leaderboard_values, verified_match_result
from .ladder import ladder_manifest
from .limits import (
    CHECKPOINTS,
    IDLE_SECONDS,
    MAX_CONNECTIONS,
    MAX_MESSAGE_BYTES,
    MAX_TRAIN_SECONDS,
    MESSAGE_RATE,
    PROCESSED,
    ROOT,
)
from .neural import TOPOLOGIES, Controller, Graph
from .protocol import Load, Observation, Reset, Train, parse_message
from .research_registry import ResearchRegistry
from .storage import read_json, safe_path

graph = None
connections = 0
training = None
canonical_arrays = None
canonical_checkpoint = "seed-initialized"
canonical_checkpoint_hash = ""


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
    global canonical_arrays, canonical_checkpoint, canonical_checkpoint_hash, graph
    if not (PROCESSED / "flywire.json").exists() and not (PROCESSED / "synthetic.json").exists():
        if SETTINGS.production:
            raise ValueError("Production requires a prepared and validated graph")
        from .preprocess import synthetic
        synthetic()
    graph = Graph(synthetic=not (PROCESSED / "flywire.json").exists())
    if SETTINGS.production:
        pointer = CHECKPOINTS / "canonical.json"
        if not pointer.exists():
            raise ValueError("Production requires a validated canonical champion pointer")
        meta = read_json(pointer)
        canonical_arrays, candidate = load_candidate(graph, meta["id"])
        canonical_checkpoint, canonical_checkpoint_hash = candidate["id"], candidate["sha256"]
    # Cache bounded control matrices once; messages cannot launch repeated rewiring.
    for topology in TOPOLOGIES:
        graph.matrix(topology)
    yield
    if training:
        await training.stop()


app = FastAPI(title="Flyweight local brain", version="0.1.0", lifespan=lifespan, docs_url=None, redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=list(SETTINGS.origins), allow_methods=["GET", "POST"], allow_headers=["content-type"])
app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(SETTINGS.allowed_hosts) + ([] if SETTINGS.production else ["testserver"]))


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
    return {"v": 2, "type": "health", "status": "ready", "training": training is not None,
            "neurons": graph.n, "edges": graph.e, "synthetic": graph.manifest["synthetic"], "training_enabled": SETTINGS.training_enabled}


def read_registry(view):
    registry = ResearchRegistry()
    try:
        return view(registry)
    finally:
        registry.close()


@app.get("/research/overview")
async def research_overview():
    return read_registry(lambda registry: registry.overview())


@app.get("/research/lineage")
async def research_lineage():
    return read_registry(lambda registry: registry.lineage())


@app.get("/research/ladder")
async def research_ladder():
    return ladder_manifest()


@app.get("/research/reports")
async def research_reports():
    return read_registry(lambda registry: registry.daily_reports())


@app.get("/research/topology")
async def research_topology():
    return read_registry(lambda registry: registry.topology_status())


@app.get("/human/matches")
async def human_matches():
    return read_registry(lambda registry: registry.recent_human_matches())


@app.get("/human/session")
async def human_session():
    def current(registry):
        champion = registry.current_champion()
        session = create_session(champion["id"], champion["checkpoint_hash"]) if champion else create_session("seed-initialized", "seed-initialized")
        registry.record_human_session(session)
        return session
    return read_registry(current)


class HumanMatchSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    session_id: str = Field(pattern=r"^human_[a-f0-9]{16}$")
    nickname: str = Field(default="", max_length=24)
    replay: str = Field(min_length=20, max_length=1_000_000)


@app.post("/human/match")
async def human_match(submission: HumanMatchSubmission):
    def record(registry):
        session = registry.claim_human_session(submission.session_id)
        result = verified_match_result(session, submission.replay)
        match_id = registry.record_human_match(result)
        entries = leaderboard_values(result, submission.nickname)
        registry.record_leaderboard_entries(match_id, entries)
        return {"status": "accepted", "match_id": match_id, "leaderboard_entries": len(entries), "result": result}
    return read_registry(record)


@app.get("/research/status")
async def research_status():
    return read_registry(lambda registry: registry.overview().get("worker_status") or {"state": "idle"})


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
                await self.send({"v": 2, "type": "error", "code": "training_failed"})
        except (OSError, ValueError, TimeoutError, RuntimeError):
            await self.send({"v": 2, "type": "error", "code": "training_stopped"})
        finally:
            if self.process and self.process.returncode is None:
                self.process.terminate()
                await self.process.wait()
            if self.cancel_path.exists():
                self.cancel_path.unlink()
            if training is self:
                training = None

    async def stop(self):
        if self.task and self.task.done():
            return
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
    if ws.headers.get("origin") not in SETTINGS.origins or connections >= MAX_CONNECTIONS:
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
    controller = Controller(graph, arrays=canonical_arrays) if canonical_arrays is not None else Controller(graph)
    checkpoint = canonical_checkpoint
    checkpoint_hash = canonical_checkpoint_hash
    owned_job = None
    last_seq = -1
    current_seed = 783

    async def status():
        await send({"v": 2, "type": "status", "controller": "approximate recurrent" if controller.topology not in {"rule", "random"} else controller.topology,
                    "topology": controller.topology, "checkpoint": checkpoint, "checkpoint_hash": checkpoint_hash, "training_enabled": SETTINGS.training_enabled, **graph.view(controller.topology)})
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
                current_seed = message.seed
                controller = Controller(graph, message.seed, message.topology, canonical_arrays)
                last_seq, checkpoint, checkpoint_hash = -1, canonical_checkpoint, canonical_checkpoint_hash
                await status()
            elif isinstance(message, Observation):
                if message.seq <= last_seq:
                    await ws.close(code=1008)
                    break
                last_seq = message.seq
                action, tick_ms = controller.act(message.values)
                await send({"v": 2, "type": "action", "seq": message.seq, "action": action, "tick_ms": tick_ms, "scores": controller.last_scores, "available": controller.available, "inputs": controller.last_inputs, "rule": controller.rule})
                await send({"v": 2, "type": "neural_activity", "seq": message.seq, "values": controller.activity(),
                            "aggregate": float(abs(controller.state).mean()), "tick_ms": tick_ms})
            elif isinstance(message, Train):
                if not SETTINGS.training_enabled:
                    await send({"v": 2, "type": "error", "code": "training_disabled_in_production"})
                    continue
                if training is not None:
                    await send({"v": 2, "type": "error", "code": "training_busy"})
                else:
                    owned_job = TrainingJob(message, send)
                    training = owned_job
                    owned_job.task = asyncio.create_task(owned_job.run())
            elif isinstance(message, Load):
                try:
                    arrays, metadata = load_candidate(graph, message.id)
                except (ValueError, OSError):
                    await send({"v": 2, "type": "error", "code": "checkpoint_incompatible"})
                    await status()
                    continue
                controller = Controller(graph, current_seed, controller.topology, arrays)
                checkpoint = message.id
                checkpoint_hash = metadata['sha256']
                await send({"v": 2, "type": "checkpoint_load", "id": checkpoint})
                await status()
            elif message.type == "health":
                await send({"v": 2, "type": "health", "status": "ready", "training": training is not None})
            elif message.type == "checkpoint_list":
                await send({"v": 2, "type": "checkpoint_list", "items": list_candidates(graph)})
            elif message.type == "train_stop":
                if owned_job:
                    await owned_job.stop()
                await send({"v": 2, "type": "health", "status": "training_cancelled", "training": False})
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

