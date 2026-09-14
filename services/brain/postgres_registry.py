"""Optional PostgreSQL adapter for the research registry.

The normal test suite does not require a live database. In production, install
and configure a PostgreSQL driver in the runtime image before using this class.
"""
from __future__ import annotations

from pathlib import Path

from .production import validate_url

MIGRATIONS_DIR = Path(__file__).with_name("migrations")


def migration_sql():
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not files:
        raise ValueError("No PostgreSQL migrations found")
    return "\n\n".join(path.read_text(encoding="utf-8") for path in files)


def validate_database_url(url):
    value = validate_url({"DATABASE_URL": url}, "DATABASE_URL", required=True, https_required=False)
    if not value.startswith(("postgres://", "postgresql://")):
        raise ValueError("DATABASE_URL must be PostgreSQL-compatible")
    return value


class PostgresRegistry:
    def __init__(self, database_url=None, connection=None):
        self.database_url = validate_database_url(database_url) if database_url else None
        if connection is not None:
            self.con = connection
        else:
            try:
                import psycopg  # type: ignore
            except ImportError as error:  # pragma: no cover - depends on production image
                raise ValueError("psycopg is required for live PostgreSQL access") from error
            self.con = psycopg.connect(self.database_url)

    def close(self):
        close = getattr(self.con, "close", None)
        if close:
            close()

    def apply_migrations(self):
        with self.con:
            self.con.execute(migration_sql())

    def promote_transactional(self, champion_id, candidate_id, checkpoint_id, checkpoint_hash, graph_hash, evidence_json):
        sql = """
        INSERT INTO champions(id, candidate_id, checkpoint_id, checkpoint_hash, graph_hash, promoted_at, selection, evidence_json)
        VALUES(%s, %s, %s, %s, %s, now(), 'automatic_gate', %s::jsonb);
        INSERT INTO canonical_champion(singleton, champion_id, updated_at)
        VALUES(true, %s, now())
        ON CONFLICT(singleton) DO UPDATE SET champion_id = EXCLUDED.champion_id, updated_at = EXCLUDED.updated_at;
        """
        with self.con:
            self.con.execute(sql, (champion_id, candidate_id, checkpoint_id, checkpoint_hash, graph_hash, evidence_json, champion_id))


def schema_summary():
    sql = migration_sql()
    tables = []
    for line in sql.splitlines():
        stripped = line.strip()
        if stripped.startswith("CREATE TABLE IF NOT EXISTS "):
            tables.append(stripped.split()[5])
    return {"migration_count": len(list(MIGRATIONS_DIR.glob("*.sql"))), "tables": tables}
