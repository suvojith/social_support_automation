"""Orchestrator agent — the master agent coordinating the five specialized agents.

Entry point of the LangGraph workflow: sets up the trace context, then hands
off to extraction → validation → eligibility → decision.
"""

from __future__ import annotations

from typing import Any

from src.graph.state import ApplicationState


def orchestrator_node(state: ApplicationState) -> dict[str, Any]:
    """Initialize the workflow state and set the trace id."""
    import uuid

    return {
        "trace_id": state.get("trace_id", str(uuid.uuid4())),
    }
