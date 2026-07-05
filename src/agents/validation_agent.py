"""Validation agent — cross-document consistency checks with Reflexion self-critique.

Deterministic checks:
  - document completeness (missing financial evidence cannot be auto-decided)
  - identity: form vs the Emirates ID card OCR (ID number, name, DOB)
  - address: application form vs credit report
  - income: bank statement vs credit report (>15% disagreement)
  - employment/education: application form vs resume
  - family-member DOB conflicts across source documents (Neo4j graph query)

An LLM pass then reviews the extracted data and critiques its own findings
(Reflexion) before returning them.
"""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from typing import Any

from src.agents.llm import chat_json
from src.config.prompts import VALIDATION_SYSTEM, VALIDATION_USER_TEMPLATE
from src.governance.tracing import observe
from src.graph.state import ApplicationState
from src.storage.neo4j import Neo4jStore

REQUIRED_DOCS = ("bank_statement", "credit_report", "emirates_id", "resume", "assets_liabilities")
EMIRATES_ID_RE = re.compile(r"^784-\d{4}-\d{7}-\d$")


def _parsed(extracted: dict, doc_type: str) -> dict:
    return extracted.get(doc_type, {}).get("parsed", {}) or {}


def _completeness_flags(extracted: dict) -> list[dict]:
    """Missing or unreadable documents. Absent financial evidence blocks auto-decision."""
    flags = []
    missing = [d for d in REQUIRED_DOCS if d not in extracted or not extracted[d].get("raw")]
    if missing:
        flags.append(
            {
                "field": "documents",
                "issue": f"Missing or unreadable document(s): {', '.join(missing)}.",
                "severity": "high" if {"bank_statement", "credit_report"} & set(missing) else "medium",
            }
        )
    return flags


def _identity_flags(extracted: dict) -> list[dict]:
    """Form identity vs the Emirates ID card OCR: ID number, name, date of birth."""
    form = _parsed(extracted, "application_form")
    card = _parsed(extracted, "emirates_id")
    flags = []

    form_eid = (form.get("emirates_id") or "").strip()
    if form_eid and not EMIRATES_ID_RE.match(form_eid):
        flags.append(
            {"field": "emirates_id", "issue": "Emirates ID on the form is not in 784-YYYY-XXXXXXX-X format.", "severity": "medium"}
        )

    card_eid = (card.get("emirates_id") or "").strip()
    if form_eid and card_eid and form_eid != card_eid:
        flags.append(
            {"field": "emirates_id", "issue": f"ID number differs: form {form_eid} vs ID card OCR {card_eid}.", "severity": "medium"}
        )

    def _norm_name(value: str) -> str:
        # OCR output can carry markdown/punctuation artifacts around the name
        return re.sub(r"[^a-z ]", "", (value or "").lower()).strip()

    # Fuzzy match: OCR of romanized Arabic names varies by a character or two
    # (Mansoori/Mansouri), which is noise, not a different person.
    form_name = _norm_name(form.get("applicant_name") or "")
    card_name = _norm_name(card.get("name") or "")
    if form_name and card_name and SequenceMatcher(None, form_name, card_name).ratio() < 0.85:
        flags.append(
            {
                "field": "applicant_name",
                "issue": f"Name on the form ('{form_name}') differs from the ID card OCR ('{card_name}').",
                "severity": "medium",
            }
        )

    form_dob = str(form.get("dob") or "").strip()
    card_dob = str(card.get("date_of_birth") or "").strip()
    if form_dob and card_dob and form_dob != card_dob:
        flags.append({"field": "dob", "issue": f"Date of birth differs: form {form_dob} vs ID card OCR {card_dob}.", "severity": "medium"})
    return flags


def _employment_flags(extracted: dict) -> list[dict]:
    """Form employment/education/experience vs what the resume states."""
    form = _parsed(extracted, "application_form")
    resume = _parsed(extracted, "resume")
    flags = []

    form_edu = (form.get("education_level") or "").strip().lower()
    resume_edu = (resume.get("education_level") or "").strip().lower()
    if form_edu and resume_edu and form_edu != resume_edu:
        flags.append(
            {"field": "education_level", "issue": f"Education differs: form '{form_edu}' vs resume '{resume_edu}'.", "severity": "medium"}
        )

    form_years = form.get("years_experience")
    resume_years = resume.get("years_experience")
    if isinstance(form_years, (int, float)) and isinstance(resume_years, (int, float)) and abs(form_years - resume_years) > 1.0:
        flags.append(
            {
                "field": "years_experience",
                "issue": f"Experience differs: form states {form_years:g} years vs resume {resume_years:g} years.",
                "severity": "medium",
            }
        )
    return flags


@observe(name="validation-agent", capture_input=False)
def validation_node(state: ApplicationState) -> dict[str, Any]:
    """Cross-check extracted data across documents + run the Neo4j conflict query."""
    extracted = state.get("extracted_data", {})
    app_id = state.get("family_graph_ref", state.get("application_id", ""))

    # Family-member DOB conflicts across source documents (graph query)
    graph_conflicts = []
    try:
        neo4j = Neo4jStore()
        graph_conflicts = neo4j.find_conflicting_dobs(app_id)
        neo4j.close()
    except Exception as e:
        graph_conflicts = [{"error": str(e)}]

    # Address mismatch check
    form_addr = extracted.get("application_form", {}).get("parsed", {}).get("address", "")
    credit_addr = extracted.get("credit_report", {}).get("parsed", {}).get("address", "")
    address_match = form_addr == credit_addr if form_addr and credit_addr else True

    # Income consistency check
    bank_income = extracted.get("bank_statement", {}).get("parsed", {}).get("income_from_bank", 0)
    credit_income = extracted.get("credit_report", {}).get("parsed", {}).get("income_from_credit_report", 0)
    income_consistent = True
    if bank_income and credit_income:
        base = max(bank_income, credit_income, 1.0)
        income_consistent = abs(bank_income - credit_income) / base <= 0.15

    # LLM-powered validation pass with Reflexion
    validation_input = json.dumps(extracted, default=str, indent=2)
    result = chat_json(
        system=VALIDATION_SYSTEM,
        user=VALIDATION_USER_TEMPLATE.format(
            extracted_json=validation_input,
            graph_conflicts=json.dumps(graph_conflicts, default=str),
        ),
    )

    flags = []
    resolvable = True
    if result and isinstance(result, dict):
        # Keep only substantive LLM findings — "low" is informational noise
        flags = [f for f in result.get("flags", []) if isinstance(f, dict) and f.get("severity") in ("medium", "high")]
        resolvable = result.get("resolvable", True)

    # Add programmatic flags
    completeness = _completeness_flags(extracted)
    flags.extend(completeness)
    if any(f["severity"] == "high" for f in completeness):
        resolvable = False  # no financial evidence — a caseworker has to look

    flags.extend(_identity_flags(extracted))
    flags.extend(_employment_flags(extracted))

    if not address_match:
        flags.append({"field": "address", "issue": "Application form and credit report addresses differ.", "severity": "medium"})
    if not income_consistent:
        flags.append({"field": "income", "issue": "Bank and credit-report income disagree >15%.", "severity": "high"})
        resolvable = False
    if graph_conflicts and not any(isinstance(g, dict) and "error" in g for g in graph_conflicts):
        flags.append(
            {
                "field": "family_member_dob",
                "issue": f"DOB conflict detected for {len(graph_conflicts)} family member(s) across documents.",
                "severity": "high",
            }
        )
        resolvable = False

    return {
        "validation_flags": flags,
        "resolvable": resolvable,
    }
