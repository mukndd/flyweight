"""Bounded multi-seed topology-control evidence batch."""
from __future__ import annotations

import argparse
import json
import time

from .checkpoints import load_candidate
from .limits import CHECKPOINTS
from .neural import Controller, Graph
from .production import load_compute_limits, load_production_env, structured_log
from .research_registry import PROJECT_EPOCH, ResearchRegistry
from .scenarios import REWARD_VERSION, SCENARIO_SET_VERSION, scenarios
from .topology_experiments import CONDITIONS, condition_records, fair_config, validate_condition_records
from .trainer import run_scenarios, summary
from .trainer_interface import CEMTrainer, TrainerConfig

TOPOLOGY_BATCH_VERSION = "topology-control-batch-v1"
TRAINABLE_CONDITIONS = (
    "REAL_CONNECTOME",
    "DEGREE_PRESERVING_RANDOMIZED",
    "WEIGHT_SHUFFLED",
    "MATCHED_RANDOM_RECURRENT",
)
DESCRIPTIVE_BASELINES = ("RULE_BASELINE", "RANDOM_ACTION_BASELINE")


def parse_seeds(raw):
    seeds = [int(part) for part in raw.split(",") if part]
    if not 2 <= len(seeds) <= 6 or len(seeds) != len(set(seeds)) or any(not 0 <= seed <= 999_999 for seed in seeds):
        raise ValueError("Topology batch requires 2-6 unique bounded seeds")
    return seeds


def heldout_subset(count):
    if not 2 <= count <= 18:
        raise ValueError("Held-out match count must use 2-18 scenarios")
    return scenarios("test")[:count]


def final_training_message(messages):
    parsed = [json.loads(line) for line in messages if json.loads(line).get("type") == "train_progress"]
    return parsed[-1] if parsed else {}


def record_batch_condition(registry, graph, exp_id, condition, topology, seed, config, heldout):
    run_id = registry.create_run(exp_id, "CEMTrainer", seed, config)
    messages = []
    started = time.perf_counter()
    process_started = time.process_time()
    try:
        trainer_config = TrainerConfig(
            seed=seed,
            generations=config["generations"],
            population=config["population"],
            seconds=config["seconds"],
            difficulties=tuple(config["difficulties"]),
            topology=topology,
        )
        cem = CEMTrainer(graph, trainer_config, emit=messages.append)
        cem.setup()
        checkpoint = cem.train_step()
        arrays, checkpoint_meta = load_candidate(graph, checkpoint)
        rows = run_scenarios(graph, arrays, heldout, config["seconds"], topology=topology)
        metrics = summary(rows) | {
            "status": "held_out_evaluated",
            "topology_batch_version": TOPOLOGY_BATCH_VERSION,
            "condition": condition,
            "topology": topology,
            "seed": seed,
            "held_out_scenarios": [item["id"] for item in heldout],
            "training_budget": {
                "generations": config["generations"],
                "population": config["population"],
                "seconds": config["seconds"],
            },
            "compute": {
                "wall_seconds": time.perf_counter() - started,
                "cpu_seconds": time.process_time() - process_started,
            },
        }
        final_training = final_training_message(messages)
        candidate_id = registry.record_candidate(
            candidate_id=checkpoint,
            parent_champion_id=None,
            run_id=run_id,
            trainer="CEMTrainer",
            trainer_version=CEMTrainer.version,
            training_seed=seed,
            graph_condition=condition,
            graph_hash=graph.manifest["graph_hash"],
            scenario_version=SCENARIO_SET_VERSION,
            reward_version=REWARD_VERSION,
            generation=int(checkpoint_meta["generation"]),
            training_metrics={
                "fitness": final_training.get("best_training_fitness", checkpoint_meta["reward"]),
                "best_generation": final_training.get("best_generation", checkpoint_meta["generation"]),
                "latest_generation": final_training.get("generation"),
                "topology_batch_version": TOPOLOGY_BATCH_VERSION,
            },
            validation_metrics=metrics,
            checkpoint_hash=checkpoint_meta["sha256"],
            checkpoint_id=checkpoint,
            status="validated",
            reason={"selection": "evidence_batch_no_promotion"},
        )
        registry.record_checkpoint(
            checkpoint,
            candidate_id,
            checkpoint_meta["sha256"],
            (CHECKPOINTS / (checkpoint + ".npz")).stat().st_size,
            "local:checkpoints/" + checkpoint + ".npz",
        )
        registry.record_evaluation(
            candidate_id,
            None,
            f"{TOPOLOGY_BATCH_VERSION}:{condition}",
            SCENARIO_SET_VERSION,
            REWARD_VERSION,
            metrics,
            rows,
        )
        registry.finish_run(run_id, "complete")
        return {"condition": condition, "seed": seed, "checkpoint": checkpoint, "metrics": metrics}
    except Exception:
        registry.finish_run(run_id, "failed")
        raise


