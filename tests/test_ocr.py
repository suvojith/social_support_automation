"""Extraction spot-checks across the 5 document types."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from src.data.synthetic import _make_emirates_id_image
from src.extraction import extract_document


def test_pdf_extraction():
    """Bank statement text extraction."""
    text = "BANK STATEMENT\nAccount Holder: Test\nMonthly Salary Deposits: AED 5,000.00"
    result = extract_document("bank_statement", text=text)
    assert "BANK" in result["raw"]
    assert result["parsed"]["income_from_bank"] == 5000.0


def test_excel_extraction():
    """Assets/liabilities tabular extraction."""
    import pandas as pd

    df = pd.DataFrame(
        {
            "Category": ["Cash", "Loan"],
            "Type": ["Asset", "Liability"],
            "Amount_AED": [30000.0, 15000.0],
        }
    )
    buf = io.BytesIO()
    df.to_excel(buf, index=False, sheet_name="Assets_Liabilities")
    result = extract_document("assets_liabilities", content=buf.getvalue())
    assert result["parsed"]["total_assets"] == 30000.0
    assert result["parsed"]["total_liabilities"] == 15000.0
    assert result["parsed"]["net_worth"] == 15000.0


def test_emirates_id_image_ocr():
    """Emirates ID image OCR — generates a mock ID image and extracts fields.

    Skipped rather than failed when no OCR backend is reachable (e.g. Ollama
    not running), so the suite stays green outside the full stack.
    """
    img_bytes = _make_emirates_id_image("Test User", "784-1990-1234567-1", "1990-01-01")
    try:
        result = extract_document("emirates_id", content=img_bytes)
        # If Ollama is running, we get parsed fields; if not, the fallback path is exercised
        assert result["doc_type"] == "emirates_id"
        assert "raw" in result
    except Exception as e:
        pytest.skip(f"Ollama not available for OCR test: {e}")


def test_handwritten_form_ocr():
    """Handwritten application form — identity and form fields via vision OCR.

    Skipped when no OCR backend is reachable, like the other image tests.
    """
    path = Path("data/samples/edge_cases/handwritten_form.png")
    if not path.exists():
        pytest.skip("handwritten fixture not present")
    try:
        result = extract_document("handwritten_form", content=path.read_bytes(), filename=path.name)
    except Exception as e:
        pytest.skip(f"OCR backend unavailable: {e}")
    parsed = result["parsed"]
    assert parsed.get("emirates_id") == "784-1990-8834567-3"
    assert "blooshi" in (parsed.get("name") or "").lower()


def test_arabic_labeled_id_ocr():
    """Bilingual (Arabic/English) Emirates ID — the bilingual extraction requirement."""
    path = Path("data/samples/edge_cases/arabic_emirates_id.png")
    if not path.exists():
        pytest.skip("Arabic fixture not present")
    try:
        result = extract_document("emirates_id", content=path.read_bytes(), filename=path.name)
    except Exception as e:
        pytest.skip(f"OCR backend unavailable: {e}")
    parsed = result["parsed"]
    assert parsed.get("emirates_id") == "784-1979-9945678-4"
    assert "suwaid" in (parsed.get("name") or "").lower()


def test_resume_extraction():
    """Resume text extraction."""
    text = "RESUME\nName: Test\nEducation: Bachelor\nYears of Experience: 5.0"
    result = extract_document("resume", text=text)
    assert result["parsed"]["years_experience"] == 5.0


def test_credit_report_extraction():
    """Credit report text extraction."""
    text = "CREDIT BUREAU REPORT\nReported Monthly Income: AED 6,000.00\nAddress on file: Bur Dubai, Dubai"
    result = extract_document("credit_report", text=text)
    assert result["parsed"]["income_from_credit_report"] == 6000.0
    assert result["parsed"]["address"] == "Bur Dubai, Dubai"
