"""The LangGraph agent (D7, D15, Architectural.md Section 6).

START -> normalize -> cache_lookup --hit--> END
                          \\-miss-> plan --smalltalk/out_of_scope--> simple ----------\\
                                      |--structured--> structured --found--> compose   |
                                      |                     \\--none--> fallback        |
                                      |       (get_office miss --> retrieve)            |
                                      \\--knowledge/live--> retrieve --ok--> compose    |
                                                    (retry once) \\--weak--> fallback  |
compose -> post_check -> finalize -> END            fallback -> finalize            <--/

LLM budget: at most `max_llm_calls_per_turn` (2) per turn: plan (fast) + compose (main).
Exact data uses templates (0 calls); knowledge without an LLM quotes the best chunk.
"""

from typing import Any, Literal

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime

from app.agent import templates
from app.agent.cache import CachedAnswer, cache_key, normalize_query
from app.agent.language import detect_language
from app.agent.planner import (
    PLAN_SCHEMA,
    asks_office_hours,
    is_follow_up,
    is_private_request,
    parse_plan,
    rule_plan,
    wants_explanation,
)
from app.agent.postcheck import check_llm_answer, ensure_required_notes
from app.agent.prompts import PLANNER_SYSTEM, composer_prompt, composer_system, planner_prompt
from app.agent.state import AgentDeps, AgentState, Plan
from app.core.logging import get_logger
from app.core.redact import redact
from app.db.repositories.agent_log import add_usage, data_version, log_unanswered
from app.services.llm import LLMBudgetError, LLMProviderError, LLMResult
from app.services.retrieval import grade
from app.tools import ToolContext, run_tool
from app.tools.base import Source, ToolResult, dedupe_sources
from app.tools.offices import OfficeArgs, all_offices, get_office
from app.tools.search import SearchArgs, search_knowledge

log = get_logger("agent")


def _tool_ctx(deps: AgentDeps) -> ToolContext:
    return ToolContext(session=deps.session, institution_id=deps.institution_id, today=deps.today)


async def _llm(
    state: AgentState,
    deps: AgentDeps,
    prompt: str,
    tier: Literal["fast", "main"],
    *,
    system: str,
    json_schema: dict[str, Any] | None = None,
) -> tuple[LLMResult | None, dict[str, Any], LLMProviderError | None]:
    """One budgeted LLM call: (result or None, state counters to merge, error or None).

    A failed attempt still counts toward the budget: it may have used provider quota."""
    used = state.get("llm_calls", 0)
    if deps.llm is None or not deps.llm.available:
        return None, {}, LLMProviderError("no LLM configured")
    if used >= deps.settings.max_llm_calls_per_turn:
        return (
            None,
            {},
            LLMBudgetError(f"LLM budget of {deps.settings.max_llm_calls_per_turn} reached"),
        )
    counters: dict[str, Any] = {"llm_calls": used + 1}
    try:
        result = await deps.llm.generate(prompt, tier, json_schema=json_schema, system=system)
    except LLMProviderError as exc:
        return None, counters, exc
    counters["tokens_in"] = state.get("tokens_in", 0) + result.tokens_in
    counters["tokens_out"] = state.get("tokens_out", 0) + result.tokens_out
    return result, counters, None


async def _office_for(deps: AgentDeps, query: str) -> dict[str, Any] | None:
    """Best-matching office contact for fallbacks: by topic, else the configured default."""
    ctx = _tool_ctx(deps)
    for needle in (query[:120], deps.institution_config.get("fallback_office") or ""):
        if len(needle.strip()) < 2:
            continue
        result = await get_office(ctx, OfficeArgs(name_or_topic=needle))
        if result.found:
            return result.data[0]
    # Last resort: the first contact from the admin Settings page (ADP-2).
    for contact in deps.institution_config.get("contacts") or []:
        if contact.get("name") and (contact.get("phone") or contact.get("email")):
            phones = [contact["phone"]] if contact.get("phone") else []
            return {"name": contact["name"], "phones": phones, "email": contact.get("email")}
    return None


# --- nodes ---------------------------------------------------------------------------------


