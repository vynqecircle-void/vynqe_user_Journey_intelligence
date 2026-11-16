# B2B SaaS synthetic dataset: full report (dev run, 16,364 accounts)

**SYNTHETIC DATA.** Every number below is measured on the generated data (`dev` preset, seed 7) and reflects configured assumptions, not any real company. No model-performance claim is made. Hidden-table figures are for validation only.

## 1. At a glance

- Accounts: 16,364 (250 base customers at the start + 15,000 new leads, plus duplicate and test accounts from noise). Contacts: 42,850. Events: 324,287. Daily usage rows: 2,874,310.
- Window: 2024-05-01 to 2026-10-31 (30 months). Months 1-15 legacy targeting, months 16-30 randomised policy with 8% whole-account holdout.
- Customer accounts (with a subscription): 352; subscription rows 1,172; invoices 3,380; opportunities 1,484; actions 18,487.
- Validator: 150 of 150 checks pass (section 8).
- **Main limit:** only about 0.7% of new leads become customers, so customer-level statistics (churn, NRR, uplift) rest on about 350 accounts.

## 2. How the data is built

1. One simulator per account draws hidden traits (prospect or customer type, fit, lock-in, champion exit hazard, usage decay, budget month, expansion headroom, sleeping-dog flag) and then plays the account's life: web sessions, lead, MQL, SQL, opportunity, e-sign, trial, subscription, billing, usage, support, health, renewal, expansion, contraction, churn, win-back.
2. Every decision (lead stall, opportunity stall, onboarding, renewal risk, expansion, win-back) picks an action under guardrails. Outcomes use a pre-drawn uniform per decision, so the planted uplift equals the probability shift exactly (`p_win_true` and `p_win_no_action` in hidden tables).
3. Churn is calibrated per segment by Monte Carlo to the answers' annual logo churn (15/10/5%); involuntary churn comes from card failure with Stripe-style retries; silent lapse only on annual plans.
4. Noise (duplicates, late, out-of-order, wrong timestamps, missing fields, bots, duplicate accounts, unmatched users, test accounts) is injected afterwards and logged in `noise_log`.
5. The reference state engine and the labels run on visible events only.

## 3. The dataset in numbers

### 3.1 Accounts

Segment mix:

| Value | Count | Share |
|---|---:|---:|
| SMB | 9,890 | 60.4% |
| MM | 4,832 | 29.5% |
| ENT | 1,642 | 10.0% |

Source:

| Value | Count | Share |
|---|---:|---:|
| inbound | 5,467 | 33.4% |
| outbound | 4,059 | 24.8% |
| partner | 1,962 | 12.0% |
| referral | 1,925 | 11.8% |
| event | 1,655 | 10.1% |
| competitor_displacement | 1,296 | 7.9% |

Region:

| Value | Count | Share |
|---|---:|---:|
| north_america | 5,756 | 35.2% |
| india | 4,875 | 29.8% |
| emea | 3,242 | 19.8% |
| apac | 2,491 | 15.2% |

Industry band:

| Value | Count | Share |
|---|---:|---:|
| software_it | 4,612 | 28.2% |
| manufacturing_retail | 3,688 | 22.5% |
| other_services | 3,239 | 19.8% |
| financial_services | 2,787 | 17.0% |
| healthcare | 2,038 | 12.5% |

Employee band:

| Value | Count | Share |
|---|---:|---:|
| 51-200 | 7,204 | 44.0% |
| 1-50 | 5,022 | 30.7% |
| 201-1000 | 3,316 | 20.3% |
| 1001+ | 822 | 5.0% |

Account status (EXTRACT-TIME snapshot, leakage trap):

| Value | Count | Share |
|---|---:|---:|
| prospect | 15,707 | 96.0% |
| lost | 304 | 1.9% |
| customer | 255 | 1.6% |
| churned | 98 | 0.6% |

Regime first seen:

| Value | Count | Share |
|---|---:|---:|
| randomised_holdout | 8,820 | 53.9% |
| legacy_targeting | 7,544 | 46.1% |

Holdout group:

| Value | Count | Share |
|---|---:|---:|
| treated | 15,078 | 92.1% |
| control | 1,286 | 7.9% |

### 3.2 Contacts

Role:

| Value | Count | Share |
|---|---:|---:|
| champion | 16,364 | 38.2% |
| end_user | 11,038 | 25.8% |
| technical | 10,736 | 25.1% |
| economic_buyer | 4,712 | 11.0% |

Email consent (snapshot):

| Value | Count | Share |
|---|---:|---:|
| unknown | 28,002 | 65.3% |
| granted | 13,689 | 31.9% |
| withdrawn | 1,159 | 2.7% |

Lead status:

| Value | Count | Share |
|---|---:|---:|
| nan | 27,850 | 65.0% |
| lost | 13,276 | 31.0% |
| new | 858 | 2.0% |
| converted | 473 | 1.1% |
| contacted | 313 | 0.7% |
| qualified | 80 | 0.2% |

Personal-email share: 12.0%. Contacts who left their account: 0.4%. Product users: 17.1%. Contacts per account (mean): 2.6.

### 3.3 Funnel and opportunities

Lead statuses (all leads):

| Value | Count | Share |
|---|---:|---:|
| lost | 13,276 | 88.5% |
| new | 858 | 5.7% |
| converted | 473 | 3.2% |
| contacted | 313 | 2.1% |
| qualified | 80 | 0.5% |

