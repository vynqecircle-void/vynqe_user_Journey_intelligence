# Table dictionary: B2B SaaS pack

Unit = account (`unit_id` = `account_id`). Timestamps are UTC. No raw name, email, phone, address, ID or exact amount appears in visible tables: keyed hashes and bands only.

## Visible tables (10)

### accounts
One row per account: bands only. Also the identity map (one ref per system) and the whole-account holdout assignment.

| Column | Type | Null | Allowed values | Description |
|---|---|---|---|---|
| `account_id` | string |  |  |  |
| `segment` | string |  | SMB, MM, ENT |  |
| `industry_band` | string |  |  |  |
| `employee_band` | string |  |  |  |
| `region` | string |  | north_america, emea, apac, india |  |
| `source` | string |  | inbound, outbound, partner, event, referral, competitor_displacement |  |
| `created_at` | timestamp |  |  |  |
| `first_won_at` | timestamp | yes |  |  |
| `status` | string |  | prospect, customer, churned, lost | EXTRACT-TIME snapshot (leakage trap) |
| `current_plan` | string | yes | starter, team, business, enterprise | EXTRACT-TIME snapshot |
| `arr_band` | string | yes | <5k, 5-10k, 10-25k, 25-50k, 50-100k, 100-250k, 250k+ | EXTRACT-TIME snapshot |
| `renewal_at` | timestamp | yes |  | EXTRACT-TIME snapshot of the current term end |
| `strategic_flag` | bool |  |  |  |
| `named_csm` | bool |  |  |  |
| `regime_first_seen` | string |  | legacy_targeting, randomised_holdout |  |
| `holdout_group` | string |  | control, treated |  |
| `holdout_assigned_at` | timestamp |  |  |  |
| `holdout_share` | float |  |  |  |
| `holdout_strategy` | string |  | random_hash |  |
| `crm_ref` | string |  |  |  |
| `billing_ref` | string | yes |  |  |
| `cs_ref` | string | yes |  |  |
| `domain_key` | string |  |  | HMAC of the company domain; no company names |

### contacts
One row per person. Leads are merged in here (lead_* columns).

| Column | Type | Null | Allowed values | Description |
|---|---|---|---|---|
| `person_key` | string |  |  | HMAC-SHA-256 of normalised work or personal email |
| `account_id` | string | yes |  | Null when unmatched |
| `contact_ref` | string |  |  |  |
| `role` | string |  | champion, economic_buyer, technical, end_user |  |
| `seniority_band` | string |  | ic, manager, director, vp, c_level |  |
| `email_consent` | string |  | granted, denied, unknown, withdrawn | EXTRACT-TIME snapshot of marketing email consent; history in consent_change events |
| `personal_email` | bool |  |  |  |
| `first_seen_at` | timestamp |  |  |  |
| `left_account_at` | timestamp | yes |  |  |
| `lead_status` | string | yes | new, contacted, qualified, converted, lost | Set for the contact that came in as a lead |
| `lead_source` | string | yes |  |  |
| `lead_created_at` | timestamp | yes |  |  |
| `lead_converted_at` | timestamp | yes |  |  |
| `is_product_user` | bool |  |  |  |

### events
Canonical event stream. Web, forms, consent, messages, CRM, e-sign, tickets, CTAs, health bands, registrations, billing and outcomes.

| Column | Type | Null | Allowed values | Description |
|---|---|---|---|---|
| `event_id` | string |  |  |  |
| `source_event_id` | string |  |  | object:id:status (brief rule 4) |
| `event_type` | string |  | identify, consent_change, link_click, page_view, decision_made, message_status, record_created, record_status_changed, outcome_confirmed |  |
| `source_system` | string |  | ga4, hubspot, salesforce, stripe, zendesk, gainsight, docusign, cvent, amplitude, okta, klaviyo, decision_service, outcome_checker, google_ads, meta_ads |  |
| `person_key` | string | yes |  |  |
| `anonymous_id` | string | yes |  |  |
| `unit_id` | string | yes |  | account_id |
| `occurred_at` | timestamp |  |  |  |
| `ingested_at` | timestamp |  |  |  |
| `channel` | string | yes | web, email, call, meeting, in_app, paid_search, paid_social, partner, event, referral, organic, direct, webinar |  |
| `campaign_id` | string | yes |  |  |
| `placement_id` | string | yes |  |  |
| `consent_status` | string | yes | granted, denied, unknown, withdrawn |  |
| `properties` | json |  |  |  |

