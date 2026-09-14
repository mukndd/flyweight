"""Production bootstrap verification for the processed FlyWire graph."""
from __future__ import annotations

import argparse
import json

from .config import SETTINGS
from .neural import Graph

BOOTSTRAP_VERSION = "flywire-bootstrap-v1"


def verify_processed_graph(production=False):
    graph = Graph(synthetic=not (SETTINGS.data_dir / "flywire.json").exists())
    if production and graph.manifest["synthetic"]:
        raise ValueError("Production bootstrap refuses synthetic graph")
    return {
        "version": BOOTSTRAP_VERSION,
        "dataset_version": "FlyWire FAFB v783",
        "graph_hash": graph.manifest["graph_hash"],
        "neurons": graph.n,
        "edges": graph.e,
        "synthetic": graph.manifest["synthetic"],
        "source": "processed graph artifact in FLYWEIGHT_DATA_DIR",
        "ready": not graph.manifest["synthetic"] or not production,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--production", action="store_true")
    args = parser.parse_args()
    print(json.dumps(verify_processed_graph(args.production), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