Opportunity type:

| Value | Count | Share |
|---|---:|---:|
| new | 741 | 49.9% |
| renewal | 432 | 29.1% |
| expansion | 302 | 20.4% |
| win_back | 9 | 0.6% |

Stage at end:

| Value | Count | Share |
|---|---:|---:|
| closed_won | 902 | 60.8% |
| closed_lost | 347 | 23.4% |
| discovery | 174 | 11.7% |
| evaluation | 23 | 1.5% |
| proposal | 20 | 1.3% |
| negotiation | 18 | 1.2% |

Loss category (lost opportunities):

| Value | Count | Share |
|---|---:|---:|
| competitor | 124 | 35.7% |
| no_decision | 102 | 29.4% |
| price | 53 | 15.3% |
| timing | 33 | 9.5% |
| product_gap | 22 | 6.3% |
| champion_left | 13 | 3.7% |

New-business sales cycle (deals created inside the window and closed), days:

| Segment | n | median | p25 | p75 |
|---|---:|---:|---:|---:|
| ENT | 33 | 171 | 120 | 271 |
| MM | 131 | 95 | 66 | 127 |
| SMB | 260 | 36 | 24 | 55 |

Win rate of closed new deals created inside the window (n=424): 24.3%. Legal-review share: 6.7%. Competitor flag: 22.8%. Amount bands:

| Value | Count | Share |
|---|---:|---:|
| 5-10k | 288 | 19.4% |
| 10-25k | 273 | 18.4% |
| 50-100k | 259 | 17.5% |
| 25-50k | 232 | 15.6% |
| 100-250k | 190 | 12.8% |
| <5k | 166 | 11.2% |
| 250k+ | 76 | 5.1% |

E-sign status (blank = no e-sign step):

| Value | Count | Share |
|---|---:|---:|
| completed | 885 | 59.6% |
| (none) | 556 | 37.5% |
| declined | 28 | 1.9% |
| voided | 15 | 1.0% |

### 3.4 Subscriptions and billing

Plan:

| Value | Count | Share |
|---|---:|---:|
| team | 517 | 44.1% |
| starter | 362 | 30.9% |
| business | 225 | 19.2% |
| enterprise | 68 | 5.8% |

Billing interval:

| Value | Count | Share |
|---|---:|---:|
| annual | 855 | 73.0% |
| monthly | 317 | 27.0% |

Subscription status (EXTRACT-TIME snapshot, leakage trap):

| Value | Count | Share |
|---|---:|---:|
| expired | 790 | 67.4% |
| active | 300 | 25.6% |
| cancelled | 75 | 6.4% |
| past_due | 5 | 0.4% |
| paused | 2 | 0.2% |

Collection method:

| Value | Count | Share |
|---|---:|---:|
| charge_automatically | 757 | 64.6% |
| send_invoice | 415 | 35.4% |

Auto-renew flag: 70.6%. Versions per subscription (max): 6.

Invoice status:

| Value | Count | Share |
|---|---:|---:|
| captured | 3,221 | 95.3% |
| created | 103 | 3.0% |
| failed | 28 | 0.8% |
| refunded | 28 | 0.8% |

Invoice error codes (failed attempts):

| Value | Count | Share |
|---|---:|---:|
| insufficient_funds | 37 | 35.9% |
| expired_card | 33 | 32.0% |
| card_declined | 33 | 32.0% |

Invoices with more than one attempt: 3.0%. Disputed: 3.08%. Renewal invoices: 19.0%.

### 3.5 Product usage

Rows 2,874,310; accounts with usage 475; users (person keys) 6,261. Unmatched usage rows (no account): 8.3%.

Feature mix (share of rows):

| Value | Count | Share |
|---|---:|---:|
| login | 1,047,665 | 36.4% |
| dashboard | 564,524 | 19.6% |
| report | 397,811 | 13.8% |
| api_call | 232,675 | 8.1% |
| admin_settings | 232,413 | 8.1% |
| export | 195,407 | 6.8% |
| invite_sent | 81,469 | 2.8% |
| integration_connected | 81,318 | 2.8% |
| seat_added | 41,028 | 1.4% |

Source system:

| Value | Count | Share |
|---|---:|---:|
| amplitude | 1,621,502 | 56.4% |
| pendo | 1,252,808 | 43.6% |

Share of rows by weekday (Mon..Sun): 19.3%, 20.3%, 20.4%, 19.9%, 16.6%, 2.1%, 1.4%

### 3.6 Actions, decisions and guardrails

Record kind:

| Value | Count | Share |
|---|---:|---:|
| decision | 8,609 | 46.6% |
| legacy_touch | 7,103 | 38.4% |
| transactional | 2,775 | 15.0% |

Regime:

| Value | Count | Share |
|---|---:|---:|
| randomised_holdout | 10,082 | 54.5% |
| legacy_targeting | 8,405 | 45.5% |

Trigger:

| Value | Count | Share |
|---|---:|---:|
| lead_stall | 13,471 | 72.9% |
| invoice | 2,184 | 11.8% |
| risk | 1,196 | 6.5% |
| renewal_notice | 591 | 3.2% |
| expansion | 523 | 2.8% |
| opp_stall | 416 | 2.3% |
| winback | 66 | 0.4% |
| onboarding | 40 | 0.2% |

