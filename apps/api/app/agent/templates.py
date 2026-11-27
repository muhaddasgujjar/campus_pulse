"""Template answers with 0 LLM calls (COST-2, ANS-13) and fixed UI copy (DESIGN.md Section 8).

Every number in a template comes straight from a tool row: templates cannot invent facts.
Missing fields are omitted, never guessed. English only for now; Urdu templates need a native
speaker review (DESIGN.md Section 8), so non-English questions use the LLM when available.
"""

from datetime import date
from typing import Any

from app.services.retrieval import coverage
from app.tools.base import ToolResult


def fmt_date(value: date) -> str:
    """DESIGN.md Section 10: 'Mon, 5 Oct 2026'."""
    return f"{value:%a}, {value.day} {value:%b %Y}"


def fmt_money(value: float) -> str:
    return f"Rs {value:,.0f}" if float(value).is_integer() else f"Rs {value:,.2f}"


def source_line(result: ToolResult) -> str:
    if not result.sources:
        return ""
    source = result.sources[0]
    parts = [f"Source: {source.title}"]
    if source.office and source.office not in source.title:
        parts.append(source.office)
    if result.last_verified:
        parts.append(f"last verified {fmt_date(result.last_verified)}")
    line = " · ".join(parts)
    if any(s.expired for s in result.sources):
        line += " · may be outdated, please confirm with the office"
    return line


def _fee(row: dict[str, Any]) -> str:
    facts = []
    if row["tuition_per_credit_hour"] is not None:
        facts.append(f"tuition is {fmt_money(row['tuition_per_credit_hour'])} per credit hour")
    if row["admission_fee"] is not None:
        facts.append(f"the admission fee is {fmt_money(row['admission_fee'])}")
    if row["misc_per_semester"] is not None:
        facts.append(
            f"miscellaneous charges are {fmt_money(row['misc_per_semester'])} per semester"
        )
    joined = (
        ", ".join(facts[:-1]) + (" and " if len(facts) > 1 else "") + facts[-1] if facts else ""
    )
    text = f"For {row['program_group']} (FY {row['fiscal_year']}), {joined}."
    if row.get("notes"):
        text += f" {row['notes']}"
    return text


def fee_answer(result: ToolResult) -> str:
    latest_year = result.data[0]["fiscal_year"]
    rows = [r for r in result.data if r["fiscal_year"] == latest_year]
    body = " ".join(_fee(r) for r in rows)
    if len(result.data) > len(rows):
        body += " Older fiscal years are also on record."
    return body


def office_answer(result: ToolResult) -> str:
    lines = []
    for row in result.data[:2]:
        parts = [row["name"]]
        if row["phones"]:
            parts.append("phone " + ", ".join(row["phones"]))
        if row["email"]:
            parts.append(f"email {row['email']}")
        if row["hours"]:
            parts.append(f"hours {row['hours']}")
        if row["location"]:
            parts.append(f"location {row['location']}")
        lines.append(": ".join([parts[0], "; ".join(parts[1:])]) if len(parts) > 1 else parts[0])
    return "\n".join(lines)


def key_dates_answer(result: ToolResult) -> str:
    lines = []
    for row in result.data[:5]:
        line = f"{row['title']}: {fmt_date(row['date'])}."
        if row["passed"]:
            office = row.get("office") or "the relevant office"
            line += f" This date has passed. Please confirm with the {office}."
        elif row["days_left"] == 0:
            line += " That is today."
        else:
            line += f" {row['days_left']} days left."
        lines.append(line)
    return "\n".join(lines)


def timetable_answer(result: ToolResult) -> str:
    first = result.data[0]
    header = f"{first['program']} semester {first['semester']}"
    if first.get("section"):
        header += f" section {first['section']}"
    lines = [f"{header} timetable:"]
    for row in result.data:
        details = [d for d in (row.get("room"), row.get("faculty")) if d]
        code = f" ({row['course_code']})" if row.get("course_code") else ""
        extra = f", {', '.join(details)}" if details else ""
        when = f"{row['day']} {row['start_time']} to {row['end_time']}"
        lines.append(f"- {when}: {row['course_name']}{code}{extra}")
    return "\n".join(lines)


