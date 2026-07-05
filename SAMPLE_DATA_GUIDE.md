# 🧪 Sample Data Guide

Everything you need to test the app against data that is **actually present in the backend databases**. The seeder loads a citizen registry of 15 people — each with a full profile and a complete document set — so you can exercise every decision path without inventing data.

## Where the sample data lives

| Store | What's in it |
|---|---|
| **PostgreSQL** → `registry_citizens` | 15 citizen profiles: name, Emirates ID, DOB, address, employment, education, family members |
| **MongoDB** → `registry_documents` | 5 documents per citizen: bank statement (PDF), credit report (PDF), Emirates ID (PNG), resume (PDF), assets/liabilities (XLSX) |
| **`data/samples/<Name>/`** | The same documents as plain files, if you want to open them or upload manually |
| **PostgreSQL** → `applications` | 200 synthetic historical applications used to train the classifier |

Re-seed anytime with `make seed` (or just the registry: `docker compose exec api python -m seeder.registry`).

## The 3-click test flow

1. Open the UI → in the **sidebar**, pick a citizen from **Sample citizen (demo)** (or type a name / Emirates ID into the form).
2. Click **📇 Get User Details** — the application form autofills from the registry (every field stays editable).
3. Click **📂 Get User Documents** — all five documents attach from the registry document store.
4. Hit **🚀 Submit Application** and watch the agentic workflow run.

## The 15 registry citizens

### ✅ Expected: Approve

| Name | Emirates ID | Profile | Enablement |
|---|---|---|---|
| Ahmed Al Mansoori | `784-1988-6612345-1` | Unemployed, Secondary education, ~AED 1,800/mo, family of 4 | Upskilling |
| Fatima Al Zaabi | `784-1992-7723456-2` | Underemployed seamstress, Diploma, ~AED 2,350/mo | Job matching |
| Hassan Al Blooshi | `784-1990-8834567-3` | Unemployed IT technician (ex-Etisalat), Bachelor | Job matching |
| Noora Al Suwaidi | `784-1979-9945678-4` | Unemployed, Primary education, family of 6, ~AED 1,500/mo | Upskilling |
| Khalid Al Marri | `784-1985-1156789-5` | Employed at RTA but low income (~AED 2,600/mo) | Job matching (higher-paying roles) |
| Mariam Al Hashimi | `784-1994-2267890-6` | Underemployed single mother, ~AED 2,000/mo | Job matching |
| Hamda Al Rashid | `784-1993-1145678-5` | Clean approve profile **but** her credit report address (Karama) differs from her form address (Deira) → validation raises a medium address-mismatch flag, decision still approves | Upskilling |

### 🟡 Expected: Soft Decline

| Name | Emirates ID | Why declined | Enablement |
|---|---|---|---|
| Sultan Al Nahyan | `784-1975-3378901-7` | High income (~AED 15,000/mo) **and** high net worth (~AED 450k) | Career counseling |
| Reem Al Falasi | `784-1983-4489012-8` | High net worth (~AED 650k) despite medium income | Job matching |
| Omar Al Dhaheri | `784-1980-5590123-9` | High income (~AED 12,400/mo) | Career counseling |
| Yousif Al Mazrouei | `784-1978-2256789-6` | High income (~AED 9,700/mo) | Career counseling |

### 🟠 Expected: Human Review

| Name | Emirates ID | What routes it to a caseworker |
|---|---|---|
| Aisha Al Ketbi | `784-1996-6601234-1` | Per-capita income ~AED 2,900 — within ±10% of the 3,000 band cutoff |
| Saeed Al Shehhi | `784-1982-7712345-2` | Per-capita income ~AED 7,800 — within ±10% of the 8,000 band cutoff |
| Layla Al Otaibi | `784-1991-8823456-3` | Bank statement says AED 4,200/mo, credit report says AED 5,600/mo — >15% disagreement |
| Rashid Al Tunaiji | `784-1987-9934567-4` | His son Ali's DOB is **2014-11-05** on the application form but **2012-11-05** on the credit report — the validation agent catches this via a Neo4j cross-document query |

## Edge cases worth demoing

- **Idempotency** — fill the *Idempotency Key* field (under *Advanced*) with any string, submit, then submit again with the same key: the same application ID comes back instantly, no duplicate is created. Reusing that key with *different* data is rejected with a clear error — a key identifies one submission, it isn't a session setting.
- **Unknown citizen** — type a made-up Emirates ID and click *Get User Details*: the UI reports it isn't in the registry.
- **Cross-document DOB conflict** — submit Rashid Al Tunaiji with his registry documents and watch the decision route to human review with a `family_member_dob` flag.
- **Manual override** — autofill Ahmed, then edit his income situation by uploading a different bank statement from `data/samples/`; the decision follows the documents, not the form.
- **Arabic UI** — switch the sidebar language selector to العربية; the whole UI flips.

## Chat prompts to try (after a submission)

- *"What training programs am I eligible for?"*
- *"Why was my application declined?"*
- *"What jobs match my experience?"*

## Verifying the data directly

```bash
# Registry profiles in PostgreSQL
docker compose exec postgres psql -U sswa -d sswa -c "SELECT emirates_id, full_name, employment_status FROM registry_citizens;"

# Documents in MongoDB
docker compose exec mongo mongosh -u sswa -p change_me_in_prod --quiet --eval \
  'db.getSiblingDB("sswa").registry_documents.aggregate([{ $group: { _id: "$emirates_id", docs: { $sum: 1 } } }])'

# Family graph in Neo4j (browser: http://localhost:7474)
# MATCH (a:Applicant)-[:DECLARES]->(p:Person) RETURN a, p LIMIT 50
```
