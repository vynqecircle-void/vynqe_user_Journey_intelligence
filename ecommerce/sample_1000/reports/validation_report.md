# Validation report

SYNTHETIC data. 87/88 checks passed. Failed checks are listed first.


## FAILED (1)

| group | check | observed | expected | note |
|---|---|---|---|---|
| uplift | randomised estimate per action vs planted mean uplift (est, std err, planted mean, n) | {'reminder': (0.009, 0.013, 0.019, 1635), 'discount': (0.038, 0.017, 0.037, 978), 'free_shipping': (0.043, 0.014, 0.042, 1556), 'bundle': (-0.001, 0.012, 0.023, 1709)} | same sign; estimates noisy at small n | Lift also includes the cart-trigger multiplier (x2) for cart rows |

## PASSED (87)

| group | check | observed | expected | note |
|---|---|---|---|---|
| schema | customers: columns match contract | 24 | 24 |  |
| schema | customers: no nulls in non-nullable columns | [] | [] |  |
| schema | customers: allowed values respected | [] | [] |  |
| schema | events: columns match contract | 14 | 14 |  |
| schema | events: no nulls in non-nullable columns | [] | [] |  |
| schema | events: allowed values respected | [] | [] |  |
| schema | orders: columns match contract | 30 | 30 |  |
| schema | orders: no nulls in non-nullable columns | [] | [] |  |
| schema | orders: allowed values respected | [] | [] |  |
| schema | payments: columns match contract | 10 | 10 |  |
| schema | payments: no nulls in non-nullable columns | [] | [] |  |
| schema | payments: allowed values respected | [] | [] |  |
| schema | tickets: columns match contract | 12 | 12 |  |
| schema | tickets: no nulls in non-nullable columns | [] | [] |  |
| schema | tickets: allowed values respected | [] | [] |  |
| schema | actions: columns match contract | 32 | 32 |  |
| schema | actions: no nulls in non-nullable columns | [] | [] |  |
| schema | actions: allowed values respected | [] | [] |  |
| schema | state_history: columns match contract | 7 | 7 |  |
| schema | state_history: no nulls in non-nullable columns | [] | [] |  |
| schema | state_history: allowed values respected | [] | [] |  |
| schema | campaigns: columns match contract | 10 | 10 |  |
| schema | campaigns: no nulls in non-nullable columns | [] | [] |  |
| schema | campaigns: allowed values respected | [] | [] |  |
| schema | category_value: columns match contract | 5 | 5 |  |
| schema | category_value: no nulls in non-nullable columns | [] | [] |  |
| schema | category_value: allowed values respected | [] | [] |  |
| schema | person_truth: columns match contract | 24 | 24 |  |
| schema | person_truth: no nulls in non-nullable columns | [] | [] |  |
| schema | person_truth: allowed values respected | [] | [] |  |
| schema | order_truth: columns match contract | 8 | 8 |  |
| schema | order_truth: no nulls in non-nullable columns | [] | [] |  |
| schema | order_truth: allowed values respected | [] | [] |  |
| schema | state_truth: columns match contract | 4 | 4 |  |
| schema | state_truth: no nulls in non-nullable columns | [] | [] |  |
| schema | state_truth: allowed values respected | [] | [] |  |
| schema | noise_log: columns match contract | 3 | 3 |  |
| schema | noise_log: no nulls in non-nullable columns | [] | [] |  |
| schema | noise_log: allowed values respected | [] | [] |  |
| integrity | orders.unit_id in customers | 0 | 0 |  |
| integrity | payments.order_id in orders (when set) | 0 | 0 |  |
| integrity | events.unit_id in customers | 0 | 0 |  |
| integrity | actions/tickets/state_history unit_id in customers | 0 | 0 |  |
| integrity | order_truth 1:1 with orders | 2448 | 2448 |  |
| integrity | person_truth 1:1 with customers | 1000 | 1000 |  |
| integrity | unique keys (orders, tickets, actions, payments) | 0 | 0 |  |
| integrity | state_history stays do not overlap | 0 | 0 |  |
| integrity | delivered_at after created_at | True | True |  |
| privacy | no raw phone/email in event properties | 0 | 0 |  |
| privacy | no raw-PII or exact-amount column names in visible tables | [] | [] |  |
| privacy | visible amounts are bands only | ['0-500', '1000-1500', '1500-2500', '2500-5000', '500-1000', '5000+'] | bands |  |
| leakage | no hidden-table column names in visible tables | [] | [] |  |
| leakage | feature/label/state-engine modules import no hidden code | [] | [] |  |
| distribution | COD share of orders | 0.594 | ~0.57 (workbook 57%) |  |
| distribution | RTO rate among shipped COD orders | 0.259 | 20-30% typical COD (flag: grade C) | Above the middle of the range; tune in config |
| distribution | RTO rate prepaid (should be far lower than COD) | 0.031 | < 0.129 |  |
| distribution | refund share of shipped orders | 0.147 | 5-15% (grade C) |  |
| distribution | payment attempt success upi | 0.944 | 0.965 |  |
| distribution | payment attempt success card | 0.854 | 0.87 |  |
| distribution | payment attempt success netbanking | 0.886 | 0.9 |  |
| distribution | payment attempt success wallet | 0.912 | 0.93 |  |
| distribution | share of customers with >=1 order | 0.724 | type-driven (one_time 40% largest) |  |
| distribution | tickets per order | 0.158 | 0.05-0.25 |  |
| distribution | events per customer | 245.2 | 180-420 (research range) |  |
| distribution | largest hidden type is one_time_buyer | one_time_buyer | one_time_buyer |  |
| distribution | sessions per customer (identified) | 28.3 | 20-46 (research range, all traffic) |  |
| noise | duplicate rate vs config | 0.0189 | 0.02 |  |
| noise | late rate vs config | 0.0192 | 0.02 |  |
| noise | missing_field rate vs config | 0.0089 | 0.01 |  |
| noise | wrong_timestamp rate vs config | 0.0045 | 0.005 |  |
| noise | bot and tracking-gap defects present | [5478, 892] | >0 |  |
| noise | duplicates are visible as repeated source_event_id | 9270 | >0 |  |
| noise | GA4 median ingest lag (hours; daily export next morning) | 19.7 | 6-30h |  |
| noise | webhook median ingest lag (seconds) | 32.6 | <120s |  |
| guardrails | every reason code appears at least once | [] | [] | Missing codes need more data or a rule tweak |
| guardrails | no executed action was also blocked (except approval -> task) | 0 | 0 |  |
| guardrails | holdout-control customers never receive an action | 0 | 0 |  |
| guardrails | holdout share | 0.077 | 0.08 |  |
| guardrails | promotional sends with no granted consent at send time (visible events; late/dup noise may add a few) | 16 | ~0 |  |
| recoverability | hidden type predicted from visible behaviour (3-fold accuracy) | 0.561 | > majority 0.364 but < 0.95 (not trivial) | Shows types are learnable but not perfectly |
| recoverability | loyal buyers order more than one-time buyers | {'deal_seeker': 4.31, 'festival_only_buyer': 0.78, 'gift_buyer': 2.09, 'loyal_buyer': 8.06, 'one_time_buyer': 1.3, 'window_shopper': 1.14} | loyal > one_time |  |
| uplift | planted uplift differs by hidden type | {'uplift_discount': {'deal_seeker': 0.079, 'festival_only_buyer': 0.032, 'gift_buyer': 0.029, 'loyal_buyer': 0.019, 'one_time_buyer': 0.019, 'window_shopper': 0.056}, 'uplift_free_shipping': {'deal_seeker': 0.061, 'festival_only_buyer': 0.018, 'gift_buyer': 0.037, 'loyal_buyer': 0.051, 'one_time_buyer': 0.028, 'window_shopper': 0.047}} | deal_seeker discount highest |  |
| uplift | sleeping dogs exist (negative planted uplift) | 0.049 | 0.04 |  |
| labels | finality buffer leaves some rows non-final near the window end | 0.746 | <1 |  |
| labels | no row marked final inside the buffer | 2026-09-13 05:10:45.891000+00:00 | >= end - 52d |  |
| state | visible-event state matches truth (unit,state pairs found) | 0.984 | < 1 (noise and identity splits cost some) |  |
| state | all six states present | ['Active', 'New customer', 'New visitor', 'Re-engage', 'Reactivate', 'Retarget'] | ['Active', 'New customer', 'New visitor', 'Re-engage', 'Reactivate', 'Retarget'] |  |