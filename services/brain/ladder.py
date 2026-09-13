"""Versioned legal benchmark ladder and certification helpers."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from .scenarios import REWARD_VERSION, SCENARIO_SET_VERSION, scenarios
from .trainer import code_commit, episode, group_summary, summary

LADDER_VERSION = "combat-ladder-v1"


@dataclass(frozen=True)
class LadderLevel:
    index: int
    version: str
    difficulty: str
    profile: str
    seconds: int
    min_win_rate: float
    min_matches: int


LEVELS = [
    LadderLevel(1, "L01-v1", "easy", "standard", 8, .55, 12),
    LadderLevel(2, "L02-v1", "easy", "aggressive", 8, .58, 12),
    LadderLevel(3, "L03-v1", "easy", "mobile", 10, .60, 18),
    LadderLevel(4, "L04-v1", "medium", "standard", 10, .60, 18),
    LadderLevel(5, "L05-v1", "medium", "aggressive", 10, .62, 18),
    LadderLevel(6, "L06-v1", "medium", "counter-focused", 12, .62, 24),
    LadderLevel(7, "L07-v1", "hard", "standard", 12, .64, 24),
    LadderLevel(8, "L08-v1", "hard", "defensive", 12, .66, 30),
    LadderLevel(9, "L09-v1", "hard", "mixed", 14, .68, 30),
    LadderLevel(10, "L10-v1", "hard", "counter-focused", 14, .70, 36),
]


def ladder_manifest():
    data = {
        "version": LADDER_VERSION,
        "scenario_set_version": SCENARIO_SET_VERSION,
        "reward_version": REWARD_VERSION,
        "levels": [level.__dict__ for level in LEVELS],
        "legal_difficulty_sources": [
            "reaction timing",
            "spacing",
            "defensive accuracy",
            "aggression",
            "counter timing",
            "profile variation",
        ],
    }
    text = json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return data | {"hash": hashlib.sha256(text.encode("utf-8")).hexdigest()}


def get_level(index_or_version):
    for level in LEVELS:
        if index_or_version in {level.index, level.version}:
            return level
    raise ValueError("Unknown ladder level")


def ladder_seeds(level, matches=None):
    count = matches or level.min_matches
    if type(count) is not int or not 2 <= count <= 120:
        raise ValueError("Ladder match count bounds")
    return [7_100_000 + level.index * 10_000 + i for i in range(count)]


def evaluate_level(graph, arrays, level_index, checkpoint_hash, topology="real", matches=None, champion_id=None):
    level = get_level(level_index)
    rows = [
        episode(graph, arrays, seed, level.difficulty, level.seconds, topology=topology, profile=level.profile)
        for seed in ladder_seeds(level, matches)
    ]
    metrics = summary(rows)
    family = group_summary(rows, "difficulty", "profile")
    sanity = {
        "invalid_unavailable_actions": metrics["invalid_unavailable_actions"],
        "unique_action_traces": metrics["unique_action_traces"],
        "mean_trace_similarity": metrics["mean_trace_similarity"],
    }
    anomaly_flags = []
    if metrics["invalid_unavailable_actions"]:
        anomaly_flags.append("invalid_unavailable_actions")
    if len(rows) >= 6 and metrics["unique_action_traces"] <= 1:
        anomaly_flags.append("trace_collapse")
    passed = metrics["episodes"] >= level.min_matches and metrics["win_rate"] >= level.min_win_rate and not anomaly_flags
    return {
        "ladder_version": LADDER_VERSION,
        "level": level.index,
        "level_version": level.version,
        "champion_id": champion_id,
        "checkpoint_hash": checkpoint_hash,
        "scenario_suite": f"{LADDER_VERSION}:{level.version}",
        "matches": metrics["episodes"],
        "wins": metrics["wins"],
        "win_rate": metrics["win_rate"],
        "wilson_95_ci": metrics["win_rate_ci95_wilson"],
        "damage_differential": metrics["average_damage_differential"],
        "scenario_family_performance": family,
        "responsiveness_sanity_checks": sanity,
        "exploit_anomaly_flags": anomaly_flags,
        "code_commit": code_commit(),
        "graph_hash": graph.manifest["graph_hash"],
        "passed": passed,
        "criterion": {
            "min_matches": level.min_matches,
            "min_win_rate": level.min_win_rate,
            "no_anomaly_flags": True,
        },
        "rows": rows,
    }


def calibrate_ladder(graph, arrays, topology="rule", matches_per_level=6):
    if type(matches_per_level) is not int or not 2 <= matches_per_level <= 30:
        raise ValueError("Calibration match bounds")
    records = []
    for level in LEVELS:
        result = evaluate_level(graph, arrays, level.index, "calibration-reference", topology, matches_per_level)
        records.append(
            {
                "level": level.index,
                "level_version": level.version,
                "win_rate": result["win_rate"],
                "mean_reward": summary(result["rows"])["mean_reward"],
                "matches": result["matches"],
            }
        )
    inversions = []
    for prev, current in zip(records, records[1:]):
        # A lower reference win rate means the opponent was harder for that fixed reference controller.
        if current["win_rate"] > prev["win_rate"] + .15:
            inversions.append({"from": prev["level_version"], "to": current["level_version"], "reason": "easier_than_previous"})
    return {
        "version": 1,
        "ladder_version": LADDER_VERSION,
        "matches_per_level": matches_per_level,
        "reference_topology": topology,
        "records": records,
        "inversions": inversions,
        "status": "needs_review" if inversions else "calibrated_reference_pass",
    }


def compact_certification(result):
    return {key: value for key, value in result.items() if key != "rows"}


def scenario_ladder_mapping():
    return {
        "ladder_version": LADDER_VERSION,
        "source_scenario_version": SCENARIO_SET_VERSION,
        "families": sorted({item["family"] for item in scenarios()}),
        "levels": [level.__dict__ for level in LEVELS],
    }
