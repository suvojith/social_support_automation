"""Synthetic applicant + mock document generator.

Generates labeled applicants, each with 5 document types:
  - application form (JSON)
  - bank statement (text/PDF)
  - credit report (text/PDF)
  - Emirates ID (image — generated as a PIL image)
  - resume (text/PDF)
  - assets/liabilities Excel (tabular)

UAE-realistic formatting: Emirates ID layout (784-YYYY-XXXXXXX-X), Arabic names,
AED bank statements. A share of applicants get deliberate cross-document DOB
conflicts for the validation agent to catch.

Label noise (~12%) is injected so the classifier has something to actually learn.
"""

from __future__ import annotations

import io
import random
from dataclasses import dataclass, field
from typing import Any

from src.data.rubric import (
    base_eligibility_label,
    compute_per_capita_income,
    income_band,
    wealth_band,
)

ARABIC_FIRST_NAMES = [
    "Ahmed",
    "Mohammed",
    "Ali",
    "Hassan",
    "Khalifa",
    "Saeed",
    "Rashid",
    "Omar",
    "Fatima",
    "Aisha",
    "Mariam",
    "Noor",
    "Layla",
    "Hessa",
    "Shaikha",
    "Mozza",
    "Abdulla",
    "Sultan",
    "Hamad",
    "Yousif",
    "Noura",
    "Amna",
    "Reem",
    "Shamsa",
]
ARABIC_LAST_NAMES = [
    "Al Mansoori",
    "Al Maktoum",
    "Al Nahyan",
    "Al Rashid",
    "Al Suwaidi",
    "Al Marri",
    "Al Zaabi",
    "Al Dhaheri",
    "Al Hashimi",
    "Al Otaibi",
    "Al Blooshi",
    "Al Shehhi",
    "Al Ketbi",
    "Al Falasi",
    "Al Tunaiji",
]
EMPLOYERS = [
    "Emirates Group",
    "ADNOC",
    "Etisalat",
    "Dubal",
    "DP World",
    "Mashreq Bank",
    "Emirates NBD",
    "Aldar Properties",
    "flydubai",
    "RTA",
    "Self-employed",
    "None",
]
EDUCATION_LEVELS = ["Primary", "Secondary", "Diploma", "Bachelor", "Master", "PhD"]
EMPLOYMENT_STATUSES = ["Unemployed", "Underemployed", "Employed"]
RELATIONS = ["spouse", "son", "daughter", "father", "mother", "brother", "sister"]
DUBAI_AREAS = [
    "Deira, Dubai",
    "Bur Dubai, Dubai",
    "Jumeirah, Dubai",
    "Al Barsha, Dubai",
    "Karama, Dubai",
    "Satwa, Dubai",
    "Ras Al Khor, Dubai",
    "Mirdif, Dubai",
]


@dataclass
class FamilyMember:
    member_id: str
    name: str
    dob: str
    relation: str
    source_doc: str


@dataclass
class SyntheticApplicant:
    application_id: str
    applicant_name: str
    emirates_id: str
    dob: str
    age_band: str
    address: str
    employment_status: str
    education_level: str
    years_experience: float
    has_qualification: bool
    household_income: float
    income_from_bank: float
    income_from_credit_report: float
    total_assets: float
    total_liabilities: float
    net_worth: float
    family_members: list[FamilyMember] = field(default_factory=list)
    features: dict = field(default_factory=dict)
    income_band_val: str = ""
    wealth_band_val: str = ""
    label: int = 0  # 1=eligible, 0=soft_decline (with noise)
    has_dob_conflict: bool = False
    address_match: bool = True
    gender: str = ""
    documents: dict[str, Any] = field(default_factory=dict)


def _random_dob(rng: random.Random, min_age: int = 20, max_age: int = 65) -> str:
    year = rng.randint(1961, 2006)
    month = rng.randint(1, 12)
    day = rng.randint(1, 28)
    return f"{year:04d}-{month:02d}-{day:02d}"


def _age_band(dob: str) -> str:
    age = 2026 - int(dob[:4])
    if age < 25:
        return "<25"
    if age <= 40:
        return "25-40"
    if age <= 55:
        return "40-55"
    return ">55"


def _random_emirates_id(rng: random.Random) -> str:
    return f"784-{rng.randint(1970, 2006)}-{rng.randint(1000000, 9999999)}-{rng.randint(1, 9)}"


