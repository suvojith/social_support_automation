"""Citizen registry — the sample "government registry" the UI integrates with.

Fifteen curated citizens with stable Emirates IDs, family records, and a full
document set each (bank statement, credit report, Emirates ID image, resume,
assets/liabilities Excel). Profiles are designed to cover every decision path:
clean approvals, soft declines on income or wealth, borderline incomes near the
band cutoffs, a bank-vs-credit income disagreement, a cross-document family
DOB conflict, and an address mismatch.

Profiles live in PostgreSQL (registry_citizens) and documents in MongoDB
(registry_documents); the /v1/registry endpoints serve both to the UI.
"""

from __future__ import annotations

import random
from typing import Any

from src.data.synthetic import _make_emirates_id_image, _make_excel, _make_pdf

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun"]

# fmt: off
CITIZENS: list[dict[str, Any]] = [
    {
        "emirates_id": "784-1988-6612345-1", "name": "Ahmed Al Mansoori", "gender": "M",
        "dob": "1988-03-14", "address": "Deira, Dubai",
        "employment_status": "Unemployed", "education_level": "Secondary",
        "years_experience": 0.0, "employer": None,
        "income_bank": 1800.0, "income_credit": 1850.0,
        "assets": {"Cash": 8000, "Vehicle": 12000}, "liabilities": {"Credit Card": 5000},
        "family": [
            {"name": "Salma Al Mansoori", "dob": "1991-07-22", "relation": "spouse"},
            {"name": "Khalid Al Mansoori", "dob": "2015-02-10", "relation": "son"},
            {"name": "Sara Al Mansoori", "dob": "2018-09-05", "relation": "daughter"},
        ],
    },
    {
        "emirates_id": "784-1992-7723456-2", "name": "Fatima Al Zaabi", "gender": "F",
        "dob": "1992-11-02", "address": "Karama, Dubai",
        "employment_status": "Underemployed", "education_level": "Diploma",
        "years_experience": 4.0, "employer": "Self-employed",
        "income_bank": 2350.0, "income_credit": 2400.0,
        "assets": {"Cash": 14000, "Jewellery": 16000}, "liabilities": {"Personal Loan": 18000},
        "family": [
            {"name": "Maha Al Zaabi", "dob": "2016-04-18", "relation": "daughter"},
            {"name": "Amna Al Zaabi", "dob": "1965-01-30", "relation": "mother"},
        ],
    },
    {
        "emirates_id": "784-1990-8834567-3", "name": "Hassan Al Blooshi", "gender": "M",
        "dob": "1990-06-25", "address": "Satwa, Dubai",
        "employment_status": "Unemployed", "education_level": "Bachelor",
        "years_experience": 6.0, "employer": None, "last_employer": "Etisalat",
        "income_bank": 2100.0, "income_credit": 2150.0,
        "assets": {"Cash": 15000, "Vehicle": 10000}, "liabilities": {"Car Loan": 20000},
        "family": [
            {"name": "Hessa Al Blooshi", "dob": "1993-12-08", "relation": "spouse"},
        ],
    },
    {
        "emirates_id": "784-1979-9945678-4", "name": "Noora Al Suwaidi", "gender": "F",
        "dob": "1979-02-17", "address": "Ras Al Khor, Dubai",
        "employment_status": "Unemployed", "education_level": "Primary",
        "years_experience": 0.0, "employer": None,
        "income_bank": 1500.0, "income_credit": 1520.0,
        "assets": {"Cash": 10000}, "liabilities": {"Credit Card": 2000},
        "family": [
            {"name": "Mohammed Al Suwaidi", "dob": "2008-06-12", "relation": "son"},
            {"name": "Shamsa Al Suwaidi", "dob": "2010-10-25", "relation": "daughter"},
            {"name": "Abdulla Al Suwaidi", "dob": "2013-01-19", "relation": "son"},
            {"name": "Saif Al Suwaidi", "dob": "1951-08-03", "relation": "father"},
        ],
    },
    {
        "emirates_id": "784-1985-1156789-5", "name": "Khalid Al Marri", "gender": "M",
        "dob": "1985-09-09", "address": "Al Barsha, Dubai",
        "employment_status": "Employed", "education_level": "Diploma",
        "years_experience": 12.0, "employer": "RTA",
        "income_bank": 2600.0, "income_credit": 2650.0,
        "assets": {"Cash": 20000, "Vehicle": 40000}, "liabilities": {"Car Loan": 25000},
        "family": [
            {"name": "Latifa Al Marri", "dob": "1988-04-14", "relation": "spouse"},
            {"name": "Rashed Al Marri", "dob": "2012-07-30", "relation": "son"},
        ],
    },
    {
        "emirates_id": "784-1994-2267890-6", "name": "Mariam Al Hashimi", "gender": "F",
        "dob": "1994-05-27", "address": "Bur Dubai, Dubai",
        "employment_status": "Underemployed", "education_level": "Secondary",
        "years_experience": 3.0, "employer": "Self-employed",
        "income_bank": 2050.0, "income_credit": 2000.0,
        "assets": {"Cash": 12000}, "liabilities": {"Personal Loan": 6000},
        "family": [
            {"name": "Omar Al Hashimi", "dob": "2019-08-14", "relation": "son"},
            {"name": "Alia Al Hashimi", "dob": "2021-03-02", "relation": "daughter"},
        ],
    },
    {
        "emirates_id": "784-1975-3378901-7", "name": "Sultan Al Nahyan", "gender": "M",
        "dob": "1975-12-01", "address": "Jumeirah, Dubai",
        "employment_status": "Employed", "education_level": "Master",
        "years_experience": 20.0, "employer": "ADNOC",
        "income_bank": 15200.0, "income_credit": 15000.0,
        "assets": {"Property": 600000, "Cash": 100000, "Vehicle": 50000},
        "liabilities": {"Mortgage": 280000, "Car Loan": 20000},
        "family": [
            {"name": "Sheikha Al Nahyan", "dob": "1979-05-16", "relation": "spouse"},
            {"name": "Zayed Al Nahyan", "dob": "2005-09-21", "relation": "son"},
        ],
    },
    {
        "emirates_id": "784-1983-4489012-8", "name": "Reem Al Falasi", "gender": "F",
        "dob": "1983-04-11", "address": "Jumeirah, Dubai",
        "employment_status": "Employed", "education_level": "Bachelor",
        "years_experience": 15.0, "employer": "Emirates NBD",
        "income_bank": 6500.0, "income_credit": 6550.0,
        "assets": {"Property": 750000, "Cash": 150000}, "liabilities": {"Mortgage": 250000},
        "family": [
            {"name": "Saeed Al Falasi", "dob": "1980-11-28", "relation": "spouse"},
        ],
    },
    {
        "emirates_id": "784-1980-5590123-9", "name": "Omar Al Dhaheri", "gender": "M",
        "dob": "1980-08-19", "address": "Mirdif, Dubai",
        "employment_status": "Employed", "education_level": "PhD",
        "years_experience": 18.0, "employer": "DP World",
        "income_bank": 12500.0, "income_credit": 12300.0,
        "assets": {"Cash": 80000, "Property": 200000}, "liabilities": {"Mortgage": 60000},
        "family": [
            {"name": "Muna Al Dhaheri", "dob": "1984-02-09", "relation": "spouse"},
            {"name": "Hind Al Dhaheri", "dob": "2011-12-17", "relation": "daughter"},
            {"name": "Tariq Al Dhaheri", "dob": "2014-06-23", "relation": "son"},
        ],
    },
    {
        "emirates_id": "784-1996-6601234-1", "name": "Aisha Al Ketbi", "gender": "F",
        "dob": "1996-01-15", "address": "Deira, Dubai",
        "employment_status": "Underemployed", "education_level": "Diploma",
        "years_experience": 2.0, "employer": "Self-employed",
        "income_bank": 2900.0, "income_credit": 2950.0,
        "assets": {"Cash": 9000}, "liabilities": {"Credit Card": 3000},
        "family": [
            {"name": "Fahad Al Ketbi", "dob": "2020-05-11", "relation": "son"},
        ],
    },
    {
        "emirates_id": "784-1982-7712345-2", "name": "Saeed Al Shehhi", "gender": "M",
        "dob": "1982-10-30", "address": "Al Barsha, Dubai",
        "employment_status": "Employed", "education_level": "Bachelor",
        "years_experience": 14.0, "employer": "Mashreq Bank",
        "income_bank": 7800.0, "income_credit": 7900.0,
        "assets": {"Cash": 45000, "Vehicle": 55000}, "liabilities": {"Car Loan": 30000},
        "family": [
            {"name": "Noura Al Shehhi", "dob": "1986-03-07", "relation": "spouse"},
            {"name": "Majid Al Shehhi", "dob": "2013-09-15", "relation": "son"},
        ],
    },
    {
        "emirates_id": "784-1991-8823456-3", "name": "Layla Al Otaibi", "gender": "F",
        "dob": "1991-07-07", "address": "Karama, Dubai",
        "employment_status": "Employed", "education_level": "Bachelor",
        "years_experience": 8.0, "employer": "flydubai",
        "income_bank": 4200.0, "income_credit": 5600.0,
        "assets": {"Cash": 25000}, "liabilities": {"Personal Loan": 12000},
        "family": [
            {"name": "Yara Al Otaibi", "dob": "2017-11-20", "relation": "daughter"},
        ],
    },
    {
        "emirates_id": "784-1987-9934567-4", "name": "Rashid Al Tunaiji", "gender": "M",
        "dob": "1987-03-23", "address": "Satwa, Dubai",
        "employment_status": "Unemployed", "education_level": "Secondary",
        "years_experience": 5.0, "employer": None, "last_employer": "Dubal",
        "income_bank": 2200.0, "income_credit": 2250.0,
        "assets": {"Cash": 13000}, "liabilities": {"Credit Card": 3000},
        "family": [
            {"name": "Moza Al Tunaiji", "dob": "1990-06-18", "relation": "spouse"},
            {"name": "Ali Al Tunaiji", "dob": "2014-11-05", "relation": "son"},
        ],
        # Credit bureau has a different DOB on record for Ali — a deliberate
        # cross-document conflict the validation agent should catch.
        "credit_dob_overrides": {"Ali Al Tunaiji": "2012-11-05"},
    },
    {
        "emirates_id": "784-1993-1145678-5", "name": "Hamda Al Rashid", "gender": "F",
        "dob": "1993-09-12", "address": "Deira, Dubai", "credit_address": "Karama, Dubai",
        "employment_status": "Unemployed", "education_level": "Diploma",
        "years_experience": 1.0, "employer": None,
        "income_bank": 1900.0, "income_credit": 1950.0,
        "assets": {"Cash": 11000}, "liabilities": {"Credit Card": 2000},
        "family": [
            {"name": "Majid Al Rashid", "dob": "1998-05-20", "relation": "brother"},
        ],
    },
    {
        "emirates_id": "784-1978-2256789-6", "name": "Yousif Al Mazrouei", "gender": "M",
        "dob": "1978-06-08", "address": "Mirdif, Dubai",
        "employment_status": "Employed", "education_level": "Master",
        "years_experience": 22.0, "employer": "Emirates Group",
        "income_bank": 9800.0, "income_credit": 9700.0,
        "assets": {"Cash": 90000, "Property": 110000}, "liabilities": {"Mortgage": 80000},
        "family": [
            {"name": "Salama Al Mazrouei", "dob": "1981-01-25", "relation": "spouse"},
            {"name": "Hamdan Al Mazrouei", "dob": "2009-04-08", "relation": "son"},
        ],
    },
]
# fmt: on

