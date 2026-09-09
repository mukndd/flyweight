"""Bounded NumPy CEM; subprocess bridge runs the exact browser combat rules."""
import argparse
import json
import queue
import shutil
import subprocess  # nosec B404 -- bounded fixed authored bridge and read-only local Git; no shell
import sys
import threading
import time
import uuid

import numpy as np

from .checkpoints import load_candidate, promote, rollback, save_candidate
from .limits import CHECKPOINTS, MAX_TRAIN_SECONDS, ROOT
from .neural import TOPOLOGIES, Controller, Graph
from .storage import digest, read_json, safe_path

EVAL_SEEDS = [10_000_001, 10_000_002, 10_000_003]
DIFFICULTIES = ["easy", "medium", "hard"]


def code_commit():
    result = subprocess.run(["git", "-c", "safe.directory=" + str(ROOT), "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=3, check=False)  # nosec B603 B607 -- fixed local read-only Git command
    return result.stdout.strip() or "uncommitted"


class Bridge:
    def __init__(self):
        node = shutil.which("node")
        if not node:
            raise ValueError("Node required for shared combat engine")
        script = ROOT / "dist/sim/sim/bridge.js"
        if not script.exists():
            raise ValueError("Compile simulation: node scripts/task.mjs sim")
        self.process = subprocess.Popen([node, str(script)], cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, text=True, bufsize=1,
                                        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)  # nosec B603 -- fixed authored local bridge, no client paths
        self.started = time.monotonic()
        self.responses = queue.Queue(maxsize=1)
        def read():
            try:
                while line := self.process.stdout.readline(32_768):
                    self.responses.put(line, timeout=5)
            except (OSError, ValueError, queue.Full):
                return
        self.reader = threading.Thread(target=read, daemon=True)
        self.reader.start()

    def request(self, value):
        if self.process.poll() is not None or time.monotonic() - self.started > MAX_TRAIN_SECONDS:
            raise ValueError("Bridge stopped/time limit")
        self.process.stdin.write(json.dumps(value, allow_nan=False) + "\n")
        self.process.stdin.flush()
        try:
            line = self.responses.get(timeout=5)
        except queue.Empty as error:
            self.process.terminate()
            raise ValueError("Bridge response time limit") from error
        if not line or len(line) >= 32_768:
            raise ValueError("Bridge response limit")
        result = json.loads(line)
        if "error" in result:
            raise ValueError("Bridge rejected request")
        return result

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
        self.process.wait(timeout=5)
        self.process.stdin.close()
        self.reader.join(timeout=1)
        self.process.stdout.close()


def episode(graph, arrays, seed, difficulty, seconds=12, topology="real", ablate=None, bridge=None):
    own = bridge is None
    bridge = bridge or Bridge()
    controller = Controller(graph, seed, topology, arrays)
    start = time.perf_counter()
    neural_ms, idle, reactions, signal_started = [], 0, [], None
    try:
        result = bridge.request({"type": "reset", "seed": seed, "difficulty": difficulty, "limit": seconds * 60})
        while result["state"]["winner"] is None:
            obs = result["observation"]
            if ablate is not None:
                obs[ablate] = 0
            if obs[7] and signal_started is None:
                signal_started = result["state"]["frame"]
            if not obs[7]:
                signal_started = None
            action, tick_ms = controller.act(obs)
            neural_ms.append(tick_ms)
            idle += action == 0
            if signal_started is not None and action in (4, 7):
                reactions.append((result["state"]["frame"] - signal_started) / 60)
                signal_started = None
            result = bridge.request({"type": "step", "action": action})
        state = result["state"]
        rival, agent = state["fighters"]
        dealt, received = 100 - rival["hp"], 100 - agent["hp"]
        win = state["winner"] == 1
        # Arena control is scored only when damage was dealt; no per-distance movement reward.
        reward = result["rewards"][1]
        return {"seed": seed, "difficulty": difficulty, "reward": reward, "win": bool(win),
                "damage_dealt": dealt, "damage_received": received, "blocks": agent["blocks"],
                "duration": state["frame"] / 60, "reaction_seconds": float(np.mean(reactions)) if reactions else None,
                "reaction_samples": len(reactions), "mean_brain_ms": float(np.mean(neural_ms)),
                "elapsed_seconds": time.perf_counter() - start, "final_hash": result["hash"], "failure": None,
                "ablated_channel": ablate}
    finally:
        if own:
            bridge.close()


def summary(rows):
    rewards = np.array([r["reward"] for r in rows], dtype=float)
    sd = float(rewards.std(ddof=1)) if len(rewards) > 1 else 0
    return {"episodes": len(rows), "mean_reward": float(rewards.mean()), "median_reward": float(np.median(rewards)),
            "std_reward": sd, "ci95_normal_approx": [float(rewards.mean() - 1.96 * sd / np.sqrt(len(rows))), float(rewards.mean() + 1.96 * sd / np.sqrt(len(rows)))],
            "win_rate": float(np.mean([r["win"] for r in rows])), "failures": sum(r["failure"] is not None for r in rows),
            "average_damage": float(np.mean([r["damage_dealt"] for r in rows])),
            "average_duration": float(np.mean([r["duration"] for r in rows]))}


def evaluate(graph, arrays, seconds=12, topology="real", ablate=None):
    bridge = Bridge()
    try:
        rows = [episode(graph, arrays, seed, difficulty, seconds, topology, ablate, bridge)
                for difficulty in DIFFICULTIES for seed in EVAL_SEEDS]
    finally:
        bridge.close()
    return {"suite": "evaluation-v2", **summary(rows), "rows": rows}


def train(graph, seed=783, generations=2, population=6, seconds=12, emit=print, cancelled=lambda: False):
    if type(seed) is not int or not 0 <= seed <= 999_999 or not 1 <= generations <= 20 or not 4 <= population <= 12 or not 6 <= seconds <= 30:
        raise ValueError("Training hyperparameter bounds")
    CHECKPOINTS.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex[:16]
    raw_path = CHECKPOINTS / ("run_" + run_id + ".jsonl")
    controller = Controller(graph, seed)
    shapes = {k: v.shape for k, v in controller.arrays().items()}
    sizes = {k: int(np.prod(v)) for k, v in shapes.items()}
    def unpack(vector):
        offset = 0
        result = {}
        for key, size in sizes.items():
            result[key] = vector[offset:offset+size].reshape(shapes[key]).astype(np.float32)
            offset += size
        return result
    mean = np.concatenate([v.ravel() for v in controller.arrays().values()])
    std = np.full_like(mean, .4)
    rng = np.random.default_rng(seed)
    started = time.monotonic()
    metadata = {"format_version": 2, "run": run_id, "seed": seed, "code_commit": code_commit(),
                "dataset_hash": graph.manifest["graph_hash"], "config": {"generations": generations, "population": population, "seconds": seconds},
                "training_seeds": [seed + 1000 + i for i in range(generations)], "evaluation_seeds": EVAL_SEEDS,
                "method": "CEM adapters only; topology and biological strengths frozen", "status": "exploratory"}
    best_arrays, checkpoint = controller.arrays(), ""
    bridge = Bridge()
    try:
        with raw_path.open("x", encoding="utf-8") as raw:
            raw.write(json.dumps(metadata) + "\n")
            for generation in range(1, generations + 1):
                if cancelled() or time.monotonic() - started > MAX_TRAIN_SECONDS:
                    emit(json.dumps({"v": 2, "type": "train_progress", "generation": generation-1, "generations": generations,
                                     "reward": 0, "win_rate": 0, "checkpoint": checkpoint, "seed": seed, "status": "cancelled"}))
                    return checkpoint
                candidates = rng.normal(mean, std, (population, len(mean))).astype(np.float32)
                candidates[0] = mean
                results = []
                for member, candidate in enumerate(candidates):
                    if cancelled():
                        emit(json.dumps({"v": 2, "type": "train_progress", "generation": generation-1, "generations": generations,
                                         "reward": 0, "win_rate": 0, "checkpoint": checkpoint, "seed": seed, "status": "cancelled"}))
                        return checkpoint
                    rows = [episode(graph, unpack(candidate), seed + 999 + generation, difficulty, seconds, bridge=bridge)
                            for difficulty in DIFFICULTIES]
                    stats = summary(rows)
                    raw.write(json.dumps({"generation": generation, "member": member, "rows": rows, "summary": stats}) + "\n")
                    raw.flush()
                    results.append(stats["mean_reward"])
                elite = np.argsort(results)[-max(2, population // 3):]
                mean = candidates[elite].mean(axis=0)
                std = np.maximum(.04, candidates[elite].std(axis=0))
                best_arrays = unpack(candidates[int(np.argmax(results))])
                checkpoint = save_candidate(graph, best_arrays, {"seed": seed, "generation": generation, "reward": max(results)})
                emit(json.dumps({"v": 2, "type": "train_progress", "generation": generation, "generations": generations,
                                 "reward": max(results), "win_rate": 0, "checkpoint": checkpoint, "seed": seed, "status": "training"}))
            report = evaluate(graph, best_arrays, seconds)
            raw.write(json.dumps({"checkpoint": checkpoint, "checkpoint_hash": digest(CHECKPOINTS / (checkpoint + ".npz")), "evaluation": report}) + "\n")
            emit(json.dumps({"v": 2, "type": "train_progress", "generation": generations, "generations": generations,
                             "reward": report["mean_reward"], "win_rate": report["win_rate"], "checkpoint": checkpoint,
                             "seed": seed, "status": "evaluated candidate"}))
    except (ValueError, OSError, RuntimeError, TimeoutError) as error:
        with raw_path.open("a", encoding="utf-8") as raw:
            raw.write(json.dumps({"status": "failed", "failure": type(error).__name__}) + "\n")
        raise
    finally:
        bridge.close()
    return checkpoint


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["train", "evaluate", "promote", "rollback", "controls"])
    parser.add_argument("--seed", type=int, default=783)
    parser.add_argument("--generations", type=int, default=2)
    parser.add_argument("--population", type=int, default=6)
    parser.add_argument("--seconds", type=int, default=12)
    parser.add_argument("--checkpoint")
    parser.add_argument("--cancel-id")
    args = parser.parse_args()
    if not 6 <= args.seconds <= 30 or not 0 <= args.seed <= 999_999:
        parser.error("Bounded seconds/seed required")
    graph = Graph(synthetic=not (ROOT / "data/processed/flywire.json").exists())
    arrays = load_candidate(graph, args.checkpoint)[0] if args.checkpoint else Controller(graph, args.seed).arrays()
    if args.command == "train":
        train(graph, args.seed, args.generations, args.population, args.seconds, emit=lambda line: print(line, flush=True), cancelled=lambda: bool(args.cancel_id and safe_path(ROOT / ".runtime", args.cancel_id).exists()))
    elif args.command == "rollback":
        rollback(graph)
    elif args.command == "controls":
        path = CHECKPOINTS / ("controls_" + uuid.uuid4().hex[:16] + ".jsonl")
        with path.open("x", encoding="utf-8") as file:
            file.write(json.dumps({"version": 1, "code_commit": code_commit(), "graph_hash": graph.manifest["graph_hash"],
                                   "checkpoint_hash": digest(CHECKPOINTS / (args.checkpoint + ".npz")) if args.checkpoint else "seed-initialized",
                                   "suite": "evaluation-v2", "seeds": EVAL_SEEDS, "seconds": args.seconds, "status": "exploratory",
                                   "compute": "8 recurrent microsteps; identical adapter shapes for neural controls"}) + "\n")
            for run_seed in [args.seed, args.seed+1, args.seed+2]:
                adapters = arrays if args.checkpoint else Controller(graph, run_seed).arrays()
                for topology in TOPOLOGIES:
                    for ablate in [None, 7]:
                        result = evaluate(graph, adapters, args.seconds, topology, ablate)
                        record = {"initialization_seed": run_seed, "topology": topology, "ablated_channel": ablate, **result}
                        file.write(json.dumps(record) + "\n")
                        file.flush()
                        print(json.dumps({k: v for k, v in record.items() if k != "rows"}), flush=True)
    else:
        result = evaluate(graph, arrays, args.seconds)
        if args.command == "promote":
            if not args.checkpoint:
                parser.error("--checkpoint required")
            pointer = CHECKPOINTS / "canonical.json"
            previous = load_candidate(graph, read_json(pointer)["id"])[0] if pointer.exists() else Controller(graph, 783).arrays()
            result["previous_reward"] = evaluate(graph, previous, args.seconds)["mean_reward"]
            promote(graph, args.checkpoint, result)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

