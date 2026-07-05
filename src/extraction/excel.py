"""Assets/liabilities Excel extraction via pandas/openpyxl."""

from __future__ import annotations

import io
from typing import Any

import pandas as pd


def extract_excel(excel_bytes: bytes) -> dict[str, Any]:
    """Extract assets/liabilities data from an Excel file."""
    df = pd.read_excel(io.BytesIO(excel_bytes), sheet_name="Assets_Liabilities")
    assets = df[df["Type"] == "Asset"]
    liabilities = df[df["Type"] == "Liability"]
    total_assets = float(assets["Amount_AED"].sum())
    total_liabilities = float(liabilities["Amount_AED"].sum())
    return {
        "total_assets": round(total_assets, 2),
        "total_liabilities": round(total_liabilities, 2),
        "net_worth": round(total_assets - total_liabilities, 2),
        "line_items": df.to_dict(orient="records"),
    }


def extract_tabular(content: bytes, filename: str | None = None) -> dict[str, Any]:
    """Extract tabular data from Excel content."""
    return extract_excel(content)
