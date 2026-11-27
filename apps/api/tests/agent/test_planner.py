"""Rule planner, LLM plan validation (D10) and language detection. No LLM, no database."""

from datetime import date

import pytest

from app.agent.language import detect_language
from app.agent.planner import (
    PLAN_SCHEMA,
    asks_office_hours,
    is_follow_up,
    parse_plan,
    rule_plan,
    wants_explanation,
)
from app.agent.state import StudentProfile

TODAY = date(2026, 10, 5)  # a Monday


@pytest.mark.parametrize("text", ["hello", "Hi!", "Assalam o alaikum", "thanks", "shukriya"])
def test_greetings_and_thanks_are_smalltalk(text: str) -> None:
    assert rule_plan(text, None, TODAY).intent == "smalltalk"


@pytest.mark.parametrize(
    "text",
    [
        "What is my result?",
        "show my attendance",
        "mera fee status kya hai",
        "What is the portal password?",
        "I need legal advice about my case",
    ],
)
def test_private_records_and_sensitive_topics_are_out_of_scope(text: str) -> None:
    assert rule_plan(text, None, TODAY).intent == "out_of_scope"


def test_fee_question_with_program_uses_get_fee() -> None:
    plan = rule_plan("What are the fees for BSCS?", None, TODAY)
    assert (plan.intent, plan.tool, plan.args) == (
        "structured",
        "get_fee",
        {"program_group": "BSCS"},
    )


def test_fee_question_takes_the_program_from_the_profile() -> None:
    plan = rule_plan("How much is the fee?", StudentProfile(program="BBA"), TODAY)
    assert plan.tool == "get_fee"
    assert plan.args == {"program_group": "BBA"}


def test_deadline_question_uses_get_key_dates_with_kind() -> None:
    plan = rule_plan("When is the last date to apply?", None, TODAY)
    assert (plan.tool, plan.args) == ("get_key_dates", {"kind": "admission"})


def test_contact_question_uses_get_office() -> None:
    plan = rule_plan("What is the phone number of the exam office?", None, TODAY)
    assert plan.tool == "get_office"
    assert "exam office" in plan.args["name_or_topic"]


def test_timetable_defaults_missing_args_from_profile() -> None:
    profile = StudentProfile(program="BSCS", semester=3, section="A")
    plan = rule_plan("What is my timetable tomorrow?", profile, TODAY)
    assert plan.tool == "get_timetable"
    assert plan.args == {"program": "BSCS", "semester": 3, "section": "A", "day": 2}


def test_explicit_args_beat_the_profile() -> None:
    profile = StudentProfile(program="BBA", semester=1)
    plan = rule_plan("BSSE 5th semester section B timetable", profile, TODAY)
    assert plan.args == {"program": "BSSE", "semester": 5, "section": "B"}


def test_timetable_without_program_and_semester_falls_to_knowledge() -> None:
    assert rule_plan("timetable please", None, TODAY).intent == "knowledge"


def test_faculty_by_title_and_name() -> None:
    plan = rule_plan("Which courses does Dr. Test Faculty teach?", None, TODAY)
    assert (plan.tool, plan.args) == ("find_faculty", {"name": "Test Faculty"})


def test_everything_else_is_a_knowledge_search_with_the_question() -> None:
    plan = rule_plan("Can F.A students apply for computer science?", None, TODAY)
    assert plan.intent == "knowledge"
    assert plan.retrieval_query == "Can F.A students apply for computer science?"


@pytest.mark.parametrize(
    ("text", "expected"),
    [("What is the BSCS fee?", False), ("Why is the fee higher for BSCS?", True),
     ("Compare BBA and BSCS fees", True), ("fee ka farq kya hai", True)],
)  # fmt: skip
def test_wants_explanation(text: str, expected: bool) -> None:
    assert wants_explanation(text) is expected


# --- LLM plan validation: the LLM picks a tool and fills typed args, never SQL (D10) ---------


def test_valid_llm_plan_is_accepted() -> None:
    plan = parse_plan({"intent": "structured", "tool": "get_fee", "args": {"program_group": "BBA"}})
    assert plan is not None and plan.tool == "get_fee"


@pytest.mark.parametrize(
    "raw",
    [
        None,
        {},
        {"intent": "teleport"},
        {"intent": "structured", "tool": "run_sql", "args": {"sql": "drop table fees"}},
        {"intent": "structured", "tool": "get_timetable", "args": {"program": "BSCS"}},
        {"intent": "structured", "tool": None},
        {"intent": "knowledge"},
        {"intent": "knowledge", "retrieval_query": ""},
    ],
)
def test_invalid_llm_plans_are_rejected(raw: dict[str, object] | None) -> None:
    assert parse_plan(raw) is None


def test_plan_schema_is_standard_json_schema() -> None:
    """Sent as response_json_schema: no OpenAPI-only keywords such as `nullable`."""
    assert "nullable" not in str(PLAN_SCHEMA)
    assert PLAN_SCHEMA["properties"]["tool"]["anyOf"][1] == {"type": "null"}


# --- language detection (rule-based, D15) ---------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("What are the fees for BSCS?", "en"),
        ("Where is the main campus address?", "en"),
        ("main campus address", "en"),
        ("BSCS ki fee kitni hai?", "roman_ur"),
        ("admission kab tak hai", "roman_ur"),
        ("داخلہ کب ہے؟", "ur"),
        ("", "en"),
    ],
)
def test_detect_language(text: str, expected: str) -> None:
    assert detect_language(text) == expected


def test_credit_hours_live_in_the_fee_table() -> None:
    plan = rule_plan("How many credit hours are in semester 1 of BSCS?", None, TODAY)
    assert (plan.tool, plan.args) == ("get_fee", {"program_group": "BSCS"})


def test_can_i_still_apply_is_a_deadline_question() -> None:
    plan = rule_plan("Can I still apply for Fall 2026 admission?", None, TODAY)
    assert (plan.tool, plan.args) == ("get_key_dates", {"kind": "admission"})


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("What are the office timings?", True),
        ("office hours?", True),
        ("When is the office open?", True),
        ("Where is the LGU main campus?", False),
        ("What is the phone number of the exam office?", False),
    ],
)
def test_asks_office_hours(text: str, expected: bool) -> None:
    assert asks_office_hours(text) is expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("And semester 2?", True),
        ("What about BBA?", True),
        ("Is it open on Saturday?", True),
        ("aur BBA ki?", True),
        ("What are the fees for BSCS?", False),
        ("Exam office phone number?", False),
        (
            "Is this the right place to ask about scholarships for students in their final year?",
            False,
        ),
    ],
)
def test_is_follow_up(text: str, expected: bool) -> None:
    assert is_follow_up(text) is expected
