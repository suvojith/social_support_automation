"""Shared LangGraph state.

This TypedDict flows through all six agents; each node reads what it needs
and returns the fields it owns, and LangGraph merges the updates.
"""

from __future__ import annotations

from typing import Any, TypedDict


class ApplicationState(TypedDict, total=False):
    # Identity + raw inputs
    application_id: str
    raw_uploads: dict[str, Any]  # doc_type -> {content, text, json, filename}

    # Extraction agent output — parsed fields per doc type
    extracted_data: dict[str, Any]  # doc_type -> parsed dict

    # Validation agent output — cross-doc conflict flags
    validation_flags: list[dict[str, Any]]
    resolvable: bool  # can validation agent reconcile conflicts?

    # Neo4j graph reference for family-member queries
    family_graph_ref: str  # application_id for graph lookups

    # Feature dictionary fed to the classifier
    features: dict[str, Any]

    # Eligibility agent output
    eligibility_score: dict[str, Any]  # income_band, wealth_band, signal, etc.

    # Decision agent output
    decision: dict[str, Any]  # recommendation, confidence, rationale, enablement

    # Enablement recommendations (upskilling / job matching / career counseling)
    enablement_recs: list[str]

    # Persisted decision record, loaded for chat grounding
    decision_record: dict[str, Any]

    # Chat history for the interactive chat agent
    chat_history: list[dict[str, str]]

    # Langfuse trace id for end-to-end observability
    trace_id: str
