# BFSI personal-loan synthetic dataset: full report (100,000 people)

**Read this first.** Everything here is synthetic. Every number comes from a configured assumption (`docs/parameters_report.md`), tuned to match the ranges in the BFSI answers file. The data is for building and testing the Customer Lifecycle Intelligence pipeline. **It makes no claim about how any model will perform on real borrowers**, and no rate in this report should be quoted as a real-world fact.

Report generated from a real run: preset `dev`, 100,000 people, seed 42, pack version 0.1.0. All numbers below were computed from the generated files.

## 1. At a glance

| Item | Value |
|---|---|
| People (leads the lender can see) | 100,000 |
| Time window | 36 months: 1 Nov 2023 to 31 Oct 2026 |
| Period 1 (legacy biased targeting) | months 1 to 18 (to about 1 May 2025) |
| Period 2 (randomised policy, 8% holdout) | months 19 to 36 |
| Visible tables | 10 (6,020,545 rows in total) |
| Hidden tables (validation only) | 4 (1,411,449 rows in total) |
| Events | 4,937,543 (49.4 per person) |
| Sessions (30-minute rule) | 562,413 (169,213 identified, 393,200 anonymous) |
| Applications | 51,062 (47.0% of people applied at least once) |
| Loans disbursed | 8,017 to 7.4% of people |
| EMI payment attempts | 98,785 |
| Decisions and sends (`actions`) | 376,706 |
| Disk size (parquet, compressed) | 183 MB (events alone 131 MB) |
| Generation time | 100 seconds; same seed gives identical data |
| Validation | 125 of 125 checks pass (see section 8, with the weak spots) |

## 2. How the data is built

The unit is a **person**, not a loan. A person is a lead the lender can see (a phone number that reached the system). People who never reach the lender are not in the data.

**Journey of one person:** lead created, anonymous browsing before and after, identification (phone OTP), application started, KYC, Account Aggregator (AA) data-sharing consent and data fetch, lender decision into band 1 to 4, offer and key fact statement, e-sign, auto-debit mandate set-up, disbursal, monthly EMIs (on time, in grace, late, missed), collections, complaints and disputes, top-up after 6 on-time EMIs, closure (matured, prepaid or cooling-off exit), win-back after closure.

**Two periods.** In months 1 to 18 the lender used rule-based, biased targeting: lower-risk and higher-value people got more nudges, with no decision id and no propensity logged. From month 19 a randomised exploration policy runs: at each decision point it chooses `do_nothing` with 25% probability and otherwise picks uniformly among the allowed actions, and logs the probability (`propensity`). An 8% salted-hash holdout never receives optional actions. Only the second period supports causal estimates.

**Guardrails** (each blocked action carries a reason code): no marketing consent (AA data-sharing consent never counts), unknown consent, collections hold, dispute hold, mandate inactive, an agent already engaged, weekly frequency cap, suitability (no offers to band 4 or to anyone late in the last 90 days), agent capacity, approval limit for large fee waivers, and the holdout. EMI reminders, pre-debit notices, key fact statements and agreements are regulatory messages: never held out and never chosen by the policy.

**Hidden drivers.** Each person has a hidden borrower type (six), true income, true risk, KYC friction, urgency and a planted true effect for each of five actions (nudge, agent call, fee waiver, offer, EMI nudge). 3.9% are "sleeping dogs" whose true effect is negative. About 9.9% change type during the window. These live only in the hidden folder. The lender band in visible data is true risk plus noise, so it is informative but not perfect.

**Controlled mess**, every instance logged in `noise_log`: duplicate events, missing fields, wrong timestamps, late and out-of-order arrivals, bots, analytics outages, shared phones, split identities, duplicate applications. Mandate results arrive 1 to 2 days late and core banking arrives as a daily extract.

## 3. The dataset in numbers

### 3.1 Who the people are

Acquisition channel (`in_app` = existing customers of the lender):

| Channel | Share |
|---|---:|
| in_app | 24.9% |
| paid_social | 22.1% |
| paid_search | 15.1% |
| organic | 12.9% |
| partner | 12.2% |
| referral | 8.0% |
| whatsapp | 4.9% |

Device:

| Device | Share |
|---|---:|
| android | 69.9% |
| web_mobile | 11.9% |
| ios | 10.1% |
| web_desktop | 8.2% |

City tier:

| Tier | Share |
|---|---:|
| tier2 | 27.0% |
| tier1 | 22.0% |
| tier3 | 20.0% |
| metro | 16.9% |
| rural | 14.1% |

Marketing consent (snapshot at extract time; AA data consent is separate and not in these columns):

| Channel | Granted | Denied | Unknown | Withdrawn |
|---|---:|---:|---:|---:|
| Email | 59.6% | 3.1% | 36.0% | 1.3% |
| SMS | 54.7% | 5.1% | 39.0% | 1.1% |
| WhatsApp | 59.5% | 3.0% | 36.2% | 1.3% |

Unknown consent means hold (no marketing). 2.0% of people carry a core-banking do-not-market flag. 2,980 people share a phone number with someone else (1,512 pairs are logged in `noise_log`).

Created in the legacy period: 43.2%; in the randomised period: 56.8%. Holdout: 8.0% control, 92.0% treated.

Hidden attributes (validation only): salaried 62.1%, self-employed 37.9%; average age 32.0; median annual income about INR 373,606; average loan-to-income 0.208; identity-fraud 0.84%; heavy stacking 30.2%; sleeping dogs 3.9%.

Hidden borrower types:

| Type | Share |
|---|---:|
| short_term_cash | 33.2% |
| repeat_borrower | 19.0% |
| planned_big_ticket | 18.9% |
| debt_consolidation | 14.3% |
| rate_shopper | 10.2% |
| one_time | 4.4% |

### 3.2 The funnel (new applications only)

| Step | People or applications | Share of leads | Share of previous step |
|---|---:|---:|---:|
| Leads (people) | 100,000 | 100.0% |  |
| New applications started | 49,413 | 49.4% | 49.4% |
| KYC started | 33,159 | 33.2% | 67.1% |
| KYC verified | 28,730 | 28.7% | 86.6% |
| AA consent given | 25,933 | 25.9% | 90.3% |
| AA data fetched | 23,648 | 23.6% | 91.2% |
| Lender decision made | 23,638 | 23.6% | 100.0% |
| Approved (sanctioned) | 12,013 | 12.0% | 50.8% |
| E-sign started (offer accepted) | 8,575 | 8.6% | 71.4% |
| E-signed | 8,083 | 8.1% | 94.3% |
| Mandate active | 7,674 | 7.7% | 94.9% |
| Disbursed | 7,356 | 7.4% | 95.9% |

