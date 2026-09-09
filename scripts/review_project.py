"""Project-only file size and common secret-pattern inspection; never reads personal files."""
import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {".git", ".venv", "node_modules", ".cache", ".runtime", "dist", "test-results", "logs",
            ".pytest_cache", ".ruff_cache", "__pycache__", "data", "checkpoints", "replays"}
PATTERNS = {
    "private-key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?" + r"PRIVATE KEY-----"),
    "github-token": re.compile(r"(?:gh[pousr]_" + r"[A-Za-z0-9]{30,}|github_pat_" + r"[A-Za-z0-9_]{50,})"),
    "aws-key": re.compile(r"(?:AKIA|ASIA)" + r"[A-Z0-9]{16}"),
    "slack-token": re.compile(r"xox[baprs]-" + r"[A-Za-z0-9-]{20,}"),
    "api-key": re.compile(r"sk-(?:proj-)?" + r"[A-Za-z0-9_-]{32,}")
}


def files():
    for directory, dirs, names in os.walk(ROOT, followlinks=False):
        dirs[:] = [d for d in dirs if not (Path(directory) / d).is_symlink() and
                   not (Path(directory) / d).is_junction()]
        for name in names:
            p = Path(directory) / name
            if not p.is_symlink():
                yield p


def scan():
    findings, scanned, ignored_binary = [], 0, 0
    for p in files():
        relative = p.relative_to(ROOT)
        if any(part in EXCLUDED for part in relative.parts):
            continue
        if p.stat().st_size > 5_000_000:
            findings.append({"file": str(relative), "issue": "oversized authored file requires review"})
            continue
        raw = p.read_bytes()
        if b"\0" in raw[:8192]:
            ignored_binary += 1
            continue
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            ignored_binary += 1
            continue
        scanned += 1
        for line, value in enumerate(text.splitlines(), 1):
            for label, pattern in PATTERNS.items():
                if pattern.search(value):
                    findings.append({"file": relative.as_posix(), "line": line, "kind": label})
    report = {"utc": datetime.now(timezone.utc).isoformat(), "scanned_text_files": scanned,
              "skipped_binary_files": ignored_binary, "exclusions": sorted(EXCLUDED),
              "limitations": "Pattern scan is not proof of absence; ignores generated assets, caches and third-party packages.",
              "findings": findings}
    (ROOT / "logs").mkdir(exist_ok=True)
    (ROOT / "logs/secret-scan.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return bool(findings)


def sizes():
    groups = {}
    for p in files():
        relative = p.relative_to(ROOT)
        group = relative.parts[0] if len(relative.parts) > 1 else "root-source"
        groups[group] = groups.get(group, 0) + p.stat().st_size
    result = {"utc": datetime.now(timezone.utc).isoformat(), "bytes": groups, "total_bytes": sum(groups.values()),
              "limit_bytes": 5_000_000_000, "within_target": sum(groups.values()) < 5_000_000_000}
    (ROOT / "logs").mkdir(exist_ok=True)
    (ROOT / "logs/size-report.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return not result["within_target"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["secrets", "size"])
    args = parser.parse_args()
    raise SystemExit(scan() if args.command == "secrets" else sizes())
