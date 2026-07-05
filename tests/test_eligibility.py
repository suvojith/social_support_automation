"""Unit tests for the eligibility rubric and enablement rules."""

from __future__ import annotations

from src.data.rubric import (
    base_eligibility_label,
    compute_per_capita_income,
    enablement_recommendation,
    income_band,
    is_borderline,
    wealth_band,
)


def test_per_capita_income():
    assert compute_per_capita_income(12000, 4) == 3000.0
    assert compute_per_capita_income(5000, 0) == 5000.0  # guards divide-by-zero


def test_income_bands():
    assert income_band(2000) == "Low"
    assert income_band(3000) == "Medium"
    assert income_band(8000) == "Medium"
    assert income_band(8001) == "High"


def test_wealth_bands():
    assert wealth_band(40000) == "Negative/Low"
    assert wealth_band(50000) == "Medium"
    assert wealth_band(300000) == "Medium"
    assert wealth_band(300001) == "High"


def test_base_eligibility():
    # Low income + Low wealth = eligible
    assert base_eligibility_label("Low", "Negative/Low") == 1
    # Medium income + Medium wealth = eligible
    assert base_eligibility_label("Medium", "Medium") == 1
    # High income = soft decline
    assert base_eligibility_label("High", "Negative/Low") == 0
    # High wealth = soft decline
    assert base_eligibility_label("Low", "High") == 0


def test_borderline_detection():
    # Near the Low/Medium cutoff (3000) within 10%
    assert is_borderline(2950, 2900, 3000) is True
    # Near the Medium/High cutoff (8000) within 10%
    assert is_borderline(8200, 8000, 8100) is True
    # Income disagreement > 15%
    assert is_borderline(5000, 5000, 7000) is True
    # Clear case — not borderline
    assert is_borderline(4000, 4000, 4100) is False


def test_enablement_rules():
    # Unemployed + no qualification -> upskilling
    assert "upskilling" in enablement_recommendation("Unemployed", "Low", False)
    # Unemployed + qualification -> job matching
    assert "job_matching" in enablement_recommendation("Unemployed", "Low", True)
    # Underemployed -> job matching
    assert "job_matching" in enablement_recommendation("Underemployed", "Medium", False)
    # Employed + High income -> career counseling only
    assert "career_counseling" in enablement_recommendation("Employed", "High", True)
