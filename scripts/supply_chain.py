"""Read-only official metadata, cross-platform wheel locks, inventories and GHSA snapshot."""
import argparse
import base64
import hashlib
import importlib.metadata as md
import json
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from scripts.download_data import HOSTS, get

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache/review"
DOCS = ROOT / "docs"
HOSTS.add("codeload.github.com")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def fetched(url, cap=4_000_000):
    CACHE.mkdir(parents=True, exist_ok=True)
    key = sha(url.encode())
    path, meta = CACHE / key, CACHE / (key + ".json")
    if path.exists() and meta.exists():
        record = json.loads(meta.read_text())
        data = path.read_bytes()
        if sha(data) != record["sha256"] or len(data) != record["bytes"]:
            raise ValueError("Metadata cache mismatch")
        return data, record
    data = get(url, cap)
    record = {"url": url, "bytes": len(data), "sha256": sha(data), "downloaded_utc": datetime.now(timezone.utc).isoformat()}
    path.write_bytes(data)
    meta.write_text(json.dumps(record, indent=2))
    return data, record


def inventory():
    downloads, packages = [], []
    installed = {canonicalize_name(d.metadata["Name"]): d for d in md.distributions(path=[str(ROOT / ".venv/Lib/site-packages")])}
    if os.name != "nt":
        installed = {canonicalize_name(d.metadata["Name"]): d for d in md.distributions()}
    runtime = set()
    def visit(name):
        name = canonicalize_name(name)
        if name in runtime or name not in installed:
            return
        runtime.add(name)
        for value in installed[name].requires or []:
            req = Requirement(value)
            if req.marker is None or any(req.marker.evaluate({"sys_platform": platform, "extra": ""}) for platform in ("win32", "linux")):
                visit(req.name)
    for line in (ROOT / "requirements.txt").read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            visit(Requirement(line).name)
    wheel_locks = {}
    for name, dist in sorted(installed.items()):
        data, record = fetched(f"https://pypi.org/pypi/{name}/{dist.version}/json")
        downloads.append(record)
        payload = json.loads(data)
        wheels = [u for u in payload["urls"] if u["packagetype"] == "bdist_wheel" and not u["yanked"]]
        if not wheels:
            raise ValueError("No reviewed binary wheels: " + name)
        hashes = sorted({u["digests"]["sha256"] for u in wheels})
        wheel_locks[name] = name + "==" + dist.version + " \\\n" + " \\\n".join("    --hash=sha256:" + h for h in hashes)
        info = payload["info"]
        packages.append({"ecosystem": "PyPI", "name": name, "version": dist.version, "scope": "runtime" if name in runtime else "development",
                         "license": info.get("license_expression") or (info.get("license") or "")[:200],
                         "source": info.get("project_urls"), "wheel_hashes": hashes})
    for name, names in [("requirements.lock", runtime), ("requirements-dev.lock", set(installed))]:
        (ROOT / name).write_text("# Exact versions and official wheel SHA-256 hashes; source distributions prohibited.\n" +
                                 "\n".join(wheel_locks[n] for n in sorted(names)) + "\n")
    reports = sorted((ROOT / "logs").glob("*install*.json")) + sorted((ROOT / "logs").glob("pip-upgrade*.json"))
    bodies = {}
    for p in (ROOT / ".cache/pip").rglob("*.body"):
        if p.stat().st_size < 250_000_000:
            bodies[sha(p.read_bytes())] = p.stat().st_size
    for report in reports:
        for item in json.loads(report.read_text()).get("install", []):
            info = item["download_info"]
            checksum = info["archive_info"]["hashes"]["sha256"]
            downloads.append({"url": info["url"], "sha256": checksum, "bytes": bodies.get(checksum),
                              "installed_name": item["metadata"]["name"], "version": item["metadata"]["version"],
                              "downloaded_utc": datetime.fromtimestamp(report.stat().st_mtime, timezone.utc).isoformat(),
                              "date_basis": "installation report modification time"})
    lock = json.loads((ROOT / "package-lock.json").read_text())
    for location, info in lock["packages"].items():
        if not location:
            continue
        name = location.split("node_modules/")[-1]
        item = {"ecosystem": "npm", "name": name, "version": info["version"], "scope": "development" if info.get("dev") else "runtime",
                "license": info.get("license"), "url": info.get("resolved"), "integrity": info.get("integrity"), "installed": (ROOT / location).exists(),
                "has_install_script": info.get("hasInstallScript", False)}
        packages.append(item)
        integrity = info.get("integrity", "")
        if integrity.startswith("sha512-"):
            hex_digest = base64.b64decode(integrity[7:]).hex()
            p = ROOT / ".cache/npm/_cacache/content-v2/sha512" / hex_digest[:2] / hex_digest[2:4] / hex_digest[4:]
            if p.exists():
                data = p.read_bytes()
                if hashlib.sha512(data).hexdigest() != hex_digest:
                    raise ValueError("npm cache integrity")
                downloads.append({"url": info.get("resolved"), "bytes": len(data), "sha256": sha(data),
                                  "downloaded_utc": datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat(), "date_basis": "cache file modification time"})
    for meta in CACHE.glob("*.json"):
        record = json.loads(meta.read_text())
        if "url" in record and record not in downloads:
            downloads.append(record)
    (DOCS / "dependency-inventory.json").write_text(json.dumps({"format": "flyweight-inventory-v1", "generated_utc": datetime.now(timezone.utc).isoformat(),
        "packages": packages, "downloads": downloads, "limitations": "Inventories registry tarballs/wheels and saved review metadata. Package-manager index/advisory response caches are not individually mapped to original URL. See source-lock.json for research downloads."}, indent=2))
    print(json.dumps({"packages": len(packages), "downloads": len(downloads), "runtime_python_packages": len(runtime),
                      "download_records_missing_bytes": sum(d.get("bytes") is None for d in downloads)}))