### opportunities
One row per deal: new, expansion, renewal and win-back. E-sign envelope merged in. Stage history is in events.

| Column | Type | Null | Allowed values | Description |
|---|---|---|---|---|
| `opp_id` | string |  |  |  |
| `account_id` | string |  |  |  |
| `type` | string |  | new, expansion, renewal, win_back |  |
| `stage` | string |  | discovery, evaluation, proposal, negotiation, closed_won, closed_lost | EXTRACT-TIME snapshot; history in events |
| `amount_band` | string |  | <5k, 5-10k, 10-25k, 25-50k, 50-100k, 100-250k, 250k+ |  |
| `discount_band` | string | yes | none, 1-10, 10-20, 20+ |  |
| `created_at` | timestamp |  |  |  |
| `close_date` | timestamp | yes |  | Expected close while open, actual when closed |
| `closed_at` | timestamp | yes |  | EXTRACT-TIME snapshot |
| `is_won` | bool | yes |  | EXTRACT-TIME snapshot |
| `loss_category` | string | yes | price, competitor, no_decision, timing, product_gap, champion_left |  |
| `competitor_flag` | bool |  |  |  |
| `incumbent_vendor_band` | string | yes | known, unknown |  |
| `incumbent_contract_end` | timestamp | yes |  |  |
| `rep_id` | string |  |  |  |
| `legal_review` | bool |  |  |  |
| `esign_status` | string | yes | created, sent, delivered, signed, completed, declined, voided | DocuSign envelope status (EXTRACT-TIME) |
| `esign_changed_at` | timestamp | yes |  |  |

### product_usage_daily
Account x person x feature x day, active days only. Logins are rows with feature=login.

| Column | Type | Null | Allowed values | Description |
|---|---|---|---|---|
| `account_id` | string | yes |  | Null for unmatched users |
| `person_key` | string |  |  |  |
| `feature` | string |  |  |  |
| `day` | timestamp |  |  |  |
| `num_events` | int |  |  |  |
| `num_minutes` | float |  |  |  |
| `session_count` | int |  |  |  |
| `source_system` | string |  | amplitude, pendo |  |
| `ingested_at` | timestamp |  |  |  |

### subscriptions
One row per plan period (amendments create a new version; Zuora-style Expired marks an old version). A term that ends with no successor is a lapse.

| Column | Type | Null | Allowed values | Description |
|---|---|---|---|---|
| `subscription_id` | string |  |  |  |
| `account_id` | string |  |  |  |
| `version` | int |  |  |  |
| `plan` | string |  | starter, team, business, enterprise |  |
| `seats_bought` | int |  |  |  |
| `seats_active_band` | string |  | <25%, 25-50%, 50-75%, 75%+ | EXTRACT-TIME snapshot (leakage trap) |
| `billing_interval` | string |  | monthly, annual |  |
| `term_months` | int |  |  |  |
| `start_at` | timestamp |  |  |  |
| `end_at` | timestamp |  |  |  |
| `auto_renew_flag` | bool |  |  |  |
| `cancel_requested` | bool |  |  |  |
| `status` | string |  | trialing, active, past_due, paused, pending, cancelled, expired | EXTRACT-TIME snapshot |
| `status_changed_at` | timestamp |  |  |  |
| `pause_collection` | bool |  |  |  |
| `collection_method` | string |  | charge_automatically, send_invoice |  |
| `trial_end` | timestamp | yes |  |  |
| `mrr_band` | string |  | <5k, 5-10k, 10-25k, 25-50k, 50-100k, 100-250k, 250k+ |  |

### invoices
One row per invoice with payment outcome and dunning attempts.

