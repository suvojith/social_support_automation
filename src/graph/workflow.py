"""LangGraph workflow — agentic orchestration.

State machine: orchestrator → extraction → validation → eligibility → decision.
The chat agent runs on a separate path (interactive chat after a decision is made).
Borderline or unresolvable cases branch to human_review rather than forcing
an automated ruling.

ReAct for tool-calling; Reflexion is scoped to the validation agent so its
self-critique latency stays contained. Langfuse traces every agent/LLM call.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from src.agents.decision_agent import decision_node
from src.agents.eligibility_agent import eligibility_node
from src.agents.extraction_agent import extraction_node
from src.agents.orchestrator import orchestrator_node
from src.agents.validation_agent import validation_node
from src.graph.state import ApplicationState


def _should_route_to_human(state: ApplicationState) -> str:
    """Conditional edge: route borderline/unresolvable cases to human_review."""
    eligibility = state.get("eligibility_score", {})
    resolvable = state.get("resolvable", True)
    signal = eligibility.get("eligible_signal", "borderline")

    if signal == "borderline" or not resolvable:
        return "human_review"
    return "finalize"


def build_workflow():
    """Build and compile the LangGraph StateGraph for the application workflow."""
    graph = StateGraph(ApplicationState)

    # 6 agents (orchestrator + 5 specialized)
    graph.add_node("orchestrator", orchestrator_node)
    graph.add_node("extraction", extraction_node)
    graph.add_node("validation", validation_node)
    graph.add_node("eligibility", eligibility_node)
    graph.add_node("decision", decision_node)
    graph.add_node("human_review", _human_review_node)

    # Edges: linear flow with a conditional branch before finalize
    graph.set_entry_point("orchestrator")
    graph.add_edge("orchestrator", "extraction")
    graph.add_edge("extraction", "validation")
    graph.add_edge("validation", "eligibility")
    graph.add_edge("eligibility", "decision")

    # Conditional: decision routes to human_review or finalize (END)
    graph.add_conditional_edges(
        "decision",
        _should_route_to_human,
        {"human_review": "human_review", "finalize": END},
    )
    graph.add_edge("human_review", END)

    return graph.compile()


def _human_review_node(state: ApplicationState) -> dict[str, Any]:
    """Mark the application for human review — a routing outcome, not a failure.

    The rationale names the exact conflicts or borderline figures a caseworker
    has to resolve, rather than a generic referral message.
    """
    from src.data.rubric import explain_decision

    decision = state.get("decision", {})
    decision["recommendation"] = "human_review"
    decision["rationale"] = explain_decision(
        "human_review",
        state.get("features", {}),
        decision.get("enablement", []),
        state.get("validation_flags", []),
    )
    return {"decision": decision}


# Singleton compiled graph
_workflow = None


def get_workflow():
    global _workflow
    if _workflow is None:
        _workflow = build_workflow()
    return _workflow
