"""Admin portal and account endpoints over HTTP (M5): authentication (AUTH-2), the RBAC matrix
on real routes (AUTH-3), staff scope, the approval workflow end to end (DATA-4, DATA-5), the
audit log (ADM-2), users (ADM-4), settings (ADP-2), metrics (ADM-3), "Delete my data"
(PRIV-2) and the deadlines card (CHAT-7).

Tokens are signed in the test with a throwaway HS256 secret (DEV_AUTH test mode). No network.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import TokenVerifier
from app.db.models import AuditLog, Conversation, KeyDate, Office, Profile
from app.main import create_app
from app.services.chat import ChatServices, run_turn
from app.services.content_admin import institution_id_for
from app.services.embeddings import FakeEmbedder
from app.services.users import LocalAuthAdmin
from tests.conftest import make_settings, running_client
from tests.integration.test_chat_turns import Events, make_services, seeded, turn

pytestmark = pytest.mark.integration
__all__ = ["seeded"]  # fixture re-used from test_chat_turns

SECRET = "test-only-secret-for-hs256-tokens-0123456789"
AUTH_SETTINGS: dict[str, Any] = {"dev_auth": True, "supabase_jwt_secret": SECRET}


class People:
    def __init__(self, verifier: TokenVerifier) -> None:
        self.verifier = verifier
        self.ids: dict[str, uuid.UUID] = {}

    def headers(self, who: str) -> dict[str, str]:
        if who == "anonymous":
            return {}
        user_id = self.ids.setdefault(who, uuid.uuid4())
        token = self.verifier.issue_dev_token(
            user_id, email=f"{who}@test.edu", is_anonymous=who == "student"
        )
        return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def services(db_session: AsyncSession, seeded: FakeEmbedder) -> ChatServices:
    return make_services(db_session, seeded, **AUTH_SETTINGS)


@pytest.fixture
async def offices(db_session: AsyncSession) -> dict[str, uuid.UUID]:
    rows = await db_session.execute(select(Office.name, Office.id))
    return {name: office_id for name, office_id in rows}


@pytest.fixture
async def people(
    db_session: AsyncSession, services: ChatServices, offices: dict[str, uuid.UUID]
) -> People:
    inst = await institution_id_for(db_session, "lgu")
    verifier = TokenVerifier(services.settings)
    found = People(verifier)
    for who, role, office in (
        ("admin", "admin", None),
        ("staff", "staff", "Admission Office"),
        ("exam", "staff", "Exam Office"),
    ):
        user_id = uuid.uuid4()
        found.ids[who] = user_id
        db_session.add(
            Profile(
                id=user_id, institution_id=inst, role=role, email=f"{who}@test.edu",
                full_name=who.title(), office_id=offices[office] if office else None,
                is_active=True,
            )
        )  # fmt: skip
    await db_session.flush()
    return found


@pytest.fixture
async def api(services: ChatServices) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(make_settings(**AUTH_SETTINGS))
    async with running_client(app) as client:
        app.state.chat = services  # bound to the test's rolled-back transaction
        app.state.auth_admin = LocalAuthAdmin()
        yield client


def entry(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "title": "Evening shuttle to Gulberg",
        "question": "Is there an evening shuttle to Gulberg?",
        "answer": "The evening shuttle to Gulberg leaves the main gate at 17:30 on weekdays.",
        "category": "transport",
        "last_verified": "2026-11-01",
        "expires_at": "2027-06-30",
    }
    body.update(overrides)
    return body


# --- authentication --------------------------------------------------------------------------


async def test_admin_routes_need_a_token(api: httpx.AsyncClient) -> None:
    response = await api.get("/api/admin/kb")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


async def test_a_forged_token_is_refused(api: httpx.AsyncClient, people: People) -> None:
    other = TokenVerifier(make_settings(dev_auth=True, supabase_jwt_secret="x" * 40))
    token = other.issue_dev_token(people.ids["admin"], email=None, is_anonymous=False)
    response = await api.get("/api/admin/kb", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


async def test_the_role_comes_from_the_profile_not_the_token(
    api: httpx.AsyncClient, people: People
) -> None:
    """A brand-new token user is a student, whatever the token says."""
    response = await api.get("/api/me", headers=people.headers("newcomer"))
    assert response.status_code == 200
    assert response.json()["role"] == "student"
    assert (await api.get("/api/admin/kb", headers=people.headers("newcomer"))).status_code == 403


async def test_a_deactivated_account_is_refused_even_with_a_valid_token(
    api: httpx.AsyncClient, people: People
) -> None:
    staff_id = people.ids["staff"]
    changed = await api.patch(
        f"/api/admin/users/{staff_id}", json={"is_active": False}, headers=people.headers("admin")
    )
    assert changed.status_code == 200
    assert (await api.get("/api/me", headers=people.headers("staff"))).status_code == 403


# --- the RBAC matrix on real routes (Architectural.md Section 11) ---------------------------

ROUTES: list[tuple[str, str, set[str]]] = [
    # method, path, roles allowed (everyone else: 401 without a token, 403 with one)
    ("GET", "/api/admin/kb", {"staff", "admin"}),
    ("GET", "/api/admin/documents", {"staff", "admin"}),
    ("GET", "/api/admin/approvals", {"staff", "admin"}),
    ("GET", "/api/admin/unanswered", {"staff", "admin"}),
    ("GET", "/api/admin/review", {"staff", "admin"}),
    ("GET", "/api/admin/tables/fees", {"staff", "admin"}),
    ("GET", "/api/admin/lookups", {"staff", "admin"}),
    ("GET", "/api/admin/users", {"admin"}),
    ("GET", "/api/admin/audit", {"admin"}),
    ("GET", "/api/admin/metrics", {"admin"}),
    ("GET", "/api/admin/settings", {"admin"}),
    ("GET", "/api/me", {"student", "staff", "admin"}),
]


@pytest.mark.parametrize("who", ["anonymous", "student", "staff", "admin"])
@pytest.mark.parametrize(("method", "path", "roles"), ROUTES)
async def test_rbac_matrix(
    api: httpx.AsyncClient, people: People, who: str, method: str, path: str, roles: set[str]
) -> None:
    response = await api.request(method, path, headers=people.headers(who))
    expected = 200 if who in roles else 401 if who == "anonymous" else 403
    assert response.status_code == expected, response.text


async def test_only_an_admin_approves(api: httpx.AsyncClient, people: People) -> None:
    created = await api.post(
        "/api/admin/kb", json=entry(submit=True), headers=people.headers("staff")
    )
    entry_id = created.json()["id"]
    path = f"/api/admin/approvals/kb/{entry_id}/approve"
    assert (await api.post(path, headers=people.headers("staff"))).status_code == 403
    assert (await api.post(path, headers=people.headers("student"))).status_code == 403
    assert (await api.post(path, headers=people.headers("admin"))).status_code == 200


# --- staff scope ------------------------------------------------------------------------------


async def test_staff_content_defaults_to_their_office(
    api: httpx.AsyncClient, people: People, offices: dict[str, uuid.UUID]
) -> None:
    created = await api.post("/api/admin/kb", json=entry(), headers=people.headers("staff"))
    assert created.status_code == 201
    body = created.json()
    assert body["office_id"] == str(offices["Admission Office"])
    assert body["status"] == "draft" and body["can_edit"] is True


async def test_staff_cannot_create_or_edit_another_offices_content(
    api: httpx.AsyncClient, people: People, offices: dict[str, uuid.UUID]
) -> None:
    exam = str(offices["Exam Office"])
    refused = await api.post(
        "/api/admin/kb", json=entry(office_id=exam), headers=people.headers("staff")
    )
    assert refused.status_code == 403
    theirs = await api.post("/api/admin/kb", json=entry(), headers=people.headers("exam"))
    entry_id = theirs.json()["id"]
    edit = await api.put(
        f"/api/admin/kb/{entry_id}",
        json=entry(office_id=exam, answer="Changed by the wrong office, which must not work."),
        headers=people.headers("staff"),
    )
    assert edit.status_code == 403
    listed = await api.get("/api/admin/kb", headers=people.headers("staff"))
    mine = {e["id"]: e["can_edit"] for e in listed.json()}
    assert mine[entry_id] is False


async def test_staff_cannot_move_their_entry_out_of_their_scope(
    api: httpx.AsyncClient, people: People, offices: dict[str, uuid.UUID]
) -> None:
    created = await api.post("/api/admin/kb", json=entry(), headers=people.headers("staff"))
    moved = await api.put(
        f"/api/admin/kb/{created.json()['id']}",
        json=entry(office_id=str(offices["Exam Office"])),
        headers=people.headers("staff"),
    )
    assert moved.status_code == 403


# --- exit criterion: staff edit, admin approves, the chat reflects it -----------------------


async def test_staff_entry_approved_by_admin_is_answered_by_the_chat(
    api: httpx.AsyncClient, people: People, services: ChatServices, db_session: AsyncSession
) -> None:
    created = await api.post(
        "/api/admin/kb", json=entry(submit=True), headers=people.headers("staff")
    )
    assert created.status_code == 201 and created.json()["status"] == "pending"
    entry_id = created.json()["id"]

    before = await turn(services, "Is there an evening shuttle to Gulberg?")
    assert all("Gulberg" not in s["title"] for e in before.of("sources") for s in e["items"])

    queue = await api.get("/api/admin/approvals", headers=people.headers("admin"))
    item = next(a for a in queue.json() if a["id"] == entry_id)
    assert item["current"] is None and item["proposed"]["title"] == "Evening shuttle to Gulberg"

    approved = await api.post(
        f"/api/admin/approvals/kb/{entry_id}/approve", headers=people.headers("admin")
    )
    assert approved.status_code == 200
    assert approved.json()["embedded"] is True and approved.json()["chunks"] >= 1

    after = await turn(services, "Is there an evening shuttle to Gulberg?")
    titles = [s["title"] for e in after.of("sources") for s in e["items"]]
    assert "Evening shuttle to Gulberg" in titles
    assert "17:30" in after.text()

    actions = await db_session.execute(
        select(AuditLog.action, AuditLog.actor_label)
        .where(AuditLog.row_id == uuid.UUID(entry_id))
        .order_by(AuditLog.created_at)
    )
    assert [tuple(r) for r in actions] == [
        ("create", "staff:staff@test.edu"),
        ("approve", "admin:admin@test.edu"),
    ]


async def test_reject_needs_a_reason_and_returns_the_entry_to_draft(
    api: httpx.AsyncClient, people: People
) -> None:
    created = await api.post(
        "/api/admin/kb", json=entry(submit=True), headers=people.headers("staff")
    )
    path = f"/api/admin/approvals/kb/{created.json()['id']}/reject"
    empty = await api.post(path, json={"comment": " "}, headers=people.headers("admin"))
    assert empty.status_code == 400
    rejected = await api.post(
        path, json={"comment": "Add the route"}, headers=people.headers("admin")
    )
    assert rejected.status_code == 200 and rejected.json()["status"] == "draft"
    again = await api.get(f"/api/admin/kb/{created.json()['id']}", headers=people.headers("staff"))
    assert again.json()["rejected_reason"] == "Add the route"


async def test_expiry_must_be_after_last_verified(api: httpx.AsyncClient, people: People) -> None:
    response = await api.post(
        "/api/admin/kb", json=entry(expires_at="2026-10-01"), headers=people.headers("staff")
    )
    assert response.status_code == 422


# --- users (ADM-4) ------------------------------------------------------------------------------


async def test_admin_creates_a_staff_account_and_it_is_audited(
    api: httpx.AsyncClient, people: People, offices: dict[str, uuid.UUID], db_session: AsyncSession
) -> None:
    created = await api.post(
        "/api/admin/users",
        json={
            "email": "New.Person@Test.edu", "password": "temporary-pass-1",
            "full_name": "New Person", "role": "staff", "office_id": str(offices["Exam Office"]),
        },
        headers=people.headers("admin"),
    )  # fmt: skip
    assert created.status_code == 201, created.text
    assert created.json()["email"] == "new.person@test.edu"
    duplicate = await api.post(
        "/api/admin/users",
        json={"email": "new.person@test.edu", "password": "temporary-pass-1",
              "full_name": "Again", "office_id": str(offices["Exam Office"])},
        headers=people.headers("admin"),
    )  # fmt: skip
    assert duplicate.status_code == 400
    audit_row = await db_session.execute(
        select(AuditLog.action).where(
            AuditLog.table_name == "profiles", AuditLog.row_id == uuid.UUID(created.json()["id"])
        )
    )
    assert audit_row.scalar_one() == "create"


async def test_staff_need_a_department_or_office(api: httpx.AsyncClient, people: People) -> None:
    response = await api.post(
        "/api/admin/users",
        json={"email": "x@test.edu", "password": "temporary-pass-1", "full_name": "No Scope"},
        headers=people.headers("admin"),
    )
    assert response.status_code == 400


async def test_an_admin_cannot_deactivate_themselves(
    api: httpx.AsyncClient, people: People
) -> None:
    response = await api.patch(
        f"/api/admin/users/{people.ids['admin']}",
        json={"is_active": False},
        headers=people.headers("admin"),
    )
    assert response.status_code == 400


# --- audit log, metrics, settings ---------------------------------------------------------------


async def test_audit_log_filters_by_actor_and_table(api: httpx.AsyncClient, people: People) -> None:
    await api.post("/api/admin/kb", json=entry(), headers=people.headers("staff"))
    page = await api.get(
        "/api/admin/audit",
        params={"actor": "staff@test.edu", "table": "kb_entries"},
        headers=people.headers("admin"),
    )
    assert page.status_code == 200
    items = page.json()["items"]
    assert items and all(i["actor_label"] == "staff:staff@test.edu" for i in items)
    assert "kb_entries" in page.json()["tables"]


async def test_metrics_count_todays_questions(
    api: httpx.AsyncClient, people: People, services: ChatServices
) -> None:
    await turn(services, "What are the fees for BSCS?")
    await turn(services, "What are the fees for BSCS?")
    response = await api.get("/api/admin/metrics", headers=people.headers("admin"))
    assert response.status_code == 200
    body = response.json()
    assert body["questions_today"] == 2
    assert body["top_questions"][0] == {"label": "what are the fees for bscs?", "count": 2}
    assert len(body["days"]) == 14 and body["avg_latency_ms"] is not None


async def test_settings_change_is_audited_and_shown_in_the_public_config(
    api: httpx.AsyncClient, people: People
) -> None:
    current = (await api.get("/api/admin/settings", headers=people.headers("admin"))).json()
    current["disclaimer"] = "Answers are checked by LGU offices. Confirm decisions with them."
    current["starter_questions"] = ["How do I apply?"]
    saved = await api.put("/api/admin/settings", json=current, headers=people.headers("admin"))
    assert saved.status_code == 200
    public = (await api.get("/api/config")).json()
    assert public["disclaimer"] == current["disclaimer"]
    assert public["starter_questions"] == ["How do I apply?"]
    audit_page = await api.get(
        "/api/admin/audit", params={"table": "institutions"}, headers=people.headers("admin")
    )
    assert set(audit_page.json()["items"][0]["diff"]) == {"disclaimer", "starter_questions"}


# --- student accounts: profile, private chats, "Delete my data" -----------------------------


async def test_student_profile_can_be_saved(api: httpx.AsyncClient, people: People) -> None:
    saved = await api.put(
        "/api/me/profile",
        json={"program": "BSCS", "semester": 3, "section": "B", "language_pref": "ur"},
        headers=people.headers("student"),
    )
    assert saved.status_code == 200
    assert saved.json()["semester"] == 3 and saved.json()["is_anonymous"] is True
    bad = await api.put("/api/me/profile", json={"semester": 13}, headers=people.headers("student"))
    assert bad.status_code == 422


async def test_a_signed_in_students_chat_is_private_and_can_be_deleted(
    api: httpx.AsyncClient, people: People, services: ChatServices, db_session: AsyncSession
) -> None:
    people.headers("student")  # assigns the student's id
    student = people.ids["student"]
    await api.get("/api/me", headers=people.headers("student"))  # creates the profile
    events = await _turn_as(services, student, "What are the fees for BSCS?")
    conversation_id = events.of("ack")[0]["conversation_id"]
    path = f"/api/conversations/{conversation_id}/messages"
    assert (await api.get(path, headers=people.headers("student"))).status_code == 200
    assert (await api.get(path)).status_code == 404  # anonymous holder of the id
    assert (await api.get(path, headers=people.headers("staff"))).status_code == 404

    deleted = await api.delete("/api/me/data", headers=people.headers("student"))
    assert deleted.status_code == 200 and deleted.json() == {"conversations": 1}
    left = await db_session.execute(select(Conversation).where(Conversation.user_id == student))
    assert left.scalars().all() == []
    audit_row = await db_session.execute(
        select(AuditLog.diff).where(AuditLog.action == "delete_my_data")
    )
    assert audit_row.scalar_one() == {"conversations": 1}  # counts only, no chat text


async def _turn_as(
    services: ChatServices, user_id: uuid.UUID, text: str, conversation_id: Any = None
) -> Events:
    events = Events()
    await run_turn(
        services, events, client_key="1.2.3.4", conversation_id=conversation_id, text=text,
        user_id=user_id,
    )  # fmt: skip
    return events


async def test_a_signed_in_student_claims_their_anonymous_chat(
    api: httpx.AsyncClient, people: People, services: ChatServices
) -> None:
    first = await turn(services, "What are the fees for BSCS?")
    conversation_id = uuid.UUID(first.of("ack")[0]["conversation_id"])
    people.headers("student")
    second = await _turn_as(services, people.ids["student"], "And for BBA?")
    assert second.of("ack")[0]["conversation_id"] != str(conversation_id)  # no id sent: new chat

    events = await _turn_as(services, people.ids["student"], "And for BBA?", conversation_id)
    assert events.of("ack")[0]["conversation_id"] == str(conversation_id)
    path = f"/api/conversations/{conversation_id}/messages"
    assert (await api.get(path)).status_code == 404  # now theirs alone


# --- local sign-in and deadlines ---------------------------------------------------------------


async def test_dev_login_signs_in_staff_by_email(api: httpx.AsyncClient, people: People) -> None:
    response = await api.post("/api/auth/dev-login", json={"email": "Staff@test.edu"})
    assert response.status_code == 200
    token = response.json()["access_token"]
    me = await api.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["role"] == "staff" and "edit_content" in me.json()["permissions"]
    assert (await api.post("/api/auth/dev-login", json={"email": "nobody@x.y"})).status_code == 401


async def test_dev_login_is_off_without_dev_auth(services: ChatServices) -> None:
    app = create_app(make_settings())
    async with running_client(app) as client:
        app.state.chat = services
        response = await client.post("/api/auth/dev-login", json={})
    assert response.status_code == 404


async def test_deadlines_show_upcoming_dates_soonest_first(
    api: httpx.AsyncClient, services: ChatServices, db_session: AsyncSession
) -> None:
    inst = await institution_id_for(db_session, "lgu")
    today = services.today()
    for title, days in (("Fee deadline", 10), ("Midterms start", 3), ("Long ago", -30)):
        db_session.add(
            KeyDate(institution_id=inst, title=title, date=today + timedelta(days=days),
                    kind="academic", office_name="Exam Office")
        )  # fmt: skip
    await db_session.flush()
    response = await api.get("/api/deadlines")
    assert response.status_code == 200
    rows = response.json()
    assert [r["title"] for r in rows] == ["Midterms start", "Fee deadline"]
    assert rows[0]["days_left"] == 3


# --- successful updates (regression: updated_at is set by the database on UPDATE and must be
# returned by the flush, or reading it afterwards crashes with MissingGreenlet) -------------


async def test_staff_edit_their_entry_and_archive_it(
    api: httpx.AsyncClient, people: People
) -> None:
    created = await api.post("/api/admin/kb", json=entry(), headers=people.headers("staff"))
    entry_id = created.json()["id"]
    edited = await api.put(
        f"/api/admin/kb/{entry_id}",
        json=entry(answer="The evening shuttle to Gulberg now leaves at 18:00 on weekdays."),
        headers=people.headers("staff"),
    )
    assert edited.status_code == 200, edited.text
    assert "18:00" in edited.json()["answer"]
    assert edited.json()["updated_at"] >= created.json()["updated_at"]
    archived = await api.post(f"/api/admin/kb/{entry_id}/archive", headers=people.headers("staff"))
    assert archived.status_code == 200, archived.text
    assert archived.json()["status"] == "archived"


async def test_an_approved_entry_goes_back_to_pending_when_edited(
    api: httpx.AsyncClient, people: People
) -> None:
    created = await api.post(
        "/api/admin/kb", json=entry(submit=True), headers=people.headers("staff")
    )
    entry_id = created.json()["id"]
    await api.post(f"/api/admin/approvals/kb/{entry_id}/approve", headers=people.headers("admin"))
    edited = await api.put(
        f"/api/admin/kb/{entry_id}",
        json=entry(answer="The evening shuttle to Gulberg leaves from Block D at 17:30."),
        headers=people.headers("staff"),
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["status"] == "pending"
    queue = await api.get("/api/admin/approvals", headers=people.headers("admin"))
    item = next(a for a in queue.json() if a["id"] == entry_id)
    assert "Block D" not in item["current"]["answer"] and "Block D" in item["proposed"]["answer"]


async def test_admin_edits_and_deletes_a_fee_row(api: httpx.AsyncClient, people: People) -> None:
    body = {"program_group": "Test program", "fiscal_year": "2026-27", "admission_fee": 15000,
            "last_verified": "2026-11-01", "source_name": "Fee notice"}  # fmt: skip
    created = await api.post("/api/admin/tables/fees", json=body, headers=people.headers("admin"))
    assert created.status_code == 201, created.text
    row_id = created.json()["id"]
    edited = await api.put(
        f"/api/admin/tables/fees/{row_id}",
        json={**body, "admission_fee": 16000},
        headers=people.headers("admin"),
    )
    assert edited.status_code == 200, edited.text
    assert float(edited.json()["admission_fee"]) == 16000
    deleted = await api.delete(f"/api/admin/tables/fees/{row_id}", headers=people.headers("admin"))
    assert deleted.status_code == 204


async def test_document_submit_and_archive(api: httpx.AsyncClient, people: People) -> None:
    from tests.support.pdf import make_pdf

    pdf = make_pdf(["Hostel gates close at 22:00 every night."] * 20)
    uploaded = await api.post(
        "/api/admin/documents",
        params={"title": "Hostel SOP", "category": "hostel", "last_verified": "2026-11-01",
                "expires_at": "2027-11-01"},
        content=pdf,
        headers={**people.headers("staff"), "Content-Type": "application/pdf"},
    )  # fmt: skip
    assert uploaded.status_code == 201, uploaded.text
    archived = await api.post(
        f"/api/admin/documents/{uploaded.json()['id']}/archive", headers=people.headers("staff")
    )
    assert archived.status_code == 200, archived.text
    assert archived.json()["status"] == "archived"


# --- Word (.docx) uploads (DATA-3) ------------------------------------------------------------

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


async def test_a_word_file_is_previewed_uploaded_approved_and_answered(
    api: httpx.AsyncClient, people: People, services: ChatServices
) -> None:
    from tests.support.docx import make_docx, paragraph, table

    body = paragraph("Hostel SOP for the Girls Hostel") + paragraph(
        "The girls hostel warden office is in Block H, room 4, open 09:00 to 17:00."
    ) + table([["Item", "Charge"], ["Hostel security deposit", "Rs 10,000"]])  # fmt: skip
    data = make_docx(body)
    headers = {**people.headers("staff"), "Content-Type": DOCX_MIME}

    preview = await api.post("/api/admin/documents/preview", content=data, headers=headers)
    assert preview.status_code == 200, preview.text
    assert preview.json()["pages"] is None and preview.json()["chunks"] >= 1
    assert "Hostel security deposit | Rs 10,000" in preview.json()["text_preview"]

    uploaded = await api.post(
        "/api/admin/documents",
        params={"title": "Girls Hostel SOP", "category": "hostel", "last_verified": "2026-11-01",
                "expires_at": "2027-11-01"},
        content=data,
        headers=headers,
    )  # fmt: skip
    assert uploaded.status_code == 201, uploaded.text
    assert uploaded.json()["mime"] == DOCX_MIME and uploaded.json()["status"] == "pending"

    approved = await api.post(
        f"/api/admin/approvals/document/{uploaded.json()['id']}/approve",
        headers=people.headers("admin"),
    )
    assert approved.status_code == 200 and approved.json()["chunks"] >= 1
    events = await turn(services, "Where is the girls hostel warden office?")
    titles = [s["title"] for e in events.of("sources") for s in e["items"]]
    assert "Girls Hostel SOP" in titles
    assert "Block H" in events.text()


@pytest.mark.parametrize(
    ("content_type", "status"),
    [("text/plain", 415), ("application/msword", 415), (DOCX_MIME, 422)],
)
async def test_unsupported_or_broken_uploads_are_refused(
    api: httpx.AsyncClient, people: People, content_type: str, status: int
) -> None:
    response = await api.post(
        "/api/admin/documents/preview",
        content=b"definitely not a document",
        headers={**people.headers("staff"), "Content-Type": content_type},
    )
    assert response.status_code == status, response.text