Chosen action:

| Value | Count | Share |
|---|---:|---:|
| do_nothing | 7,971 | 43.1% |
| rep_outreach | 5,503 | 29.8% |
| regulatory | 2,719 | 14.7% |
| email | 1,600 | 8.7% |
| discount | 386 | 2.1% |
| csm_task | 136 | 0.7% |
| exec_call | 116 | 0.6% |
| transactional | 56 | 0.3% |

Randomised-period chosen action:

| Value | Count | Share |
|---|---:|---:|
| rep_outreach | 4,197 | 48.8% |
| do_nothing | 2,674 | 31.1% |
| email | 1,261 | 14.6% |
| discount | 298 | 3.5% |
| csm_task | 98 | 1.1% |
| exec_call | 81 | 0.9% |

Block reasons seen in reason_codes:

| Reason | Count |
|---|---:|
| unknown_consent | 8,557 |
| capacity_full | 1,095 |
| approval_limit | 968 |
| in_holdout | 623 |
| rep_engaged | 579 |
| open_opportunity | 416 |
| frequency_cap | 387 |
| no_consent | 274 |
| open_ticket | 262 |
| in_legal_review | 188 |
| payment_failed | 10 |
| renewal_within_14d | 2 |

Propensity logged: legacy 0.0%, randomised 92.8%. Held-out accounts' decisions are all do_nothing in the randomised period.

Message final status:

| Value | Count | Share |
|---|---:|---:|
| delivered | 3,004 | 68.7% |
| opened | 1,108 | 25.3% |
| clicked | 196 | 4.5% |
| bounced | 67 | 1.5% |

CS task status:

| Value | Count | Share |
|---|---:|---:|
| done | 4,450 | 72.5% |
| ignored | 1,089 | 17.7% |
| overridden | 602 | 9.8% |

### 3.7 Events

Event type:

| Value | Count | Share |
|---|---:|---:|
| page_view | 145,728 | 44.9% |
| record_status_changed | 65,163 | 20.1% |
| record_created | 51,836 | 16.0% |
| decision_made | 15,775 | 4.9% |
| identify | 15,055 | 4.6% |
| consent_change | 14,872 | 4.6% |
| message_status | 10,295 | 3.2% |
| link_click | 2,934 | 0.9% |
| outcome_confirmed | 2,629 | 0.8% |

Source system:

| Value | Count | Share |
|---|---:|---:|
| ga4 | 145,728 | 44.9% |
| salesforce | 41,267 | 12.7% |
| hubspot | 38,197 | 11.8% |
| zendesk | 35,581 | 11.0% |
| decision_service | 15,775 | 4.9% |
| okta | 13,238 | 4.1% |
| klaviyo | 10,295 | 3.2% |
| stripe | 8,124 | 2.5% |
| gainsight | 7,938 | 2.4% |
| cvent | 3,036 | 0.9% |
| docusign | 2,107 | 0.6% |
| google_ads | 1,945 | 0.6% |
| meta_ads | 989 | 0.3% |
| amplitude | 67 | 0.0% |

Ingest lag (hours): median 0.03, p95 29.2, share of negative lag (timestamp errors) 0.00%.

### 3.8 Lifecycle states (state engine output)

State rows by state:

| Value | Count | Share |
|---|---:|---:|
| Lead | 15,142 | 88.6% |
| Active | 600 | 3.5% |
| Opportunity | 339 | 2.0% |
| Lost | 299 | 1.7% |
| At-risk renewal | 258 | 1.5% |
| Expansion | 139 | 0.8% |
| Competitor displacement | 134 | 0.8% |
| Onboarding | 109 | 0.6% |
| Churned | 67 | 0.4% |

Entered by:

| Value | Count | Share |
|---|---:|---:|
| event | 16,894 | 98.9% |
| clock | 193 | 1.1% |

### 3.9 Noise and hidden data

Defects logged:

| Value | Count | Share |
|---|---:|---:|
| bot | 56,257 | 76.1% |
| late | 5,438 | 7.4% |
| out_of_order | 5,104 | 6.9% |
| missing_field | 1,695 | 2.3% |
| tracking_gap | 1,461 | 2.0% |
| duplicate_account | 1,114 | 1.5% |
| duplicate | 1,057 | 1.4% |
| wrong_timestamp | 1,040 | 1.4% |
| unmatched_user | 573 | 0.8% |
| wrongly_matched | 171 | 0.2% |
| test_account | 52 | 0.1% |

Hidden prospect types (new prospects):

| Value | Count | Share |
|---|---:|---:|
| browser | 7,541 | 49.4% |
| researcher | 3,830 | 25.1% |
| evaluator | 2,309 | 15.1% |
| locked_in | 1,570 | 10.3% |

Hidden customer types (customers):

| Value | Count | Share |
|---|---:|---:|
| steady | 4,477 | 29.4% |
| shallow | 3,789 | 24.8% |
| shelfware | 2,299 | 15.1% |
| power | 1,561 | 10.2% |
| project_based | 1,258 | 8.2% |
| champion_dependent | 1,073 | 7.0% |
| price_sensitive | 793 | 5.2% |

## 4. Retention, billing and revenue measures

Renewal-cycle outcomes (hidden outcomes of every cycle ending before the extract):

