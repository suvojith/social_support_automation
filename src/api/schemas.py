"""API schemas — Pydantic models for request/response validation."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ApplyRequest(BaseModel):
    applicant_name: str
    emirates_id: str
    application_form: dict[str, Any]
    idempotency_key: str | None = None


class UploadDocument(BaseModel):
    doc_type: str = Field(..., description="application_form|bank_statement|credit_report|emirates_id|resume|assets_liabilities")
    filename: str | None = None
    content_b64: str | None = None
    text: str | None = None


class ApplyWithUploads(BaseModel):
    applicant_name: str
    emirates_id: str
    application_form: dict[str, Any]
    documents: list[UploadDocument] = []
    idempotency_key: str | None = None


class ChatRequest(BaseModel):
    application_id: str
    message: str


class DecisionResponse(BaseModel):
    application_id: str
    recommendation: str
    confidence: float
    rationale: str
    enablement: list[str]
    features: dict[str, Any]
    shap_values: list[dict[str, Any]]
    feature_importances: list[dict[str, Any]]
    validation_flags: list[dict[str, Any]] = []


class StatusResponse(BaseModel):
    application_id: str
    status: str
    decision: dict[str, Any] | None = None
