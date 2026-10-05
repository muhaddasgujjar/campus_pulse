"""LangGraph agent (D7, D15, Architectural.md Section 6).

graph.py (nodes and routing), state.py (AgentState, Plan), planner.py (LLM plan with a
rule-based fallback), prompts.py (composer rules), templates.py (0-LLM answers), postcheck.py
(invented-number check), cache.py (response cache), service.py (answer_question).
Budget: at most 2 LLM calls and 1 embedding call per turn. Tests use FakeLLM."""
