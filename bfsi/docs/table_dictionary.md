# Table dictionary: BFSI pack

Generated from the table contracts in `vynqe_synth/packs/bfsi/schemas.py`. `null` = nullable column. Hidden tables are for validation only.

## Visible tables (10)

### `borrowers`

One row per person; also holds the identity map (one ref per system), marketing consent snapshot and holdout assignment. Leads live in events.

| Column | Type | Null | Allowed values | Description |
|---|---|---|---|---|
| `unit_id` | string |  |  |  |
| `person_key` | string |  |  | HMAC-SHA-256 of normalised phone; not unique when a phone is shared |
| `created_at` | timestamp |  |  |  |
| `first_application_at` | timestamp | null |  |  |
| `applications_count` | int |  |  | EXTRACT-TIME snapshot (leakage trap) |
| `loans_count` | int |  |  | EXTRACT-TIME snapshot (leakage trap) |
| `existing_customer` | bool |  |  | From core banking at first contact |
| `acquisition_channel` | string |  |  |  |
| `device_class` | string |  | android, ios, web_mobile, web_desktop |  |
| `geo_tier` | string | null | metro, tier1, tier2, tier3, rural | Flagged extension: not in workbook |
| `email_consent` | string |  | granted, denied, unknown, withdrawn | EXTRACT-TIME snapshot of MARKETING consent; history in consent_change events |
| `sms_consent` | string |  | granted, denied, unknown, withdrawn |  |
| `whatsapp_consent` | string |  | granted, denied, unknown, withdrawn |  |
| `do_not_market` | bool |  |  |  |
| `regime_first_seen` | string |  | legacy_targeting, randomised_holdout |  |
| `holdout_group` | string |  | control, treated |  |
| `holdout_assigned_at` | timestamp |  |  |  |
| `holdout_share` | float |  |  |  |
| `holdout_strategy` | string |  | random_hash |  |
| `los_customer_ref` | string |  |  |  |
| `salesforce_lead_ref` | string |  |  |  |
| `klaviyo_profile_ref` | string |  |  |  |
| `razorpay_ref` | string | null |  |  |
| `core_banking_ref` | string | null |  | Hashed CIF; set once a loan is disbursed |
| `trackflow_user_id` | string |  |  |  |
| `email_key` | string |  |  | HMAC of lowercased email |

### `events`

Canonical event stream. Leads, stage history, consent history, message status, decisions, risk-band updates and outcomes live here.

| Column | Type | Null | Allowed values | Description |
|---|---|---|---|---|
| `event_id` | string |  |  |  |
| `source_event_id` | string |  |  | object:id:status (brief rule 4) |
| `event_type` | string |  | identify, consent_change, link_click, qr_scan, quiz_started, quiz_step_answered, quiz_abandoned, quiz_completed, game_started, game_retry, game_quit, game_completed, page_view, decision_made, webhook_status, message_status, record_created, record_status_changed, outcome_confirmed |  |
| `source_system` | string |  | trackflow, salesforce, loan_origination, kyc, account_aggregator, docusign, razorpay, core_banking, service_collections, contact_centre, klaviyo, whatsapp, warehouse, decision_service, outcome_checker, google_ads, meta_ads |  |
| `person_key` | string | null |  |  |
| `anonymous_id` | string | null |  |  |
| `unit_id` | string | null |  |  |
| `occurred_at` | timestamp |  |  |  |
| `ingested_at` | timestamp |  |  |  |
| `channel` | string | null | web, app, email, sms, whatsapp, push, in_app, call, store, kiosk, paid_search, paid_social, affiliate, partner, referral, organic, branch |  |
| `campaign_id` | string | null |  |  |
| `placement_id` | string | null |  |  |
| `consent_status` | string | null | granted, denied, unknown, withdrawn |  |
| `properties` | json |  |  |  |

### `applications`

One row per loan application. Stage history is in events (record_status_changed).

