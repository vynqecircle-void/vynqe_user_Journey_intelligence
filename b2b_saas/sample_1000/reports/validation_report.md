# B2B SaaS validation report

SYNTHETIC data. 135/150 checks passed. Failed checks are listed first.


## FAILED (15)

| group | check | observed | expected | note |
|---|---|---|---|---|
| funnel | SQL to opportunity (converted) (Q9) | 0.4925 | 0.42 +/- 0.06 | 67 SQLs |
| funnel | every loss category appears | ['champion_left'] | [] |  |
| retention | annual logo churn MM (Q41) | 0.2381 | 0.1 +/- 0.04 | 21 cycles |
| retention | GRR per cycle MM (Q41, default 0.9) | 0.762 | 0.9 +/- 0.06 | per renewal cycle, ignoring price rises |
| retention | NRR per cycle MM (Q41, 1.08) | 0.892 | 1.08 +/- 0.10 | answers' NRR and GRR are not mutually consistent |
| retention | annual logo churn ENT (Q41) | 0.0 | 0.05 +/- 0.04 | 5 cycles |
| retention | NRR per cycle ENT (Q41, 1.18) | 1.035 | 1.18 +/- 0.10 | answers' NRR and GRR are not mutually consistent |
| retention | mid-market annual renewal split vs Q42 rescaled to Q41 churn of 10% (59.6/21.7/8.7/5.9/4.1) | {'as_is': 0.75, 'expanded': 0.05, 'contracted': 0.0, 'cancelled': 0.05, 'silent_lapse': 0.15} | rescaled targets within 8 points each (expansion also happens mid-term) | answers' split sums to 17% churn but Q41 says 10%: this pack follows Q41 |
| holdout | holdout balanced on hidden customer_type (max share gap) | 0.091 | < 0.03 |  |
| holdout | holdout balanced on hidden prospect_type (max share gap) | 0.0575 | < 0.03 |  |
| billing | late-paid share of invoice-method accounts (Q49: 25-35%) | 0.1923 | 0.3 +/- 0.08 |  |
| guardrails | do_nothing share where nothing is blocked (exploration 25%) | 0.1991 | 0.25 +/- 0.04 | 226 decisions |
| recovery | visible usage recovers the hidden customer type | 24 | >= 100 accounts | too few accounts with 120+ days of usage |
| uplift | estimated effect (action vs do_nothing, stratified by blocked set) has the planted sign in the randomised regime | {'cells': 2, 'sign_agreement': 0.5} | sign agreement > 0.6 over cells with planted |effect| >= 0.01 | estimate noise is large for small cells; labels differ slightly from the planted outcome |
| uplift | estimated and planted effects are positively correlated across (trigger, action) cells | nan | > 0.3 | lead_stall/email: est 0.166 planted 0.018 n=81; lead_stall/rep_outreach: est -0.008 planted 0.029 n=204 |

## PASSED (135)

