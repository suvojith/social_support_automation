"""Evaluation harness — measures every stage of the pipeline and tabulates the results.

Sections:
  1. Classifier: k-fold CV metrics (F1, accuracy, precision, recall, ROC-AUC) vs baseline.
  2. Document extraction accuracy: every parsed field vs registry ground truth (15 citizens).
  3. End-to-end routing correctness: predicted outcome vs expected outcome per citizen.
  4. RAG retrieval precision@3: retrieved program types vs the intent of the query.
  5. LLM-as-judge, chat agent: groundedness / persona / completeness scored 1-5.
  6. LLM-as-judge, decision rationales: consistency with the decision record scored 1-5.
  7. Fairness: demographic-parity slices.

Usage (inside the stack): docker compose exec api python -m tests.evals
Writes docs/evaluation_report.md and prints a summary.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agents.eligibility_agent import _build_features
from src.agents.llm import chat_json
from src.data.registry import CITIZENS, build_documents, get_profile_payload
from src.data.rubric import income_band, is_borderline, wealth_band
from src.extraction import extract_document

API_BASE = "http://localhost:8000"
AUTH = ("reviewer", "change_me_in_prod")

EXPECTED_OUTCOME = {
    "784-1988-6612345-1": "approve",  # Ahmed Al Mansoori
    "784-1992-7723456-2": "approve",  # Fatima Al Zaabi
    "784-1990-8834567-3": "approve",  # Hassan Al Blooshi
    "784-1979-9945678-4": "approve",  # Noora Al Suwaidi
    "784-1985-1156789-5": "approve",  # Khalid Al Marri
    "784-1994-2267890-6": "approve",  # Mariam Al Hashimi
    "784-1993-1145678-5": "approve",  # Hamda Al Rashid (address mismatch, still approve)
    "784-1975-3378901-7": "soft_decline",  # Sultan Al Nahyan
    "784-1983-4489012-8": "soft_decline",  # Reem Al Falasi
    "784-1980-5590123-9": "soft_decline",  # Omar Al Dhaheri
    "784-1978-2256789-6": "soft_decline",  # Yousif Al Mazrouei
    "784-1996-6601234-1": "human_review",  # Aisha Al Ketbi (borderline income)
    "784-1982-7712345-2": "human_review",  # Saeed Al Shehhi (borderline income)
    "784-1991-8823456-3": "human_review",  # Layla Al Otaibi (income disagreement)
    "784-1987-9934567-4": "human_review",  # Rashid Al Tunaiji (family DOB conflict)
}

RAG_QUERIES = [
    ("training programs for unemployed people without qualifications", "upskilling"),
    ("open job roles for candidates with diplomas or degrees", "job_matching"),
    ("career growth counseling for employed applicants", "career_counseling"),
]

CHAT_QUESTIONS = [
    "Why was this decision made?",
    "What verification was done for this application?",
]

JUDGE_SYSTEM = """You are a strict evaluation judge for a government case-review assistant.
You are given the decision record of an application, a department employee's question, and the
assistant's answer. Score the answer on three criteria, each an integer from 1 (bad) to 5 (excellent):
- groundedness: every claim is supported by the decision record; nothing is invented.
- persona: the answer addresses a department EMPLOYEE in the third person about the applicant;
  it never addresses the applicant directly and never invites anyone to apply.
- completeness: the employee's question is actually answered.
Return ONLY JSON: {"groundedness": int, "persona": int, "completeness": int, "note": str}."""

JUDGE_USER_TEMPLATE = """Decision record (JSON):
{record}

Employee question: {question}

Assistant answer:
{answer}

Score it."""

RATIONALE_JUDGE_SYSTEM = """You are a strict evaluation judge. You are given an application's decision
record (recommendation, eligibility features, validation flags) and the rationale text stored with it.
Score how consistent the rationale is with the record, 1 (contradicts it) to 5 (fully consistent).
Return ONLY JSON: {"consistency": int, "note": str}."""


def _extract_all(citizen: dict) -> dict:
    """Run the real extractors over a citizen's generated documents."""
    extracted = {"application_form": {"parsed": get_profile_payload(citizen), "raw": "form"}}
    for doc in build_documents(citizen):
        extracted[doc["doc_type"]] = extract_document(doc["doc_type"], content=doc["content"], filename=doc["filename"])
    return extracted


