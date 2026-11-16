# Q53 (leakage and point-in-time rules): our own answer

The e-commerce answers file had no usable answer to Q53, so this is OUR rule, not the client's. Replace it when the client answers.

1. Features for a decision at time t use only events with `occurred_at <= t` AND `ingested_at <= t` (what the system could actually see then). Never use `customers.orders_count`, `spend_band` or the consent columns: they are extract-time snapshots and leak the future.
2. A label for horizon H (7 or 30 days) counts orders created in (t, t+H]. A row is FINAL only when t + H + 45 days <= extract time, so late (up to ~3 days for GA4) and out-of-order events cannot change it afterwards.
3. Training uses only final rows. Rows inside the buffer are reported as not final and are never used.
4. Regime 1 (legacy) rows were sent to people likely to buy and carry no decision id or propensity. They must not be used to estimate uplift. Regime 2 rows (randomised policy with logged propensity, plus the 8% holdout) are the only causal source.
5. Hidden truth tables are for validation only. They live in `hidden/`, and feature, label and state-engine code must not import them (checked by an AST test).
