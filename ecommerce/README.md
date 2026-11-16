> Part of the combined package. Run all commands from the root folder (where `vynqe_synth/` is). `docs/` and `sample_1000/` below are inside this pack's folder.

# vynqe_synth: synthetic data generator (e-commerce pack, v0.1.0)

**This data is synthetic.** Every number comes from a configured assumption (see `docs/parameters_report.md`). It is for building and testing the Customer Lifecycle Intelligence pipeline. **It makes no claim about how any model will perform on real customers**, and nothing here should be quoted as evidence of real-world uplift.

## Run
```
pip install pyarrow pyyaml pandas numpy scikit-learn pytest
python -m vynqe_synth generate --pack ecommerce --preset tiny --seed 42 --out ./out [--csv]
python -m vynqe_synth validate --out ./out
python -m pytest tests
```
Presets (`vynqe_synth/config/presets.yaml`): `tiny` 1,000 customers (~8 s), `dev` 10,000 (~80 s, ~2.6M events, recommended), `full` 100,000 (not run here; expect ~15 minutes and ~26M events). Same seed gives byte-identical data.

## Output
- `visible/` (9 tables): customers, events, orders, payments, tickets, actions, state_history, campaigns, category_value. Sessions are derived from page views (30-minute rule), not stored.
- `hidden/` (4 tables, validation only): person_truth (true customer type, planted uplift per action), order_truth (exact amounts), state_truth, noise_log. Feature and model code must never read these.
- `schemas/` JSON contracts; `reports/` row counts and validation results.
- No raw phone, email, name, address or exact amount in visible tables: keyed hashes and amount bands only.

## What the data contains
Two periods: first 365 days a legacy biased-targeting regime; then a randomised regime with logged propensities, guardrails and an 8% holdout. Planted truths: six hidden customer types, per-type true uplift for each action, sleeping dogs (negative responders), fatigue, pull-forward after discounts. Controlled mess: duplicates, missing fields, wrong timestamps, late and out-of-order arrivals, bots, tracking gaps, shared phones, split identities.

## What this data CAN prove
The pipeline works end to end; the code handles messy, late and duplicated data; labels are point-in-time safe; an uplift method recovers the planted per-action effects from the randomised period (the validator shows the naive estimate recovers them within about 1 point at 10,000 customers); guardrails are enforced and logged.

## What it CANNOT prove
That real customers behave like this; that any specific lift, margin, RTO or return rate is right; that a model that works here works in production. Most parameters are grade C or D assumptions. The 1,000-customer sample is too small to recover per-action uplift reliably (its validator run fails that one check: 87/88).

## Known limits and deviations
See `docs/CHANGELOG.md` and the validation report. Notably: 4 hidden tables (order_truth added); stateless discount-budget proxy; `expected_value` and uplift in actions are empty (no trained model); workbook extensions flagged in `schemas/`; leakage rules in `docs/q53_leakage.md` are our own; ~0.1% of promotional sends show no granted consent in visible events (believed timestamp noise, not verified). Where the brief and the workbook conflicted, the workbook was followed.
