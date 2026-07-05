"""Image OCR via a vision LLM (primary) with a Tesseract backstop.

qwen3.5:9b-mlx on Ollama ships without a vision projector (text-only), so a
dedicated vision model handles image OCR while qwen3.5 keeps the reasoning and
decisioning work. minicpm-v:8b tested accurate on Emirates ID extraction;
Tesseract covers the case where the vision model is unavailable.
"""

from __future__ import annotations

import base64
import io
import os
from typing import Any

import httpx
from PIL import Image

from src.config.settings import get_settings
from src.governance.tracing import langfuse_context, observe

VISION_MODEL = os.environ.get("VISION_MODEL", "minicpm-v:8b")


def _ollama_host() -> str:
    host = get_settings().ollama_host
    if "host.docker.internal" in host and not os.path.exists("/.dockerenv"):
        host = host.replace("host.docker.internal", "localhost")
    return host


@observe(as_type="generation", name="vision-ocr", capture_input=False)
def ocr_with_vision_model(image_bytes: bytes, prompt: str | None = None) -> str:
    """Send an image to the vision LLM for OCR / field extraction."""
    import uuid

    langfuse_context.update_current_observation(model=VISION_MODEL, metadata={"image_bytes": len(image_bytes)})
    b64 = base64.b64encode(image_bytes).decode()
    user_prompt = prompt or (
        f"[scan-ref:{uuid.uuid4().hex[:8]}]\n"
        "Read every piece of text on this card, line by line. "
        "Transcribe numbers and dates exactly as printed (dates stay in YYYY-MM-DD form). "
        "Output only the text, nothing else."
    )
    resp = httpx.post(
        f"{_ollama_host()}/api/chat",
        json={
            "model": VISION_MODEL,
            "messages": [
                {"role": "user", "content": user_prompt, "images": [b64]},
            ],
            "stream": False,
        },
        timeout=120.0,
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"]


def ocr_with_tesseract(image_bytes: bytes) -> str:
    """Classic OCR via Tesseract — reliable backstop if vision LLM is unavailable."""
    try:
        import pytesseract

        img = Image.open(io.BytesIO(image_bytes))
        return pytesseract.image_to_string(img)
    except ImportError:
        return "[OCR unavailable: pytesseract not installed]"
    except Exception as e:
        return f"[OCR error: {e}]"


def _parse_id_fields(text: str) -> dict[str, Any]:
    """Parse raw OCR text into structured Emirates ID fields."""
    import re

    text = text.replace("*", "")  # vision models wrap labels in markdown emphasis
    fields: dict[str, Any] = {}
    m = re.search(r"Name[:\s]*(.+)", text, re.I)
    if m:
        # Vision models sometimes prefix section headers ("Body Text: Name: X")
        # or markdown emphasis — keep only the name itself.
        name_val = m.group(1).split(":")[-1]
        fields["name"] = re.sub(r"[*_#|]", "", name_val).strip()
    m = re.search(r"(?:Emirates\s*ID|EID)[:\s]*(784-\d{4}-\d{7}-\d)", text, re.I)
    if m:
        fields["emirates_id"] = m.group(1)
    elif re.search(r"784-\d{4}-\d{7}-\d", text):
        fields["emirates_id"] = re.search(r"784-\d{4}-\d{7}-\d", text).group()
    m = re.search(r"(?:Date\s*of\s*Birth|DOB)[:\s]*(\d{4}-\d{2}-\d{2})", text, re.I)
    if m:
        fields["date_of_birth"] = m.group(1)
    m = re.search(r"Nationality[:\s]*(\w+)", text, re.I)
    if m:
        fields["nationality"] = m.group(1)
    return fields


def extract_image(image_bytes: bytes, doc_type: str = "emirates_id") -> dict[str, Any]:
    """Extract structured fields from an image document via OCR.

    Primary: vision LLM. Backstop: Tesseract (no model needed).
    """
    try:
        raw = ocr_with_vision_model(image_bytes)
        parsed = _parse_id_fields(raw) if doc_type in ("emirates_id", "handwritten_form") else {}
        return {"raw_text": raw, "method": f"{VISION_MODEL}_vision", "parsed": parsed}
    except Exception as e:
        text = ocr_with_tesseract(image_bytes)
        parsed = _parse_id_fields(text) if doc_type in ("emirates_id", "handwritten_form") else {}
        return {
            "raw_text": text,
            "method": "tesseract_fallback",
            "parsed": parsed,
            "vision_error": str(e),
        }
