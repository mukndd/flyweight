"""Local object-store abstraction for immutable research artifacts."""
from __future__ import annotations

import hashlib
import hmac
import json
import shutil
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

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

    def get_file(self, namespace, ident, suffix, expected_hash, max_bytes=MAX_OBJECT_BYTES):
        bucket = safe_path(self.root, namespace)
        path = safe_path(bucket, ident, suffix)
        if not path.is_file() or path.stat().st_size > max_bytes:
            raise ValueError("Artifact size/type limit")
        if digest_file(path) != expected_hash:
            raise ValueError("Artifact hash mismatch")
        return path


class S3ArtifactStore:
    """Small S3-compatible object store for Cloudflare R2.

    Uses path-style requests and AWS SigV4. Tests can inject a transport to
    avoid live network access.
    """

    def __init__(self, endpoint, bucket, access_key_id, secret_access_key, region="auto", transport=None):
        parsed = urlparse(endpoint)
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("S3 endpoint must be a clean HTTPS URL")
        if not bucket or not bucket.replace("-", "").replace("_", "").isalnum():
            raise ValueError("Invalid S3 bucket")
        if not access_key_id or not secret_access_key:
            raise ValueError("S3 credentials required")
        self.endpoint = endpoint.rstrip("/")
        self.bucket = bucket
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.region = region
        self.transport = transport or default_transport

    def key_for_bytes(self, artifact_type, payload, suffix):
        if not artifact_type.replace("-", "").replace("_", "").isalnum() or suffix and not suffix.startswith("."):
            raise ValueError("Invalid artifact key components")
        sha = hashlib.sha256(payload).hexdigest()
        return f"{artifact_type}/{sha[:2]}/{sha}{suffix}"

    def put_bytes(self, artifact_type, payload, suffix="", metadata=None):
        if not isinstance(payload, bytes) or not 0 < len(payload) <= MAX_OBJECT_BYTES:
            raise ValueError("Artifact bytes limit")
        key = self.key_for_bytes(artifact_type, payload, suffix)
        sha = hashlib.sha256(payload).hexdigest()
        self._request("PUT", key, payload, {"x-amz-meta-sha256": sha})
        manifest = {
            "version": OBJECT_STORE_VERSION,
            "backend": "s3",
            "artifact_type": artifact_type,
            "storage_key": key,
            "bytes": len(payload),
            "sha256": sha,
            "created_ns": time.time_ns(),
            "metadata": metadata or {},
        }
        self._request(
            "PUT",
            key + ".manifest.json",
            json.dumps(manifest, sort_keys=True, allow_nan=False).encode("utf-8"),
            {"content-type": "application/json"},
        )
        return manifest

    def get_bytes(self, key, expected_hash, max_bytes=MAX_OBJECT_BYTES):
        if not safe_key(key):
            raise ValueError("Invalid storage key")
        data = self._request("GET", key, b"", {})
        if not 0 < len(data) <= max_bytes or hashlib.sha256(data).hexdigest() != expected_hash:
            raise ValueError("Artifact hash/size mismatch")
        return data

    def _request(self, method, key, body, extra_headers):
        if not safe_key(key):
            raise ValueError("Invalid storage key")
        url = f"{self.endpoint}/{quote(self.bucket)}/{quote(key, safe='/.-_')}"
        parsed = urlparse(url)
        now = datetime.now(timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")
        payload_hash = hashlib.sha256(body).hexdigest()
        headers = {
            "host": parsed.netloc,
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": amz_date,
            **{k.lower(): v for k, v in extra_headers.items()},
        }
        signed_headers = ";".join(sorted(headers))
        canonical_headers = "".join(f"{name}:{headers[name]}\n" for name in sorted(headers))
        canonical = "\n".join([method, parsed.path, "", canonical_headers, signed_headers, payload_hash])
        scope = f"{date_stamp}/{self.region}/s3/aws4_request"
        string_to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()])
        signature = hmac.new(signing_key(self.secret_access_key, date_stamp, self.region), string_to_sign.encode(), hashlib.sha256).hexdigest()
        headers["authorization"] = (
            f"AWS4-HMAC-SHA256 Credential={self.access_key_id}/{scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        return self.transport(method, url, body, headers)


def digest_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as file:
        for block in iter(lambda: file.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def safe_key(value):
    return isinstance(value, str) and 1 <= len(value) <= 512 and ".." not in value and "\\" not in value and not value.startswith("/")


def signing_key(secret, date_stamp, region):
    key = ("AWS4" + secret).encode("utf-8")
    for part in (date_stamp, region, "s3", "aws4_request"):
        key = hmac.new(key, part.encode("utf-8"), hashlib.sha256).digest()
    return key


def default_transport(method, url, body, headers):
    request = Request(url, data=body if method in {"PUT", "POST"} else None, headers=headers, method=method)
    with urlopen(request, timeout=10) as response:  # nosec B310 -- endpoint is validated HTTPS and caller-configured
        data = response.read(MAX_OBJECT_BYTES + 1)
    if len(data) > MAX_OBJECT_BYTES:
        raise ValueError("Artifact response size limit")
    return data
