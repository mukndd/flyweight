"""Independent v783 adapter. Full input is batched; only a bounded selected subgraph is serialized."""
import argparse
import csv
import json
import time

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from scipy import sparse
from scipy.sparse.csgraph import dijkstra

from .limits import (MAX_EDGES, MAX_NEURONS, MAX_PROCESSED_BYTES, MAX_RAW_BYTES,
                     MAX_RAW_NEURONS, MAX_RAW_ROWS, PROCESSED, RAW, ROOT)
from .storage import atomic_json, digest, graph_fingerprint, read_json

VERSION = 1
COLUMNS = ["Presynaptic_ID", "Postsynaptic_ID", "Presynaptic_Index", "Postsynaptic_Index",
           "Connectivity", "Excitatory", "Excitatory x Connectivity", "__index_level_0__"]
ANNOTATIONS = "supervoxel_id root_id pos_x pos_y pos_z soma_x soma_y soma_z nucleus_id flow super_class cell_class cell_sub_class cell_type hemibrain_type ito_lee_hemilineage hartenstein_hemilineage morphology_group top_nt top_nt_conf known_nt known_nt_source side nerve vfb_id fbbt_id status".split()


def bounded_integer(value, low=0, high=2**63 - 1):
    if not isinstance(value, str) or not value.isascii() or not value.isdigit() or len(value) > 19:
        raise ValueError("Invalid bounded integer")
    result = int(value)
    if not low <= result <= high:
        raise ValueError("Integer out of bounds")
    return result


def verify_raw(name, lock):
    path = RAW / name
    entry = lock["files"][name]
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_RAW_BYTES or path.stat().st_size != entry["bytes"]:
        raise ValueError("Raw file byte limit/mismatch")
    if digest(path) != entry["sha256"]:
        raise ValueError("Raw source hash mismatch")
    return path


def read_metadata(path):
    ids = []
    with path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames != ["", "Completed"]:
            raise ValueError("Unknown completeness schema")
        for row in reader:
            if len(ids) >= MAX_RAW_NEURONS or row["Completed"] not in {"True", "False"}:
                raise ValueError("Metadata row/boolean limit")
            ids.append(bounded_integer(row[""], 1))
    if not ids or len(ids) != len(set(ids)):
        raise ValueError("Empty/duplicate neuron IDs")
    return np.array(ids, dtype=np.int64)


def read_annotations(path, ids):
    mapping = {int(x): i for i, x in enumerate(ids)}
    roles = np.zeros(len(ids), dtype=np.int8)
    seen = set()
    with path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file, delimiter="\t")
        if reader.fieldnames != ANNOTATIONS:
            raise ValueError("Unknown annotation schema")
        for count, row in enumerate(reader):
            if count >= MAX_RAW_NEURONS or any(v is None or len(v) > 2048 for v in row.values()):
                raise ValueError("Annotation limit")
            neuron = bounded_integer(row["root_id"], 1)
            if neuron in seen:
                raise ValueError("Duplicate annotation ID")
            seen.add(neuron)
            if row["top_nt_conf"]:
                confidence = float(row["top_nt_conf"])
                if not np.isfinite(confidence) or not 0 <= confidence <= 1:
                    raise ValueError("Invalid transmitter confidence")
            if neuron in mapping:
                role = 1 if row["flow"] == "afferent" or row["super_class"] == "sensory" else 0
                if row["super_class"] == "descending" or row["cell_class"] == "descending":
                    role = 2
                roles[mapping[neuron]] = role
    return roles


def validate_batch(values, ids):
    if set(values) != set(COLUMNS):
        raise ValueError("Unknown critical columns")
    arrays = {k: np.asarray(v) for k, v in values.items()}
    length = len(arrays[COLUMNS[0]])
    if length > 250_000 or any(a.dtype != np.int64 or a.ndim != 1 or len(a) != length for a in arrays.values()):
        raise ValueError("Column dtype/size")
    pre, post = arrays["Presynaptic_Index"], arrays["Postsynaptic_Index"]
    count, sign = arrays["Connectivity"], arrays["Excitatory"]
    if np.any(pre < 0) or np.any(post < 0) or np.any(pre >= len(ids)) or np.any(post >= len(ids)):
        raise ValueError("Index outside metadata")
    if not np.array_equal(ids[pre], arrays["Presynaptic_ID"]) or not np.array_equal(ids[post], arrays["Postsynaptic_ID"]):
        raise ValueError("ID/index disagreement")
    if np.any(count < 0) or np.any(count > 1_000_000) or not np.all(np.isin(sign, [-1, 0, 1])):
        raise ValueError("Invalid synapse count/sign")
    if not np.array_equal(count * sign, arrays["Excitatory x Connectivity"]):
        raise ValueError("Signed weight disagreement")
    return pre.astype(np.int32), post.astype(np.int32), count.astype(np.int32), sign.astype(np.int8)