| Value | Count | Share |
|---|---:|---:|
| renewed | 875 | 87.8% |
| cancelled | 61 | 6.1% |
| silent_lapse | 33 | 3.3% |
| involuntary | 28 | 2.8% |

Per segment: cycles, share churned, mean months per cycle:

| Segment | cycles | churned | mean months |
|---|---:|---:|---:|
| ENT | 108 | 6.5% | 14.9 |
| MM | 308 | 11.7% | 12.0 |
| SMB | 581 | 13.6% | 12.0 |

## 5. Table by table

### `accounts`: 16,364 rows

One row per account: bands only. Also the identity map (one ref per system) and the whole-account holdout assignment.

| Column | Type | Null share | Distinct | Meaning |
|---|---|---:|---:|---|
| `account_id` | string | 0.0% | 16,364 |  |
| `segment` | string | 0.0% | 3 |  |
| `industry_band` | string | 0.0% | 5 |  |
| `employee_band` | string | 0.0% | 4 |  |
| `region` | string | 0.0% | 4 |  |
| `source` | string | 0.0% | 6 |  |
| `created_at` | timestamp | 0.0% | 16,364 |  |
| `first_won_at` | timestamp | 97.8% | 352 |  |
| `status` | string | 0.0% | 4 | EXTRACT-TIME snapshot (leakage trap) |
| `current_plan` | string | 97.8% | 4 | EXTRACT-TIME snapshot |
| `arr_band` | string | 97.8% | 7 | EXTRACT-TIME snapshot |
| `renewal_at` | timestamp | 98.4% | 254 | EXTRACT-TIME snapshot of the current term end |
| `strategic_flag` | bool | 0.0% | 2 |  |
| `named_csm` | bool | 0.0% | 2 |  |
| `regime_first_seen` | string | 0.0% | 2 |  |
| `holdout_group` | string | 0.0% | 2 |  |
| `holdout_assigned_at` | timestamp | 0.0% | 8,225 |  |
| `holdout_share` | float | 0.0% | 1 |  |
| `holdout_strategy` | string | 0.0% | 1 |  |
| `crm_ref` | string | 0.0% | 16,364 |  |
| `billing_ref` | string | 97.8% | 353 |  |
| `cs_ref` | string | 97.8% | 353 |  |
| `domain_key` | string | 0.0% | 15,250 | HMAC of the company domain; no company names |

### `contacts`: 42,850 rows

One row per person. Leads are merged in here (lead_* columns).

| Column | Type | Null share | Distinct | Meaning |
|---|---|---:|---:|---|
| `person_key` | string | 0.0% | 41,736 | HMAC-SHA-256 of normalised work or personal email |
| `account_id` | string | 1.3% | 16,364 | Null when unmatched |
| `contact_ref` | string | 0.0% | 42,850 |  |
| `role` | string | 0.0% | 4 |  |
| `seniority_band` | string | 0.0% | 5 |  |
| `email_consent` | string | 0.0% | 3 | EXTRACT-TIME snapshot of marketing email consent; history in consent_change events |
| `personal_email` | bool | 0.0% | 2 |  |
| `first_seen_at` | timestamp | 0.0% | 36,170 |  |
| `left_account_at` | timestamp | 99.6% | 157 |  |
| `lead_status` | string | 65.0% | 5 | Set for the contact that came in as a lead |
| `lead_source` | string | 65.0% | 6 |  |
| `lead_created_at` | timestamp | 65.0% | 15,000 |  |
| `lead_converted_at` | timestamp | 98.9% | 473 |  |
| `is_product_user` | bool | 0.0% | 2 |  |

### `events`: 324,287 rows

Canonical event stream. Web, forms, consent, messages, CRM, e-sign, tickets, CTAs, health bands, registrations, billing and outcomes.

| Column | Type | Null share | Distinct | Meaning |
|---|---|---:|---:|---|
| `event_id` | string | 0.0% | 324,287 |  |
| `source_event_id` | string | 0.0% | 322,869 | object:id:status (brief rule 4) |
| `event_type` | string | 0.0% | 9 |  |
| `source_system` | string | 0.0% | 14 |  |
| `person_key` | string | 48.2% | 27,397 |  |
| `anonymous_id` | string | 49.5% | 16,035 |  |
| `unit_id` | string | 17.3% | 16,322 | account_id |
| `occurred_at` | timestamp | 0.0% | 292,354 |  |
| `ingested_at` | timestamp | 0.0% | 324,257 |  |
| `channel` | string | 36.9% | 10 |  |
| `campaign_id` | string | 85.7% | 17 |  |
| `placement_id` | string | 100.0% | 0 |  |
| `consent_status` | string | 95.4% | 2 |  |
| `properties` | json | 0.0% | 250,145 |  |

### `opportunities`: 1,484 rows

One row per deal: new, expansion, renewal and win-back. E-sign envelope merged in. Stage history is in events.