def eval_extraction(results: dict) -> list[str]:
    checks = {
        "income_from_bank (bank statement PDF)": 0,
        "income_from_credit_report (credit report PDF)": 0,
        "net_worth (assets/liabilities Excel)": 0,
        "years_experience (resume PDF)": 0,
        "education_level (resume PDF)": 0,
        "family_members (credit report PDF)": 0,
        "emirates_id (ID card OCR)": 0,
        "date_of_birth (ID card OCR)": 0,
        "name (ID card OCR, fuzzy >= 0.85)": 0,
    }
    n = len(CITIZENS)
    for citizen in CITIZENS:
        ex = results[citizen["emirates_id"]]
        bank = ex["bank_statement"]["parsed"]
        credit = ex["credit_report"]["parsed"]
        excel = ex["assets_liabilities"]["parsed"]
        resume = ex["resume"]["parsed"]
        card = ex["emirates_id"]["parsed"]

        net_truth = sum(citizen["assets"].values()) - sum(citizen["liabilities"].values())
        checks["income_from_bank (bank statement PDF)"] += bank.get("income_from_bank") == citizen["income_bank"]
        checks["income_from_credit_report (credit report PDF)"] += credit.get("income_from_credit_report") == citizen["income_credit"]
        checks["net_worth (assets/liabilities Excel)"] += excel.get("net_worth") == net_truth
        checks["years_experience (resume PDF)"] += resume.get("years_experience") == citizen["years_experience"]
        checks["education_level (resume PDF)"] += (resume.get("education_level") or "").lower() == citizen["education_level"].lower()
        checks["family_members (credit report PDF)"] += len(credit.get("family_members") or []) == len(citizen["family"])
        checks["emirates_id (ID card OCR)"] += card.get("emirates_id") == citizen["emirates_id"]
        checks["date_of_birth (ID card OCR)"] += card.get("date_of_birth") == citizen["dob"]
        name_ratio = SequenceMatcher(None, (card.get("name") or "").lower(), citizen["name"].lower()).ratio()
        checks["name (ID card OCR, fuzzy >= 0.85)"] += name_ratio >= 0.85

    lines = ["| Field (source document) | Correct | Accuracy |", "|---|---|---|"]
    for field, correct in checks.items():
        lines.append(f"| {field} | {correct}/{n} | {correct / n:.0%} |")
    return lines


def _predict_outcome(citizen: dict, extracted: dict) -> str:
    """Deterministic pipeline outcome: rubric signal + unresolvable-conflict routing."""
    features = _build_features(extracted)
    borderline = is_borderline(features["per_capita_income"], features["income_from_bank"], features["income_from_credit_report"])

    form_members = {m["name"]: m["dob"] for m in citizen["family"]}
    credit_members = {m["name"]: m["dob"] for m in extracted["credit_report"]["parsed"].get("family_members", [])}
    dob_conflict = any(form_members.get(name) not in (None, dob) for name, dob in credit_members.items())

    if borderline or not features["income_consistent"] or dob_conflict:
        return "human_review"
    ib = income_band(features["per_capita_income"])
    wb = wealth_band(features["net_worth"])
    return "approve" if ib in ("Low", "Medium") and wb in ("Negative/Low", "Medium") else "soft_decline"


def eval_routing(results: dict) -> list[str]:
    lines = ["| Citizen | Expected | Predicted | Match |", "|---|---|---|---|"]
    correct = 0
    for citizen in CITIZENS:
        expected = EXPECTED_OUTCOME[citizen["emirates_id"]]
        predicted = _predict_outcome(citizen, results[citizen["emirates_id"]])
        match = predicted == expected
        correct += match
        lines.append(f"| {citizen['name']} | {expected} | {predicted} | {'✅' if match else '❌'} |")
    lines.append(f"| **Accuracy** | | | **{correct}/{len(CITIZENS)} ({correct / len(CITIZENS):.0%})** |")
    return lines


def eval_classifier() -> list[str]:
    metrics = json.loads(Path("docs/cv_metrics.json").read_text())
    lines = ["| Metric (5-fold CV) | GradientBoosting | LogisticRegression baseline |", "|---|---|---|"]
    for metric in ("f1", "accuracy", "precision", "recall", "roc_auc"):
        gb = metrics.get(f"gradient_boosting_{metric}_mean")
        lr = metrics.get(f"logistic_regression_{metric}_mean")
        gb_std = metrics.get(f"gradient_boosting_{metric}_std")
        if gb is None:
            continue
        lines.append(f"| {metric.upper()} | {gb:.3f} ± {gb_std:.3f} | {lr:.3f} |")
    lines.append(
        f"\nTrained on {metrics['n_samples']} labeled applicants, {metrics['n_features']} features, "
        f"{metrics['label_noise_rate']:.0%} label noise."
    )
    return lines


def eval_rag() -> list[str]:
    from src.data.embeddings import embed
    from src.data.programs import ENABLEMENT_PROGRAMS
    from src.storage.qdrant import QdrantStore

    available = {}
    for program in ENABLEMENT_PROGRAMS:
        available[program["type"]] = available.get(program["type"], 0) + 1

    store = QdrantStore()
    lines = ["| Query intent | Expected type | Retrieved in top-3 | Recall |", "|---|---|---|---|"]
    for query, expected_type in RAG_QUERIES:
        hits = store.search_programs(embed(query), limit=3)
        relevant = sum(1 for h in hits if h.get("type") == expected_type)
        expected_n = min(3, available.get(expected_type, 0))
        lines.append(f"| {query} | {expected_type} | {relevant}/{expected_n} | {relevant / max(expected_n, 1):.0%} |")
    store.close()
    return lines


