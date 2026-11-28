"""Run the API locally with no cloud services (dev only): `make api-local`.

Starts the embedded Postgres + pgvector (pgserver, a dev dependency), migrates it, loads
seed/<slug> (idempotent), then runs uvicorn with DATABASE_URL pointing at it. The chat works
end to end on a laptop: no Supabase, no Redis (in-process fallbacks), and templates instead of
an LLM unless LLM_PROVIDERS and keys are set in .env.

Embeddings: seeding and querying must use the same embedder. Unless EMBEDDING_MODEL and the
key of its provider (OPENAI_API_KEY for text-embedding-*, else GEMINI_API_KEY) are configured,
EMBEDDING_MODEL=fake is used for both (lexical vectors,
like `make eval`). After switching embedders, run `uv run python -m app.cli reindex`.

Sign-in (M5): with no SUPABASE_URL, DEV_AUTH is turned on with a throwaway JWT secret and two
accounts are created: admin@local.test (admin) and staff@local.test (staff, Admission Office).
Sign in at /admin/login with either email (no password is checked on a laptop).

Never used in production: the Docker image does not include dev dependencies.
"""

import argparse
import os
import secrets
import subprocess
import sys
from pathlib import Path

from app.core.config import Settings
from app.devtools.localdb import API_DIR, database_url, migrate
from app.services.embeddings import is_openai_embedding_model

REPO = API_DIR.parents[1]


def embeddings_configured(settings: Settings) -> bool:
    """Real embeddings need the model and the key of its provider (OpenAI or Gemini)."""
    if not settings.embedding_model or settings.embedding_model == "fake":
        return False
    if is_openai_embedding_model(settings.embedding_model):
        return settings.openai_api_key is not None
    return settings.gemini_api_key is not None


def local_env(url: str, settings: Settings, cors_origins: str) -> dict[str, str]:
    env = dict(os.environ, DATABASE_URL=url, APP_ENV="local")
    if not embeddings_configured(settings):
        env["EMBEDDING_MODEL"] = "fake"
    env.setdefault("CORS_ORIGINS", cors_origins)
    if not settings.supabase_url:
        env["DEV_AUTH"] = "true"
        if not settings.supabase_jwt_secret:
            env["SUPABASE_JWT_SECRET"] = secrets.token_urlsafe(32)  # new each run, never stored
    return env


DEV_ACCOUNTS = (
    ["admin@local.test", "--name", "Local Admin", "--role", "admin"],
    [
        "staff@local.test",
        "--name",
        "Local Staff",
        "--role",
        "staff",
        "--office",
        "Admission Office",
    ],
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the API on a local embedded database.")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--db", default="campus_pulse_local", help="local database name")
    parser.add_argument("--seed-dir", type=Path, default=REPO / "seed" / "lgu")
    parser.add_argument("--no-seed", action="store_true", help="skip loading the seed folder")
    parser.add_argument("--cors-origins", default="http://localhost:3000")
    args = parser.parse_args(argv)

    os.environ.pop("DATABASE_URL", None)  # always the local database, never the cloud one
    url = database_url(args.db)
    migrate(url)
    env = local_env(url, Settings(), args.cors_origins)
    print(f"Local database {args.db} migrated. Embeddings: {env.get('EMBEDDING_MODEL')}.")
    if not args.no_seed:
        subprocess.run(  # noqa: S603 - fixed argv, no shell, dev only
            [sys.executable, "-m", "app.cli", "seed", str(args.seed_dir)],
            cwd=API_DIR,
            env=env,
            check=True,
        )
    if env.get("DEV_AUTH") == "true":
        for account in DEV_ACCOUNTS:
            subprocess.run(  # noqa: S603 - fixed argv, no shell, dev only
                [sys.executable, "-m", "app.cli", "user", "add", *account, "--if-missing"],
                cwd=API_DIR,
                env=env,
                check=True,
            )
    print(f"API on http://localhost:{args.port} (Ctrl+C to stop)", flush=True)
    try:
        return subprocess.run(  # noqa: S603 - fixed argv, no shell, dev only
            [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(args.port)],
            cwd=API_DIR,
            env=env,
            check=False,
        ).returncode
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
