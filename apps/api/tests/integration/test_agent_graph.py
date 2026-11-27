"""The LangGraph agent end to end over the real seed/lgu rows (Postgres + pgvector), with FakeLLM
and the fake embedder. Checks the LLM budget (D15), templates, fallback, post-check, cache and
redaction. Seed facts are the only facts asserted; nothing here is invented."""

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.cache import InMemoryResponseCache
from app.agent.service import AgentAnswer, answer_question, make_deps
from app.agent.state import StudentProfile
from app.db.models import Institution, KbEntry, UnansweredQuery, UsageDaily
from app.services import audit
from app.services.embeddings import FakeEmbedder
from app.services.ingestion import index_entry
from app.services.llm import FakeLLM, LLMRouter
from app.services.seeding import load_seed_dir
from tests.conftest import make_settings

pytestmark = pytest.mark.integration

SEED_DIR = Path(__file__).resolve().parents[4] / "seed" / "lgu"
TODAY = date(2026, 10, 5)


@pytest.fixture
async def embedder(db_session: AsyncSession) -> FakeEmbedder:
    fake = FakeEmbedder()

    async def on_entry(entry: KbEntry) -> None:
        await index_entry(db_session, entry, fake)

    await load_seed_dir(db_session, SEED_DIR, on_kb_entry=on_entry)
    fake.calls = 0  # count only the calls made by the agent
    return fake


async def ask(
    session: AsyncSession,
    embedder: FakeEmbedder,
    query: str,
    *,
    llm: FakeLLM | None = None,
    cache: InMemoryResponseCache | None = None,
    profile: StudentProfile | None = None,
    voice: bool = False,
    **settings: Any,
) -> AgentAnswer:
    deps = await make_deps(
        session,
        make_settings(**settings),
        llm=LLMRouter([llm]) if llm is not None else None,
        embedder=embedder,
        cache=cache,
        today=TODAY,
    )
    return await answer_question(
        deps, query, modality="voice" if voice else "text", profile=profile
    )


def plan_json(**plan: Any) -> str:
    return json.dumps(plan)


# --- exact data: templates, 0 LLM calls ----------------------------------------------------


async def test_fee_answer_matches_the_table_with_no_llm(
    db_session: AsyncSession, embedder: FakeEmbedder
) -> None:
    result = await ask(db_session, embedder, "What are the fees for BSCS?")
    assert (result.mode, result.tool_used, result.llm_calls) == ("template", "get_fee", 0)
    assert "Rs 7,744 per credit hour" in result.answer
    assert "Rs 17,500" in result.answer
    assert "Rs 6,360 per semester" in result.answer
    assert "FY 2026-27" in result.answer
    assert result.sources and "last verified Mon, 5 Oct 2026" in result.answer


async def test_english_fee_question_skips_compose_even_with_an_llm(
    db_session: AsyncSession, embedder: FakeEmbedder
) -> None:
    llm = FakeLLM([plan_json(intent="structured", tool="get_fee", args={"program_group": "BBA"})])
    result = await ask(db_session, embedder, "What is the BBA fee?", llm=llm)
    assert result.mode == "template"
    assert [tier for tier, _ in llm.calls] == ["fast"]  # plan only, template answer
    assert "Rs 7,392 per credit hour" in result.answer
    assert "admission fee" not in result.answer  # not in the source, never invented


async def test_passed_deadline_is_described_as_passed(
    db_session: AsyncSession, embedder: FakeEmbedder
) -> None:
    result = await ask(db_session, embedder, "When is the last date to apply?")
    assert result.tool_used == "get_key_dates"
    assert "Fri, 2 Oct 2026" in result.answer
    assert "This date has passed. Please confirm with the Admission Office." in result.answer


async def test_office_contact_comes_from_the_table(
    db_session: AsyncSession, embedder: FakeEmbedder
) -> None:
    result = await ask(db_session, embedder, "What is the phone number of the exam office?")
    assert result.tool_used == "get_office"
    assert "Exam Office" in result.answer and "042-37181828" in result.answer


async def test_office_hours_without_an_office_name_list_every_office(
    db_session: AsyncSession, embedder: FakeEmbedder
) -> None:
    result = await ask(db_session, embedder, "What are the office timings?")
    assert (result.tool_used, result.mode) == ("get_office", "template")
    assert "Admission Office" in result.answer and "Exam Office" in result.answer
    assert "08:00 to 16:00" in result.answer
    assert embedder.calls == 0  # answered from the table, no retrieval


# --- rule shortcuts: 0 LLM calls --------------------------------------------------------------


