"""Command line for data tasks and the first admin account (Phases.md M2, M5).

Run from apps/api:  uv run python -m app.cli <command> ...   (see `--help` on each command)

Database: DATABASE_URL from env/.env (your dev Supabase project). If it is not set, a local
embedded Postgres (pgserver, dev only) is used and migrated automatically.
Every write records an audit_log row with actor "cli:<os user>" (rule 7). The CLI needs direct
database access, which only admins have; everyone else uses the admin portal (RBAC, AUTH-3).

The first admin: `user add you@lgu.edu.pk --name "..." --role admin` creates the Supabase account
(email pre-confirmed) and the profile. The password is read from NEW_USER_PASSWORD or prompted.
"""

import argparse
import asyncio
import getpass
import json
import os
import sys
import uuid
from collections.abc import Awaitable, Callable
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthenticatedUser
from app.core.config import get_settings
from app.db.models import Department, Document, KbEntry, Office, Profile
from app.db.session import create_engine, create_sessionmaker
from app.services import content_admin as admin
from app.services import users
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
    embedder = build_embedder(get_settings())
    for document_id in args.ids:
        document, result = await admin.approve_document(
            session, document_id, actor(), embedder, verified_on=args.verified
        )
        print(f"Approved {document.id}: {result.chunks} chunk(s), embedded={result.embedded}")
    return 0


async def cmd_doc_list(session: AsyncSession, args: argparse.Namespace) -> int:
    stmt = select(Document).where(Document.institution_id == await _institution(session))
    if args.status:
        stmt = stmt.where(Document.status == args.status)
    if args.category:
        stmt = stmt.where(Document.category == args.category)
    rows = await session.execute(stmt.order_by(Document.category, Document.title))
    for document in rows.scalars():
        url = f"  {document.source_url}" if document.source_url else ""
        print(f"{document.id}  {document.status:<8} {document.category:<12} {document.title}{url}")
    return 0


async def cmd_doc_show(session: AsyncSession, args: argparse.Namespace) -> int:
    document = await session.get(Document, args.id)
    if document is None:
        raise admin.ContentError(f"Document {args.id} not found.")
    print(f"{document.title} [{document.status}, {document.category}] {document.source_url or ''}")
    print(f"last verified: {document.last_verified or 'not yet'}\n")
    print(document.content)
    return 0


async def cmd_doc_import_web(session: AsyncSession, args: argparse.Namespace) -> int:
    payload = json.loads(await asyncio.to_thread(Path(args.snapshot).read_text, encoding="utf-8"))
    pages = [admin.WebPage.model_validate(page) for page in payload["pages"]]
    report = await admin.import_web_pages(
        session, await _institution(session), pages, actor(), owner_name=args.owner
    )
    print(
        f"{len(pages)} page(s): {report.created} created, {report.updated} changed (back to "
        f"pending), {report.unchanged} unchanged, {report.archived_skipped} archived (skipped)"
    )
    print("All imported pages are PENDING: review with `doc list --status pending` and "
          "`doc show ID`, then `doc approve ID ...` (D6).")  # fmt: skip
    return 0


async def cmd_reindex(session: AsyncSession, args: argparse.Namespace) -> int:
    chunks, embedded = await admin.reindex_all(
        session, await _institution(session), build_embedder(get_settings())
    )
    print(f"Re-indexed {chunks} chunk(s), {embedded} with vectors")
    return 0


# --- parser --------------------------------------------------------------------------------


async def _named(
    session: AsyncSession, model: type[Department] | type[Office], name: str
) -> uuid.UUID:
    found = (
        await session.execute(select(model.id).where(model.name.ilike(name.strip())))
    ).scalar_one_or_none()
    if found is None:
        raise admin.ContentError(f"No {model.__tablename__[:-1]} named {name!r}.")
    return found


async def cmd_user_add(session: AsyncSession, args: argparse.Namespace) -> int:
    email = args.email.strip().lower()
    existing = await session.execute(select(Profile.id).where(Profile.email == email))
    if existing.scalar_one_or_none() is not None:
        if args.if_missing:
            print(f"{email} already exists.")
            return 0
        raise admin.ContentError("A user with this email already exists.")
    provider = users.build_auth_admin(get_settings())
    if provider is None:
        raise admin.ContentError(
            "Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (or DEV_AUTH=true on a laptop)."
        )
    password = os.environ.get("NEW_USER_PASSWORD") or (
        "local-dev-only" if get_settings().dev_auth else getpass.getpass("Temporary password: ")
    )
    inst = await _institution(session)
    cli_admin = AuthenticatedUser(
        user_id=uuid.UUID(int=0), role="admin", is_anonymous=False, institution_id=inst,
        email=actor().label,
    )  # fmt: skip
    new = users.NewStaff(
        email=email,
        password=password,
        full_name=args.name,
        role=args.role,
        department_id=await _named(session, Department, args.department)
        if args.department
        else None,
        office_id=await _named(session, Office, args.office) if args.office else None,
    )
    try:
        profile = await users.create_staff(session, provider, cli_admin, new)
    except users.AuthAdminError as exc:
        raise admin.ContentError(str(exc)) from exc
    print(f"Created {profile.role} {email} ({profile.id}).")
    return 0


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

    doc = sub.add_parser("doc", help="Documents: text PDFs and imported web pages").add_subparsers(
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
    doc_approve = doc.add_parser("approve", help="Approve, chunk and embed pending documents")
    doc_approve.add_argument("ids", type=uuid.UUID, nargs="+")
    doc_approve.add_argument(
        "--verified", type=_date, default=date.today(), help="date checked with the office"
    )
    doc_approve.set_defaults(func=cmd_doc_approve)
    doc_list = doc.add_parser("list")
    doc_list.add_argument("--status", choices=["draft", "pending", "approved", "archived"])
    doc_list.add_argument("--category")
    doc_list.set_defaults(func=cmd_doc_list)
    doc_show = doc.add_parser("show", help="Print a document's text for review")
    doc_show.add_argument("id", type=uuid.UUID)
    doc_show.set_defaults(func=cmd_doc_show)
    web = doc.add_parser(
        "import-web", help="Load a website snapshot (app.devtools.web_import) as pending documents"
    )
    web.add_argument("snapshot")
    web.add_argument("--owner", default="LGU website", help="shown as the source office")
    web.set_defaults(func=cmd_doc_import_web)

    reindex = sub.add_parser("reindex", help="Re-chunk and re-embed all approved content")
    reindex.set_defaults(func=cmd_reindex)

    user = sub.add_parser("user", help="Staff and admin accounts").add_subparsers(
        dest="user_command", required=True
    )
    user_add = user.add_parser("add", help="Create a staff or admin account (email confirmed)")
    user_add.add_argument("email")
    user_add.add_argument("--name", required=True)
    user_add.add_argument("--role", choices=["staff", "admin"], default="staff")
    user_add.add_argument("--department", help="department name (staff scope)")
    user_add.add_argument("--office", help="office name (staff scope)")
    user_add.add_argument("--if-missing", action="store_true", help="do nothing if it exists")
    user_add.set_defaults(func=cmd_user_add)
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
