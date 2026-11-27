"""Golden-set evaluation (PRD Sections 3 and 10, Phases M2): `make eval`.

Every item in eval/golden.jsonl runs through the real agent against seed/<slug>/, loaded inside
a transaction that is always rolled back, so evaluation never changes any database.

Default (offline): no LLM (templates, extractive answers and the rule planner) and the fake
embedder, so it burns no quota and runs anywhere. `--live` uses LLM_PROVIDERS and the
configured embedder instead (counts against the free Gemini quota, about 2 calls per item).

Scoring
- correct: a `should_fallback` item gets a fallback or an out-of-scope refusal; any other item
  gets an answer (not a fallback) that contains every expected fact and used the expected tool.
- invented numbers: numbers in the answer that are in no tool row, source, office contact,
  the question or today's date (PRD: 0).
"""

import argparse
import asyncio
import json
import math
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from app.agent.cache import InMemoryResponseCache
from app.agent.postcheck import collect_numbers, numbers_in
from app.agent.service import AgentAnswer, answer_question, make_deps
from app.agent.state import StudentProfile
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.models import KbEntry
from app.db.session import create_engine, create_sessionmaker
from app.services.embeddings import CachedQueryEmbedder, Embedder, FakeEmbedder, build_embedder
from app.services.ingestion import index_entry
from app.services.llm import LLMRouter, build_llm
from app.services.seeding import load_seed_dir
from app.tools import STRUCTURED_TOOLS

REQUIRED_FIELDS = ("question", "expected_facts", "expected_tool", "should_fallback")
NO_ANSWER_TOOLS = {None, "none", "fallback"}


@dataclass
class Item:
    id: str
    question: str
    expected_facts: list[str]
    expected_tool: str | None
    should_fallback: bool
    language: str = "en"
    category: str = "other"
    modality: str = "text"
    profile: dict[str, Any] | None = None


@dataclass
class Outcome:
    item: Item
    answer: AgentAnswer
    correct: bool
    missing_facts: list[str] = field(default_factory=list)
    wrong_tool: bool = False
    invented: set[str] = field(default_factory=set)

    @property
    def has_source(self) -> bool:
        return bool(self.answer.sources)


def load_items(path: Path) -> list[Item]:
    items: list[Item] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        raw = json.loads(line)
        missing = [name for name in REQUIRED_FIELDS if name not in raw]
        if missing:
            raise ValueError(f"{path.name}:{number} missing fields: {', '.join(missing)}")
        items.append(
            Item(
                id=str(raw.get("id", number)),
                question=raw["question"],
                expected_facts=list(raw["expected_facts"]),
                expected_tool=raw["expected_tool"],
                should_fallback=bool(raw["should_fallback"]),
                language=raw.get("language", "en"),
                category=raw.get("category", "other"),
                modality=raw.get("modality", "text"),
                profile=raw.get("profile"),
            )
        )
    return items


def invented_numbers(answer: AgentAnswer, query: str, today: date) -> set[str]:
    allowed = numbers_in(query)
    collect_numbers(today, allowed)
    collect_numbers(answer.tool_data, allowed)
    collect_numbers(answer.office_contact, allowed)
    for source in answer.sources:
        collect_numbers(source.title, allowed)
        collect_numbers(source.last_verified, allowed)
    return numbers_in(answer.answer) - allowed


def _contains(answer: str, fact: str) -> bool:
    return fact.lower() in answer.lower()


def score(item: Item, answer: AgentAnswer, today: date) -> Outcome:
    invented = invented_numbers(answer, item.question, today)
    if item.should_fallback:
        refused = answer.fallback or answer.intent == "out_of_scope"
        return Outcome(item, answer, correct=refused and not invented, invented=invented)
    missing = [fact for fact in item.expected_facts if not _contains(answer.answer, fact)]
    wrong_tool = (
        item.expected_tool not in NO_ANSWER_TOOLS and answer.tool_used != item.expected_tool
    )
    correct = not answer.fallback and not missing and not wrong_tool and not invented
    return Outcome(item, answer, correct, missing, wrong_tool, invented)