async def normalize(state: AgentState, runtime: Runtime[AgentDeps]) -> dict[str, Any]:
    deps = runtime.context
    query = state["query"]
    redacted = redact(query)  # before anything is stored or sent to the LLM (SEC-3, SEC-5)
    language = detect_language(query)
    profile = state.get("profile")
    use_cache = deps.cache is not None and not (state.get("history") and is_follow_up(query))
    # Read the content version only when there is a cache to key (one indexed query).
    version = await data_version(deps.session, deps.institution_id) if use_cache else "0"
    return {
        "use_cache": use_cache,
        "redacted_query": redacted,
        "language": language,
        "today": deps.today,
        "cache_key": cache_key(
            normalize_query(redacted),
            language,
            profile.program if profile else None,
            version,
            deps.today,
        ),
        "llm_calls": 0,
        "tokens_in": 0,
        "tokens_out": 0,
        "tool_results": [],
        "retrieval_attempts": 0,
        "cache_hit": False,
        "post_check_failed": False,
        "fallback_reason": None,
    }


async def cache_lookup(state: AgentState, runtime: Runtime[AgentDeps]) -> dict[str, Any]:
    deps = runtime.context
    if deps.cache is None or not state.get("use_cache"):
        return {}
    hit = await deps.cache.get(state["cache_key"])
    if hit is None:
        return {}
    sources = [Source.from_dict(item) for item in hit.sources]
    return {"cache_hit": True, "answer": hit.answer, "answer_mode": "cache", "sources": sources}


async def plan(state: AgentState, runtime: Runtime[AgentDeps]) -> dict[str, Any]:
    deps = runtime.context
    query = state["redacted_query"]
    profile = state.get("profile")
    rules = rule_plan(query, profile, deps.today)
    # Rules decide greetings and private/sensitive requests without spending an LLM call.
    if rules.intent in ("smalltalk", "out_of_scope"):
        return {"plan": rules, "planned_by": "rules"}
    # Rules first for exact data (D3, D15): a question the rules route to a table tool is
    # answered from that table with no plan call. The LLM plans only what rules cannot:
    # Urdu script, policies, follow-ups that need the history, and "why/compare" questions.
    follow_up = bool(state.get("history")) and is_follow_up(query)
    if (
        rules.intent == "structured"
        and rules.tool
        and not follow_up
        and not wants_explanation(query)
    ):
        return {"plan": rules, "planned_by": "rules"}
    result, counters, error = await _llm(
        state,
        deps,
        planner_prompt(query, profile, deps.today, state.get("history")),
        "fast",
        system=PLANNER_SYSTEM,
        json_schema=PLAN_SCHEMA,
    )
    if error is not None or result is None:
        log.info("plan_by_rules", reason=type(error).__name__)
        return {"plan": rules, "planned_by": "rules", **counters}
    llm_plan = parse_plan(result.json)
    if llm_plan is None:
        log.warning("plan_invalid_json_using_rules")
        return {"plan": rules, "planned_by": "rules", **counters}
    return {"plan": llm_plan, "planned_by": "llm", **counters}


async def simple(state: AgentState, runtime: Runtime[AgentDeps]) -> dict[str, Any]:
    deps = runtime.context
    short_name = deps.institution_config.get("short_name", "the university")
    if state["plan"].intent == "smalltalk":
        lowered = state["redacted_query"].lower()
        thanks = any(w in lowered for w in ("thank", "shukriya", "jazak"))
        text = templates.thanks(short_name) if thanks else templates.greeting(short_name)
        return {"answer": text, "answer_mode": "simple", "sources": []}
    office = await _office_for(deps, state["redacted_query"])
    private = is_private_request(state["redacted_query"])
    return {
        "answer": templates.out_of_scope_text(office, private=private),
        "answer_mode": "simple",
        "sources": [],
        "office_contact": office,
    }


async def structured(state: AgentState, runtime: Runtime[AgentDeps]) -> dict[str, Any]:
    deps = runtime.context
    current = state["plan"]
    assert current.tool is not None
    try:
        result = await run_tool(_tool_ctx(deps), current.tool, current.args)
    except (KeyError, ValueError) as exc:
        log.warning("tool_args_rejected", tool=current.tool, error=str(exc))
        return {"tool_results": [], "fallback_reason": "invalid_tool_args"}
    if not result.found and current.tool == "get_office" and asks_office_hours(state["query"]):
        # Opening hours without an office name: answer with every office's own hours.
        result = await all_offices(_tool_ctx(deps))
    if not result.found:
        return {"tool_results": [result], "fallback_reason": "no_structured_data"}
    return {"tool_results": [result]}


