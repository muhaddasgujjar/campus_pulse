"""Planning: one LLM call (fast model, JSON) that picks intent + tool + args + retrieval query,
with a rule-based planner used when the LLM is unavailable, out of quota or returns invalid
JSON (Architectural.md Section 6). Rules also short-circuit greetings and private-record
requests without spending any LLM call.
"""

import json
import re
from datetime import date, timedelta
from typing import Any

from pydantic import ValidationError

from app.agent.state import Plan, StudentProfile
from app.tools import STRUCTURED_TOOLS

# --- rule patterns ---------------------------------------------------------------------------

_SMALLTALK = re.compile(
    r"^\s*(hi+|hello|hey|salam|salaam|assalam\s*[ou]?\s*alaikum|aoa|good\s+(morning|afternoon|"
    r"evening)|thanks?|thank\s+you|shukriya|jazakallah|bye|ok(ay)?|great|nice)\b[\s!.?]*\w*[\s!.?]*$",
    re.IGNORECASE,
)
_PRIVATE = re.compile(
    r"\b(my|mera|meri|mere)\s+(result|results|attendance|cgpa|gpa|marks|grades?|fee\s+status|"
    r"challan|transcript|roll\s*number)\b|\b(password|portal\s+login|hack)\b",
    re.IGNORECASE,
)
_SENSITIVE = re.compile(
    r"\b(legal\s+advice|lawyer|sue|medical\s+advice|medicine|diagnos\w*|disciplinary|"
    r"suspend\w*|expel\w*)\b",
    re.IGNORECASE,
)
_TIMETABLE = re.compile(r"\b(time\s*table|schedule|classes|class\s+timings?|lectures?)\b", re.I)
_DATES = re.compile(
    r"\b(deadline|last\s+date|due\s+date|when|kab|date|dates|tareekh|start\s+date|"
    r"akhri\s+tareekh|still\s+apply)\b",
    re.IGNORECASE,
)
_FEE = re.compile(
    r"\b(fee|fees|tuition|charges|dues|cost|per\s+credit|credit\s+hours?)\b", re.IGNORECASE
)
_OFFICE = re.compile(
    r"\b(phone|number|contact|email|e-mail|call|address|location|where\s+is|office\s+hours|"
    r"timings?|open|rabta)\b",
    re.IGNORECASE,
)
_FACULTY = re.compile(
    r"\b(teacher|teaches|faculty\s+member|professor|lecturer|instructor)\b|\bdr\.", re.I
)
_EXPLAIN = re.compile(
    r"\b(why|explain|compare|comparison|difference|calculate|total|in\s+total|altogether|"
    r"kyun|farq)\b",
    re.IGNORECASE,
)

_PROGRAM = re.compile(
    r"\b(BS\s?CySec|BS\s?[A-Z]{2,4}|BBA|MBA|MCS|MS\s?[A-Z]{2,4}|ADP|HND)\b", re.IGNORECASE
)
_PROGRAM_PHRASES = {"computer science": "computer sciences", "software engineering": "BSSE",
                    "information technology": "BSIT", "data science": "BSDS",
                    "artificial intelligence": "BSAI", "cyber security": "BS CySec",
                    "cybersecurity": "BS CySec"}  # fmt: skip
_SEMESTER = re.compile(
    r"\b(?:semester|sem)\s*(\d{1,2})\b|\b(\d{1,2})(?:st|nd|rd|th)\s+(?:semester|sem)\b", re.I
)
_SECTION = re.compile(r"\bsection\s+([A-Za-z])\b", re.IGNORECASE)
_DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
# Title in any case, then one or two capitalised words (the name itself stays case-sensitive).
_NAME = re.compile(
    r"\b(?i:dr\.?|sir|madam|ma'?am|professor|prof\.?)\s+([A-Z][\w.'-]+(?:\s+[A-Z][\w.'-]+)?)"
)
_COURSE = re.compile(r"\b([A-Z]{2,5}-?\d{3})\b")

_DATE_KINDS = (
    (re.compile(r"\b(apply|application|admission|admissions|dakhla)\b", re.I), "admission"),
    (re.compile(r"\b(scholarship|financial\s+aid)\b", re.I), "scholarship"),
    (re.compile(r"\b(exam|exams|mid\s*term|final|datesheet)\b", re.I), "exam"),
    (re.compile(r"\b(fee|fees|challan)\b", re.I), "fee"),
    (re.compile(r"\b(semester|classes)\s+(start|begin)", re.I), "semester"),
)