def _pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.0f}% ({part}/{whole})" if whole else "n/a"


def _p95(values: list[int]) -> int:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)] if ordered else 0


def report(outcomes: list[Outcome], live: bool) -> tuple[list[tuple[str, str, str]], float]:
    total = len(outcomes)
    correct = sum(o.correct for o in outcomes)
    fallback_items = [o for o in outcomes if o.item.should_fallback]
    answerable = [
        o for o in outcomes if not o.item.should_fallback and o.item.category != "smalltalk"
    ]
    exact = [o for o in answerable if o.item.expected_tool in STRUCTURED_TOOLS]
    invented = sum(1 for o in outcomes if o.invented)
    latency = _p95([o.answer.latency_ms for o in outcomes])
    latency_note = "" if live else " (no LLM)"
    voice = [o for o in outcomes if o.item.modality == "voice"]
    rows = [
        ("Correct answers on golden set", ">= 85%", _pct(correct, total)),
        ("Correct fallback on questions with no data", ">= 90%",
         _pct(sum(o.correct for o in fallback_items), len(fallback_items))),
        ("Answers carrying a valid source (excl. small talk)", "100%",
         _pct(sum(o.has_source for o in answerable if not o.answer.fallback),
              sum(1 for o in answerable if not o.answer.fallback))),
        ("Invented phone numbers, fees or dates", "0", str(invented)),
        ("Exact-data answers matching tables", "100%",
         _pct(sum(o.correct for o in exact), len(exact))),
        ("Agent latency p95 (in process)", "< 4 s", f"{latency} ms{latency_note}"),
        ("Voice items answered correctly (transcript-style)", ">= 85%",
         _pct(sum(o.correct for o in voice), len(voice))),
        ("Voice message round trip p95 (server awake)", "< 8 s",
         "browser only: measure on devices (M4 test sheet)"),
    ]  # fmt: skip
    return rows, (correct / total if total else 0.0)


def print_report(path: Path, outcomes: list[Outcome], live: bool) -> float:
    rows, accuracy = report(outcomes, live)
    fallbacks = sum(o.item.should_fallback for o in outcomes)
    mode = "live providers" if live else "offline: no LLM, fake embedder"
    print(f"Golden set: {path} ({len(outcomes)} items, {fallbacks} should fall back)")
    llm_calls = sum(o.answer.llm_calls for o in outcomes)
    over_budget = sum(1 for o in outcomes if o.answer.llm_calls > 2)
    print(f"Mode: {mode}. LLM calls: {llm_calls} (items over the 2-call budget: {over_budget})\n")
    width = max(len(name) for name, _, _ in rows)
    print(f"{'Metric':<{width}}  {'Target':<8}  Result")
    print(f"{'-' * width}  {'-' * 8}  ------")
    for name, target, result in rows:
        print(f"{name:<{width}}  {target:<8}  {result}")

    by_category: dict[str, list[Outcome]] = {}
    for outcome in outcomes:
        by_category.setdefault(outcome.item.category, []).append(outcome)
    print("\nBy category: " + ", ".join(
        f"{name} {sum(o.correct for o in group)}/{len(group)}"
        for name, group in sorted(by_category.items())
    ))  # fmt: skip

    failures = [o for o in outcomes if not o.correct]
    if failures:
        print(f"\nFailures ({len(failures)}):")
    for o in failures:
        why = []
        if o.item.should_fallback:
            why.append(f"expected a fallback, got {o.answer.mode}")
        elif o.answer.fallback:
            why.append(f"fell back ({o.answer.fallback_reason})")
        if o.missing_facts:
            why.append(f"missing {o.missing_facts}")
        if o.wrong_tool:
            why.append(f"tool {o.answer.tool_used} != {o.item.expected_tool}")
        if o.invented:
            why.append(f"invented numbers {sorted(o.invented)}")
        print(f"- [{o.item.id}] {o.item.question}\n    {'; '.join(why)}")
        print(f"    answer: {o.answer.answer[:200]!r}")
    return accuracy


