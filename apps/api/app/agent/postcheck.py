"""Post-checks on LLM answers (Architectural.md Section 6, PRD metric: 0 invented numbers).

An LLM answer is rejected when it contains a number that is not in the tool data, the
question or today's date. The agent then uses the template or extractive answer instead.
The checks also add what the composer must never omit: the fiscal year for fees and the
"this date has passed" notice.
"""

import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.tools.base import ToolResult

_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _norm(token: str) -> str:
    token = token.replace(",", "")
    if "." in token:
        token = token.rstrip("0").rstrip(".")
    return token.lstrip("0") or "0"


def numbers_in(text: str) -> set[str]:
    return {_norm(m) for m in _NUMBER.findall(text)}


def collect_numbers(value: Any, out: set[str]) -> None:
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, date):
        out.update({_norm(str(value.day)), _norm(str(value.month)), str(value.year)})
        out.update(numbers_in(value.isoformat()))
    elif isinstance(value, int | float):
        out.add(_norm(f"{value:.2f}") if isinstance(value, float) else _norm(str(value)))
        out.add(_norm(str(abs(value))))
    elif isinstance(value, str):
        out.update(numbers_in(value))
    elif isinstance(value, dict):
        for item in value.values():
            collect_numbers(item, out)
    elif isinstance(value, list | tuple):
        for item in value:
            collect_numbers(item, out)


def allowed_numbers(results: list[ToolResult], query: str, today: date) -> set[str]:
    allowed = numbers_in(query)
    collect_numbers(today, allowed)
    for result in results:
        collect_numbers(result.data, allowed)
        collect_numbers(result.last_verified, allowed)
        for source in result.sources:
            collect_numbers(source.title, allowed)
            collect_numbers(source.last_verified, allowed)
    return allowed


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    invented: set[str]
    answer: str


def check_llm_answer(
    answer: str, results: list[ToolResult], query: str, today: date
) -> CheckResult:
    if not answer.strip() or answer.strip().upper().startswith("NO_ANSWER"):
        return CheckResult(False, set(), answer)
    invented = numbers_in(answer) - allowed_numbers(results, query, today)
    if invented:
        return CheckResult(False, invented, answer)
    return CheckResult(True, set(), ensure_required_notes(answer, results))


def ensure_required_notes(answer: str, results: list[ToolResult]) -> str:
    """Append the fiscal year and passed-date notices if the composer left them out."""
    extra: list[str] = []
    for result in results:
        if result.tool == "get_fee" and result.data:
            fiscal_year = result.data[0]["fiscal_year"]
            if fiscal_year not in answer:
                extra.append(f"(Fee figures are for FY {fiscal_year}.)")
        if result.tool == "get_key_dates":
            passed = [row for row in result.data if row["passed"]]
            if passed and "passed" not in answer.lower():
                office = passed[0].get("office") or "the relevant office"
                extra.append(f"This date has passed. Please confirm with the {office}.")
    return answer if not extra else answer.rstrip() + "\n" + " ".join(extra)