RESUME_ROLES = {
    "Etisalat": "Network Support Technician",
    "RTA": "Operations Coordinator",
    "ADNOC": "Senior Project Manager",
    "Emirates NBD": "Relationship Manager",
    "DP World": "Logistics Analyst",
    "Mashreq Bank": "Branch Operations Officer",
    "flydubai": "Ground Services Agent",
    "Dubal": "Plant Operator",
    "Emirates Group": "Fleet Planning Manager",
    "Self-employed": "Independent Trader",
}

SKILLS_BY_EDUCATION = {
    "Primary": "Housekeeping, Cooking, Childcare",
    "Secondary": "Customer Service, Cash Handling, Arabic/English Communication",
    "Diploma": "MS Office, Data Entry, Bookkeeping, Customer Service",
    "Bachelor": "MS Office, Project Coordination, Reporting, Team Leadership",
    "Master": "Strategic Planning, Budget Management, Stakeholder Engagement",
    "PhD": "Research, Data Analysis, Technical Writing, Leadership",
}


def _rng_for(citizen: dict) -> random.Random:
    return random.Random(citizen["emirates_id"])


def get_profile_payload(citizen: dict) -> dict[str, Any]:
    """The form-autofill payload served by GET /v1/registry/{emirates_id}."""
    return {
        "applicant_name": citizen["name"],
        "emirates_id": citizen["emirates_id"],
        "gender": citizen["gender"],
        "dob": citizen["dob"],
        "address": citizen["address"],
        "employment_status": citizen["employment_status"],
        "education_level": citizen["education_level"],
        "years_experience": citizen["years_experience"],
        "employer": citizen.get("employer"),
        "family_members": citizen["family"],
    }