Lead to disbursal is 7.4% (answers file Q7: 3 to 8%). Application to disbursal is 14.9% (Q7: about 12%). Applications include about 4.8% duplicates (rate shoppers resubmit), which are flagged in `noise_log`. Not every application that is disbursed went through each step above, because mandate failures can still lead to disbursal with manual repayment.

Application kinds: new 49,413, top_up 1,111, win_back 538.

Application stage at the extract date:

| Stage | Applications | Share |
|---|---:|---:|
| applied | 16,483 | 32.3% |
| rejected | 11,973 | 23.4% |
| docs_pending | 9,511 | 18.6% |
| disbursed | 8,017 | 15.7% |
| approved | 3,747 | 7.3% |
| signed | 793 | 1.6% |
| offer_accepted | 528 | 1.0% |
| in_review | 10 | 0.0% |

Decision and band (decided applications):

| Decision | Applications | Share |
|---|---:|---:|
| approve | 12,188 | 48.6% |
| decline | 10,848 | 43.3% |
| refer | 2,022 | 8.1% |

| Lender band at decision | Applications | Share |
|---|---:|---:|
| band_2 | 9,954 | 39.7% |
| band_1 | 7,911 | 31.6% |
| band_3 | 4,724 | 18.9% |
| band_4 | 2,469 | 9.9% |

Rejection reasons:

| Reason | Applications | Share |
|---|---:|---:|
| policy | 4,224 | 35.3% |
| income | 3,562 | 29.8% |
| other | 2,314 | 19.3% |
| kyc | 1,148 | 9.6% |
| fraud | 725 | 6.1% |

Requested amount band (INR):

| Band | Applications | Share |
|---|---:|---:|
| 100k-250k | 11,443 | 22.4% |
| 50k-100k | 11,068 | 21.7% |
| 25k-50k | 10,815 | 21.2% |
| 10k-25k | 9,760 | 19.1% |
| 250k+ | 4,320 | 8.5% |
| 0-10k | 3,656 | 7.2% |

### 3.3 Steps (KYC, AA, e-sign, mandate)

Final status of each step row (`application_steps`):

| Step | Rows | Final statuses |
|---|---:|---|
| aa_consent | 31,074 | active 26,964, expired 1,819, failed 1,057, rejected 740, revoked 494 |
| aa_fetch | 30,118 | completed 25,068, failed 5,050 |
| esign | 9,494 | declined 473, signed 8,810, voided 211 |
| kyc | 41,724 | expired 2,573, failed 10,391, pending 30, verified 28,730 |
| mandate | 9,629 | active 8,366, failed 370, rejected 893 |

KYC first attempt passes about 71%; AA consent about 87%; AA fetch first try 85%; e-sign 93%; mandate first try 88%. KYC methods: ekyc_otp 15,666, digilocker 13,801, manual_document 9,020, video_kyc 3,237 attempts.

### 3.4 Loans and repayments

8,017 loans. Average rate 20.3%, average term 22.1 months, median disbursed amount INR 47,700 (mean 84,735), median EMI INR 2,986. These exact figures live only in the hidden `application_truth` table.

Loan status at the extract date:

| Status | Loans | Share |
|---|---:|---:|
| active | 4,765 | 59.4% |
| closed | 2,802 | 35.0% |
| defaulted | 450 | 5.6% |

Closure type (closed loans):

| Closure | Loans | Share |
|---|---:|---:|
| matured | 2,019 | 72.1% |
| prepaid | 698 | 24.9% |
| foreclosed | 85 | 3.0% |

Tenure band:

| Tenure band | Loans | Share |
|---|---:|---:|
| 13-24m | 4,052 | 50.5% |
| <=12m | 2,233 | 27.9% |
| 25-36m | 1,192 | 14.9% |
| 37-60m | 540 | 6.7% |

**EMI states** over 84,954 instalments (hidden pay_path): on time 84.0%, grace 8.2%, late 4.8%, missed 2.9%. Answers file Q31: 80 to 85 / 8 to 10 / 5 to 8 / 1 to 3%.

**EMI payment attempts** (98,785): captured 83,206, failed 15,579. Failure reasons: insufficient_funds 11,241, technical 2,332, bank_decline 1,229, mandate_inactive 777. Methods: upi_autopay 54,208, emandate 29,873, manual_upi 10,292, netbanking 4,412. First-attempt bounce is about 14.7% (Q33 says 5 to 12%, Q31 implies about 15%: the two answers disagree and the pack sits between them).

**Default label** (90+ days past due within 12 months of disbursal): final only for loans 15+ months old. 8,017 loans disbursed, 3,806 old enough to be final, 178 defaults among those, so **4.68%** (Q26 placeholders: digital personal loans 1 to 6%). All loans so far: 262 reached 90+ days past due within 12 months (not final for young loans). Lender flag `defaulted` is set on 450 loans (this includes defaults after month 12).

Default rate by lender band (final loans):

| Band | Final loans | Default rate | Q26 placeholder |
|---|---:|---:|---|
| band_1 | 1,723 | 2.1% | 1 to 2% |
| band_2 | 1,509 | 3.6% | 4 to 6% |
| band_3 | 462 | 12.8% | 10 to 15% |
| band_4 | 112 | 25.0% | high |

Band 2 sits slightly under its placeholder and band 4 above it (band 4 has only 112 final loans, so that figure is noisy). By application kind: new 4.8%, top-up 1.7%, win-back 3.0%.

Highest days past due reached: (-1.0, 0.0] 3,778, (0.0, 29.0] 3,157, (89.0, 1000.0] 452, (59.0, 89.0] 335, (29.0, 59.0] 293.

Complaints, disputes and collections: collections 6,539, complaint 391, dispute 170 cases (7,100). Every case suppresses marketing while open.

### 3.5 Messages, decisions and actions

`actions` has 376,706 rows: transactional 202,573, decision 148,578, legacy_send 25,555.

Chosen action (all rows):

