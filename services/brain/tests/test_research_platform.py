import json

import pytest

from services.brain import artifact_store, human_challenge, ladder, research_loop, topology_experiments
from services.brain.neural import Controller
from services.brain.research_registry import ResearchRegistry


def test_registry_records_lineage_and_append_only_champions(tmp_path, graph):
    registry = ResearchRegistry(tmp_path / "research.sqlite")
    exp = registry.create_experiment("unit", "Unit experiment", {"seed": 1}, "running")
    run = registry.create_run(exp, "CEMTrainer", 1, {"generations": 1})
    registry.record_candidate(
        candidate_id="candidate_abc",
        parent_id=None,
        parent_champion_id="seed",
        run_id=run,
        trainer="CEMTrainer",
        trainer_version="cem-adapters-v1",
        training_seed=1,
        graph_condition="REAL_CONNECTOME",
        graph_hash=graph.manifest["graph_hash"],
        scenario_version="scenario-library-v1",
        reward_version="combat-v2-reward-1",
        generation=1,
        training_metrics={"fitness": 10},
        validation_metrics={"win_rate": .6},
        checkpoint_hash="a" * 64,
        checkpoint_id="candidate_abc",
        status="validated",
    )
    first = registry.record_champion("candidate_abc", "candidate_abc", "a" * 64, graph.manifest["graph_hash"], {}, "gate")
    second = registry.record_champion("candidate_abc", "candidate_abc", "a" * 64, graph.manifest["graph_hash"], {}, "gate")
    assert first != second
    lineage = registry.lineage()
    assert lineage["nodes"][0]["id"] == "candidate_abc"
    assert registry.overview()["best_ever_candidate"]["training_metrics"]["fitness"] == 10
    assert registry.con.execute("SELECT COUNT(*) AS count FROM champions").fetchone()["count"] == 2
    registry.close()


def test_registry_lease_blocks_other_owner(tmp_path):
    registry = ResearchRegistry(tmp_path / "research.sqlite")
    assert registry.acquire_lease("research-loop", "owner-a", ttl_seconds=60)
    assert not registry.acquire_lease("research-loop", "owner-b", ttl_seconds=60)
    assert registry.acquire_lease("research-loop", "owner-a", ttl_seconds=60)
    registry.release_lease("research-loop", "owner-a")
    assert registry.acquire_lease("research-loop", "owner-b", ttl_seconds=60)
    registry.close()


def stub_episode(graph, arrays, seed, difficulty, seconds=12, topology="real", ablate=None, bridge=None, profile="standard"):
    return {
        "reward": 10,
        "win": True,
        "failure": None,
        "damage_dealt": 70,
        "damage_received": 20,
        "damage_differential": 50,
        "duration": seconds,
        "blocks": 1,
        "elapsed_seconds": 0,
        "mean_brain_ms": 0,
        "reaction_seconds": .2,
        "reaction_samples": 1,
        "final_hash": hex(seed % 2**32)[2:].zfill(8),
        "final_dynamics_hash": str(seed),
        "action_trace_hash": str(seed),
        "action_trace": [1, 5, 4],
        "invalid_unavailable_actions": 0,
        "difficulty": difficulty,
        "profile": profile,
    }


def test_ladder_manifest_certification_and_calibration(monkeypatch, graph):
    monkeypatch.setattr(ladder, "episode", stub_episode)
    arrays = Controller(graph, 1).arrays()
    manifest = ladder.ladder_manifest()
    assert manifest["version"] == "combat-ladder-v1"
    assert len(manifest["levels"]) == 10
    result = ladder.evaluate_level(graph, arrays, 1, "a" * 64, matches=12)
    assert result["level_version"] == "L01-v1"
    assert result["passed"] is True
    progress = ladder.evaluate_level(graph, arrays, 1, "a" * 64, matches=4)
    assert progress["passed"] is False
    calibration = ladder.calibrate_ladder(graph, arrays, matches_per_level=2)
    assert calibration["records"][0]["level"] == 1


def test_topology_control_conditions_are_complete(graph):
    config = topology_experiments.fair_config(seed=4, generations=1, population=4, seconds=6, independent_runs=2)
    records = topology_experiments.condition_records(graph, config)
    assert topology_experiments.validate_condition_records(records)
    names = {record["condition"] for record in records}
    assert {"REAL_CONNECTOME", "DEGREE_PRESERVING_RANDOMIZED", "MATCHED_RANDOM_RECURRENT"} <= names
    real = next(record for record in records if record["condition"] == "REAL_CONNECTOME")
    degree = next(record for record in records if record["condition"] == "DEGREE_PRESERVING_RANDOMIZED")
    assert real["edge_count"] == degree["edge_count"]


def test_daily_report_uses_recorded_metrics(tmp_path, graph):
    registry = ResearchRegistry(tmp_path / "research.sqlite")
    report = research_loop.generate_daily_report(registry, graph, date="2026-09-14")
    assert report["day"] >= 1
    assert report["candidates_evaluated"] == 0
    assert registry.overview()["today"]["date"] == "2026-09-14"
    registry.close()


def test_human_challenge_requires_verified_replay_and_bounds():
    session = human_challenge.create_session("champion_1", "a" * 64, seed=123)
    replay = {
        "v": 2,
        "controlMode": "human",
        "seed": 123,
        "checkpointHash": "a" * 64,
        "claimed": "I won",
    }

    def verifier(_text):
        return {"winner": 0, "duration": 12.5, "damage": [100, 10], "checkpointHash": "a" * 64}

    result = human_challenge.verified_match_result(session, json.dumps(replay), verify=verifier)
    assert result["result"] == "human_win"
    entries = human_challenge.leaderboard_values(result, "Ada_1")
    assert {entry["metric"] for entry in entries} == human_challenge.METRICS
    with pytest.raises(ValueError):
        human_challenge.leaderboard_values(result, "../bad")
    bad = dict(replay)
    bad["seed"] = 999
    with pytest.raises(ValueError):
        human_challenge.verified_match_result(session, json.dumps(bad), verify=verifier)


def test_local_artifact_store_is_hash_verified_and_immutable(tmp_path):
    store = artifact_store.LocalArtifactStore(tmp_path / "objects")
    source = tmp_path / "result.json"
    source.write_text('{"ok":true}', encoding="utf-8")
    manifest = store.put_file("reports", "day_1", source)
    assert manifest["sha256"] == artifact_store.digest_file(tmp_path / "objects" / "reports" / "day_1.json")
    assert store.get_manifest("reports", "day_1")["uri"] == "local:reports/day_1.json"
    with pytest.raises(ValueError):
        store.put_file("reports", "day_1", source)
