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
from .storage import atomic_json, digest, read_json, safe_path, validate_npz

EVAL_SEEDS = [10_000_001, 10_000_002, 10_000_003]
DIFFICULTIES = ["easy", "medium", "hard"]

# Bounded, documented presets. --preset fully determines the tunable search
# parameters below (individual flags are ignored when --preset is given) so
# a run is reproducible from its name alone; --seed and --resume still apply.
PRESETS = {
    "starter": {"generations": 4, "population": 8, "seconds": 10, "difficulties": ["easy"],
                "elite_fraction": 1 / 3, "sigma_init": .4, "sigma_floor": .05, "checkpoint_every": 1},
    "serious": {"generations": 20, "population": 12, "seconds": 25, "difficulties": DIFFICULTIES,
                "elite_fraction": 1 / 3, "sigma_init": .4, "sigma_floor": .04, "checkpoint_every": 2},
}


def save_resume_state(run_id, graph, mean, std, generation, config, root=CHECKPOINTS):
    root.mkdir(parents=True, exist_ok=True)
    ident = "resume_" + run_id
    path = safe_path(root, ident, ".npz")
    np.savez(path, mean=mean.astype(np.float32), std=std.astype(np.float32))
    atomic_json(safe_path(root, ident, ".json"), {"version": 1, "run_id": run_id, "graph_hash": graph.manifest["graph_hash"],
                "sha256": digest(path), "generation": generation, "config": config, "created_ns": time.time_ns()})


def load_resume_state(run_id, graph, root=CHECKPOINTS):
    ident = "resume_" + run_id
    meta = read_json(safe_path(root, ident, ".json"))
    if meta.get("version") != 1 or meta.get("run_id") != run_id:
        raise ValueError("Resume state metadata mismatch")
    if meta.get("graph_hash") != graph.manifest["graph_hash"]:
        raise ValueError("Resume state was recorded for a different connectome graph/subgraph")
    total = sum(int(np.prod(v.shape)) for v in Controller(graph).arrays().values())
    arrays = validate_npz(safe_path(root, ident, ".npz"), {"mean": ((total,), "float32"), "std": ((total,), "float32")}, meta["sha256"])
    if np.any(arrays["std"] <= 0):
        raise ValueError("Resume state has non-positive search spread")
    return arrays["mean"], arrays["std"], int(meta["generation"]), meta.get("config", {})


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


