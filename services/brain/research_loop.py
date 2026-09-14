"""Bounded local autonomous research loop."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import time

from .checkpoints import load_candidate
from .ladder import calibrate_ladder, compact_certification, evaluate_level
from .limits import CHECKPOINTS
from .neural import Controller, Graph
from .production import load_compute_limits, load_production_env, structured_log
from .research_registry import PROJECT_EPOCH, ResearchRegistry, stable_id
from .scenarios import REWARD_VERSION, SCENARIO_SET_VERSION
from .storage import read_json
from .topology_experiments import condition_records, fair_config, validate_condition_records
from .trainer_interface import CEMTrainer, TrainerConfig

RESEARCH_LOOP_VERSION = "autonomous-research-loop-v1"


def project_day(today=None, epoch=PROJECT_EPOCH):
    today = today or dt.date.today().isoformat()
    return (dt.date.fromisoformat(today) - dt.date.fromisoformat(epoch)).days + 1


def current_champion_checkpoint(graph):
    pointer = CHECKPOINTS / "canonical.json"
    if pointer.exists():
        meta = read_json(pointer)
        try:
            arrays, _ = load_candidate(graph, meta["id"])
            return meta["id"], meta["sha256"], arrays
        except ValueError:
            if not graph.manifest["synthetic"]:
                raise
    controller = Controller(graph, 783)
    return "seed-initialized", "seed-initialized", controller.arrays()


def ensure_champion_record(registry, graph, checkpoint_id, checkpoint_hash):
    if checkpoint_id == "seed-initialized":
        return None
    row = registry.con.execute("SELECT id FROM candidates WHERE id = ?", (checkpoint_id,)).fetchone()
    if row is None:
        _, meta = load_candidate(graph, checkpoint_id)
        registry.record_candidate(
            candidate_id=checkpoint_id,
            parent_champion_id=None,
            run_id=None,
            trainer="CEMTrainer",
            trainer_version="cem-adapters-v1",
            training_seed=meta["seed"],
            graph_condition=meta.get("topology", "real").upper(),
            graph_hash=graph.manifest["graph_hash"],
            scenario_version=SCENARIO_SET_VERSION,
            reward_version=REWARD_VERSION,
            generation=meta["generation"],
            training_metrics={"fitness": meta["reward"], "source": "existing canonical checkpoint"},
            validation_metrics={},
            checkpoint_hash=checkpoint_hash,
            checkpoint_id=checkpoint_id,
            status="promoted",
            reason={"source": "canonical pointer at research registry initialization"},
        )
    champion = registry.current_champion()
    if champion is None:
        return registry.record_champion(
            checkpoint_id,
            checkpoint_id,
            checkpoint_hash,
            graph.manifest["graph_hash"],
            {"source": "existing canonical pointer"},
            "existing_canonical",
        )
    return champion["id"]


CONDITION_TO_TOPOLOGY = {
    "REAL_CONNECTOME": "real",
    "DEGREE_PRESERVING_RANDOMIZED": "degree_randomized",
    "WEIGHT_SHUFFLED": "weight_shuffled",
    "MATCHED_RANDOM_RECURRENT": "ordinary",
}


def select_experiment(seed, tiny=False, topology_condition="REAL_CONNECTOME"):
    if topology_condition not in CONDITION_TO_TOPOLOGY:
        raise ValueError("Unsupported trainable topology condition")
    return {
        "dimension": "cem_seed_budget_probe",
        "seed": seed,
        "generations": 1 if tiny else 4,
        "population": 4 if tiny else 8,
        "seconds": 6 if tiny else 8,
        "difficulties": ["easy"],
        "topology_condition": topology_condition,
        "topology": CONDITION_TO_TOPOLOGY[topology_condition],
        "promotion_mode": "record_only_no_fake_promotion",
    }


def run_once(args):
    graph = Graph(synthetic=bool(args.synthetic))
    registry = ResearchRegistry(args.db)
    owner = stable_id("worker")
    limits = load_compute_limits()
    if not registry.acquire_lease("research-loop", owner, ttl_seconds=args.lease_seconds):
        registry.close()
        raise ValueError("Another research worker owns the lease")
    try:
        recovered = registry.recover_interrupted_runs(older_than_ns=args.lease_seconds * 1_000_000_000)
        registry.record_worker_status(
            "research-loop",
            owner,
            "idle",
            message="lease acquired",
            metrics={"recovered_interrupted_runs": len(recovered)},
        )
        champion_checkpoint, champion_hash, _champion_arrays = current_champion_checkpoint(graph)
        champion_record_id = ensure_champion_record(registry, graph, champion_checkpoint, champion_hash)
        config = select_experiment(args.seed, args.tiny, args.topology_condition)
        if not limits.within_experiment(config["generations"], config["population"], config["seconds"]):
            registry.record_worker_status("research-loop", owner, "budget_exhausted", message="selected experiment exceeds governor")
            return {"status": "budget_exhausted", "reason": "selected experiment exceeds configured compute limits"}
        topology_config = fair_config(
            seed=args.seed,
            generations=config["generations"],
            population=config["population"],
            seconds=config["seconds"],
            independent_runs=1 if args.tiny else 3,
        )
        exp_id = registry.create_experiment(
            "autonomous_cem_probe",
            "Bounded CEM challenger cycle",
            {"loop_version": RESEARCH_LOOP_VERSION, "selected": config, "topology": topology_config},
            "running",
        )
        registry.record_worker_status("research-loop", owner, "training", exp_id, "training challenger", {"seed": args.seed})
        for record in condition_records(graph, topology_config):
            registry.record_topology_condition(exp_id, record["condition"], record["graph_hash"], record["control_hash"], record)
        validate_condition_records(condition_records(graph, topology_config))
        run_id = registry.create_run(exp_id, "CEMTrainer", args.seed, config)
        messages = []
        trainer_config = TrainerConfig(
            seed=args.seed,
            generations=config["generations"],
            population=config["population"],
            seconds=config["seconds"],
            difficulties=tuple(config["difficulties"]),
            topology=config["topology"],
        )
        checkpoint = ""
        try:
            cem = CEMTrainer(graph, trainer_config, emit=messages.append)
            cem.setup()
            checkpoint = cem.train_step()
            arrays, checkpoint_meta = load_candidate(graph, checkpoint)
            training_messages = [json.loads(line) for line in messages if json.loads(line).get("type") == "train_progress"]
            final_training = training_messages[-1] if training_messages else {}
            candidate_id = registry.record_candidate(
                candidate_id=checkpoint,
                parent_champion_id=champion_record_id,
                run_id=run_id,
                trainer="CEMTrainer",
                trainer_version=CEMTrainer.version,
                training_seed=args.seed,
                graph_condition=config["topology_condition"],
                graph_hash=graph.manifest["graph_hash"],
                scenario_version=SCENARIO_SET_VERSION,
                reward_version=REWARD_VERSION,
                generation=int(checkpoint_meta["generation"]),
                training_metrics={
                    "fitness": final_training.get("best_training_fitness", checkpoint_meta["reward"]),
                    "best_generation": final_training.get("best_generation", checkpoint_meta["generation"]),
                    "latest_generation": final_training.get("generation"),
                },
                validation_metrics={},
                checkpoint_hash=checkpoint_meta["sha256"],
                checkpoint_id=checkpoint,
                status="promising",
                reason={},
            )
            registry.record_checkpoint(
                checkpoint,
                candidate_id,
                checkpoint_meta["sha256"],
                (CHECKPOINTS / (checkpoint + ".npz")).stat().st_size,
                "local:checkpoints/" + checkpoint + ".npz",
            )
            certification = evaluate_level(
                graph,
                arrays,
                args.level,
                checkpoint_meta["sha256"],
                topology=config["topology"],
                matches=args.ladder_matches,
                champion_id=champion_record_id,
            )
            registry.record_worker_status("research-loop", owner, "certifying", exp_id, "ladder certification/progress", {"matches": args.ladder_matches})
            metrics = compact_certification(certification)
            registry.record_evaluation(
                candidate_id,
                None,
                metrics["scenario_suite"],
                SCENARIO_SET_VERSION,
                REWARD_VERSION,
                metrics,
                certification["rows"],
            )
            registry.record_ladder_certification(metrics)
            status = "validated" if metrics["passed"] else "certification_failed"
            reason = {} if metrics["passed"] else {"failed_level": metrics["level_version"], "flags": metrics["exploit_anomaly_flags"]}
            registry.update_candidate_status(candidate_id, status, reason, metrics)
            registry.finish_run(run_id, "complete")
            registry.update_experiment(exp_id, "complete")
        except Exception as error:
            registry.finish_run(run_id, "failed")
            registry.update_experiment(exp_id, "failed")
            raise ValueError(f"Research cycle failed: {type(error).__name__}") from error
        report = generate_daily_report(registry, graph)
        registry.record_worker_status("research-loop", owner, "idle", message="cycle complete", metrics={"experiments": 1})
        return {
            "status": "complete",
            "experiment_id": exp_id,
            "run_id": run_id,
            "checkpoint": checkpoint,
            "champion_at_start": champion_checkpoint,
            "daily_report": report,
            "db": str(registry.path),
        }
    finally:
        registry.release_lease("research-loop", owner)
        registry.close()


def generate_daily_report(registry, graph, date=None):
    date = date or dt.date.today().isoformat()
    day = project_day(date)
    overview = registry.overview()
    lineage = registry.lineage()
    candidates = lineage["nodes"]
    promotions = [item for item in candidates if item["status"] == "promoted"]
    report = {
        "version": 1,
        "project_epoch": PROJECT_EPOCH,
        "day": day,
        "date": date,
        "matches_simulated": sum(
            (item.get("validation_metrics") or {}).get("matches", 0) for item in candidates
        ),
        "experiments_completed": registry.con.execute(
            "SELECT COUNT(*) AS count FROM experiments WHERE status = 'complete'"
        ).fetchone()["count"],
        "candidates_evaluated": len(candidates),
        "compute_runtime_used": "local bounded CPU runs only",
        "champion_at_start": None,
        "champion_at_end": overview["current_champion"],
        "promotions": len(promotions),
        "rejected_promotions": len([item for item in candidates if item["status"] == "certification_failed"]),
        "certified_level": overview["certified_level"],
        "next_level_win_rate": None,
        "major_improvement": None,
        "major_regression": None,
        "current_blocker": None if candidates else "No autonomous research cycle recorded yet",
        "topology_experiments_status": "planned and registered; fair-control runs not concluded",
        "graph_hash": graph.manifest["graph_hash"],
    }
    registry.record_daily_report(day, date, report)
    return report


def run_loop(args):
    deadline = time.monotonic() + args.time_budget_seconds
    limits = load_compute_limits()
    results = []
    cycles = 0
    budget = min(args.candidate_budget, limits.max_daily_experiments)
    while cycles < budget and time.monotonic() < deadline:
        args.seed += cycles
        results.append(run_once(args))
        cycles += 1
    status = "budget_exhausted" if cycles >= budget else "complete"
    return {"status": status, "cycles": cycles, "results": results}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["once", "run", "daily", "calibrate"])
    parser.add_argument("--seed", type=int, default=9201)
    parser.add_argument("--db")
    parser.add_argument("--synthetic", action="store_true")
    parser.add_argument("--tiny", action="store_true")
    parser.add_argument("--level", type=int, default=1)
    parser.add_argument("--ladder-matches", type=int, default=4)
    parser.add_argument("--candidate-budget", type=int, default=1)
    parser.add_argument("--time-budget-seconds", type=int, default=600)
    parser.add_argument("--lease-seconds", type=int, default=900)
    parser.add_argument("--topology-condition", default="REAL_CONNECTOME", choices=sorted(CONDITION_TO_TOPOLOGY))
    parser.add_argument("--production", action="store_true")
    args = parser.parse_args()
    if args.production:
        env = load_production_env()
        if env.role != "RESEARCH_WORKER":
            raise ValueError("prod:research requires FLYWEIGHT_SERVICE_ROLE=RESEARCH_WORKER")
        if args.synthetic:
            raise ValueError("Production research requires real FlyWire graph")
        structured_log("research_worker_start", topology_condition=args.topology_condition, candidate_budget=args.candidate_budget)
    if args.command == "once":
        result = run_once(args)
    elif args.command == "run":
        result = run_loop(args)
    else:
        graph = Graph(synthetic=bool(args.synthetic))
        registry = ResearchRegistry(args.db)
        try:
            if args.command == "daily":
                result = generate_daily_report(registry, graph)
            else:
                result = calibrate_ladder(graph, Controller(graph, args.seed).arrays(), matches_per_level=args.ladder_matches)
        finally:
            registry.close()
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