| Column | Type | Null | Allowed values | Description |
|---|---|---|---|---|
| `application_ref` | string |  |  |  |
| `unit_id` | string |  |  |  |
| `product_code` | string |  | personal_loan |  |
| `application_kind` | string |  | new, top_up, win_back | Flagged extension |
| `created_at` | timestamp |  |  |  |
| `channel` | string | null | web, app, email, sms, whatsapp, push, in_app, call, store, kiosk, paid_search, paid_social, affiliate, partner, referral, organic, branch |  |
| `campaign_id` | string | null |  |  |
| `branch_code` | string | null |  |  |
| `stage` | string |  | applied, docs_pending, in_review, approved, offer_accepted, signed, rejected, disbursed | Snapshot at extract time; offer_accepted and signed are additions to confirm |
| `stage_changed_at` | timestamp |  |  |  |
| `rejection_reason_category` | string | null | policy, income, kyc, fraud, other |  |
| `requested_amount_band` | string |  |  |  |
| `sanctioned_amount_band` | string | null |  |  |
| `disbursed_amount_band` | string | null |  |  |
| `sanction_date` | timestamp | null |  |  |
| `disbursal_date` | timestamp | null |  |  |
| `decision_band` | string | null | approve, refer, decline |  |
| `risk_band` | string | null | band_1, band_2, band_3, band_4 | The lender's own band (noisy function of true risk); null until decided |
| `decision_id` | string | null |  | Set only when the person clicked or was called after a decision (observable attribution) |

### `application_steps`

One row per KYC attempt, Account Aggregator consent, data fetch, e-sign envelope or mandate set-up. AA consent is NOT marketing consent.

| Column | Type | Null | Allowed values | Description |
|---|---|---|---|---|
| `step_id` | string |  |  |  |
| `application_ref` | string |  |  |  |
| `unit_id` | string |  |  |  |
| `step_type` | string |  | kyc, aa_consent, aa_fetch, esign, mandate |  |
| `external_id` | string |  |  | verification_id, consent_id, session_id, envelope_id or token_id |
| `method` | string | null | ekyc_otp, digilocker, video_kyc, manual_document, account_aggregator, docusign, upi_autopay, emandate |  |
| `status` | string |  | pending, verified, failed, expired, active, rejected, paused, revoked, completed, created, sent, delivered, signed, declined, voided, cancelling, cancelled | Final status at extract time |
| `attempt_no` | int |  |  |  |
| `started_at` | timestamp |  |  |  |
| `completed_at` | timestamp | null |  |  |
| `reason_category` | string | null |  | KYC: document_quality, mismatch, timeout, other. AA: bank_timeout, denied, technical. Mandate: our own categories |
| `amount_band` | string | null |  | Mandate max amount band |

### `loans`

One row per disbursed loan (core banking view).