async def retrieve(state: AgentState, runtime: Runtime[AgentDeps]) -> dict[str, Any]:
    deps = runtime.context
    attempts = state.get("retrieval_attempts", 0)
    planned = state["plan"].retrieval_query or state["redacted_query"]
    # Retry once with the student's own words (ANS-4) at zero LLM cost. The retry is keyword
    # only: a turn makes at most 1 embedding call (D15).
    query = planned if attempts == 0 else state["redacted_query"]
    tool_result, search = await search_knowledge(
        _tool_ctx(deps),
        SearchArgs(
            query=query[:300], category=state["plan"].category, k=deps.settings.retrieval_top_k
        ),
        deps.embedder if attempts == 0 else None,
    )
    verdict = grade(
        query,
        search.chunks,
        min_similarity=deps.settings.min_similarity,
        min_coverage=deps.settings.retrieval_min_keyword_coverage,
    )
    update: dict[str, Any] = {
        "retrieval_attempts": attempts + 1,
        "tool_results": [tool_result] if verdict.ok else [],
        "grade_reason": verdict.reason,
        "fallback_reason": None if verdict.ok else f"retrieval_{verdict.reason}",
    }
    if attempts == 0:  # the keyword-only retry says nothing about the embedder
        update["embedding_failed"] = search.embedding_failed
    return update


def _template_for(results: list[ToolResult], query: str) -> str:
    result = results[0]
    if result.tool == "search_knowledge":
        return templates.extractive_answer(result, query)
    return templates.structured_answer(result)


async def compose(state: AgentState, runtime: Runtime[AgentDeps]) -> dict[str, Any]:
    deps = runtime.context
    results = state["tool_results"]
    sources = dedupe_sources([s for r in results for s in r.sources])
    is_structured = results[0].tool != "search_knowledge"
    language = state["language"]
    use_template = is_structured and language == "en" and not wants_explanation(state["query"])
    template_mode = "template" if is_structured else "extractive"
    if use_template:
        return {
            "answer": _template_for(results, state["redacted_query"]),
            "answer_mode": "template",
            "sources": sources,
        }
    result, counters, error = await _llm(
        state,
        deps,
        composer_prompt(state["redacted_query"], results),
        "main",
        system=composer_system(
            deps.institution_name, deps.today, language, voice=state.get("modality") == "voice"
        ),
    )
    if error is not None or result is None:
        log.info("compose_by_template", reason=type(error).__name__)
        return {
            "answer": _template_for(results, state["redacted_query"]),
            "answer_mode": template_mode,
            "sources": sources,
            **counters,
        }
    return {"answer": result.text.strip(), "answer_mode": "llm", "sources": sources, **counters}


async def post_check(state: AgentState, runtime: Runtime[AgentDeps]) -> dict[str, Any]:
    deps = runtime.context
    results = state["tool_results"]
    if state["answer_mode"] != "llm":
        return {"answer": ensure_required_notes(state["answer"], results)}
    check = check_llm_answer(state["answer"], results, state["redacted_query"], deps.today)
    if check.ok:
        return {"answer": check.answer}
    if not check.invented:  # the composer said NO_ANSWER: the data does not answer it
        return {
            "post_check_failed": True,
            "fallback_reason": "composer_no_answer",
            "answer_mode": "fallback",
        }
    log.warning("post_check_invented_numbers", invented=sorted(check.invented))
    template = _template_for(results, state["redacted_query"])
    return {
        "answer": ensure_required_notes(template, results),
        "answer_mode": "template" if results[0].tool != "search_knowledge" else "extractive",
        "post_check_failed": True,
    }