def train(graph, seed=783, generations=2, population=6, seconds=12, emit=print, cancelled=lambda: False,
          difficulties=None, elite_fraction=1 / 3, sigma_init=.4, sigma_floor=.04, checkpoint_every=1, run_id=None):
    if type(seed) is not int or not 0 <= seed <= 999_999 or not 1 <= generations <= 20 or not 4 <= population <= 12 or not 6 <= seconds <= 30:
        raise ValueError("Training hyperparameter bounds")
    difficulties = list(difficulties) if difficulties is not None else list(DIFFICULTIES)
    if not difficulties or any(d not in DIFFICULTIES for d in difficulties) or len(difficulties) != len(set(difficulties)):
        raise ValueError("Invalid training difficulty set")
    if not 0 < elite_fraction <= 1 or not 0 < sigma_floor <= sigma_init or not np.isfinite(sigma_init) or not 1 <= checkpoint_every <= generations:
        raise ValueError("Invalid search hyperparameters")
    CHECKPOINTS.mkdir(parents=True, exist_ok=True)
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
    resumed_from = None
    start_generation = 0
    if run_id is not None:
        # Explicit --resume must either genuinely continue the named run or fail
        # clearly; it must never silently restart search state under the same id.
        mean, std, start_generation, _prior_config = load_resume_state(run_id, graph, root=CHECKPOINTS)
        resumed_from = start_generation
    else:
        run_id = uuid.uuid4().hex[:16]
        mean = np.concatenate([v.ravel() for v in controller.arrays().values()])
        std = np.full_like(mean, sigma_init)
    raw_path = CHECKPOINTS / ("run_" + run_id + ".jsonl")
    rng = np.random.default_rng(seed + start_generation)
    started = time.monotonic()
    config = {"generations": generations, "population": population, "seconds": seconds, "difficulties": difficulties,
              "elite_fraction": elite_fraction, "sigma_init": sigma_init, "sigma_floor": sigma_floor}
    metadata = {"format_version": 2, "run": run_id, "seed": seed, "code_commit": code_commit(),
                "dataset_hash": graph.manifest["graph_hash"], "config": config,
                "training_seeds": [seed + 1000 + i for i in range(start_generation + 1, start_generation + generations + 1)],
                "evaluation_seeds": EVAL_SEEDS, "resumed_from_generation": resumed_from,
                "method": "CEM adapters only; topology and biological strengths frozen", "status": "exploratory"}
    best_arrays, checkpoint = controller.arrays(), ""
    bridge = Bridge()
    try:
        with raw_path.open("a" if resumed_from else "x", encoding="utf-8") as raw:
            raw.write(json.dumps(metadata) + "\n")
            for generation in range(start_generation + 1, start_generation + generations + 1):
                if cancelled() or time.monotonic() - started > MAX_TRAIN_SECONDS:
                    emit(json.dumps({"v": 2, "type": "train_progress", "generation": generation-1, "generations": start_generation + generations,
                                     "reward": 0, "win_rate": 0, "checkpoint": checkpoint, "seed": seed, "status": "cancelled", "run": run_id}))
                    return checkpoint
                candidates = rng.normal(mean, std, (population, len(mean))).astype(np.float32)
                candidates[0] = mean
                results, rows_by_member = [], []
                for member, candidate in enumerate(candidates):
                    if cancelled():
                        emit(json.dumps({"v": 2, "type": "train_progress", "generation": generation-1, "generations": start_generation + generations,
                                         "reward": 0, "win_rate": 0, "checkpoint": checkpoint, "seed": seed, "status": "cancelled", "run": run_id}))
                        return checkpoint
                    rows = [episode(graph, unpack(candidate), seed + 999 + generation, difficulty, seconds, bridge=bridge)
                            for difficulty in difficulties]
                    stats = summary(rows)
                    raw.write(json.dumps({"generation": generation, "member": member, "rows": rows, "summary": stats}) + "\n")
                    raw.flush()
                    results.append(stats["mean_reward"])
                    rows_by_member.append(rows)
                elite = np.argsort(results)[-max(2, int(population * elite_fraction)):]
                mean = candidates[elite].mean(axis=0)
                std = np.maximum(sigma_floor, candidates[elite].std(axis=0))
                best_member = int(np.argmax(results))
                best_arrays = unpack(candidates[best_member])
                training_win_rate = float(np.mean([r["win"] for r in rows_by_member[best_member]]))
                if generation % checkpoint_every == 0 or generation == start_generation + generations:
                    checkpoint = save_candidate(graph, best_arrays, {"seed": seed, "generation": generation, "reward": max(results)})
                    save_resume_state(run_id, graph, mean, std, generation, config, root=CHECKPOINTS)
                emit(json.dumps({"v": 2, "type": "train_progress", "generation": generation, "generations": start_generation + generations,
                                 "reward": max(results), "win_rate": 0, "training_win_rate": training_win_rate,
                                 "checkpoint": checkpoint, "seed": seed, "status": "training", "run": run_id}))
            report = evaluate(graph, best_arrays, seconds)
            raw.write(json.dumps({"checkpoint": checkpoint, "checkpoint_hash": digest(CHECKPOINTS / (checkpoint + ".npz")), "evaluation": report}) + "\n")
            emit(json.dumps({"v": 2, "type": "train_progress", "generation": start_generation + generations, "generations": start_generation + generations,
                             "reward": report["mean_reward"], "win_rate": report["win_rate"], "checkpoint": checkpoint,
                             "seed": seed, "status": "evaluated candidate", "run": run_id}))
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
    parser.add_argument("--generations", type=int, default=None)
    parser.add_argument("--population", type=int, default=None)
    parser.add_argument("--seconds", type=int, default=None)
    parser.add_argument("--checkpoint", help="Candidate id to load adapters from (evaluate/promote/rollback/controls).")
    parser.add_argument("--cancel-id")
    parser.add_argument("--preset", choices=sorted(PRESETS), help="Apply a named, documented training configuration (train only). Cannot be combined with --generations/--population/--seconds/--difficulties/--elite-fraction/--sigma-init/--sigma-floor/--checkpoint-every.")
    parser.add_argument("--difficulties", help="Comma-separated training opponents, e.g. easy,medium,hard (train only; default: all three, same as before).")
    parser.add_argument("--elite-fraction", type=float, default=None, dest="elite_fraction")
    parser.add_argument("--sigma-init", type=float, default=None, dest="sigma_init")
    parser.add_argument("--sigma-floor", type=float, default=None, dest="sigma_floor")
    parser.add_argument("--checkpoint-every", type=int, default=None, dest="checkpoint_every")
    parser.add_argument("--resume", help="Training run id to continue (see the 'run' field in train_progress output / run_<id>.jsonl). Fails clearly if the saved search state doesn't match this connectome graph.")
    args = parser.parse_args()
    train_only = ("generations", "population", "difficulties", "elite_fraction", "sigma_init", "sigma_floor", "checkpoint_every", "preset", "resume")
    if args.command != "train" and any(getattr(args, name) is not None for name in train_only):
        parser.error("--preset/--generations/--population/--seconds/--difficulties/--elite-fraction/--sigma-init/--sigma-floor/--checkpoint-every/--resume only apply to the train command")
    if args.preset:
        conflicting = [n for n in ("generations", "population", "seconds", "difficulties", "elite_fraction", "sigma_init", "sigma_floor", "checkpoint_every") if getattr(args, n) is not None]
        if conflicting:
            parser.error("--preset cannot be combined with: " + ", ".join("--" + n.replace("_", "-") for n in conflicting))
        preset = PRESETS[args.preset]
        generations, population, seconds = preset["generations"], preset["population"], preset["seconds"]
        difficulties, elite_fraction, sigma_init, sigma_floor, checkpoint_every = preset["difficulties"], preset["elite_fraction"], preset["sigma_init"], preset["sigma_floor"], preset["checkpoint_every"]
    else:
        generations = args.generations if args.generations is not None else 2
        population = args.population if args.population is not None else 6
        seconds = args.seconds if args.seconds is not None else 12
        difficulties = [d.strip() for d in args.difficulties.split(",")] if args.difficulties else None
        elite_fraction = args.elite_fraction if args.elite_fraction is not None else 1 / 3
        sigma_init = args.sigma_init if args.sigma_init is not None else .4
        sigma_floor = args.sigma_floor if args.sigma_floor is not None else .04
        checkpoint_every = args.checkpoint_every if args.checkpoint_every is not None else 1
    if not 6 <= seconds <= 30 or not 0 <= args.seed <= 999_999:
        parser.error("Bounded seconds/seed required")
    graph = Graph(synthetic=not (ROOT / "data/processed/flywire.json").exists())
    arrays = load_candidate(graph, args.checkpoint)[0] if args.checkpoint else Controller(graph, args.seed).arrays()
    if args.command == "train":
        try:
            train(graph, args.seed, generations, population, seconds, emit=lambda line: print(line, flush=True),
                  cancelled=lambda: bool(args.cancel_id and safe_path(ROOT / ".runtime", args.cancel_id).exists()),
                  difficulties=difficulties, elite_fraction=elite_fraction, sigma_init=sigma_init,
                  sigma_floor=sigma_floor, checkpoint_every=checkpoint_every, run_id=args.resume)
        except (ValueError, OSError) as error:
            parser.error(str(error))
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

