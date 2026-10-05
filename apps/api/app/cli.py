"""Command line for data tasks: the minimal admin path until the M5 portal (Phases.md M2).

Run from apps/api:  uv run python -m app.cli <command> ...   (see `--help` on each command)

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
import uuid
from collections.abc import Awaitable, Callable
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import KbEntry
from app.db.session import create_engine, create_sessionmaker
from app.services import content_admin as admin
from app.services.embeddings import build_embedder
from app.services.ingestion import index_entry
from app.services.pdf import PdfRejectedError
from app.services.seeding import KbEntryRow, load_seed_dir

Command = Callable[[AsyncSession, argparse.Namespace], Awaitable[int]]


def actor() -> admin.Actor:
    try:
        user = getpass.getuser()
    except Exception:
        user = "unknown"
    return admin.Actor(label=f"cli:{user}")


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
            code = await command(session, args)
            if code != 0:  # dry runs and failures change nothing
                await session.rollback()
            return code
    finally:
        await engine.dispose()


async def _institution(session: AsyncSession) -> uuid.UUID:
    return await admin.institution_id_for(session, get_settings().institution_slug)


# --- commands ------------------------------------------------------------------------------


async def cmd_seed(session: AsyncSession, args: argparse.Namespace) -> int:
    embedder = build_embedder(get_settings())

    async def on_entry(entry: KbEntry) -> None:
        await index_entry(session, entry, embedder)

    report = await load_seed_dir(
        session, Path(args.seed_dir), actor_label=f"seed:{actor().label}", on_kb_entry=on_entry
    )
    print(report.summary())
    if embedder is None:
        print("Note: no embedder configured, so KB chunks have no vectors (keyword search only).")
    return 0


async def cmd_kb_list(session: AsyncSession, args: argparse.Namespace) -> int:
    stmt = select(KbEntry).where(KbEntry.institution_id == await _institution(session))
    if args.status:
        stmt = stmt.where(KbEntry.status == args.status)
    for entry in (await session.execute(stmt.order_by(KbEntry.title))).scalars():
        print(f"{entry.id}  {entry.status:<9} v{entry.version}  {entry.title}")
    return 0


async def cmd_kb_add(session: AsyncSession, args: argparse.Namespace) -> int:
    row = KbEntryRow(
        title=args.title,
        question=args.question,
        answer=args.answer,
        category=args.category,
        owner_name=args.owner,
        last_verified=args.last_verified,
        expires_at=args.expires,
        source_url=args.source_url,
    )
    entry = await admin.create_entry(
        session, await _institution(session), row, actor(), submit=args.submit
    )
    print(f"Created {entry.status} entry {entry.id}")
    return 0


async def cmd_kb_submit(session: AsyncSession, args: argparse.Namespace) -> int:
    entry = await admin.submit_entry(session, args.id, actor())
    print(f"Submitted {entry.id} for approval")
    return 0


async def cmd_kb_approve(session: AsyncSession, args: argparse.Namespace) -> int:
    entry, result = await admin.approve_entry(
        session, args.id, actor(), build_embedder(get_settings())
    )
    print(f"Approved {entry.id}: {result.chunks} chunk(s), embedded={result.embedded}")
    return 0


async def cmd_kb_reject(session: AsyncSession, args: argparse.Namespace) -> int:
    entry = await admin.reject_entry(session, args.id, actor(), args.reason)
    print(f"Rejected {entry.id}: back to draft")
    return 0


async def cmd_kb_archive(session: AsyncSession, args: argparse.Namespace) -> int:
    entry = await admin.archive_entry(session, args.id, actor())
    print(f"Archived {entry.id}")
    return 0


async def cmd_import(session: AsyncSession, args: argparse.Namespace) -> int:
    preview = admin.preview_csv(args.kind, Path(args.csv))
    print(f"{len(preview.rows)} valid row(s), {len(preview.errors)} error(s)")
    for error in preview.errors:
        print(f"  {error}")
    if preview.errors:
        print("Nothing imported: fix the errors above and run again.")
        return 2
    if not args.commit:
        print("Dry run: nothing imported. Add --commit to import.")
        return 3
    stats = await admin.import_rows(
        session, await _institution(session), args.kind, preview.rows, actor()
    )
    print(
        f"Imported: {stats.created} created, {stats.updated} updated, {stats.unchanged} unchanged"
    )
    return 0


async def cmd_doc_upload(session: AsyncSession, args: argparse.Namespace) -> int:
    settings = get_settings()
    document = await admin.upload_document(
        session,
        await _institution(session),
        await asyncio.to_thread(Path(args.pdf).read_bytes),
        title=args.title,
        category=args.category,
        owner_name=args.owner,
        last_verified=args.last_verified,
        expires_at=args.expires,
        max_mb=settings.pdf_max_mb,
        actor=actor(),
    )
    preview = document.content[:400].replace("\n", " ")
    print(f"Uploaded pending document {document.id} ({len(document.content)} characters)")
    print(f"Preview: {preview}...")
    return 0


async def cmd_doc_approve(session: AsyncSession, args: argparse.Namespace) -> int:
    document, result = await admin.approve_document(
        session, args.id, actor(), build_embedder(get_settings())
    )
    print(f"Approved {document.id}: {result.chunks} chunk(s), embedded={result.embedded}")
    return 0


async def cmd_reindex(session: AsyncSession, args: argparse.Namespace) -> int:
    chunks, embedded = await admin.reindex_all(
        session, await _institution(session), build_embedder(get_settings())
    )
    print(f"Re-indexed {chunks} chunk(s), {embedded} with vectors")
    return 0


# --- parser --------------------------------------------------------------------------------


def _date(value: str) -> date:
    return date.fromisoformat(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    seed = sub.add_parser("seed", help="Load seed/<slug>/ (idempotent) and index KB entries")
    seed.add_argument("seed_dir")
    seed.set_defaults(func=cmd_seed)

    kb = sub.add_parser("kb", help="Knowledge base entries").add_subparsers(
        dest="kb_command", required=True
    )
    kb_list = kb.add_parser("list")
    kb_list.add_argument("--status", choices=["draft", "pending", "approved", "archived"])
    kb_list.set_defaults(func=cmd_kb_list)
    kb_add = kb.add_parser("add", help="Create a draft (or --submit for approval)")
    kb_add.add_argument("--title", required=True)
    kb_add.add_argument("--answer", required=True)
    kb_add.add_argument("--category", required=True)
    kb_add.add_argument("--question")
    kb_add.add_argument("--owner", help="Office responsible for this fact")
    kb_add.add_argument("--last-verified", type=_date, required=True, help="YYYY-MM-DD")
    kb_add.add_argument("--expires", type=_date, help="YYYY-MM-DD")
    kb_add.add_argument("--source-url")
    kb_add.add_argument("--submit", action="store_true")
    kb_add.set_defaults(func=cmd_kb_add)
    for name, func in (("submit", cmd_kb_submit), ("approve", cmd_kb_approve),
                       ("archive", cmd_kb_archive)):  # fmt: skip
        command = kb.add_parser(name)
        command.add_argument("id", type=uuid.UUID)
        command.set_defaults(func=func)
    kb_reject = kb.add_parser("reject")
    kb_reject.add_argument("id", type=uuid.UUID)
    kb_reject.add_argument("--reason", required=True)
    kb_reject.set_defaults(func=cmd_kb_reject)

    imp = sub.add_parser("import", help="Import timetable or faculty CSV (dry run by default)")
    imp.add_argument("kind", choices=["timetable", "faculty"])
    imp.add_argument("csv")
    imp.add_argument("--commit", action="store_true")
    imp.set_defaults(func=cmd_import)

    doc = sub.add_parser("doc", help="Text PDF documents").add_subparsers(
        dest="doc_command", required=True
    )
    upload = doc.add_parser("upload", help="Extract text and create a pending document")
    upload.add_argument("pdf")
    upload.add_argument("--title", required=True)
    upload.add_argument("--category", required=True)
    upload.add_argument("--owner")
    upload.add_argument("--last-verified", type=_date, required=True)
    upload.add_argument("--expires", type=_date)
    upload.set_defaults(func=cmd_doc_upload)
    doc_approve = doc.add_parser("approve")
    doc_approve.add_argument("id", type=uuid.UUID)
    doc_approve.set_defaults(func=cmd_doc_approve)

    reindex = sub.add_parser("reindex", help="Re-chunk and re-embed all approved content")
    reindex.set_defaults(func=cmd_reindex)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return asyncio.run(_run(args.func, args))
    except (admin.ContentError, PdfRejectedError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
