"""Production role environment and compute-governor validation."""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from urllib.parse import urlparse

ROLES = {"WEB", "BRAIN_API", "RESEARCH_WORKER", "DAILY_EVALUATOR"}


def structured_log(event, **fields):
    print(json.dumps({"event": event, "timestamp_ns": time.time_ns(), **fields}, allow_nan=False), flush=True)


def env_int(values, name, default, minimum, maximum):
    raw = values.get(name, str(default))
    if not isinstance(raw, str) or not raw.isascii() or not raw.isdigit():
        raise ValueError(f"Invalid {name}")
    value = int(raw)
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} outside allowed range")
    return value


def validate_url(values, name, required=False, https_required=True):
    raw = values.get(name, "")
    if not raw:
        if required:
            raise ValueError(f"{name} is required")
        return ""
    parsed = urlparse(raw)
    if parsed.username or parsed.password or parsed.query or parsed.fragment or not parsed.hostname:
        raise ValueError(f"Invalid {name}")
    if parsed.scheme not in {"https", "http", "postgres", "postgresql"}:
        raise ValueError(f"Invalid {name} scheme")
    if https_required and parsed.scheme != "https":
        raise ValueError(f"{name} must use HTTPS")
    return raw.rstrip("/")


@dataclass(frozen=True)
class ComputeLimits:
    max_daily_experiments: int
    max_concurrent_experiments: int
    max_generations_per_experiment: int
    max_population: int
    max_experiment_runtime_seconds: int
    max_retries: int
    max_failures: int
    max_storage_bytes: int
    max_workers: int
    daily_cpu_time_budget_seconds: int

    def within_experiment(self, generations, population, runtime_seconds=0):
        return (
            1 <= generations <= self.max_generations_per_experiment
            and 4 <= population <= self.max_population
            and 0 <= runtime_seconds <= self.max_experiment_runtime_seconds
        )


def load_compute_limits(values=None):
    values = os.environ if values is None else values
    return ComputeLimits(
        max_daily_experiments=env_int(values, "MAX_DAILY_EXPERIMENTS", 3, 0, 50),
        max_concurrent_experiments=env_int(values, "MAX_CONCURRENT_EXPERIMENTS", 1, 1, 4),
        max_generations_per_experiment=env_int(values, "MAX_GENERATIONS_PER_EXPERIMENT", 4, 1, 20),
        max_population=env_int(values, "MAX_POPULATION", 8, 4, 12),
        max_experiment_runtime_seconds=env_int(values, "MAX_EXPERIMENT_RUNTIME", 600, 30, 3600),
        max_retries=env_int(values, "MAX_RETRIES", 1, 0, 5),
        max_failures=env_int(values, "MAX_FAILURES", 3, 0, 20),
        max_storage_bytes=env_int(values, "MAX_STORAGE_BYTES", 200_000_000, 10_000_000, 5_000_000_000),
        max_workers=env_int(values, "MAX_WORKERS", 1, 1, 4),
        daily_cpu_time_budget_seconds=env_int(values, "DAILY_CPU_TIME_BUDGET", 900, 30, 86_400),
    )


@dataclass(frozen=True)
class ProductionEnv:
    role: str
    database_url: str
    artifact_backend: str
    public_app_url: str
    brain_public_url: str
    s3_endpoint: str
    s3_bucket: str
    limits: ComputeLimits


def load_production_env(values=None):
    values = os.environ if values is None else values
    role = values.get("FLYWEIGHT_SERVICE_ROLE", "")
    if role not in ROLES:
        raise ValueError("FLYWEIGHT_SERVICE_ROLE must name a production role")
    database_required = role in {"RESEARCH_WORKER", "DAILY_EVALUATOR", "BRAIN_API"}
    database_url = validate_url(values, "DATABASE_URL", database_required, https_required=False)
    if database_url and not database_url.startswith(("postgres://", "postgresql://")):
        raise ValueError("DATABASE_URL must be PostgreSQL-compatible")
    artifact_backend = values.get("ARTIFACT_BACKEND", "local")
    if artifact_backend not in {"local", "s3"}:
        raise ValueError("ARTIFACT_BACKEND must be local or s3")
    s3_endpoint = validate_url(values, "S3_ENDPOINT", artifact_backend == "s3")
    s3_bucket = values.get("S3_BUCKET", "")
    if artifact_backend == "s3":
        if not s3_bucket or not s3_bucket.replace("-", "").replace("_", "").isalnum():
            raise ValueError("S3_BUCKET is required")
        for secret in ("S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY"):
            if not values.get(secret):
                raise ValueError(f"{secret} is required")
    public_app_url = validate_url(values, "PUBLIC_APP_URL", role == "WEB")
    brain_public_url = validate_url(values, "BRAIN_PUBLIC_URL", role in {"WEB", "BRAIN_API"})
    limits = load_compute_limits(values)
    return ProductionEnv(role, database_url, artifact_backend, public_app_url, brain_public_url, s3_endpoint, s3_bucket, limits)