async def test_greeting_costs_no_llm_call(db_session: AsyncSession, embedder: FakeEmbedder) -> None:
    llm = FakeLLM()
    result = await ask(db_session, embedder, "Assalam o alaikum", llm=llm)
    assert result.mode == "simple" and result.answer.startswith("Hi, I'm Campus Pulse")
    assert llm.calls == [] and embedder.calls == 0


async def test_private_record_request_is_refused_with_an_office(
    db_session: AsyncSession, embedder: FakeEmbedder
) -> None:
    llm = FakeLLM()
    result = await ask(db_session, embedder, "What is my result?", llm=llm)
    assert result.intent == "out_of_scope" and llm.calls == []
    assert "can't access personal records" in result.answer
    assert result.office_contact is not None


# --- knowledge (RAG) --------------------------------------------------------------------------


async def test_knowledge_without_llm_quotes_the_approved_entry(
    db_session: AsyncSession, embedder: FakeEmbedder
) -> None:
    result = await ask(
        db_session, embedder, "Can F.A or I.Com students apply for Computer Science programs?"
    )
    assert result.mode == "extractive"
    assert "not eligible for Computer Science programs" in result.answer
    assert result.sources[0].title == "Eligibility for Computer Science programs (F.A and I.Com)"
    assert embedder.calls == 1


async def test_knowledge_with_llm_uses_two_calls_and_the_voice_rules(
    db_session: AsyncSession, embedder: FakeEmbedder
) -> None:
    llm = FakeLLM(
        [
            plan_json(intent="knowledge", retrieval_query="F.A I.Com eligibility computer science"),
            "No. According to the Admission Office, F.A and I.Com students are not eligible.",
        ]
    )
    result = await ask(
        db_session, embedder, "Can F.A students do computer science?", llm=llm, voice=True
    )
    assert result.mode == "llm" and result.llm_calls == 2
    assert [tier for tier, _ in llm.calls] == ["fast", "main"]
    assert "voice reply" in (llm.systems[1] or "")
    assert "<data>" in llm.calls[1][1]
    assert embedder.calls == 1


async def test_unknown_topic_falls_back_and_is_logged(
    db_session: AsyncSession, embedder: FakeEmbedder
) -> None:
    result = await ask(db_session, embedder, "Is there a swimming pool on campus?")
    assert result.fallback
    assert result.answer.startswith("I don't have verified information on this.")
    assert result.office_contact is not None and result.sources == []
    logged = (await db_session.execute(select(UnansweredQuery))).scalars().all()
    assert [row.query for row in logged] == ["Is there a swimming pool on campus?"]


async def test_retrieval_retry_never_makes_a_second_embedding_call(
    db_session: AsyncSession, embedder: FakeEmbedder
) -> None:
    llm = FakeLLM([plan_json(intent="knowledge", retrieval_query="aquatics centre membership")])
    result = await ask(db_session, embedder, "Is there a swimming pool on campus?", llm=llm)
    assert result.fallback
    assert embedder.calls == 1  # D15: at most 1 embedding call per turn
    assert len(llm.calls) == 1  # no compose on a fallback


# --- composer safety: post-check and failures ----------------------------------------------


async def test_llm_answer_in_roman_urdu_passes_post_check(
    db_session: AsyncSession, embedder: FakeEmbedder
) -> None:
    llm = FakeLLM(
        [
            plan_json(intent="structured", tool="get_fee", args={"program_group": "BSCS"}),
            "BSCS ki tuition Rs 7,744 per credit hour hai (FY 2026-27).",
        ]
    )
    result = await ask(db_session, embedder, "BSCS ki fee kitni hai?", llm=llm)
    assert (result.language, result.mode, result.llm_calls) == ("roman_ur", "llm", 2)
    assert "Roman Urdu" in (llm.systems[1] or "")
    assert result.answer.startswith("BSCS ki tuition Rs 7,744")


async def test_invented_number_is_replaced_by_the_template(
    db_session: AsyncSession, embedder: FakeEmbedder
) -> None:
    llm = FakeLLM(
        [
            plan_json(intent="structured", tool="get_fee", args={"program_group": "BSCS"}),
            "BSCS ki tuition Rs 9,999 per credit hour hai (FY 2026-27).",
        ]
    )
    result = await ask(db_session, embedder, "BSCS ki fee kitni hai?", llm=llm)
    assert result.mode == "template"
    assert "9,999" not in result.answer and "Rs 7,744" in result.answer


async def test_composer_no_answer_becomes_a_fallback(
    db_session: AsyncSession, embedder: FakeEmbedder
) -> None:
    llm = FakeLLM(
        [
            plan_json(intent="structured", tool="get_fee", args={"program_group": "BSCS"}),
            "NO_ANSWER",
        ]
    )
    result = await ask(db_session, embedder, "BSCS ki fee kitni hai?", llm=llm)
    assert result.fallback and result.fallback_reason == "composer_no_answer"


