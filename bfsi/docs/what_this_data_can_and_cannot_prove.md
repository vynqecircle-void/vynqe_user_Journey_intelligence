# What this data can and cannot prove (BFSI pack)

## It CAN show
1. **The pipeline works end to end.** Ingest, identity stitching on a hashed phone, state engine, point-in-time labels, guardrails and holdout all run on a realistic mix of messy events.
2. **The code survives bad data.** Duplicates, missing fields, wrong timestamps, late and out-of-order events, bots, tracking gaps, shared phones and duplicate applications are injected at known rates and logged, so you can measure how much each one hurts.
3. **Labels are point-in-time safe.** The default label (90+ days past due within 12 months on book) is final only for loans 15+ months old. Funnel labels use a 45-day finality buffer. The visible default flag appears 1 to 5 days after the hidden 90-day date, never before.
4. **Leakage handling can be tested.** Snapshot columns that carry the future are planted on purpose (see `q54_leakage_rules.md`); a pipeline that uses them will look too good here and should be caught.
5. **Guardrails work.** No promotional message goes to a person without granted marketing consent (2 exceptions in 100,000 people, from late events), holdout people receive no optional action, regulatory messages are never held out, Account Aggregator consent never enables marketing, and every blocked action has a reason code.
6. **An uplift method can be tested against planted truth** in the randomised period (months 19 to 36). At 100,000 people the simple randomised comparison has the right sign for nudge, agent call, fee waiver and offer, and the EMI nudge lowers first-attempt EMI failure. The estimates are smaller than the planted means for some actions because borrowers who would have returned anyway dilute them.
7. **Legacy-period bias is visible.** Legacy sends go more to lower-risk applicants (78% against a 70% base), so a naive before/after comparison is misleading, as in the real situation.

## It CANNOT show
1. That real borrowers behave like this. Funnel rates, approval by band, repayment states, cure rates, prepayment, complaint rates and uplifts are settings, mostly grade C or D (see `parameters_report.md`).
2. That any default rate is right. Default by band is tuned to the Q26 placeholders; real lender vintages replace them.
3. That a model's performance here predicts performance on a real book. No model-performance claim is made anywhere in this package.
4. Anything about bureau data, collections strategy, legal recovery, restructuring or part-payments (not modelled).
5. Anything about the effect of regulation changes over time (no drift in rules is modelled beyond a small month-on-book drift).
6. Per-action uplift at small sizes. The 1,000-person sample has about 70 loans and too few stalled applications per action; use `dev`.
