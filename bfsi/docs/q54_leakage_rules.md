# Q54 (leakage and point-in-time rules): rules for this pack

Q54 in the answers file lists what leaks the future: final days past due, write-off flag, closure status, final risk band, later mandate cancellations, and anything dated after the prediction date. The rules below turn that into practice. They are OUR rules; replace them when the client confirms.

1. Features for a decision at time t use only events with `occurred_at <= t` AND `ingested_at <= t` (what the system could see then). Core banking is a daily extract and mandate results arrive one to two days late, so `ingested_at` matters.
2. Never use these extract-time snapshot columns as features: `loans.account_status`, `loans.closed_at`, `loans.closure_type`, `loans.defaulted_at`, `loans.lender_band_latest`, `borrowers.applications_count`, `borrowers.loans_count`, the three consent columns, `applications.stage` and `applications.stage_changed_at`. Use the event history instead (`events`: record_status_changed, consent_change, risk-band update events).
3. `loans.lender_band_latest` is deliberately contaminated: it moves to band 4 after default. The band at decision time is `applications.risk_band` (and the risk-band event).
4. Default label: 90+ days past due within 12 months of disbursal, built only for loans 15+ months old at the extract date. Younger loans are not final and are never used for training. The visible flag `defaulted_at` is for reference only, not a label: it is set 1 to 5 days after the 90th day.
5. Funnel and nudge labels (for example "application resumes within 7 or 30 days") count events in (t, t+H]. A row is FINAL only when t + H + 45 days is on or before the extract time.
6. Months 1 to 18 (legacy) rows carry no decision id or propensity and were sent to a biased group. They must not be used to estimate uplift. Months 19 to 36 rows (randomised policy with logged propensity, plus the 8% holdout) are the only causal source. `actions.decision_id` attribution on applications is set only when the person clicked or was called after a decision.
7. Account Aggregator consent is a data-sharing consent. It never counts as marketing consent.
8. Hidden truth tables live in `hidden/`. Feature, label and state-engine code must not import them (an AST test checks this).
