"""Golden-set scoring and the golden file itself (PRD Section 10). No database."""

import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from app.agent.service import AgentAnswer
from app.evaluation import Item, invented_numbers, load_items, score
from app.tools import STRUCTURED_TOOLS
from app.tools.base import Source

GOLDEN = Path(__file__).resolve().parents[4] / "eval" / "golden.jsonl"
TODAY = date(2026, 10, 5)


def _answer(text: str, *, mode: str = "template", tool: str | None = "get_fee",
            intent: str = "structured", data: list[dict[str, Any]] | None = None,
            office: dict[str, Any] | None = None) -> AgentAnswer:  # fmt: skip
    return AgentAnswer(
        answer=text, mode=mode, sources=[Source(title="Test fees (FY 2026-27)")], intent=intent,
        tool_used=tool, planned_by="rules", language="en", llm_calls=0, cache_hit=False,
        fallback_reason="x" if mode == "fallback" else None, latency_ms=1,
        tool_data=data or [], office_contact=office,
    )  # fmt: skip


def _item(**overrides: object) -> Item:
    values: dict[str, object] = {
        "id": "t1", "question": "What is the test fee?", "expected_facts": ["1,234"],
        "expected_tool": "get_fee", "should_fallback": False,
    }  # fmt: skip
    values.update(overrides)
    return Item(**values)  # type: ignore[arg-type]


def test_correct_answer_needs_facts_and_tool() -> None:
    data = [{"tuition_per_credit_hour": 1234.0}]
    assert score(_item(), _answer("Rs 1,234 per credit hour", data=data), TODAY).correct
    wrong_tool = score(_item(), _answer("Rs 1,234", tool="get_office", data=data), TODAY)
    assert not wrong_tool.correct and wrong_tool.wrong_tool
    missing = score(_item(), _answer("Rs 99", data=[{"x": 99}]), TODAY)
    assert missing.missing_facts == ["1,234"]


def test_invented_number_fails_an_otherwise_correct_answer() -> None:
    outcome = score(_item(), _answer("Rs 1,234 or maybe Rs 5,555", data=[{"t": 1234}]), TODAY)
    assert not outcome.correct and outcome.invented == {"5555"}


def test_fallback_item_accepts_fallback_or_refusal_only() -> None:
    item = _item(expected_facts=[], expected_tool=None, should_fallback=True)
    assert score(item, _answer("I don't have it", mode="fallback", tool=None), TODAY).correct
    refusal = _answer("Can't help", mode="simple", tool=None, intent="out_of_scope")
    assert score(item, refusal, TODAY).correct
    assert not score(item, _answer("Rs 1,234", data=[{"t": 1234}]), TODAY).correct


def test_office_contact_numbers_in_a_fallback_are_not_invented() -> None:
    office = {"name": "Test Office", "phones": ["000-1111111"]}
    answer = _answer("Call 000-1111111", mode="fallback", tool=None, office=office)
    assert invented_numbers(answer, "q", TODAY) == set()


def test_missing_fields_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "g.jsonl"
    path.write_text(json.dumps({"question": "q"}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing fields"):
        load_items(path)


def test_golden_v1_meets_the_minimum_mix() -> None:
    """Phases M2: at least 50 items. PRD Section 10 mix: no-data, injection, Urdu items."""
    items = load_items(GOLDEN)
    categories = Counter(item.category for item in items)
    assert len(items) >= 50
    assert len({item.id for item in items}) == len(items)
    assert sum(item.should_fallback for item in items) >= 20
    assert categories["injection"] >= 6
    assert sum(item.language != "en" for item in items) >= 10
    known = {*STRUCTURED_TOOLS, "search_knowledge", None}
    assert all(item.expected_tool in known for item in items)
    assert all(item.expected_facts for item in items if item.expected_tool is not None)
