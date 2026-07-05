"""OCR smoke test — verifies the image→text path in isolation.

Usage: python -m tests.ocr_smoke_test

Worth running before anything that depends on extraction: it generates a mock
Emirates ID card and checks that at least one OCR backend (vision LLM or
Tesseract) can pull structured fields out of it.
"""

from __future__ import annotations

import sys

from src.config.settings import get_settings
from src.data.synthetic import _make_emirates_id_image
from src.extraction.image_ocr import extract_image


def main():
    print("=" * 60)
    print("  OCR Smoke Test — image→text path")
    print("=" * 60)
    settings = get_settings()
    print(f"LLM (reasoning): {settings.llm_model}")
    print(f"Ollama: {settings.ollama_host}")

    img = _make_emirates_id_image("Ahmed Al Mansoori", "784-1990-1234567-1", "1990-01-01")
    print(f"Generated mock Emirates ID image ({len(img)} bytes)")

    print("\nRunning OCR extraction...")
    try:
        result = extract_image(img, "emirates_id")
        method = result.get("method", "unknown")
        print(f"Method: {method}")
        print(f"Raw output: {result.get('raw_text', '')[:300]}")
        parsed = result.get("parsed", {})
        print(f"Parsed fields: {parsed}")

        if parsed and (parsed.get("name") or parsed.get("emirates_id")):
            print(f"\n✅ OCR SMOKE TEST PASSED — {method} works.")
            return 0
        print("\n❌ OCR SMOKE TEST FAILED — no fields parsed.")
        return 1
    except Exception as e:
        print(f"\n❌ OCR SMOKE TEST FAILED: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
