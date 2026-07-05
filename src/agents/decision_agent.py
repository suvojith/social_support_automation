"""Decision agent — recommendation plus borderline routing.

Outputs are recommendations for caseworker sign-off, never an autonomous
final ruling. Borderline or unresolvable cases route to human_review.
"""

from __future__ import annotations

import json
from typing import Any

from src.agents.llm import chat_json
from src.config.prompts import DECISION_SYSTEM, DECISION_USER_TEMPLATE
from src.data.rubric import enablement_recommendation, explain_decision
from src.governance.tracing import observe
from src.graph.state import ApplicationState
from src.models.classifier import predict


@observe(name="decision-agent", capture_input=False)
def decision_node(state: ApplicationState) -> dict[str, Any]:
    """Produce a recommendation: approve / soft_decline / human_review."""
    eligibility = state.get("eligibility_score", {})
    validation_flags = state.get("validation_flags", [])
    resolvable = state.get("resolvable", True)
    features = state.get("features", {})

    # Classifier prediction + SHAP
    classifier_result = {
        "prediction": "approve",
        "probability": 0.5,
        "shap_top_features": [],
        "feature_importances": [],
    }
    try:
        classifier_result = predict(features)
    except Exception as e:
        classifier_result["error"] = str(e)

    signal = eligibility.get("eligible_signal", "borderline")

    # Routing logic
    if signal == "borderline" or not resolvable:
        recommendation = "human_review"
    elif signal == "approve":
        recommendation = "approve"
    else:
        recommendation = "soft_decline"

    # Enablement recommendations come from the rule layer, not raw RAG similarity
    emp_status = features.get("employment_score", "Unemployed")
    ib = eligibility.get("income_band", "Low")
    has_qual = features.get("employment_score") in ("Employed", "Underemployed")  # proxy
    enablement_types = enablement_recommendation(emp_status, ib, has_qual)

    # LLM reasoning pass — a second opinion on the routing, traced in Langfuse
    llm_view = chat_json(
        system=DECISION_SYSTEM,
        user=DECISION_USER_TEMPLATE.format(
            eligibility_json=json.dumps(eligibility, default=str),
            validation_flags=json.dumps(validation_flags, default=str),
            classifier_pred=classifier_result.get("prediction", "unknown"),
            classifier_prob=classifier_result.get("probability", 0),
            shap_features=json.dumps(classifier_result.get("shap_top_features", []), default=str),
        ),
    )

    # The stored rationale is always built from the case's own figures —
    # deterministic and auditable. The LLM's view is advisory: it is recorded
    # only when it disagrees with the rubric outcome.
    rationale = explain_decision(recommendation, features, enablement_types, validation_flags)
    llm_recommendation = llm_view.get("recommendation") if isinstance(llm_view, dict) else None
    if llm_recommendation and llm_recommendation != recommendation:
        rationale += f" Note: the LLM reviewer suggested '{llm_recommendation}'; the rubric outcome stands for caseworker sign-off."

    decision = {
        "application_id": state.get("application_id", ""),
        "recommendation": recommendation,
        "confidence": round(classifier_result.get("probability", 0.5), 4),
        "rationale": rationale,
        "enablement": enablement_types,
        "classifier_pred": classifier_result.get("prediction"),
        "classifier_prob": classifier_result.get("probability"),
        "validation_flags": validation_flags,
        "features": features,
        "shap_values": classifier_result.get("shap_top_features", []),
        "feature_importances": classifier_result.get("feature_importances", []),
    }

    return {
        "decision": decision,
        "enablement_recs": enablement_types,
    }