| Column | Type | Null | Allowed values | Description |
|---|---|---|---|---|
| `invoice_id` | string |  |  |  |
| `subscription_id` | string |  |  |  |
| `account_id` | string |  |  |  |
| `amount_band` | string |  | <5k, 5-10k, 10-25k, 25-50k, 50-100k, 100-250k, 250k+ |  |
| `issued_at` | timestamp |  |  |  |
| `due_at` | timestamp |  |  |  |
| `paid_at` | timestamp | yes |  |  |
| `status` | string |  | created, authorised, captured, failed, refunded | EXTRACT-TIME snapshot |
| `collection_method` | string |  | charge_automatically, send_invoice |  |
| `attempt_count` | int |  |  |  |
| `error_code` | string | yes |  |  |
| `disputed` | bool |  |  |  |
| `is_renewal` | bool |  |  |  |

### actions
One row per decision point or send: messages, decisions, rep and CSM tasks merged.

| Column | Type | Null | Allowed values | Description |
|---|---|---|---|---|
| `action_id` | string |  |  |  |
| `unit_id` | string |  |  |  |
| `person_key` | string | yes |  |  |
| `opp_id` | string | yes |  |  |
| `record_kind` | string |  | legacy_touch, decision, transactional |  |
| `regime` | string |  | legacy_targeting, randomised_holdout |  |
| `decided_at` | timestamp |  |  |  |
| `state` | string | yes | Lead, Opportunity, Competitor displacement, Onboarding, Active, Expansion, At-risk renewal, Churned, Lost | Filled from state_history |
| `trigger` | string |  | lead_stall, opp_stall, onboarding, risk, expansion, winback, invoice, renewal_notice, security, legacy |  |
| `chosen_action` | string |  | do_nothing, email, rep_outreach, discount, exec_call, csm_task, transactional, regulatory |  |
| `channel` | string | yes | web, email, call, meeting, in_app, paid_search, paid_social, partner, event, referral, organic, direct, webinar |  |
| `category` | string | yes | transactional, regulatory, promotional | regulatory = billing notices, security alerts, legal terms: never held out, never chosen by the policy |
| `template` | string | yes |  |  |
| `message_id` | string | yes |  |  |
| `campaign_id` | string | yes |  |  |
| `sent_at` | timestamp | yes |  |  |
| `final_status` | string | yes | sent, delivered, opened, clicked, bounced, failed, unsubscribed |  |
| `options_considered` | json | yes |  |  |
| `blocked_actions` | json | yes |  |  |
| `reason_codes` | json | yes |  |  |
| `propensity` | float | yes |  | Exploration policy probability of the chosen action |
| `expected_value` | float | yes |  | Null: no trained model yet |
| `model_versions` | string | yes |  |  |
| `rule_version` | string | yes |  |  |
| `needs_approval` | bool |  |  |  |
| `in_holdout` | bool |  |  |  |
| `holdout_group` | string | yes | control, treated |  |
| `task_id` | string | yes |  |  |
| `task_target` | string | yes | csm_cta, crm_task |  |
| `task_status` | string | yes | open, done, ignored, overridden |  |
| `task_due_at` | timestamp | yes |  |  |
| `task_owner_id` | string | yes |  |  |
| `disposition` | string | yes | connected, not_reachable, meeting_booked, not_interested, replied |  |
| `call_duration_s` | int | yes |  |  |

### state_history
Output of the reference state engine run on the VISIBLE events.

| Column | Type | Null | Allowed values | Description |
|---|---|---|---|---|
| `unit_id` | string |  |  |  |
| `state` | string |  | Lead, Opportunity, Competitor displacement, Onboarding, Active, Expansion, At-risk renewal, Churned, Lost |  |
| `entered_at` | timestamp |  |  |  |
| `exited_at` | timestamp | yes |  |  |
| `entered_by` | string |  | event, silence, clock |  |
| `flags` | json |  |  |  |
| `rule_version` | string |  |  |  |

### campaigns
campaign_map and ad_spend_daily merged (row_type).

