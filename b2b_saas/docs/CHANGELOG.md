# Changelog

- 0.1.0 B2B SaaS pack: 10 visible tables, 5 hidden tables, B2B state engine (9 states, rule version in config), noise, six labels, validator (150 checks), 12 tests. E-commerce and BFSI packs unchanged (their 20 tests still pass).

## Deviations and gaps (read before use)
1. **Stripe is in the workbook** although the brief says it is not; billing follows the Stripe shape (statuses incomplete, incomplete_expired, trialing, active, past_due, canceled, unpaid, paused). `paused` is kept distinct from `pause_collection`.
2. Lead statuses add `qualified`; subscription statuses add `paused` and `pending` (workbook extensions, flagged in `schemas/`).
3. Window is 30 months (brief 24, answers 24 to 36). Regime 2 starts at month 16.
4. MQL to SQL conflicts in the answers (13% vs 38%); 25% used. Sales cycle conflicts; mid values per segment used (dev medians 36 / 95 / 171 days).
5. The 3.5% churn figure is ignored. Q41 annual logo churn (15 / 10 / 5%) wins over the Q42 mid-market renewal split, which sums to 17% churn. The validator compares to the Q42 split rescaled to 10% churn.
6. The brief's hidden `account_type` is mapped to the answers' customer and prospect types. Currency is USD bands.
7. Dev-run NRR per cycle is 0.94 / 1.03 / 1.09 (SMB / MM / ENT) against answers' 0.97 / 1.08 / 1.18. GRR is within tolerance. The answers' NRR and GRR are not consistent with their churn figures.
8. Win-back share of churned is 7.5% (answers: 8 to 12%), inside the validator's tolerance.
9. Customer counts are small: dev has about 352 customer accounts (250 base, about 100 new) because only about 0.7% of leads reach a subscription. Retention checks on dev use wide tolerances for that reason; `full` has about 1,667 customers but was not validated.
10b. Usage is sampled for large accounts (cap 40 named users).
10. Gainsight CTA statuses in the workbook (Draft, Closed, Snoozed) differ from Gainsight's defaults (New, Work In Progress, Closed Success/No Action/Invalid); the workbook was followed. PaymentIntent `requires_confirmation` is missing from the workbook map; DocuSign `deleted` and `timedout` are not modelled.
11. The leakage-trap check uses AUC above 0.85 (measured 0.91 on dev, 0.897 on an earlier dev run).
12. The 1,000-account sample fails 15 of 150 checks because it has only 29 customers.
13. `full` was generated but not validated (validator out of memory on 7 GB).
14. Only 4 (trigger, action) uplift cells are large enough to test; uplift estimates are noisy elsewhere.
15. About 2.6% of contacts share a `person_key` with one other contact: logged duplicate-account noise, by design.
16. Fixed before release: personal-email contacts all hashed to the same `person_key` (generator bug, found by the consent check); guards could not see opportunity activities, legal-review intervals or renewal-opportunity intervals planned after a decision; base-account consent events before the window start were dropped.
17. Known issue in older packs, not fixed here: the e-commerce and BFSI `noise_log` shared-phone logging noted in the BFSI changelog.
