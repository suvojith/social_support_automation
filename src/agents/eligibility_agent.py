"""Eligibility agent — applies the eligibility rubric to compute a signal.

Does not make the final decision; it computes income_band, wealth_band, and
an eligibility signal (approve / soft_decline / borderline) for the decision
agent to act on.
"""

from __future__ import annotations

import json
from typing import Any

from src.agents.llm import chat_json
from src.config.prompts import ELIGIBILITY_SYSTEM, ELIGIBILITY_USER_TEMPLATE
from src.data.rubric import (
    compute_per_capita_income,
    income_band,
    is_borderline,
    wealth_band,
)
from src.graph.state import ApplicationState


def _build_features(extracted: dict) -> dict[str, Any]:
    """Assemble the classifier feature dictionary from extracted document data."""
    form = extracted.get("application_form", {}).get("parsed", {})
    bank = extracted.get("bank_statement", {}).get("parsed", {})
    credit = extracted.get("credit_report", {}).get("parsed", {})
    assets = extracted.get("assets_liabilities", {}).get("parsed", {})

    income_bank = bank.get("income_from_bank", 0.0)
    income_credit = credit.get("income_from_credit_report", 0.0)
    income_consistent = abs(income_bank - income_credit) / max(income_bank, income_credit, 1.0) <= 0.15
    income_used = min(income_bank, income_credit)
    family_size = len(form.get("family_members", [])) + 1
    per_capita = compute_per_capita_income(income_used * family_size, family_size)
    net_worth = assets.get("net_worth", 0.0)

    # age_band from DOB
    dob = form.get("dob", "1990-01-01")
    age = 2026 - int(dob[:4]) if dob[:4].isdigit() else 30
    if age < 25:
        age_b = "<25"
    elif age <= 40:
        age_b = "25-40"
    elif age <= 55:
        age_b = "40-55"
    else:
        age_b = ">55"

    return {
        "income_from_bank": income_bank,
        "income_from_credit_report": income_credit,
        "income_consistent": int(income_consistent),
        "income_used": income_used,
        "per_capita_income": round(per_capita, 2),
        "family_size": family_size,
        "net_worth": net_worth,
        "employment_score": form.get("employment_status", "Unemployed"),
        "age_band": age_b,
        "address_match": int(form.get("address", "") == credit.get("address", "")),
    }


def eligibility_node(state: ApplicationState) -> dict[str, Any]:
    """Apply the rubric + LLM reasoning to compute the eligibility signal."""
    extracted = state.get("extracted_data", {})
    features = _build_features(extracted)

    # Programmatic rubric computation
    ib = income_band(features["per_capita_income"])
    wb = wealth_band(features["net_worth"])
    borderline = is_borderline(
        features["per_capita_income"],
        features["income_from_bank"],
        features["income_from_credit_report"],
    )

    if borderline:
        signal = "borderline"
    elif ib in ("Low", "Medium") and wb in ("Negative/Low", "Medium"):
        signal = "approve"
    else:
        signal = "soft_decline"

    # LLM reasoning pass (ReAct)
    result = chat_json(
        system=ELIGIBILITY_SYSTEM,
        user=ELIGIBILITY_USER_TEMPLATE.format(features_json=json.dumps(features, indent=2)),
    )

    eligibility = {
        "income_band": ib,
        "wealth_band": wb,
        "per_capita_income": features["per_capita_income"],
        "employment_status": features["employment_score"],
        "eligible_signal": signal,
        "llm_reasoning": result if result else {"note": "LLM pass skipped"},
    }

    return {
        "features": features,
        "eligibility_score": eligibility,
    }
