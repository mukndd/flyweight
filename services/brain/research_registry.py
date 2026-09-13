"""Local-first research metadata registry.

The registry is intentionally small and boring: SQLite in project-local storage
today, structured around tables that can be mapped to PostgreSQL later.
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
import time
import uuid
from pathlib import Path

from .limits import CHECKPOINTS, ROOT

SCHEMA_VERSION = 1
PROJECT_EPOCH = "2026-09-09"
STATUSES = {
    "training",
    "failed",
    "rejected",
    "promising",
    "validated",
    "certification_failed",
    "promoted",
    "archived",
}


def now_ns():
    return time.time_ns()


def stable_id(prefix):
    return prefix + "_" + uuid.uuid4().hex[:16]


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def decode(value):
    return json.loads(value) if value else {}


def default_db_path():
    return CHECKPOINTS / "research.sqlite"


def validate_db_path(path):
    path = Path(path).resolve()
    temp_root = Path(tempfile.gettempdir()).resolve()
    allowed = path.is_relative_to(ROOT.resolve()) or path.is_relative_to(temp_root)
    if not allowed:
        raise ValueError("Research registry path must stay inside this project")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


class ResearchRegistry:
    def __init__(self, path=None):
        self.path = validate_db_path(path or default_db_path())
        self.con = sqlite3.connect(self.path)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys = ON")
        self.con.execute("PRAGMA journal_mode = WAL")
        self.migrate()

    def close(self):
        self.con.close()

    def migrate(self):
        with self.con:
            self.con.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_info(
                    version INTEGER NOT NULL,
                    applied_ns INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS experiments(
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    created_ns INTEGER NOT NULL,
                    updated_ns INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runs(
                    id TEXT PRIMARY KEY,
                    experiment_id TEXT NOT NULL REFERENCES experiments(id),
                    trainer TEXT NOT NULL,
                    seed INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    started_ns INTEGER NOT NULL,
                    ended_ns INTEGER
                );
                CREATE TABLE IF NOT EXISTS candidates(
                    id TEXT PRIMARY KEY,
                    parent_id TEXT,
                    parent_champion_id TEXT,
                    run_id TEXT REFERENCES runs(id),
                    trainer TEXT NOT NULL,
                    trainer_version TEXT NOT NULL,
                    training_seed INTEGER NOT NULL,
                    graph_condition TEXT NOT NULL,
                    graph_hash TEXT NOT NULL,
                    scenario_version TEXT NOT NULL,
                    reward_version TEXT NOT NULL,
                    generation INTEGER NOT NULL,
                    training_metrics_json TEXT NOT NULL,
                    validation_metrics_json TEXT NOT NULL,
                    checkpoint_hash TEXT NOT NULL,
                    checkpoint_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    reason_json TEXT NOT NULL,
                    created_ns INTEGER NOT NULL,
                    updated_ns INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS champions(
                    id TEXT PRIMARY KEY,
                    candidate_id TEXT NOT NULL REFERENCES candidates(id),
                    checkpoint_id TEXT NOT NULL,
                    checkpoint_hash TEXT NOT NULL,
                    graph_hash TEXT NOT NULL,
                    promoted_ns INTEGER NOT NULL,
                    selection TEXT NOT NULL,
                    evidence_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS checkpoints(
                    id TEXT PRIMARY KEY,
                    candidate_id TEXT,
                    sha256 TEXT NOT NULL,
                    bytes INTEGER NOT NULL,
                    uri TEXT NOT NULL,
                    created_ns INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS evaluations(
                    id TEXT PRIMARY KEY,
                    candidate_id TEXT,
                    champion_id TEXT,
                    suite TEXT NOT NULL,
                    scenario_version TEXT NOT NULL,
                    reward_version TEXT NOT NULL,
                    metrics_json TEXT NOT NULL,
                    rows_json TEXT NOT NULL,
                    created_ns INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ladder_certifications(
                    id TEXT PRIMARY KEY,
                    level_version TEXT NOT NULL,
                    champion_id TEXT,
                    checkpoint_hash TEXT NOT NULL,
                    scenario_suite TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    passed INTEGER NOT NULL,
                    code_commit TEXT NOT NULL,
                    graph_hash TEXT NOT NULL,
                    created_ns INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS topology_conditions(
                    id TEXT PRIMARY KEY,
                    experiment_id TEXT,
                    condition TEXT NOT NULL,
                    graph_hash TEXT NOT NULL,
                    control_hash TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    created_ns INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS daily_reports(
                    id TEXT PRIMARY KEY,
                    project_day INTEGER NOT NULL,
                    report_date TEXT NOT NULL,
                    report_json TEXT NOT NULL,
                    created_ns INTEGER NOT NULL,
                    UNIQUE(project_day, report_date)
                );
                CREATE TABLE IF NOT EXISTS human_matches(
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    champion_id TEXT NOT NULL,
                    match_seed INTEGER NOT NULL,
                    scenario TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    replay_hash TEXT NOT NULL,
                    verified INTEGER NOT NULL,
                    tag TEXT NOT NULL,
                    created_ns INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS leaderboard_entries(
                    id TEXT PRIMARY KEY,
                    human_match_id TEXT NOT NULL REFERENCES human_matches(id),
                    nickname TEXT NOT NULL,
                    metric TEXT NOT NULL,
                    value REAL NOT NULL,
                    created_ns INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS worker_leases(
                    name TEXT PRIMARY KEY,
                    owner TEXT NOT NULL,
                    expires_ns INTEGER NOT NULL,
                    updated_ns INTEGER NOT NULL
                );
                """
            )
            row = self.con.execute("SELECT version FROM schema_info ORDER BY applied_ns DESC LIMIT 1").fetchone()
            if row is None:
                self.con.execute(
                    "INSERT INTO schema_info(version, applied_ns) VALUES(?, ?)", (SCHEMA_VERSION, now_ns())
                )

    def create_experiment(self, kind, title, config, status="planned"):
        ident = stable_id("exp")
        stamp = now_ns()
        with self.con:
            self.con.execute(
                """
                INSERT INTO experiments(id, kind, title, status, config_json, created_ns, updated_ns)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (ident, kind, title[:120], status, encode(config), stamp, stamp),
            )
        return ident

    def update_experiment(self, ident, status):
        with self.con:
            self.con.execute(
                "UPDATE experiments SET status = ?, updated_ns = ? WHERE id = ?", (status, now_ns(), ident)
            )

    def create_run(self, experiment_id, trainer, seed, config, status="running"):
        ident = stable_id("run")
        with self.con:
            self.con.execute(
                """
                INSERT INTO runs(id, experiment_id, trainer, seed, status, config_json, started_ns)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (ident, experiment_id, trainer, int(seed), status, encode(config), now_ns()),
            )
        return ident

    def finish_run(self, ident, status):
        with self.con:
            self.con.execute("UPDATE runs SET status = ?, ended_ns = ? WHERE id = ?", (status, now_ns(), ident))

    def record_candidate(self, **fields):
        status = fields.get("status", "training")
        if status not in STATUSES:
            raise ValueError("Invalid candidate status")
        ident = fields["candidate_id"]
        stamp = now_ns()
        with self.con:
            self.con.execute(
                """
                INSERT INTO candidates(
                    id, parent_id, parent_champion_id, run_id, trainer, trainer_version, training_seed,
                    graph_condition, graph_hash, scenario_version, reward_version, generation,
                    training_metrics_json, validation_metrics_json, checkpoint_hash, checkpoint_id,
                    status, reason_json, created_ns, updated_ns
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ident,
                    fields.get("parent_id"),
                    fields.get("parent_champion_id"),
                    fields.get("run_id"),
                    fields["trainer"],
                    fields["trainer_version"],
                    int(fields["training_seed"]),
                    fields["graph_condition"],
                    fields["graph_hash"],
                    fields["scenario_version"],
                    fields["reward_version"],
                    int(fields["generation"]),
                    encode(fields.get("training_metrics", {})),
                    encode(fields.get("validation_metrics", {})),
                    fields["checkpoint_hash"],
                    fields["checkpoint_id"],
                    status,
                    encode(fields.get("reason", {})),
                    stamp,
                    stamp,
                ),
            )
        return ident

    def update_candidate_status(self, ident, status, reason=None, validation_metrics=None):
        if status not in STATUSES:
            raise ValueError("Invalid candidate status")
        with self.con:
            if validation_metrics is None:
                self.con.execute(
                    "UPDATE candidates SET status = ?, reason_json = ?, updated_ns = ? WHERE id = ?",
                    (status, encode(reason or {}), now_ns(), ident),
                )
            else:
                self.con.execute(
                    """
                    UPDATE candidates
                    SET status = ?, reason_json = ?, updated_ns = ?, validation_metrics_json = ?
                    WHERE id = ?
                    """,
                    (status, encode(reason or {}), now_ns(), encode(validation_metrics), ident),
                )

    def record_evaluation(self, candidate_id, champion_id, suite, scenario_version, reward_version, metrics, rows):
        ident = stable_id("eval")
        with self.con:
            self.con.execute(
                """
                INSERT INTO evaluations(
                    id, candidate_id, champion_id, suite, scenario_version, reward_version,
                    metrics_json, rows_json, created_ns
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ident,
                    candidate_id,
                    champion_id,
                    suite,
                    scenario_version,
                    reward_version,
                    encode(metrics),
                    encode(rows[:300]),
                    now_ns(),
                ),
            )
        return ident

    def record_champion(self, candidate_id, checkpoint_id, checkpoint_hash, graph_hash, evidence, selection):
        ident = stable_id("champion")
        with self.con:
            self.con.execute(
                """
                INSERT INTO champions(
                    id, candidate_id, checkpoint_id, checkpoint_hash, graph_hash, promoted_ns,
                    selection, evidence_json
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (ident, candidate_id, checkpoint_id, checkpoint_hash, graph_hash, now_ns(), selection, encode(evidence)),
            )
        return ident

    def record_checkpoint(self, checkpoint_id, candidate_id, sha256, byte_count, uri):
        with self.con:
            self.con.execute(
                """
                INSERT OR IGNORE INTO checkpoints(id, candidate_id, sha256, bytes, uri, created_ns)
                VALUES(?, ?, ?, ?, ?, ?)
                """,
                (checkpoint_id, candidate_id, sha256, int(byte_count), uri, now_ns()),
            )

    def record_ladder_certification(self, result):
        ident = stable_id("cert")
        with self.con:
            self.con.execute(
                """
                INSERT INTO ladder_certifications(
                    id, level_version, champion_id, checkpoint_hash, scenario_suite, result_json,
                    passed, code_commit, graph_hash, created_ns
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ident,
                    result["level_version"],
                    result.get("champion_id"),
                    result["checkpoint_hash"],
                    result["scenario_suite"],
                    encode(result),
                    1 if result["passed"] else 0,
                    result["code_commit"],
                    result["graph_hash"],
                    now_ns(),
                ),
            )
        return ident

    def record_topology_condition(self, experiment_id, condition, graph_hash, control_hash, config):
        ident = stable_id("topology")
        with self.con:
            self.con.execute(
                """
                INSERT INTO topology_conditions(
                    id, experiment_id, condition, graph_hash, control_hash, config_json, created_ns
                ) VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (ident, experiment_id, condition, graph_hash, control_hash, encode(config), now_ns()),
            )
        return ident

    def record_daily_report(self, project_day, report_date, report):
        ident = stable_id("day")
        with self.con:
            self.con.execute(
                """
                INSERT OR REPLACE INTO daily_reports(id, project_day, report_date, report_json, created_ns)
                VALUES(?, ?, ?, ?, ?)
                """,
                (ident, int(project_day), report_date, encode(report), now_ns()),
            )
        return ident

    def acquire_lease(self, name, owner, ttl_seconds=300):
        stamp = now_ns()
        expires = stamp + int(ttl_seconds * 1_000_000_000)
        with self.con:
            row = self.con.execute("SELECT owner, expires_ns FROM worker_leases WHERE name = ?", (name,)).fetchone()
            if row and int(row["expires_ns"]) > stamp and row["owner"] != owner:
                return False
            self.con.execute(
                """
                INSERT INTO worker_leases(name, owner, expires_ns, updated_ns)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET owner=excluded.owner,
                expires_ns=excluded.expires_ns, updated_ns=excluded.updated_ns
                """,
                (name, owner, expires, stamp),
            )
        return True

    def release_lease(self, name, owner):
        with self.con:
            self.con.execute("DELETE FROM worker_leases WHERE name = ? AND owner = ?", (name, owner))

    def current_champion(self):
        row = self.con.execute("SELECT * FROM champions ORDER BY promoted_ns DESC LIMIT 1").fetchone()
        return dict(row) if row else None

    def latest_candidate(self):
        row = self.con.execute("SELECT * FROM candidates ORDER BY created_ns DESC LIMIT 1").fetchone()
        return self._candidate(row) if row else None

    def best_candidate(self):
        rows = self.con.execute("SELECT * FROM candidates").fetchall()
        parsed = [self._candidate(row) for row in rows]
        parsed.sort(key=lambda item: item["training_metrics"].get("fitness", float("-inf")), reverse=True)
        return parsed[0] if parsed else None

    def overview(self):
        today = self.con.execute("SELECT * FROM daily_reports ORDER BY project_day DESC LIMIT 1").fetchone()
        cert = self.con.execute(
            "SELECT * FROM ladder_certifications WHERE passed = 1 ORDER BY created_ns DESC LIMIT 1"
        ).fetchone()
        running = self.con.execute("SELECT COUNT(*) AS count FROM runs WHERE status = 'running'").fetchone()
        candidate_count = self.con.execute("SELECT COUNT(*) AS count FROM candidates").fetchone()
        champion = self.current_champion()
        return {
            "schema_version": SCHEMA_VERSION,
            "project_epoch": PROJECT_EPOCH,
            "training_status": "running" if running and running["count"] else "idle",
            "current_champion": self._champion(champion) if champion else None,
            "best_ever_candidate": self.best_candidate(),
            "latest_candidate": self.latest_candidate(),
            "certified_level": decode(cert["result_json"]) if cert else None,
            "today": decode(today["report_json"]) if today else None,
            "counts": {"candidates": int(candidate_count["count"] if candidate_count else 0)},
        }

    def lineage(self, limit=80):
        rows = self.con.execute("SELECT * FROM candidates ORDER BY created_ns ASC LIMIT ?", (limit,)).fetchall()
        champions = {
            row["candidate_id"]: self._champion(dict(row))
            for row in self.con.execute("SELECT * FROM champions ORDER BY promoted_ns ASC").fetchall()
        }
        return {"nodes": [self._candidate(row) | {"champion": champions.get(row["id"])} for row in rows]}

    def _candidate(self, row):
        if row is None:
            return None
        row = dict(row)
        return {
            "id": row["id"],
            "parent_id": row["parent_id"],
            "parent_champion_id": row["parent_champion_id"],
            "run_id": row["run_id"],
            "trainer": row["trainer"],
            "trainer_version": row["trainer_version"],
            "training_seed": row["training_seed"],
            "graph_condition": row["graph_condition"],
            "graph_hash": row["graph_hash"],
            "scenario_version": row["scenario_version"],
            "reward_version": row["reward_version"],
            "generation": row["generation"],
            "training_metrics": decode(row["training_metrics_json"]),
            "validation_metrics": decode(row["validation_metrics_json"]),
            "checkpoint_hash": row["checkpoint_hash"],
            "checkpoint_id": row["checkpoint_id"],
            "status": row["status"],
            "reason": decode(row["reason_json"]),
            "created_ns": row["created_ns"],
        }

    def _champion(self, row):
        if row is None:
            return None
        row = dict(row)
        return {
            "id": row["id"],
            "candidate_id": row["candidate_id"],
            "checkpoint_id": row["checkpoint_id"],
            "checkpoint_hash": row["checkpoint_hash"],
            "graph_hash": row["graph_hash"],
            "promoted_ns": row["promoted_ns"],
            "selection": row["selection"],
            "evidence": decode(row["evidence_json"]),
        }
