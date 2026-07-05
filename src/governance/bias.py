"""Demographic-parity check across applicant slices.

Approval-rate parity is computed per slice (gender, age band, family size) and
written to a report. The data is synthetic, but the check runs for real so the
practice carries over unchanged to production data.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np


def demographic_parity_check(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    groups: dict[str, np.ndarray],
) -> dict[str, Any]:
    """Compute approval rates per demographic slice and the max disparity.

    Args:
        y_true: ground-truth labels (1=approve, 0=decline).
        y_pred: classifier predictions.
        groups: mapping of slice_name -> boolean mask over the same array.

    Returns:
        {"slices": {name: {"approval_rate": float, "count": int}}, "max_disparity": float}
    """
    slices: dict[str, dict[str, float]] = {}
    rates: list[float] = []
    for name, mask in groups.items():
        preds = y_pred[mask]
        rate = float(preds.mean()) if len(preds) > 0 else 0.0
        slices[name] = {"approval_rate": round(rate, 4), "count": int(mask.sum())}
        rates.append(rate)
    max_disparity = round(max(rates) - min(rates), 4) if rates else 0.0
    return {"slices": slices, "max_disparity": max_disparity}


def save_bias_report(report: dict, path: str | Path = "docs/bias_report.json"):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(report, f, indent=2)
