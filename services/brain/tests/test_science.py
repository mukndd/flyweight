
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from services.brain.neural import LIF, Controller, control_edges
from services.brain.preprocess import COLUMNS, read_metadata, validate_batch


def fixture_batch():
    ids = np.array([101, 202, 303], dtype=np.int64)
    values = {"Presynaptic_ID": [101, 202], "Postsynaptic_ID": [202, 303], "Presynaptic_Index": [0, 1],
              "Postsynaptic_Index": [1, 2], "Connectivity": [3, 7], "Excitatory": [1, -1],
              "Excitatory x Connectivity": [3, -7], "__index_level_0__": [0, 1]}
    return ids, {k: np.array(v, dtype=np.int64) for k, v in values.items()}


def test_graph_direction_counts_sign_and_id_invariants():
    ids, values = fixture_batch()
    pre, post, counts, signs = validate_batch(values, ids)
    assert pre.tolist() == [0, 1] and post.tolist() == [1, 2]
    assert counts.tolist() == [3, 7] and signs.tolist() == [1, -1]
    for key in COLUMNS:
        bad = dict(values)
        bad[key] = bad[key].astype(np.float64)
        with pytest.raises(ValueError):
            validate_batch(bad, ids)
    for key, value in [("Presynaptic_Index", -1), ("Postsynaptic_ID", 999), ("Connectivity", -1), ("Excitatory", 7), ("Excitatory x Connectivity", 9)]:
        bad = {k: v.copy() for k, v in values.items()}
        bad[key][0] = value
        with pytest.raises(ValueError):
            validate_batch(bad, ids)


def test_csv_and_parquet_schema(tmp_path):
    file = tmp_path / "bad.csv"
    for content in ["id,Completed\n1,True", ",Completed\n1,True\n1,False", ",Completed\nNaN,True", ",Completed\n1,yes"]:
        file.write_text(content)
        with pytest.raises(ValueError):
            read_metadata(file)
    path = tmp_path / "bad.parquet"
    pq.write_table(pa.table({"wrong": [1, 2]}), path)
    batch = next(pq.ParquetFile(path).iter_batches())
    with pytest.raises(ValueError):
        validate_batch(batch.to_pydict(), np.array([1, 2]))


def test_degree_preserving_rewire_and_weight_controls(graph):
    pre, post, weights, info = control_edges(graph.pre, graph.post, graph.counts*graph.signs, graph.n, "degree_randomized", 9)
    assert info["directed_swaps"] > 0
    assert np.array_equal(np.bincount(pre, minlength=graph.n), np.bincount(graph.pre, minlength=graph.n))
    assert np.array_equal(np.bincount(post, minlength=graph.n), np.bincount(graph.post, minlength=graph.n))
    assert len(set(zip(pre, post, strict=True))) == len(pre)
    _, _, shuffled, _ = control_edges(graph.pre, graph.post, weights, graph.n, "weight_shuffled", 9)
    assert np.array_equal(np.sort(weights), np.sort(shuffled))


def test_neural_normalization_fuzz_and_no_bypass(graph):
    rng = np.random.default_rng(7)
    c = Controller(graph)
    for _ in range(100):
        a, ms = c.act(rng.uniform(-1, 1, 20))
        assert 0 <= a < 14 and ms >= 0 and np.isfinite(c.state).all() and max(abs(c.state)) <= 1
    for value in [np.nan, np.inf, -np.inf, 1.01, -1.01]:
        with pytest.raises(ValueError):
            c.act([value]*20)
    # Remove the network: non-input output neurons can receive no stimulus.
    c = Controller(graph)
    c.matrix = c.matrix * 0
    for _ in range(20):
        c.act([1.]*20)
    assert np.all(c.state[graph.outputs] == 0)
    assert np.any(c.state[graph.inputs] != 0)


def test_recurrent_reset_is_deterministic(graph):
    a, b = Controller(graph, 4), Controller(graph, 4)
    for _ in range(20):
        assert a.act([.4]*20)[0] == b.act([.4]*20)[0]
    assert np.array_equal(a.state, b.state)


def test_lif_rest_stimulation_and_limits(graph):
    lif = LIF(graph)
    rest = lif.run(20, 0, [], 7)
    assert rest["spike_count"] == 0
    a, b = lif.run(50, 300, [0, 1], 783), lif.run(50, 300, [0, 1], 783)
    assert a["spike_count"] > 0 and a["spikes"] == b["spikes"]
    for duration in [np.nan, np.inf, -1, 1001]:
        with pytest.raises(ValueError):
            lif.run(duration)
    with pytest.raises(ValueError):
        lif.run(10, 400, [0])
