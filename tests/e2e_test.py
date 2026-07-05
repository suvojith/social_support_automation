"""End-to-end app test — exercises the running app with dummy documents.

Tests the full workflow: submit application → get decision → chat → status check.
Generates real dummy documents (bank statement, credit report, Emirates ID image,
resume, assets/liabilities Excel) and submits them through the API.

Usage: python tests/e2e_test.py
Run after `bash setup.sh` has started all services.
"""

from __future__ import annotations

import base64
import io
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
import pandas as pd
from PIL import Image, ImageDraw

API_BASE = os.environ.get("API_BASE", "http://localhost:8000")
AUTH = ("reviewer", os.environ.get("API_PASSWORD", "change_me_in_prod"))


def make_emirates_id_image(name: str, eid: str, dob: str) -> str:
    """Generate a mock Emirates ID card image, return base64."""
    img = Image.new("RGB", (600, 380), "white")
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, 600, 60], fill=(10, 60, 120))
    draw.text((20, 18), "UNITED ARAB EMIRATES", fill="white")
    draw.text((20, 80), f"Name: {name}", fill="black")
    draw.text((20, 120), f"Emirates ID: {eid}", fill="black")
    draw.text((20, 160), f"Date of Birth: {dob}", fill="black")
    draw.text((20, 200), "Nationality: UAE", fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def make_excel_b64(total_assets: float, total_liabilities: float) -> str:
    """Generate an assets/liabilities Excel file, return base64."""
    df = pd.DataFrame(
        {
            "Category": ["Cash", "Property", "Vehicle", "Loan", "Credit Card"],
            "Type": ["Asset", "Asset", "Asset", "Liability", "Liability"],
            "Amount_AED": [
                total_assets * 0.3,
                total_assets * 0.5,
                total_assets * 0.2,
                total_liabilities * 0.6,
                total_liabilities * 0.4,
            ],
        }
    )
    buf = io.BytesIO()
    df.to_excel(buf, index=False, sheet_name="Assets_Liabilities")
    return base64.b64encode(buf.getvalue()).decode()


# ---- Test cases ----
TEST_CASES = [
    {
        "name": "Case A — Clean Approve (low income, low wealth, unemployed)",
        "applicant": {
            "applicant_name": "Ahmed Al Mansoori",
            "emirates_id": "784-1990-1234567-1",
            "application_form": {
                "applicant_name": "Ahmed Al Mansoori",
                "emirates_id": "784-1990-1234567-1",
                "dob": "1990-01-15",
                "address": "Deira, Dubai",
                "employment_status": "Unemployed",
                "education_level": "Secondary",
                "years_experience": 0,
                "family_members": [
                    {"name": "Fatima Al Mansoori", "dob": "1992-03-20", "relation": "spouse"},
                    {"name": "Ali Al Mansoori", "dob": "2015-06-10", "relation": "son"},
                ],
            },
            "documents": [
                {
                    "doc_type": "bank_statement",
                    "filename": "bank_statement.txt",
                    "text": (
                        "BANK STATEMENT — Mashreq Bank\n"
                        "Account Holder: Ahmed Al Mansoori\n"
                        "Account Number: 0123456789012345\n"
                        "Period: Jan-Jun 2026\n"
                        "Average Monthly Balance: AED 4,500.00\n"
                        "Monthly Salary Deposits: AED 1,500.00\n"
                        "Address on file: Deira, Dubai"
                    ),
                },
                {
                    "doc_type": "credit_report",
                    "filename": "credit_report.txt",
                    "text": (
                        "CREDIT BUREAU REPORT — UAE Credit Bureau\n"
                        "Name: Ahmed Al Mansoori\n"
                        "Emirates ID: 784-1990-1234567-1\n"
                        "Reported Monthly Income: AED 1,550.00\n"
                        "Address on file: Deira, Dubai\n"
                        "Employment Status: Unemployed\n"
                        "Credit Score: 620"
                    ),
                },
                {
                    "doc_type": "emirates_id",
                    "filename": "emirates_id.png",
                    "content_b64": make_emirates_id_image("Ahmed Al Mansoori", "784-1990-1234567-1", "1990-01-15"),
                },
                {
                    "doc_type": "resume",
                    "filename": "resume.txt",
                    "text": (
                        "RESUME\n"
                        "Name: Ahmed Al Mansoori\n"
                        "Education: Secondary\n"
                        "Years of Experience: 0\n"
                        "Employment Status: Unemployed\n"
                        "Skills: Communication, Teamwork"
                    ),
                },
                {
                    "doc_type": "assets_liabilities",
                    "filename": "assets_liabilities.xlsx",
                    "content_b64": make_excel_b64(total_assets=25000, total_liabilities=15000),
                },
            ],
            "idempotency_key": f"e2e-test-case-A-{int(time.time())}",
        },
        "expected": "approve",
    },
    {
        "name": "Case B — Soft Decline (high income, high wealth, employed)",
        "applicant": {
            "applicant_name": "Sultan Al Nahyan",
            "emirates_id": "784-1985-9876543-2",
            "application_form": {
                "applicant_name": "Sultan Al Nahyan",
                "emirates_id": "784-1985-9876543-2",
                "dob": "1985-05-20",
                "address": "Jumeirah, Dubai",
                "employment_status": "Employed",
                "education_level": "Bachelor",
                "years_experience": 12,
                "family_members": [
                    {"name": "Aisha Al Nahyan", "dob": "1988-09-15", "relation": "spouse"},
                ],
            },
            "documents": [
                {
                    "doc_type": "bank_statement",
                    "filename": "bank_statement.txt",
                    "text": (
                        "BANK STATEMENT — Emirates NBD\n"
                        "Account Holder: Sultan Al Nahyan\n"
                        "Account Number: 9876543210987654\n"
                        "Period: Jan-Jun 2026\n"
                        "Average Monthly Balance: AED 45,000.00\n"
                        "Monthly Salary Deposits: AED 22,000.00\n"
                        "Address on file: Jumeirah, Dubai"
                    ),
                },
                {
                    "doc_type": "credit_report",
                    "filename": "credit_report.txt",
                    "text": (
                        "CREDIT BUREAU REPORT — UAE Credit Bureau\n"
                        "Name: Sultan Al Nahyan\n"
                        "Emirates ID: 784-1985-9876543-2\n"
                        "Reported Monthly Income: AED 22,500.00\n"
                        "Address on file: Jumeirah, Dubai\n"
                        "Employment Status: Employed\n"
                        "Credit Score: 780"
                    ),
                },
                {
                    "doc_type": "emirates_id",
                    "filename": "emirates_id.png",
                    "content_b64": make_emirates_id_image("Sultan Al Nahyan", "784-1985-9876543-2", "1985-05-20"),
                },
                {
                    "doc_type": "resume",
                    "filename": "resume.txt",
                    "text": (
                        "RESUME\n"
                        "Name: Sultan Al Nahyan\n"
                        "Education: Bachelor\n"
                        "Years of Experience: 12\n"
                        "Employment Status: Employed\n"
                        "Skills: Management, Finance, Leadership"
                    ),
                },
                {
                    "doc_type": "assets_liabilities",
                    "filename": "assets_liabilities.xlsx",
                    "content_b64": make_excel_b64(total_assets=450000, total_liabilities=80000),
                },
            ],
            "idempotency_key": f"e2e-test-case-B-{int(time.time())}",
        },
        "expected": "soft_decline",
    },
    {
        "name": "Case C — Human Review (borderline: income near cutoff + address mismatch)",
        "applicant": {
            "applicant_name": "Mariam Al Suwaidi",
            "emirates_id": "784-1995-4567890-3",
            "application_form": {
                "applicant_name": "Mariam Al Suwaidi",
                "emirates_id": "784-1995-4567890-3",
                "dob": "1995-11-30",
                "address": "Karama, Dubai",
                "employment_status": "Underemployed",
                "education_level": "Diploma",
                "years_experience": 3,
                "family_members": [
                    {"name": "Hassan Al Suwaidi", "dob": "2020-02-14", "relation": "son"},
                    {"name": "Noor Al Suwaidi", "dob": "2022-07-08", "relation": "daughter"},
                    {"name": "Khalid Al Suwaidi", "dob": "2019-12-01", "relation": "son"},
                ],
            },
            "documents": [
                {
                    "doc_type": "bank_statement",
                    "filename": "bank_statement.txt",
                    "text": (
                        "BANK STATEMENT — ADCB\n"
                        "Account Holder: Mariam Al Suwaidi\n"
                        "Account Number: 5678901234567890\n"
                        "Period: Jan-Jun 2026\n"
                        "Average Monthly Balance: AED 8,200.00\n"
                        "Monthly Salary Deposits: AED 2,900.00\n"
                        "Address on file: Karama, Dubai"
                    ),
                },
                {
                    "doc_type": "credit_report",
                    "filename": "credit_report.txt",
                    "text": (
                        "CREDIT BUREAU REPORT — UAE Credit Bureau\n"
                        "Name: Mariam Al Suwaidi\n"
                        "Emirates ID: 784-1995-4567890-3\n"
                        "Reported Monthly Income: AED 3,100.00\n"
                        "Address on file: Bur Dubai, Dubai\n"
                        "Employment Status: Underemployed\n"
                        "Credit Score: 650"
                    ),
                },
                {
                    "doc_type": "emirates_id",
                    "filename": "emirates_id.png",
                    "content_b64": make_emirates_id_image("Mariam Al Suwaidi", "784-1995-4567890-3", "1995-11-30"),
                },
                {
                    "doc_type": "resume",
                    "filename": "resume.txt",
                    "text": (
                        "RESUME\n"
                        "Name: Mariam Al Suwaidi\n"
                        "Education: Diploma\n"
                        "Years of Experience: 3\n"
                        "Employment Status: Underemployed\n"
                        "Skills: Data Entry, MS Office, Customer Service"
                    ),
                },
                {
                    "doc_type": "assets_liabilities",
                    "filename": "assets_liabilities.xlsx",
                    "content_b64": make_excel_b64(total_assets=35000, total_liabilities=20000),
                },
            ],
            "idempotency_key": f"e2e-test-case-C-{int(time.time())}",
        },
        "expected": "any",  # borderline — could be approve, soft_decline, or human_review
    },
]


def run_e2e_tests():
    """Run all E2E tests and produce a report."""
    report_lines: list[str] = []
    results: list[dict] = []

    def log(msg: str):
        print(msg)
        report_lines.append(msg)

    log("=" * 80)
    log("  E2E APP TEST REPORT — Social Support Workflow Automation")
    log(f"  Run at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"  API: {API_BASE}")
    log("=" * 80)
    log("")

    # ---- 1. Health checks ----
    log("─" * 80)
    log("  PHASE 1: Service Health Checks")
    log("─" * 80)

    health_checks = {
        "FastAPI": ("http://localhost:8000/health", "api"),
        "Streamlit UI": ("http://localhost:8501/_stcore/health", "ui"),
        "Langfuse": ("http://localhost:3000", "langfuse"),
    }

    for name, (url, _) in health_checks.items():
        try:
            resp = httpx.get(url, timeout=10.0)
            status = "PASS" if resp.status_code == 200 else f"FAIL ({resp.status_code})"
            log(f"  [{'✅' if status == 'PASS' else '❌'}] {name:20s} {url:45s} → {status}")
        except Exception as e:
            log(f"  [❌] {name:20s} {url:45s} → FAIL ({e})")

    log("")

    # ---- 2. Submit applications ----
    log("─" * 80)
    log("  PHASE 2: Application Submission (3 test cases)")
    log("─" * 80)

    for i, tc in enumerate(TEST_CASES):
        case_name = tc["name"]
        applicant = tc["applicant"]
        expected = tc["expected"]

        log(f"\n  [{i + 1}/3] {case_name}")
        log(f"       Applicant: {applicant['applicant_name']}")
        log(f"       Emirates ID: {applicant['emirates_id']}")
        log(f"       Documents: {len(applicant['documents'])} files ({', '.join(d['doc_type'] for d in applicant['documents'])})")
        log(f"       Expected: {expected}")

        start_time = time.time()
        try:
            resp = httpx.post(
                f"{API_BASE}/v1/apply",
                json=applicant,
                auth=AUTH,
                timeout=300.0,
            )
            elapsed = time.time() - start_time

            if resp.status_code == 200:
                data = resp.json()
                app_id = data.get("application_id", "N/A")
                recommendation = data.get("recommendation", "N/A")
                confidence = data.get("confidence", "N/A")
                enablement = data.get("enablement", [])

                log(f"       ✅ Submitted in {elapsed:.1f}s")
                log(f"       Application ID: {app_id}")
                log(f"       Recommendation: {recommendation}")
                log(f"       Confidence: {confidence}")
                log(f"       Enablement: {enablement if enablement else 'none'}")

                if expected == "any":
                    match = "N/A (any acceptable)"
                else:
                    match = "PASS" if recommendation == expected else "MISMATCH"
                log(f"       Expected match: {match}")

                results.append(
                    {
                        "case": case_name,
                        "status": "PASS",
                        "app_id": app_id,
                        "recommendation": recommendation,
                        "confidence": confidence,
                        "enablement": enablement,
                        "elapsed": elapsed,
                        "expected": expected,
                        "match": match,
                    }
                )
            else:
                log(f"       ❌ HTTP {resp.status_code}: {resp.text[:200]}")
                results.append({"case": case_name, "status": "FAIL", "error": resp.text[:200]})
        except Exception as e:
            elapsed = time.time() - start_time
            log(f"       ❌ Error after {elapsed:.1f}s: {e}")
            results.append({"case": case_name, "status": "FAIL", "error": str(e)})

    log("")

    # ---- 3. Idempotency test ----
    log("─" * 80)
    log("  PHASE 3: Idempotency Test (resubmit Case A with same key)")
    log("─" * 80)

    case_a = TEST_CASES[0]["applicant"]
    try:
        resp1 = httpx.post(f"{API_BASE}/v1/apply", json=case_a, auth=AUTH, timeout=300.0)
        resp2 = httpx.post(f"{API_BASE}/v1/apply", json=case_a, auth=AUTH, timeout=300.0)

        if resp1.status_code == 200 and resp2.status_code == 200:
            id1 = resp1.json().get("application_id")
            id2 = resp2.json().get("application_id")
            idem_pass = id1 == id2
            log(f"  [{'✅' if idem_pass else '❌'}] First submission ID:  {id1}")
            log(f"  [{'✅' if idem_pass else '❌'}] Retry submission ID:     {id2}")
            log(f"  [{'✅' if idem_pass else '❌'}] Idempotency: {'PASS — same ID returned' if idem_pass else 'FAIL — different IDs!'}")
        else:
            log(f"  [❌] HTTP error: {resp1.status_code} / {resp2.status_code}")
            idem_pass = False
    except Exception as e:
        log(f"  [❌] Error: {e}")
        idem_pass = False

    log("")

    # ---- 4. Status + Decision checks ----
    log("─" * 80)
    log("  PHASE 4: Status & Decision Retrieval")
    log("─" * 80)

    for r in results:
        if r.get("status") != "PASS":
            continue
        app_id = r["app_id"]
        case_name = r["case"]
        log(f"\n  {case_name}")
        log(f"       App ID: {app_id}")

        # Status
        try:
            resp = httpx.get(f"{API_BASE}/v1/status/{app_id}", auth=AUTH, timeout=10.0)
            if resp.status_code == 200:
                status_data = resp.json()
                log(f"       ✅ Status: {status_data.get('status', 'N/A')}")
            else:
                log(f"       ❌ Status check failed: HTTP {resp.status_code}")
        except Exception as e:
            log(f"       ❌ Status error: {e}")

        # Decision with SHAP
        try:
            resp = httpx.get(f"{API_BASE}/v1/decision/{app_id}", auth=AUTH, timeout=10.0)
            if resp.status_code == 200:
                decision = resp.json()
                log(f"       ✅ Decision: {decision.get('recommendation', 'N/A')}")
                log(f"          Confidence: {decision.get('confidence', 'N/A')}")
                log(f"          Rationale: {decision.get('rationale', 'N/A')[:120]}...")
                shap = decision.get("shap_values", [])
                if shap:
                    log("          SHAP top features:")
                    for s in shap[:3]:
                        log(f"            • {s.get('feature', '?')}: {s.get('shap_value', 0)}")
                else:
                    feat_imp = decision.get("feature_importances", [])
                    if feat_imp:
                        log("          Feature importances (SHAP not available):")
                        for f in feat_imp[:3]:
                            log(f"            • {f.get('feature', '?')}: {f.get('importance', 0)}")
                    else:
                        log("          ⚠️ No explainability data available")
            else:
                log(f"       ❌ Decision check failed: HTTP {resp.status_code}")
        except Exception as e:
            log(f"       ❌ Decision error: {e}")

    log("")

    # ---- 5. Chat test ----
    log("─" * 80)
    log("  PHASE 5: Chat Interaction (enablement recommendations)")
    log("─" * 80)

    for r in results[:2]:  # Test chat on first 2 cases
        if r.get("status") != "PASS":
            continue
        app_id = r["app_id"]
        case_name = r["case"]
        log(f"\n  {case_name}")
        log(f"       App ID: {app_id}")

        try:
            resp = httpx.post(
                f"{API_BASE}/v1/chat",
                json={"application_id": app_id, "message": "What training programs are available for me?"},
                auth=AUTH,
                timeout=120.0,
            )
            if resp.status_code == 200:
                chat_data = resp.json()
                response_text = chat_data.get("response", "")
                log(f"       ✅ Chat response received ({len(response_text)} chars)")
                log(f"          Response: {response_text[:200]}...")
            else:
                log(f"       ❌ Chat failed: HTTP {resp.status_code} — {resp.text[:100]}")
        except Exception as e:
            log(f"       ❌ Chat error: {e}")

    log("")

    # ---- 6. Applications list ----
    log("─" * 80)
    log("  PHASE 6: Applications List")
    log("─" * 80)

    try:
        resp = httpx.get(f"{API_BASE}/v1/applications", auth=AUTH, timeout=10.0)
        if resp.status_code == 200:
            apps = resp.json()
            log(f"  ✅ Retrieved {len(apps)} applications")
            # Show our test applications
            test_ids = {r["app_id"] for r in results if r.get("app_id")}
            found = [a for a in apps if a.get("id") in test_ids]
            log(f"  Test applications found: {len(found)}")
            for a in found:
                log(f"    • {a['id']}: {a['applicant_name']} — status: {a['status']}")
        else:
            log(f"  ❌ List failed: HTTP {resp.status_code}")
    except Exception as e:
        log(f"  ❌ List error: {e}")

    log("")

    # ---- Summary ----
    log("=" * 80)
    log("  SUMMARY")
    log("=" * 80)

    passed = sum(1 for r in results if r.get("status") == "PASS")
    failed = sum(1 for r in results if r.get("status") == "FAIL")
    log(f"  Applications submitted: {len(results)} ({passed} passed, {failed} failed)")
    log(f"  Idempotency test:       {'PASS' if idem_pass else 'FAIL'}")

    for r in results:
        if r.get("status") == "PASS":
            icon = "✅"
            rec = r["recommendation"]
            conf = r["confidence"]
            match = r.get("match", "N/A")
            log(f"  {icon} {r['case'][:50]:50s} → {rec:15s} (conf: {conf}, match: {match})")
        else:
            log(f"  ❌ {r['case'][:50]:50s} → FAILED: {r.get('error', 'unknown')[:60]}")

    log("")
    log("=" * 80)
    report = "\n".join(report_lines)
    print(report)

    Path("docs/e2e_test_report.txt").write_text(report)
    print("\nReport saved to docs/e2e_test_report.txt")

    return 0 if failed == 0 and idem_pass else 1


if __name__ == "__main__":
    sys.exit(run_e2e_tests())
