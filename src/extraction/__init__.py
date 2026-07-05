"""Unified multimodal extraction — one entry point for all 5 document types.

Per-data-type tools:
  - Text (forms, resume, credit report): pypdf, with regex field parsers
  - Images (Emirates ID, handwritten forms): vision LLM OCR, Tesseract backstop
  - Tabular (assets/liabilities Excel): pandas / openpyxl
"""

from __future__ import annotations

import json
from typing import Any

from src.extraction.excel import extract_excel
from src.extraction.image_ocr import extract_image
from src.extraction.pdf import extract_text


def extract_document(
    doc_type: str,
    content: bytes | None = None,
    text: str | None = None,
    json_data: dict | None = None,
    filename: str | None = None,
) -> dict[str, Any]:
    """Route to the correct extractor based on document type.

    Returns a dict with 'doc_type', 'raw', and 'parsed' fields.
    """
    result: dict[str, Any] = {"doc_type": doc_type}

    if doc_type == "application_form":
        data = json_data or {}
        if not data and text:
            data = json.loads(text)
        result["raw"] = json.dumps(data)
        result["parsed"] = data

    elif doc_type == "bank_statement":
        raw = text or (extract_text(content, filename) if content else "")
        result["raw"] = raw
        result["parsed"] = _parse_bank_statement(raw)

    elif doc_type == "credit_report":
        raw = text or (extract_text(content, filename) if content else "")
        result["raw"] = raw
        result["parsed"] = _parse_credit_report(raw)

    elif doc_type in ("emirates_id", "handwritten_form"):
        if content:
            ocr_result = extract_image(content, doc_type)
            result["raw"] = ocr_result["raw_text"]
            parsed = dict(ocr_result.get("parsed", {}))
            if doc_type == "handwritten_form":
                parsed.update(_parse_form_fields(result["raw"]))
            result["parsed"] = parsed
            result["ocr_method"] = ocr_result.get("method", "vision")
        else:
            result["raw"] = ""
            result["parsed"] = {}

    elif doc_type == "resume":
        raw = text or (extract_text(content, filename) if content else "")
        result["raw"] = raw
        result["parsed"] = _parse_resume(raw)

    elif doc_type == "assets_liabilities":
        if content:
            result["parsed"] = extract_excel(content)
            result["raw"] = json.dumps(result["parsed"])
        else:
            result["raw"] = ""
            result["parsed"] = {}

    else:
        result["raw"] = text or ""
        result["parsed"] = {}

    return result


def _parse_form_fields(text: str) -> dict:
    """Extract the form fields a handwritten application carries beyond identity."""
    import re

    text = text.replace("*", "")  # vision models wrap labels in markdown emphasis
    fields: dict = {}
    m = re.search(r"Address[:\s]*(.+)", text, re.I)
    if m:
        fields["address"] = m.group(1).strip()
    m = re.search(r"Employment[:\s]*(\w+)", text, re.I)
    if m:
        fields["employment_status"] = m.group(1).strip()
    m = re.search(r"Family members[:\s]*(\d+)", text, re.I)
    if m:
        fields["family_members_declared"] = int(m.group(1))
    return fields


def _parse_bank_statement(text: str) -> dict:
    """Extract key fields from bank statement text."""
    import re

    income = 0.0
    m = re.search(r"(?:Salary Deposits|Monthly Salary)[:\s]*AED\s*([\d,]+\.?\d*)", text, re.I)
    if m:
        income = float(m.group(1).replace(",", ""))
    address = ""
    m = re.search(r"Address on file[:\s]*(.+)", text, re.I)
    if m:
        address = m.group(1).strip()
    return {"income_from_bank": income, "address": address}


def _parse_credit_report(text: str) -> dict:
    """Extract key fields from credit report text."""
    import re

    income = 0.0
    m = re.search(r"Reported Monthly Income[:\s]*AED\s*([\d,]+\.?\d*)", text, re.I)
    if m:
        income = float(m.group(1).replace(",", ""))
    address = ""
    m = re.search(r"Address on file[:\s]*(.+)", text, re.I)
    if m:
        address = m.group(1).strip()
    members = [
        {"name": fm.group(1).strip(), "dob": fm.group(2), "relation": fm.group(3)}
        for fm in re.finditer(r"^-\s+(.+?)\s*\|\s*DOB:\s*(\d{4}-\d{2}-\d{2})\s*\|\s*Relation:\s*(\w+)", text, re.M)
    ]
    return {"income_from_credit_report": income, "address": address, "family_members": members}


def _parse_resume(text: str) -> dict:
    """Extract key fields from resume text."""
    import re

    years = 0.0
    m = re.search(r"Years of Experience[:\s]*([\d.]+)", text, re.I)
    if m:
        years = float(m.group(1))
    education = ""
    m = re.search(r"Education[:\s]*(\w+)", text, re.I)
    if m:
        education = m.group(1)
    return {"years_experience": years, "education_level": education}