| Column | Type | Null share | Distinct | Meaning |
|---|---|---:|---:|---|
| `opp_id` | string | 0.0% | 1,484 |  |
| `account_id` | string | 0.0% | 723 |  |
| `type` | string | 0.0% | 4 |  |
| `stage` | string | 0.0% | 6 | EXTRACT-TIME snapshot; history in events |
| `amount_band` | string | 0.0% | 7 |  |
| `discount_band` | string | 0.0% | 2 |  |
| `created_at` | timestamp | 0.0% | 1,484 |  |
| `close_date` | timestamp | 0.0% | 1,409 | Expected close while open, actual when closed |
| `closed_at` | timestamp | 15.8% | 1,191 | EXTRACT-TIME snapshot |
| `is_won` | bool | 15.8% | 2 | EXTRACT-TIME snapshot |
| `loss_category` | string | 76.6% | 6 |  |
| `competitor_flag` | bool | 0.0% | 2 |  |
| `incumbent_vendor_band` | string | 77.2% | 2 |  |
| `incumbent_contract_end` | timestamp | 90.6% | 140 |  |
| `rep_id` | string | 0.0% | 24 |  |
| `legal_review` | bool | 0.0% | 2 |  |
| `esign_status` | string | 37.5% | 3 | DocuSign envelope status (EXTRACT-TIME) |
| `esign_changed_at` | timestamp | 37.5% | 928 |  |

### `product_usage_daily`: 2,874,310 rows

Account x person x feature x day, active days only. Logins are rows with feature=login.

| Column | Type | Null share | Distinct | Meaning |
|---|---|---:|---:|---|
| `account_id` | string | 8.3% | 475 | Null for unmatched users |
| `person_key` | string | 0.0% | 6,261 |  |
| `feature` | string | 0.0% | 9 |  |
| `day` | timestamp | 0.0% | 914 |  |
| `num_events` | int | 0.0% | 74 |  |
| `num_minutes` | float | 0.0% | 1,185 |  |
| `session_count` | int | 0.0% | 1 |  |
| `source_system` | string | 0.0% | 2 |  |
| `ingested_at` | timestamp | 0.0% | 1,622,320 |  |

### `subscriptions`: 1,172 rows

One row per plan period (amendments create a new version; Zuora-style Expired marks an old version). A term that ends with no successor is a lapse.

| Column | Type | Null share | Distinct | Meaning |
|---|---|---:|---:|---|
| `subscription_id` | string | 0.0% | 1,004 |  |
| `account_id` | string | 0.0% | 352 |  |
| `version` | int | 0.0% | 6 |  |
| `plan` | string | 0.0% | 4 |  |
| `seats_bought` | int | 0.0% | 175 |  |
| `seats_active_band` | string | 0.0% | 1 | EXTRACT-TIME snapshot (leakage trap) |
| `billing_interval` | string | 0.0% | 2 |  |
| `term_months` | int | 0.0% | 2 |  |
| `start_at` | timestamp | 0.0% | 1,172 |  |
| `end_at` | timestamp | 0.0% | 1,004 |  |
| `auto_renew_flag` | bool | 0.0% | 2 |  |
| `cancel_requested` | bool | 0.0% | 2 |  |
| `status` | string | 0.0% | 5 | EXTRACT-TIME snapshot |
| `status_changed_at` | timestamp | 0.0% | 962 |  |
| `pause_collection` | bool | 0.0% | 1 |  |
| `collection_method` | string | 0.0% | 2 |  |
| `trial_end` | timestamp | 98.2% | 21 |  |
| `mrr_band` | string | 0.0% | 5 |  |

### `invoices`: 3,380 rows

One row per invoice with payment outcome and dunning attempts.

| Column | Type | Null share | Distinct | Meaning |
|---|---|---:|---:|---|
| `invoice_id` | string | 0.0% | 3,380 |  |
| `subscription_id` | string | 0.0% | 1,004 |  |
| `account_id` | string | 0.0% | 352 |  |
| `amount_band` | string | 0.0% | 7 |  |
| `issued_at` | timestamp | 0.0% | 3,380 |  |
| `due_at` | timestamp | 0.0% | 3,380 |  |
| `paid_at` | timestamp | 3.9% | 3,249 |  |
| `status` | string | 0.0% | 4 | EXTRACT-TIME snapshot |
| `collection_method` | string | 0.0% | 2 |  |
| `attempt_count` | int | 0.0% | 6 |  |
| `error_code` | string | 97.0% | 3 |  |
| `disputed` | bool | 0.0% | 2 |  |
| `is_renewal` | bool | 0.0% | 2 |  |

### `actions`: 18,487 rows

One row per decision point or send: messages, decisions, rep and CSM tasks merged.

