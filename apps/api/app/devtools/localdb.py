"""Local throwaway Postgres + pgvector for tests, `make seed` and `make eval` (dev only).

If DATABASE_URL is set (CI service container, or your dev Supabase project) it is used as is.
Otherwise an embedded Postgres 16 with pgvector is started with the `pgserver` dev dependency,
so no Docker or Postgres install is needed. Never used in production (pgserver is a dev dep).
"""

import os
import re
import subprocess
import sys
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = API_DIR / ".localdb"
_DB_NAME = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def database_url(db_name: str = "campus_pulse_local", data_dir: Path | None = None) -> str:
    """Return a Postgres URL: DATABASE_URL if set, else a local pgserver database."""
    configured = os.environ.get("DATABASE_URL", "").strip()
    if configured:
        return configured
    try:
        import pgserver  # dev dependency, imported lazily
    except ImportError as exc:  # pragma: no cover - only without dev deps
        raise RuntimeError(
            "DATABASE_URL is not set and pgserver is not installed (run `uv sync`)."
        ) from exc

    if not _DB_NAME.match(db_name):  # psql takes raw SQL, so only allow plain identifiers
        raise ValueError(f"invalid database name: {db_name!r}")
    server = pgserver.get_server(str(data_dir or DEFAULT_DATA_DIR), cleanup_mode=None)
    exists = server.psql(f"select 1 from pg_database where datname = '{db_name}';")  # noqa: S608
    if "(1 row)" not in exists:
        server.psql(f'create database "{db_name}";')
    base: str = server.get_uri()
    return base.rsplit("/", 1)[0] + f"/{db_name}"


def migrate(url: str) -> None:
    """Run `alembic upgrade head` against `url` (session-capable URL)."""
    env = dict(os.environ, DATABASE_URL_MIGRATIONS=url)
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=API_DIR,
        env=env,
        check=True,
        capture_output=True,
    )


if __name__ == "__main__":
    print(database_url())