def build_bank_statement(citizen: dict) -> bytes:
    rng = _rng_for(citizen)
    account = rng.randint(10**15, 10**16 - 1)
    income = citizen["income_bank"]
    opening = round(income * rng.uniform(1.5, 3.0), 2)
    lines = [
        "MASHREQ BANK — PERSONAL ACCOUNT STATEMENT",
        "",
        f"Account Holder: {citizen['name']}",
        f"Account Number: {account}",
        f"Address on file: {citizen['address']}",
        "Statement Period: 01 Jan 2026 - 30 Jun 2026",
        "",
        f"Opening Balance: AED {opening:,.2f}",
        "",
        "TRANSACTIONS",
        "-" * 70,
    ]
    balance = opening
    for month in MONTHS:
        rent = round(income * rng.uniform(0.30, 0.42), 2)
        utilities = round(rng.uniform(180, 420), 2)
        balance = round(balance + income - rent - utilities, 2)
        lines += [
            f"{month} 25  SALARY / INCOME DEPOSIT          +AED {income:,.2f}",
            f"{month} 28  RENT PAYMENT                     -AED {rent:,.2f}",
            f"{month} 30  DEWA UTILITIES                   -AED {utilities:,.2f}",
        ]
    lines += [
        "-" * 70,
        "",
        f"Closing Balance: AED {balance:,.2f}",
        f"Average Monthly Balance: AED {round((opening + balance) / 2, 2):,.2f}",
        f"Monthly Salary Deposits: AED {income:,.2f}",
    ]
    return _make_pdf("\n".join(lines))