| Column | Type | Null | Allowed values | Description |
|---|---|---|---|---|
| `loan_id` | string |  |  |  |
| `application_ref` | string |  |  |  |
| `unit_id` | string |  |  |  |
| `account_status` | string |  | active, dormant, closed, defaulted | 'defaulted' is a coarse lender flag (90+ days past due under the lender's rule): proposed extension, no days or balances |
| `opened_at` | timestamp |  |  |  |
| `closed_at` | timestamp | null |  |  |
| `closure_type` | string | null | matured, prepaid, foreclosed |  |
| `defaulted_at` | timestamp | null |  | When the lender flag was set (a few days after 90 DPD). Never available before then |
| `tenure_band` | string |  |  | Flagged: workbook marks tenure Skip; banded months |
| `disbursed_amount_band` | string |  |  |  |
| `lender_band_latest` | string | null | band_1, band_2, band_3, band_4 | EXTRACT-TIME snapshot of the lender band (leakage trap) |

### `emi_payments`

One row per EMI payment attempt.

| Column | Type | Null | Allowed values | Description |
|---|---|---|---|---|
| `payment_id` | string |  |  |  |
| `loan_id` | string |  |  |  |
| `unit_id` | string |  |  |  |
| `instalment_no` | int |  |  |  |
| `due_date` | timestamp |  |  |  |
| `status` | string |  | created, authorised, captured, failed, refunded | Final status of this attempt: captured or failed |
| `method` | string |  | upi_autopay, emandate, manual_upi, netbanking |  |
| `amount_band` | string |  |  |  |
| `created_at` | timestamp |  |  |  |
| `error_category` | string | null | insufficient_funds, technical, mandate_inactive, bank_decline |  |
| `attempt_no` | int |  |  |  |

### `service_cases`

One row per dispute, complaint or collections case. Suppression flag only: no money detail, no days past due.

| Column | Type | Null | Allowed values | Description |
|---|---|---|---|---|
| `case_id` | string |  |  |  |
| `unit_id` | string |  |  |  |
| `status` | string |  | open, in_progress, resolved, closed |  |
| `category` | string |  | dispute, complaint, collections, grievance |  |
| `opened_at` | timestamp |  |  |  |
| `closed_at` | timestamp | null |  |  |
| `suppress_marketing` | bool |  |  |  |

### `actions`

One row per decision point or send: messages, decisions, tasks and agent calls merged.

| Column | Type | Null | Allowed values | Description |
|---|---|---|---|---|
| `action_id` | string |  |  |  |
| `unit_id` | string |  |  |  |
| `person_key` | string |  |  |  |
| `application_ref` | string | null |  |  |
| `record_kind` | string |  | legacy_send, decision, transactional |  |
| `regime` | string |  | legacy_targeting, randomised_holdout |  |
| `decided_at` | timestamp |  |  |  |
| `state` | string | null | Lead, Application started, KYC drop-off, Consent pending, In review, Offer pending, Signing and mandate pending, Rejected, Activated, Repaying, Late, Top-up eligible, Dormant | Filled from state_history |
| `trigger` | string |  | stall, lead, emi_due, topup, winback, legacy, service |  |
| `chosen_action` | string |  | do_nothing, nudge, agent_call, fee_waiver, offer, emi_nudge, transactional, regulatory |  |
| `channel` | string | null | web, app, email, sms, whatsapp, push, in_app, call, store, kiosk, paid_search, paid_social, affiliate, partner, referral, organic, branch |  |
| `category` | string | null | transactional, regulatory, promotional | regulatory = EMI reminders, pre-debit notices, statements, KFS: never held out, never chosen by the policy |
| `template` | string | null |  |  |
| `message_id` | string | null |  |  |
| `campaign_id` | string | null |  |  |
| `sent_at` | timestamp | null |  |  |
| `final_status` | string | null | sent, delivered, opened, clicked, bounced, failed, unsubscribed |  |
| `options_considered` | json | null |  |  |
| `blocked_actions` | json | null |  |  |
| `reason_codes` | json | null |  |  |
| `propensity` | float | null |  | Exploration policy probability of the chosen action |
| `expected_value` | float | null |  | Null: no trained model yet |
| `model_versions` | string | null |  |  |
| `rule_version` | string | null |  |  |
| `needs_approval` | bool |  |  |  |
| `in_holdout` | bool |  |  |  |
| `holdout_group` | string | null | control, treated |  |
| `task_id` | string | null |  |  |
| `task_target` | string | null | agent_call_list, crm_task |  |
| `task_status` | string | null | open, done, ignored, overridden |  |
| `task_due_at` | timestamp | null |  |  |
| `task_owner_id` | string | null |  |  |
| `task_capacity_bucket` | string | null |  |  |
| `disposition` | string | null | connected, not_reachable, callback_requested, not_interested, application_completed |  |
| `call_duration_s` | int | null |  |  |

### `state_history`

Output of the reference state engine run on the VISIBLE events.

| Column | Type | Null | Allowed values | Description |
|---|---|---|---|---|
| `unit_id` | string |  |  |  |
| `state` | string |  | Lead, Application started, KYC drop-off, Consent pending, In review, Offer pending, Signing and mandate pending, Rejected, Activated, Repaying, Late, Top-up eligible, Dormant |  |
| `entered_at` | timestamp |  |  |  |
| `exited_at` | timestamp | null |  |  |
| `entered_by` | string |  | event, silence |  |
| `flags` | json |  |  |  |
| `rule_version` | string |  |  |  |

### `campaigns`

campaign_map and ad_spend_daily merged (row_type).

| Column | Type | Null | Allowed values | Description |
|---|---|---|---|---|
| `row_type` | string |  | map, ad_daily |  |
| `campaign_id` | string |  |  |  |
| `system` | string |  |  |  |
| `system_campaign_id` | string |  |  |  |
| `name_hash` | string |  |  |  |
| `channel` | string |  |  |  |
| `date` | timestamp | null |  |  |
| `cost` | float | null |  |  |
| `clicks` | int | null |  |  |
| `impressions` | int | null |  |  |

## Hidden tables (4, folder `hidden/`)

### `person_truth`

HIDDEN. True type, income and employment, true risk and planted true effect of each action.

| Column | Type | Null | Allowed values | Description |
|---|---|---|---|---|
| `unit_id` | string |  |  |  |
| `hidden_type` | string |  |  |  |
| `type_changes` | json |  |  |  |
| `employment_type` | string |  | salaried, self_employed |  |
| `age` | int |  |  |  |
| `income_annual` | float |  |  |  |
| `loan_to_income` | float |  |  |  |
| `true_risk_z` | float |  |  |  |
| `lender_band_true_noise` | float |  |  |  |
| `kyc_friction` | float |  |  |  |
| `doc_quality` | float |  |  |  |
| `urgency` | float |  |  |  |
| `shopping_around` | float |  |  |  |
| `mandate_failure_propensity` | float |  |  |  |
| `prepay_propensity` | float |  |  |  |
| `topup_propensity` | float |  |  |  |
| `uplift_nudge` | float |  |  |  |
| `uplift_agent_call` | float |  |  |  |
| `uplift_fee_waiver` | float |  |  |  |
| `uplift_offer` | float |  |  |  |
| `uplift_emi_nudge` | float |  |  |  |
| `reacts_badly` | bool |  |  |  |
| `fraud_flag` | bool |  |  |  |
| `stacking` | bool |  |  |  |
| `shared_phone_with` | string | null |  |  |
| `anon_ids` | json |  |  |  |
| `geo_tier` | string |  |  |  |

### `application_truth`

HIDDEN. Exact amounts, terms, days-past-due path and the true default label.

| Column | Type | Null | Allowed values | Description |
|---|---|---|---|---|
| `application_ref` | string |  |  |  |
| `unit_id` | string |  |  |  |
| `kind` | string |  | natural, incremental |  |
| `cause_decision_id` | string | null |  |  |
| `requested_amount` | float |  |  |  |
| `sanctioned_amount` | float | null |  |  |
| `disbursed_amount` | float | null |  |  |
| `apr` | float | null |  |  |
| `tenure_months` | int | null |  |  |
| `fee_pct` | float | null |  |  |
| `emi_amount` | float | null |  |  |
| `true_default` | bool | null |  | 90+ DPD within 12 months on book; null when not disbursed |
| `label_final` | bool |  |  | Loan old enough (15+ months) for the default label to be final |
| `first_dpd90_at` | timestamp | null |  |  |
| `pay_path` | json | null |  | Per instalment: state, days late |
| `max_dpd` | int | null |  |  |
| `prepay_month` | int | null |  |  |
| `p_default_hint` | float | null |  |  |

### `state_truth`

HIDDEN. Same state rules run on the clean, un-noised, fully linked event stream.

| Column | Type | Null | Allowed values | Description |
|---|---|---|---|---|
| `unit_id` | string |  |  |  |
| `state` | string |  | Lead, Application started, KYC drop-off, Consent pending, In review, Offer pending, Signing and mandate pending, Rejected, Activated, Repaying, Late, Top-up eligible, Dormant |  |
| `entered_at` | timestamp |  |  |  |
| `exited_at` | timestamp | null |  |  |

### `noise_log`

HIDDEN. Every injected defect.

| Column | Type | Null | Allowed values | Description |
|---|---|---|---|---|
| `event_id` | string | null |  |  |
| `defect` | string |  | duplicate, missing_field, wrong_timestamp, late, out_of_order, bot, shared_device, tracking_gap |  |
| `detail` | json |  |  |  |