| Column | Type | Null share | Distinct | Meaning |
|---|---|---:|---:|---|
| `action_id` | string | 0.0% | 18,487 |  |
| `unit_id` | string | 0.0% | 13,818 |  |
| `person_key` | string | 0.0% | 13,818 |  |
| `opp_id` | string | 97.7% | 416 |  |
| `record_kind` | string | 0.0% | 3 |  |
| `regime` | string | 0.0% | 2 |  |
| `decided_at` | timestamp | 0.0% | 18,487 |  |
| `state` | string | 2.3% | 8 | Filled from state_history |
| `trigger` | string | 0.0% | 8 |  |
| `chosen_action` | string | 0.0% | 8 |  |
| `channel` | string | 43.1% | 3 |  |
| `category` | string | 43.1% | 3 | regulatory = billing notices, security alerts, legal terms: never held out, never chosen by the policy |
| `template` | string | 76.3% | 8 |  |
| `message_id` | string | 76.3% | 4,375 |  |
| `campaign_id` | string | 76.3% | 12 |  |
| `sent_at` | timestamp | 43.1% | 10,516 |  |
| `final_status` | string | 76.3% | 4 |  |
| `options_considered` | json | 15.0% | 6 |  |
| `blocked_actions` | json | 47.5% | 78 |  |
| `reason_codes` | json | 46.2% | 93 |  |
| `propensity` | float | 56.8% | 6 | Exploration policy probability of the chosen action |
| `expected_value` | float | 100.0% | 0 | Null: no trained model yet |
| `model_versions` | string | 100.0% | 0 |  |
| `rule_version` | string | 53.4% | 1 |  |
| `needs_approval` | bool | 0.0% | 2 |  |
| `in_holdout` | bool | 0.0% | 2 |  |
| `holdout_group` | string | 53.4% | 2 |  |
| `task_id` | string | 66.8% | 6,141 |  |
| `task_target` | string | 66.8% | 2 |  |
| `task_status` | string | 66.8% | 3 |  |
| `task_due_at` | timestamp | 66.8% | 6,141 |  |
| `task_owner_id` | string | 66.8% | 24 |  |
| `disposition` | string | 67.5% | 5 |  |
| `call_duration_s` | int | 82.1% | 1,453 |  |

### `state_history`: 17,087 rows

Output of the reference state engine run on the VISIBLE events.

| Column | Type | Null share | Distinct | Meaning |
|---|---|---:|---:|---|
| `unit_id` | string | 0.0% | 15,372 |  |
| `state` | string | 0.0% | 9 |  |
| `entered_at` | timestamp | 0.0% | 16,843 |  |
| `exited_at` | timestamp | 14.9% | 14,511 |  |
| `entered_by` | string | 0.0% | 2 |  |
| `flags` | json | 0.0% | 22 |  |
| `rule_version` | string | 0.0% | 1 |  |

### `campaigns`: 9,164 rows

campaign_map and ad_spend_daily merged (row_type).

| Column | Type | Null share | Distinct | Meaning |
|---|---|---:|---:|---|
| `row_type` | string | 0.0% | 2 |  |
| `campaign_id` | string | 0.0% | 24 |  |
| `system` | string | 0.0% | 4 |  |
| `system_campaign_id` | string | 0.0% | 25 |  |
| `name_hash` | string | 0.0% | 25 |  |
| `channel` | string | 0.0% | 4 |  |
| `date` | timestamp | 0.3% | 914 |  |
| `cost` | float | 0.3% | 8,681 |  |
| `clicks` | int | 0.3% | 187 |  |
| `impressions` | int | 0.3% | 187 |  |

### Hidden tables (folder `hidden/`)

#### `account_truth`: 15,250 rows

HIDDEN. True types, drivers, exact ACV, planted effect of each action and the true outcomes.

| Column | Type | Meaning |
|---|---|---|
| `unit_id` | string |  |
| `kind` | string |  |
| `prospect_type` | string |  |
| `customer_type` | string |  |
| `fit_score` | float |  |
| `intent_stage` | string |  |
| `incumbent_lock_in` | string |  |
| `champion_exit_hazard` | float |  |
| `usage_decay_rate` | float |  |
| `decay_mode` | string |  |
| `budget_cycle_month` | int |  |
| `competitor_win_prob` | float |  |
| `expansion_headroom` | float |  |
| `acv` | float |  |
| `seats_true` | int |  |
| `integration_connected` | bool |  |
| `reacts_badly` | bool |  |
| `uplift_prospect` | json |  |
| `uplift_customer` | json |  |
| `p_win_base` | float |  |
| `will_win` | bool |  |
| `churn_kind` | string | cancelled, silent_lapse, involuntary or null |
| `churn_at` | timestamp |  |
| `renewal_outcomes` | json |  |
| `is_test_account` | bool |  |
| `duplicate_of` | string |  |
| `champion_left_at` | timestamp |  |

#### `contact_truth`: 42,850 rows

HIDDEN. Which account a person really belongs to.

| Column | Type | Meaning |
|---|---|---|
| `person_key` | string |  |
| `contact_ref` | string |  |
| `true_account` | string |  |
| `visible_account` | string |  |
| `is_champion` | bool |  |
| `wrongly_matched` | bool |  |
| `also_in_account` | string |  |

#### `opportunity_truth`: 1,234 rows

HIDDEN. Exact amounts, true win probability with and without the action, and the true label.

| Column | Type | Meaning |
|---|---|---|
| `opp_id` | string |  |
| `unit_id` | string |  |
| `p_win_true` | float |  |
| `p_win_no_action` | float |  |
| `cycle_days_true` | float |  |
| `amount` | float |  |
| `discount_pct` | float |  |
| `true_won` | bool |  |
| `true_loss_category` | string |  |
| `label_final` | bool | Old enough for the outcome to be final |
| `cause_decision_id` | string |  |

#### `state_truth`: 16,970 rows

HIDDEN. Same state rules run on the clean, un-noised, fully linked event stream.

| Column | Type | Meaning |
|---|---|---|
| `unit_id` | string |  |
| `state` | string |  |
| `entered_at` | timestamp |  |
| `exited_at` | timestamp |  |

#### `noise_log`: 73,962 rows

HIDDEN. Every injected defect.

| Column | Type | Meaning |
|---|---|---|
| `event_id` | string |  |
| `defect` | string |  |
| `detail` | json |  |

## 6. Labels you can build

