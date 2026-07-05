"""Langfuse tracing — every agent and model call becomes an observation.

The v2 SDK decorators pick up LANGFUSE_HOST / LANGFUSE_PUBLIC_KEY /
LANGFUSE_SECRET_KEY from the environment and batch events in a background
thread, so tracing never sits on the request path. If the SDK is missing or
incompatible, everything degrades to no-ops — observability must never be
the reason a decision fails.
"""

from __future__ import annotations

try:
    from langfuse.decorators import langfuse_context, observe  # noqa: F401

    TRACING_ENABLED = True
except Exception:  # pragma: no cover - fallback when the SDK is unavailable
    TRACING_ENABLED = False

    def observe(*args, **kwargs):
        if len(args) == 1 and callable(args[0]) and not kwargs:
            return args[0]

        def wrap(fn):
            return fn

        return wrap

    class _NoopContext:
        def update_current_trace(self, **kwargs):
            pass

        def update_current_observation(self, **kwargs):
            pass

        def flush(self):
            pass

    langfuse_context = _NoopContext()


def flush():
    """Push any buffered events; safe to call after every request."""
    try:
        langfuse_context.flush()
    except Exception:
        pass
