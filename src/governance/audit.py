"""Audit-log helpers — append-only trail in PostgreSQL for traceability and appeals."""

from __future__ import annotations

from src.storage.postgres import PostgresClient


def log_action(
    pg: PostgresClient,
    application_id: str,
    action: str,
    detail: dict | None = None,
    actor: str = "system",
):
    """Append an entry to the audit trail. Never updates or deletes prior entries."""
    pg.audit(application_id=application_id, action=action, detail=detail, actor=actor)
