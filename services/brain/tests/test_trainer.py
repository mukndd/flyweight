import json

import numpy as np
import pytest

from services.brain import checkpoints, trainer
from services.brain.neural import Controller
from services.brain.scenarios import scenarios


def stub_episode(*, win, reward):
    def episode(graph, arrays, seed, difficulty, seconds=12, topology="real", ablate=None, bridge=None):
        return {"reward": reward, "win": win, "failure": None, "damage_dealt": 0, "damage_received": 0,
                "duration": seconds, "blocks": 0, "elapsed_seconds": 0, "mean_brain_ms": 0,
                "reaction_seconds": None, "reaction_samples": 0, "final_hash": "0", "ablated_channel": ablate,
                "seed": seed, "difficulty": difficulty}
    return episode


def isolate(monkeypatch, tmp_path, win=False, reward=1.0):
    monkeypatch.setattr(trainer, "CHECKPOINTS", tmp_path)
    monkeypatch.setattr(trainer, "episode", stub_episode(win=win, reward=reward))
    monkeypatch.setattr(trainer, "save_candidate", lambda g, a, m: checkpoints.save_candidate(g, a, m, tmp_path))
    return tmp_path


def test_resume_state_roundtrip(graph, tmp_path):
    controller = Controller(graph, 1)
    mean = np.concatenate([v.ravel() for v in controller.arrays().values()])
    std = np.full_like(mean, .3)
    trainer.save_resume_state("abc123", graph, mean, std, 5, {"generations": 5}, root=tmp_path)
    loaded_mean, loaded_std, generation, config = trainer.load_resume_state("abc123", graph, root=tmp_path)
    np.testing.assert_allclose(loaded_mean, mean)
    np.testing.assert_allclose(loaded_std, std)
    assert generation == 5
    assert config == {"generations": 5}


def test_resume_state_rejects_mismatched_graph(graph, tmp_path):
    controller = Controller(graph, 1)
    mean = np.concatenate([v.ravel() for v in controller.arrays().values()])
    std = np.full_like(mean, .3)
    trainer.save_resume_state("abc123", graph, mean, std, 3, {}, root=tmp_path)
    other = graph.manifest["graph_hash"]
    graph.manifest = {**graph.manifest, "graph_hash": "different-" + other}
    with pytest.raises(ValueError):
        trainer.load_resume_state("abc123", graph, root=tmp_path)


def test_resume_state_rejects_nonpositive_spread(graph, tmp_path):
    controller = Controller(graph, 1)
    mean = np.concatenate([v.ravel() for v in controller.arrays().values()])
    std = np.zeros_like(mean)
    trainer.save_resume_state("abc123", graph, mean, std, 1, {}, root=tmp_path)
    with pytest.raises(ValueError):
        trainer.load_resume_state("abc123", graph, root=tmp_path)


def test_train_resume_continues_generation_numbering(graph, tmp_path, monkeypatch):
    isolate(monkeypatch, tmp_path)
    messages = []
    trainer.train(graph, seed=1, generations=1, population=4, seconds=6, emit=messages.append, difficulties=["easy"])
    run_id = json.loads(messages[0])["run"]
    resumed = []
    trainer.train(graph, seed=1, generations=1, population=4, seconds=6, emit=resumed.append,
                  difficulties=["easy"], run_id=run_id)
    generations_seen = [json.loads(m)["generation"] for m in resumed if json.loads(m)["status"] == "training"]
    assert generations_seen == [2]
    raw = (tmp_path / f"run_{run_id}.jsonl").read_text().splitlines()
    assert sum(1 for line in raw if json.loads(line).get("run") == run_id or "config" in json.loads(line)) >= 2


def test_train_resume_unknown_run_fails_clearly(graph, tmp_path, monkeypatch):
    isolate(monkeypatch, tmp_path)
    with pytest.raises((ValueError, OSError)):
        trainer.train(graph, seed=1, generations=1, population=4, seconds=6, emit=lambda _: None,
                      difficulties=["easy"], run_id="does-not-exist")


def test_train_rejects_invalid_difficulties(graph, tmp_path, monkeypatch):
    isolate(monkeypatch, tmp_path)
    with pytest.raises(ValueError):
        trainer.train(graph, generations=1, population=4, seconds=6, emit=lambda _: None, difficulties=["extreme"])
    with pytest.raises(ValueError):
        trainer.train(graph, generations=1, population=4, seconds=6, emit=lambda _: None, difficulties=[])


@pytest.mark.parametrize(("elite_fraction", "sigma_init", "sigma_floor", "checkpoint_every"), [
    (0, .4, .04, 1), (1.5, .4, .04, 1), (1 / 3, .4, .5, 1), (1 / 3, .4, .04, 0), (1 / 3, .4, .04, 99),
])
def test_train_rejects_invalid_search_hyperparameters(graph, tmp_path, monkeypatch, elite_fraction, sigma_init, sigma_floor, checkpoint_every):
    isolate(monkeypatch, tmp_path)
    with pytest.raises(ValueError):
        trainer.train(graph, generations=1, population=4, seconds=6, emit=lambda _: None,
                      elite_fraction=elite_fraction, sigma_init=sigma_init, sigma_floor=sigma_floor,
                      checkpoint_every=checkpoint_every)


