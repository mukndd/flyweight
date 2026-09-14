"""Tiny local production-lifecycle burn-in harness."""
from __future__ import annotations

import argparse
import datetime as dt
import json
from types import SimpleNamespace

from .daily_evaluator import evaluate_daily
from .neural import Graph
from .research_loop import run_once
from .research_registry import ResearchRegistry

BURN_IN_VERSION = "burn-in-v1"


def run_burn_in(args):
    graph = Graph(synthetic=bool(args.synthetic))
    daily_date = (dt.date.fromisoformat(args.date) + dt.timedelta(days=1)).isoformat()
    registry = ResearchRegistry(args.db)
    try:
        if not registry.acquire_lease("burn-in-experiment", "worker-a", ttl_seconds=0):
            raise ValueError("Burn-in could not acquire initial lease")
        recovered = registry.acquire_lease("burn-in-experiment", "worker-b", ttl_seconds=60)
        registry.release_lease("burn-in-experiment", "worker-b")
    finally:
        registry.close()
    cycle = run_once(
        SimpleNamespace(
            synthetic=args.synthetic,
            db=args.db,
            lease_seconds=60,
            seed=args.seed,
            tiny=True,
            level=1,
            ladder_matches=4,
            topology_condition="REAL_CONNECTOME",
        )
    )
    first_daily = evaluate_daily(
        SimpleNamespace(
            synthetic=args.synthetic,
            production=False,
            db=args.db,
            date=daily_date,
            force=False,
            matches=4,
            max_levels=1,
            lease_seconds=60,
        )
    )
    second_daily = evaluate_daily(
        SimpleNamespace(
            synthetic=args.synthetic,
            production=False,
            db=args.db,
            date=daily_date,
            force=False,
            matches=4,
            max_levels=1,
            lease_seconds=60,
        )
    )
    registry = ResearchRegistry(args.db)
    try:
        overview = registry.overview()
    finally:
        registry.close()
    return {
        "version": BURN_IN_VERSION,
        "status": "complete",
        "graph_hash": graph.manifest["graph_hash"],
        "stale_lease_recovered": recovered,
        "cycle": cycle,
        "daily_first": first_daily["status"],
        "daily_second": second_daily["status"],
        "daily_date": daily_date,
        "dashboard_has_state": overview["today"] is not None and overview["latest_candidate"] is not None,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db")
    parser.add_argument("--synthetic", action="store_true")
    parser.add_argument("--seed", type=int, default=9301)
    parser.add_argument("--date", default="2026-09-14")
    args = parser.parse_args()
    print(json.dumps(run_burn_in(args), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