def build_credit_report(citizen: dict) -> bytes:
    rng = _rng_for(citizen)
    overrides = citizen.get("credit_dob_overrides", {})
    score = rng.randint(560, 650) if citizen["income_credit"] < 5000 else rng.randint(680, 780)
    lines = [
        "UAE CREDIT BUREAU — CONSUMER CREDIT REPORT",
        "",
        f"Name: {citizen['name']}",
        f"Emirates ID: {citizen['emirates_id']}",
        f"Date of Birth: {citizen['dob']}",
        f"Address on file: {citizen.get('credit_address', citizen['address'])}",
        f"Employment Status: {citizen['employment_status']}",
        f"Reported Monthly Income: AED {citizen['income_credit']:,.2f}",
        f"Credit Score: {score}",
        "",
        "ACTIVE LIABILITIES",
        "-" * 70,
    ]
    for item, amount in citizen["liabilities"].items():
        lines.append(f"{item}: AED {amount:,.2f} outstanding")
    lines += ["", "FAMILY MEMBERS ON RECORD", "-" * 70]
    for member in citizen["family"]:
        dob = overrides.get(member["name"], member["dob"])
        lines.append(f"- {member['name']} | DOB: {dob} | Relation: {member['relation']}")
    lines += ["", "END OF REPORT"]
    return _make_pdf("\n".join(lines))


