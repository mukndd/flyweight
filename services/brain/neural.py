"""Two independent runtimes: bounded engineering recurrence and research LIF."""
import time

import numpy as np
from scipy import sparse

from .limits import MAX_EDGES, MAX_LIF_STEPS, MAX_NEURONS, MAX_SPIKES, PROCESSED
from .storage import read_json, validate_npz

TOPOLOGIES = ("real", "degree_randomized", "weight_shuffled", "ordinary", "rule", "random")
OBSERVATIONS = 20
ACTION_COUNT = 14


class Graph:
    def __init__(self, synthetic=False):
        name = "synthetic" if synthetic else "flywire"
        manifest = read_json(PROCESSED / (name + ".json"))
        n, e = manifest["neurons"], manifest["edges"]
        if type(n) is not int or type(e) is not int or not 8 <= n <= MAX_NEURONS or not 0 < e <= MAX_EDGES:
            raise ValueError("Graph limits")
        if manifest["version"] != 1 or type(manifest["synthetic"]) is not bool:
            raise ValueError("Graph manifest version")
        specs = {"ids": ((n,), "int64"), "pre": ((e,), "int32"), "post": ((e,), "int32"),
                 "counts": ((e,), "int32"), "signs": ((e,), "int8"), "roles": ((n,), "int8")}
        arrays = validate_npz(PROCESSED / (name + ".npz"), specs, manifest["sha256"], 32_000_000)
        self.ids, self.pre, self.post = arrays["ids"], arrays["pre"], arrays["post"]
        self.counts, self.signs, self.roles = arrays["counts"], arrays["signs"], arrays["roles"]
        if len(np.unique(self.ids)) != n or np.any(self.ids < 0):
            raise ValueError("Graph IDs")
        if np.any(self.pre < 0) or np.any(self.post < 0) or np.any(self.pre >= n) or np.any(self.post >= n):
            raise ValueError("Graph index")
        if np.any(self.counts <= 0) or np.any(self.counts > 1_000_000) or not np.isin(self.signs, [-1, 0, 1]).all() or not np.isin(self.roles, [0, 1, 2]).all():
            raise ValueError("Graph count/sign/role")
        self.n, self.e, self.manifest = n, e, manifest
        self.inputs = np.flatnonzero(self.roles == 1)[:64]
        self.outputs = np.flatnonzero(self.roles == 2)[:64]
        if len(self.inputs) < 1 or len(self.outputs) < 1 or np.intersect1d(self.inputs, self.outputs).size:
            raise ValueError("Missing/disjoint adapters")
        self._matrices = {}
        rng = np.random.default_rng(783)
        selected = set(map(int, self.inputs[:20])) | set(map(int, self.outputs[:20]))
        selected.update(map(int, rng.choice(n, min(n, 140), replace=False)))
        self.sample = np.array(sorted(selected), dtype=np.int32)

    def matrix(self, topology="real"):
        if topology not in TOPOLOGIES:
            raise ValueError("Unknown topology")
        if topology in self._matrices:
            return self._matrices[topology]
        pre, post, weights, details = control_edges(self.pre, self.post, self.counts * self.signs, self.n, topology, 783)
        matrix = sparse.csr_matrix((weights.astype(np.float32), (post, pre)), shape=(self.n, self.n))
        # Engineering normalization: preserves direction and per-target ratios, limits gain.
        sums = np.asarray(abs(matrix).sum(axis=1)).ravel()
        matrix = (sparse.diags(.92 / np.maximum(1, sums)) @ matrix).tocsr()
        self._matrices[topology] = (matrix, details)
        return matrix, details

    def view(self, topology="real"):
        if topology in {"rule", "random"}:
            return {"ids": [], "roles": [], "edges": [], "neurons": 0, "edge_count": 0,
                    "synthetic": self.manifest["synthetic"], "dataset_hash": self.manifest["graph_hash"],
                    "input_count": 0, "output_count": 0}
        matrix, _ = self.matrix(topology)
        index = {int(v): i for i, v in enumerate(self.sample)}
        coo = matrix[self.sample][:, self.sample].tocoo()
        order = np.argsort(-np.abs(coo.data), kind="stable")[:600]
        edges = [[int(coo.col[i]), int(coo.row[i]), round(float(coo.data[i]), 7)] for i in order]
        return {"ids": [("synthetic:" + str(self.ids[i])) if self.manifest["synthetic"] else str(self.ids[i]) for i in self.sample],
                "roles": [1 if i in self.inputs else 2 if i in self.outputs else 0 for i in index],
                "edges": edges, "neurons": self.n, "edge_count": int(matrix.nnz),
                "synthetic": self.manifest["synthetic"], "dataset_hash": self.manifest["graph_hash"],
                "input_count": len(self.inputs), "output_count": len(self.outputs)}


