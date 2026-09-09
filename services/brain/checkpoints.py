import time
import uuid

import numpy as np

from .limits import CHECKPOINTS, MAX_CHECKPOINTS, MAX_TRAINING_BYTES
from .storage import atomic_json, digest, read_json, safe_path, validate_npz


def save_candidate(graph, arrays, metadata, root=CHECKPOINTS):
    root.mkdir(parents=True, exist_ok=True)
    if len(list(root.glob("candidate_*.npz"))) >= MAX_CHECKPOINTS:
        raise ValueError("Checkpoint count quota")
    if sum(p.stat().st_size for p in root.iterdir() if p.is_file()) > MAX_TRAINING_BYTES - 8_000_000:
        raise ValueError("Training storage quota")
    ident = "candidate_" + uuid.uuid4().hex[:16]
    path = safe_path(root, ident, ".npz")
    np.savez(path, **arrays)
    entry = {"version": 1, "id": ident, "sha256": digest(path), "graph_hash": graph.manifest["graph_hash"],
             "created_ns": time.time_ns(), "seed": metadata["seed"], "generation": metadata["generation"],
             "reward": float(metadata["reward"]), "kind": "candidate", "topology": metadata.get("topology", "real")}
    atomic_json(safe_path(root, ident, ".json"), entry)
    return ident


def load_candidate(graph, ident, root=CHECKPOINTS):
    meta = read_json(safe_path(root, ident, ".json"))
    expected = {"version", "id", "sha256", "graph_hash", "created_ns", "seed", "generation", "reward", "kind", "topology"}
    if set(meta) != expected or meta["version"] != 1 or meta["id"] != ident or meta["graph_hash"] != graph.manifest["graph_hash"] or meta["kind"] != "candidate":
        raise ValueError("Checkpoint metadata mismatch")
    if type(meta["seed"]) is not int or not 0 <= meta["seed"] <= 2**32 - 1 or type(meta["generation"]) is not int or not 0 <= meta["generation"] <= 20 or not isinstance(meta["reward"], (int, float)) or not np.isfinite(meta["reward"]):
        raise ValueError("Checkpoint metadata values")
    specs = {"encoder": ((len(graph.inputs), 16), "float32"), "readout": ((8, len(graph.outputs)), "float32"),
             "bias": ((8,), "float32")}
    arrays = validate_npz(safe_path(root, ident, ".npz"), specs, meta["sha256"])
    if any(np.max(abs(v)) > 100 for v in arrays.values()):
        raise ValueError("Adapter amplitude limit")
    return arrays, meta


def list_candidates(graph, root=CHECKPOINTS):
    if not root.exists():
        return []
    canonical_path = root / "canonical.json"
    canonical = read_json(canonical_path).get("id") if canonical_path.exists() else None
    result = []
    for file in sorted(root.glob("candidate_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:MAX_CHECKPOINTS]:
        try:
            _, meta = load_candidate(graph, file.stem, root)
            result.append({k: meta[k] for k in ("id", "seed", "generation", "reward")} | {"canonical": file.stem == canonical})
        except (ValueError, OSError, KeyError):
            continue
    return result


def promote(graph, ident, evidence, root=CHECKPOINTS):
    _, meta = load_candidate(graph, ident, root)
    # CLI only. Suite gate is applied to freshly recomputed evidence by the trainer command.
    if evidence.get("suite") != "evaluation-v1" or evidence.get("episodes") != 9 or evidence.get("failures") != 0 or evidence.get("win_rate", 0) < .55 or evidence.get("mean_reward", -999) < evidence.get("previous_reward", 0) + 1:
        raise ValueError("Predefined evaluation gate failed")
    pointer = root / "canonical.json"
    previous = read_json(pointer).get("id") if pointer.exists() else None
    record = {"id": ident, "sha256": meta["sha256"], "previous": previous, "time_ns": time.time_ns(), "selection": "automatic_gate", "evidence": evidence}
    history = root / "promotions.jsonl"
    if history.exists() and history.stat().st_size > 1_000_000:
        raise ValueError("Promotion history quota")
    with history.open("a", encoding="utf-8") as file:
        import json
        file.write(json.dumps(record, allow_nan=False) + "\n")
    atomic_json(pointer, record)


def rollback(graph, root=CHECKPOINTS):
    pointer = root / "canonical.json"
    current = read_json(pointer)
    previous = current.get("previous")
    if not previous:
        raise ValueError("No prior canonical checkpoint")
    _, meta = load_candidate(graph, previous, root)
    record = {"id": previous, "sha256": meta["sha256"], "previous": current["id"], "time_ns": time.time_ns(), "selection": "rollback"}
    history = root / "promotions.jsonl"
    if history.stat().st_size > 1_000_000:
        raise ValueError("Promotion history quota")
    with history.open("a", encoding="utf-8") as file:
        import json
        file.write(json.dumps(record) + "\n")
    atomic_json(pointer, record)