| Action | Rows | Share |
|---|---:|---:|
| regulatory | 186,994 | 49.6% |
| nudge | 64,582 | 17.1% |
| do_nothing | 63,747 | 16.9% |
| agent_call | 25,828 | 6.9% |
| transactional | 15,579 | 4.1% |
| emi_nudge | 9,251 | 2.5% |
| offer | 8,998 | 2.4% |
| fee_waiver | 1,727 | 0.5% |

In the randomised period there are 148,578 decision points; 63,747 chose `do_nothing` (this includes people blocked by guardrails, for whom the policy has no allowed action). 10,610 decision rows were blocked only by the holdout.

Trigger (why the decision happened):

| Trigger | Rows | Share |
|---|---:|---:|
| emi_due | 195,436 | 51.9% |
| lead | 65,623 | 17.4% |
| stall | 54,275 | 14.4% |
| legacy | 25,555 | 6.8% |
| service | 21,101 | 5.6% |
| topup | 9,353 | 2.5% |
| winback | 5,363 | 1.4% |

Guardrail reason codes (counts of blocked actions):

| Reason code | Count | Share |
|---|---:|---:|
| capacity_full | 27,957 | 42.7% |
| in_holdout | 10,610 | 16.2% |
| rep_engaged | 9,830 | 15.0% |
| unknown_consent | 8,282 | 12.6% |
| aa_consent_only | 2,139 | 3.3% |
| no_consent | 2,128 | 3.2% |
| suitability_failed | 1,388 | 2.1% |
| collections_hold | 1,196 | 1.8% |
| frequency_cap | 1,138 | 1.7% |
| approval_limit | 396 | 0.6% |
| mandate_inactive | 357 | 0.5% |
| dispute_hold | 66 | 0.1% |

Channel of messages and calls:

| Channel | Rows | Share |
|---|---:|---:|
| whatsapp | 126,361 | 42.0% |
| sms | 84,853 | 28.2% |
| email | 75,745 | 25.2% |
| call | 14,178 | 4.7% |

Final message status:

| Status | Messages | Share |
|---|---:|---:|
| delivered | 241,407 | 84.2% |
| opened | 20,173 | 7.0% |
| failed | 11,863 | 4.1% |
| clicked | 10,482 | 3.7% |
| bounced | 2,353 | 0.8% |
| unsubscribed | 478 | 0.2% |

Agent-call disposition: connected 6,243, not_reachable 3,827, application_completed 1,555, not_interested 1,313, callback_requested 1,240. Task status: done 14,402, ignored 6,513, overridden 3,996, open 1,313.

### 3.6 Events and sessions

4,937,543 events.

| Event type | Events | Share |
|---|---:|---:|
| page_view | 3,117,757 | 63.1% |
| message_status | 623,881 | 12.6% |
| record_created | 423,525 | 8.6% |
| record_status_changed | 314,878 | 6.4% |
| consent_change | 193,167 | 3.9% |
| decision_made | 151,571 | 3.1% |
| identify | 102,021 | 2.1% |
| link_click | 10,743 | 0.2% |

By source system:

| Source | Events | Share |
|---|---:|---:|
| trackflow | 3,219,778 | 65.2% |
| klaviyo | 355,479 | 7.2% |
| whatsapp | 297,767 | 6.0% |
| salesforce | 254,115 | 5.1% |
| loan_origination | 190,403 | 3.9% |
| decision_service | 151,571 | 3.1% |
| account_aggregator | 125,361 | 2.5% |
| razorpay | 105,601 | 2.1% |
| kyc | 85,047 | 1.7% |
| warehouse | 59,177 | 1.2% |
| docusign | 28,380 | 0.6% |
| core_banking | 26,457 | 0.5% |
| service_collections | 23,967 | 0.5% |
| contact_centre | 14,440 | 0.3% |

**Sessions** are not stored; they are derived from page views with the 30-minute inactivity rule. 3,117,757 page views make 562,413 sessions (5.54 page views each, median 3). 169,213 sessions (1.69 per person) belong to known people and 393,200 are anonymous (including bots, about 3% of anonymous sessions, and people who never identified).

Median delay from occurrence to ingestion: real-time sources about 30 to 40 seconds, messaging 2.6 minutes, core banking 19.8 hours (daily extract), payment/mandate vendor 1.5 days (T+1 to T+2).

### 3.7 Lifecycle states (state engine output)

The reference state engine reads events only and produces 308,316 state stays (3.08 per person); 279,561 were entered by an event and 28,755 by silence (a timer). Visible and truth state pairs agree 99.8% of the time (noise and identity splits cause the difference).

| State | Stays | Share |
|---|---:|---:|
| Lead | 114,468 | 37.1% |
| Application started | 58,579 | 19.0% |
| Consent pending | 28,613 | 9.3% |
| In review | 25,178 | 8.2% |
| KYC drop-off | 14,380 | 4.7% |
| Offer pending | 13,085 | 4.2% |
| Repaying | 12,433 | 4.0% |
| Rejected | 11,972 | 3.9% |
| Signing and mandate pending | 9,385 | 3.0% |
| Activated | 8,026 | 2.6% |
| Late | 5,489 | 1.8% |
| Top-up eligible | 4,832 | 1.6% |
| Dormant | 1,876 | 0.6% |

### 3.8 Noise and hidden data

Injected defects (hidden `noise_log`, 951,713 rows):

| Defect | Rows | Share |
|---|---:|---:|
| bot | 681,327 | 71.6% |
| duplicate | 85,732 | 9.0% |
| late | 82,833 | 8.7% |
| missing_field | 38,043 | 4.0% |
| out_of_order | 24,292 | 2.6% |
| wrong_timestamp | 20,756 | 2.2% |
| tracking_gap | 17,218 | 1.8% |
| shared_device | 1,512 | 0.2% |

Campaigns: 17 campaign rows and 10,960 daily ad-spend rows (total spend INR 44,387,705, 3,165,763 clicks).

## 4. Table by table

Common rules: `unit_id` joins everything; `application_ref` joins applications, steps, loans and actions; `loan_id` joins loans and EMI payments. Visible tables never contain raw phone, email, name, address, income, days past due or exact amounts. Amounts appear only as bands. Hidden tables are in a separate folder and must never be read by feature or model code.

### 4.1 `borrowers`: 100,000 rows

**Grain:** One row per person.