| group | check | observed | expected | note |
|---|---|---|---|---|
| schema | accounts: columns match contract | 23 | 23 |  |
| schema | accounts: no nulls in non-nullable columns | [] | [] |  |
| schema | accounts: allowed values respected | [] | [] |  |
| schema | contacts: columns match contract | 14 | 14 |  |
| schema | contacts: no nulls in non-nullable columns | [] | [] |  |
| schema | contacts: allowed values respected | [] | [] |  |
| schema | events: columns match contract | 14 | 14 |  |
| schema | events: no nulls in non-nullable columns | [] | [] |  |
| schema | events: allowed values respected | [] | [] |  |
| schema | opportunities: columns match contract | 18 | 18 |  |
| schema | opportunities: no nulls in non-nullable columns | [] | [] |  |
| schema | opportunities: allowed values respected | [] | [] |  |
| schema | product_usage_daily: columns match contract | 9 | 9 |  |
| schema | product_usage_daily: no nulls in non-nullable columns | [] | [] |  |
| schema | product_usage_daily: allowed values respected | [] | [] |  |
| schema | subscriptions: columns match contract | 18 | 18 |  |
| schema | subscriptions: no nulls in non-nullable columns | [] | [] |  |
| schema | subscriptions: allowed values respected | [] | [] |  |
| schema | invoices: columns match contract | 13 | 13 |  |
| schema | invoices: no nulls in non-nullable columns | [] | [] |  |
| schema | invoices: allowed values respected | [] | [] |  |
| schema | actions: columns match contract | 34 | 34 |  |
| schema | actions: no nulls in non-nullable columns | [] | [] |  |
| schema | actions: allowed values respected | [] | [] |  |
| schema | state_history: columns match contract | 7 | 7 |  |
| schema | state_history: no nulls in non-nullable columns | [] | [] |  |
| schema | state_history: allowed values respected | [] | [] |  |
| schema | campaigns: columns match contract | 10 | 10 |  |
| schema | campaigns: no nulls in non-nullable columns | [] | [] |  |
| schema | campaigns: allowed values respected | [] | [] |  |
| schema | account_truth: columns match contract | 27 | 27 |  |
| schema | account_truth: no nulls in non-nullable columns | [] | [] |  |
| schema | account_truth: allowed values respected | [] | [] |  |
| schema | contact_truth: columns match contract | 7 | 7 |  |
| schema | contact_truth: no nulls in non-nullable columns | [] | [] |  |
| schema | contact_truth: allowed values respected | [] | [] |  |
| schema | opportunity_truth: columns match contract | 11 | 11 |  |
| schema | opportunity_truth: no nulls in non-nullable columns | [] | [] |  |
| schema | opportunity_truth: allowed values respected | [] | [] |  |
| schema | state_truth: columns match contract | 4 | 4 |  |
| schema | state_truth: no nulls in non-nullable columns | [] | [] |  |
| schema | state_truth: allowed values respected | [] | [] |  |
| schema | noise_log: columns match contract | 3 | 3 |  |
| schema | noise_log: no nulls in non-nullable columns | [] | [] |  |
| schema | noise_log: allowed values respected | [] | [] |  |
| schema | visible tables count (brief: 7 to 10) | 10 | 7-10 |  |
| privacy | no visible column named like a Never field (name, email, phone, address, ip, exact amount) | [] | [] |  |
| privacy | no raw email address in visible events or contacts | 0 | 0 |  |
| privacy | person_key is a 32-hex keyed hash | 1.0 | 1.0 |  |
| privacy | amounts are bands only | ['10-25k', '100-250k', '25-50k', '250k+', '5-10k', '50-100k', '<5k'] | bands |  |
| integrity | events.unit_id exists in accounts | 0 | 0 |  |
| integrity | opportunities.account_id exists in accounts | 0 | 0 |  |
| integrity | subscriptions.account_id exists in accounts | 0 | 0 |  |
| integrity | invoices.account_id exists in accounts | 0 | 0 |  |
| integrity | actions.unit_id exists in accounts | 0 | 0 |  |
| integrity | state_history.unit_id exists in accounts | 0 | 0 |  |
| integrity | contacts.account_id exists in accounts | 0 | 0 |  |
| integrity | product_usage_daily.account_id exists in accounts | 0 | 0 | wrong matches point to real accounts by design |
| integrity | invoices.subscription_id in subscriptions | 0 | 0 |  |
| integrity | account_id unique | 0 | 0 |  |
| integrity | opp_id unique | 0 | 0 |  |
| integrity | (subscription_id, version) unique | 0 | 0 |  |
| integrity | invoice_id unique | 0 | 0 |  |
| integrity | ingested_at >= occurred_at for every event | 0 | 0 |  |
| integrity | all events inside the window | 0 | 0 | wrong-timestamp noise shifts at most one day |
| integrity | source_event_id present and object:id:status shaped | 1.0 | 1.0 |  |
| distribution | segment share SMB (Q2) | 0.5971 | 0.6 +/- 0.02 |  |
| distribution | segment share MM (Q2) | 0.3059 | 0.3 +/- 0.02 |  |
| distribution | segment share ENT (Q2) | 0.0971 | 0.1 +/- 0.02 |  |
| distribution | customer type share power (Q24) | 0.0892 | 0.1 +/- 0.03 | hidden truth, all accounts |
| distribution | customer type share steady (Q24) | 0.302 | 0.3 +/- 0.03 | hidden truth, all accounts |
| distribution | customer type share shallow (Q24) | 0.2549 | 0.25 +/- 0.03 | hidden truth, all accounts |
| distribution | customer type share shelfware (Q24) | 0.1608 | 0.15 +/- 0.03 | hidden truth, all accounts |
| distribution | customer type share project_based (Q24) | 0.0706 | 0.08 +/- 0.03 | hidden truth, all accounts |
| distribution | customer type share champion_dependent (Q24) | 0.0657 | 0.07 +/- 0.03 | hidden truth, all accounts |
| distribution | customer type share price_sensitive (Q24) | 0.0569 | 0.05 +/- 0.03 | hidden truth, all accounts |
| distribution | prospect type share browser (Q24) | 0.507 | 0.5 +/- 0.03 |  |
| distribution | prospect type share researcher (Q24) | 0.247 | 0.25 +/- 0.03 |  |
| distribution | prospect type share evaluator (Q24) | 0.151 | 0.15 +/- 0.03 |  |
| distribution | prospect type share locked_in (Q24) | 0.095 | 0.1 +/- 0.03 |  |
| funnel | lead to MQL (contacted) (Q9) | 0.292 | 0.3 +/- 0.03 | 1007 leads; junk leads never progress, so this is after junk |
| funnel | MQL to SQL (qualified) (Q9) | 0.2279 | 0.25 +/- 0.04 | answers conflict 13% vs 38%; 294 MQLs |
| funnel | opportunity to won, closed new deals (Q9) | 0.3 | 0.25 +/- 0.05 | 30 closed deals |
| funnel | median sales cycle SMB days (Q10) | 34.0 | 30 +/- 35% | n=17; answers conflict 40-190 days |
| funnel | median sales cycle MM days (Q10) | 90.5 | 75 +/- 35% | n=8; answers conflict 40-190 days |
| funnel | median sales cycle ENT days (Q10) | 172.0 | 150 +/- 35% | n=5; answers conflict 40-190 days |
| retention | annual logo churn SMB (Q41) | 0.1515 | 0.15 +/- 0.04 | 33 cycles |
| retention | GRR per cycle SMB (Q41, default 0.82) | 0.833 | 0.82 +/- 0.06 | per renewal cycle, ignoring price rises |
| retention | NRR per cycle SMB (Q41, 0.97) | 0.922 | 0.97 +/- 0.10 | answers' NRR and GRR are not mutually consistent |
| retention | GRR per cycle ENT (Q41, default 0.93) | 0.94 | 0.93 +/- 0.06 | per renewal cycle, ignoring price rises |
| retention | involuntary share of churn (Q42: 20 to 40%) | 0.4 | 0.20-0.40 | 10 churn events |
| retention | silent lapse share of voluntary churn (Q42 mid-market 7 of 17 = 0.41; lower for monthly plans) | 0.5 | 0.20-0.50 | monthly plans cannot lapse |
| retention | win-back share of churned (Q53: 8-12%) | 0.1111 | 0.1 +/- 0.06 | 9 churned |
| distribution | holdout share of accounts (Q70: 5-10%) | 0.0814 | 0.08 +/- 0.015 |  |
| noise | duplicate accounts (Q74: 5-10%) | 0.0853 | 0.075 +/- 0.015 |  |
| noise | users unmatched to an account (Q37/75: 5-15%) | 0.0871 | 0.08 +/- 0.03 |  |
| noise | out-of-order share of all events (Q76: 1-3%) | 0.0156 | 0.02 +/- 0.015 |  |
| noise | late events share | 0.0176 | 0.02 +/- 0.01 |  |
| noise | every defect type is logged | ['bot', 'duplicate', 'duplicate_account', 'late', 'missing_field', 'out_of_order', 'test_account', 'tracking_gap', 'unmatched_user', 'wrong_timestamp', 'wrongly_matched'] | all injected types |  |
| noise | duplicate events share the source_event_id of an original | 1.0 | 1.0 |  |
| usage | Tue-Thu peak, weekend trough (Q36) | {0: 591663, 1: 620627, 2: 627528, 3: 608865, 4: 506425, 5: 62837, 6: 43324} | Tue..Thu > Mon, Sat/Sun < 25% of Tue |  |
| usage | holiday-week dip of 30-40% (Q36) | 0.738 | 0.5-0.8 (growth adds noise) |  |
| usage | every user-day has a login row when any feature row exists (sampled) | 1.0 | 1.0 | by construction; login is the first feature row of each active day |
| billing | disputed invoices (Q49: 2-4%) | 0.0248 | 0.03 +/- 0.012 |  |
| billing | card invoices with a failed first attempt (Q48: 3-5%) | 0.0438 | 0.04 +/- 0.015 | attempt_count > 1 means at least one retry |
| support | tickets per paying account per month (Q56: median 0.5-1.0, scaled by size) | 0.785 | 0.3-2.0 | sanity only; scaled by seats |
| billing | invoice statuses: captured majority, some failed, some refunded | {'captured': 0.963, 'created': 0.019, 'failed': 0.012, 'refunded': 0.006} | captured > 0.8, failed > 0 |  |
| guardrails | every blocked-action reason appears in the data | [] | [] | payment_failed and in_legal_review are rare: tiny presets may miss them |
| guardrails | no promotional action for a held-out account (regime 2) | 0 | 0 | 42 control decisions |
| guardrails | regulatory and transactional rows are never held out | 0 | 0 |  |
| guardrails | policy never chooses regulatory/transactional | 0 | 0 |  |
| guardrails | no marketing email without granted consent at decision time (visible consent history) | 0 of 136 | < 0.5% | a few violations can come from late or wrong-timestamp consent events |
| guardrails | no marketing email while an opportunity is open | 0 of 136 | < 1% | opportunity rows are extract-time snapshots; legacy and regime 2 both obey the hold |
| guardrails | no marketing email within 14 days of a renewal date | 0 of 136 | < 1% |  |
| guardrails | propensity logged for every randomised, non-held-out decision | 1.0 | 1.0 |  |
| guardrails | propensity in (0,1] | [0.15, 1.0] | (0,1] |  |
| regimes | regime 1 touches high-fit accounts more (planted selection bias) | {'high_fit': 0.311, 'low_fit': 0.192} | high > low + 0.03 |  |
| regimes | regime 2 touch rate does not depend on fit | 0.01 | < 0.04 |  |
| leakage | state_engine.py imports nothing from hidden/truth and never reads *_truth | [] | [] |  |
| leakage | labels.py imports nothing from hidden/truth and never reads *_truth | [] | [] |  |
| leakage | hidden folder separate from visible | ['account_truth.parquet', 'contact_truth.parquet', 'noise_log.parquet', 'opportunity_truth.parquet', 'state_truth.parquet'] | ['account_truth.parquet', 'contact_truth.parquet', 'opportunity_truth.parquet', 'state_truth.parquet', 'noise_log.parquet'] |  |
| leakage | no hidden-only column name appears in a visible table | [] | [] |  |
| labels | every final label has its horizon plus buffer inside the extract window | 0 | 0 |  |
| labels | some labels are not yet final | 0.12262357414448669 | > 0 |  |
| labels | label table has all six labels | {'churned_within_165d': {'size': 65, 'mean': 0.154}, 'deal_won_180d': {'size': 22, 'mean': 0.364}, 'expansion_won_120d': {'size': 30, 'mean': 0.033}, 'first_value_90d': {'size': 7, 'mean': 0.143}, 'lead_progressed_30d': {'size': 794, 'mean': 0.205}, 'resubscribed_180d': {'size': 5, 'mean': 0.0}} | 6 labels |  |
| leakage | trap exists: accounts.status (extract-time snapshot) separates churn labels almost perfectly | 0.964 | AUC > 0.85 (documented trap; feature code must not use it) | features must be built point-in-time from events, not from snapshot columns |
| state | visible-event state pairs found in truth (noise and duplicate accounts cost some) | 0.969 | 0.8-1.0 |  |
| state | all 9 states present | [] | [] |  |
| state | no subscription started before an account's first Lost stay (a lost deal may win later after cooling-off) | 0 | 0 |  |
| state | At-risk renewal starts within 120 days before (or 60 after) a term end | 1.0 | > 0.95 |  |
| state | flags present and parseable | 1.0 | 1.0 |  |
| state | actions carry the state at decision time | 0.975 | > 0.9 |  |
| uplift | planted win-probability shift is zero when do_nothing and positive for rep_outreach/exec_call on average | {'do_nothing': 0.0, 'rep_outreach': 0.067} | 0 and > 0 |  |
| uplift | sleeping dogs exist (reacts_badly share) | 0.0569 | 0.05 +/- 0.01 |  |
| uplift | planted negative effects exist for some types and actions | [('power', 'discount'), ('shelfware', 'discount'), ('project_based', 'email')] | at least one |  |