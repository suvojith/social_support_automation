# Evaluation Report

Generated: 2026-07-05 16:15 · judge model: qwen3.5 (local) · ground truth: citizen registry

## 1. Eligibility classifier — cross-validated metrics

| Metric (5-fold CV) | GradientBoosting | LogisticRegression baseline |
|---|---|---|
| F1 | 0.831 ± 0.033 | 0.790 |
| ACCURACY | 0.805 ± 0.029 | 0.755 |
| PRECISION | 0.804 ± 0.033 | 0.762 |
| RECALL | 0.866 ± 0.080 | 0.821 |
| ROC_AUC | 0.861 ± 0.055 | 0.829 |

Trained on 200 labeled applicants, 10 features, 12% label noise.

## 2. Document extraction accuracy vs ground truth (15 citizens)

| Field (source document) | Correct | Accuracy |
|---|---|---|
| income_from_bank (bank statement PDF) | 15/15 | 100% |
| income_from_credit_report (credit report PDF) | 15/15 | 100% |
| net_worth (assets/liabilities Excel) | 15/15 | 100% |
| years_experience (resume PDF) | 15/15 | 100% |
| education_level (resume PDF) | 15/15 | 100% |
| family_members (credit report PDF) | 15/15 | 100% |
| emirates_id (ID card OCR) | 14/15 | 93% |
| date_of_birth (ID card OCR) | 14/15 | 93% |
| name (ID card OCR, fuzzy >= 0.85) | 14/15 | 93% |

## 3. End-to-end routing correctness (rubric + validation on extracted documents)

| Citizen | Expected | Predicted | Match |
|---|---|---|---|
| Ahmed Al Mansoori | approve | approve | ✅ |
| Fatima Al Zaabi | approve | approve | ✅ |
| Hassan Al Blooshi | approve | approve | ✅ |
| Noora Al Suwaidi | approve | approve | ✅ |
| Khalid Al Marri | approve | approve | ✅ |
| Mariam Al Hashimi | approve | approve | ✅ |
| Sultan Al Nahyan | soft_decline | soft_decline | ✅ |
| Reem Al Falasi | soft_decline | soft_decline | ✅ |
| Omar Al Dhaheri | soft_decline | soft_decline | ✅ |
| Aisha Al Ketbi | human_review | human_review | ✅ |
| Saeed Al Shehhi | human_review | human_review | ✅ |
| Layla Al Otaibi | human_review | human_review | ✅ |
| Rashid Al Tunaiji | human_review | human_review | ✅ |
| Hamda Al Rashid | approve | approve | ✅ |
| Yousif Al Mazrouei | soft_decline | soft_decline | ✅ |
| **Accuracy** | | | **15/15 (100%)** |

## 4. Enablement RAG retrieval — recall of available programs in top-3

| Query intent | Expected type | Retrieved in top-3 | Recall |
|---|---|---|---|
| training programs for unemployed people without qualifications | upskilling | 2/3 | 67% |
| open job roles for candidates with diplomas or degrees | job_matching | 2/2 | 100% |
| career growth counseling for employed applicants | career_counseling | 2/2 | 100% |

## 5. Chat agent quality — LLM-as-judge (1-5)

| Application | Question | Groundedness | Persona | Completeness |
|---|---|---|---|---|
| APP-1731AC09 (approve) | Why was this decision made? | 5/5 | 5/5 | 5/5 |
| APP-1731AC09 (approve) | What verification was done for this application? | 5/5 | 5/5 | 5/5 |
| APP-AB36688D (human_review) | Why was this decision made? | 5/5 | 1/5 | 5/5 |
| APP-AB36688D (human_review) | What verification was done for this application? | 5/5 | 5/5 | 5/5 |
| APP-9381A7F3 (human_review) | Why was this decision made? | 5/5 | 5/5 | 5/5 |
| APP-9381A7F3 (human_review) | What verification was done for this application? | 5/5 | 5/5 | 5/5 |
| **Mean** | | **5.0/5** | **4.3/5** | **5.0/5** |

## 6. Decision rationale consistency — LLM-as-judge (1-5)

| Application | Recommendation | Rationale consistency |
|---|---|---|
| APP-1731AC09 | approve | 5/5 |
| APP-AB36688D | human_review | 5/5 |
| APP-9381A7F3 | human_review | 5/5 |
| **Mean** | | **5.0/5** |

## 7. Fairness — demographic parity (synthetic set)

| Demographic slice | Approval rate | n |
|---|---|---|
| Male | 60.4% | 106 |
| Female | 51.1% | 94 |
| Age <25 | 44.0% | 25 |
| Age 25-40 | 66.1% | 56 |
| Age 40-55 | 60.3% | 73 |
| Age >55 | 43.5% | 46 |
| Family <=3 | 59.3% | 81 |
| Family >3 | 53.8% | 119 |
| **Max disparity** | **22.6%** | |