**Why it exists:** The identity map (one reference per system), the marketing consent snapshot and the holdout assignment. The brief had separate lead and consent tables; leads and consent history live in `events`.

**Watch out:** Counts columns (`applications_count`, `loans_count`) and consent columns are extract-time snapshots (leakage traps). Use `events` for history.

**Counts:** applications per person 0: 52,960, 1: 43,277, 2: 3,534, 3: 199, 4: 30; loans per person 0: 92,644, 1: 6,759, 2: 539, 3: 52, 4: 6.

| Column | Type | Null | Meaning |
|---|---|---|---|
| `unit_id` | string |  | Person key used across all tables (B + 7 digits). One person = one lead the lender can see. |
| `person_key` | string |  | HMAC-SHA-256 of the normalised phone number (hash only; the raw phone is never stored). Two people can share a key when they share a phone. |
| `created_at` | timestamp |  | When the row was created. |
| `first_application_at` | timestamp | yes | Time of the person's first application. |
| `applications_count` | int |  | EXTRACT-TIME snapshot (leakage trap) |
| `loans_count` | int |  | EXTRACT-TIME snapshot (leakage trap) |
| `existing_customer` | bool |  | From core banking at first contact |
| `acquisition_channel` | string |  | Where the lead came from: paid_social, paid_search, partner, organic, whatsapp, referral, in_app (existing base). |
| `device_class` | string |  | android, ios, web_mobile or web_desktop. Values: android, ios, web_mobile, web_desktop. |
| `geo_tier` | string | yes | Flagged extension: not in workbook Values: metro, tier1, tier2, tier3, rural. |
| `email_consent` | string |  | EXTRACT-TIME snapshot of MARKETING consent; history in consent_change events Values: granted, denied, unknown, withdrawn. |
| `sms_consent` | string |  | Same for SMS. Values: granted, denied, unknown, withdrawn. |
| `whatsapp_consent` | string |  | Same for WhatsApp. Values: granted, denied, unknown, withdrawn. |
| `do_not_market` | bool |  | Core-banking flag. True means never send marketing. |
| `regime_first_seen` | string |  | legacy_targeting if the person was created in months 1 to 18, else randomised_holdout. Values: legacy_targeting, randomised_holdout. |
| `holdout_group` | string |  | control = held out of optional nudges (8%), treated = eligible. Values: control, treated. |
| `holdout_assigned_at` | timestamp |  | Assignment time (max of created_at and the start of the randomised period). |
| `holdout_share` | float |  | Configured share of control (0.08). |
| `holdout_strategy` | string |  | random_hash: salted hash of unit_id. Values: random_hash. |
| `los_customer_ref` | string |  | Reference in the loan origination system. |
| `salesforce_lead_ref` | string |  | Lead id in the CRM. |
| `klaviyo_profile_ref` | string |  | Messaging platform profile id. |
| `razorpay_ref` | string | yes | Payment/mandate vendor customer id; set only for people who tried a mandate. |
| `core_banking_ref` | string | yes | Hashed CIF; set once a loan is disbursed |
| `trackflow_user_id` | string |  | Analytics tool user id. |
| `email_key` | string |  | HMAC of lowercased email |

### 4.2 `events`: 4,937,543 rows

**Grain:** One row per event.

**Why it exists:** The canonical stream: leads, page views, stage history, KYC and AA steps, consent changes, messages, decisions, risk-band updates, loan and EMI events. It is the only table a point-in-time feature builder should rely on, using `occurred_at` and `ingested_at`.

**Watch out:** `source_event_id` has the form object:id:status and is the dedupe key (duplicates share it). Features at time t must use only rows with `ingested_at <= t`.

| Column | Type | Null | Meaning |
|---|---|---|---|
| `event_id` | string |  | Unique id of the event row (duplicates get a -D suffix). |
| `source_event_id` | string |  | object:id:status (brief rule 4) |
| `event_type` | string |  | Kind of event (page_view, message_status, record_created, record_status_changed, consent_change, decision_made, identify, link_click). |
| `source_system` | string |  | System that produced the event (trackflow, salesforce, loan_origination, kyc, account_aggregator, docusign, razorpay, core_banking, service_collections, contact_centre, klaviyo, whatsapp, warehouse, decision_service). |
| `person_key` | string | yes | HMAC-SHA-256 of the normalised phone number (hash only; the raw phone is never stored). Two people can share a key when they share a phone. |
| `anonymous_id` | string | yes | Browser or device id before the person is known. |
| `unit_id` | string | yes | Person key used across all tables (B + 7 digits). One person = one lead the lender can see. |
| `occurred_at` | timestamp |  | When it happened (can carry injected timestamp errors). |
| `ingested_at` | timestamp |  | When the warehouse received it. Always later than occurred_at; features must respect this. |
| `channel` | string | yes | Acquisition or message channel. |
| `campaign_id` | string | yes | Campaign the event belongs to (null when none). |
| `placement_id` | string | yes | Always null in this pack (kept for contract compatibility). |
| `consent_status` | string | yes | Marketing consent at the time of the event, where relevant. Values: granted, denied, unknown, withdrawn. |
| `properties` | json |  | JSON with event details (object, ids, status, feature, template...). |

### 4.3 `applications`: 51,062 rows

**Grain:** One row per loan application (new, top-up or win-back).

**Why it exists:** The funnel record. Stage history is in `events`; this table is the snapshot at extract time.

**Watch out:** `stage` and `stage_changed_at` are snapshots (traps). `risk_band` is the lender band at decision. `decision_id` is set only when the person clicked or was called after a decision.

**Counts:** channel in_app 15,919, paid_social 9,657, paid_search 7,053, organic 6,276, partner 5,526, referral 4,176, whatsapp 2,455.

