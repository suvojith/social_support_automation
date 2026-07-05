"""Enablement programs + job listings seeded into Qdrant for RAG retrieval."""

from __future__ import annotations

ENABLEMENT_PROGRAMS = [
    {
        "id": "prog-001",
        "type": "upskilling",
        "title": "Digital Skills Bootcamp — 12 weeks",
        "provider": "UAE Ministry of Education",
        "description": "IT fundamentals, data entry, office productivity. For unemployed applicants with no formal qualification.",
        "language": "EN/AR",
        "duration_weeks": 12,
    },
    {
        "id": "prog-002",
        "type": "upskilling",
        "title": "Vocational Training — Hospitality & Retail",
        "provider": "Dubai Tourism Institute",
        "description": "Hands-on hospitality and retail skills. Certificates on completion.",
        "language": "EN/AR",
        "duration_weeks": 8,
    },
    {
        "id": "prog-003",
        "type": "upskilling",
        "title": "Financial Literacy Program",
        "provider": "Emirates NBD",
        "description": "Budgeting, saving, debt management basics.",
        "language": "EN/AR",
        "duration_weeks": 4,
    },
    {
        "id": "prog-004",
        "type": "job_matching",
        "title": "Job Matching — Administration Roles",
        "provider": "UAE Job Connect",
        "description": "Matching qualified candidates to administrative and clerical openings.",
        "language": "EN",
        "roles": ["Admin Assistant", "Data Entry Clerk", "Receptionist"],
    },
    {
        "id": "prog-005",
        "type": "job_matching",
        "title": "Job Matching — Technical Roles",
        "provider": "UAE Tech Council",
        "description": "Matching candidates with diplomas/degrees to IT and engineering roles.",
        "language": "EN",
        "roles": ["IT Support", "Junior Developer", "Field Technician"],
    },
    {
        "id": "prog-006",
        "type": "career_counseling",
        "title": "Career Counseling — 1-on-1 Sessions",
        "provider": "UAE Career Development Center",
        "description": "Personalized career path guidance for employed applicants seeking growth.",
        "language": "EN/AR",
        "duration_weeks": 2,
    },
    {
        "id": "prog-007",
        "type": "career_counseling",
        "title": "Entrepreneurship Workshop",
        "provider": "Dubai SME",
        "description": "Business startup fundamentals for applicants considering self-employment.",
        "language": "EN/AR",
        "duration_weeks": 6,
    },
]

ELIGIBILITY_RULES = [
    {
        "id": "rule-001",
        "text": "Applicant is eligible for financial support if income_band is Low or Medium AND wealth_band is Negative/Low or Medium.",
        "criterion": "income + wealth",
    },
    {
        "id": "rule-002",
        "text": "Applicant receives a soft_decline if income_band is High OR wealth_band is High — still eligible for enablement support.",
        "criterion": "income + wealth",
    },
    {
        "id": "rule-003",
        "text": "Borderline cases (per_capita_income within ±10% of a band cutoff, "
        "or bank vs credit-report income disagreement >15%) route to human review.",
        "criterion": "borderline",
    },
    {
        "id": "rule-004",
        "text": "Unemployed applicants with no formal qualification are directed to upskilling programs.",
        "criterion": "enablement",
    },
    {
        "id": "rule-005",
        "text": "Employed applicants with stable income above threshold receive career counseling only, no financial support.",
        "criterion": "enablement",
    },
]
