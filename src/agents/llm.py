"""LLM helper — wraps Ollama chat API for agent reasoning (ReAct)."""

from __future__ import annotations

import os
import uuid
from typing import Any

import httpx

from src.config.settings import get_settings


def _host() -> str:
    host = get_settings().ollama_host
    # Only replace host.docker.internal with localhost when running OUTSIDE Docker
    # (e.g. local tests). Inside Docker, host.docker.internal is correct.
    if "host.docker.internal" in host and not os.path.exists("/.dockerenv"):
        host = host.replace("host.docker.internal", "localhost")
    return host


def chat(
    system: str,
    user: str,
    model: str | None = None,
    images: list[str] | None = None,
    temperature: float = 0.3,
    max_tokens: int = 2000,
) -> str:
    """Call the Ollama chat endpoint with a system + user message (ReAct reasoning)."""
    # Unique first token per request: successive prompts here share long prefixes
    # (same templates, different JSON), which has triggered KV-cache bleed in
    # Ollama — answers resuming from a previous request's context. Forcing
    # divergence at the start of the user turn prevents stale cache resumption.
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"[case-ref:{uuid.uuid4().hex[:8]}]\n{user}"},
    ]
    payload: dict[str, Any] = {
        "model": model or get_settings().llm_model,
        "messages": messages,
        "stream": False,
        # Disable thinking mode: it slows responses and can burn the whole
        # token budget on reasoning, leaving message.content empty.
        "think": False,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    if images:
        payload["messages"][-1]["images"] = images

    resp = httpx.post(f"{_host()}/api/chat", json=payload, timeout=180.0)
    resp.raise_for_status()
    return resp.json()["message"]["content"]


def chat_json(
    system: str,
    user: str,
    model: str | None = None,
    images: list[str] | None = None,
) -> dict | list | None:
    """Call chat() and parse the response as JSON (best-effort)."""
    import json
    import re

    raw = chat(system, user, model, images)
    # Strip markdown fences
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`")
    match = re.search(r"[\[{].*[\]}]", cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None
