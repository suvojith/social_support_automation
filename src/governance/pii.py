"""PII masking, applied before anything is persisted.

Masks Emirates ID numbers, account numbers, and exact income figures in
extracted data. Original values stay in memory for the decision flow; only
the persisted form is masked.
"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

# Emirates ID: 784-YYYY-XXXXXXX-X (UAE format)
EMIRATES_ID_RE = re.compile(r"\b784-\d{4}-\d{7}-\d\b")
# Generic account number: 6-20 consecutive digits after "account"/"acct"/"iban"
ACCOUNT_RE = re.compile(r"(?i)(account|acct|iban)[:\s#]*([0-9]{6,20})")
# AED amounts: "AED 12,345.67" or "12,345.67 AED"
AED_AMOUNT_RE = re.compile(r"(?i)(AED\s)?[\d,]+\.\d{2}(\s?AED)?")


def mask_emirates_id(text: str) -> str:
    return EMIRATES_ID_RE.sub("784-XXXX-XXXXXXX-X", text)


def mask_account_numbers(text: str) -> str:
    return ACCOUNT_RE.sub(lambda m: f"{m.group(1)}: ****{m.group(2)[-4:]}", text)


def mask_value(value: Any) -> Any:
    """Recursively mask PII fields in a nested dict/list structure."""
    if isinstance(value, dict):
        result = {}
        for k, v in value.items():
            kl = k.lower()
            if kl in ("emirates_id", "eid", "national_id"):
                result[k] = mask_emirates_id(str(v)) if v else v
            elif kl in ("account_number", "iban", "bank_account"):
                result[k] = f"****{str(v)[-4:]}" if v else v
            elif kl in ("exact_income", "salary", "income_amount") and isinstance(v, (int, float)):
                result[k] = "***"
            else:
                result[k] = mask_value(v)
        return result
    if isinstance(value, list):
        return [mask_value(item) for item in value]
    if isinstance(value, str):
        return mask_account_numbers(mask_emirates_id(value))
    return value


def mask_for_storage(data: dict) -> dict:
    """Return a deep copy with PII masked, safe to persist to Mongo/PG."""
    return mask_value(deepcopy(data))
