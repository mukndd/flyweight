"""Anonymous human challenge sessions and leaderboard validation."""
from __future__ import annotations

import json
import re
import shutil
import subprocess  # nosec B404 -- fixed local verifier, no shell or client command
import sys
import time
import uuid

from .limits import ROOT

SESSION_VERSION = "human-challenge-v1"
NICKNAME = re.compile(r"^[a-zA-Z0-9 _.-]{1,24}$")
METRICS = {"fastest_win", "lowest_damage_received", "highest_damage_differential"}


def create_session(champion_id, checkpoint_hash, seed=None):
    if not isinstance(champion_id, str) or not 1 <= len(champion_id) <= 80:
        raise ValueError("Invalid champion id")
    if not isinstance(checkpoint_hash, str) or not re.fullmatch(r"[a-f0-9]{64}|seed-initialized", checkpoint_hash):
        raise ValueError("Invalid checkpoint hash")
    seed = int(seed if seed is not None else 8_300_000 + uuid.uuid4().int % 100_000)
    if not 0 <= seed <= 2**32 - 1:
        raise ValueError("Invalid match seed")
    return {
        "version": SESSION_VERSION,
        "session_id": "human_" + uuid.uuid4().hex[:16],
        "champion_id": champion_id,
        "checkpoint_hash": checkpoint_hash,
        "match_seed": seed,
        "scenario": "standard",
        "tag": "HUMAN_EXHIBITION",
        "created_ns": time.time_ns(),
    }


def validate_nickname(value):
    if value == "":
        return "anonymous"
    if not isinstance(value, str) or not NICKNAME.fullmatch(value) or value.strip() != value:
        raise ValueError("Invalid leaderboard nickname")
    return value


def verify_replay_text(replay_text):
    if not isinstance(replay_text, str) or len(replay_text.encode("utf-8")) > 1_000_000:
        raise ValueError("Replay size limit")
    verifier = ROOT / "dist" / "sim" / "sim" / "verify_replay.js"
    if not verifier.exists():
        raise ValueError("Compile simulation verifier first")
    node = shutil.which("node")
    if not node:
        raise ValueError("Node required for replay verification")
    options = {}
    if sys.platform == "win32":
        options["creationflags"] = subprocess.CREATE_NO_WINDOW
    proc = subprocess.run(
        [node, str(verifier)],
        cwd=ROOT,
        input=replay_text + "\n",
        text=True,
        capture_output=True,
        timeout=5,
        check=False,
        **options,
    )  # nosec B603 -- fixed executable path and fixed local script
    if proc.returncode != 0:
        raise ValueError("Replay verification failed")
    result = json.loads(proc.stdout)
    if not result.get("ok"):
        raise ValueError("Replay verification failed")
    return result


def verified_match_result(session, replay_text, verify=verify_replay_text):
    replay = json.loads(replay_text)
    verified = verify(replay_text)
    if replay.get("v") != 2 or replay.get("controlMode") != "human":
        raise ValueError("Human challenge requires a v2 human replay")
    if replay.get("seed") != session["match_seed"] or replay.get("checkpointHash") != session["checkpoint_hash"]:
        raise ValueError("Replay does not match issued session")
    won = verified["winner"] == 0
    damage_dealt = float(verified["damage"][0])
    damage_received = float(verified["damage"][1])
    return {
        "session_id": session["session_id"],
        "champion_id": session["champion_id"],
        "match_seed": session["match_seed"],
        "scenario": session["scenario"],
        "result": "human_win" if won else "fly_win" if verified["winner"] == 1 else "draw",
        "damage_dealt": damage_dealt,
        "damage_received": damage_received,
        "damage_differential": damage_dealt - damage_received,
        "duration": float(verified["duration"]),
        "replay_hash": digest_text(replay_text),
        "tag": "HUMAN_EXHIBITION",
    }


def digest_text(value):
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def leaderboard_values(match_result, nickname):
    nickname = validate_nickname(nickname)
    if match_result["result"] != "human_win":
        return []
    return [
        {"nickname": nickname, "metric": "fastest_win", "value": float(match_result["duration"])},
        {"nickname": nickname, "metric": "lowest_damage_received", "value": float(match_result["damage_received"])},
        {
            "nickname": nickname,
            "metric": "highest_damage_differential",
            "value": float(match_result["damage_differential"]),
        },
    ]


def validate_metric(metric):
    if metric not in METRICS:
        raise ValueError("Unknown leaderboard metric")
    return metric
