"""Agent state and per-turn dependencies (Architectural.md Section 6)."""

import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.services.embeddings import Embedder
from app.services.llm import LLMRouter
from app.services.session_memory import Turn
from app.tools.base import Source, ToolResult

Intent = Literal["structured", "knowledge", "live", "smalltalk", "out_of_scope"]
AnswerMode = Literal["template", "llm", "extractive", "fallback", "cache", "simple"]


class Plan(BaseModel):
    """Output of the plan step (LLM call 1, or the rule-based planner)."""

    intent: Intent
    tool: str | None = Field(
        default=None, description="Structured tool name, if intent is structured"
    )
    args: dict[str, Any] = Field(default_factory=dict, description="Tool arguments")
    retrieval_query: str | None = Field(
        default=None, description="Short search query for knowledge questions"
    )
    category: str | None = None


@dataclass
class StudentProfile:
    """Self-declared profile only (D11, PER-1). Never private records."""

    program: str | None = None
    semester: int | None = None
    section: str | None = None


class AgentState(TypedDict, total=False):
    # input
    query: str
    modality: Literal["text", "voice"]
    profile: StudentProfile | None
    conversation_id: uuid.UUID | None
    history: list[Turn]  # last turns of this chat (CHAT-5), redacted questions
    # normalize
    redacted_query: str
    language: str
    cache_key: str
    use_cache: bool  # off for follow-ups, whose meaning depends on the history
    today: date
    # plan
    plan: Plan
    planned_by: Literal["llm", "rules"]
    # tools / retrieval
    tool_results: list[ToolResult]
    retrieval_attempts: int
    grade_reason: str | None
    embedding_failed: bool
    # answer
    answer: str
    answer_mode: AnswerMode
    sources: list[Source]
    fallback_reason: str | None
    office_contact: dict[str, Any] | None
    llm_calls: int
    tokens_in: int
    tokens_out: int
    cache_hit: bool
    post_check_failed: bool


@dataclass
class AgentDeps:
    """Everything a turn needs, passed as LangGraph runtime context (no globals)."""

    session: AsyncSession
    institution_id: uuid.UUID
    institution_name: str
    institution_config: dict[str, Any]
    settings: Settings
    llm: LLMRouter | None
    embedder: Embedder | None
    cache: Any = None  # ResponseCache
    today: date = field(default_factory=date.today)