def record_baseline(registry, graph, condition, topology, seed, heldout, seconds):
    started = time.perf_counter()
    process_started = time.process_time()
    arrays = Controller(graph, seed, topology=topology).arrays()
    rows = run_scenarios(graph, arrays, heldout, seconds, topology=topology)
    metrics = summary(rows) | {
        "status": "descriptive_baseline",
        "topology_batch_version": TOPOLOGY_BATCH_VERSION,
        "condition": condition,
        "topology": topology,
        "seed": seed,
        "held_out_scenarios": [item["id"] for item in heldout],
        "training_budget": None,
        "compute": {
            "wall_seconds": time.perf_counter() - started,
            "cpu_seconds": time.process_time() - process_started,
        },
    }
    registry.record_evaluation(
        None,
        None,
        f"{TOPOLOGY_BATCH_VERSION}:{condition}",
        SCENARIO_SET_VERSION,
        REWARD_VERSION,
        metrics,
        rows,
    )
    return {"condition": condition, "seed": seed, "checkpoint": None, "metrics": metrics}


def aggregate(results):
    grouped = {}
    for result in results:
        metrics = result["metrics"]
        grouped.setdefault(result["condition"], []).append(metrics)
    output = {}
    for condition, values in sorted(grouped.items()):
        output[condition] = {
            "runs": len(values),
            "status": values[0]["status"],
            "mean_win_rate": sum(item["win_rate"] for item in values) / len(values),
            "mean_reward": sum(item["mean_reward"] for item in values) / len(values),
            "mean_cpu_seconds": sum(item["compute"]["cpu_seconds"] for item in values) / len(values),
            "seeds": [item["seed"] for item in values],
        }
    return output


