"""Scheduled one-shot daily scientific evaluator."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import time

from .checkpoints import load_candidate
from .ladder import LEVELS, compact_certification, evaluate_level
from .neural import Controller, Graph
from .production import load_compute_limits, load_production_env, structured_log
from .research_loop import current_champion_checkpoint, ensure_champion_record, project_day
from .research_registry import PROJECT_EPOCH, ResearchRegistry
from .scenarios import SCENARIO_SET_VERSION

DAILY_EVALUATOR_VERSION = "daily-evaluator-v1"


def summarize(report):
    if "champion_id" not in report:
        return report.get("summary", "Existing immutable research report for this date.")
    champion = report["champion_id"] or "seed-initialized"
    certified = report["certified_level"] or 0
    next_progress = report["next_level_progress"]
    line = "No next-level attempt recorded."
    if next_progress:
        line = f"{next_progress['level_version']} win rate: {round(next_progress['win_rate'] * 100, 1)}%."
    return "\n".join(
        [
            f"DAY {report['day']}",
            "",
            f"Champion {champion}",
            f"Certified Level {certified}",
            "",
            "No promotion today.",
            line,
        ]
    )


def evaluate_daily(args):
    if args.production:
        env = load_production_env()
        if env.role != "DAILY_EVALUATOR":
            raise ValueError("prod:daily requires FLYWEIGHT_SERVICE_ROLE=DAILY_EVALUATOR")
    graph = Graph(synthetic=bool(args.synthetic))
    if graph.manifest["synthetic"] and args.production:
        raise ValueError("Production daily evaluation requires real FlyWire graph")
    registry = ResearchRegistry(args.db)
    owner = "daily-evaluator"
    date = args.date or dt.date.today().isoformat()
    day = project_day(date, PROJECT_EPOCH)
    existing = registry.con.execute(
        "SELECT report_json FROM daily_reports WHERE project_day = ? AND report_date = ?",
        (day, date),
    ).fetchone()
    if existing and not args.force:
        report = json.loads(existing["report_json"])
        return {"status": "already_exists", "report": report, "summary": summarize(report)}
    if not registry.acquire_lease("daily-evaluator", owner, ttl_seconds=args.lease_seconds):
        registry.close()
        raise ValueError("Daily evaluator lease is already owned")
    try:
        registry.record_worker_status("daily-evaluator", owner, "certifying", message="daily evaluation started")
        checkpoint_id, checkpoint_hash, arrays = current_champion_checkpoint(graph)
        champion_id = ensure_champion_record(registry, graph, checkpoint_id, checkpoint_hash)
        if checkpoint_id != "seed-initialized":
            arrays, _ = load_candidate(graph, checkpoint_id)
        else:
            arrays = Controller(graph, 783).arrays()
        limits = load_compute_limits()
        started = time.process_time()
        per_level = []
        certified_level = 0
        max_levels = min(args.max_levels, len(LEVELS))
        for level in LEVELS[:max_levels]:
            if time.process_time() - started > limits.daily_cpu_time_budget_seconds:
                break
            result = compact_certification(
                evaluate_level(graph, arrays, level.index, checkpoint_hash, matches=args.matches, champion_id=champion_id)
            )
            registry.record_ladder_certification(result)
            per_level.append(result)
            if result["passed"]:
                certified_level = level.index
            else:
                break
        next_progress = per_level[-1] if per_level and not per_level[-1]["passed"] else None
        report = {
            "version": 1,
            "evaluator_version": DAILY_EVALUATOR_VERSION,
            "day": day,
            "date": date,
            "champion_id": champion_id,
            "champion_checkpoint": checkpoint_id,
            "champion_hash": checkpoint_hash,
            "code_commit": per_level[0]["code_commit"] if per_level else "unavailable",
            "graph_hash": graph.manifest["graph_hash"],
            "ladder_version": "combat-ladder-v1",
            "scenario_version": SCENARIO_SET_VERSION,
            "certified_level": certified_level,
            "per_level_results": per_level,
            "next_level_progress": next_progress,
            "generalisation_results": {"source": "ladder profiles and scenario families"},
            "responsiveness_results": [item["responsiveness_sanity_checks"] for item in per_level],
            "anomaly_flags": [flag for item in per_level for flag in item["exploit_anomaly_flags"]],
            "compute": {
                "cpu_seconds": time.process_time() - started,
                "levels_attempted": len(per_level),
                "matches": sum(item["matches"] for item in per_level),
            },
        }
        report["summary"] = summarize(report)
        registry.record_daily_report(day, date, report)
        registry.record_worker_status(
            "daily-evaluator",
            owner,
            "idle",
            message="daily evaluation complete",
            metrics=report["compute"],
        )
        return {"status": "complete", "report": report, "summary": report["summary"]}
    finally:
        registry.release_lease("daily-evaluator", owner)
        registry.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db")
    parser.add_argument("--synthetic", action="store_true")
    parser.add_argument("--production", action="store_true")
    parser.add_argument("--date")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--matches", type=int, default=12)
    parser.add_argument("--max-levels", type=int, default=10)
    parser.add_argument("--lease-seconds", type=int, default=900)
    args = parser.parse_args()
    structured_log("daily_evaluator_start", max_levels=args.max_levels, matches=args.matches)
    print(json.dumps(evaluate_daily(args), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
