> Part of the combined package. Run all commands from the root folder (where `vynqe_synth/` is). `docs/` and `sample_1000/` below are inside this pack's folder.

# vynqe_synth: synthetic data generator (B2B SaaS pack, v0.1.0)

**This data is synthetic.** Every number comes from a configured assumption (see `docs/parameters_report.md`, 178 graded settings). It is for building and testing the Customer Lifecycle Intelligence pipeline. **It makes no claim about how any model will perform on real accounts**, and nothing here should be quoted as evidence of real-world uplift, win rates, churn or expansion.

The code folder also contains the e-commerce and BFSI packs (delivered earlier) because all packs share `vynqe_synth/core`. This package is the B2B SaaS delivery.

## Run
```
pip install pyarrow pyyaml pandas numpy scikit-learn pytest pydantic
python -m vynqe_synth generate --pack b2b_saas --preset dev --seed 42 --out ./out [--csv]
python -m vynqe_synth validate --out ./out
python -m pytest tests
```
Presets (`vynqe_synth/config/presets.yaml`, section `b2b_saas`):

| Preset | Base accounts + new leads | Time | Events | Notes |
|---|---|---|---|---|
| `tiny` | 50 + 2,500 | about 10 s | about 57k events, 0.6M usage rows | smoke test; 139 of 150 checks pass; too small for churn, renewal or uplift estimates |
| `dev` | 250 + 15,000 | about 30 s | about 324k events, 2.9M usage rows | recommended; all 150 validation checks pass |
| `full` | 1,200 + 66,000 | about 2 min (generated) | about 1.45M events, 13.7M usage rows | generated, **not validated**: the validator ran out of memory on a 7 GB machine |

`--n 1000` overrides the new-lead count (that is how `sample_1000/` was made). The same seed gives byte-identical data (tested). The unit is an **account** (a company the vendor can see, from lead through customer to churn), not a person or a subscription. Only about 0.7% of new leads become customers (the configured funnel multiplies out that way), so `dev` has about 352 accounts with a subscription (250 base accounts plus about 100 new ones) and 1,172 subscription rows, and `full` about 1,667 customer accounts. Retention, renewal and uplift statistics rest on those few hundred to few thousand customers.

## Output
- `visible/` (10 tables): accounts, contacts (leads merged in), events, opportunities (e-sign merged in), product_usage_daily, subscriptions, invoices, actions, state_history, campaigns. `docs/table_dictionary.md` lists every column. `docs/B2B_DATASET_FULL_REPORT_dev_15k.md` is the full report for the dev run (distributions, table by table, labels, validation).
- `hidden/` (5 tables, validation only): account_truth (true customer or prospect type, fit score, lock-in, churn hazard, planted uplift), contact_truth, opportunity_truth (true win probability with and without action), state_truth, noise_log. Feature, state and label code must never read these (checked by a test and a validator check).
- `schemas/` JSON contracts; `reports/` row counts and the validation report.
- No raw name, email, phone, address, ID or exact amount in visible tables: keyed hashes and amount bands only.
- The brief's tables were merged into 10 visible tables (leads in `contacts`; e-sign in `opportunities`; consent history, tickets, CS health scores and CTAs, web and product sessions in `events`; tasks, messages and calls in `actions`).

## What the data contains
- **Journey:** anonymous web sessions, lead, MQL, SQL, opportunity (discovery, evaluation, proposal, negotiation, with legal or security review and e-sign), trial, subscription (monthly or annual, Stripe-shaped statuses), invoices and card payment retries, onboarding, daily product usage, support tickets, health scores and CS tasks, expansion, contraction, renewal opportunities, cancellation, silent lapse (annual plans only), involuntary churn from payment failure, win-back.
- **Two periods:** months 1 to 15 use legacy biased targeting (no decision id, no propensity; touch probability rises with fit and ARR); months 16 to 30 use a randomised policy with logged propensity (25% do_nothing, the rest uniform over allowed actions), guardrail reason codes and an 8% whole-account holdout by salted hash. Transactional and regulatory notices are logged but never held out and never chosen by the policy.
- **Guardrails (12 reason codes):** no_consent, unknown_consent, open_opportunity, open_ticket, renewal_within_14d, rep_engaged, frequency_cap, capacity_full, approval_limit, in_holdout, in_legal_review, payment_failed.
- **Planted truths:** seven hidden customer types (power, steady, shallow, shelfware, project_based, champion_dependent, price_sensitive), four prospect types (browser, researcher, evaluator, locked_in), fit score, incumbent lock-in, champion exit hazard, usage decay, budget-cycle month, expansion headroom, a true uplift per (trigger, action), and sleeping dogs (about 5%) who react badly.
- **Controlled mess** (every item logged in `noise_log`): duplicate events, late and out-of-order events, wrong timestamps, missing fields, bots, tracking gaps, duplicate accounts (about 7%), users unmatched or wrongly matched to an account (about 8%), test accounts.
- **Leakage traps** (by design, see `docs/leakage_rules.md`): extract-time snapshot columns such as `accounts.status`, `accounts.arr_band`, `accounts.renewal_at`, `subscriptions.status` and `subscriptions.seats_active_band`. On the dev run `accounts.status` alone separates the churn label with AUC about 0.91.

## What this data CAN and CANNOT prove
See `docs/what_this_data_can_and_cannot_prove.md`. In short: the pipeline runs end to end on messy, late and duplicated data; labels are point-in-time safe and final only when old enough; guardrails and holdouts are enforced and logged; an uplift method can be tested against planted effects in the randomised period. It cannot show that real accounts behave like this, that any rate is right, or that a model that works here works on a real book.

## Validation (real results)
- `dev` (16,364 accounts, seed 7): 150 of 150 checks pass (`docs/validation_report_dev_15k.md`). Several checks use wide tolerances; some targets were rescaled where the answers contradict each other (see `docs/CHANGELOG.md`).
- `sample_1000` (1,107 accounts, seed 42): **135 of 150 checks pass; the 15 failures are small-sample effects** (only 29 customers, so churn, renewal, billing, holdout balance and uplift checks are noisy or empty). See `docs/validation_report_sample_1000.md`. The sample is for looking at the shape of the data, not for estimating anything.
- Tests: `python -m pytest tests` runs 12 B2B tests, 12 BFSI tests and 8 e-commerce tests (32 pass).
- `full` was generated (about 2 minutes) but the validator was killed for running out of memory on a 7 GB machine. No validation result exists for it.

## Known limits
See `docs/CHANGELOG.md`. Where the brief and the workbook conflicted, the workbook was followed. Where answers conflicted (window length, MQL to SQL rate, sales-cycle length, churn figures) the choice is recorded in the parameters report.
