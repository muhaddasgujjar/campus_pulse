"""Entry point for one chat turn: `answer_question()`. Used by eval now, by the WebSocket in M3.

The caller owns the database transaction (the agent writes unanswered_queries and usage_daily
rows into the given session) and decides when to commit.
"""

import time
import uuid
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from typing import Any, Literal, cast

from langgraph.graph.state import CompiledStateGraph
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.graph import build_graph
from app.agent.state import AgentDeps, AgentState, StudentProfile
from app.core.config import Settings
from app.db.models import Institution
from app.services.embeddings import Embedder
from app.services.llm import LLMRouter
from app.tools.base import Source


@dataclass(frozen=True)
class AgentAnswer:
    answer: str
    mode: str  # template | llm | extractive | fallback | cache | simple
    sources: list[Source]
    intent: str | None
    tool_used: str | None
    planned_by: str | None
    language: str
    llm_calls: int
    cache_hit: bool
    fallback_reason: str | None
    latency_ms: int
    tool_data: list[dict[str, Any]] = field(default_factory=list)
    office_contact: dict[str, Any] | None = None

    @property
    def fallback(self) -> bool:
        return self.mode == "fallback"


@lru_cache(maxsize=1)
def _graph() -> CompiledStateGraph[AgentState, AgentDeps, AgentState, AgentState]:
    return build_graph()


async def make_deps(
    session: AsyncSession,
    settings: Settings,
    *,
    llm: LLMRouter | None,
    embedder: Embedder | None,
    cache: Any = None,
    today: date | None = None,
    institution_slug: str | None = None,
) -> AgentDeps:
    slug = institution_slug or settings.institution_slug
    institution = (
        await session.execute(select(Institution).where(Institution.slug == slug))
    ).scalar_one_or_none()
    if institution is None:
        raise LookupError(f"institution '{slug}' not found: run `make seed`")
    return AgentDeps(
        session=session,
        institution_id=institution.id,
        institution_name=institution.name,
        institution_config=dict(institution.config or {}),
        settings=settings,
        llm=llm,
        embedder=embedder,
        cache=cache,
        today=today or date.today(),
    )


async def answer_question(
    deps: AgentDeps,
    query: str,
    *,
    modality: Literal["text", "voice"] = "text",
    profile: StudentProfile | None = None,
    conversation_id: uuid.UUID | None = None,
) -> AgentAnswer:
    started = time.perf_counter()
    raw = await _graph().ainvoke(
        {
            "query": query[:2000],  # input length limit (SEC-2)
            "modality": modality,
            "profile": profile,
            "conversation_id": conversation_id,
        },
        context=deps,
    )
    state = cast(AgentState, raw)
    results = state.get("tool_results") or []
    plan = state.get("plan")
    return AgentAnswer(
        answer=state["answer"],
        mode=state["answer_mode"],
        sources=list(state.get("sources") or []),
        intent=plan.intent if plan else None,
        tool_used=results[0].tool if results else (plan.tool if plan else None),
        planned_by=state.get("planned_by"),
        language=state.get("language", "en"),
        llm_calls=state.get("llm_calls", 0),
        cache_hit=bool(state.get("cache_hit")),
        fallback_reason=state.get("fallback_reason"),
        latency_ms=round((time.perf_counter() - started) * 1000),
        tool_data=[row for r in results for row in r.data],
        office_contact=state.get("office_contact"),
    )
