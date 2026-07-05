"""PostgreSQL client + schema initialization.

Source of truth: applications, decisions, audit trail (append-only), idempotency keys.
"""

from __future__ import annotations

import psycopg2
from psycopg2.extras import Json, RealDictCursor

from src.config.settings import get_settings

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS applications (
    id              TEXT PRIMARY KEY,
    applicant_name  TEXT NOT NULL,
    emirates_id     TEXT NOT NULL,
    submitted_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status          TEXT NOT NULL DEFAULT 'submitted',
    raw_form        JSONB NOT NULL,
    idempotency_key TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS decisions (
    id              SERIAL PRIMARY KEY,
    application_id  TEXT NOT NULL REFERENCES applications(id),
    recommendation  TEXT NOT NULL,
    confidence      REAL NOT NULL,
    rationale       TEXT,
    enablement      JSONB,
    features        JSONB,
    shap_values     JSONB,
    classifier_pred TEXT,
    classifier_prob REAL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Append-only audit trail: only the decision service inserts, never updates/deletes.
CREATE TABLE IF NOT EXISTS audit_log (
    id              SERIAL PRIMARY KEY,
    application_id  TEXT NOT NULL,
    action          TEXT NOT NULL,
    actor           TEXT NOT NULL DEFAULT 'system',
    detail          JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Idempotency keys for /apply: a retried upload must not create a duplicate
-- application. The request hash detects a key being reused for a DIFFERENT
-- payload, which is rejected rather than silently replayed.
CREATE TABLE IF NOT EXISTS idempotency_keys (
    key             TEXT PRIMARY KEY,
    application_id  TEXT NOT NULL,
    request_hash    TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ NOT NULL
);

ALTER TABLE idempotency_keys ADD COLUMN IF NOT EXISTS request_hash TEXT;
ALTER TABLE decisions ADD COLUMN IF NOT EXISTS validation_flags JSONB;

-- Citizen registry: the pre-existing government registry the UI integrates with.
-- Identity, employment, and family data live here; financials live in documents.
CREATE TABLE IF NOT EXISTS registry_citizens (
    emirates_id       TEXT PRIMARY KEY,
    full_name         TEXT NOT NULL,
    gender            TEXT,
    dob               DATE NOT NULL,
    address           TEXT NOT NULL,
    employment_status TEXT NOT NULL,
    education_level   TEXT NOT NULL,
    years_experience  REAL NOT NULL DEFAULT 0,
    employer          TEXT,
    family_members    JSONB NOT NULL DEFAULT '[]',
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_decisions_app ON decisions(application_id);
CREATE INDEX IF NOT EXISTS idx_audit_app ON audit_log(application_id);
CREATE INDEX IF NOT EXISTS idx_registry_name ON registry_citizens(LOWER(full_name));
"""


class PostgresClient:
    def __init__(self, dsn: str | None = None):
        self.dsn = dsn or get_settings().pg_dsn
        self._conn = None

    @property
    def conn(self):
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(self.dsn)
        return self._conn

    def init_schema(self):
        with self.conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
        self.conn.commit()

    def create_application(
        self,
        app_id: str,
        applicant_name: str,
        emirates_id: str,
        raw_form: dict,
        idempotency_key: str | None = None,
    ) -> str:
        with self.conn.cursor() as cur:
            cur.execute(
                """INSERT INTO applications (id, applicant_name, emirates_id, raw_form, idempotency_key)
                   VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                (app_id, applicant_name, emirates_id, Json(raw_form), idempotency_key),
            )
            row = cur.fetchone()
        self.conn.commit()
        return row[0]

    def check_idempotency(self, key: str) -> dict | None:
        """Return {application_id, request_hash} if the key was seen before, else None."""
        if not key:
            return None
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """SELECT application_id, request_hash FROM idempotency_keys
                   WHERE key = %s AND expires_at > NOW()""",
                (key,),
            )
            row = cur.fetchone()
        return dict(row) if row else None

    def record_idempotency(self, key: str, application_id: str, request_hash: str | None = None, ttl_hours: int = 24):
        if not key:
            return
        with self.conn.cursor() as cur:
            cur.execute(
                """INSERT INTO idempotency_keys (key, application_id, request_hash, expires_at)
                   VALUES (%s, %s, %s, NOW() + INTERVAL '%s hours')
                   ON CONFLICT (key) DO NOTHING""",
                (key, application_id, request_hash, ttl_hours),
            )
        self.conn.commit()

    def get_application(self, app_id: str) -> dict | None:
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM applications WHERE id = %s", (app_id,))
            return cur.fetchone()

    def update_status(self, app_id: str, status: str):
        with self.conn.cursor() as cur:
            cur.execute("UPDATE applications SET status = %s WHERE id = %s", (status, app_id))
        self.conn.commit()

    def save_decision(self, decision: dict, replace: bool = False):
        with self.conn.cursor() as cur:
            if replace:
                cur.execute("DELETE FROM decisions WHERE application_id = %s", (decision["application_id"],))
            cur.execute(
                """INSERT INTO decisions
                   (application_id, recommendation, confidence, rationale, enablement,
                    features, shap_values, classifier_pred, classifier_prob, validation_flags)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    decision["application_id"],
                    decision["recommendation"],
                    decision["confidence"],
                    decision.get("rationale"),
                    Json(decision.get("enablement")),
                    Json(decision.get("features")),
                    Json(decision.get("shap_values")),
                    decision.get("classifier_pred"),
                    decision.get("classifier_prob"),
                    Json(decision.get("validation_flags")),
                ),
            )
        self.conn.commit()

    def get_decision(self, app_id: str) -> dict | None:
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """SELECT * FROM decisions WHERE application_id = %s
                   ORDER BY created_at DESC LIMIT 1""",
                (app_id,),
            )
            row = cur.fetchone()
        return dict(row) if row else None

    def audit(self, application_id: str, action: str, detail: dict | None = None, actor: str = "system"):
        with self.conn.cursor() as cur:
            cur.execute(
                """INSERT INTO audit_log (application_id, action, actor, detail)
                   VALUES (%s, %s, %s, %s)""",
                (application_id, action, actor, Json(detail) if detail else None),
            )
        self.conn.commit()

    def upsert_citizen(self, profile: dict):
        with self.conn.cursor() as cur:
            cur.execute(
                """INSERT INTO registry_citizens
                   (emirates_id, full_name, gender, dob, address, employment_status,
                    education_level, years_experience, employer, family_members, updated_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                   ON CONFLICT (emirates_id) DO UPDATE SET
                     full_name = EXCLUDED.full_name,
                     gender = EXCLUDED.gender,
                     dob = EXCLUDED.dob,
                     address = EXCLUDED.address,
                     employment_status = EXCLUDED.employment_status,
                     education_level = EXCLUDED.education_level,
                     years_experience = EXCLUDED.years_experience,
                     employer = EXCLUDED.employer,
                     family_members = EXCLUDED.family_members,
                     updated_at = NOW()""",
                (
                    profile["emirates_id"],
                    profile["applicant_name"],
                    profile.get("gender"),
                    profile["dob"],
                    profile["address"],
                    profile["employment_status"],
                    profile["education_level"],
                    profile.get("years_experience", 0),
                    profile.get("employer"),
                    Json(profile.get("family_members", [])),
                ),
            )
        self.conn.commit()

    def get_citizen(self, query: str) -> dict | None:
        """Look up a registry citizen by Emirates ID, falling back to full name."""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM registry_citizens WHERE emirates_id = %s", (query,))
            row = cur.fetchone()
            if not row:
                cur.execute(
                    "SELECT * FROM registry_citizens WHERE LOWER(full_name) = LOWER(%s)",
                    (query.strip(),),
                )
                row = cur.fetchone()
        return dict(row) if row else None

    def list_citizens(self) -> list[dict]:
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """SELECT emirates_id, full_name, dob, address, employment_status,
                          education_level, years_experience, employer,
                          jsonb_array_length(family_members) + 1 AS family_size
                   FROM registry_citizens ORDER BY full_name"""
            )
            return [dict(r) for r in cur.fetchall()]

    def list_applications(self, limit: int = 100) -> list[dict]:
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM applications ORDER BY submitted_at DESC LIMIT %s", (limit,))
            return [dict(r) for r in cur.fetchall()]

    def get_audit(self, application_id: str) -> list[dict]:
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """SELECT action, actor, detail, created_at FROM audit_log
                   WHERE application_id = %s ORDER BY created_at""",
                (application_id,),
            )
            return [dict(r) for r in cur.fetchall()]

    def status_counts(self) -> dict[str, int]:
        """Application counts per status across the whole table (dashboard metrics)."""
        with self.conn.cursor() as cur:
            cur.execute("SELECT status, COUNT(*) FROM applications GROUP BY status")
            return {status: int(count) for status, count in cur.fetchall()}

    def close(self):
        if self._conn and not self._conn.closed:
            self._conn.close()