def advisories():
    data, head = fetched("https://api.github.com/repos/github/advisory-database/commits/main")
    commit = json.loads(data)["sha"]
    if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
        raise ValueError("Advisory commit")
    data, archive_record = fetched("https://codeload.github.com/github/advisory-database/zip/" + commit, 200_000_000)
    path = CACHE / sha(archive_record["url"].encode())
    lock = json.loads((ROOT / "package-lock.json").read_text())
    names = {location.split("node_modules/")[-1] for location in lock["packages"] if location}
    matches = []
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if len(members) > 300_000 or sum(m.file_size for m in members) > 1_000_000_000:
            raise ValueError("Advisory archive quota")
        for member in members:
            if not member.filename.endswith(".json") or "/advisories/" not in member.filename:
                continue
            if member.file_size > 2_000_000 or member.file_size > max(1, member.compress_size) * 500:
                raise ValueError("Advisory member quota")
            item = json.loads(archive.read(member))
            if item.get("withdrawn"):
                continue
            for affected in item.get("affected", []):
                package = affected.get("package", {})
                if package.get("ecosystem") == "npm" and package.get("name") in names:
                    matches.append({"id": item["id"], "name": package["name"], "summary": item.get("summary"),
                                    "severity": item.get("database_specific", {}).get("severity"),
                                    "ranges": affected.get("ranges", []), "versions": affected.get("versions", []),
                                    "url": "https://github.com/advisories/" + item["id"]})
    result = {"commit": commit, "snapshot": archive_record, "matching_package_advisories": matches}
    (ROOT / "logs/npm-advisory-candidates.json").write_text(json.dumps(result, indent=2))
    print(json.dumps({"commit": commit, "archive_bytes": len(data), "candidates": len(matches)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["inventory", "advisories"])
    args = parser.parse_args()
    inventory() if args.command == "inventory" else advisories()
