"""Reproduce the bounded exploratory v2 suite; every raw row is retained locally."""
import json
import os
import time
import uuid
from pathlib import Path

for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[name] = "1"

from services.brain import trainer  # noqa: E402
from services.brain.neural import LIF, TOPOLOGIES, Controller, Graph  # noqa: E402
from services.brain.storage import digest  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def main():
    graph = Graph()
    before = digest(ROOT / "data/processed/flywire.npz")
    directory = ROOT / "docs/results" / ("suite_" + uuid.uuid4().hex[:12])
    directory.mkdir(parents=True)
    config = {"version": 2, "code_commit": trainer.code_commit(), "dataset_hash": graph.manifest["graph_hash"],
              "graph_file_sha256": before, "initialization_seeds": [783, 784, 785],
              "training": {"generations": 2, "population": 4, "episode_seconds": 6},
              "evaluation_seeds": trainer.EVAL_SEEDS, "difficulties": trainer.DIFFICULTIES,
              "status": "exploratory", "selection": "all runs retained; no canonical promotion"}
    (directory / "config.json").write_text(json.dumps(config, indent=2))
    started = time.perf_counter()
    try:
        for seed in config["initialization_seeds"]:
            old = set((ROOT / "checkpoints").glob("run_*.jsonl"))
            checkpoint = trainer.train(graph, seed, 2, 4, 6)
            new = set((ROOT / "checkpoints").glob("run_*.jsonl")) - old
            for raw in new:
                (directory / raw.name).write_bytes(raw.read_bytes())
            print(json.dumps({"trained_seed": seed, "checkpoint": checkpoint}), flush=True)
        with (directory / "controls.jsonl").open("x", encoding="utf-8") as raw:
            for seed in config["initialization_seeds"]:
                arrays = Controller(graph, seed).arrays()
                for topology in TOPOLOGIES:
                    for ablate in (None, 7):
                        report = trainer.evaluate(graph, arrays, 6, topology, ablate)
                        record = {"initialization_seed": seed, "topology": topology, "ablated_channel": ablate, **report}
                        raw.write(json.dumps(record, allow_nan=False) + "\n")
                        raw.flush()
                print(json.dumps({"controls_seed_complete": seed}), flush=True)
        lif = LIF(graph).run(100, 150, list(map(int, graph.inputs[:8])), 783)
        (directory / "lif.json").write_text(json.dumps(lif))
        assert before == digest(ROOT / "data/processed/flywire.npz"), "Fixed graph changed"
        (directory / "completion.json").write_text(json.dumps({"elapsed_seconds": time.perf_counter()-started, "graph_unchanged": True, "status": "complete"}))
    except (ValueError, OSError, AssertionError) as error:
        (directory / "failure.json").write_text(json.dumps({"type": type(error).__name__, "elapsed_seconds": time.perf_counter()-started}))
        raise
    print(json.dumps({"results": str(directory), "elapsed_seconds": time.perf_counter()-started}), flush=True)


if __name__ == "__main__":
    main()