def test_checkpoint_every_preserves_best_ever_candidate(graph, tmp_path, monkeypatch):
    isolate(monkeypatch, tmp_path)
    messages = []
    trainer.train(graph, seed=2, generations=2, population=4, seconds=6, emit=messages.append,
                  difficulties=["easy"], checkpoint_every=2)
    parsed = [json.loads(m) for m in messages]
    training_msgs = [m for m in parsed if m["status"] == "training"]
    assert training_msgs[0]["best_checkpoint"].startswith("candidate_")
    assert training_msgs[0]["checkpoint"] == training_msgs[0]["best_checkpoint"]
    assert training_msgs[1]["checkpoint"] != ""


def test_presets_are_within_existing_bounds():
    for name, preset in trainer.PRESETS.items():
        assert 1 <= preset["generations"] <= 20, name
        assert 4 <= preset["population"] <= 12, name
        assert 6 <= preset["seconds"] <= 30, name
        assert preset["difficulties"] and set(preset["difficulties"]) <= set(trainer.DIFFICULTIES)
        assert 0 < preset["elite_fraction"] <= 1
        assert 0 < preset["sigma_floor"] <= preset["sigma_init"]
        assert 1 <= preset["checkpoint_every"] <= preset["generations"]


def test_train_still_returns_plain_checkpoint_string_when_cancelled(graph, tmp_path, monkeypatch):
    isolate(monkeypatch, tmp_path)
    assert trainer.train(graph, generations=1, population=4, seconds=6, emit=lambda _: None, cancelled=lambda: True) == ""


def test_counterfactual_transforms_are_bounded_and_targeted():
    obs = [0.1] * 20
    obs[7] = 1
    obs[6] = .4
    assert trainer.apply_counterfactual(obs, "zero_attack")[7] == 0
    removed = trainer.apply_counterfactual(obs, "remove_distance")
    assert removed[0] == removed[1] == removed[6] == 0
    inverted = trainer.apply_counterfactual(obs, "invert_direction")
    assert inverted[0] == pytest.approx(-.1)
    noisy = trainer.apply_counterfactual(obs, "bounded_noise", np.random.default_rng(1))
    assert len(noisy) == 20
    assert all(-1 <= value <= 1 for value in noisy)


def test_summary_reports_action_diversity_and_wilson_interval():
    rows = [
        {"reward": 1, "win": True, "failure": None, "damage_dealt": 20, "damage_received": 5,
         "duration": 6, "final_hash": "a", "action_trace": [1, 1, 5], "action_trace_hash": "x",
         "invalid_unavailable_actions": 0},
        {"reward": -1, "win": False, "failure": None, "damage_dealt": 7, "damage_received": 10,
         "duration": 8, "final_hash": "b", "action_trace": [1, 4, 5], "action_trace_hash": "y",
         "invalid_unavailable_actions": 1},
    ]
    result = trainer.summary(rows)
    assert result["wins"] == 1
    assert result["losses"] == 1
    assert result["unique_final_hashes"] == 2
    assert result["unique_action_traces"] == 2
    assert result["action_distribution"] == {"1": 3, "4": 1, "5": 2}
    assert 0 <= result["win_rate_ci95_wilson"][0] <= result["win_rate_ci95_wilson"][1] <= 1
    assert result["invalid_unavailable_actions"] == 1


def test_scenario_library_has_disjoint_balanced_splits():
    all_items = scenarios()
    ids = [item["id"] for item in all_items]
    assert len(ids) == len(set(ids))
    assert {item["split"] for item in all_items} == {"train", "validation", "test"}
    assert len(scenarios("train")) == 18
    assert len(scenarios("validation")) == 9
    assert len(scenarios("test")) == 18
    assert set(item["id"] for item in scenarios("train")).isdisjoint(item["id"] for item in scenarios("test"))
    assert {"very_close", "far_distance", "corner_pressure", "early_attack"} <= {item["family"] for item in all_items}


def test_robust_fitness_penalizes_bad_scenario_family():
    balanced = [
        {"reward": 10, "win": True, "failure": None, "damage_dealt": 20, "damage_received": 5,
         "duration": 6, "final_hash": "a", "scenario_family": "close"},
        {"reward": 10, "win": True, "failure": None, "damage_dealt": 20, "damage_received": 5,
         "duration": 6, "final_hash": "b", "scenario_family": "far"},
    ]
    lopsided = [
        {"reward": 35, "win": True, "failure": None, "damage_dealt": 40, "damage_received": 0,
         "duration": 6, "final_hash": "c", "scenario_family": "close"},
        {"reward": -20, "win": False, "failure": None, "damage_dealt": 0, "damage_received": 30,
         "duration": 6, "final_hash": "d", "scenario_family": "far"},
    ]
    assert trainer.robust_fitness(balanced) > trainer.robust_fitness(lopsided)
    assert trainer.score_rows(balanced, "mean") == pytest.approx(10)
    assert trainer.score_rows(balanced, "light_robust") == pytest.approx(10)


def test_conditional_action_metrics_detect_state_split():
    rows = [{"profile": "standard", "scenario_family": "close", "trace": [
        {"observation": [0, 0, 0, 0, 0, 0, .05, 1, 0, 1, 1, 0, 0, 0, 4 / 13, 1, 1, 1, 0, 0],
         "selected_action": 4},
        {"observation": [0, 0, 0, 0, 0, 0, .5, 0, 0, 1, 1, 0, 0, 0, 5 / 13, 1, 1, 1, 0, 0],
         "selected_action": 2},
    ]}]
    conditionals = trainer.action_conditionals(rows)
    assert conditionals["opponent_attacking"]["yes"] == {"4": 1}
    assert conditionals["distance"]["far"] == {"2": 1}
    assert trainer.conditional_action_divergence(conditionals)["opponent_attacking"] > 0
