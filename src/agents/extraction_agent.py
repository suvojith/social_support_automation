"""Extraction agent — multimodal document extraction (ReAct).

Ingests: application form, bank statement, credit report, Emirates ID, resume,
assets/liabilities Excel. Routes each to the correct per-data-type extractor,
then mirrors the family members it found into Neo4j so the validation agent
can query for cross-document conflicts on this application.
"""

from __future__ import annotations

from typing import Any

from src.extraction import extract_document
from src.graph.state import ApplicationState
from src.storage.neo4j import Neo4jStore


def _sync_family_graph(app_id: str, extracted: dict[str, Any]):
    """Upsert applicant + family members (per source document) into the graph."""
    form = extracted.get("application_form", {}).get("parsed", {})
    credit = extracted.get("credit_report", {}).get("parsed", {})
    form_members = form.get("family_members") or []
    credit_members = credit.get("family_members") or []
    if not form_members and not credit_members:
        return

    store = Neo4jStore()
    try:
        store.upsert_applicant(app_id, form.get("applicant_name", ""), form.get("emirates_id", ""))
        for i, m in enumerate(form_members):
            store.upsert_family_member(
                application_id=app_id,
                member_id=f"{app_id}-F{i + 1}",
                name=m.get("name", ""),
                dob=str(m.get("dob", "")),
                relation=m.get("relation", ""),
                source_doc="application_form",
            )
        for i, m in enumerate(credit_members):
            store.upsert_family_member(
                application_id=app_id,
                member_id=f"{app_id}-C{i + 1}",
                name=m.get("name", ""),
                dob=str(m.get("dob", "")),
                relation=m.get("relation", ""),
                source_doc="credit_report",
            )
    finally:
        store.close()


def extraction_node(state: ApplicationState) -> dict[str, Any]:
    """Extract structured fields from all uploaded documents."""
    app_id = state.get("application_id", "")
    raw_uploads = state.get("raw_uploads", {})
    extracted: dict[str, Any] = {}

    for doc_type, payload in raw_uploads.items():
        result = extract_document(
            doc_type=doc_type,
            content=payload.get("content"),
            text=payload.get("text"),
            json_data=payload.get("json"),
            filename=payload.get("filename"),
        )
        extracted[doc_type] = result

    try:
        _sync_family_graph(app_id, extracted)
    except Exception:
        pass  # graph enrichment is best-effort; validation degrades gracefully

    return {
        "extracted_data": extracted,
        "family_graph_ref": app_id,
    }
