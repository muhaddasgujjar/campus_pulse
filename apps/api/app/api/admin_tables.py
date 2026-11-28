"""Admin portal: structured tables (DATA-1) and CSV import with a validation preview (DATA-2).

/api/admin/{faculty|timetable|fees|offices|key-dates}: list, create, update, delete.
/api/admin/{timetable|faculty}/import: raw CSV body; `dry_run=true` validates every row and
reports all errors without writing; `dry_run=false` imports only when there are no errors.
Scope checks per row (AUTH-3) are in app.services.admin_tables.can_edit.
"""

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, ValidationError

from app.api.admin_content import actor, ensure_scope
from app.api.deps import Session, StaffUser, read_capped
from app.services import admin_tables as tables
from app.services.content_admin import ContentError, import_rows, preview_csv_text

router = APIRouter(prefix="/api/admin", tags=["admin"])

CSV_MAX_BYTES = 2 * 1024 * 1024


def _spec(table: str) -> tables.TableSpec:
    spec = tables.TABLES.get(table)
    if spec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown table")
    return spec


def _out(spec: tables.TableSpec, row: Any, user: Any) -> dict[str, Any]:
    values = tables.row_values(spec, row)
    return {
        "id": row.id,
        **values,
        "updated_at": row.updated_at,
        "can_edit": tables.can_edit(user, spec, row, values),
    }


def _forbidden() -> HTTPException:
    return HTTPException(
        status.HTTP_403_FORBIDDEN, "you can only edit rows of your department or office"
    )


def _parse(spec: tables.TableSpec, body: dict[str, Any]) -> tables._In:
    try:
        return spec.schema.model_validate(body)
    except ValidationError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            [{"loc": e["loc"], "msg": e["msg"]} for e in exc.errors()],
        ) from exc


TableName = Literal["faculty", "timetable", "fees", "offices", "key-dates"]


@router.get("/tables/{table}")
async def list_table(
    table: TableName,
    user: StaffUser,
    session: Session,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[dict[str, Any]]:
    spec = _spec(table)
    rows = await tables.list_rows(
        session, spec, user.institution_id, query=q, limit=limit, offset=offset
    )
    return [_out(spec, row, user) for row in rows]


@router.post("/tables/{table}", status_code=status.HTTP_201_CREATED)
async def create_table_row(
    table: TableName, body: dict[str, Any], user: StaffUser, session: Session
) -> dict[str, Any]:
    spec = _spec(table)
    data = _parse(spec, body)
    if not tables.can_edit(user, spec, None, data.model_dump()):
        raise _forbidden()
    async with session.begin():
        row = await tables.create_row(session, spec, user, data)
    return _out(spec, row, user)


@router.put("/tables/{table}/{row_id}")
async def update_table_row(
    table: TableName, row_id: uuid.UUID, body: dict[str, Any], user: StaffUser, session: Session
) -> dict[str, Any]:
    spec = _spec(table)
    data = _parse(spec, body)
    async with session.begin():
        try:
            row = await tables.get_row(session, spec, user.institution_id, row_id)
        except ContentError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
        if not tables.can_edit(user, spec, row, data.model_dump()):
            raise _forbidden()
        row = await tables.update_row(session, spec, user, row, data)
    return _out(spec, row, user)


@router.delete("/tables/{table}/{row_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_table_row(
    table: TableName, row_id: uuid.UUID, user: StaffUser, session: Session
) -> None:
    spec = _spec(table)
    async with session.begin():
        try:
            row = await tables.get_row(session, spec, user.institution_id, row_id)
        except ContentError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
        if not tables.can_edit(user, spec, row, tables.row_values(spec, row)):
            raise _forbidden()
        await tables.delete_row(session, spec, user, row)


class ImportResult(BaseModel):
    valid_rows: int
    errors: list[str]
    imported: bool
    created: int = 0
    updated: int = 0
    unchanged: int = 0


@router.post("/import/{kind}", response_model=ImportResult)
async def import_csv(
    kind: Literal["timetable", "faculty"],
    request: Request,
    user: StaffUser,
    session: Session,
    dry_run: bool = True,
    department_id: uuid.UUID | None = None,
) -> ImportResult:
    """Timetable rows are tagged with `department_id` (defaults to the staff member's own).
    Faculty rows carry their department by name and are matched by name, so a faculty import
    could move another department's row: it is admin-only."""
    if kind == "faculty" and user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only an admin imports faculty CSVs")
    raw = await read_capped(request, CSV_MAX_BYTES, "CSV larger than 2 MB")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "save the CSV as UTF-8"
        ) from exc
    preview = preview_csv_text(kind, text)
    if kind == "timetable":
        department_id = department_id or (user.department_id if user.role == "staff" else None)
        ensure_scope(user, department_id, None)
    result = ImportResult(valid_rows=len(preview.rows), errors=preview.errors, imported=False)
    if dry_run or preview.errors:
        return result
    async with session.begin():
        try:
            stats = await import_rows(
                session, user.institution_id, kind, preview.rows, actor(user),
                department_id=department_id if kind == "timetable" else None,
            )  # fmt: skip
        except ContentError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    result.imported = True
    result.created, result.updated, result.unchanged = stats.created, stats.updated, stats.unchanged
    return result