def find_program(text: str) -> str | None:
    lowered = text.lower()
    for phrase, program in _PROGRAM_PHRASES.items():
        if phrase in lowered:
            return program
    match = _PROGRAM.search(text)
    return match.group(1).upper().replace("CYSEC", "CySec") if match else None


def find_day(text: str, today: date) -> int | None:
    lowered = text.lower()
    if "today" in lowered or " aaj" in f" {lowered}":
        return today.isoweekday()
    if "tomorrow" in lowered or " kal" in f" {lowered}":
        return (today + timedelta(days=1)).isoweekday()
    for number, name in enumerate(_DAYS, start=1):
        if name in lowered or name[:3] + " " in lowered + " ":
            return number
    return None


def rule_plan(query: str, profile: StudentProfile | None, today: date) -> Plan:
    """Keyword routing. Cheap, deterministic, and good enough when no LLM is available."""
    text = query.strip()
    if _SMALLTALK.match(text):
        return Plan(intent="smalltalk")
    if _PRIVATE.search(text) or _SENSITIVE.search(text):
        return Plan(intent="out_of_scope")

    program = find_program(text) or (profile.program if profile else None)

    if _TIMETABLE.search(text):
        sem_match = _SEMESTER.search(text)
        semester = int(next(g for g in sem_match.groups() if g)) if sem_match else None
        semester = semester or (profile.semester if profile else None)
        section_match = _SECTION.search(text)
        section = (
            section_match.group(1) if section_match else (profile.section if profile else None)
        )
        if program and semester:
            args: dict[str, Any] = {"program": program, "semester": semester}
            if section:
                args["section"] = section
            day = find_day(text, today)
            if day:
                args["day"] = day
            return Plan(intent="structured", tool="get_timetable", args=args)
        return Plan(intent="knowledge", retrieval_query=text)

    if _DATES.search(text) and not _OFFICE.search(text):
        args = {}
        for pattern, kind in _DATE_KINDS:
            if pattern.search(text):
                args["kind"] = kind
                break
        return Plan(intent="structured", tool="get_key_dates", args=args)

    if _FEE.search(text) and program:
        return Plan(intent="structured", tool="get_fee", args={"program_group": program})

    if _OFFICE.search(text):
        return Plan(intent="structured", tool="get_office", args={"name_or_topic": text[:120]})

    if _FACULTY.search(text):
        name = _NAME.search(text)
        course = _COURSE.search(text)
        if name or course:
            faculty_args = {"name": name.group(1)} if name else {"course": course.group(1)}  # type: ignore[union-attr]
            return Plan(intent="structured", tool="find_faculty", args=faculty_args)

    return Plan(intent="knowledge", retrieval_query=text)


def wants_explanation(query: str) -> bool:
    """Exact-data answers use templates unless the user asks for an explanation/comparison."""
    return bool(_EXPLAIN.search(query))


# --- LLM planning ----------------------------------------------------------------------------


def _nullable(schema: dict[str, Any]) -> dict[str, Any]:
    return {"anyOf": [schema, {"type": "null"}]}


# Standard JSON Schema (sent as Gemini's response_json_schema), so null uses anyOf.
PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "enum": ["structured", "knowledge", "live", "smalltalk", "out_of_scope"],
        },
        "tool": _nullable({"type": "string", "enum": [*STRUCTURED_TOOLS]}),
        "args": {"type": "object"},
        "retrieval_query": _nullable({"type": "string"}),
        "category": _nullable({"type": "string"}),
    },
    "required": ["intent"],
}


def parse_plan(raw: dict[str, Any] | None) -> Plan | None:
    """Validate the LLM's JSON. Unknown tools or bad arguments are rejected (D10)."""
    if not raw:
        return None
    try:
        plan = Plan.model_validate(raw)
    except ValidationError:
        return None
    if plan.intent == "structured":
        if plan.tool not in STRUCTURED_TOOLS:
            return None
        try:
            STRUCTURED_TOOLS[plan.tool].args_model.model_validate(plan.args)
        except ValidationError:
            return None
    if plan.intent in ("knowledge", "live") and not plan.retrieval_query:
        return None
    return plan


def tool_catalog() -> str:
    return json.dumps(
        [
            {"name": s.name, "description": s.description, "args_schema": s.json_schema()}
            for s in STRUCTURED_TOOLS.values()
        ],
        indent=1,
    )
