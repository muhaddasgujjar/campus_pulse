"""LangGraph agent (D7, D15), built in M2.

Planned modules (Architectural.md Section 6): graph.py (the graph), state.py (AgentState),
nodes/ (normalize, plan, tools, grade, compose, fallback), prompts.py (composer rules).
Budget: at most 2 LLM calls and 1 embedding call per turn. Tests use FakeLLM."""
