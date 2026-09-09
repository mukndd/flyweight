from dataclasses import replace

import numpy as np
import pytest

from services.brain import app as server
from services.brain import neural, trainer
from services.brain.config import load_settings
from services.brain.limits import ORIGIN


@pytest.mark.parametrize("values", [
    {"FLYWEIGHT_ENV": "production"},
    {"FLYWEIGHT_BIND_HOST": "0.0.0.0"},
    {"PORT": "8000;exit"},
    {"PORT": "80"},
    {"FLYWEIGHT_PUBLIC_ORIGINS": "https://*.example.com"},
    {"FLYWEIGHT_PUBLIC_ORIGINS": "https://example.com/path"},
    {"FLYWEIGHT_ALLOWED_HOSTS": "*"},
    {"FLYWEIGHT_DATA_DIR": "/unrelated"},
])
def test_configuration_fails_closed(values):
    with pytest.raises(ValueError):
        load_settings(values)


def test_production_configuration():
    s = load_settings({"FLYWEIGHT_ENV": "production", "FLYWEIGHT_BIND_HOST": "0.0.0.0", "PORT": "8080",
                       "FLYWEIGHT_PUBLIC_ORIGINS": "https://demo.example.com",
                       "FLYWEIGHT_ALLOWED_HOSTS": "brain.example.com,healthcheck.railway.app"})
    assert s.production and not s.training_enabled and s.port == 8080
    assert load_settings({}).host == "127.0.0.1"


def test_dev_default_accepts_127_and_localhost_origins():
    # A browser opened via http://localhost:5173 must not be rejected as an
    # untrusted origin merely because it didn't use 127.0.0.1 (regression:
    # this previously caused every WebSocket handshake to 403).
    origins = load_settings({}).origins
    assert "http://127.0.0.1:5173" in origins
    assert "http://localhost:5173" in origins


def test_plain_http_loopback_origins_do_not_require_https():
    s = load_settings({"FLYWEIGHT_PUBLIC_ORIGINS": "http://127.0.0.1:6000,http://localhost:6000"})
    assert set(s.origins) == {"http://127.0.0.1:6000", "http://localhost:6000"}
    with pytest.raises(ValueError):
        load_settings({"FLYWEIGHT_PUBLIC_ORIGINS": "http://example.com:6000"})


def test_public_training_disabled(graph, monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setattr(server, "graph", graph)
    monkeypatch.setattr(server, "SETTINGS", replace(server.SETTINGS, production=True))
    with TestClient(server.app).websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        assert not ws.receive_json()["training_enabled"]
        ws.send_json({"v": 2, "type": "train_start", "seed": 3, "generations": 1, "population": 4, "episode_seconds": 6})
        assert ws.receive_json()["code"] == "training_disabled_in_production"


def test_training_cannot_mutate_fixed_graph(graph, tmp_path, monkeypatch):
    monkeypatch.setattr(trainer, "CHECKPOINTS", tmp_path)
    # Exercise optimizer updates with deterministic fixture episodes; actual bridge is tested separately.
    monkeypatch.setattr(trainer, "episode", lambda *a, **k: {"reward": 2, "win": False, "failure": None, "damage_dealt": 0, "duration": 6})
    from services.brain import checkpoints
    monkeypatch.setattr(trainer, "save_candidate", lambda g, a, m: checkpoints.save_candidate(g, a, m, tmp_path))
    before = [a.copy() for a in (graph.pre, graph.post, graph.counts, graph.signs, graph.matrix()[0].data)]
    trainer.train(graph, generations=1, population=4, seconds=6, emit=lambda _: None)
    for a, b in zip(before, (graph.pre, graph.post, graph.counts, graph.signs, graph.matrix()[0].data), strict=True):
        np.testing.assert_array_equal(a, b)


def test_baselines_have_no_neural_activity(graph):
    for topology in ("rule", "random"):
        c = neural.Controller(graph, topology=topology)
        c.act([.2]*20)
        assert c.activity() == [] and c.last_scores == [] and graph.view(topology)["neurons"] == 0