def _make_emirates_id_image(name: str, eid: str, dob: str) -> bytes:
    """Generate a mock Emirates-ID card image (PNG) using PIL.

    Rendered large and high-contrast, like a decent scan — tiny fonts make
    the OCR model misread digits, which is noise, not a useful test.
    """
    from PIL import Image, ImageDraw, ImageFont

    try:
        header_font = ImageFont.load_default(size=30)
        body_font = ImageFont.load_default(size=26)
        footer_font = ImageFont.load_default(size=18)
    except TypeError:  # very old Pillow: no size argument
        header_font = body_font = footer_font = ImageFont.load_default()

    img = Image.new("RGB", (900, 560), "white")
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, 900, 90], fill=(10, 60, 120))
    draw.text((30, 28), "UNITED ARAB EMIRATES", fill="white", font=header_font)
    draw.text((30, 130), f"Name: {name}", fill="black", font=body_font)
    draw.text((30, 190), f"Emirates ID: {eid}", fill="black", font=body_font)
    draw.text((30, 250), f"Date of Birth: {dob}", fill="black", font=body_font)
    draw.text((30, 310), "Nationality: UAE", fill="black", font=body_font)
    draw.rectangle([30, 380, 870, 392], fill=(200, 200, 200))
    draw.text((30, 430), "MOCK ID — for prototype only", fill=(120, 120, 120), font=footer_font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_pdf(text: str) -> bytes:
    """Generate a simple PDF from text using pypdf (no external writer needed)."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas

        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        y = 800
        for line in text.split("\n"):
            c.drawString(40, y, line[:90])
            y -= 15
            if y < 40:
                c.showPage()
                y = 800
        c.save()
        return buf.getvalue()
    except Exception:
        return text.encode("utf-8")


def _make_excel(assets: dict, liabilities: dict) -> bytes:
    """Generate an assets/liabilities Excel file as bytes."""
    import pandas as pd

    df = pd.DataFrame(
        {
            "Category": list(assets.keys()) + list(liabilities.keys()),
            "Type": ["Asset"] * len(assets) + ["Liability"] * len(liabilities),
            "Amount_AED": list(assets.values()) + list(liabilities.values()),
        }
    )
    buf = io.BytesIO()
    df.to_excel(buf, index=False, sheet_name="Assets_Liabilities")
    return buf.getvalue()


def generate_applicants(
    n: int = 200,
    label_noise_rate: float = 0.12,
    seed: int = 42,
    conflict_rate: float = 0.15,
) -> list[SyntheticApplicant]:
    """Generate n synthetic applicants with 5 doc types, rubric labels + noise, DOB conflicts."""
    rng = random.Random(seed)
    applicants: list[SyntheticApplicant] = []

    for i in range(n):
        app_id = f"APP-{i + 1:04d}"
        name = f"{rng.choice(ARABIC_FIRST_NAMES)} {rng.choice(ARABIC_LAST_NAMES)}"
        eid = _random_emirates_id(rng)
        dob = _random_dob(rng)
        age_b = _age_band(dob)
        address = rng.choice(DUBAI_AREAS)
        gender = (
            "F"
            if name.split()[0]
            in (
                "Fatima",
                "Aisha",
                "Mariam",
                "Noor",
                "Layla",
                "Hessa",
                "Shaikha",
                "Mozza",
                "Noura",
                "Amna",
                "Reem",
                "Shamsa",
            )
            else "M"
        )

        emp_status = rng.choices(EMPLOYMENT_STATUSES, weights=[0.35, 0.25, 0.40], k=1)[0]
        education = rng.choice(EDUCATION_LEVELS)
        has_qual = education in ("Diploma", "Bachelor", "Master", "PhD")
        years_exp = round(rng.uniform(0, 25), 1) if emp_status != "Unemployed" else 0.0

        # Income (AED/month) — varies by employment status
        if emp_status == "Unemployed":
            base_income = rng.uniform(500, 3000)
        elif emp_status == "Underemployed":
            base_income = rng.uniform(2000, 8000)
        else:
            base_income = rng.uniform(5000, 25000)

        # Bank vs credit-report income: mostly consistent, sometimes disagree
        income_bank = round(base_income, 2)
        if rng.random() < 0.20:
            income_credit = round(base_income * rng.uniform(0.7, 1.3), 2)
        else:
            income_credit = round(base_income * rng.uniform(0.95, 1.05), 2)

        # Family
        family_size = rng.randint(1, 8)
        household_income = income_bank * family_size  # simplified
        members: list[FamilyMember] = []
        for j in range(family_size - 1):  # applicant + members
            mname = f"{rng.choice(ARABIC_FIRST_NAMES)} {rng.choice(ARABIC_LAST_NAMES)}"
            mdob = _random_dob(rng)
            members.append(
                FamilyMember(
                    member_id=f"{app_id}-M{j + 1}",
                    name=mname,
                    dob=mdob,
                    relation=rng.choice(RELATIONS),
                    source_doc="application_form",
                )
            )

        # Deliberate DOB conflict: ~15% of applicants have a member whose DOB
        # differs between the application form and the credit report.
        has_conflict = rng.random() < conflict_rate
        if has_conflict and members:
            m = rng.choice(members)
            conflict_dob = _random_dob(rng)
            members.append(
                FamilyMember(
                    member_id=f"{m.member_id}-CREDIT",
                    name=m.name,
                    dob=conflict_dob,
                    relation=m.relation,
                    source_doc="credit_report",
                )
            )

        # Assets / liabilities
        total_assets = round(rng.uniform(0, 500000), 2)
        total_liabilities = round(rng.uniform(0, 400000), 2)
        net_worth = round(total_assets - total_liabilities, 2)

        # Address match: ~80% match
        address_match = rng.random() < 0.80
        credit_address = address if address_match else rng.choice([a for a in DUBAI_AREAS if a != address])

        # Compute rubric
        per_capita = compute_per_capita_income(household_income, family_size)
        ib = income_band(per_capita)
        wb = wealth_band(net_worth)
        base_label = base_eligibility_label(ib, wb)

        # Inject label noise (~12%): flip the label
        label = base_label
        if rng.random() < label_noise_rate:
            label = 1 - base_label

        applicant = SyntheticApplicant(
            application_id=app_id,
            applicant_name=name,
            emirates_id=eid,
            dob=dob,
            age_band=age_b,
            address=address,
            employment_status=emp_status,
            education_level=education,
            has_qualification=has_qual,
            years_experience=years_exp,
            household_income=round(household_income, 2),
            income_from_bank=income_bank,
            income_from_credit_report=income_credit,
            total_assets=total_assets,
            total_liabilities=total_liabilities,
            net_worth=net_worth,
            family_members=members,
            features={},
            income_band_val=ib,
            wealth_band_val=wb,
            label=label,
            has_dob_conflict=has_conflict,
            address_match=address_match,
            gender=gender,
        )

        income_consistent = abs(income_bank - income_credit) / max(income_bank, income_credit, 1) <= 0.15
        applicant.features = {
            "income_from_bank": income_bank,
            "income_from_credit_report": income_credit,
            "income_consistent": int(income_consistent),
            "income_used": min(income_bank, income_credit),
            "per_capita_income": round(per_capita, 2),
            "family_size": family_size,
            "net_worth": net_worth,
            "employment_score": emp_status,
            "age_band": age_b,
            "address_match": int(address_match),
        }

        # Generate mock documents
        applicant.documents = _generate_documents(applicant, credit_address, rng)
        applicants.append(applicant)

    return applicants


def _generate_documents(a: SyntheticApplicant, credit_address: str, rng: random.Random) -> dict[str, Any]:
    """Generate the 5 document types as in-memory bytes/text."""
    # Application form (JSON)
    form = {
        "applicant_name": a.applicant_name,
        "emirates_id": a.emirates_id,
        "dob": a.dob,
        "address": a.address,
        "employment_status": a.employment_status,
        "education_level": a.education_level,
        "years_experience": a.years_experience,
        "family_members": [
            {"name": m.name, "dob": m.dob, "relation": m.relation} for m in a.family_members if m.source_doc == "application_form"
        ],
    }

    # Bank statement (text)
    bank_text = f"""BANK STATEMENT — Mashreq Bank
Account Holder: {a.applicant_name}
Account Number: {rng.randint(10**15, 10**16 - 1)}
Period: Jan-Jun 2026
Average Monthly Balance: AED {round(a.income_from_bank * 3, 2)}
Monthly Salary Deposits: AED {a.income_from_bank}
Address on file: {a.address}
"""

    # Credit report (text)
    family_credit = [{"name": m.name, "dob": m.dob, "relation": m.relation} for m in a.family_members if m.source_doc == "credit_report"]
    credit_text = f"""CREDIT BUREAU REPORT — UAE Credit Bureau
Name: {a.applicant_name}
Emirates ID: {a.emirates_id}
Reported Monthly Income: AED {a.income_from_credit_report}
Address on file: {credit_address}
Employment Status: {a.employment_status}
Family Members: {len(family_credit) + 1}
Credit Score: {rng.randint(550, 800)}
"""

    # Resume (text)
    resume_text = f"""RESUME
Name: {a.applicant_name}
Education: {a.education_level}
Years of Experience: {a.years_experience}
Employment Status: {a.employment_status}
Skills: Communication, Teamwork, MS Office
"""

    # Emirates ID (image)
    eid_image = _make_emirates_id_image(a.applicant_name, a.emirates_id, a.dob)

    # Assets/liabilities (Excel)
    assets = {
        "Cash": round(a.total_assets * 0.3, 2),
        "Property": round(a.total_assets * 0.5, 2),
        "Vehicle": round(a.total_assets * 0.2, 2),
    }
    liabilities = {"Loan": round(a.total_liabilities * 0.6, 2), "Credit Card": round(a.total_liabilities * 0.4, 2)}
    excel_bytes = _make_excel(assets, liabilities)

    return {
        "application_form": {"json": form},
        "bank_statement": {"text": bank_text},
        "credit_report": {"text": credit_text, "family_members": family_credit},
        "emirates_id": {"image": eid_image, "name": a.applicant_name, "eid": a.emirates_id, "dob": a.dob},
        "resume": {"text": resume_text},
        "assets_liabilities": {
            "excel": excel_bytes,
            "total_assets": a.total_assets,
            "total_liabilities": a.total_liabilities,
        },
    }
