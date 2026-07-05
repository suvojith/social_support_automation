"""Eligibility rubric + feature dictionary.

Thresholds are synthetic and illustrative, not real policy — but concrete
enough to drive the seeder, the classifier, and the SHAP explanations.
Label noise (~12%) is injected at generation time so the classifier has
something to actually learn and CV metrics stay realistic rather than ~1.0.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Rubric thresholds
INCOME_BAND_LOW = 3000.0  # AED/month per capita
INCOME_BAND_HIGH = 8000.0
WEALTH_BAND_LOW = 50000.0  # AED net worth
WEALTH_BAND_HIGH = 300000.0
INCOME_DISAGREEMENT_THRESHOLD = 0.15  # 15%
BORDERLINE_CUTOFF_MARGIN = 0.10  # ±10% of a band cutoff


def compute_per_capita_income(household_income: float, family_size: int) -> float:
    return household_income / max(family_size, 1)


def income_band(per_capita: float) -> str:
    if per_capita < INCOME_BAND_LOW:
        return "Low"
    if per_capita <= INCOME_BAND_HIGH:
        return "Medium"
    return "High"


def wealth_band(net_worth: float) -> str:
    if net_worth < WEALTH_BAND_LOW:
        return "Negative/Low"
    if net_worth <= WEALTH_BAND_HIGH:
        return "Medium"
    return "High"


def is_borderline(
    per_capita: float,
    income_from_bank: float,
    income_from_credit: float,
) -> bool:
    """Borderline → human review: per_capita within ±10% of a cutoff, OR income disagreement >15%."""
    near_low = abs(per_capita - INCOME_BAND_LOW) / INCOME_BAND_LOW <= BORDERLINE_CUTOFF_MARGIN
    near_high = abs(per_capita - INCOME_BAND_HIGH) / INCOME_BAND_HIGH <= BORDERLINE_CUTOFF_MARGIN
    base = max(income_from_bank, income_from_credit, 1.0)
    disagree = abs(income_from_bank - income_from_credit) / base > INCOME_DISAGREEMENT_THRESHOLD
    return near_low or near_high or disagree


def base_eligibility_label(ib: str, wb: str) -> int:
    """Deterministic rubric label: 1 = eligible_for_financial_support, 0 = soft_decline."""
    eligible = ib in ("Low", "Medium") and wb in ("Negative/Low", "Medium")
    return 1 if eligible else 0


# Feature dictionary (raw field → model feature)
FEATURE_COLUMNS = [
    "income_from_bank",
    "income_from_credit_report",
    "income_consistent",
    "income_used",
    "per_capita_income",
    "family_size",  # family_size OR dependents_count — not both (avoids double-counting)
    "net_worth",
    "employment_score",
    "age_band",
    "address_match",
]


@dataclass
class ApplicantFeatures:
    """The feature vector fed to the classifier."""

    income_from_bank: float
    income_from_credit_report: float
    income_consistent: bool
    income_used: float
    per_capita_income: float
    family_size: int
    net_worth: float
    employment_score: str  # categorical: Unemployed / Underemployed / Employed
    age_band: str  # categorical: <25 / 25-40 / 40-55 / >55
    address_match: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "income_from_bank": self.income_from_bank,
            "income_from_credit_report": self.income_from_credit_report,
            "income_consistent": int(self.income_consistent),
            "income_used": self.income_used,
            "per_capita_income": self.per_capita_income,
            "family_size": self.family_size,
            "net_worth": self.net_worth,
            "employment_score": self.employment_score,
            "age_band": self.age_band,
            "address_match": int(self.address_match),
        }


ENABLEMENT_LABELS = {
    "upskilling": "upskilling (training programs)",
    "job_matching": "job matching",
    "career_counseling": "career counseling",
}


def explain_decision(
    recommendation: str,
    features: dict[str, Any],
    enablement: list[str],
    validation_flags: list[dict] | None = None,
) -> str:
    """Write the case rationale from the applicant's own figures.

    Every stored decision carries this explanation: exact amounts against the
    exact thresholds that produced the outcome — auditable and reproducible,
    with no dependence on LLM phrasing.
    """
    per_capita = float(features.get("per_capita_income") or 0)
    net_worth = float(features.get("net_worth") or 0)
    bank = float(features.get("income_from_bank") or 0)
    credit = float(features.get("income_from_credit_report") or 0)
    family = int(features.get("family_size") or 1)
    employment = str(features.get("employment_score") or "Unemployed")
    ib = income_band(per_capita)
    wb = wealth_band(net_worth)

    income_context = {
        "Low": f"below the AED {INCOME_BAND_LOW:,.0f}/month support threshold",
        "Medium": f"between AED {INCOME_BAND_LOW:,.0f} and AED {INCOME_BAND_HIGH:,.0f}/month",
        "High": f"above the AED {INCOME_BAND_HIGH:,.0f}/month upper threshold",
    }[ib]
    wealth_context = {
        "Negative/Low": f"below the AED {WEALTH_BAND_LOW:,.0f} low-wealth mark",
        "Medium": f"between AED {WEALTH_BAND_LOW:,.0f} and AED {WEALTH_BAND_HIGH:,.0f}",
        "High": f"above the AED {WEALTH_BAND_HIGH:,.0f} wealth ceiling",
    }[wb]
    employment_phrase = {
        "Unemployed": "The applicant is currently unemployed",
        "Underemployed": "The applicant is underemployed (informal or part-time work)",
        "Employed": "The applicant is in stable formal employment",
    }.get(employment, f"Employment status: {employment}")

    base = max(bank, credit, 1.0)
    income_gap = abs(bank - credit) / base
    if bank and credit and income_gap <= INCOME_DISAGREEMENT_THRESHOLD:
        agreement = f"Bank-statement and credit-bureau income figures agree (AED {bank:,.0f} vs AED {credit:,.0f})"
    elif bank and credit:
        agreement = (
            f"Bank-statement income (AED {bank:,.0f}) and credit-bureau income (AED {credit:,.0f}) "
            f"differ by {income_gap:.0%}, beyond the {INCOME_DISAGREEMENT_THRESHOLD:.0%} tolerance"
        )
    else:
        agreement = "Income could not be corroborated across both financial documents"

    enab = ", ".join(ENABLEMENT_LABELS.get(e, e) for e in enablement) or "none"

    rubric_approves = base_eligibility_label(ib, wb) == 1

    if recommendation == "approve":
        if not rubric_approves:
            # Historical archive case where the recorded outcome deviates from
            # the rubric — a documented caseworker judgment call, not a formula.
            return (
                f"Approved by recorded caseworker discretion: per-capita income of AED {per_capita:,.0f}/month "
                f"({ib} band) and net worth of AED {net_worth:,.0f} ({wb}) would not ordinarily qualify under "
                f"the standard rubric, but discretionary factors documented in the case file prevailed. "
                f"{employment_phrase}. {agreement}. Recommended enablement: {enab}."
            )
        return (
            f"Approved for financial support: per-capita income of AED {per_capita:,.0f}/month across a "
            f"household of {family} places the case in the {ib} income band ({income_context}), and net worth "
            f"of AED {net_worth:,.0f} is {wealth_context}. {employment_phrase}. {agreement}. "
            f"Recommended enablement: {enab}."
        )

    if recommendation == "soft_decline":
        if rubric_approves:
            return (
                f"Declined by recorded caseworker discretion: per-capita income of AED {per_capita:,.0f}/month "
                f"({ib} band) and net worth of AED {net_worth:,.0f} ({wb}) would ordinarily qualify, but "
                f"discretionary factors documented in the case file led to refusal. {employment_phrase}. "
                f"{agreement}. Economic enablement is still offered: {enab}."
            )
        reasons = []
        if ib == "High":
            reasons.append(f"per-capita income of AED {per_capita:,.0f}/month is {income_context}")
        if wb == "High":
            reasons.append(f"net worth of AED {net_worth:,.0f} is {wealth_context}")
        return (
            f"Financial support declined — {' and '.join(reasons)} (household of {family}). "
            f"{employment_phrase}. {agreement}. Economic enablement is still offered: {enab}."
        )

    # human_review: name exactly what a caseworker has to resolve
    blockers = []
    seen = set()
    for flag in validation_flags or []:
        issue = str(flag.get("issue", "")).rstrip(".")
        if issue and issue.lower() not in seen:
            seen.add(issue.lower())
            blockers.append(issue)
    near_low = abs(per_capita - INCOME_BAND_LOW) / INCOME_BAND_LOW <= BORDERLINE_CUTOFF_MARGIN
    near_high = abs(per_capita - INCOME_BAND_HIGH) / INCOME_BAND_HIGH <= BORDERLINE_CUTOFF_MARGIN
    if near_low:
        blockers.append(f"per-capita income of AED {per_capita:,.0f}/month is within 10% of the AED {INCOME_BAND_LOW:,.0f} band cutoff")
    elif near_high:
        blockers.append(f"per-capita income of AED {per_capita:,.0f}/month is within 10% of the AED {INCOME_BAND_HIGH:,.0f} band cutoff")
    detail = "; ".join(blockers) if blockers else "the extracted records could not be reconciled automatically"
    return (
        f"Referred for caseworker review — this case cannot be auto-decided: {detail}. "
        f"Provisional assessment: {ib} income band, {wb} wealth band, household of {family}. "
        f"{employment_phrase}. Enablement pending review: {enab}."
    )


# Enablement matching
def enablement_recommendation(
    employment_status: str,
    income_band_val: str,
    has_qualification: bool,
) -> list[str]:
    """Rule layer that feeds Qdrant retrieval, so recommendations are grounded
    in the applicant's employment/income situation rather than similarity alone."""
    recs: list[str] = []
    if employment_status == "Unemployed":
        if has_qualification:
            recs.append("job_matching")
        else:
            recs.append("upskilling")
    elif employment_status == "Underemployed" or (employment_status == "Employed" and income_band_val in ("Low", "Medium")):
        recs.append("job_matching")
    elif employment_status == "Employed" and income_band_val == "High":
        recs.append("career_counseling")
    else:
        recs.append("career_counseling")
    return recs
