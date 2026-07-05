"""FastAPI application — model serving + agent endpoints.

Endpoints:
  POST /v1/apply    — submit application + documents (idempotency key supported)
  POST /v1/chat     — interactive chat with the chat agent
  GET  /v1/status/{id}    — application status
  GET  /v1/decision/{id}  — decision + SHAP explainability
  GET  /health      — health check
  GET  /docs        — OpenAPI/Swagger auto-docs

Endpoints are versioned under /v1/ so schema changes don't break integrations.
"""

from __future__ import annotations

import base64
import hashlib
import json
import uuid
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasicCredentials

from src.api.auth import require_auth, security
from src.api.schemas import (
    ApplyWithUploads,
    ChatRequest,
    DecisionResponse,
    StatusResponse,
)
from src.graph.workflow import get_workflow
from src.storage.mongo import MongoStore
from src.storage.postgres import PostgresClient

app = FastAPI(
    title="Social Support Workflow Automation",
    version="1.0.0",
    description="AI workflow automating social-support application decisions for a government social security department.",
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
async def health():
    return {"status": "ok"}


def _request_fingerprint(req: ApplyWithUploads) -> str:
    """Stable hash of the submission payload, used to detect idempotency-key reuse."""
    digest_input = {
        "applicant_name": req.applicant_name,
        "emirates_id": req.emirates_id,
        "application_form": req.application_form,
        "documents": [
            [d.doc_type, d.filename, hashlib.sha256((d.content_b64 or d.text or "").encode()).hexdigest()] for d in req.documents
        ],
    }
    return hashlib.sha256(json.dumps(digest_input, sort_keys=True, default=str).encode()).hexdigest()


@app.post("/v1/apply", response_model=dict)
async def apply(req: ApplyWithUploads, credentials: HTTPBasicCredentials = Depends(security)):
    """Submit an application with documents and run the agentic workflow.

    If the idempotency_key was seen before with the same payload, returns the
    existing application_id instead of creating a duplicate. Reusing a key with
    a DIFFERENT payload is rejected — that's a client error, not a retry.
    """
    require_auth(credentials)
    pg = PostgresClient()

    request_hash = _request_fingerprint(req)
    if req.idempotency_key:
        existing = pg.check_idempotency(req.idempotency_key)
        if existing:
            if existing.get("request_hash") in (None, request_hash):
                pg.close()
                return {
                    "application_id": existing["application_id"],
                    "message": "Idempotent replay — existing application returned.",
                }
            pg.close()
            raise HTTPException(
                status_code=422,
                detail=(
                    "This idempotency key was already used for a different application. "
                    "Clear the key or choose a new one to submit new data."
                ),
            )

    app_id = f"APP-{uuid.uuid4().hex[:8].upper()}"

    # Build raw_uploads dict from the request documents
    raw_uploads: dict[str, Any] = {"application_form": {"json": req.application_form}}
    for doc in req.documents:
        content = None
        if doc.content_b64:
            content = base64.b64decode(doc.content_b64)
        raw_uploads[doc.doc_type] = {
            "content": content,
            "text": doc.text,
            "filename": doc.filename,
        }

    # Persist application
    pg.create_application(
        app_id=app_id,
        applicant_name=req.applicant_name,
        emirates_id=req.emirates_id,
        raw_form=req.application_form,
        idempotency_key=req.idempotency_key,
    )
    if req.idempotency_key:
        pg.record_idempotency(req.idempotency_key, app_id, request_hash)

    pg.audit(app_id, "application_submitted", {"doc_count": len(req.documents)})

    # Run the LangGraph workflow
    initial_state = {
        "application_id": app_id,
        "raw_uploads": raw_uploads,
        "chat_history": [],
    }

    try:
        workflow = get_workflow()
        final_state = workflow.invoke(initial_state)

        # Persist decision
        decision = final_state.get("decision", {})
        decision["application_id"] = app_id
        pg.save_decision(decision)
        pg.update_status(app_id, decision.get("recommendation", "processed"))
        pg.audit(app_id, "decision_made", {"recommendation": decision.get("recommendation")})

        # Save extracted data to Mongo (PII-masked)
        try:
            from src.governance.pii import mask_for_storage

            mongo = MongoStore()
            mongo.save_extracted(app_id, "all", mask_for_storage(final_state.get("extracted_data", {})))
            mongo.close()
        except Exception:
            pass

        return {
            "application_id": app_id,
            "recommendation": decision.get("recommendation"),
            "confidence": decision.get("confidence"),
            "enablement": decision.get("enablement", []),
        }
    except Exception as e:
        pg.update_status(app_id, "error")
        pg.audit(app_id, "workflow_error", {"error": str(e)})
        raise HTTPException(status_code=500, detail=f"Workflow error: {e}")
    finally:
        pg.close()


@app.post("/v1/chat", response_model=dict)
async def chat(req: ChatRequest, credentials: HTTPBasicCredentials = Depends(security)):
    """Interactive chat with the chat agent (enablement recommendations)."""
    require_auth(credentials)
    from src.agents.chat_agent import chat_node

    # Load the application's features from the decision
    pg = PostgresClient()
    decision = pg.get_decision(req.application_id)
    pg.close()

    if not decision:
        raise HTTPException(status_code=404, detail="Application not found or no decision yet.")

    features = decision.get("features", {}) if isinstance(decision.get("features"), dict) else {}
    enablement = decision.get("enablement", []) if isinstance(decision.get("enablement"), list) else []

    state = {
        "application_id": req.application_id,
        "features": features,
        "enablement_recs": enablement,
        "decision_record": {
            "recommendation": decision.get("recommendation"),
            "confidence": decision.get("confidence"),
            "rationale": decision.get("rationale"),
            "validation_flags": decision.get("validation_flags") or [],
            "shap_top_features": (decision.get("shap_values") or [])[:5],
        },
        "chat_history": [{"role": "user", "content": req.message}],
    }

    try:
        result = chat_node(state)
        response_text = result["chat_history"][-1]["content"]
        return {"application_id": req.application_id, "response": response_text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat error: {e}")


@app.get("/v1/status/{app_id}", response_model=StatusResponse)
async def get_status(app_id: str, credentials: HTTPBasicCredentials = Depends(security)):
    """Get the status of an application."""
    require_auth(credentials)
    pg = PostgresClient()
    app = pg.get_application(app_id)
    if not app:
        pg.close()
        raise HTTPException(status_code=404, detail="Application not found.")
    decision = pg.get_decision(app_id)
    pg.close()
    return StatusResponse(
        application_id=app_id,
        status=app["status"],
        decision=dict(decision) if decision else None,
    )


@app.get("/v1/decision/{app_id}", response_model=DecisionResponse)
async def get_decision(app_id: str, credentials: HTTPBasicCredentials = Depends(security)):
    """Get the full decision with SHAP explainability."""
    require_auth(credentials)
    pg = PostgresClient()
    decision = pg.get_decision(app_id)
    pg.close()
    if not decision:
        raise HTTPException(status_code=404, detail="Decision not found.")
    return DecisionResponse(
        application_id=app_id,
        recommendation=decision["recommendation"],
        confidence=decision["confidence"],
        rationale=decision.get("rationale", ""),
        enablement=decision.get("enablement", []),
        features=decision.get("features", {}),
        shap_values=decision.get("shap_values", []),
        feature_importances=decision.get("feature_importances", []) if decision.get("feature_importances") else [],
        validation_flags=decision.get("validation_flags") or [],
    )


@app.get("/v1/applications", response_model=list)
async def list_applications(credentials: HTTPBasicCredentials = Depends(security)):
    """List recent applications (for the UI dashboard)."""
    require_auth(credentials)
    pg = PostgresClient()
    apps = pg.list_applications(limit=50)
    pg.close()
    return apps


@app.get("/v1/applications/stats", response_model=dict)
async def application_stats(credentials: HTTPBasicCredentials = Depends(security)):
    """Application counts by status across the whole database (dashboard metrics)."""
    require_auth(credentials)
    pg = PostgresClient()
    counts = pg.status_counts()
    pg.close()
    return {"total": sum(counts.values()), "by_status": counts}


@app.get("/v1/applications/{app_id}/audit", response_model=list)
async def application_audit(app_id: str, credentials: HTTPBasicCredentials = Depends(security)):
    """Audit-trail entries for an application (admin diagnostics)."""
    require_auth(credentials)
    pg = PostgresClient()
    entries = pg.get_audit(app_id)
    pg.close()
    return entries


@app.get("/v1/admin/metrics", response_model=dict)
async def admin_metrics(credentials: HTTPBasicCredentials = Depends(security)):
    """Model and evaluation artifacts for the admin view."""
    require_auth(credentials)
    from pathlib import Path

    out: dict[str, Any] = {}
    for key, path in (("cv_metrics", "docs/cv_metrics.json"), ("bias_report", "docs/bias_report.json")):
        try:
            out[key] = json.loads(Path(path).read_text())
        except Exception:
            out[key] = None
    try:
        out["evaluation_report_md"] = Path("docs/evaluation_report.md").read_text()
    except Exception:
        out["evaluation_report_md"] = None
    return out


@app.get("/v1/registry", response_model=list)
async def registry_list(credentials: HTTPBasicCredentials = Depends(security)):
    """List citizens in the government registry (UI integration browser)."""
    require_auth(credentials)
    pg = PostgresClient()
    citizens = pg.list_citizens()
    pg.close()
    return citizens


@app.get("/v1/registry/{query}", response_model=dict)
async def registry_profile(query: str, credentials: HTTPBasicCredentials = Depends(security)):
    """Fetch a citizen's registry profile by Emirates ID (or full name).

    Powers the UI's "Get User Details" integration: returns the fields needed
    to prefill the application form.
    """
    require_auth(credentials)
    pg = PostgresClient()
    row = pg.get_citizen(query)
    pg.close()
    if not row:
        raise HTTPException(status_code=404, detail="No citizen found in the registry for that ID or name.")
    return {
        "applicant_name": row["full_name"],
        "emirates_id": row["emirates_id"],
        "gender": row["gender"],
        "dob": str(row["dob"]),
        "address": row["address"],
        "employment_status": row["employment_status"],
        "education_level": row["education_level"],
        "years_experience": row["years_experience"],
        "employer": row["employer"],
        "family_members": row["family_members"],
    }


@app.get("/v1/registry/{query}/documents", response_model=list)
async def registry_documents(query: str, credentials: HTTPBasicCredentials = Depends(security)):
    """Fetch a citizen's documents from the registry document store.

    Powers the UI's "Get User Documents" integration: returns all five
    documents (base64) ready to attach to an application.
    """
    require_auth(credentials)
    pg = PostgresClient()
    row = pg.get_citizen(query)
    pg.close()
    if not row:
        raise HTTPException(status_code=404, detail="No citizen found in the registry for that ID or name.")

    mongo = MongoStore()
    docs = mongo.get_registry_documents(row["emirates_id"])
    mongo.close()
    return [
        {
            "doc_type": d["doc_type"],
            "filename": d["filename"],
            "content_b64": base64.b64encode(bytes(d["content"])).decode(),
        }
        for d in docs
    ]