def _latest_decided_applications(names: list[str]) -> list[dict]:
    from src.storage.postgres import PostgresClient

    pg = PostgresClient()
    picked = []
    with pg.conn.cursor() as cur:
        for name in names:
            cur.execute(
                """SELECT d.application_id, d.recommendation, d.confidence, d.rationale,
                          d.validation_flags, d.features, d.shap_values
                   FROM decisions d JOIN applications a ON a.id = d.application_id
                   WHERE a.applicant_name = %s AND a.id LIKE 'APP-%%' AND LENGTH(a.id) = 12
                   ORDER BY d.created_at DESC LIMIT 1""",
                (name,),
            )
            row = cur.fetchone()
            if row:
                picked.append(
                    {
                        "application_id": row[0],
                        "recommendation": row[1],
                        "confidence": row[2],
                        "rationale": row[3],
                        "validation_flags": row[4] or [],
                        "features": row[5] or {},
                        "shap_top_features": (row[6] or [])[:5],
                    }
                )
    pg.close()
    return picked


def eval_chat_judge(records: list[dict]) -> list[str]:
    lines = [
        "| Application | Question | Groundedness | Persona | Completeness |",
        "|---|---|---|---|---|",
    ]
    totals = {"groundedness": [], "persona": [], "completeness": []}
    for record in records:
        for question in CHAT_QUESTIONS:
            resp = httpx.post(
                f"{API_BASE}/v1/chat",
                json={"application_id": record["application_id"], "message": question},
                auth=AUTH,
                timeout=180,
            ).json()
            answer = resp.get("response", "")
            verdict = (
                chat_json(
                    system=JUDGE_SYSTEM,
                    user=JUDGE_USER_TEMPLATE.format(record=json.dumps(record, default=str), question=question, answer=answer),
                )
                or {}
            )
            g, p, c = (verdict.get(k, 0) for k in ("groundedness", "persona", "completeness"))
            for key, val in zip(totals, (g, p, c)):
                totals[key].append(val)
            lines.append(f"| {record['application_id']} ({record['recommendation']}) | {question} | {g}/5 | {p}/5 | {c}/5 |")
    means = {k: sum(v) / max(len(v), 1) for k, v in totals.items()}
    lines.append(f"| **Mean** | | **{means['groundedness']:.1f}/5** | **{means['persona']:.1f}/5** | **{means['completeness']:.1f}/5** |")
    return lines


def eval_rationale_judge(records: list[dict]) -> list[str]:
    lines = ["| Application | Recommendation | Rationale consistency |", "|---|---|---|"]
    scores = []
    for record in records:
        verdict = (
            chat_json(
                system=RATIONALE_JUDGE_SYSTEM,
                user=f"Decision record (JSON):\n{json.dumps(record, default=str)}\n\nRationale:\n{record['rationale']}\n\nScore it.",
            )
            or {}
        )
        score = verdict.get("consistency", 0)
        scores.append(score)
        lines.append(f"| {record['application_id']} | {record['recommendation']} | {score}/5 |")
    lines.append(f"| **Mean** | | **{sum(scores) / max(len(scores), 1):.1f}/5** |")
    return lines


def eval_fairness() -> list[str]:
    report = json.loads(Path("docs/bias_report.json").read_text())
    lines = ["| Demographic slice | Approval rate | n |", "|---|---|---|"]
    for name, stats in report["slices"].items():
        lines.append(f"| {name} | {stats['approval_rate']:.1%} | {stats['count']} |")
    lines.append(f"| **Max disparity** | **{report['max_disparity']:.1%}** | |")
    return lines


def main() -> int:
    out: list[str] = [
        "# Evaluation Report",
        f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M')} · judge model: qwen3.5 (local) · ground truth: citizen registry\n",
    ]

    print("[evals] 1/7 classifier CV metrics...")
    out += ["## 1. Eligibility classifier — cross-validated metrics\n", *eval_classifier(), ""]

    print("[evals] 2/7 extraction accuracy (15 citizens, includes OCR)...")
    extracted = {c["emirates_id"]: _extract_all(c) for c in CITIZENS}
    out += ["## 2. Document extraction accuracy vs ground truth (15 citizens)\n", *eval_extraction(extracted), ""]

    print("[evals] 3/7 routing correctness...")
    out += ["## 3. End-to-end routing correctness (rubric + validation on extracted documents)\n", *eval_routing(extracted), ""]

    print("[evals] 4/7 RAG retrieval precision...")
    out += ["## 4. Enablement RAG retrieval — recall of available programs in top-3\n", *eval_rag(), ""]

    print("[evals] 5/7 chat agent, LLM-as-judge...")
    records = _latest_decided_applications(["Ahmed Al Mansoori", "Layla Al Otaibi", "Rashid Al Tunaiji"])
    out += ["## 5. Chat agent quality — LLM-as-judge (1-5)\n", *eval_chat_judge(records), ""]

    print("[evals] 6/7 decision rationales, LLM-as-judge...")
    out += ["## 6. Decision rationale consistency — LLM-as-judge (1-5)\n", *eval_rationale_judge(records), ""]

    print("[evals] 7/7 fairness slices...")
    out += ["## 7. Fairness — demographic parity (synthetic set)\n", *eval_fairness(), ""]

    report = "\n".join(out)
    Path("docs/evaluation_report.md").write_text(report)
    print("\n" + report)
    print("\n[evals] Report written to docs/evaluation_report.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
