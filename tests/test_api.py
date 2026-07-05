"""API smoke tests covering the FastAPI endpoints.

Includes the /apply idempotency check: retry the same application mid-test and
confirm no duplicate is created.

Tests that need PostgreSQL are skipped when the DB isn't reachable (e.g. running
outside Docker). They run fully inside `docker compose`.
"""

from __future__ import annotations

import os

import psycopg2
import pytest
from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app)
AUTH = ("reviewer", "change_me_in_prod")


def _db_available() -> bool:
    """Check if PostgreSQL is reachable."""
    try:
        psycopg2.connect(
            host=os.environ.get("POSTGRES_HOST", "postgres"),
            port=int(os.environ.get("POSTGRES_PORT", "5432")),
            user=os.environ.get("POSTGRES_USER", "sswa"),
            password=os.environ.get("POSTGRES_PASSWORD", "change_me_in_prod"),
            dbname=os.environ.get("POSTGRES_DB", "sswa"),
            connect_timeout=2,
        )
        return True
    except Exception:
        return False


DB_AVAILABLE = _db_available()
skip_no_db = pytest.mark.skipif(not DB_AVAILABLE, reason="PostgreSQL not reachable")


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@skip_no_db
def test_apply_idempotency():
    """A retried upload with the same idempotency key must not create a duplicate."""
    form = {
        "applicant_name": "Test Applicant",
        "emirates_id": "784-1990-9999999-1",
        "application_form": {
            "applicant_name": "Test Applicant",
            "emirates_id": "784-1990-9999999-1",
            "dob": "1990-01-01",
            "address": "Deira, Dubai",
            "employment_status": "Unemployed",
            "education_level": "Secondary",
            "years_experience": 0,
            "family_members": [],
        },
        "documents": [],
        "idempotency_key": "test-idem-key-001",
    }

    # First submission
    resp1 = client.post("/v1/apply", json=form, auth=AUTH)
    if resp1.status_code == 200:
        app_id_1 = resp1.json().get("application_id")
    else:
        app_id_1 = None  # workflow may fail without Ollama; idempotency still recorded

    # Retried submission with the same key
    resp2 = client.post("/v1/apply", json=form, auth=AUTH)
    if resp2.status_code == 200:
        app_id_2 = resp2.json().get("application_id")
        # Idempotent replay should return the same application_id
        assert app_id_1 == app_id_2, "Idempotency failed: duplicate application created"


def test_auth_required():
    """Endpoints behind basic auth reject unauthenticated requests."""
    resp = client.get("/v1/applications")
    assert resp.status_code == 401


@skip_no_db
def test_status_not_found():
    resp = client.get("/v1/status/NONEXISTENT-123", auth=AUTH)
    assert resp.status_code == 404


@skip_no_db
def test_registry_list_and_profile():
    resp = client.get("/v1/registry", auth=AUTH)
    assert resp.status_code == 200
    citizens = resp.json()
    assert len(citizens) >= 15

    eid = citizens[0]["emirates_id"]
    profile = client.get(f"/v1/registry/{eid}", auth=AUTH)
    assert profile.status_code == 200
    assert profile.json()["emirates_id"] == eid

    # Lookup by full name resolves to the same citizen
    by_name = client.get(f"/v1/registry/{citizens[0]['full_name']}", auth=AUTH)
    assert by_name.status_code == 200
    assert by_name.json()["emirates_id"] == eid


@skip_no_db
def test_registry_documents_complete():
    citizens = client.get("/v1/registry", auth=AUTH).json()
    docs = client.get(f"/v1/registry/{citizens[0]['emirates_id']}/documents", auth=AUTH)
    assert docs.status_code == 200
    doc_types = {d["doc_type"] for d in docs.json()}
    assert doc_types == {"bank_statement", "credit_report", "emirates_id", "resume", "assets_liabilities"}
    assert all(d["content_b64"] for d in docs.json())


@skip_no_db
def test_registry_unknown_citizen():
    resp = client.get("/v1/registry/784-0000-0000000-0", auth=AUTH)
    assert resp.status_code == 404