def faculty_answer(result: ToolResult) -> str:
    lines = []
    for row in result.data[:5]:
        parts = [row["name"]]
        parts += [p for p in (row.get("designation"), row.get("department")) if p]
        text = ", ".join(parts) + "."
        if row.get("office_room"):
            text += f" Office: {row['office_room']}."
        if row.get("email"):
            text += f" Email: {row['email']}."
        lines.append(text)
    return "\n".join(lines)


RENDERERS = {
    "get_fee": fee_answer,
    "get_office": office_answer,
    "get_key_dates": key_dates_answer,
    "get_timetable": timetable_answer,
    "find_faculty": faculty_answer,
}


def structured_answer(result: ToolResult) -> str:
    body = RENDERERS[result.tool](result)
    line = source_line(result)
    return f"{body}\n{line}" if line else body


def best_passage(content: str, query: str, max_chars: int = 700) -> str:
    """The run of consecutive lines (at most max_chars) that covers most of the question's
    words. A KB entry ("Q: ... A: ...") is quoted by its answer."""
    if "\nA: " in content:
        content = content.split("\nA: ", 1)[1]
    if len(content) <= max_chars:
        return content.strip()
    lines = [line for line in content.splitlines() if line.strip()]
    best_score, best = -1.0, ""
    for start in range(len(lines)):
        window: list[str] = []
        size = 0
        for line in lines[start:]:
            if window and size + len(line) > max_chars:
                break
            window.append(line[:max_chars])
            size += len(line) + 1
        text = "\n".join(window)
        score = coverage(query, text)
        if score > best_score:  # ties keep the earlier passage
            best_score, best = score, text
    return best.strip()


def extractive_answer(result: ToolResult, query: str) -> str:
    """Knowledge answer without an LLM: quote the passage of the approved chunks that best
    covers the question (grounded by design: every word is the source's own)."""
    top = max(result.data, key=lambda row: coverage(query, f"{row['title']} {row['content']}"))
    owner = f" ({top['owner']})" if top.get("owner") else ""
    passage = best_passage(top["content"], query)
    text = f'According to "{top["title"]}"{owner}:\n{passage}'
    cited = [s for s in result.sources if s.title == top["title"]] or result.sources
    line = source_line(ToolResult(result.tool, [top], cited, top.get("last_verified")))
    return f"{text}\n{line}" if line else text


# --- fixed copy ----------------------------------------------------------------------------


def greeting(short_name: str) -> str:
    return f"Hi, I'm Campus Pulse. Ask me anything about {short_name}."


def thanks(short_name: str) -> str:
    return f"You're welcome! Ask me anything else about {short_name}."


def contact_text(office: dict[str, Any] | None) -> str:
    if not office:
        return "Please contact the university office."
    parts = [f"The {office['name']} can help"]
    details = []
    if office.get("phones"):
        details.append(", ".join(office["phones"]))
    if office.get("email"):
        details.append(office["email"])
    return parts[0] + (": " + "; ".join(details) if details else "") + "."


def fallback_text(office: dict[str, Any] | None) -> str:
    return f"I don't have verified information on this. {contact_text(office)}"


def out_of_scope_text(office: dict[str, Any] | None, *, private: bool = True) -> str:
    """A short refusal (ANS-12). Private-record wording only for private-record requests."""
    if private:
        return (
            "I can't help with that here. I can only answer from verified university "
            "information, and I can't access personal records such as results, attendance or "
            "fee status. " + contact_text(office)
        )
    return (
        "I can only help with questions about the university, using verified university "
        "information. " + contact_text(office)
    )


def busy_text(office: dict[str, Any] | None) -> str:
    return (
        "Lots of students are asking right now. Please try again in a minute, or contact the "
        "office. " + contact_text(office)
    )