def select_subgraph(outgoing, roles, n, seed):
    rng = np.random.default_rng(seed)
    incoming_strength = np.asarray(outgoing.sum(axis=0)).ravel()
    outputs = np.flatnonzero(roles == 2)
    inputs = np.flatnonzero(roles == 1)
    if len(outputs) == 0 or len(inputs) == 0:
        raise ValueError("Annotations contain no sensory/descending candidates")
    outputs = outputs[np.argsort(-incoming_strength[outputs], kind="stable")[:16]]
    dist, predecessors = dijkstra(outgoing.T.tocsr(), directed=True, indices=outputs, unweighted=True,
                                  limit=8, return_predecessors=True)
    chosen = set(map(int, outputs))
    paths = []
    candidate_pairs = sorted((float(dist[j, i]), int(i), j) for j in range(len(outputs)) for i in inputs
                             if np.isfinite(dist[j, i]) and dist[j, i] > 0)
    used_inputs = set()
    for _, input_id, j in candidate_pairs:
        if input_id in used_inputs:
            continue
        path = [input_id]
        while path[-1] != outputs[j]:
            parent = int(predecessors[j, path[-1]])
            if parent < 0 or len(path) > 10:
                raise ValueError("Invalid directed path")
            path.append(parent)
        if len(chosen | set(path)) > n // 2:
            break
        chosen.update(path)
        used_inputs.add(input_id)
        paths.append(path)
        if len(used_inputs) >= 64:
            break
    if not paths:
        raise ValueError("No sensory-to-descending path within eight hops")
    tie = rng.random(outgoing.shape[0]) * 1e-6
    while len(chosen) < n:
        idx = np.array(sorted(chosen))
        score = np.asarray(outgoing[idx].sum(axis=0)).ravel() + np.asarray(outgoing[:, idx].sum(axis=1)).ravel()
        score = score.astype(float) + tie
        score[idx] = -1
        take = min(128, n - len(chosen))
        partners = np.argsort(-score, kind="stable")[:take]
        chosen.update(map(int, partners))
    return np.array(sorted(chosen), dtype=np.int32), paths


def save_graph(ids, pre, post, counts, signs, roles, seed, synthetic, sources, details):
    n, e = len(ids), len(pre)
    if not 8 <= n <= MAX_NEURONS or not 0 < e <= MAX_EDGES:
        raise ValueError("Graph neuron/edge limit")
    if any(a.shape != (e,) for a in (post, counts, signs)) or roles.shape != (n,):
        raise ValueError("Graph shapes")
    if np.any(pre < 0) or np.any(post < 0) or np.any(pre >= n) or np.any(post >= n):
        raise ValueError("Graph indices")
    PROCESSED.mkdir(parents=True, exist_ok=True)
    used = sum(p.stat().st_size for p in PROCESSED.iterdir() if p.is_file())
    if used + n * 16 + e * 16 > MAX_PROCESSED_BYTES:
        raise ValueError("Processed storage quota")
    fingerprint = graph_fingerprint(ids, pre, post, counts, signs)
    name = "synthetic" if synthetic else "flywire"
    path = PROCESSED / f"{name}.npz"
    # Uncompressed safe NPZ avoids decompression expansion and is still compact at this scale.
    np.savez(path, ids=ids.astype(np.int64), pre=pre.astype(np.int32), post=post.astype(np.int32),
             counts=counts.astype(np.int32), signs=signs.astype(np.int8), roles=roles.astype(np.int8))
    manifest = {"version": VERSION, "neurons": n, "edges": e, "synthetic": synthetic, "seed": seed,
                "sha256": digest(path), "graph_hash": fingerprint, "bytes": path.stat().st_size,
                "sources": sources, "selection": details, "input_count": int(np.sum(roles == 1)),
                "output_count": int(np.sum(roles == 2)), "zero_sign_edges": int(np.sum(signs == 0))}
    atomic_json(PROCESSED / f"{name}.json", manifest)
    print(json.dumps(manifest, indent=2), flush=True)
    return manifest


