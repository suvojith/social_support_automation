"""Seeder — one-shot init container.

Runs in order:
  1. Generate synthetic applicants (rubric labels + ~12% noise + DOB conflicts).
  2. Seed PostgreSQL (applications table).
  3. Seed MongoDB (raw docs + extracted data).
  4. Seed Qdrant (eligibility rules + enablement programs KB).
  5. Seed Neo4j (family/employment graph, family members as individual nodes).
  6. Train + save the classifier (GradientBoosting + logreg baseline + k-fold CV).
  7. Run the demographic-parity bias check, save report to docs/.
  8. Save CV metrics to docs/cv_metrics.json.
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

import numpy as np

# Ensure src is importable when running as a module
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config.settings import get_settings
from src.data.programs import ELIGIBILITY_RULES, ENABLEMENT_PROGRAMS
from src.data.synthetic import generate_applicants
from src.governance.bias import demographic_parity_check, save_bias_report
from src.models.classifier import train_and_save
from src.storage.mongo import MongoStore
from src.storage.neo4j import Neo4jStore
from src.storage.postgres import PostgresClient
from src.storage.qdrant import QdrantStore


def seed_qdrant_kb(qdrant: QdrantStore):
    """Seed eligibility rules + enablement programs into Qdrant via embeddings."""
    from src.data.embeddings import embed_batch

    print("[seeder] Embedding + upserting eligibility rules...")
    rule_texts = [r["text"] for r in ELIGIBILITY_RULES]
    rule_embs = embed_batch(rule_texts)
    qdrant.upsert_rules(ELIGIBILITY_RULES, rule_embs)

    print("[seeder] Embedding + upserting enablement programs...")
    prog_texts = [f"{p['title']}: {p['description']}" for p in ENABLEMENT_PROGRAMS]
    prog_embs = embed_batch(prog_texts)
    qdrant.upsert_programs(ENABLEMENT_PROGRAMS, prog_embs)
    print(f"[seeder] Qdrant KB seeded: {len(ELIGIBILITY_RULES)} rules, {len(ENABLEMENT_PROGRAMS)} programs")


def seed_neo4j_graph(neo4j: Neo4jStore, applicants):
    """Seed the family/employment graph — family members as individual Person nodes."""
    print("[seeder] Seeding Neo4j graph...")
    neo4j.clear_all()
    neo4j.init_constraints()
    for a in applicants:
        neo4j.upsert_applicant(a.application_id, a.applicant_name, a.emirates_id)
        for m in a.family_members:
            neo4j.upsert_family_member(
                application_id=a.application_id,
                member_id=m.member_id,
                name=m.name,
                dob=m.dob,
                relation=m.relation,
                source_doc=m.source_doc,
            )
    print(f"[seeder] Neo4j: {len(applicants)} applicants, family-member nodes created")


def seed_postgres(pg: PostgresClient, applicants):
    """Seed applications as decided historical cases: status + a decision record each."""
    from src.data.rubric import enablement_recommendation, explain_decision
    from src.models.classifier import predict

    print("[seeder] Seeding PostgreSQL (applications + historical decisions)...")
    pg.init_schema()
    for a in applicants:
        try:
            pg.create_application(
                app_id=a.application_id,
                applicant_name=a.applicant_name,
                emirates_id=a.emirates_id,
                raw_form=a.documents["application_form"]["json"],
            )
        except Exception:
            pg.conn.rollback()  # row exists from a previous run; refresh status/decision below

        status = "approve" if a.label == 1 else "soft_decline"
        pg.update_status(a.application_id, status)

        try:
            pred = predict(a.features)
        except Exception:
            pred = {"prediction": status, "probability": 0.9, "shap_top_features": [], "feature_importances": []}
        enablement = enablement_recommendation(a.employment_status, a.income_band_val, a.has_qualification)
        pg.save_decision(
            {
                "application_id": a.application_id,
                "recommendation": status,
                "confidence": pred.get("probability", 0.9),
                "rationale": explain_decision(status, a.features, enablement),
                "enablement": enablement,
                "features": a.features,
                "shap_values": pred.get("shap_top_features", []),
                "classifier_pred": pred.get("prediction"),
                "classifier_prob": pred.get("probability"),
                "validation_flags": [],
            },
            replace=True,
        )
    print(f"[seeder] PostgreSQL: {len(applicants)} applications with decisions")


def seed_mongo(mongo: MongoStore, applicants):
    print("[seeder] Seeding MongoDB (raw docs + extracted)...")
    for a in applicants:
        # Idempotent re-runs: replace this application's documents, don't stack them
        mongo.raw_docs.delete_many({"application_id": a.application_id})
        mongo.extracted.delete_many({"application_id": a.application_id})
        docs = a.documents
        mongo.save_raw_document(
            a.application_id,
            "application_form",
            content_bytes=json.dumps(docs["application_form"]["json"]).encode(),
            metadata={"source": "form"},
        )
        mongo.save_raw_document(
            a.application_id,
            "bank_statement",
            content_bytes=docs["bank_statement"]["text"].encode(),
            metadata={"source": "bank"},
        )
        mongo.save_raw_document(
            a.application_id,
            "credit_report",
            content_bytes=docs["credit_report"]["text"].encode(),
            metadata={"source": "credit_bureau"},
        )
        mongo.save_raw_document(
            a.application_id,
            "emirates_id",
            content_bytes=docs["emirates_id"]["image"],
            metadata={"source": "id_card", "filename": f"{a.application_id}_eid.png"},
        )
        mongo.save_raw_document(a.application_id, "resume", content_bytes=docs["resume"]["text"].encode(), metadata={"source": "applicant"})
        mongo.save_raw_document(
            a.application_id,
            "assets_liabilities",
            content_bytes=docs["assets_liabilities"]["excel"],
            metadata={"source": "applicant", "filename": f"{a.application_id}_assets.xlsx"},
        )
        # Save extracted data (features) — PII-masked for storage
        from src.governance.pii import mask_for_storage

        mongo.save_extracted(a.application_id, "features", mask_for_storage(a.features))
    print(f"[seeder] MongoDB: {len(applicants)} applicants × 6 docs")


def main():
    settings = get_settings()
    print("=" * 60)
    print("  SSWA Seeder — synthetic data, KB, graph, classifier, bias check")
    print("=" * 60)

    # 1. Generate synthetic applicants
    print(f"\n[seeder] Generating {settings.n_synthetic_applicants} synthetic applicants...")
    applicants = generate_applicants(
        n=settings.n_synthetic_applicants,
        label_noise_rate=settings.label_noise_rate,
        seed=settings.random_seed,
    )
    approve_count = sum(1 for a in applicants if a.label == 1)
    conflict_count = sum(1 for a in applicants if a.has_dob_conflict)
    print(
        f"[seeder] Generated: {approve_count} eligible, {len(applicants) - approve_count} soft-decline, {conflict_count} with DOB conflicts"
    )

    # 2. Train classifier first — the PG seeding stamps each historical
    #    application with the model's confidence + SHAP explanation.
    print("\n[seeder] Training classifier...")
    X = np.array(
        [
            [
                a.features[c] if isinstance(a.features[c], (int, float)) else hash(a.features[c]) % 100
                for c in [
                    "income_from_bank",
                    "income_from_credit_report",
                    "income_consistent",
                    "income_used",
                    "per_capita_income",
                    "family_size",
                    "net_worth",
                    "address_match",
                ]
            ]
            for a in applicants
        ],
        dtype=float,
    )
    # Encode categoricals
    emp_map = {"Unemployed": 0, "Underemployed": 1, "Employed": 2}
    age_map = {"<25": 0, "25-40": 1, "40-55": 2, ">55": 3}
    emp_enc = np.array([[emp_map[a.features["employment_score"]]] for a in applicants])
    age_enc = np.array([[age_map[a.features["age_band"]]] for a in applicants])
    X = np.hstack([X, emp_enc, age_enc])
    y = np.array([a.label for a in applicants])

    genders = np.array([a.gender for a in applicants])
    ages = np.array([a.age_band for a in applicants])
    fam_sizes = np.array([a.features["family_size"] for a in applicants])

    model_artifact = train_and_save(
        X,
        y,
        feature_names=[
            "income_from_bank",
            "income_from_credit_report",
            "income_consistent",
            "income_used",
            "per_capita_income",
            "family_size",
            "net_worth",
            "address_match",
            "employment_score_enc",
            "age_band_enc",
        ],
    )

    # 3. Seed PostgreSQL (applications + decisions, using the trained model)
    pg = PostgresClient()
    seed_postgres(pg, applicants)

    # 4. Seed MongoDB
    mongo = MongoStore()
    seed_mongo(mongo, applicants)

    # 4b. Seed the citizen registry (profiles + per-citizen document sets)
    from seeder.registry import seed_registry

    seed_registry(pg=pg, mongo=mongo)

    # 5. Seed Qdrant KB
    try:
        qdrant = QdrantStore()
        seed_qdrant_kb(qdrant)
        qdrant.close()
    except Exception as e:
        print(f"[seeder] WARN: Qdrant seeding skipped ({e})")

    # 6. Seed Neo4j graph
    try:
        neo4j = Neo4jStore()
        seed_neo4j_graph(neo4j, applicants)
        neo4j.close()
    except Exception as e:
        print(f"[seeder] WARN: Neo4j seeding skipped ({e})")

    # 7. Bias check (demographic parity) — predict on scaled features, same as inference
    print("\n[seeder] Running demographic-parity bias check...")
    y_pred = model_artifact["model"].predict(model_artifact["scaler"].transform(X))
    groups = {
        "Male": genders == "M",
        "Female": genders == "F",
        "Age <25": ages == "<25",
        "Age 25-40": ages == "25-40",
        "Age 40-55": ages == "40-55",
        "Age >55": ages == ">55",
        "Family <=3": fam_sizes <= 3,
        "Family >3": fam_sizes > 3,
    }
    bias_report = demographic_parity_check(y, y_pred, groups)
    save_bias_report(bias_report)
    print(f"[seeder] Bias report saved: max disparity = {bias_report['max_disparity']}")

    # 8. Save CV metrics
    cv_metrics = model_artifact.get("cv_metrics", {})
    Path("docs").mkdir(exist_ok=True)
    with open("docs/cv_metrics.json", "w") as f:
        json.dump(cv_metrics, f, indent=2)
    print(f"[seeder] CV metrics saved: {json.dumps(cv_metrics)}")

    # Cleanup
    pg.close()
    mongo.close()

    print("\n" + "=" * 60)
    print("  Seeding complete. Ready for the application workflow.")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        traceback.print_exc()
        print(f"[seeder] FATAL: {e}", file=sys.stderr)
        sys.exit(1)
