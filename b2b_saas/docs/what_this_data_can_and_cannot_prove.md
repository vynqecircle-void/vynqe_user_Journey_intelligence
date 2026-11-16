# What this data can and cannot prove (B2B SaaS pack)

This data is **synthetic**. Every rate comes from a configured assumption, most of them grade C (our assumption) or D (placeholder). Nothing here is a measurement of a real company.

## It CAN show
- **The pipeline works end to end** on 10 visible tables with duplicates, late and out-of-order events, wrong timestamps, bots, duplicate accounts and users that do not match an account.
- **Point-in-time labels are safe.** Six labels (lead_progressed_30d, deal_won_180d, first_value_90d, churned_within_165d, expansion_won_120d, resubscribed_180d) are final only when the horizon plus a 45-day buffer fits inside the extract window. A validator check confirms no final label breaks this.
- **Guardrails and holdouts are enforced and logged.** Held-out accounts get no optional action in the randomised period; transactional and regulatory notices are never held out or chosen; consent, open-opportunity, open-ticket, frequency-cap, legal-review and payment-failure rules show up as reason codes. On the dev run all 12 reason codes appear.
- **The state engine works from events alone.** The reference engine (9 states, 7 flags) run on visible events agrees with hidden truth on about 97% of state pairs.
- **An uplift method can be tested.** The randomised period carries a logged propensity and a hidden planted effect per (trigger, action), including negative effects and sleeping dogs. On the dev run the estimated and planted effects agreed in sign in all 4 testable cells (correlation 0.94). Legacy-period rows are deliberately biased and must not be used for uplift.
- **Leakage detection works.** The snapshot columns are traps: a model that uses `accounts.status` will look excellent (AUC about 0.91 on the churn label) and be useless in production.
- **Hidden types are recoverable, imperfectly.** Visible usage recovers the hidden customer type with 60% cross-validated accuracy against a 30% majority baseline.

## It CANNOT show
- That real accounts behave like this. Funnel rates, sales cycles, churn, expansion, health-score behaviour and payment failure are assumptions from the answers file (grade C/D) and public benchmarks (grade B).
- That any win rate, churn rate, NRR or GRR is right. The answers file is internally inconsistent here: its NRR/GRR figures do not follow from its churn figures, and the mid-market renewal split sums to 17% churn where the annual churn figure says 10%. This pack follows the annual churn figures. Dev-run NRR per cycle runs 0.94 (SMB), 1.03 (mid-market), 1.09 (enterprise) against targets of 0.97, 1.08 and 1.18, so treat NRR as approximate.
- That a model or policy that works here will work on a real book. No model-performance claim is made anywhere in this package.
- That the planted uplift sizes are realistic. They are illustrative.
- Anything precise about retention. Even the `dev` preset has only about 352 customer accounts (882 labelled renewal cycles), so churn, NRR and GRR figures carry wide sampling error.
- Anything about small cells. In the dev run only 4 (trigger, action) cells have a large enough planted effect to test; per-cell uplift estimates are noisy.
- Anything about the `tiny` preset or the 1,000-account sample for retention or uplift: only 29 customers exist in the sample (about 100 new customers in `dev`).
- Anything about the `full` preset's quality: it was generated but not validated (the validator ran out of memory).
