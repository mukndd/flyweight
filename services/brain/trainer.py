"""Bounded NumPy CEM; subprocess bridge runs the exact browser combat rules."""
import argparse
import json
import math
import queue
import shutil
import subprocess  # nosec B404 -- bounded fixed authored bridge and read-only local Git; no shell
import sys
import threading
import time
import uuid
from collections import Counter

import numpy as np

from .checkpoints import load_candidate, promote, rollback, save_candidate
from .limits import CHECKPOINTS, MAX_TRAIN_SECONDS, ROOT
from .neural import ACTION_COUNT, TOPOLOGIES, Controller, Graph
from .scenarios import REWARD_VERSION, SCENARIO_SET_VERSION, scenarios
from .storage import atomic_json, digest, read_json, safe_path, validate_npz

EVAL_SEEDS = [10_000_001, 10_000_002, 10_000_003]
DIFFICULTIES = ["easy", "medium", "hard"]
PROFILES = ["standard", "aggressive", "defensive", "counter-focused", "mobile", "mixed"]
COUNTERFACTUALS = ["none", "zero_attack", "zero_relative_velocity", "remove_distance", "invert_direction", "bounded_noise"]

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
    result = subprocess.run(["git", "-c", "safe.directory=" + ROOT.as_posix(), "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=3, check=False)  # nosec B603 B607 -- fixed local read-only Git command
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


def controller_state_summary(controller):
    state = controller.state
    outputs = state[controller.graph.outputs] if controller.topology not in {"rule", "random"} else np.array([], dtype=np.float32)
    return {"ticks": int(controller.ticks), "state_mean_abs": float(np.mean(np.abs(state))) if state.size else 0.0,
            "state_max_abs": float(np.max(np.abs(state))) if state.size else 0.0,
            "output_mean": float(np.mean(outputs)) if outputs.size else 0.0,
            "output_std": float(np.std(outputs)) if outputs.size else 0.0}


def apply_counterfactual(obs, mode, rng=None):
    values = list(obs)
    if mode in (None, "none"):
        return values
    if mode == "zero_attack":
        values[7] = 0
    elif mode == "zero_relative_velocity":
        values[2] = 0
        values[3] = 0
    elif mode == "remove_distance":
        values[0] = 0
        values[1] = 0
        values[6] = 0
    elif mode == "invert_direction":
        values[0] = -values[0]
        values[1] = -values[1]
        values[2] = -values[2]
        values[3] = -values[3]
    elif mode == "bounded_noise":
        if rng is None:
            raise ValueError("Noise counterfactual requires seeded rng")
        values = np.clip(np.asarray(values, dtype=np.float32) + rng.normal(0, 0.035, len(values)), -1, 1).astype(float).tolist()
    else:
        raise ValueError("Unknown counterfactual")
    return values


def trace_digest(actions):
    text = json.dumps(actions, separators=(",", ":"), allow_nan=False)
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stable_json_digest(value):
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def dynamics_state(state):
    return {key: value for key, value in state.items() if key not in {"seed", "rng"}}


def pairwise_trace_similarity(traces):
    if len(traces) < 2:
        return 1.0
    scores = []
    for i in range(len(traces)):
        for j in range(i + 1, len(traces)):
            a, b = traces[i], traces[j]
            total = max(len(a), len(b), 1)
            same = sum(1 for k in range(min(len(a), len(b))) if a[k] == b[k])
            scores.append(same / total)
    return float(np.mean(scores)) if scores else 1.0


def bridge_scenario(scenario):
    if scenario is None:
        return None
    return {"id": scenario["id"], "player": scenario["player"], "opponent": scenario["opponent"]}


def episode(graph, arrays, seed, difficulty, seconds=12, topology="real", ablate=None, bridge=None,
            profile="standard", trace=False, counterfactual="none", scenario=None):
    own = bridge is None
    bridge = bridge or Bridge()
    controller = Controller(graph, seed, topology, arrays)
    noise_rng = np.random.default_rng(seed ^ 0xA5A5) if counterfactual == "bounded_noise" else None
    start = time.perf_counter()
    neural_ms, idle, reactions, signal_started, trace_rows, actions, invalid_unavailable = [], 0, [], None, [], [], 0
    try:
        reset = {"type": "reset", "seed": seed, "difficulty": difficulty, "profile": profile, "limit": seconds * 60}
        payload = bridge_scenario(scenario)
        if payload is not None:
            reset["scenario"] = payload
        result = bridge.request(reset)
        initial_positions = [round(float(f["x"]), 5) for f in result["state"]["fighters"]]
        while result["state"]["winner"] is None:
            raw_obs = list(result["observation"])
            obs = apply_counterfactual(raw_obs, counterfactual, noise_rng)
            if ablate is not None:
                obs[ablate] = 0
            if obs[7] and signal_started is None:
                signal_started = result["state"]["frame"]
            if not obs[7]:
                signal_started = None
            action, tick_ms = controller.act(obs)
            neural_ms.append(tick_ms)
            idle += action == 0
            actions.append(action)
            if not controller.available[action]:
                invalid_unavailable += 1
            if signal_started is not None and action in (4, 7):
                reactions.append((result["state"]["frame"] - signal_started) / 60)
                signal_started = None
            if trace:
                state = result["state"]
                opponent, player = state["fighters"]
                trace_rows.append({"timestamp_ns": time.time_ns(), "frame": int(state["frame"]), "match_seed": seed,
                                   "difficulty": difficulty, "profile": profile, "observation": obs,
                                   "raw_observation": raw_obs, "counterfactual": counterfactual,
                                   "selected_action": action, "available_actions": list(controller.available),
                                   "action_scores": list(controller.last_scores),
                                   "controller_state": controller_state_summary(controller),
                                   "player": {"x": player["x"], "y": player["y"], "vx": player["vx"], "vy": player["vy"]},
                                   "opponent": {"x": opponent["x"], "y": opponent["y"], "vx": opponent["vx"], "vy": opponent["vy"]},
                                   "health": {"player": player["hp"], "opponent": opponent["hp"]},
                                   "damage": {"dealt": 100 - opponent["hp"], "received": 100 - player["hp"]},
                                   "reward": result["rewards"][1]})
            result = bridge.request({"type": "step", "action": action})
        state = result["state"]
        rival, agent = state["fighters"]
        dealt, received = 100 - rival["hp"], 100 - agent["hp"]
        win = state["winner"] == 1
        # Arena control is scored only when damage was dealt; no per-distance movement reward.
        reward = result["rewards"][1]
        return {"seed": seed, "difficulty": difficulty, "profile": profile, "scenario_id": scenario["id"] if scenario else None,
                "scenario_family": scenario["family"] if scenario else None, "scenario_split": scenario["split"] if scenario else None,
                "reward": reward, "win": bool(win),
                "damage_dealt": dealt, "damage_received": received, "blocks": agent["blocks"],
                "damage_differential": dealt - received, "invalid_unavailable_actions": invalid_unavailable,
                "duration": state["frame"] / 60, "reaction_seconds": float(np.mean(reactions)) if reactions else None,
                "reaction_samples": len(reactions), "mean_brain_ms": float(np.mean(neural_ms)),
                "elapsed_seconds": time.perf_counter() - start, "final_hash": result["hash"], "failure": None,
                "ablated_channel": ablate, "counterfactual": counterfactual,
                "final_dynamics_hash": stable_json_digest(dynamics_state(state)),
                "action_trace_hash": trace_digest(actions), "action_trace": actions if trace else None,
                "trace": trace_rows if trace else None, "initial_positions": initial_positions,
                "decision_count": len(actions)}
    finally:
        if own:
            bridge.close()


def summary(rows):
    rewards = np.array([r["reward"] for r in rows], dtype=float)
    sd = float(rewards.std(ddof=1)) if len(rewards) > 1 else 0
    wins = sum(bool(r["win"]) for r in rows)
    n = len(rows)
    p = wins / n if n else 0
    z = 1.96
    denom = 1 + z * z / n if n else 1
    center = (p + z * z / (2 * n)) / denom if n else 0
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denom if n else 0
    actions = [a for row in rows for a in (row.get("action_trace") or [])]
    counts = Counter(actions)
    probs = np.array(list(counts.values()), dtype=float) / max(1, len(actions))
    entropy = float(-(probs * np.log2(probs)).sum()) if probs.size else 0.0
    traces = [r.get("action_trace") or [] for r in rows if r.get("action_trace") is not None]
    damage_dealt = [r.get("damage_dealt", 0) for r in rows]
    damage_received = [r.get("damage_received", 0) for r in rows]
    final_hashes = [r.get("final_hash", "") for r in rows]
    final_dynamics_hashes = [r.get("final_dynamics_hash", r.get("final_hash", "")) for r in rows]
    return {"episodes": len(rows), "wins": wins, "losses": n - wins, "mean_reward": float(rewards.mean()), "median_reward": float(np.median(rewards)),
            "std_reward": sd, "ci95_normal_approx": [float(rewards.mean() - 1.96 * sd / np.sqrt(len(rows))), float(rewards.mean() + 1.96 * sd / np.sqrt(len(rows)))],
            "win_rate": float(p), "win_rate_ci95_wilson": [float(max(0, center - margin)), float(min(1, center + margin))],
            "failures": sum(r["failure"] is not None for r in rows),
            "average_damage": float(np.mean(damage_dealt)),
            "average_damage_dealt": float(np.mean(damage_dealt)),
            "average_damage_received": float(np.mean(damage_received)),
            "average_damage_differential": float(np.mean([r.get("damage_differential", r.get("damage_dealt", 0) - r.get("damage_received", 0)) for r in rows])),
            "average_duration": float(np.mean([r["duration"] for r in rows])),
            "action_distribution": {str(k): int(v) for k, v in sorted(counts.items())},
            "action_entropy_bits": entropy, "unique_final_hashes": len(set(final_hashes)),
            "unique_final_dynamics_hashes": len(set(final_dynamics_hashes)),
            "unique_action_traces": len({r.get("action_trace_hash") for r in rows}),
            "mean_trace_similarity": pairwise_trace_similarity(traces),
            "invalid_unavailable_actions": int(sum(r.get("invalid_unavailable_actions", 0) for r in rows))}


def evaluate(graph, arrays, seconds=12, topology="real", ablate=None):
    bridge = Bridge()
    try:
        rows = [episode(graph, arrays, seed, difficulty, seconds, topology, ablate, bridge)
                for difficulty in DIFFICULTIES for seed in EVAL_SEEDS]
    finally:
        bridge.close()
    return {"suite": "evaluation-v2", **summary(rows), "rows": rows}


def heldout_seeds(start, count):
    if type(count) is not int or not 1 <= count <= 300:
        raise ValueError("Evaluation match bounds")
    return [start + i for i in range(count)]


def group_summary(rows, *keys):
    result = {}
    for row in rows:
        name = "/".join(str(row[key]) for key in keys)
        result.setdefault(name, []).append(row)
    return {key: summary(value) for key, value in sorted(result.items())}


def observation_action_dependence(rows):
    pairs = [(decision["observation"], decision["selected_action"]) for row in rows for decision in (row.get("trace") or [])]
    if not pairs:
        return {"samples": 0, "channels": {}}
    observations = np.asarray([p[0] for p in pairs], dtype=float)
    actions = np.asarray([p[1] for p in pairs], dtype=float)
    action_var = float(np.var(actions))
    channels = {}
    for index in range(observations.shape[1]):
        values = observations[:, index]
        obs_var = float(np.var(values))
        if obs_var <= 1e-12 or action_var <= 1e-12:
            corr = 0.0
        else:
            corr = float(np.corrcoef(values, actions)[0, 1])
            if not np.isfinite(corr):
                corr = 0.0
        channels[str(index)] = {"abs_correlation": abs(corr), "observation_std": float(np.std(values))}
    strongest = sorted(channels.items(), key=lambda item: item[1]["abs_correlation"], reverse=True)[:5]
    return {"samples": len(pairs), "strongest_channels": [{"channel": key, **value} for key, value in strongest],
            "channels": channels}


def action_conditionals(rows):
    groups = {"opponent_attacking": {}, "distance": {}, "relative_direction": {}, "health": {},
              "profile": {}, "family": {}}
    for row in rows:
        profile = row.get("profile", "unknown")
        family = row.get("scenario_family", "unknown")
        for decision in row.get("trace") or []:
            obs = decision["observation"]
            action = decision["selected_action"]
            labels = {
                "opponent_attacking": "yes" if obs[7] > .5 else "no",
                "distance": "close" if obs[6] < .12 else "mid" if obs[6] < .35 else "far",
                "relative_direction": "right" if obs[0] > .03 else "left" if obs[0] < -.03 else "center",
                "health": "advantage" if obs[9] - obs[10] > .2 else "disadvantage" if obs[10] - obs[9] > .2 else "even",
                "profile": profile,
                "family": family,
            }
            for key, label in labels.items():
                groups[key].setdefault(label, Counter())[action] += 1
    result = {}
    for key, values in groups.items():
        result[key] = {label: {str(action): int(count) for action, count in sorted(counter.items())}
                       for label, counter in sorted(values.items())}
    return result


def conditional_action_divergence(conditionals):
    scores = {}
    for key, labels in conditionals.items():
        counters = [Counter({int(k): v for k, v in dist.items()}) for dist in labels.values()]
        if len(counters) < 2:
            scores[key] = 0.0
            continue
        distances = []
        for i in range(len(counters)):
            for j in range(i + 1, len(counters)):
                total_i, total_j = sum(counters[i].values()), sum(counters[j].values())
                if not total_i or not total_j:
                    continue
                actions = set(counters[i]) | set(counters[j])
                distances.append(.5 * sum(abs(counters[i][a] / total_i - counters[j][a] / total_j) for a in actions))
        scores[key] = float(np.mean(distances)) if distances else 0.0
    return scores


def run_matrix(graph, arrays, seeds, difficulties, profiles, seconds, topology="real", trace=False, counterfactual="none"):
    if any(d not in DIFFICULTIES for d in difficulties) or any(p not in PROFILES for p in profiles):
        raise ValueError("Invalid evaluation matrix")
    bridge = Bridge()
    rows = []
    try:
        for profile in profiles:
            for difficulty in difficulties:
                for seed in seeds:
                    rows.append(episode(graph, arrays, seed, difficulty, seconds, topology, bridge=bridge,
                                        profile=profile, trace=trace, counterfactual=counterfactual))
    finally:
        bridge.close()
    return rows


def run_scenarios(graph, arrays, items, seconds, topology="real", trace=False, counterfactual="none"):
    bridge = Bridge()
    rows = []
    try:
        for item in items:
            rows.append(episode(graph, arrays, item["seed"], item["difficulty"], seconds, topology, bridge=bridge,
                                profile=item["profile"], trace=trace, counterfactual=counterfactual, scenario=item))
    finally:
        bridge.close()
    return rows


def robust_fitness(rows):
    rewards = np.asarray([row["reward"] for row in rows], dtype=float)
    by_family = group_summary(rows, "scenario_family")
    family_means = np.asarray([value["mean_reward"] for value in by_family.values()], dtype=float)
    return float(.55 * rewards.mean() + .25 * np.percentile(rewards, 25) + .20 * family_means.min())


def score_rows(rows, objective="robust"):
    rewards = np.asarray([row["reward"] for row in rows], dtype=float)
    family_means = np.asarray([value["mean_reward"] for value in group_summary(rows, "scenario_family").values()], dtype=float)
    if objective == "mean":
        return float(rewards.mean())
    if objective == "light_robust":
        return float(.80 * rewards.mean() + .10 * np.percentile(rewards, 25) + .10 * family_means.min())
    if objective == "robust":
        return robust_fitness(rows)
    raise ValueError("Unknown scenario objective")


def curriculum_items(generation, total_generations, mode):
    train_items = scenarios("train")
    if mode == "full":
        return train_items
    if mode != "staged":
        raise ValueError("Unknown curriculum")
    if generation <= max(2, total_generations // 3):
        return [item for item in train_items if item["difficulty"] == "easy" and item["family"] not in {"health_disadvantage"}]
    if generation <= max(4, 2 * total_generations // 3):
        return [item for item in train_items if item["difficulty"] in {"easy", "medium"} and item["family"] not in {"right_corner"}]
    return train_items


def reward_audit():
    return {"reward_version": REWARD_VERSION, "changed": False,
            "formula": "dealt - 1.1*received + win/loss bonus + 1.5*actual blocks - idle penalty + damage-gated arena control",
            "block_assessment": "Block is not rewarded by button press. The +1.5 term uses fighter.blocks, which increments only when a block/counter actually resolves a hit. The Light-Block-Block-Block loop is indirectly supported because it periodically deals damage and reduces received damage, not because idle blocking alone earns reward.",
            "decision": "Leave reward unchanged for this phase; scenario diversity and robust aggregation should test whether the defensive loop generalizes before changing incentives."}


def promotion_gate_v2(candidate, baseline):
    family = candidate["by_family"]
    catastrophic = [key for key, value in family.items() if value["win_rate"] < .20 or value["average_damage_differential"] < -45]
    summary_stats = candidate["summary"]
    passed = (summary_stats["win_rate"] >= max(.50, baseline["summary"]["win_rate"] + .15)
              and summary_stats["average_damage_differential"] > baseline["summary"]["average_damage_differential"] + 5
              and summary_stats["unique_action_traces"] > 1
              and not catastrophic)
    return {"version": "promotion-gate-v2", "passed": bool(passed),
            "criteria": {"min_heldout_win_rate": .50, "min_improvement_over_baseline": .15,
                         "min_damage_differential_improvement": 5, "min_unique_action_traces": 2,
                         "catastrophic_family": "no family with win_rate < 0.20 or damage differential < -45"},
            "catastrophic_families": catastrophic}


def matrix_similarity(rows):
    if len(rows) < 2:
        return 1.0
    values = np.asarray(rows, dtype=float)
    norms = np.linalg.norm(values, axis=1)
    sims = []
    for i in range(len(values)):
        for j in range(i + 1, len(values)):
            denom = norms[i] * norms[j]
            sims.append(float(np.dot(values[i], values[j]) / denom) if denom > 1e-12 else 1.0)
    return float(np.mean(sims)) if sims else 1.0


def information_flow_diagnostics(graph, arrays, items, seconds=8, max_decisions=18):
    bridge = Bridge()
    records = []
    encoder_norm = float(np.linalg.norm(arrays["encoder"]))
    readout_norm = float(np.linalg.norm(arrays["readout"]))
    bias_norm = float(np.linalg.norm(arrays["bias"]))
    try:
        for item in items:
            controller = Controller(graph, item["seed"], "real", arrays)
            reset = {"type": "reset", "seed": item["seed"], "difficulty": item["difficulty"], "profile": item["profile"],
                     "limit": seconds * 60, "scenario": bridge_scenario(item)}
            result = bridge.request(reset)
            decisions = 0
            while result["state"]["winner"] is None and decisions < max_decisions:
                obs = np.asarray(result["observation"], dtype=np.float32)
                stimulus = controller.encoder @ obs
                recurrent = controller.matrix @ controller.state
                for _ in range(8):
                    drive = controller.matrix @ controller.state
                    drive[controller.graph.inputs] += stimulus
                    controller.state = (.65 * controller.state + .35 * np.tanh(drive)).astype(np.float32)
                features = controller.state[controller.graph.outputs]
                neural_logits = controller.readout @ (features * 8)
                logits = neural_logits + controller.bias
                available = [True] * ACTION_COUNT
                grounded, ready, combo = bool(obs[16] > .5), bool(obs[17] > .5), bool(obs[18] >= .99)
                available[11] = not grounded and ready
                available[13] = combo and ready
                for attack in (5, 6, 9, 10, 12):
                    available[attack] = ready and (grounded or attack not in (9, 12))
                available[3] = grounded
                action = int(np.argmax(np.where(available, logits, -np.inf)))
                saturation = float(np.mean(np.abs(controller.state) > .95))
                records.append({"scenario_id": item["id"], "family": item["family"], "profile": item["profile"],
                                "difficulty": item["difficulty"], "frame": result["state"]["frame"],
                                "observation": obs.astype(float).tolist(), "stimulus_norm": float(np.linalg.norm(stimulus)),
                                "recurrent_norm": float(np.linalg.norm(recurrent)),
                                "state_mean_abs": float(np.mean(np.abs(controller.state))),
                                "state_std": float(np.std(controller.state)), "saturation_fraction": saturation,
                                "output_norm": float(np.linalg.norm(features)), "output_std": float(np.std(features)),
                                "neural_logit_std": float(np.std(neural_logits)), "bias_logit_std": float(np.std(controller.bias)),
                                "logit_std": float(np.std(logits)), "bias_to_neural_norm": float(bias_norm / max(1e-9, np.linalg.norm(neural_logits))),
                                "selected_action": action})
                result = bridge.request({"type": "step", "action": action})
                decisions += 1
    finally:
        bridge.close()
    observations = [record["observation"] for record in records]
    state_metrics = np.asarray([[record["state_mean_abs"], record["state_std"], record["output_norm"],
                                 record["output_std"], record["logit_std"]] for record in records], dtype=float)
    return {"samples": len(records), "encoder_norm": encoder_norm, "readout_norm": readout_norm, "bias_norm": bias_norm,
            "observation_similarity": matrix_similarity(observations),
            "state_metric_similarity": matrix_similarity(state_metrics),
            "stimulus_norm_mean": float(np.mean([r["stimulus_norm"] for r in records])),
            "stimulus_norm_std": float(np.std([r["stimulus_norm"] for r in records])),
            "recurrent_norm_mean": float(np.mean([r["recurrent_norm"] for r in records])),
            "state_mean_abs_mean": float(np.mean([r["state_mean_abs"] for r in records])),
            "state_std_mean": float(np.mean([r["state_std"] for r in records])),
            "saturation_fraction_mean": float(np.mean([r["saturation_fraction"] for r in records])),
            "output_norm_mean": float(np.mean([r["output_norm"] for r in records])),
            "output_std_mean": float(np.mean([r["output_std"] for r in records])),
            "logit_std_mean": float(np.mean([r["logit_std"] for r in records])),
            "bias_to_neural_norm_mean": float(np.mean([r["bias_to_neural_norm"] for r in records])),
            "unique_actions": len({r["selected_action"] for r in records}), "records": records}


def resolve_checkpoint(graph, ident):
    if ident in (None, "", "seed-initialized"):
        return Controller(graph, 783).arrays(), {"id": "seed-initialized", "sha256": "seed-initialized"}
    if ident == "canonical":
        ident = read_json(CHECKPOINTS / "canonical.json")["id"]
    arrays, meta = load_candidate(graph, ident)
    return arrays, meta


def validation_report(graph, checkpoint="canonical", seconds=12, matches=120, trace_limit=24):
    if not 6 <= seconds <= 30 or not 100 <= matches <= 300 or not 3 <= trace_limit <= 60:
        raise ValueError("Validation bounds")
    arrays, meta = resolve_checkpoint(graph, checkpoint)
    baseline = Controller(graph, 783).arrays()
    per_difficulty = max(1, matches // len(DIFFICULTIES))
    standard_seeds = heldout_seeds(20_000_000, per_difficulty)
    trace_seeds = heldout_seeds(30_000_000, trace_limit)
    profile_seeds = heldout_seeds(40_000_000, 10)
    counterfactual_seeds = heldout_seeds(50_000_000, 8)
    trained_rows = run_matrix(graph, arrays, standard_seeds, DIFFICULTIES, ["standard"], seconds, trace=True)
    seed_rows = run_matrix(graph, baseline, standard_seeds, DIFFICULTIES, ["standard"], seconds, trace=True)
    reproduction_rows = run_matrix(graph, arrays, EVAL_SEEDS, DIFFICULTIES, ["standard"], seconds, trace=True)
    trace_rows = run_matrix(graph, arrays, trace_seeds, DIFFICULTIES, ["standard"], seconds, trace=True)
    generalization_rows = run_matrix(graph, arrays, profile_seeds, DIFFICULTIES,
                                     ["aggressive", "defensive", "counter-focused", "mobile", "mixed"], seconds, trace=True)
    counterfactual_results = {}
    for mode in [m for m in COUNTERFACTUALS if m != "none"]:
        rows = run_matrix(graph, arrays, counterfactual_seeds, DIFFICULTIES, ["standard"], seconds, trace=True, counterfactual=mode)
        counterfactual_results[mode] = {"summary": summary(rows), "by_difficulty": group_summary(rows, "difficulty"), "rows": rows}
    all_rows = trained_rows + seed_rows + reproduction_rows + trace_rows + generalization_rows
    seed_effect = {"standard_initial_positions_by_seed": {str(r["seed"]): r["initial_positions"] for r in reproduction_rows},
                   "initial_position_unique_count": len({tuple(r["initial_positions"]) for r in reproduction_rows}),
                   "medium_hard_unique_hashes": {difficulty: len({r["final_hash"] for r in reproduction_rows if r["difficulty"] == difficulty})
                                                  for difficulty in ["medium", "hard"]},
                   "medium_hard_unique_dynamics_hashes": {difficulty: len({r["final_dynamics_hash"] for r in reproduction_rows if r["difficulty"] == difficulty})
                                                          for difficulty in ["medium", "hard"]},
                   "cause": "The seed currently changes only initial spacing in createMatch; standard medium/hard bot decisions are deterministic functions of state. For nearby seeds the first LCG sample can quantize to the same integer offset, and an open-loop action trace can then drive identical dynamics even when the serialized final hash still differs because it includes the seed/rng fields."}
    report = {"version": 1, "suite": "scientific-validation-phase-1", "status": "exploratory",
              "code_commit": code_commit(), "graph_hash": graph.manifest["graph_hash"],
              "checkpoint": meta["id"], "checkpoint_hash": meta["sha256"], "seconds": seconds,
              "evaluation_config": {"matches_requested": matches, "standard_matches_per_difficulty": per_difficulty,
                                    "standard_seeds": standard_seeds, "trace_seeds": trace_seeds,
                                    "profile_seeds": profile_seeds, "counterfactual_seeds": counterfactual_seeds,
                                    "difficulties": DIFFICULTIES, "profiles": PROFILES,
                                    "counterfactuals": COUNTERFACTUALS},
              "reproduction": {"summary": summary(reproduction_rows), "by_difficulty": group_summary(reproduction_rows, "difficulty"), "rows": reproduction_rows},
              "trained_standard": {"summary": summary(trained_rows), "by_difficulty": group_summary(trained_rows, "difficulty"), "rows": trained_rows},
              "seed_initialized_standard": {"summary": summary(seed_rows), "by_difficulty": group_summary(seed_rows, "difficulty"), "rows": seed_rows},
              "trace_analysis": {"summary": summary(trace_rows), "by_difficulty": group_summary(trace_rows, "difficulty"), "rows": trace_rows},
              "generalization": {"summary": summary(generalization_rows), "by_profile_difficulty": group_summary(generalization_rows, "profile", "difficulty"), "rows": generalization_rows},
              "counterfactuals": counterfactual_results, "seed_effect": seed_effect}
    def compact_row(row):
        return {key: value for key, value in row.items() if key != "trace"}

    def compact_section(section, by_key):
        return {"summary": section["summary"], by_key: section[by_key], "rows": [compact_row(row) for row in section["rows"]]}

    compact_counterfactuals = {mode: {"summary": result["summary"], "by_difficulty": result["by_difficulty"],
                                      "rows": [compact_row(row) for row in result["rows"]]}
                               for mode, result in counterfactual_results.items()}
    compact_report = report | {
        "reproduction": compact_section(report["reproduction"], "by_difficulty"),
        "trained_standard": compact_section(report["trained_standard"], "by_difficulty"),
        "seed_initialized_standard": compact_section(report["seed_initialized_standard"], "by_difficulty"),
        "trace_analysis": compact_section(report["trace_analysis"], "by_difficulty"),
        "generalization": compact_section(report["generalization"], "by_profile_difficulty"),
        "counterfactuals": compact_counterfactuals,
    }
    suite = ROOT / "docs" / "results" / ("validation_phase1_" + uuid.uuid4().hex[:12])
    suite.mkdir(parents=False, exist_ok=False)
    compact_report["result_dir"] = str(suite)
    compact_report["trace_decisions_file"] = str(suite / "trace_decisions.jsonl")
    atomic_json(suite / "report.json", compact_report)
    atomic_json(suite / "summary.json", {k: compact_report[k] for k in ("version", "suite", "status", "code_commit", "graph_hash", "checkpoint", "checkpoint_hash", "seconds", "evaluation_config", "seed_effect", "trace_decisions_file")})
    with (suite / "rows.jsonl").open("x", encoding="utf-8") as file:
        for row in all_rows:
            file.write(json.dumps(compact_row(row), allow_nan=False) + "\n")
        for mode, result in counterfactual_results.items():
            for row in result["rows"]:
                file.write(json.dumps(compact_row(row) | {"counterfactual_suite": mode}, allow_nan=False) + "\n")
    with (suite / "trace_decisions.jsonl").open("x", encoding="utf-8") as file:
        for row in all_rows:
            for decision in row.get("trace") or []:
                file.write(json.dumps(decision, allow_nan=False) + "\n")
        for mode, result in counterfactual_results.items():
            for row in result["rows"]:
                for decision in row.get("trace") or []:
                    file.write(json.dumps(decision | {"counterfactual_suite": mode}, allow_nan=False) + "\n")
    atomic_json(suite / "completion.json", {"status": "complete", "result_dir": str(suite), "created_ns": time.time_ns()})
    return compact_report


def checkpoint_hash_for(meta):
    return meta["sha256"] if meta["id"] != "seed-initialized" else "seed-initialized"


def scenario_evaluation(graph, arrays, meta, split="test", seconds=12, counterfactuals=False):
    items = scenarios(split)
    rows = run_scenarios(graph, arrays, items, seconds, trace=True)
    result = {"controller": meta["id"], "checkpoint_hash": checkpoint_hash_for(meta), "split": split,
              "summary": summary(rows), "by_family": group_summary(rows, "scenario_family"),
              "by_scenario": group_summary(rows, "scenario_id"),
              "observation_action_dependence": observation_action_dependence(rows), "rows": rows}
    if counterfactuals:
        result["counterfactuals"] = {}
        for mode in [m for m in COUNTERFACTUALS if m != "none"]:
            cf_rows = run_scenarios(graph, arrays, items[:9], seconds, trace=True, counterfactual=mode)
            result["counterfactuals"][mode] = {"summary": summary(cf_rows),
                                               "observation_action_dependence": observation_action_dependence(cf_rows),
                                               "rows": cf_rows}
    return result


def train_scenarios(graph, seed=2468, generations=2, population=4, seconds=8, emit=print,
                    objective="robust", curriculum="full"):
    if type(seed) is not int or not 0 <= seed <= 999_999 or not 1 <= generations <= 10 or not 4 <= population <= 12 or not 6 <= seconds <= 12:
        raise ValueError("Scenario pilot bounds")
    controller = Controller(graph, seed)
    shapes = {key: value.shape for key, value in controller.arrays().items()}
    sizes = {key: int(np.prod(value)) for key, value in shapes.items()}

    def unpack(vector):
        offset = 0
        result = {}
        for key, size in sizes.items():
            result[key] = vector[offset:offset + size].reshape(shapes[key]).astype(np.float32)
            offset += size
        return result

    run_id = "scenario_" + uuid.uuid4().hex[:12]
    mean = np.concatenate([value.ravel() for value in controller.arrays().values()])
    std = np.full_like(mean, .35)
    rng = np.random.default_rng(seed)
    raw_path = CHECKPOINTS / ("run_" + run_id + ".jsonl")
    CHECKPOINTS.mkdir(parents=True, exist_ok=True)
    best_score, best_arrays, checkpoint = -math.inf, controller.arrays(), ""
    metadata = {"format_version": 3, "run": run_id, "seed": seed, "code_commit": code_commit(),
                "graph_hash": graph.manifest["graph_hash"], "scenario_set_version": SCENARIO_SET_VERSION,
                "reward_version": REWARD_VERSION, "config": {"generations": generations, "population": population,
                                                             "seconds": seconds, "objective": objective,
                                                             "curriculum": curriculum},
                "scenario_ids": [item["id"] for item in scenarios("train")], "method": "CEM adapters only; topology and biological strengths frozen",
                "status": "exploratory-pilot"}
    diagnostics = []
    bridge = Bridge()
    started = time.monotonic()
    try:
        with raw_path.open("x", encoding="utf-8") as raw:
            raw.write(json.dumps(metadata, allow_nan=False) + "\n")
            for generation in range(1, generations + 1):
                if time.monotonic() - started > MAX_TRAIN_SECONDS:
                    break
                items = curriculum_items(generation, generations, curriculum)
                candidates = rng.normal(mean, std, (population, len(mean))).astype(np.float32)
                candidates[0] = mean
                scores, rows_by_member, member_stats = [], [], []
                for member, candidate in enumerate(candidates):
                    arrays = unpack(candidate)
                    rows = [episode(graph, arrays, item["seed"], item["difficulty"], seconds, bridge=bridge,
                                    profile=item["profile"], scenario=item)
                            for item in items]
                    stats = summary(rows)
                    by_family = group_summary(rows, "scenario_family")
                    score = score_rows(rows, objective)
                    raw.write(json.dumps({"generation": generation, "member": member, "robust_fitness": score,
                                          "summary": stats, "by_family": by_family}, allow_nan=False) + "\n")
                    raw.flush()
                    scores.append(score)
                    rows_by_member.append(rows)
                    member_stats.append({"member": member, "score": float(score), "mean_reward": stats["mean_reward"],
                                         "p25_reward": float(np.percentile([row["reward"] for row in rows], 25)),
                                         "worst_family_reward": min(value["mean_reward"] for value in by_family.values()),
                                         "win_rate": stats["win_rate"]})
                elite = np.argsort(scores)[-max(2, population // 3):]
                old_mean = mean.copy()
                mean = candidates[elite].mean(axis=0)
                std = np.maximum(.045, candidates[elite].std(axis=0))
                best_member = int(np.argmax(scores))
                if scores[best_member] > best_score:
                    best_score = float(scores[best_member])
                    best_arrays = unpack(candidates[best_member])
                checkpoint = save_candidate(graph, best_arrays, {"seed": seed, "generation": generation, "reward": best_score})
                save_resume_state(run_id, graph, mean, std, generation, metadata["config"], root=CHECKPOINTS)
                generation_record = {"generation": generation, "scenario_count": len(items),
                                     "scenario_ids": [item["id"] for item in items],
                                     "fitness_min": float(np.min(scores)), "fitness_p25": float(np.percentile(scores, 25)),
                                     "fitness_mean": float(np.mean(scores)), "fitness_max": float(np.max(scores)),
                                     "elite_mean": float(np.mean([scores[i] for i in elite])),
                                     "sigma_mean": float(np.mean(std)), "sigma_max": float(np.max(std)),
                                     "parameter_mean_change_norm": float(np.linalg.norm(mean - old_mean)),
                                     "best_member": best_member, "best_ever_score": best_score,
                                     "final_generation_best_score": float(scores[best_member]),
                                     "members": member_stats,
                                     "best_family_scores": group_summary(rows_by_member[best_member], "scenario_family")}
                diagnostics.append(generation_record)
                progress = {"v": 2, "type": "train_progress", "status": "scenario_pilot", "run": run_id,
                            "generation": generation, "generations": generations, "reward": best_score,
                            "win_rate": summary(rows_by_member[best_member])["win_rate"], "checkpoint": checkpoint, "seed": seed}
                emit(json.dumps(progress, allow_nan=False))
            raw.write(json.dumps({"checkpoint": checkpoint, "checkpoint_hash": digest(CHECKPOINTS / (checkpoint + ".npz")),
                                  "best_robust_fitness": best_score, "diagnostics": diagnostics}, allow_nan=False) + "\n")
    finally:
        bridge.close()
    return checkpoint, run_id, best_score, diagnostics


def compact_row(row):
    return {key: value for key, value in row.items() if key != "trace"}


def compact_eval(result):
    compact = {key: value for key, value in result.items() if key not in {"rows", "counterfactuals"}}
    compact["rows"] = [compact_row(row) for row in result["rows"]]
    if "counterfactuals" in result:
        compact["counterfactuals"] = {mode: {key: value for key, value in cf.items() if key != "rows"} | {"rows": [compact_row(row) for row in cf["rows"]]}
                                      for mode, cf in result["counterfactuals"].items()}
    return compact


def write_phase2_results(report, trace_sources):
    suite = ROOT / "docs" / "results" / ("scenario_phase2_" + uuid.uuid4().hex[:12])
    suite.mkdir(parents=False, exist_ok=False)
    report["result_dir"] = str(suite)
    report["trace_decisions_file"] = str(suite / "trace_decisions.jsonl")
    atomic_json(suite / "report.json", report)
    atomic_json(suite / "scenario_library.json", {"version": SCENARIO_SET_VERSION, "scenarios": scenarios()})
    atomic_json(suite / "summary.json", {key: report[key] for key in ("version", "suite", "status", "code_commit",
                                                                       "graph_hash", "scenario_set_version",
                                                                       "reward_audit", "promotion_gate_v2",
                                                                       "result_dir", "trace_decisions_file")})
    with (suite / "rows.jsonl").open("x", encoding="utf-8") as file:
        for label, result in trace_sources:
            for row in result["rows"]:
                file.write(json.dumps(compact_row(row) | {"evaluation": label}, allow_nan=False) + "\n")
    with (suite / "trace_decisions.jsonl").open("x", encoding="utf-8") as file:
        for label, result in trace_sources:
            for row in result["rows"]:
                for decision in row.get("trace") or []:
                    file.write(json.dumps(decision | {"evaluation": label, "scenario_id": row["scenario_id"],
                                                      "scenario_family": row["scenario_family"]}, allow_nan=False) + "\n")
            for mode, cf in result.get("counterfactuals", {}).items():
                for row in cf["rows"]:
                    for decision in row.get("trace") or []:
                        file.write(json.dumps(decision | {"evaluation": label, "counterfactual_suite": mode,
                                                          "scenario_id": row["scenario_id"],
                                                          "scenario_family": row["scenario_family"]}, allow_nan=False) + "\n")
    atomic_json(suite / "completion.json", {"status": "complete", "result_dir": str(suite), "created_ns": time.time_ns()})
    return suite


def ranking_correlation(a, b):
    if len(a) < 2:
        return 1.0
    ra = np.argsort(np.argsort(a))
    rb = np.argsort(np.argsort(b))
    return float(np.corrcoef(ra, rb)[0, 1])


def fitness_aggregation_audit(graph, seed=1357, population=8, seconds=8):
    base = Controller(graph, seed)
    shapes = {key: value.shape for key, value in base.arrays().items()}
    sizes = {key: int(np.prod(value)) for key, value in shapes.items()}

    def unpack(vector):
        offset = 0
        result = {}
        for key, size in sizes.items():
            result[key] = vector[offset:offset + size].reshape(shapes[key]).astype(np.float32)
            offset += size
        return result

    mean = np.concatenate([value.ravel() for value in base.arrays().values()])
    rng = np.random.default_rng(seed)
    candidates = rng.normal(mean, .35, (population, len(mean))).astype(np.float32)
    candidates[0] = mean
    items = curriculum_items(1, 5, "staged")
    rows = []
    bridge = Bridge()
    try:
        for member, candidate in enumerate(candidates):
            arrays = unpack(candidate)
            member_rows = [episode(graph, arrays, item["seed"], item["difficulty"], seconds, bridge=bridge,
                                   profile=item["profile"], scenario=item)
                           for item in items]
            scores = {objective: score_rows(member_rows, objective) for objective in ("mean", "light_robust", "robust")}
            rows.append({"member": member, "summary": summary(member_rows), "scores": scores,
                         "by_family": group_summary(member_rows, "scenario_family")})
    finally:
        bridge.close()
    vectors = {objective: [row["scores"][objective] for row in rows] for objective in ("mean", "light_robust", "robust")}
    return {"population": population, "seconds": seconds, "scenario_ids": [item["id"] for item in items],
            "rank_correlations": {"mean_vs_light_robust": ranking_correlation(vectors["mean"], vectors["light_robust"]),
                                  "mean_vs_robust": ranking_correlation(vectors["mean"], vectors["robust"]),
                                  "light_robust_vs_robust": ranking_correlation(vectors["light_robust"], vectors["robust"])},
            "score_spreads": {objective: {"min": float(np.min(values)), "mean": float(np.mean(values)),
                                          "max": float(np.max(values)), "std": float(np.std(values))}
                              for objective, values in vectors.items()},
            "rows": rows}


def enrich_responsiveness(result):
    conditionals = action_conditionals(result["rows"])
    result["conditional_actions"] = conditionals
    result["conditional_action_divergence"] = conditional_action_divergence(conditionals)
    return result


def scenario_phase3_report(graph, checkpoint="canonical", seconds=8):
    old_arrays, old_meta = resolve_checkpoint(graph, checkpoint)
    baseline_arrays, baseline_meta = resolve_checkpoint(graph, "seed-initialized")
    diagnostic_items = scenarios("validation") + scenarios("test")[:6]
    info_old = information_flow_diagnostics(graph, old_arrays, diagnostic_items, seconds=seconds)
    info_baseline = information_flow_diagnostics(graph, baseline_arrays, diagnostic_items, seconds=seconds)
    aggregation = fitness_aggregation_audit(graph, seconds=seconds)
    configs = [
        {"name": "mean_full_pop8_gen5", "seed": 3101, "population": 8, "generations": 5,
         "objective": "mean", "curriculum": "full"},
        {"name": "light_staged_pop8_gen5", "seed": 3102, "population": 8, "generations": 5,
         "objective": "light_robust", "curriculum": "staged"},
    ]
    experiments = []
    best = None
    baseline_test = enrich_responsiveness(scenario_evaluation(graph, baseline_arrays, baseline_meta, "test", seconds))
    old_test = enrich_responsiveness(scenario_evaluation(graph, old_arrays, old_meta, "test", seconds, counterfactuals=True))
    for config in configs:
        checkpoint_id, run_id, best_score, diagnostics = train_scenarios(
            graph, seed=config["seed"], generations=config["generations"], population=config["population"],
            seconds=seconds, objective=config["objective"], curriculum=config["curriculum"])
        arrays, meta = resolve_checkpoint(graph, checkpoint_id)
        validation = enrich_responsiveness(scenario_evaluation(graph, arrays, meta, "validation", seconds, counterfactuals=True))
        test = enrich_responsiveness(scenario_evaluation(graph, arrays, meta, "test", seconds, counterfactuals=True))
        experiment = {"config": config, "checkpoint": checkpoint_id, "run": run_id,
                      "best_robust_fitness": best_score, "cem_diagnostics": diagnostics,
                      "validation": compact_eval(validation), "test": compact_eval(test)}
        experiments.append(experiment)
        value = validation["summary"]["win_rate"] * 100 + validation["summary"]["average_damage_differential"]
        if best is None or value > best["selection_score"]:
            best = {"selection_score": value, "checkpoint": checkpoint_id, "run": run_id,
                    "validation": validation, "test": test, "config": config}
    best_arrays, best_meta = resolve_checkpoint(graph, best["checkpoint"])
    train_eval = enrich_responsiveness(scenario_evaluation(graph, best_arrays, best_meta, "train", seconds))
    gate = promotion_gate_v2(best["test"], baseline_test)
    recommendation = "ADD PPO AS SECOND TRAINER"
    if info_old["stimulus_norm_std"] < 1e-6 or info_old["output_std_mean"] < 1e-6:
        recommendation = "ARCHITECTURE PROBLEM"
    elif best["test"]["summary"]["win_rate"] > old_test["summary"]["win_rate"] and best["test"]["summary"]["average_damage_differential"] > old_test["summary"]["average_damage_differential"]:
        recommendation = "KEEP CEM"
    elif max(exp["validation"]["summary"]["win_rate"] for exp in experiments) > baseline_test["summary"]["win_rate"]:
        recommendation = "CEM NEEDS MORE SCALE"
    report = {"version": 1, "suite": "scientific-validation-phase-3-diagnostics", "status": "exploratory",
              "code_commit": code_commit(), "graph_hash": graph.manifest["graph_hash"],
              "scenario_set_version": SCENARIO_SET_VERSION, "reward_version": REWARD_VERSION,
              "information_flow": {"old_checkpoint": {k: v for k, v in info_old.items() if k != "records"},
                                   "seed_initialized": {k: v for k, v in info_baseline.items() if k != "records"}},
              "neural_dynamics": {"old_checkpoint": {key: info_old[key] for key in ("state_mean_abs_mean", "state_std_mean", "saturation_fraction_mean", "state_metric_similarity", "recurrent_norm_mean")},
                                  "seed_initialized": {key: info_baseline[key] for key in ("state_mean_abs_mean", "state_std_mean", "saturation_fraction_mean", "state_metric_similarity", "recurrent_norm_mean")}},
              "adapter_diagnostics": {"old_checkpoint": {key: info_old[key] for key in ("encoder_norm", "readout_norm", "bias_norm", "bias_to_neural_norm_mean", "logit_std_mean")},
                                      "seed_initialized": {key: info_baseline[key] for key in ("encoder_norm", "readout_norm", "bias_norm", "bias_to_neural_norm_mean", "logit_std_mean")}},
              "fitness_aggregation_audit": aggregation,
              "old_checkpoint_test": compact_eval(old_test), "baseline_test": compact_eval(baseline_test),
              "bounded_search": experiments, "best_responsive_controller": {"checkpoint": best["checkpoint"],
                                                                            "run": best["run"],
                                                                            "config": best["config"],
                                                                            "train": compact_eval(train_eval),
                                                                            "validation": compact_eval(best["validation"]),
                                                                            "test": compact_eval(best["test"])},
              "promotion_gate_v2": gate, "trainer_decision": recommendation,
              "trainer_interface_plan": {"common_contract": ["scenario_batch", "frozen graph/controller factory",
                                                             "adapter checkpoint arrays", "evaluation rows",
                                                             "promotion gate evidence"],
                                         "future_trainers": ["CEM over adapter vectors", "PPO over adapter/readout policy parameters",
                                                             "genetic algorithm over adapter vectors", "MAP-Elites over adapter vectors"],
                                         "excluded_primary": "NEAT should not be the primary FlyWire trainer because it evolves topology; keep it to artificial-control or adapter-only experiments."}}
    suite = ROOT / "docs" / "results" / ("phase3_diagnostics_" + uuid.uuid4().hex[:12])
    suite.mkdir(parents=False, exist_ok=False)
    report["result_dir"] = str(suite)
    atomic_json(suite / "report.json", report)
    atomic_json(suite / "summary.json", {key: report[key] for key in ("version", "suite", "status", "code_commit",
                                                                       "graph_hash", "scenario_set_version",
                                                                       "reward_version", "trainer_decision",
                                                                       "promotion_gate_v2", "result_dir")})
    atomic_json(suite / "scenario_library.json", {"version": SCENARIO_SET_VERSION, "scenarios": scenarios()})
    with (suite / "diagnostic_records.jsonl").open("x", encoding="utf-8") as file:
        for label, info in (("old_checkpoint", info_old), ("seed_initialized", info_baseline)):
            for record in info["records"]:
                file.write(json.dumps(record | {"controller": label}, allow_nan=False) + "\n")
    with (suite / "rows.jsonl").open("x", encoding="utf-8") as file:
        for label, result in (("old_checkpoint_test", old_test), ("baseline_test", baseline_test),
                              ("best_train", train_eval), ("best_validation", best["validation"]),
                              ("best_test", best["test"])):
            for row in result["rows"]:
                file.write(json.dumps(compact_row(row) | {"evaluation": label}, allow_nan=False) + "\n")
    atomic_json(suite / "completion.json", {"status": "complete", "result_dir": str(suite), "created_ns": time.time_ns()})
    return report


def scenario_phase2_report(graph, checkpoint="canonical", seconds=8, pilot=False):
    arrays, meta = resolve_checkpoint(graph, checkpoint)
    baseline_arrays, baseline_meta = resolve_checkpoint(graph, "seed-initialized")
    old_test = scenario_evaluation(graph, arrays, meta, "test", seconds, counterfactuals=True)
    baseline_test = scenario_evaluation(graph, baseline_arrays, baseline_meta, "test", seconds, counterfactuals=False)
    pilot_result = None
    pilot_test = None
    if pilot:
        checkpoint_id, run_id, best_score, diagnostics = train_scenarios(graph, seed=2468, generations=2, population=4, seconds=seconds)
        pilot_arrays, pilot_meta = resolve_checkpoint(graph, checkpoint_id)
        pilot_validation = scenario_evaluation(graph, pilot_arrays, pilot_meta, "validation", seconds, counterfactuals=True)
        pilot_test = scenario_evaluation(graph, pilot_arrays, pilot_meta, "test", seconds, counterfactuals=True)
        pilot_result = {"checkpoint": checkpoint_id, "run": run_id, "best_robust_fitness": best_score,
                        "cem_diagnostics": diagnostics,
                        "validation": compact_eval(pilot_validation), "test": compact_eval(pilot_test)}
    gate_subject = pilot_test if pilot_test is not None else old_test
    gate = promotion_gate_v2(gate_subject, baseline_test)
    report = {"version": 1, "suite": "scientific-validation-phase-2-scenarios", "status": "exploratory",
              "code_commit": code_commit(), "graph_hash": graph.manifest["graph_hash"],
              "scenario_set_version": SCENARIO_SET_VERSION, "reward_version": REWARD_VERSION,
              "scenario_counts": {split: len(scenarios(split)) for split in ("train", "validation", "test")},
              "scenario_families": sorted({item["family"] for item in scenarios()}),
              "old_checkpoint_test": compact_eval(old_test), "baseline_test": compact_eval(baseline_test),
              "reward_audit": reward_audit(), "pilot_training": pilot_result,
              "promotion_gate_v2": gate}
    trace_sources = [("old_checkpoint_test", old_test), ("baseline_test", baseline_test)]
    if pilot_test is not None:
        trace_sources.append(("pilot_test", pilot_test))
    suite = write_phase2_results(report, trace_sources)
    report["result_dir"] = str(suite)
    return report


def train(graph, seed=783, generations=2, population=6, seconds=12, emit=print, cancelled=lambda: False,
          difficulties=None, elite_fraction=1 / 3, sigma_init=.4, sigma_floor=.04, checkpoint_every=1, run_id=None,
          topology="real"):
    if type(seed) is not int or not 0 <= seed <= 999_999 or not 1 <= generations <= 20 or not 4 <= population <= 12 or not 6 <= seconds <= 30:
        raise ValueError("Training hyperparameter bounds")
    difficulties = list(difficulties) if difficulties is not None else list(DIFFICULTIES)
    if not difficulties or any(d not in DIFFICULTIES for d in difficulties) or len(difficulties) != len(set(difficulties)):
        raise ValueError("Invalid training difficulty set")
    if topology not in {"real", "degree_randomized", "weight_shuffled", "ordinary"}:
        raise ValueError("Topology condition is not trainable by CEM adapters")
    if not 0 < elite_fraction <= 1 or not 0 < sigma_floor <= sigma_init or not np.isfinite(sigma_init) or not 1 <= checkpoint_every <= generations:
        raise ValueError("Invalid search hyperparameters")
    CHECKPOINTS.mkdir(parents=True, exist_ok=True)
    controller = Controller(graph, seed, topology=topology)
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
    best_checkpoint = ""
    best_generation = start_generation
    best_training_fitness = float("-inf")
    best_training_win_rate = 0.0
    bridge = Bridge()
    try:
        with raw_path.open("a" if resumed_from else "x", encoding="utf-8") as raw:
            raw.write(json.dumps(metadata) + "\n")
            for generation in range(start_generation + 1, start_generation + generations + 1):
                if cancelled() or time.monotonic() - started > MAX_TRAIN_SECONDS:
                    emit(json.dumps({"v": 2, "type": "train_progress", "generation": generation-1, "generations": start_generation + generations,
                                     "reward": best_training_fitness if np.isfinite(best_training_fitness) else 0,
                                     "win_rate": 0, "checkpoint": best_checkpoint, "seed": seed, "status": "cancelled",
                                     "run": run_id, "trainer": "CEMTrainer", "population": population,
                                     "scenario_set": SCENARIO_SET_VERSION, "reward_version": REWARD_VERSION,
                                     "best_training_fitness": best_training_fitness if np.isfinite(best_training_fitness) else None,
                                     "best_generation": best_generation, "best_checkpoint": best_checkpoint}))
                    return best_checkpoint
                candidates = rng.normal(mean, std, (population, len(mean))).astype(np.float32)
                candidates[0] = mean
                results, rows_by_member = [], []
                for member, candidate in enumerate(candidates):
                    if cancelled():
                        emit(json.dumps({"v": 2, "type": "train_progress", "generation": generation-1, "generations": start_generation + generations,
                                         "reward": best_training_fitness if np.isfinite(best_training_fitness) else 0,
                                         "win_rate": 0, "checkpoint": best_checkpoint, "seed": seed, "status": "cancelled",
                                         "run": run_id, "trainer": "CEMTrainer", "population": population,
                                         "scenario_set": SCENARIO_SET_VERSION, "reward_version": REWARD_VERSION,
                                         "best_training_fitness": best_training_fitness if np.isfinite(best_training_fitness) else None,
                                         "best_generation": best_generation, "best_checkpoint": best_checkpoint}))
                        return best_checkpoint
                    rows = [episode(graph, unpack(candidate), seed + 999 + generation, difficulty, seconds, topology=topology, bridge=bridge)
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
                final_generation_best = float(max(results))
                generation_arrays = unpack(candidates[best_member])
                training_win_rate = float(np.mean([r["win"] for r in rows_by_member[best_member]]))
                if final_generation_best > best_training_fitness:
                    best_training_fitness = final_generation_best
                    best_generation = generation
                    best_training_win_rate = training_win_rate
                    best_arrays = generation_arrays
                    best_checkpoint = save_candidate(graph, best_arrays, {"seed": seed, "generation": generation, "reward": best_training_fitness, "topology": topology})
                    checkpoint = best_checkpoint
                elif generation % checkpoint_every == 0 or generation == start_generation + generations:
                    checkpoint = save_candidate(graph, generation_arrays, {"seed": seed, "generation": generation, "reward": final_generation_best, "topology": topology})
                if generation % checkpoint_every == 0 or generation == start_generation + generations:
                    save_resume_state(run_id, graph, mean, std, generation, config, root=CHECKPOINTS)
                emit(json.dumps({"v": 2, "type": "train_progress", "generation": generation, "generations": start_generation + generations,
                                 "reward": final_generation_best, "win_rate": 0, "training_win_rate": training_win_rate,
                                 "checkpoint": checkpoint, "seed": seed, "status": "training", "run": run_id,
                                 "trainer": "CEMTrainer", "population": population,
                                 "scenario_set": SCENARIO_SET_VERSION, "reward_version": REWARD_VERSION,
                                 "best_training_fitness": best_training_fitness,
                                 "best_generation": best_generation, "best_checkpoint": best_checkpoint,
                                 "best_training_win_rate": best_training_win_rate,
                                 "final_generation_best": final_generation_best,
                                 "final_generation_win_rate": training_win_rate}))
            report = evaluate(graph, best_arrays, seconds, topology=topology)
            checkpoint = best_checkpoint
            raw.write(json.dumps({"checkpoint": checkpoint, "checkpoint_hash": digest(CHECKPOINTS / (checkpoint + ".npz")),
                                  "best_generation": best_generation, "best_training_fitness": best_training_fitness,
                                  "evaluation": report}) + "\n")
            emit(json.dumps({"v": 2, "type": "train_progress", "generation": start_generation + generations, "generations": start_generation + generations,
                             "reward": report["mean_reward"], "win_rate": report["win_rate"], "checkpoint": checkpoint,
                             "seed": seed, "status": "evaluated candidate", "run": run_id,
                             "trainer": "CEMTrainer", "population": population,
                             "scenario_set": SCENARIO_SET_VERSION, "reward_version": REWARD_VERSION,
                             "evaluation_suite": report["suite"], "candidate_evaluation_reward": report["mean_reward"],
                             "held_out_win_rate": report["win_rate"], "held_out_episodes": report["episodes"],
                             "best_training_fitness": best_training_fitness,
                             "best_generation": best_generation, "best_checkpoint": best_checkpoint,
                             "best_training_win_rate": best_training_win_rate}))
    except (ValueError, OSError, RuntimeError, TimeoutError) as error:
        with raw_path.open("a", encoding="utf-8") as raw:
            raw.write(json.dumps({"status": "failed", "failure": type(error).__name__}) + "\n")
        raise
    finally:
        bridge.close()
    return checkpoint


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["train", "evaluate", "promote", "rollback", "controls", "validate", "scenario-phase2", "phase3"])
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
    parser.add_argument("--topology", default="real", choices=["real", "degree_randomized", "weight_shuffled", "ordinary"], help="Train adapters against one approved graph condition.")
    parser.add_argument("--matches", type=int, default=120, help="Validation-only total standard-profile matches; explicit research command only.")
    parser.add_argument("--trace-limit", type=int, default=24, dest="trace_limit", help="Validation-only trace sample count per difficulty.")
    parser.add_argument("--pilot", action="store_true", help="Scenario Phase 2 only: run the small CEM pilot after baseline evaluation.")
    args = parser.parse_args()
    train_only = ("generations", "population", "difficulties", "elite_fraction", "sigma_init", "sigma_floor", "checkpoint_every", "preset", "resume")
    if args.command != "train" and (any(getattr(args, name) is not None for name in train_only) or args.topology != "real"):
        parser.error("--preset/--generations/--population/--seconds/--difficulties/--elite-fraction/--sigma-init/--sigma-floor/--checkpoint-every/--resume/--topology only apply to the train command")
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
    if args.command != "validate" and (args.matches != 120 or args.trace_limit != 24):
        parser.error("--matches/--trace-limit only apply to the validate command")
    if args.command != "scenario-phase2" and args.pilot:
        parser.error("--pilot only applies to scenario-phase2")
    if not 6 <= seconds <= 30 or not 0 <= args.seed <= 999_999:
        parser.error("Bounded seconds/seed required")
    graph = Graph(synthetic=not (ROOT / "data/processed/flywire.json").exists())
    arrays = resolve_checkpoint(graph, args.checkpoint)[0] if args.checkpoint else Controller(graph, args.seed).arrays()
    if args.command == "train":
        try:
            train(graph, args.seed, generations, population, seconds, emit=lambda line: print(line, flush=True),
                  cancelled=lambda: bool(args.cancel_id and safe_path(ROOT / ".runtime", args.cancel_id).exists()),
                  difficulties=difficulties, elite_fraction=elite_fraction, sigma_init=sigma_init,
                  sigma_floor=sigma_floor, checkpoint_every=checkpoint_every, run_id=args.resume, topology=args.topology)
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
    elif args.command == "validate":
        try:
            result = validation_report(graph, args.checkpoint or "canonical", seconds=args.seconds, matches=args.matches,
                                       trace_limit=args.trace_limit)
        except (ValueError, OSError) as error:
            parser.error(str(error))
        print(json.dumps({k: v for k, v in result.items() if k not in {"reproduction", "trained_standard", "seed_initialized_standard", "trace_analysis", "generalization", "counterfactuals"}}, indent=2))
    elif args.command == "scenario-phase2":
        try:
            result = scenario_phase2_report(graph, args.checkpoint or "canonical", seconds=args.seconds, pilot=args.pilot)
        except (ValueError, OSError) as error:
            parser.error(str(error))
        print(json.dumps({k: v for k, v in result.items() if k not in {"old_checkpoint_test", "baseline_test", "pilot_training"}}, indent=2))
    elif args.command == "phase3":
        try:
            result = scenario_phase3_report(graph, args.checkpoint or "canonical", seconds=args.seconds)
        except (ValueError, OSError) as error:
            parser.error(str(error))
        print(json.dumps({k: v for k, v in result.items() if k not in {"old_checkpoint_test", "baseline_test", "bounded_search", "best_responsive_controller", "fitness_aggregation_audit"}}, indent=2))
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

