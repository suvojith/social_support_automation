"""Embeddings helper — wraps Ollama bge-m3 for vector generation."""

from __future__ import annotations

import os

import httpx

from src.config.settings import get_settings
from src.governance.tracing import observe


@observe(name="embed", capture_output=False)
def embed(text: str, model: str | None = None) -> list[float]:
    """Generate an embedding via Ollama's /api/embeddings endpoint."""
    s = get_settings()
    host = s.ollama_host
    if "host.docker.internal" in host and not os.path.exists("/.dockerenv"):
        host = host.replace("host.docker.internal", "localhost")
    resp = httpx.post(
        f"{host}/api/embeddings",
        json={"model": model or s.embed_model, "prompt": text},
        timeout=60.0,
    )
    resp.raise_for_status()
    return resp.json()["embedding"]


def embed_batch(texts: list[str], model: str | None = None) -> list[list[float]]:
    return [embed(t, model) for t in texts]