| Column | Type | Null | Meaning |
|---|---|---|---|
| `application_ref` | string |  | Application id (APP + person + number). |
| `unit_id` | string |  | Person key used across all tables (B + 7 digits). One person = one lead the lender can see. |
| `product_code` | string |  | Always personal_loan. Values: personal_loan. |
| `application_kind` | string |  | Flagged extension Values: new, top_up, win_back. |
| `created_at` | timestamp |  | When the row was created. |
| `channel` | string | yes | Acquisition or message channel. |
| `campaign_id` | string | yes | Campaign the event belongs to (null when none). |
| `branch_code` | string | yes | Always null (digital lender). |
| `stage` | string |  | Snapshot at extract time; offer_accepted and signed are additions to confirm Values: applied, docs_pending, in_review, approved, offer_accepted, signed, rejected, disbursed. |
| `stage_changed_at` | timestamp |  | Time of the latest stage change (snapshot at extract). |
| `rejection_reason_category` | string | yes | policy, income, kyc, fraud or other (categories only, no bureau detail). Values: policy, income, kyc, fraud, other. |
| `requested_amount_band` | string |  | Requested amount in a band: 0-10k, 10k-25k, 25k-50k, 50k-100k, 100k-250k, 250k+ (INR). |
| `sanctioned_amount_band` | string | yes | Sanctioned amount band (null until approved). |
| `disbursed_amount_band` | string | yes | Disbursed amount band (null until disbursed). |
| `sanction_date` | timestamp | yes | Time the lender approved. |
| `disbursal_date` | timestamp | yes | Time money was disbursed. |
| `decision_band` | string | yes | approve, refer (manual review) or decline. Values: approve, refer, decline. |
| `risk_band` | string | yes | The lender's own band (noisy function of true risk); null until decided Values: band_1, band_2, band_3, band_4. |
| `decision_id` | string | yes | Set only when the person clicked or was called after a decision (observable attribution) |

### 4.4 `application_steps`: 122,039 rows

**Grain:** One row per KYC attempt, AA consent, AA data fetch, e-sign envelope or mandate attempt.

**Why it exists:** Merges four brief tables (KYC, AA, e-sign, mandate) because they share one shape: a step with a method, a status and a time. AA consent is a data-sharing consent, never marketing consent.

**Watch out:** `status` is the final status at extract time; use the step events in `events` for point-in-time.

| Column | Type | Null | Meaning |
|---|---|---|---|
| `step_id` | string |  | Unique step row id. |
| `application_ref` | string |  | Application id (APP + person + number). |
| `unit_id` | string |  | Person key used across all tables (B + 7 digits). One person = one lead the lender can see. |
| `step_type` | string |  | kyc, aa_consent, aa_fetch, esign or mandate. Values: kyc, aa_consent, aa_fetch, esign, mandate. |
| `external_id` | string |  | verification_id, consent_id, session_id, envelope_id or token_id |
| `method` | string | yes | How it was done (KYC: ekyc_otp, digilocker, video_kyc, manual_document; mandate: upi_autopay or emandate). Values: ekyc_otp, digilocker, video_kyc, manual_document, account_aggregator, docusign, upi_autopay, emandate. |
| `status` | string |  | Final status at extract time |
| `attempt_no` | int |  | 1 for the first attempt, 2 for a retry. |
| `started_at` | timestamp |  | Step start. |
| `completed_at` | timestamp | yes | Step end (null while pending). |
| `reason_category` | string | yes | KYC: document_quality, mismatch, timeout, other. AA: bank_timeout, denied, technical. Mandate: our own categories |
| `amount_band` | string | yes | Mandate max amount band |

### 4.5 `loans`: 8,017 rows

**Grain:** One row per disbursed loan (core banking view).

**Why it exists:** What the lender's core system shows: status, closure, a coarse default flag, tenure band and amount band. It holds no days past due or balance.

**Watch out:** `account_status`, `closed_at`, `closure_type`, `defaulted_at` and `lender_band_latest` are extract-time snapshots that leak the future. `lender_band_latest` becomes band 4 after default.

**Lender band now:** band_1 3,483, band_2 2,729, band_3 939, band_4 781 (snapshot; compare with the band at decision).