Labels are one row per decision (`actions` row) and label, long format: `label, horizon_days, y, is_final, final_at`. `build_labels` in `vynqe_synth/packs/b2b_saas/labels.py` builds six point-in-time labels with a 45-day finality buffer:

| Label | Horizon (days) | Rows | Final rows | Positive share (final rows) |
|---|---:|---:|---:|---:|
| churned_within_165d | 165 | 1,196 | 882 | 7.3% |
| deal_won_180d | 180 | 416 | 290 | 25.2% |
| expansion_won_120d | 120 | 523 | 410 | 15.6% |
| first_value_90d | 90 | 40 | 35 | 11.4% |
| lead_progressed_30d | 30 | 13,471 | 12,206 | 21.3% |
| resubscribed_180d | 180 | 66 | 49 | 12.2% |

## 7. Leakage traps built in on purpose

- `accounts.status`, `accounts.arr_band`, `accounts.renewal_at`, `subscriptions.status`, `subscriptions.status_changed_at`, `subscriptions.seats_active_band`, `subscriptions.cancel_requested` are extract-time snapshots. Using them as features leaks the outcome (on this run `accounts.status` alone gives AUC about 0.91 on the churn label).
- Legacy-period actions are biased by fit and ARR and carry no propensity: do not use them for uplift.
- Hidden tables must never be read by feature, state or label code (AST test and validator check).

## 8. Validation (150 checks, real results)

All 150 checks pass on this run. Key observed values:

