import json
from types import SimpleNamespace

import pytest

from services.brain import (
    artifact_store,
    burn_in,
    daily_evaluator,
    human_challenge,
    ladder,
    postgres_registry,
    research_loop,
    topology_batch,
    topology_experiments,
)
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


def test_registry_transactional_promotion_daily_idempotency_and_recovery(tmp_path, graph):
    registry = ResearchRegistry(tmp_path / "research.sqlite")
    exp = registry.create_experiment("unit", "Unit experiment", {"seed": 1}, "running")
    run = registry.create_run(exp, "CEMTrainer", 1, {"generations": 1})
    registry.record_candidate(
        candidate_id="candidate_tx",
        parent_id=None,
        parent_champion_id=None,
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
        validation_metrics={"win_rate": .7},
        checkpoint_hash="b" * 64,
        checkpoint_id="candidate_tx",
        status="validated",
    )
    champion = registry.promote_transactional(
        "candidate_tx",
        "candidate_tx",
        "b" * 64,
        graph.manifest["graph_hash"],
        {"suite": "unit"},
    )
    assert registry.current_champion()["id"] == champion
    first_report = registry.record_daily_report(1, "2026-09-14", {"day": 1, "value": "first"})
    second_report = registry.record_daily_report(1, "2026-09-14", {"day": 1, "value": "second"})
    assert first_report == second_report
    assert registry.daily_reports()["reports"][0]["value"] == "first"
    recovered = registry.recover_interrupted_runs(older_than_ns=0)
    assert recovered == [run]
    assert registry.con.execute("SELECT status FROM runs WHERE id = ?", (run,)).fetchone()["status"] == "failed"
    registry.close()


def test_registry_lease_blocks_other_owner(tmp_path):
    registry = ResearchRegistry(tmp_path / "research.sqlite")
    assert registry.acquire_lease("research-loop", "owner-a", ttl_seconds=60)
    assert not registry.acquire_lease("research-loop", "owner-b", ttl_seconds=60)
    assert registry.acquire_lease("research-loop", "owner-a", ttl_seconds=60)
    registry.release_lease("research-loop", "owner-a")
    assert registry.acquire_lease("research-loop", "owner-b", ttl_seconds=60)
    registry.close()


def test_registry_env_path_stays_bounded(tmp_path, monkeypatch):
    db = tmp_path / "research.sqlite"
    monkeypatch.setenv("FLYWEIGHT_RESEARCH_DB", str(db))
    registry = ResearchRegistry()
    try:
        assert registry.path == db
    finally:
        registry.close()
    monkeypatch.setenv("FLYWEIGHT_RESEARCH_DB", "C:/unrelated/research.sqlite")
    with pytest.raises(ValueError):
        ResearchRegistry()


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


def test_s3_artifact_store_signs_content_addressed_objects_without_network():
    calls = []

    def transport(method, url, body, headers):
        calls.append((method, url, body, headers))
        return b'{"ok":true}' if method == "PUT" else b"payload"

    store = artifact_store.S3ArtifactStore(
        "https://r2.example.com",
        "flyweight-artifacts",
        "access",
        "secret",
        transport=transport,
    )
    manifest = store.put_bytes("daily_reports", b"payload", ".json", {"day": 1})
    assert manifest["sha256"] == artifact_store.hashlib.sha256(b"payload").hexdigest()
    assert manifest["storage_key"].startswith("daily_reports/")
    assert calls[0][0] == "PUT"
    assert calls[0][1].startswith("https://r2.example.com/flyweight-artifacts/daily_reports/")
    assert "authorization" in calls[0][3]
    assert store.get_bytes(manifest["storage_key"], manifest["sha256"]) == b"payload"
    with pytest.raises(ValueError):
        store.get_bytes("../bad", manifest["sha256"])


def test_postgres_schema_and_promotion_use_parameterized_transaction():
    class FakeConnection:
        def __init__(self):
            self.calls = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, params=None):
            self.calls.append((sql, params))

    fake = FakeConnection()
    registry = postgres_registry.PostgresRegistry(connection=fake)
    registry.apply_migrations()
    registry.promote_transactional("champion_1", "candidate_1", "checkpoint_1", "c" * 64, "g" * 64, '{"ok":true}')
    assert "CREATE TABLE IF NOT EXISTS experiments" in fake.calls[0][0]
    assert "canonical_champion" in fake.calls[1][0]
    assert fake.calls[1][1][-1] == "champion_1"
    summary = postgres_registry.schema_summary()
    assert {"experiments", "champions", "artifact_metadata"} <= set(summary["tables"])
    with pytest.raises(ValueError):
        postgres_registry.validate_database_url("https://example.com/db")


def test_daily_evaluator_is_idempotent_and_records_summary(tmp_path, graph, monkeypatch):
    monkeypatch.setattr(daily_evaluator, "Graph", lambda synthetic=False: graph)
    monkeypatch.setattr(
        daily_evaluator,
        "evaluate_level",
        lambda g, a, level, h, matches, champion_id=None: {
            "ladder_version": "combat-ladder-v1",
            "level": level,
            "level_version": "L01-v1",
            "champion_id": champion_id,
            "checkpoint_hash": h,
            "scenario_suite": "combat-ladder-v1:L01-v1",
            "matches": matches,
            "wins": matches,
            "win_rate": 1.0,
            "wilson_95_ci": [1.0, 1.0],
            "damage_differential": 40,
            "scenario_family_performance": {},
            "responsiveness_sanity_checks": {"unique_action_traces": 2},
            "exploit_anomaly_flags": [],
            "code_commit": "unit",
            "graph_hash": g.manifest["graph_hash"],
            "passed": True,
            "criterion": {},
            "rows": [],
        },
    )
    monkeypatch.setattr(
        daily_evaluator,
        "current_champion_checkpoint",
        lambda g: ("seed-initialized", "seed-initialized", Controller(g, 783).arrays()),
    )
    args = SimpleNamespace(
        production=False,
        synthetic=True,
        db=tmp_path / "research.sqlite",
        date="2026-09-14",
        force=False,
        matches=4,
        max_levels=1,
        lease_seconds=60,
    )
    first = daily_evaluator.evaluate_daily(args)
    second = daily_evaluator.evaluate_daily(args)
    assert first["status"] == "complete"
    assert second["status"] == "already_exists"
    assert "Certified Level 1" in first["summary"]


