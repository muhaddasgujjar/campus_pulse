"""Typed, parameterized agent tools (D3, D10, ANS-2).

The registry maps a tool name to its argument model and function. The planner LLM sees the
names, descriptions and JSON schemas; it can only pick one and fill its arguments, which are
validated here before any query runs. search_knowledge (RAG) is added in tools/search.py.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from app.tools.base import Source, ToolContext, ToolResult
from app.tools.dates import KeyDatesArgs, get_key_dates
from app.tools.faculty import FacultyArgs, find_faculty
from app.tools.fees import FeeArgs, get_fee
from app.tools.offices import OfficeArgs, get_office
from app.tools.timetable import TimetableArgs, get_timetable


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    args_model: type[BaseModel]
    func: Callable[[ToolContext, Any], Awaitable[ToolResult]]

    def json_schema(self) -> dict[str, Any]:
        return self.args_model.model_json_schema()


STRUCTURED_TOOLS: dict[str, ToolSpec] = {
    spec.name: spec
    for spec in (
        ToolSpec(
            "get_timetable",
            "Class timetable for a program, semester and optional section and day.",
            TimetableArgs,
            get_timetable,
        ),
        ToolSpec(
            "find_faculty",
            "Find teachers by name, department or course.",
            FacultyArgs,
            find_faculty,
        ),
        ToolSpec(
            "get_fee",
            "Fee structure (admission fee, tuition per credit hour, misc) for a program.",
            FeeArgs,
            get_fee,
        ),
        ToolSpec(
            "get_office",
            "Contact details (phones, email, hours, location) of an office by name or topic.",
            OfficeArgs,
            get_office,
        ),
        ToolSpec(
            "get_key_dates",
            "Deadlines and academic dates (admission, fee, scholarship, exam, semester).",
            KeyDatesArgs,
            get_key_dates,
        ),
    )
}


async def run_tool(ctx: ToolContext, name: str, raw_args: dict[str, Any]) -> ToolResult:
    """Validate arguments against the tool's model, then run it. Raises ValueError/KeyError."""
    spec = STRUCTURED_TOOLS[name]
    args = spec.args_model.model_validate(raw_args)
    return await spec.func(ctx, args)


__all__ = ["STRUCTURED_TOOLS", "Source", "ToolContext", "ToolResult", "ToolSpec", "run_tool"]