def run_batch(args):
    if args.production:
        env = load_production_env()
        if env.role != "RESEARCH_WORKER":
            raise ValueError("Topology batch requires FLYWEIGHT_SERVICE_ROLE=RESEARCH_WORKER")
        if args.synthetic:
            raise ValueError("Production topology batch requires real FlyWire graph")
    graph = Graph(synthetic=bool(args.synthetic))
    limits = load_compute_limits()
    seeds = parse_seeds(args.seeds)
    heldout = heldout_subset(args.heldout_matches)
    base_config = fair_config(args.base_seed, args.generations, args.population, args.seconds, len(seeds))
    validate_condition_records(condition_records(graph, base_config))
    if not limits.within_experiment(args.generations, args.population, args.seconds):
        raise ValueError("Topology batch exceeds configured compute limits")
    registry = ResearchRegistry(args.db)
    exp_id = registry.create_experiment(
        "topology_control_batch",
        "Bounded multi-seed topology-control evidence batch",
        {
            "version": TOPOLOGY_BATCH_VERSION,
            "project_epoch": PROJECT_EPOCH,
            "base_config": base_config,
            "seeds": seeds,
            "held_out_scenarios": [item["id"] for item in heldout],
            "claim_boundary": "Initial evidence batch only; no superiority claim.",
        },
        "running",
    )
    try:
        for record in condition_records(graph, base_config):
            registry.record_topology_condition(exp_id, record["condition"], record["graph_hash"], record["control_hash"], record)
        registry.record_worker_status("topology-batch", "topology-batch", "training", exp_id, "running topology batch")
        results = []
        for condition in TRAINABLE_CONDITIONS:
            detail = CONDITIONS[condition]
            for seed in seeds:
                config = {
                    "generations": args.generations,
                    "population": args.population,
                    "seconds": args.seconds,
                    "difficulties": ["easy"],
                    "condition": condition,
                    "topology": detail["topology"],
                    "held_out_suite": SCENARIO_SET_VERSION + ":test",
                }
                results.append(record_batch_condition(registry, graph, exp_id, condition, detail["topology"], seed, config, heldout))
        registry.record_worker_status("topology-batch", "topology-batch", "validating", exp_id, "recording baselines")
        for condition in DESCRIPTIVE_BASELINES:
            detail = CONDITIONS[condition]
            for seed in seeds:
                results.append(record_baseline(registry, graph, condition, detail["topology"], seed, heldout, args.seconds))
        direct = {
            "status": CONDITIONS["DIRECT_BASELINE"]["status"],
            "topology_batch_version": TOPOLOGY_BATCH_VERSION,
            "condition": "DIRECT_BASELINE",
            "topology": "direct",
            "reason": "Direct no-recurrent adapter/readout baseline is not implemented in this phase.",
            "training_budget": {
                "generations": args.generations,
                "population": args.population,
                "seconds": args.seconds,
            },
            "held_out_scenarios": [item["id"] for item in heldout],
            "win_rate": 0.0,
            "mean_reward": 0.0,
            "compute": {"wall_seconds": 0.0, "cpu_seconds": 0.0},
            "seed": None,
        }
        registry.record_evaluation(
            None,
            None,
            f"{TOPOLOGY_BATCH_VERSION}:DIRECT_BASELINE",
            SCENARIO_SET_VERSION,
            REWARD_VERSION,
            direct,
            [],
        )
        registry.update_experiment(exp_id, "complete")
        registry.record_worker_status("topology-batch", "topology-batch", "idle", exp_id, "batch complete")
        report = {
            "version": TOPOLOGY_BATCH_VERSION,
            "status": "complete",
            "experiment_id": exp_id,
            "db": str(registry.path),
            "synthetic": graph.manifest["synthetic"],
            "graph_hash": graph.manifest["graph_hash"],
            "seeds": seeds,
            "held_out_scenarios": [item["id"] for item in heldout],
            "training_budget": {
                "generations": args.generations,
                "population": args.population,
                "seconds": args.seconds,
            },
            "conditions": aggregate(results) | {"DIRECT_BASELINE": direct},
            "claim_boundary": "Do not infer condition superiority from this initial bounded batch.",
        }
        registry.record_daily_report(args.project_day, args.report_date, report)
        return report
    except Exception:
        registry.update_experiment(exp_id, "failed")
        registry.record_worker_status("topology-batch", "topology-batch", "error", exp_id, "batch failed")
        raise
    finally:
        registry.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db")
    parser.add_argument("--synthetic", action="store_true")
    parser.add_argument("--production", action="store_true")
    parser.add_argument("--base-seed", type=int, default=9401)
    parser.add_argument("--seeds", default="9401,9402")
    parser.add_argument("--generations", type=int, default=1)
    parser.add_argument("--population", type=int, default=4)
    parser.add_argument("--seconds", type=int, default=6)
    parser.add_argument("--heldout-matches", type=int, default=6)
    parser.add_argument("--project-day", type=int, default=1)
    parser.add_argument("--report-date", default="2026-09-14")
    args = parser.parse_args()
    structured_log("topology_batch_start", seeds=args.seeds, heldout_matches=args.heldout_matches)
    print(json.dumps(run_batch(args), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