| Column | Type | Null | Meaning |
|---|---|---|---|
| `loan_id` | string |  | Loan id (LN + person + number). |
| `application_ref` | string |  | Application id (APP + person + number). |
| `unit_id` | string |  | Person key used across all tables (B + 7 digits). One person = one lead the lender can see. |
| `account_status` | string |  | 'defaulted' is a coarse lender flag (90+ days past due under the lender's rule): proposed extension, no days or balances Values: active, dormant, closed, defaulted. |
| `opened_at` | timestamp |  | Disbursal time (loans) or case open time (cases). |
| `closed_at` | timestamp | yes | Closure time. |
| `closure_type` | string | yes | matured, prepaid or foreclosed (cooling-off exit). Values: matured, prepaid, foreclosed. |
| `defaulted_at` | timestamp | yes | When the lender flag was set (a few days after 90 DPD). Never available before then |
| `tenure_band` | string |  | Flagged: workbook marks tenure Skip; banded months |
| `disbursed_amount_band` | string |  | Disbursed amount band (null until disbursed). |
| `lender_band_latest` | string | yes | EXTRACT-TIME snapshot of the lender band (leakage trap) Values: band_1, band_2, band_3, band_4. |

### 4.6 `emi_payments`: 98,785 rows

**Grain:** One row per EMI payment attempt.

**Why it exists:** Repayment behaviour as the payment vendor and core banking see it: attempts, failures with reasons, method (autopay or manual).

**Watch out:** Most EMIs are small, so `amount_band` is mostly `0-10k` (the bands are loan-size bands). The visible outcome of an instalment is the sequence of attempts, not a state name.

| Column | Type | Null | Meaning |
|---|---|---|---|
| `payment_id` | string |  | Payment attempt id. |
| `loan_id` | string |  | Loan id (LN + person + number). |
| `unit_id` | string |  | Person key used across all tables (B + 7 digits). One person = one lead the lender can see. |
| `instalment_no` | int |  | 1 to tenure. |
| `due_date` | timestamp |  | Due date of the instalment (06:00 UTC on the due day). |
| `status` | string |  | Final status of this attempt: captured or failed Values: created, authorised, captured, failed, refunded. |
| `method` | string |  | How it was done (KYC: ekyc_otp, digilocker, video_kyc, manual_document; mandate: upi_autopay or emandate). Values: upi_autopay, emandate, manual_upi, netbanking. |
| `amount_band` | string |  | Amount band (mandate maximum, or EMI amount). |
| `created_at` | timestamp |  | When the row was created. |
| `error_category` | string | yes | insufficient_funds, technical, mandate_inactive or bank_decline. Values: insufficient_funds, technical, mandate_inactive, bank_decline. |
| `attempt_no` | int |  | 1 for the first attempt, 2 for a retry. |

### 4.7 `service_cases`: 7,100 rows

**Grain:** One row per collections, complaint or dispute case.

**Why it exists:** Drives the marketing hold. It carries a suppression flag only, with no money detail and no days past due.

**Watch out:** A collections case means the person is late. It is a strong future-leaking signal when read after the fact.

**Status:** closed 5,393, open 1,547, in_progress 137, resolved 23.

| Column | Type | Null | Meaning |
|---|---|---|---|
| `case_id` | string |  | Case id. |
| `unit_id` | string |  | Person key used across all tables (B + 7 digits). One person = one lead the lender can see. |
| `status` | string |  | Current status. Values: open, in_progress, resolved, closed. |
| `category` | string |  | Case type (collections, complaint, dispute, grievance) or message category (regulatory, transactional, promotional). Values: dispute, complaint, collections, grievance. |
| `opened_at` | timestamp |  | Disbursal time (loans) or case open time (cases). |
| `closed_at` | timestamp | yes | Closure time. |
| `suppress_marketing` | bool |  | True means marketing is held while the case is open. |

### 4.8 `actions`: 376,706 rows

**Grain:** One row per decision point, legacy send or transactional message.

**Why it exists:** Merges messages, decisions, tasks and agent calls. It records what the policy considered, what was blocked and why, the propensity, and the message outcome.

**Watch out:** Legacy rows have no propensity. Randomised rows have `propensity` in (0,1]. `expected_value` is empty. `state` is filled from `state_history` at decision time.

| Column | Type | Null | Meaning |
|---|---|---|---|
| `action_id` | string |  | Decision or send id. |
| `unit_id` | string |  | Person key used across all tables (B + 7 digits). One person = one lead the lender can see. |
| `person_key` | string |  | HMAC-SHA-256 of the normalised phone number (hash only; the raw phone is never stored). Two people can share a key when they share a phone. |
| `application_ref` | string | yes | Application id (APP + person + number). |
| `record_kind` | string |  | decision (policy decision point), legacy_send (old rule-based send), transactional (regulatory/transactional message). Values: legacy_send, decision, transactional. |
| `regime` | string |  | legacy_targeting or randomised_holdout. Values: legacy_targeting, randomised_holdout. |
| `decided_at` | timestamp |  | When the decision was taken. |
| `state` | string | yes | Filled from state_history |
| `trigger` | string |  | Why: stall, lead, emi_due, topup, winback, legacy or service. Values: stall, lead, emi_due, topup, winback, legacy, service. |
| `chosen_action` | string |  | do_nothing, nudge, agent_call, fee_waiver, offer, emi_nudge, transactional or regulatory. Values: do_nothing, nudge, agent_call, fee_waiver, offer, emi_nudge, transactional, regulatory. |
| `channel` | string | yes | Acquisition or message channel. |
| `category` | string | yes | regulatory = EMI reminders, pre-debit notices, statements, KFS: never held out, never chosen by the policy Values: transactional, regulatory, promotional. |
| `template` | string | yes | Message template name. |
| `message_id` | string | yes | Message id. |
| `campaign_id` | string | yes | Campaign the event belongs to (null when none). |
| `sent_at` | timestamp | yes | Send time. |
| `final_status` | string | yes | Latest message status: sent, delivered, opened, clicked, bounced, failed, unsubscribed. Values: sent, delivered, opened, clicked, bounced, failed, unsubscribed. |
| `options_considered` | json | yes | JSON of actions the policy could choose, with cost. |
| `blocked_actions` | json | yes | JSON of actions blocked, each with a reason code. |
| `reason_codes` | json | yes | JSON list of guardrail codes that applied. |
| `propensity` | float | yes | Exploration policy probability of the chosen action |
| `expected_value` | float | yes | Null: no trained model yet |
| `model_versions` | string | yes | exploration_policy_v0 for randomised decisions. |
| `rule_version` | string | yes | State-rule version (bfsi_rules_v0.1). |
| `needs_approval` | bool |  | True when a fee waiver needs approval (becomes a task). |
| `in_holdout` | bool |  | True when the action was blocked only because the person is in the holdout. |
| `holdout_group` | string | yes | control = held out of optional nudges (8%), treated = eligible. Values: control, treated. |
| `task_id` | string | yes | CRM task id. |
| `task_target` | string | yes | agent_call_list or crm_task. Values: agent_call_list, crm_task. |
| `task_status` | string | yes | open, done, ignored or overridden. Values: open, done, ignored, overridden. |
| `task_due_at` | timestamp | yes | Task due time. |
| `task_owner_id` | string | yes | Pseudo owner id. |
| `task_capacity_bucket` | string | yes | low, medium or high (agent capacity at the time). |
| `disposition` | string | yes | Outcome of an agent call. Values: connected, not_reachable, callback_requested, not_interested, application_completed. |
| `call_duration_s` | int | yes | Call length in seconds. |

### 4.9 `state_history`: 308,316 rows

**Grain:** One row per state stay per person.

**Why it exists:** Output of the reference state engine run on the visible events. A pipeline can compare its own engine against it.

**Watch out:** Built from noisy events, so it differs a little from the hidden `state_truth`.

| Column | Type | Null | Meaning |
|---|---|---|---|
| `unit_id` | string |  | Person key used across all tables (B + 7 digits). One person = one lead the lender can see. |
| `state` | string |  | Lifecycle state. |
| `entered_at` | timestamp |  | When the state started. |
| `exited_at` | timestamp | yes | When it ended (null = still in it). |
| `entered_by` | string |  | event (an event caused it) or silence (a timer: no activity for N days). Values: event, silence. |
| `flags` | json |  | JSON: collections_open, dispute_open, no_marketing_consent, in_holdout. |
| `rule_version` | string |  | State-rule version (bfsi_rules_v0.1). |

### 4.10 `campaigns`: 10,977 rows

**Grain:** Two row types in one table: `map` (campaign dictionary) and `ad_daily` (daily spend, clicks, impressions).

**Why it exists:** Cost side of acquisition: cost per click and per lead can be computed against `events.campaign_id`.

**Watch out:** Costs are planted, not measured.

| Column | Type | Null | Meaning |
|---|---|---|---|
| `row_type` | string |  | map (campaign dictionary) or ad_daily (daily ad spend). Values: map, ad_daily. |
| `campaign_id` | string |  | Campaign the event belongs to (null when none). |
| `system` | string |  | Ad or messaging system. |
| `system_campaign_id` | string |  | Id in that system. |
| `name_hash` | string |  | Hash of the campaign name. |
| `channel` | string |  | Acquisition or message channel. |
| `date` | timestamp | yes | Day of the spend row. |
| `cost` | float | yes | Ad cost in INR. |
| `clicks` | int | yes | Clicks. |
| `impressions` | int | yes | Impressions. |

### Hidden tables (folder `hidden/`)

#### `person_truth`: 100,000 rows

**Grain:** One row per person.

**Why it exists:** The hidden causes: true type, income, true risk, behavioural scores and the planted effect of each action. The validator uses it to check that estimates recover the planted truth.

| Column | Type | Null | Meaning |
|---|---|---|---|
| `unit_id` | string |  | Person key used across all tables (B + 7 digits). One person = one lead the lender can see. |
| `hidden_type` | string |  | True borrower type: short_term_cash, planned_big_ticket, debt_consolidation, rate_shopper, repeat_borrower, one_time. |
| `type_changes` | json |  | JSON list of later type changes. |
| `employment_type` | string |  | salaried or self_employed. Values: salaried, self_employed. |
| `age` | int |  | Age in years. |
| `income_annual` | float |  | True annual income (INR). |
| `loan_to_income` | float |  | Requested amount divided by annual income. |
| `true_risk_z` | float |  | Standardised true credit risk. The lender band is this plus noise. |
| `lender_band_true_noise` | float |  | The noise added to get the lender band. |
| `kyc_friction` | float |  | 0 to 1: how hard KYC is for this person. |
| `doc_quality` | float |  | 0 to 1: quality of documents. |
| `urgency` | float |  | 0 to 1: how urgently they need money. |
| `shopping_around` | float |  | 0 to 1: comparing lenders. |
| `mandate_failure_propensity` | float |  | 0 to 1: chance of mandate trouble. |
| `prepay_propensity` | float |  | 0 to 1. |
| `topup_propensity` | float |  | 0 to 1. |
| `uplift_nudge` | float |  | Planted true effect of a nudge on resuming an application (probability points). |
| `uplift_agent_call` | float |  | Same for an agent call. |
| `uplift_fee_waiver` | float |  | Same for a fee waiver. |
| `uplift_offer` | float |  | Same for a pre-approved offer. |
| `uplift_emi_nudge` | float |  | Planted effect of an EMI nudge on repayment stress. |
| `reacts_badly` | bool |  | Sleeping dog: marketing makes this person worse (negative planted uplift). |
| `fraud_flag` | bool |  | Identity-fraud person. |
| `stacking` | bool |  | Holds several live loans. |
| `shared_phone_with` | string | yes | Another unit that shares this phone, if any. |
| `anon_ids` | json |  | JSON list of this person's anonymous ids. |
| `geo_tier` | string |  | City tier: metro, tier1, tier2, tier3, rural. |

#### `application_truth`: 51,062 rows

**Grain:** One row per application.

**Why it exists:** Exact amounts, rate, term, EMI, the per-instalment pay path, the highest days past due and the true default label with its finality flag.

| Column | Type | Null | Meaning |
|---|---|---|---|
| `application_ref` | string |  | Application id (APP + person + number). |
| `unit_id` | string |  | Person key used across all tables (B + 7 digits). One person = one lead the lender can see. |
| `kind` | string |  | natural = would have happened anyway, incremental = caused by an action. Values: natural, incremental. |
| `cause_decision_id` | string | yes | Decision that caused an incremental application. |
| `requested_amount` | float |  | Exact requested amount (INR). |
| `sanctioned_amount` | float | yes | Exact sanctioned amount. |
| `disbursed_amount` | float | yes | Exact disbursed amount. |
| `apr` | float | yes | Annual rate (decimal). |
| `tenure_months` | int | yes | Exact term in months. |
| `fee_pct` | float | yes | Processing fee share. |
| `emi_amount` | float | yes | Exact EMI. |
| `true_default` | bool | yes | 90+ DPD within 12 months on book; null when not disbursed |
| `label_final` | bool |  | Loan old enough (15+ months) for the default label to be final |
| `first_dpd90_at` | timestamp | yes | Time the loan reached 90 days past due. |
| `pay_path` | json | yes | Per instalment: state, days late |
| `max_dpd` | int | yes | Highest days past due reached by the extract date. |
| `prepay_month` | int | yes | Instalment at which the loan was prepaid. |
| `p_default_hint` | float | yes | A rough default probability hint from true risk (for sanity checks only). |

#### `state_truth`: 308,674 rows

**Grain:** One row per state stay.

**Why it exists:** The same state rules run on the clean, un-noised, fully linked events. The gap to `state_history` is the cost of noise.

| Column | Type | Null | Meaning |
|---|---|---|---|
| `unit_id` | string |  | Person key used across all tables (B + 7 digits). One person = one lead the lender can see. |
| `state` | string |  | Lifecycle state. |
| `entered_at` | timestamp |  | When the state started. |
| `exited_at` | timestamp | yes | When it ended (null = still in it). |

#### `noise_log`: 951,713 rows

**Grain:** One row per injected defect.

**Why it exists:** Every defect injected, so a cleaning step can be scored against what was actually broken.

| Column | Type | Null | Meaning |
|---|---|---|---|
| `event_id` | string | yes | Unique id of the event row (duplicates get a -D suffix). |
| `defect` | string |  | duplicate, missing_field, wrong_timestamp, late, out_of_order, bot, shared_device or tracking_gap. Values: duplicate, missing_field, wrong_timestamp, late, out_of_order, bot, shared_device, tracking_gap. |
| `detail` | json |  | JSON with defect details. |

Planted true uplift by hidden type (mean, probability points; illustrative planted values, not measurements):

| Type | Nudge | Agent call | Fee waiver | Offer | EMI nudge |
|---|---:|---:|---:|---:|---:|
| debt_consolidation | 0.040 | 0.091 | 0.060 | 0.040 | 0.030 |
| one_time | 0.019 | 0.029 | 0.009 | 0.009 | 0.019 |
| planned_big_ticket | 0.040 | 0.101 | 0.080 | 0.029 | 0.019 |
| rate_shopper | 0.019 | 0.040 | 0.121 | 0.030 | 0.009 |
| repeat_borrower | 0.050 | 0.060 | 0.029 | 0.121 | 0.030 |
| short_term_cash | 0.080 | 0.121 | 0.029 | 0.019 | 0.050 |

## 5. Labels and targets you can build

| Label | Definition | Built from | Size at 100,000 people |
|---|---|---|---|
| Default (12 months) | 90+ days past due within 12 months of disbursal. Final only for loans 15+ months old | `application_truth.true_default` with `label_final` (hidden, for training targets in the generator world); visible proxy: `loans.defaulted_at` | 3,806 final loans, 178 defaults |
| Application resumes (7 or 30 days) | The application shows any new step or stage event after a stall decision | `actions` (trigger stall, with `application_ref`) joined to `events` | 54,275 stall decision rows (all periods) |
| Lead starts an application | A new application within 7 or 30 days of a lead decision | `actions` (trigger lead) and `applications` | 65,623 lead decision rows |
| EMI first-attempt failure | Attempt 1 of an instalment failed | `emi_payments` (attempt_no = 1) | 84,767 first attempts |
| Late or missed instalment | Instalment state late or missed | hidden `application_truth.pay_path` | 84,954 instalments |
| Top-up taken | A top-up application after 6 on-time EMIs | `applications` (kind top_up) | 1,111 applications |
| Win-back | A win-back application after closure | `applications` (kind win_back) | 538 applications |
| Incremental application | Application caused by an action (planted truth) | `application_truth.kind` | 3,515 with a cause decision |

Funnel labels follow point-in-time rules: a row is final only when decision time plus horizon plus a 45-day buffer is on or before the extract time, so late and out-of-order events cannot change it afterwards. Only the randomised period (months 19 to 36) supports uplift estimates.

## 6. Leakage traps built in on purpose

| Column | Why it leaks |
|---|---|
| `loans.lender_band_latest` | Moves to band 4 after default. The band at decision is `applications.risk_band` |
| `loans.account_status`, `closed_at`, `closure_type`, `defaulted_at` | Extract-time state of the loan, including the default |
| `applications.stage`, `stage_changed_at` | Final stage, not the stage at prediction time |
| `borrowers.applications_count`, `loans_count` | Counts including the future |
| `borrowers.*_consent` | Latest consent, not consent at the time |
| `events.ingested_at` | A feature may only use events whose `ingested_at` is on or before the decision time |

Full rules: `docs/q54_leakage_rules.md`.

## 7. Parameters and how sure we are

All 161 settings are in `docs/parameters_report.md`, each graded: **A** verified from an official source (4), **B** researched benchmark with low confidence (18), **C** our assumption or calibration (133), **D** placeholder, client data needed (6). Grade C and D settings include the funnel pass rates beyond the default chain, repayment stress, cure rates, planted uplifts and messaging response. They were tuned until a 30,000-person run matched the answers file ranges; a real lender sample replaces them.

Not verified at all: the 80% AA monthly success floor from 1 December 2026, TRAI promotional rules (the 10:00 to 19:00 window is our assumption), DPDP consent-manager dates (law-firm summaries only), Diwali and festive dates.

## 8. Validation (125 checks, real results)

125 of 125 checks pass on the 100,000-person run (`docs/validation_report_dev_100k.md`). They cover schema and allowed values, referential integrity, privacy (no raw phone, email, income, days past due or exact amount in visible tables), leakage (no hidden imports; traps exist), distributions against the answers file, noise rates and lags, guardrails (holdout, consent, collections hold, regulatory messages), recoverability of hidden types and bands, uplift recovery in the randomised period, label finality and state-engine agreement. Twelve tests also run with `pytest`.

**Several checks use wide tolerances, so a pass is not a claim of exact match.** The weak spots:
1. Default by band: band 2 at 3.6% is just under the 4 to 6% placeholder; band 4 at 25% is above the 10 to 15% placeholder and rests on 112 final loans.
2. Defaults do not peak in months 3 to 9 (Q28). The monthly hazard is flat plus a small drift; 66% of defaulters' first missed instalment falls in months 3 to 9, but no peak is planted.
3. EMI first-attempt bounce is 14.7%; Q33 says 5 to 12% and Q31 implies about 15%. The answers disagree.
4. Prepaid loans are 24.9% of closed loans; Q34 says 10 to 20% of loans prepay before term (different denominators).
5. Legacy-period targeting is only mildly biased (78% of sends go to bands 1 and 2, against a 70% base).
6. Randomised uplift estimates for nudge and agent call are below the planted means because people who would have returned anyway dilute them (agent call 0.042 against 0.09). Fee waiver and offer match more closely.
7. 246 promotional messages were sent while a collections or dispute case was open, under the 0.3% tolerance but not zero (a case can open between a decision and its send time).
8. EMI amount bands are coarse: about 92% of EMIs fall in `0-10k` because the bands are loan-size bands.
9. Not modelled: part-payments, restructuring, a pre-approved-offer holder flag, bureau data, collections recovery and legal steps, regulation changes over time.

## 9. What this data can and cannot prove

**It can show** that the pipeline runs end to end on messy, late and duplicated data; that identity stitching, the state engine and point-in-time labels work; that guardrails, holdout and regulatory messages behave as specified; that leakage handling catches planted traps; and that an uplift method can be tested against planted effects in the randomised period.

**It cannot show** that real borrowers behave like this; that any approval, default, roll or cure rate is right; that a model that works here works on a real book; anything about bureau data or collections strategy; or per-action uplift at small sizes. At 10,000 people there are only 784 loans, so loan-level rates are noisy; at 100,000 people there are 8,017.

## 10. How to generate and where files are

```
pip install pyarrow pyyaml pandas numpy scikit-learn pytest
python -m vynqe_synth generate --pack bfsi --preset dev --seed 42 --out ./out        # 100,000 people, about 2.5 minutes
python -m vynqe_synth generate --pack bfsi --preset tiny --n 10000 --out ./out_10k   # 10,000 people, about 12 seconds
python -m vynqe_synth validate --out ./out
python -m pytest tests
```
Output folders: `visible/` (10 parquet tables), `hidden/` (4 parquet tables), `schemas/` (JSON contracts), `reports/` (row counts, validation). Add `--csv` for CSV copies. The package also contains `docs/` (parameters report, table dictionary, leakage rules, changelog, validation reports) and a 1,000-person `sample_1000/`.
