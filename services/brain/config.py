"""Read only documented configuration keys, validate before starting any listener."""
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
# Matches the frontend's own loopback allowlist (apps/web/src/config.ts) so a
# browser opened via any of these three equivalent local addresses is not
# rejected as if it were a different, untrusted origin.
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


@dataclass(frozen=True)
class Settings:
    production: bool
    host: str
    port: int
    origins: tuple[str, ...]
    allowed_hosts: tuple[str, ...]
    data_dir: Path

    @property
    def training_enabled(self):
        return not self.production


def load_settings(values=None):
    values = os.environ if values is None else values
    mode = values.get("FLYWEIGHT_ENV", "development")
    if mode not in {"development", "production"}:
        raise ValueError("Invalid environment mode")
    production = mode == "production"
    host = values.get("FLYWEIGHT_BIND_HOST", "127.0.0.1")
    if host not in ({"127.0.0.1", "0.0.0.0"} if production else {"127.0.0.1"}):  # nosec B104
        raise ValueError("Invalid bind address")
    raw_port = values.get("PORT", "8000")
    if not raw_port.isascii() or not raw_port.isdigit() or not 1024 <= int(raw_port) <= 65535:
        raise ValueError("Invalid port")
    raw_origins = values.get("FLYWEIGHT_PUBLIC_ORIGINS", "" if production else "http://127.0.0.1:5173,http://localhost:5173")
    origins = tuple(x.strip().rstrip("/") for x in raw_origins.split(",") if x.strip())
    if not 1 <= len(origins) <= 4:
        raise ValueError("Exact frontend origins required")
    for origin in origins:
        p = urlparse(origin)
        if p.scheme not in {"https", "http"} or not p.hostname or p.username or p.password or p.path or p.query or p.fragment or "*" in origin:
            raise ValueError("Invalid exact origin")
        if p.scheme != "https" and (production or p.hostname not in LOOPBACK_HOSTS):
            raise ValueError("Production origins require HTTPS")
    hosts = tuple(x.strip() for x in values.get("FLYWEIGHT_ALLOWED_HOSTS", "127.0.0.1" if not production else "").split(",") if x.strip())
    if not hosts or len(hosts) > 5 or any(not x or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-" for c in x) for x in hosts):
        raise ValueError("Exact service hostnames required")
    path = Path(values.get("FLYWEIGHT_DATA_DIR", str(ROOT / "data/processed"))).resolve()
    allowed = path.is_relative_to(ROOT) or (os.name != "nt" and path.is_relative_to(Path("/data")))
    if not allowed:
        raise ValueError("Data directory must be in project or the explicit /data volume")
    return Settings(production, host, int(raw_port), origins, hosts, path)


SETTINGS = load_settings()
