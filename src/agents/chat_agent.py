"""Chat agent — interactive chat grounded in the applicant's own data.

Enablement recommendations come from the rule layer first; Qdrant retrieval
then surfaces matching programs, so answers aren't driven by raw semantic
similarity alone. Responds in the applicant's language.
"""

from __future__ import annotations

import json
from typing import Any

from src.agents.llm import chat
from src.config.prompts import CHAT_SYSTEM, CHAT_USER_TEMPLATE
from src.data.embeddings import embed
from src.graph.state import ApplicationState
from src.storage.qdrant import QdrantStore


def chat_node(state: ApplicationState) -> dict[str, Any]:
    """Answer a caseworker's question about this application, grounded in its decision record."""
    chat_history = state.get("chat_history", [])
    features = state.get("features", {})
    enablement_types = state.get("enablement_recs", [])
    decision_record = state.get("decision_record") or {}

    # Get the latest user message
    latest = chat_history[-1] if chat_history else {"role": "user", "content": ""}
    user_message = latest.get("content", "")

    # RAG retrieval from Qdrant based on the user message
    retrieved_items = []
    try:
        qdrant = QdrantStore()
        query_vec = embed(user_message)
        if "job_matching" in enablement_types:
            retrieved_items = qdrant.search_programs(query_vec, limit=3)
        elif "upskilling" in enablement_types:
            retrieved_items = qdrant.search_programs(query_vec, limit=3)
        else:
            retrieved_items = qdrant.search_programs(query_vec, limit=2)
        qdrant.close()
    except Exception:
        retrieved_items = []

    applicant_context = json.dumps(
        {
            "recommendation": decision_record.get("recommendation"),
            "confidence": decision_record.get("confidence"),
            "rationale": decision_record.get("rationale"),
            "validation_flags": decision_record.get("validation_flags", []),
            "shap_top_features": decision_record.get("shap_top_features", []),
            "eligibility_features": features,
            "enablement_types": enablement_types,
        },
        default=str,
        indent=2,
    )

    response = chat(
        system=CHAT_SYSTEM,
        user=CHAT_USER_TEMPLATE.format(
            applicant_context=applicant_context,
            retrieved_items=json.dumps(retrieved_items, default=str),
            user_message=user_message,
        ),
        temperature=0.1,  # case notes should be consistent, not creative
    )

    # Append the assistant response to chat history
    new_history = list(chat_history) + [{"role": "assistant", "content": response}]

    return {"chat_history": new_history}