def write_json(path: Path, outcomes: list[Outcome], live: bool) -> None:
    rows, accuracy = report(outcomes, live)
    payload = {
        "date": date.today().isoformat(),
        "mode": "live" if live else "offline",
        "accuracy": round(accuracy, 4),
        "metrics": [{"metric": m, "target": t, "result": r} for m, t, r in rows],
        "items": [
            {
                "id": o.item.id,
                "question": o.item.question,
                "correct": o.correct,
                "mode": o.answer.mode,
                "tool": o.answer.tool_used,
                "planned_by": o.answer.planned_by,
                "llm_calls": o.answer.llm_calls,
                "missing_facts": o.missing_facts,
                "invented": sorted(o.invented),
                "answer": o.answer.answer,
            }
            for o in outcomes
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")


def _database_url(settings: Settings) -> str:
    if settings.database_url:
        print("Using DATABASE_URL (all changes are rolled back).", file=sys.stderr)
        return settings.database_url
    from app.devtools.localdb import database_url, migrate

    url = database_url("campus_pulse_eval")
    migrate(url)
    return url


async def run(
    golden: Path, seed_dir: Path, *, live: bool, today: date, json_out: Path | None
) -> float:
    settings = get_settings()
    items = load_items(golden)
    llm: LLMRouter | None = build_llm(settings) if live else None
    built = build_embedder(settings) if live else None
    embedder: Embedder = built or CachedQueryEmbedder(FakeEmbedder(settings.embedding_dim))
    engine = create_engine(_database_url(settings))
    outcomes: list[Outcome] = []
    try:
        async with create_sessionmaker(engine)() as session:
            await session.begin()
            try:

                async def on_entry(entry: KbEntry) -> None:
                    await index_entry(session, entry, embedder)

                await load_seed_dir(session, seed_dir, on_kb_entry=on_entry)
                deps = await make_deps(
                    session,
                    settings,
                    llm=llm,
                    embedder=embedder,
                    cache=InMemoryResponseCache(ttl_seconds=0),  # every item runs the graph
                    today=today,
                )
                for item in items:
                    profile = StudentProfile(**item.profile) if item.profile else None
                    answer = await answer_question(
                        deps,
                        item.question,
                        modality="voice" if item.modality == "voice" else "text",
                        profile=profile,
                    )
                    outcomes.append(score(item, answer, today))
            finally:
                await session.rollback()
    finally:
        await engine.dispose()

    accuracy = print_report(golden, outcomes, live)
    if json_out is not None:
        write_json(json_out, outcomes, live)
        print(f"\nJSON report: {json_out}")
    return accuracy


def main(argv: list[str] | None = None) -> int:
    repo = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description="Run the golden-set evaluation.")
    parser.add_argument("golden", nargs="?", type=Path, default=repo / "eval" / "golden.jsonl")
    parser.add_argument("--seed-dir", type=Path, default=repo / "seed" / "lgu")
    parser.add_argument("--live", action="store_true", help="use LLM_PROVIDERS and real embeddings")
    parser.add_argument(
        "--today", type=date.fromisoformat, default=None, help="pin today's date (YYYY-MM-DD)"
    )
    parser.add_argument("--json", type=Path, default=None, help="also write a JSON report")
    parser.add_argument(
        "--min-accuracy", type=float, default=0.0, help="exit 1 below this share (0 to 1)"
    )
    args = parser.parse_args(argv)
    configure_logging("WARNING")  # keep the report readable; warnings still show
    if hasattr(sys.stdout, "reconfigure"):  # Urdu questions on a cp1252 Windows console
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    accuracy = asyncio.run(
        run(
            args.golden,
            args.seed_dir,
            live=args.live,
            today=args.today or date.today(),
            json_out=args.json,
        )
    )
    return 0 if accuracy >= args.min_accuracy else 1


if __name__ == "__main__":
    sys.exit(main())