async def fallback(state: AgentState, runtime: Runtime[AgentDeps]) -> dict[str, Any]:
    deps = runtime.context
    office = await _office_for(deps, state["redacted_query"])
    reason = state.get("fallback_reason") or "unknown"
    await log_unanswered(
        deps.session,
        deps.institution_id,
        state["redacted_query"],
        reason,
        state.get("conversation_id"),
    )
    return {
        "answer": templates.fallback_text(office),
        "answer_mode": "fallback",
        "sources": [],
        "office_contact": office,
        "fallback_reason": reason,
    }


async def finalize(state: AgentState, runtime: Runtime[AgentDeps]) -> dict[str, Any]:
    deps = runtime.context
    is_fallback = state["answer_mode"] == "fallback"
    await add_usage(
        deps.session,
        deps.institution_id,
        deps.today,
        llm_calls=state.get("llm_calls", 0),
        embed_calls=1 if state.get("retrieval_attempts") and deps.embedder else 0,
        cache_hits=1 if state.get("cache_hit") else 0,
        fallbacks=1 if is_fallback else 0,
    )
    cacheable = state["answer_mode"] in ("template", "llm", "extractive")
    if (
        deps.cache is not None
        and state.get("use_cache")
        and cacheable
        and not state.get("cache_hit")
    ):
        await deps.cache.set(
            state["cache_key"],
            CachedAnswer(
                answer=state["answer"],
                sources=[s.as_dict() for s in state.get("sources", [])],
                tool_used=state["tool_results"][0].tool if state.get("tool_results") else None,
            ),
        )
    return {}


# --- routing -------------------------------------------------------------------------------


def after_cache(state: AgentState) -> str:
    return "hit" if state.get("cache_hit") else "miss"


def after_plan(state: AgentState) -> str:
    current: Plan = state["plan"]
    if current.intent in ("smalltalk", "out_of_scope"):
        return "simple"
    if current.intent == "structured" and current.tool:
        return "structured"
    return "retrieve"


def after_structured(state: AgentState) -> str:
    if state.get("tool_results") and not state.get("fallback_reason"):
        return "compose"
    # Office and date questions are often free text ("where is the main campus?", "when can I
    # apply for a scholarship?"): on a miss, try the approved knowledge base before giving up.
    # Fees and timetables are keyed by program, so they fall back directly.
    if (
        state["plan"].tool in ("get_office", "get_key_dates")
        and state.get("fallback_reason") == "no_structured_data"
    ):
        return "retrieve"
    return "fallback"


def after_retrieve(state: AgentState) -> str:
    if state.get("tool_results"):
        return "compose"
    planned = state["plan"].retrieval_query
    retry_possible = planned is not None and planned != state["redacted_query"]
    if state.get("retrieval_attempts", 0) < 2 and retry_possible:
        return "retry"
    return "fallback"


def after_post_check(state: AgentState) -> str:
    return "fallback" if state.get("answer_mode") == "fallback" else "finalize"


def build_graph() -> CompiledStateGraph[AgentState, AgentDeps, AgentState, AgentState]:
    graph = StateGraph(AgentState, context_schema=AgentDeps)
    for name, node in (
        ("normalize", normalize), ("cache_lookup", cache_lookup), ("plan", plan),
        ("simple", simple), ("structured", structured), ("retrieve", retrieve),
        ("compose", compose), ("post_check", post_check), ("fallback", fallback),
        ("finalize", finalize),
    ):  # fmt: skip
        graph.add_node(name, node)
    graph.add_edge(START, "normalize")
    graph.add_edge("normalize", "cache_lookup")
    graph.add_conditional_edges("cache_lookup", after_cache, {"hit": END, "miss": "plan"})
    graph.add_conditional_edges(
        "plan", after_plan, {"simple": "simple", "structured": "structured", "retrieve": "retrieve"}
    )
    graph.add_conditional_edges(
        "structured",
        after_structured,
        {"compose": "compose", "retrieve": "retrieve", "fallback": "fallback"},
    )
    graph.add_conditional_edges(
        "retrieve",
        after_retrieve,
        {"compose": "compose", "retry": "retrieve", "fallback": "fallback"},
    )
    graph.add_edge("compose", "post_check")
    graph.add_conditional_edges(
        "post_check", after_post_check, {"finalize": "finalize", "fallback": "fallback"}
    )
    graph.add_edge("simple", "finalize")
    graph.add_edge("fallback", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile()