def synthetic(n=256, seed=783):
    if not 32 <= n <= MAX_NEURONS:
        raise ValueError("Synthetic neuron cap")
    rng = np.random.default_rng(seed)
    pairs = {(i, (i + 1) % n) for i in range(n)}
    pairs.update((int(a), int(b)) for a, b in zip(rng.integers(0, n, n * 7), rng.integers(0, n, n * 7), strict=True) if a != b)
    pre, post = np.array(sorted(pairs), dtype=np.int32).T
    roles = np.zeros(n, dtype=np.int8)
    roles[:32] = 1
    roles[-16:] = 2
    signs = np.where(rng.random(n) < .2, -1, 1).astype(np.int8)[pre]
    return save_graph(np.arange(n, dtype=np.int64), pre, post, rng.integers(1, 20, len(pre), dtype=np.int32),
                      signs, roles, seed, True, {}, {"method": "Synthetic ring plus seeded random edges; IDs are synthetic indices"})


def real(n=1536, seed=783):
    if not 1000 <= n <= MAX_NEURONS:
        raise ValueError("Real subgraph size must be 1000..5000")
    started = time.monotonic()
    lock = read_json(ROOT / "docs/source-lock.json")
    if sum(p.stat().st_size for p in RAW.iterdir() if p.is_file()) > MAX_RAW_BYTES:
        raise ValueError("Raw storage quota")
    ids = read_metadata(verify_raw("Completeness_783.csv", lock))
    roles = read_annotations(verify_raw("annotations_783.tsv", lock), ids)
    print(f"Metadata: {len(ids)} neurons; sensory={sum(roles == 1)}, descending={sum(roles == 2)}", flush=True)
    pf = pq.ParquetFile(verify_raw("Connectivity_783.parquet", lock))
    if pf.schema_arrow.names != COLUMNS or any(field.type != pa.int64() for field in pf.schema_arrow):
        raise ValueError("Unknown parquet schema/dtype")
    rows = pf.metadata.num_rows
    if not 0 < rows <= MAX_RAW_ROWS:
        raise ValueError("Parquet row cap")
    pre = np.empty(rows, dtype=np.int32)
    post = np.empty(rows, dtype=np.int32)
    counts = np.empty(rows, dtype=np.int32)
    signs = np.empty(rows, dtype=np.int8)
    offset = 0
    for batch in pf.iter_batches(batch_size=200_000, use_threads=False):
        if time.monotonic() - started > 180:
            raise ValueError("Preprocessing time limit")
        values = {name: batch.column(name).to_numpy(zero_copy_only=False) for name in COLUMNS}
        arrays = validate_batch(values, ids)
        length = len(arrays[0])
        for target, source in zip((pre, post, counts, signs), arrays, strict=True):
            target[offset:offset + length] = source
        offset += length
    outgoing = sparse.csr_matrix((counts, (pre, post)), shape=(len(ids), len(ids)))
    if outgoing.nnz != rows:
        raise ValueError("Duplicate directed edge records")
    selected, paths = select_subgraph(outgoing, roles, n, seed)
    mapping = np.full(len(ids), -1, dtype=np.int32)
    mapping[selected] = np.arange(n, dtype=np.int32)
    mask = (mapping[pre] >= 0) & (mapping[post] >= 0) & (counts > 0)
    details = {"method": "16 strongest descending anchors; up to 64 sensory shortest directed paths (<=8 hops); iterative strongest partners in batches of 128",
               "path_count": len(paths), "paths_flywire_ids": [[str(ids[i]) for i in p] for p in paths],
               "full_neuron_count": len(ids), "full_edge_count": rows, "elapsed_seconds": time.monotonic() - started,
               "sign_policy": "Author-distributed Excitatory column; includes uniform transmitter/receptor assumptions; unknown sign=0",
               "coordinates": "No anatomical coordinates used; visualization is a seeded schematic"}
    return save_graph(ids[selected], mapping[pre[mask]], mapping[post[mask]], counts[mask], signs[mask], roles[selected],
                      seed, False, {k: v["sha256"] for k, v in lock["files"].items()}, details)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--synthetic", action="store_true")
    parser.add_argument("--neurons", type=int)
    parser.add_argument("--seed", type=int, default=783)
    args = parser.parse_args()
    if not 0 <= args.seed <= 2**32 - 1:
        parser.error("Seed out of range")
    try:
        (synthetic if args.synthetic else real)(args.neurons or (256 if args.synthetic else 1536), args.seed)
    except KeyboardInterrupt:
        raise SystemExit("Preprocessing cancelled; raw input unchanged")

