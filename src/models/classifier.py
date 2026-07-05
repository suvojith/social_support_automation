"""Eligibility classifier — GradientBoosting with a logistic-regression baseline.

GradientBoosting was chosen for interpretability (feature_importances_ + SHAP)
on tabular features; logistic regression is kept as a baseline in case boosting
doesn't clearly win on held-out data. k-fold CV metrics are reported for both.

Label noise (~12%) is injected at synthetic-generation time so CV metrics are
realistic rather than ~1.0.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_validate
from sklearn.preprocessing import StandardScaler

CV_SCORING = ("f1", "accuracy", "precision", "recall", "roc_auc")

MODELS_DIR = Path("models")
MODELS_DIR.mkdir(exist_ok=True)


def train_and_save(
    X: np.ndarray,
    y: np.ndarray,
    feature_names: list[str],
) -> dict[str, Any]:
    """Train GradientBoosting + logreg baseline, run k-fold CV, save artifacts + SHAP.

    Returns an artifact dict with the model, scaler, CV metrics, and feature names.
    """
    from joblib import dump

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Primary: GradientBoosting (interpretable via feature_importances_ + SHAP)
    gb = GradientBoostingClassifier(
        n_estimators=100,
        max_depth=3,
        learning_rate=0.1,
        random_state=42,
    )
    gb.fit(X_scaled, y)

    # Baseline: LogisticRegression
    lr = LogisticRegression(max_iter=1000, random_state=42)
    lr.fit(X_scaled, y)

    # k-fold cross-validation across multiple metrics, for both models
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    gb_cv = cross_validate(gb, X_scaled, y, cv=skf, scoring=CV_SCORING)
    lr_cv = cross_validate(lr, X_scaled, y, cv=skf, scoring=CV_SCORING)

    cv_metrics: dict[str, Any] = {
        "n_samples": int(len(y)),
        "n_features": int(X.shape[1]),
        "feature_names": feature_names,
        "label_noise_rate": float(os.environ.get("LABEL_NOISE_RATE", "0.12")),
    }
    for name, scores in (("gradient_boosting", gb_cv), ("logistic_regression", lr_cv)):
        for metric in CV_SCORING:
            values = scores[f"test_{metric}"]
            cv_metrics[f"{name}_{metric}_mean"] = round(float(values.mean()), 4)
            cv_metrics[f"{name}_{metric}_std"] = round(float(values.std()), 4)
    cv_metrics["gradient_boosting_f1_folds"] = [round(float(v), 4) for v in gb_cv["test_f1"]]
    cv_metrics["logistic_regression_f1_folds"] = [round(float(v), 4) for v in lr_cv["test_f1"]]

    # SHAP explainer
    try:
        import shap

        explainer = shap.TreeExplainer(gb)
        shap_sample = X_scaled[:50]
        shap_values = explainer.shap_values(shap_sample)
        cv_metrics["shap_available"] = True
    except Exception:
        shap_values = None
        cv_metrics["shap_available"] = False

    # Feature importances
    importances = gb.feature_importances_
    cv_metrics["feature_importances"] = {name: round(float(imp), 4) for name, imp in zip(feature_names, importances)}

    # Save artifacts
    artifact = {
        "model": gb,
        "baseline": lr,
        "scaler": scaler,
        "feature_names": feature_names,
        "cv_metrics": cv_metrics,
        "shap_values": shap_values,
    }
    dump(gb, MODELS_DIR / "gradient_boosting.joblib")
    dump(lr, MODELS_DIR / "logistic_regression.joblib")
    dump(scaler, MODELS_DIR / "scaler.joblib")
    dump(feature_names, MODELS_DIR / "feature_names.joblib")

    global _artifacts
    _artifacts = None  # invalidate the inference cache — fresh artifacts on disk

    print(f"[models] GradientBoosting F1: {cv_metrics['gradient_boosting_f1_mean']} ± {cv_metrics['gradient_boosting_f1_std']}")
    print(f"[models] LogisticRegression F1: {cv_metrics['logistic_regression_f1_mean']} ± {cv_metrics['logistic_regression_f1_std']}")
    top_features = sorted(cv_metrics["feature_importances"].items(), key=lambda x: -x[1])[:3]
    print(f"[models] Top features: {top_features}")

    return artifact


_artifacts: dict[str, Any] | None = None


def load_model() -> dict[str, Any]:
    """Load the saved classifier artifacts once and cache them for inference."""
    global _artifacts
    if _artifacts is None:
        from joblib import load

        _artifacts = {
            "model": load(MODELS_DIR / "gradient_boosting.joblib"),
            "scaler": load(MODELS_DIR / "scaler.joblib"),
            "feature_names": load(MODELS_DIR / "feature_names.joblib"),
        }
    return _artifacts


def predict(features: dict) -> dict[str, Any]:
    """Run inference on a single applicant's features."""
    artifacts = load_model()
    model = artifacts["model"]
    scaler = artifacts["scaler"]
    feature_names = artifacts["feature_names"]

    # Build feature vector in the same order as training
    emp_map = {"Unemployed": 0, "Underemployed": 1, "Employed": 2}
    age_map = {"<25": 0, "25-40": 1, "40-55": 2, ">55": 3}
    vec = [
        features.get("income_from_bank", 0),
        features.get("income_from_credit_report", 0),
        features.get("income_consistent", 0),
        features.get("income_used", 0),
        features.get("per_capita_income", 0),
        features.get("family_size", 1),
        features.get("net_worth", 0),
        features.get("address_match", 1),
        emp_map.get(features.get("employment_score", "Unemployed"), 0),
        age_map.get(features.get("age_band", "25-40"), 1),
    ]
    X = np.array([vec], dtype=float)
    X_scaled = scaler.transform(X)
    pred = int(model.predict(X_scaled)[0])
    proba = float(model.predict_proba(X_scaled)[0][pred])

    # SHAP explanation (explainer is built once and cached with the artifacts)
    shap_vals = None
    try:
        import shap

        explainer = artifacts.get("explainer")
        if explainer is None:
            explainer = shap.TreeExplainer(model)
            artifacts["explainer"] = explainer
        shap_vals = explainer.shap_values(X_scaled)
        shap_list = [{"feature": name, "shap_value": round(float(val), 4)} for name, val in zip(feature_names, shap_vals[0])]
        shap_list.sort(key=lambda x: -abs(x["shap_value"]))
    except Exception:
        shap_list = []

    # Feature importances fallback
    importances = model.feature_importances_
    feat_imp = [{"feature": name, "importance": round(float(imp), 4)} for name, imp in zip(feature_names, importances)]
    feat_imp.sort(key=lambda x: -x["importance"])

    return {
        "prediction": "approve" if pred == 1 else "soft_decline",
        "probability": round(proba, 4),
        "shap_top_features": shap_list[:5],
        "feature_importances": feat_imp[:5],
    }
