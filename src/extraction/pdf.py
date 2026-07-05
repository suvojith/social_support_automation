"""PDF text extraction via pypdf."""

from __future__ import annotations

import io

from pypdf import PdfReader


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract text from a PDF file's bytes."""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    text_parts = []
    for page in reader.pages:
        text_parts.append(page.extract_text() or "")
    return "\n".join(text_parts).strip()


def extract_text(content: bytes, filename: str | None = None) -> str:
    """Extract text from content that may be PDF or plain text.

    The magic bytes decide, not the filename — a mislabeled or corrupted
    "PDF" degrades to plain-text decoding instead of failing the workflow.
    """
    if content[:4] == b"%PDF":
        try:
            return extract_pdf_text(content)
        except Exception:
            return content.decode("utf-8", errors="replace")
    return content.decode("utf-8", errors="replace")