def control_edges(pre, post, weights, n, topology, seed):
    pre, post, weights = pre.copy(), post.copy(), weights.copy()
    rng = np.random.default_rng(seed)
    swaps = 0
    if topology == "degree_randomized":
        pairs = set(zip(map(int, pre), map(int, post), strict=True))
        for _ in range(len(pre) * 5):
            a, b = rng.integers(0, len(pre), 2)
            u, v, x, y = int(pre[a]), int(post[a]), int(pre[b]), int(post[b])
            if u == x or v == y or u == y or x == v or (u, y) in pairs or (x, v) in pairs:
                continue
            pairs.remove((u, v))
            pairs.remove((x, y))
            pairs.update(((u, y), (x, v)))
            post[a], post[b] = y, v
            swaps += 1
    elif topology == "weight_shuffled":
        rng.shuffle(weights)
    elif topology == "ordinary":
        e = min(len(pre), n * (n - 1))
        chosen = rng.choice(n * (n - 1), e, replace=False)
        pre = (chosen // (n - 1)).astype(np.int32)
        post = (chosen % (n - 1)).astype(np.int32)
        post += post >= pre
        weights = weights[:e]
        rng.shuffle(weights)
    return pre, post, weights, {"directed_swaps": swaps, "seed": seed}


class Controller:
    def __init__(self, graph, seed=783, topology="real", arrays=None):
        self.graph, self.topology = graph, topology
        self.matrix, self.control_details = graph.matrix(topology)
        self.rng = np.random.default_rng(seed)
        ni, no = len(graph.inputs), len(graph.outputs)
        self.encoder = self.rng.normal(0, .7, (ni, OBSERVATIONS)).astype(np.float32)
        self.readout = self.rng.normal(0, .6, (ACTION_COUNT, no)).astype(np.float32)
        self.bias = np.zeros(ACTION_COUNT, dtype=np.float32)
        if arrays is not None:
            self.encoder, self.readout, self.bias = arrays["encoder"].copy(), arrays["readout"].copy(), arrays["bias"].copy()
        self.state = np.zeros(graph.n, dtype=np.float32)
        self.ticks = 0
        self.last_scores = []
        self.available = [True] * ACTION_COUNT
        self.last_inputs = []
        self.rule = None

    def arrays(self):
        return {"encoder": self.encoder, "readout": self.readout, "bias": self.bias}

    def act(self, values):
        start = time.perf_counter()
        obs = np.asarray(values, dtype=np.float32)
        if obs.shape != (OBSERVATIONS,) or not np.isfinite(obs).all() or np.max(np.abs(obs)) > 1:
            raise ValueError("Invalid normalized observation")
        self.ticks += 1
        if self.ticks > 3600:
            raise ValueError("Episode decision cap")
        self.last_inputs = obs.tolist()
        grounded, ready, combo = bool(obs[16] > .5), bool(obs[17] > .5), bool(obs[18] >= .99)
        self.available = [True] * ACTION_COUNT
        self.available[11] = not grounded and ready
        self.available[13] = combo and ready
        for attack in (5, 6, 9, 10, 12):
            self.available[attack] = ready and (grounded or attack not in (9, 12))
        self.available[3] = grounded
        if self.topology == "rule":
            action = 4 if obs[7] and obs[6] < .125 else 13 if combo and ready and obs[6] < .12 else (9 if obs[8] and grounded else 11 if not grounded else 5) if ready and obs[6] < .09 else 2 if obs[0] > 0 else 1
            self.rule = "Incoming attack: block" if action == 4 else "Attack within reach" if action in (5, 9, 11, 13) else "Close the distance"
            self.last_scores = []
            return action, (time.perf_counter() - start) * 1000
        if self.topology == "random":
            self.rule = "Seeded uniform choice among available actions"
            self.last_scores = []
            return int(self.rng.choice(np.flatnonzero(self.available))), (time.perf_counter() - start) * 1000
        stimulus = self.encoder @ obs
        for _ in range(8):
            drive = self.matrix @ self.state
            drive[self.graph.inputs] += stimulus
            self.state = (.65 * self.state + .35 * np.tanh(drive)).astype(np.float32)
        if not np.isfinite(self.state).all() or np.max(np.abs(self.state)) > 1.001:
            raise ValueError("Unstable neural state")
        # No observation bypass: readout sees only recurrent output-neuron activity.
        features = self.state[self.graph.outputs]
        logits = self.readout @ (features * 8) + self.bias
        self.last_scores = logits.astype(float).tolist()
        action = int(np.argmax(np.where(self.available, logits, -np.inf)))
        return action, (time.perf_counter() - start) * 1000

    def activity(self):
        if self.topology in {"rule", "random"}:
            return []
        return [round(float(v), 6) for v in self.state[self.graph.sample]]


class LIF:
    """Independent exact between-event integration of published linear equations; dt=0.1 ms."""
    def __init__(self, graph):
        self.n = graph.n
        self.weights = sparse.csr_matrix((graph.counts * graph.signs * .275, (graph.post, graph.pre)),
                                         shape=(self.n, self.n), dtype=np.float64)

    def run(self, duration_ms=100, rate_hz=150, input_indices=(), seed=783):
        if not isinstance(duration_ms, (float, int)) or not np.isfinite(duration_ms) or not 0 < duration_ms <= 1000:
            raise ValueError("Biological duration limit")
        if not np.isfinite(rate_hz) or not 0 <= rate_hz <= 300 or len(input_indices) > 64:
            raise ValueError("Stimulation limit")
        if any(type(i) is not int or not 0 <= i < self.n for i in input_indices):
            raise ValueError("Stimulation index")
        steps = int(round(duration_ms / .1))
        if steps > MAX_LIF_STEPS:
            raise ValueError("Biological step limit")
        rng = np.random.default_rng(seed)
        v = np.full(self.n, -52., dtype=np.float64)
        g = np.zeros(self.n)
        refractory = np.zeros(self.n, dtype=np.int32)
        delayed = np.zeros((19, self.n), dtype=np.float64)
        records = []
        counts = np.zeros(self.n, dtype=np.int32)
        started = time.monotonic()
        a, b = np.exp(-.1 / 20), np.exp(-.1 / 5)
        inputs = np.array(input_indices, dtype=np.int32)
        for tick in range(steps):
            if time.monotonic() - started > 20:
                raise ValueError("LIF execution time limit")
            g += delayed[tick % 19]
            delayed[tick % 19] = 0
            active = refractory == 0
            v[active] = -52 + (v[active] + 52) * a + g[active] * 5 / (5 - 20) * (b - a)
            g[active] *= b
            if len(inputs):
                v[inputs] += (rng.random(len(inputs)) < rate_hz * .0001) * (.275 * 250)
            spikes = (v > -45) & active
            emitted = np.flatnonzero(spikes)
            counts[emitted] += 1
            if emitted.size:
                records.extend((round(tick * .1, 1), int(i)) for i in emitted)
                if len(records) > MAX_SPIKES:
                    raise ValueError("Spike output quota")
                delayed[(tick + 18) % 19] += self.weights @ spikes.astype(float)
                v[spikes], g[spikes], refractory[spikes] = -52, 0, 23
            refractory = np.maximum(0, refractory - 1)
            if not np.isfinite(v).all() or not np.isfinite(g).all() or np.max(abs(g)) > 1e7:
                raise ValueError("LIF instability")
        return {"version": 1, "duration_ms": duration_ms, "seed": seed, "spikes": records,
                "spike_count": len(records), "max_rate_hz": float(counts.max() / (duration_ms / 1000)),
                "elapsed_seconds": time.monotonic() - started}

