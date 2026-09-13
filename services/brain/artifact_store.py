"""Local object-store abstraction for immutable research artifacts."""
from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path

from .limits import ROOT
from .storage import safe_path

OBJECT_STORE_VERSION = "artifact-store-v1"
MAX_OBJECT_BYTES = 64_000_000


class LocalArtifactStore:
    def __init__(self, root=None):
        self.root = Path(root or (ROOT / "checkpoints" / "artifacts")).resolve()
        temp_root = Path(tempfile.gettempdir()).resolve()
        if not (self.root.is_relative_to(ROOT.resolve()) or self.root.is_relative_to(temp_root)):
            raise ValueError("Artifact store must stay inside project storage")
        self.root.mkdir(parents=True, exist_ok=True)

    def put_file(self, namespace, ident, source):
        bucket = safe_path(self.root, namespace)
        bucket.mkdir(exist_ok=True)
        source = Path(source).resolve()
        if not source.is_file() or source.stat().st_size > MAX_OBJECT_BYTES:
            raise ValueError("Artifact size/type limit")
        target = safe_path(bucket, ident, source.suffix)
        if target.exists():
            raise ValueError("Artifact already exists")
        shutil.copyfile(source, target)
        sha = digest_file(target)
        manifest = {
            "version": OBJECT_STORE_VERSION,
            "uri": f"local:{namespace}/{ident}{source.suffix}",
            "bytes": target.stat().st_size,
            "sha256": sha,
        }
        safe_path(bucket, ident, ".manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return manifest

    def get_manifest(self, namespace, ident):
        bucket = safe_path(self.root, namespace)
        path = safe_path(bucket, ident, ".manifest.json")
        return json.loads(path.read_text(encoding="utf-8"))


def digest_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as file:
        for block in iter(lambda: file.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()