def build_resume(citizen: dict) -> bytes:
    rng = _rng_for(citizen)
    employer = citizen.get("employer") or citizen.get("last_employer")
    role = RESUME_ROLES.get(employer or "", "General Worker")
    years = citizen["years_experience"]
    lines = [
        citizen["name"].upper(),
        f"{citizen['address']}  |  {citizen['emirates_id']}",
        "",
        "PROFESSIONAL SUMMARY",
        "-" * 70,
    ]
    if citizen["employment_status"] == "Unemployed" and years > 0:
        lines.append(f"{role} with {years:g} years of experience, currently seeking new opportunities after a period out of work.")
    elif citizen["employment_status"] == "Unemployed":
        lines.append("Motivated candidate seeking a first formal role; open to training programs.")
    else:
        lines.append(f"{role} with {years:g} years of hands-on experience.")
    lines += [
        "",
        f"Education: {citizen['education_level']}",
        f"Years of Experience: {years:g}",
        f"Employment Status: {citizen['employment_status']}",
        "",
        "EMPLOYMENT HISTORY",
        "-" * 70,
    ]
    if employer:
        start_year = 2026 - int(years) if years else 2026
        end = "Present" if citizen["employment_status"] != "Unemployed" else str(rng.randint(2023, 2025))
        lines.append(f"{role} — {employer} ({start_year} - {end})")
        lines.append("Key responsibilities: daily operations, reporting, coordination with team leads.")
    else:
        lines.append("No formal employment history.")
    lines += [
        "",
        "SKILLS",
        "-" * 70,
        SKILLS_BY_EDUCATION.get(citizen["education_level"], "Communication, Teamwork"),
    ]
    return _make_pdf("\n".join(lines))


def build_assets_excel(citizen: dict) -> bytes:
    return _make_excel(citizen["assets"], citizen["liabilities"])


def build_eid_image(citizen: dict) -> bytes:
    return _make_emirates_id_image(citizen["name"], citizen["emirates_id"], citizen["dob"])


def build_documents(citizen: dict) -> list[dict[str, Any]]:
    """All five documents for one citizen as {doc_type, filename, content} records."""
    eid = citizen["emirates_id"].replace("-", "")
    return [
        {"doc_type": "bank_statement", "filename": f"bank_statement_{eid}.pdf", "content": build_bank_statement(citizen)},
        {"doc_type": "credit_report", "filename": f"credit_report_{eid}.pdf", "content": build_credit_report(citizen)},
        {"doc_type": "emirates_id", "filename": f"emirates_id_{eid}.png", "content": build_eid_image(citizen)},
        {"doc_type": "resume", "filename": f"resume_{eid}.pdf", "content": build_resume(citizen)},
        {"doc_type": "assets_liabilities", "filename": f"assets_liabilities_{eid}.xlsx", "content": build_assets_excel(citizen)},
    ]


def find_citizen(query: str) -> dict | None:
    """Match a citizen by Emirates ID (exact) or name (case-insensitive)."""
    q = query.strip().lower()
    for c in CITIZENS:
        if c["emirates_id"].lower() == q or c["name"].lower() == q:
            return c
    return None
