> Part of the combined package. Run all commands from the root folder (where `vynqe_synth/` is). `docs/` and `sample_1000/` below are inside this pack's folder.

# vynqe_synth: synthetic data generator (BFSI personal-loan pack, v0.1.0)

**This data is synthetic.** Every number comes from a configured assumption (see `docs/parameters_report.md`). It is for building and testing the Customer Lifecycle Intelligence pipeline. **It makes no claim about how any model will perform on real borrowers**, and nothing here should be quoted as evidence of real-world uplift, default rates or approval rates.

The code folder also contains the e-commerce pack (delivered earlier) because both packs share `vynqe_synth/core`. This package is the BFSI delivery.

## Run
```
pip install pyarrow pyyaml pandas numpy scikit-learn pytest
python -m vynqe_synth generate --pack bfsi --preset tiny --seed 42 --out ./out [--csv]
python -m vynqe_synth validate --out ./out
python -m pytest tests
```
Presets (`vynqe_synth/config/presets.yaml`, section `bfsi`):

| Preset | People | Time | Events | Notes |
|---|---|---|---|---|
| `tiny` | 2,000 | about 10 s | about 110k | smoke test; too small to recover per-action uplift |
| `dev` | 100,000 | about 2.5 min | about 4.9M | recommended; all 125 validation checks pass |
| `full` | 400,000 | not run | about 20M (estimate) | expect about 10 minutes |

Use `--n 1000` to override the count (that is how `sample_1000/` was made). The same seed gives byte-identical data. The unit is a **person** (a lead the lender can see), not a loan: about 7% of people reach disbursal, so 100,000 people gives about 8,000 loans.

## Output
- `visible/` (10 tables): borrowers, events, applications, application_steps, loans, emi_payments, service_cases, actions, state_history, campaigns. `docs/table_dictionary.md` lists every column; `docs/BFSI_DATASET_FULL_REPORT_100k.md` is the full report for 100,000 people.
- `hidden/` (4 tables, validation only): person_truth (true borrower type, income, true risk, planted uplift per action), application_truth (exact amounts, days-past-due path, true default label), state_truth, noise_log. Feature and model code must never read these (checked by a test).
- `schemas/` JSON contracts; `reports/` row counts.
- No raw phone, email, name, address, income, days past due or exact amount in visible tables: keyed hashes and amount bands only. Visible risk is the lender's own band 1 to 4, never bureau data.
- The 16 tables in the brief were merged into 10 visible tables (stage history, leads, consent history and risk-band updates live in `events`; KYC, Account Aggregator, e-sign and mandate live in `application_steps`; messages, tasks and agent calls live in `actions`).

## What the data contains
- **Journey:** lead, application, KYC, Account Aggregator data-sharing consent (never treated as marketing consent), decision (lender band), offer and key fact statement, e-sign and mandate, disbursal, monthly EMIs, collections, complaints and disputes, top-up after 6 on-time EMIs, win-back after closure.
- **Two periods:** months 1 to 18 use legacy biased targeting (no decision id, no propensity); months 19 to 36 use a randomised exploration policy with logged propensity (25% do_nothing, the rest uniform over allowed actions), guardrail reason codes and an 8% salted-hash holdout. Mandatory EMI reminders, pre-debit notices, statements and key fact statements are never held out and never chosen by the policy.
- **Planted truths:** six hidden borrower types (not static: 10% change), a true uplift for each of five actions (nudge, agent call, fee waiver, offer, EMI nudge), sleeping dogs (4%), fatigue, repayment stress that persists month to month.
- **Controlled mess** (every item logged in `noise_log`): duplicates, missing fields, wrong timestamps, late and out-of-order events, bots, tracking gaps, shared phones, split identities, duplicate applications, mandate results arriving one to two days late, core banking as a daily extract.
- **Leakage traps** (by design, see `docs/q54_leakage_rules.md`): extract-time snapshot columns such as `loans.lender_band_latest`, `loans.account_status`, `borrowers.loans_count` and the consent columns.

## What this data CAN prove
See `docs/what_this_data_can_and_cannot_prove.md`. In short: the pipeline runs end to end on messy, late and duplicated data; labels are point-in-time safe and final only when old enough; guardrails and holdouts are enforced and logged; an uplift method can be tested against planted effects in the randomised period.

## What it CANNOT prove
That real borrowers behave like this; that any approval, default, roll or cure rate is right; that a model that works here works on a real book. Most parameters are grade C or D assumptions.

## Validation (real results)
- `dev` (100,000 people): 125 of 125 checks pass (`docs/validation_report_dev_100k.md`). Several checks use wide tolerances; the weak spots are listed in `docs/CHANGELOG.md`.
- `sample_1000` (1,000 people): 118 of 123 checks pass; the 5 failures are small-sample effects (71 loans, so default by band and the mandate rate are noisy; one reason code never fires; 4 marketing messages during open cases). See `docs/validation_report_sample_1000.md`. The sample is for looking at the shape of the data, not for estimating effects.
- Tests: `python -m pytest tests` runs 12 BFSI tests and the 8 e-commerce tests.

## Known limits
See `docs/CHANGELOG.md`. Where the brief and the workbook conflicted, the workbook was followed. Where answers conflicted (Q2 24 vs 36 months; Q31 vs Q33 bounce rate; RBI buckets vs vendor collections buckets) the choice is recorded in the parameters report.
