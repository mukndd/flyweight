import io
import json
import zipfile

import numpy as np
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from services.brain import app as server
from services.brain import checkpoints, neural, preprocess, trainer
from services.brain.limits import ORIGIN
from services.brain.protocol import parse_message
from services.brain.storage import digest, safe_path, validate_npz


@pytest.mark.parametrize("name", ["../x", "..", "/absolute", "C:\\x", "x/y", "x\\y", ".env", "", "x:stream", "a"*81])
def test_path_traversal(tmp_path, name):
    with pytest.raises(ValueError):
        safe_path(tmp_path, name, ".npz")


@pytest.mark.parametrize("raw", [
    '{"v":3,"type":"health"}', '{"v":true,"type":"health"}', '{"v":2,"type":"execute"}',
    '{"v":2,"type":"health","path":"../x"}', '{"v":2,"type":"action","action":99}',
    '{"v":2,"type":"reset","seed":NaN,"topology":"real"}', '{"v":2,"type":"reset","seed":Infinity,"topology":"real"}',
    '{"v":2,"type":"reset","seed":-1,"topology":"real"}', '{"v":2,"type":"reset","seed":3,"topology":"evil"}',
    '{"v":2,"type":"checkpoint_load","id":"../x"}', '[]', 'null', '{}', 'x'*8193
])
def test_protocol_invalid(raw):
    with pytest.raises(ValueError):
        parse_message(raw)


def test_protocol_observation_fuzz():
    rng = np.random.default_rng(41)
    for _ in range(100):
        values = rng.uniform(-1, 1, 20).tolist()
        raw = {"v": 2, "type": "observation", "seq": 0, "values": values}
        assert parse_message(json.dumps(raw)).values == values
        raw["values"][int(rng.integers(20))] = float(rng.choice([np.nan, np.inf, -np.inf, 2, -2]))
        with pytest.raises(ValueError):
            parse_message(json.dumps(raw))


@pytest.mark.parametrize("bad", [b"not an npz", b"\x80\x04pickle"])
def test_corrupt_pickle_rejected(tmp_path, bad):
    path = tmp_path / "bad.npz"
    path.write_bytes(bad)
    with pytest.raises(ValueError):
        validate_npz(path, {"a": ((1,), "float32")}, digest(path))
    path = tmp_path / "bad.pkl"
    path.write_bytes(bad)
    with pytest.raises(ValueError):
        validate_npz(path, {}, digest(path))


def test_checkpoint_size_hash_shapes_nonfinite_and_archive_attacks(tmp_path):
    path = tmp_path / "state.npz"
    np.savez(path, a=np.array([1], dtype=np.float32))
    with pytest.raises(ValueError):
        validate_npz(path, {"a": ((1,), "float32")}, "0"*64)
    with pytest.raises(ValueError):
        validate_npz(path, {"a": ((1,), "float32")}, digest(path), limit=1)
    with pytest.raises(ValueError):
        validate_npz(path, {"a": ((100_000_000,), "float32")}, digest(path))
    np.savez(path, a=np.array([np.nan], dtype=np.float32))
    with pytest.raises(ValueError):
        validate_npz(path, {"a": ((1,), "float32")}, digest(path))
    np.savez(path, a=np.array([{"bad": "pickle"}], dtype=object))
    with pytest.raises(ValueError):
        validate_npz(path, {"a": ((1,), "float32")}, digest(path))
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("../a.npy", b"x")
    with pytest.raises(ValueError):
        validate_npz(path, {"a": ((1,), "float32")}, digest(path))
    # Header claims a huge tensor but provides no body: reject before allocation.
    payload = io.BytesIO()
    np.lib.format.write_array_header_1_0(payload, {"descr": "<f4", "fortran_order": False, "shape": (10**10,)})
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("a.npy", payload.getvalue())
    with pytest.raises(ValueError):
        validate_npz(path, {"a": ((1,), "float32")}, digest(path))


def test_graph_extreme_counts_before_allocation(tmp_path, monkeypatch):
    monkeypatch.setattr(neural, "PROCESSED", tmp_path)
    for n, e in [(5001, 20), (10, 500001), (0, 5), (True, 20)]:
        (tmp_path / "synthetic.json").write_text(json.dumps({"neurons": n, "edges": e, "version": 1, "synthetic": True}))
        with pytest.raises(ValueError):
            neural.Graph(True)
    with pytest.raises(ValueError):
        preprocess.synthetic(5001)


def test_raw_hash_fails_before_parse(tmp_path, monkeypatch):
    monkeypatch.setattr(preprocess, "RAW", tmp_path)
    (tmp_path / "test.csv").write_text("malformed")
    with pytest.raises(ValueError):
        preprocess.verify_raw("test.csv", {"files": {"test.csv": {"bytes": 9, "sha256": "0"*64}}})


