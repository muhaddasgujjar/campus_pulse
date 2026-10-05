"""Command line for data tasks: the minimal admin path until the M5 portal (Phases.md M2).

Run from apps/api:  uv run python -m app.cli <command> ...

Database: DATABASE_URL from env/.env (your dev Supabase project). If it is not set, a local
embedded Postgres (pgserver, dev only) is used and migrated automatically.
Every write records an audit_log row with actor "cli:<os user>" (rule 7). Real user identity
and RBAC come with Supabase Auth in M5; the CLI needs direct database access, which only
admins have.
"""

import argparse
import asyncio
import getpass
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import create_engine, create_sessionmaker
from app.services.seeding import load_seed_dir

Command = Callable[[AsyncSession, argparse.Namespace], Awaitable[int]]


def actor_label() -> str:
    try:
        user = getpass.getuser()
    except Exception:
        user = "unknown"
    return f"cli:{user}"


def resolve_database_url() -> str:
    settings = get_settings()
    if settings.database_url:
        print("Using DATABASE_URL from the environment.", file=sys.stderr)
        return settings.database_url
    from app.devtools.localdb import database_url, migrate

    url = database_url()
    migrate(url)
    print("DATABASE_URL not set: using the local pgserver database (migrated).", file=sys.stderr)
    return url


async def _run(command: Command, args: argparse.Namespace) -> int:
    engine = create_engine(resolve_database_url())
    try:
        maker = create_sessionmaker(engine)
        async with maker() as session, session.begin():
            return await command(session, args)
    finally:
        await engine.dispose()


async def cmd_seed(session: AsyncSession, args: argparse.Namespace) -> int:
    report = await load_seed_dir(session, Path(args.seed_dir), actor_label=f"seed:{actor_label()}")
    print(report.summary())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    seed = sub.add_parser("seed", help="Load seed/<slug>/ (idempotent) and index KB entries")
    seed.add_argument("seed_dir", help="Path to the seed directory, e.g. ../../seed/lgu")
    seed.set_defaults(func=cmd_seed)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return asyncio.run(_run(args.func, args))
    except ValueError as exc:  # validation errors: show them plainly, no traceback
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