def test_burn_in_recovers_lease_and_detects_dashboard_state(tmp_path, graph, monkeypatch):
    monkeypatch.setattr(burn_in, "Graph", lambda synthetic=False: graph)

    def fake_once(args):
        registry = ResearchRegistry(args.db)
        try:
            exp = registry.create_experiment("unit", "Unit", {}, "complete")
            run = registry.create_run(exp, "CEMTrainer", 1, {}, status="complete")
            registry.record_candidate(
                candidate_id="candidate_burn",
                parent_id=None,
                parent_champion_id=None,
                run_id=run,
                trainer="CEMTrainer",
                trainer_version="cem-adapters-v1",
                training_seed=1,
                graph_condition="REAL_CONNECTOME",
                graph_hash=graph.manifest["graph_hash"],
                scenario_version="scenario-library-v1",
                reward_version="combat-v2-reward-1",
                generation=1,
                training_metrics={"fitness": 1},
                validation_metrics={},
                checkpoint_hash="d" * 64,
                checkpoint_id="candidate_burn",
                status="validated",
            )
        finally:
            registry.close()
        return {"status": "complete"}

    monkeypatch.setattr(burn_in, "run_once", fake_once)
    seen = {"count": 0}

    def fake_daily(args):
        seen["count"] += 1
        registry = ResearchRegistry(args.db)
        try:
            registry.record_daily_report(1, args.date, {"day": 1, "date": args.date})
        finally:
            registry.close()
        return {"status": "complete" if seen["count"] == 1 else "already_exists"}

    monkeypatch.setattr(burn_in, "evaluate_daily", fake_daily)
    result = burn_in.run_burn_in(
        SimpleNamespace(synthetic=True, db=tmp_path / "research.sqlite", seed=1, date="2026-09-14")
    )
    assert result["status"] == "complete"
    assert result["stale_lease_recovered"] is True
    assert result["daily_second"] == "already_exists"
    assert result["dashboard_has_state"] is True


def test_topology_batch_records_all_conditions_without_claims(tmp_path, graph, monkeypatch):
    checkpoint_dir = tmp_path / "checkpoints"
    checkpoint_dir.mkdir()
    counter = {"value": 0}

    class FakeTrainer:
        version = "cem-adapters-v1"

        def __init__(self, graph, config, emit=lambda _line: None):
            self.graph = graph
            self.config = config
            self.emit = emit

        def setup(self):
            return {}

        def train_step(self):
            counter["value"] += 1
            ident = f"candidate_batch_{counter['value']:02d}"
            (checkpoint_dir / f"{ident}.npz").write_bytes(b"npz")
            self.emit(json.dumps({"type": "train_progress", "best_training_fitness": 3.0, "generation": 1}))
            return ident

    def fake_load_candidate(graph, ident):
        return Controller(graph, 1).arrays(), {"generation": 1, "reward": 3.0, "sha256": "f" * 64}

    def fake_run_scenarios(_graph, _arrays, heldout, _seconds, topology="real"):
        return [
            {
                "reward": 1.0,
                "win": index % 2 == 0,
                "failure": None,
                "damage_dealt": 20,
                "damage_received": 10,
                "damage_differential": 10,
                "duration": 6,
                "final_hash": f"{topology}-{index}",
                "final_dynamics_hash": f"{topology}-{index}",
                "action_trace_hash": f"{topology}-{index}",
                "action_trace": [1, 5],
                "invalid_unavailable_actions": 0,
            }
            for index, _item in enumerate(heldout)
        ]

    monkeypatch.setattr(topology_batch, "Graph", lambda synthetic=False: graph)
    monkeypatch.setattr(topology_batch, "CEMTrainer", FakeTrainer)
    monkeypatch.setattr(topology_batch, "load_candidate", fake_load_candidate)
    monkeypatch.setattr(topology_batch, "run_scenarios", fake_run_scenarios)
    monkeypatch.setattr(topology_batch, "CHECKPOINTS", checkpoint_dir)
    result = topology_batch.run_batch(
        SimpleNamespace(
            production=False,
            synthetic=True,
            db=tmp_path / "research.sqlite",
            base_seed=9401,
            seeds="9401,9402",
            generations=1,
            population=4,
            seconds=6,
            heldout_matches=2,
            project_day=1,
            report_date="2026-09-14",
        )
    )
    registry = ResearchRegistry(tmp_path / "research.sqlite")
    try:
        status = registry.topology_status()
    finally:
        registry.close()
    assert result["claim_boundary"].startswith("Do not infer")
    assert set(result["conditions"]) >= {
        "REAL_CONNECTOME",
        "DEGREE_PRESERVING_RANDOMIZED",
        "WEIGHT_SHUFFLED",
        "MATCHED_RANDOM_RECURRENT",
        "DIRECT_BASELINE",
        "RULE_BASELINE",
        "RANDOM_ACTION_BASELINE",
    }
    assert result["conditions"]["DIRECT_BASELINE"]["status"] == "planned_interface_only"
    assert len(status["conditions"]) == len(topology_experiments.CONDITIONS)
    assert len(status["comparisons"]) == 13
