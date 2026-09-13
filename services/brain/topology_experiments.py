"""Fair topology-control experiment planning."""
from __future__ import annotations

import hashlib
import json

from .neural import TOPOLOGIES
from .scenarios import REWARD_VERSION, SCENARIO_SET_VERSION

TOPOLOGY_EXPERIMENT_VERSION = "topology-controls-v1"

CONDITIONS = {
    "REAL_CONNECTOME": {"topology": "real", "trainable": True, "description": "FlyWire-derived topology"},
    "DEGREE_PRESERVING_RANDOMIZED": {
        "topology": "degree_randomized",
        "trainable": True,
        "description": "Directed degree-preserving randomized topology",
    },
    "WEIGHT_SHUFFLED": {
        "topology": "weight_shuffled",
        "trainable": True,
        "description": "Original topology with shuffled signed weights",
    },
    "MATCHED_RANDOM_RECURRENT": {
        "topology": "ordinary",
        "trainable": True,
        "description": "Sparse ordinary recurrent graph matched to node and edge budget",
    },
    "DIRECT_BASELINE": {
        "topology": "direct",
        "trainable": True,
        "description": "Planned no-recurrent adapter/readout baseline",
        "status": "planned_interface_only",
    },
    "RULE_BASELINE": {"topology": "rule", "trainable": False, "description": "Hand-authored legal rule policy"},
    "RANDOM_ACTION_BASELINE": {
        "topology": "random",
        "trainable": False,
        "description": "Seeded uniform legal action baseline",
    },
}


def _fingerprint(value):
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def fair_config(seed=783, generations=4, population=8, seconds=8, independent_runs=3):
    if type(seed) is not int or not 0 <= seed <= 999_999:
        raise ValueError("Invalid topology experiment seed")
    if not 1 <= generations <= 20 or not 4 <= population <= 12 or not 6 <= seconds <= 30:
        raise ValueError("Invalid topology experiment budget")
    if not 1 <= independent_runs <= 12:
        raise ValueError("Invalid independent-run count")
    config = {
        "version": TOPOLOGY_EXPERIMENT_VERSION,
        "base_seed": seed,
        "independent_runs": independent_runs,
        "trainer": "CEMTrainer",
        "trainer_budget": {"generations": generations, "population": population, "seconds": seconds},
        "observation_space": "protocol-v2-20-observations",
        "action_space": "protocol-v2-14-actions",
        "scenario_version": SCENARIO_SET_VERSION,
        "reward_version": REWARD_VERSION,
        "held_out_suite": "scenario-library-v1:test",
        "conditions": CONDITIONS,
        "unavoidable_differences": {
            "DIRECT_BASELINE": "No recurrent graph exists yet; reserved behind an explicit condition id.",
            "RULE_BASELINE": "No trainable adapter parameters.",
            "RANDOM_ACTION_BASELINE": "No trainable adapter parameters.",
        },
    }
    return config | {"config_hash": _fingerprint(config)}


def condition_records(graph, config):
    records = []
    for name, detail in CONDITIONS.items():
        topology = detail["topology"]
        if topology in TOPOLOGIES:
            matrix, info = graph.matrix(topology)
            control_hash = _fingerprint(
                {
                    "condition": name,
                    "topology": topology,
                    "nnz": int(matrix.nnz),
                    "details": info,
                    "graph_hash": graph.manifest["graph_hash"],
                }
            )
            edges = int(matrix.nnz)
        else:
            control_hash = _fingerprint(
                {"condition": name, "topology": topology, "status": detail.get("status", "planned")}
            )
            edges = 0
        records.append(
            {
                "condition": name,
                "topology": topology,
                "graph_hash": graph.manifest["graph_hash"],
                "control_hash": control_hash,
                "node_count": graph.n if topology not in {"rule", "random", "direct"} else 0,
                "edge_count": edges,
                "config_hash": config["config_hash"],
                "trainable": detail["trainable"],
                "status": detail.get("status", "implemented"),
            }
        )
    return records


def validate_condition_records(records):
    names = [record["condition"] for record in records]
    if set(names) != set(CONDITIONS) or len(names) != len(set(names)):
        raise ValueError("Topology condition coverage mismatch")
    for record in records:
        if record["status"] == "implemented" and record["topology"] not in TOPOLOGIES:
            raise ValueError("Implemented topology is unavailable")
    return True