| Column | Type | Null | Allowed values | Description |
|---|---|---|---|---|
| `row_type` | string |  | map, ad_daily |  |
| `campaign_id` | string |  |  |  |
| `system` | string |  |  |  |
| `system_campaign_id` | string |  |  |  |
| `name_hash` | string |  |  |  |
| `channel` | string |  |  |  |
| `date` | timestamp | yes |  |  |
| `cost` | float | yes |  |  |
| `clicks` | int | yes |  |  |
| `impressions` | int | yes |  |  |

## Hidden tables (5, validation only, never import in feature, state or label code)

### account_truth
HIDDEN. True types, drivers, exact ACV, planted effect of each action and the true outcomes.

| Column | Type | Null | Allowed values | Description |
|---|---|---|---|---|
| `unit_id` | string |  |  |  |
| `kind` | string |  | base, new |  |
| `prospect_type` | string |  |  |  |
| `customer_type` | string |  |  |  |
| `fit_score` | float |  |  |  |
| `intent_stage` | string |  |  |  |
| `incumbent_lock_in` | string |  |  |  |
| `champion_exit_hazard` | float |  |  |  |
| `usage_decay_rate` | float |  |  |  |
| `decay_mode` | string |  | none, gradual, sudden |  |
| `budget_cycle_month` | int |  |  |  |
| `competitor_win_prob` | float |  |  |  |
| `expansion_headroom` | float |  |  |  |
| `acv` | float | yes |  |  |
| `seats_true` | int | yes |  |  |
| `integration_connected` | bool |  |  |  |
| `reacts_badly` | bool |  |  |  |
| `uplift_prospect` | json |  |  |  |
| `uplift_customer` | json |  |  |  |
| `p_win_base` | float | yes |  |  |
| `will_win` | bool |  |  |  |
| `churn_kind` | string | yes |  | cancelled, silent_lapse, involuntary or null |
| `churn_at` | timestamp | yes |  |  |
| `renewal_outcomes` | json | yes |  |  |
| `is_test_account` | bool |  |  |  |
| `duplicate_of` | string | yes |  |  |
| `champion_left_at` | timestamp | yes |  |  |

### contact_truth
HIDDEN. Which account a person really belongs to.

| Column | Type | Null | Allowed values | Description |
|---|---|---|---|---|
| `person_key` | string |  |  |  |
| `contact_ref` | string |  |  |  |
| `true_account` | string |  |  |  |
| `visible_account` | string | yes |  |  |
| `is_champion` | bool |  |  |  |
| `wrongly_matched` | bool |  |  |  |
| `also_in_account` | string | yes |  |  |

### opportunity_truth
HIDDEN. Exact amounts, true win probability with and without the action, and the true label.

| Column | Type | Null | Allowed values | Description |
|---|---|---|---|---|
| `opp_id` | string |  |  |  |
| `unit_id` | string |  |  |  |
| `p_win_true` | float |  |  |  |
| `p_win_no_action` | float |  |  |  |
| `cycle_days_true` | float |  |  |  |
| `amount` | float |  |  |  |
| `discount_pct` | float |  |  |  |
| `true_won` | bool |  |  |  |
| `true_loss_category` | string | yes |  |  |
| `label_final` | bool |  |  | Old enough for the outcome to be final |
| `cause_decision_id` | string | yes |  |  |

### state_truth
HIDDEN. Same state rules run on the clean, un-noised, fully linked event stream.

| Column | Type | Null | Allowed values | Description |
|---|---|---|---|---|
| `unit_id` | string |  |  |  |
| `state` | string |  | Lead, Opportunity, Competitor displacement, Onboarding, Active, Expansion, At-risk renewal, Churned, Lost |  |
| `entered_at` | timestamp |  |  |  |
| `exited_at` | timestamp | yes |  |  |

### noise_log
HIDDEN. Every injected defect.

| Column | Type | Null | Allowed values | Description |
|---|---|---|---|---|
| `event_id` | string | yes |  |  |
| `defect` | string |  | duplicate, missing_field, wrong_timestamp, late, out_of_order, bot, tracking_gap, duplicate_account, unmatched_user, wrongly_matched, test_account, multi_account_user |  |
| `detail` | json |  |  |  |
