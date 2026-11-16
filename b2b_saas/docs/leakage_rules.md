# Leakage and point-in-time rules (B2B SaaS)

These are OUR rules, written because the answers file had no usable answer on leakage. Replace them when the client answers.

1. Features for a decision at time t use only events with `occurred_at <= t` AND `ingested_at <= t` (what the system could see then). Never use extract-time snapshot columns: `accounts.status`, `accounts.arr_band`, `accounts.renewal_at`, `subscriptions.status`, `subscriptions.status_changed_at`, `subscriptions.seats_active_band`, `subscriptions.cancel_requested`.
2. A label with horizon H is FINAL only when t + H + 45 days <= extract time. Rows inside the buffer are not final and are never used for training.
3. `deal_won_180d` is linked through `opp_id`; `resubscribed_180d` through the `returning` flag on the subscription event.
4. Regime 1 (legacy) rows carry no decision id or propensity and were targeted by fit and ARR. They must not be used to estimate uplift. Regime 2 rows (randomised, logged propensity, 8% whole-account holdout) can be.
5. Hidden truth tables live in `hidden/` and are for validation only. Feature, state and label code must not import or read them (checked by an AST test and a validator check).
6. Usage rows for large accounts are sampled (cap of 40 named users), so per-user counts are not exact.
7. Duplicate accounts and unmatched users exist on purpose; deduplicate with `source_event_id` and `person_key`, never with truth tables.