| Group | Check | Observed | Expected |
|---|---|---|---|
| funnel | lead to MQL (contacted) (Q9) | 0.2985 | 0.3 +/- 0.03 |
| funnel | MQL to SQL (qualified) (Q9) | 0.2462 | 0.25 +/- 0.04 |
| funnel | SQL to opportunity (converted) (Q9) | 0.4096 | 0.42 +/- 0.06 |
| funnel | opportunity to won, closed new deals (Q9) | 0.2429 | 0.25 +/- 0.05 |
| funnel | median sales cycle SMB days (Q10) | 35.5 | 30 +/- 35% |
| funnel | median sales cycle MM days (Q10) | 95.0 | 75 +/- 35% |
| funnel | median sales cycle ENT days (Q10) | 171.0 | 150 +/- 35% |
| funnel | every loss category appears | [] | [] |
| retention | annual logo churn SMB (Q41) | 0.1471 | 0.15 +/- 0.04 |
| retention | GRR per cycle SMB (Q41, default 0.82) | 0.841 | 0.82 +/- 0.06 |
| retention | NRR per cycle SMB (Q41, 0.97) | 0.939 | 0.97 +/- 0.10 |
| retention | annual logo churn MM (Q41) | 0.133 | 0.1 +/- 0.04 |
| retention | GRR per cycle MM (Q41, default 0.9) | 0.855 | 0.9 +/- 0.06 |
| retention | NRR per cycle MM (Q41, 1.08) | 1.026 | 1.08 +/- 0.10 |
| retention | annual logo churn ENT (Q41) | 0.0553 | 0.05 +/- 0.04 |
| retention | GRR per cycle ENT (Q41, default 0.93) | 0.911 | 0.93 +/- 0.06 |
| retention | NRR per cycle ENT (Q41, 1.18) | 1.087 | 1.18 +/- 0.10 |
| retention | involuntary share of churn (Q42: 20 to 40%) | 0.26 | 0.20-0.40 |
| retention | silent lapse share of voluntary churn (Q42 mid-market 7 of 17 = 0.41; lower for monthly plans) | 0.338 | 0.20-0.50 |
| retention | mid-market annual renewal split vs Q42 rescaled to Q41 churn of 10% (59.6/21.7/8.7/5.9/4.1) | {'as_is': 0.668, 'expanded': 0.181, 'contracted': 0.065, 'cancelled': 0.04, 'silent_lapse' | rescaled targets within 8 points each (expansion also happen |
| retention | win-back share of churned (Q53: 8-12%) | 0.075 | 0.1 +/- 0.06 |
| holdout | holdout balanced on hidden customer_type (max share gap) | 0.015 | < 0.03 |
| holdout | holdout balanced on hidden prospect_type (max share gap) | 0.0177 | < 0.03 |
| noise | duplicate accounts (Q74: 5-10%) | 0.073 | 0.075 +/- 0.015 |
| noise | users unmatched to an account (Q37/75: 5-15%) | 0.0843 | 0.08 +/- 0.03 |
| noise | out-of-order share of all events (Q76: 1-3%) | 0.0157 | 0.02 +/- 0.015 |
| noise | late events share | 0.0168 | 0.02 +/- 0.01 |
| noise | every defect type is logged | ['bot', 'duplicate', 'duplicate_account', 'late', 'missing_field', 'out_of_order', 'test_a | all injected types |
| noise | duplicate events share the source_event_id of an original | 1.0 | 1.0 |
| usage | Tue-Thu peak, weekend trough (Q36) | {'0': 5852399, '1': 6157940, '2': 6195304, '3': 6061884, '4': 5054480, '5': 649324, '6': 4 | Tue..Thu > Mon, Sat/Sun < 25% of Tue |
| usage | holiday-week dip of 30-40% (Q36) | 0.709 | 0.5-0.8 (growth adds noise) |
| usage | every user-day has a login row when any feature row exists (sampled) | 1.0 | 1.0 |
| billing | late-paid share of invoice-method accounts (Q49: 25-35%) | 0.2983 | 0.3 +/- 0.08 |
| billing | disputed invoices (Q49: 2-4%) | 0.0308 | 0.03 +/- 0.012 |
| billing | card invoices with a failed first attempt (Q48: 3-5%) | 0.0395 | 0.04 +/- 0.015 |
| support | tickets per paying account per month (Q56: median 0.5-1.0, scaled by size) | 0.768 | 0.3-2.0 |
| billing | invoice statuses: captured majority, some failed, some refunded | {'captured': 0.953, 'created': 0.03, 'failed': 0.008, 'refunded': 0.008} | captured > 0.8, failed > 0 |
| guardrails | every blocked-action reason appears in the data | [] | [] |
| guardrails | no promotional action for a held-out account (regime 2) | 0 | 0 |
| guardrails | regulatory and transactional rows are never held out | 0 | 0 |
| guardrails | policy never chooses regulatory/transactional | 0 | 0 |
| guardrails | no marketing email without granted consent at decision time (visible consent history) | 0 of 1600 | < 0.5% |
| guardrails | no marketing email while an opportunity is open | 3 of 1600 | < 1% |
| guardrails | no marketing email within 14 days of a renewal date | 0 of 1600 | < 1% |
| guardrails | propensity logged for every randomised, non-held-out decision | 1.0 | 1.0 |
| guardrails | propensity in (0,1] | [0.15, 1.0] | (0,1] |
| guardrails | do_nothing share where nothing is blocked (exploration 25%) | 0.2411 | 0.25 +/- 0.04 |
| regimes | regime 1 touches high-fit accounts more (planted selection bias) | {'high_fit': 0.289, 'low_fit': 0.219} | high > low + 0.03 |
| regimes | regime 2 touch rate does not depend on fit | 0.012 | < 0.04 |
| leakage | state_engine.py imports nothing from hidden/truth and never reads *_truth | [] | [] |
| leakage | labels.py imports nothing from hidden/truth and never reads *_truth | [] | [] |
| leakage | hidden folder separate from visible | ['account_truth.parquet', 'contact_truth.parquet', 'noise_log.parquet', 'opportunity_truth | ['account_truth.parquet', 'contact_truth.parquet', 'opportun |
| leakage | no hidden-only column name appears in a visible table | [] | [] |
| labels | every final label has its horizon plus buffer inside the extract window | 0 | 0 |
| labels | some labels are not yet final | 0.11710794297352342 | > 0 |
| labels | label table has all six labels | {'churned_within_165d': {'size': 882, 'mean': 0.073}, 'deal_won_180d': {'size': 290, 'mean | 6 labels |
| leakage | trap exists: accounts.status (extract-time snapshot) separates churn labels almost perfectly | 0.911 | AUC > 0.85 (documented trap; feature code must not use it) |
| state | visible-event state pairs found in truth (noise and duplicate accounts cost some) | 0.971 | 0.8-1.0 |
| state | all 9 states present | [] | [] |
| state | no subscription started before an account's first Lost stay (a lost deal may win later after cooling-off) | 0 | 0 |
| state | At-risk renewal starts within 120 days before (or 60 after) a term end | 1.0 | > 0.95 |
| state | flags present and parseable | 1.0 | 1.0 |
| state | actions carry the state at decision time | 0.977 | > 0.9 |
| recovery | visible usage recovers the hidden customer type better than chance but not perfectly | {'cv_accuracy': 0.603, 'majority_baseline': 0.305, 'n': 292} | baseline + 0.05 < accuracy < 0.90 |
| uplift | estimated effect (action vs do_nothing, stratified by blocked set) has the planted sign in the randomised regi | {'cells': 4, 'sign_agreement': 1.0} | sign agreement > 0.6 over cells with planted /effect/ >= 0.0 |
| uplift | estimated and planted effects are positively correlated across (trigger, action) cells | 0.939 | > 0.3 |
| uplift | planted win-probability shift is zero when do_nothing and positive for rep_outreach/exec_call on average | {'do_nothing': 0.0, 'rep_outreach': 0.086} | 0 and > 0 |
| uplift | sleeping dogs exist (reacts_badly share) | 0.0483 | 0.05 +/- 0.01 |
| uplift | planted negative effects exist for some types and actions | [['power', 'discount'], ['shelfware', 'discount'], ['project_based', 'email']] | at least one |

The full list, including schema, privacy and integrity checks, is in `validation_report_dev_15k.md`. Weak spots: see `CHANGELOG.md` (customer counts are small; the answers' NRR/GRR and Q42 split contradict Q41; `full` was not validated).

## 9. What this data can and cannot prove

See `what_this_data_can_and_cannot_prove.md`. It can test pipeline correctness, point-in-time labelling, guardrail enforcement, state-engine behaviour and uplift-method recovery against planted effects. It cannot show that real accounts behave like this, that any rate is right, or how a model will perform on real data.

## 10. How to generate and where files are

```
python -m vynqe_synth generate --pack b2b_saas --preset dev --seed 7 --out ./out
python -m vynqe_synth validate --out ./out
```
`visible/` 10 tables, `hidden/` 5 tables, `schemas/` JSON contracts, `reports/` row counts and validation. Parameters: `parameters_report.md`.