async def test_provider_down_uses_rules_and_templates(
    db_session: AsyncSession, embedder: FakeEmbedder
) -> None:
    llm = FakeLLM(fail=True)
    result = await ask(db_session, embedder, "BSCS ki fee kitni hai?", llm=llm)
    assert (result.planned_by, result.mode) == ("rules", "template")
    assert "Rs 7,744" in result.answer
    assert result.llm_calls == 2  # failed attempts still count: they may have used quota


async def test_llm_plan_with_an_unknown_tool_is_ignored(
    db_session: AsyncSession, embedder: FakeEmbedder
) -> None:
    llm = FakeLLM([plan_json(intent="structured", tool="run_sql", args={"sql": "select 1"})])
    result = await ask(db_session, embedder, "What are the fees for BSCS?", llm=llm)
    assert result.planned_by == "rules" and result.tool_used == "get_fee"


async def test_budget_setting_caps_llm_calls(
    db_session: AsyncSession, embedder: FakeEmbedder
) -> None:
    llm = FakeLLM([plan_json(intent="structured", tool="get_fee", args={"program_group": "BSCS"})])
    result = await ask(
        db_session, embedder, "BSCS ki fee kitni hai?", llm=llm, max_llm_calls_per_turn=1
    )
    assert len(llm.calls) == 1 and result.mode == "template"


# --- cache, redaction, usage --------------------------------------------------------------------


async def test_repeat_question_is_served_from_cache_until_data_changes(
    db_session: AsyncSession, embedder: FakeEmbedder
) -> None:
    cache = InMemoryResponseCache(ttl_seconds=3600)
    first = await ask(db_session, embedder, "What are the fees for BSCS?", cache=cache)
    second = await ask(db_session, embedder, "what are the fees for bscs", cache=cache)
    assert (first.cache_hit, second.cache_hit, second.mode) == (False, True, "cache")
    assert second.answer == first.answer and second.sources == first.sources
    institution_id = (await db_session.execute(select(Institution.id))).scalar_one()
    audit.record(  # a staff edit: every content write records an audit row (rule 7)
        db_session,
        institution_id=institution_id,
        action="update",
        table_name="fees",
        row_id=None,
        diff={},
        actor_label="test",
    )
    await db_session.flush()
    third = await ask(db_session, embedder, "What are the fees for BSCS?", cache=cache)
    assert not third.cache_hit


async def test_fallbacks_are_not_cached(db_session: AsyncSession, embedder: FakeEmbedder) -> None:
    cache = InMemoryResponseCache(ttl_seconds=3600)
    await ask(db_session, embedder, "Is there a swimming pool on campus?", cache=cache)
    again = await ask(db_session, embedder, "Is there a swimming pool on campus?", cache=cache)
    assert not again.cache_hit


async def test_personal_identifiers_never_reach_the_llm_or_the_log(
    db_session: AsyncSession, embedder: FakeEmbedder
) -> None:
    llm = FakeLLM([plan_json(intent="knowledge", retrieval_query="swimming pool")])
    await ask(
        db_session, embedder, "My CNIC is 35202-1234567-1. Is there a swimming pool?", llm=llm
    )
    assert "35202-1234567-1" not in llm.calls[0][1] and "[CNIC]" in llm.calls[0][1]
    logged = (await db_session.execute(select(UnansweredQuery))).scalars().one()
    assert "35202" not in logged.query and "[CNIC]" in logged.query


async def test_usage_is_counted_per_day(db_session: AsyncSession, embedder: FakeEmbedder) -> None:
    await ask(db_session, embedder, "Is there a swimming pool on campus?")
    await ask(db_session, embedder, "What are the fees for BSCS?")
    row = (await db_session.execute(select(UsageDaily))).scalars().one()
    assert (row.day, row.llm_calls, row.embed_calls, row.fallbacks) == (TODAY, 0, 1, 1)


async def test_office_miss_falls_through_to_the_knowledge_base(
    db_session: AsyncSession, embedder: FakeEmbedder
) -> None:
    result = await ask(db_session, embedder, "Where is the LGU main campus?")
    assert (result.intent, result.tool_used, result.mode) == (
        "structured",
        "search_knowledge",
        "extractive",
    )
    assert "Sector C, DHA Phase 6, Lahore" in result.answer
    assert embedder.calls == 1


async def test_one_matching_word_is_not_enough_for_a_short_question(
    db_session: AsyncSession, embedder: FakeEmbedder
) -> None:
    """'hostel fee' shares only 'hostel' with the policies entry: fall back, don't quote it."""
    result = await ask(db_session, embedder, "What is the hostel fee?")
    assert result.fallback