def test_checkpoint_isolation_gate_and_rollback(graph, tmp_path):
    arrays = neural.Controller(graph).arrays()
    first = checkpoints.save_candidate(graph, arrays, {"seed": 783, "generation": 1, "reward": 2}, tmp_path)
    second = checkpoints.save_candidate(graph, arrays, {"seed": 784, "generation": 2, "reward": 5}, tmp_path)
    assert not (tmp_path / "canonical.json").exists()
    with pytest.raises(ValueError):
        checkpoints.promote(graph, first, {}, tmp_path)
    evidence = {"suite": "evaluation-v2", "episodes": 9, "failures": 0, "win_rate": 1, "mean_reward": 20, "previous_reward": 0}
    checkpoints.promote(graph, first, evidence, tmp_path)
    checkpoints.promote(graph, second, evidence, tmp_path)
    checkpoints.rollback(graph, tmp_path)
    assert json.loads((tmp_path / "canonical.json").read_text())["id"] == first
    assert len((tmp_path / "promotions.jsonl").read_text().splitlines()) == 3
    path = tmp_path / (first + ".npz")
    path.write_bytes(b"corrupted")
    with pytest.raises(ValueError):
        checkpoints.load_candidate(graph, first, tmp_path)


def test_rate_limit_refill():
    limiter = server.RateLimiter(3)
    now = limiter.last
    assert [limiter.allow(now) for _ in range(4)] == [True, True, True, False]
    assert limiter.allow(now + 1)


@pytest.fixture
def client(graph, monkeypatch):
    monkeypatch.setattr(server, "graph", graph)
    monkeypatch.setattr(server, "connections", 0)
    return TestClient(server.app)


def test_websocket_origin(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws", headers={"origin": "https://evil.example"}):
            pass


@pytest.mark.parametrize("raw,code", [("x"*8193, 1009), ('{"v":2,"type":"unknown"}', 1008),
                                    ('{"v":2,"type":"health","extra":1}', 1008)])
def test_websocket_invalid_and_oversize(client, raw, code):
    with client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        assert ws.receive_json()["type"] == "status"
        ws.send_text(raw)
        with pytest.raises(WebSocketDisconnect) as error:
            ws.receive_json()
        assert error.value.code == code


def test_websocket_rate_and_connection_cap(client, monkeypatch):
    limiter_class = server.RateLimiter
    monkeypatch.setattr(server, "RateLimiter", lambda: limiter_class(2))
    with client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        ws.receive_json()
        for _ in range(2):
            ws.send_json({"v": 2, "type": "health"})
            assert ws.receive_json()["type"] == "health"
        ws.send_json({"v": 2, "type": "health"})
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
    monkeypatch.setattr(server, "connections", 4)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws", headers={"origin": ORIGIN}):
            pass


def test_websocket_schemas_and_neural_route(client):
    with client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        status = ws.receive_json()
        assert status["synthetic"] is True
        ws.send_json({"v": 2, "type": "reset", "seed": 783, "topology": "real"})
        assert ws.receive_json()["type"] == "status"
        ws.send_json({"v": 2, "type": "observation", "seq": 0, "values": [.2]*20})
        action, activity = ws.receive_json(), ws.receive_json()
        assert 0 <= action["action"] < 14 and action["seq"] == 0
        assert activity["type"] == "neural_activity" and max(activity["values"]) > 0
        ws.send_json({"v": 2, "type": "observation", "seq": 0, "values": [.2]*20})
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


def test_security_headers(client):
    response = client.get("/health", headers={"origin": ORIGIN})
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert "default-src 'none'" in response.headers["content-security-policy"]
    assert "access-control-allow-origin" not in client.get("/health", headers={"origin": "https://evil.example"}).headers


def test_training_cancel(graph, tmp_path, monkeypatch):
    monkeypatch.setattr(trainer, "CHECKPOINTS", tmp_path)
    messages = []
    assert trainer.train(graph, generations=1, population=4, seconds=6, emit=messages.append, cancelled=lambda: True) == ""
    assert json.loads(messages[-1])["status"] == "cancelled"
    assert not list(tmp_path.glob("candidate_*.npz"))


def test_deterministic_evaluation(graph):
    arrays = neural.Controller(graph, 5).arrays()
    a = trainer.episode(graph, arrays, 10000001, "medium", 1)
    b = trainer.episode(graph, arrays, 10000001, "medium", 1)
    assert a["final_hash"] == b["final_hash"]
    assert a["reward"] == b["reward"]
    assert min(trainer.EVAL_SEEDS) > 999999 + 1000 + 20
