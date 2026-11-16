"""BFSI personal-loan visible and hidden table contracts. Status values follow the workbook Status_maps sheet."""
from ...core.schema import Col, TableSchema

TS, S, I, F, B, J = "timestamp", "string", "int", "float", "bool", "json"
DEVICE = ("android", "ios", "web_mobile", "web_desktop")
CONSENT = ("granted", "denied", "unknown", "withdrawn")
TIERS = ("metro", "tier1", "tier2", "tier3", "rural")
REGIME = ("legacy_targeting", "randomised_holdout")
CHANNELS = ("web", "app", "email", "sms", "whatsapp", "push", "in_app", "call", "store", "kiosk", "paid_search",
            "paid_social", "affiliate", "partner", "referral", "organic", "branch")
EVENT_TYPES = ("identify", "consent_change", "link_click", "qr_scan", "quiz_started", "quiz_step_answered",
               "quiz_abandoned", "quiz_completed", "game_started", "game_retry", "game_quit", "game_completed",
               "page_view", "decision_made", "webhook_status", "message_status", "record_created",
               "record_status_changed", "outcome_confirmed")
SOURCES = ("trackflow", "salesforce", "loan_origination", "kyc", "account_aggregator", "docusign", "razorpay",
           "core_banking", "service_collections", "contact_centre", "klaviyo", "whatsapp", "warehouse",
           "decision_service", "outcome_checker", "google_ads", "meta_ads")
STAGES = ("applied", "docs_pending", "in_review", "approved", "offer_accepted", "signed", "rejected", "disbursed")
STEP_TYPES = ("kyc", "aa_consent", "aa_fetch", "esign", "mandate")
STEP_STATUS = ("pending", "verified", "failed", "expired", "active", "rejected", "paused", "revoked", "completed",
               "created", "sent", "delivered", "signed", "declined", "voided", "cancelling", "cancelled")
BANDS = ("band_1", "band_2", "band_3", "band_4")
PAYST = ("created", "authorised", "captured", "failed", "refunded")
MSG = ("sent", "delivered", "opened", "clicked", "bounced", "failed", "unsubscribed")
ACTIONS = ("do_nothing", "nudge", "agent_call", "fee_waiver", "offer", "emi_nudge", "transactional", "regulatory")
REASONS = ("no_consent", "unknown_consent", "aa_consent_only", "collections_hold", "dispute_hold", "mandate_inactive",
           "rep_engaged", "frequency_cap", "suitability_failed", "capacity_full", "approval_limit", "in_holdout")
STATES = ("Lead", "Application started", "KYC drop-off", "Consent pending", "In review", "Offer pending",
          "Signing and mandate pending", "Rejected", "Activated", "Repaying", "Late", "Top-up eligible", "Dormant")
TRIGGERS = ("stall", "lead", "emi_due", "topup", "winback", "legacy", "service")

borrowers = TableSchema("borrowers", (
    Col("unit_id", S), Col("person_key", S, desc="HMAC-SHA-256 of normalised phone; not unique when a phone is shared"),
    Col("created_at", TS), Col("first_application_at", TS, True),
    Col("applications_count", I, desc="EXTRACT-TIME snapshot (leakage trap)"),
    Col("loans_count", I, desc="EXTRACT-TIME snapshot (leakage trap)"),
    Col("existing_customer", B, desc="From core banking at first contact"),
    Col("acquisition_channel", S), Col("device_class", S, allowed=DEVICE),
    Col("geo_tier", S, True, TIERS, "Flagged extension: not in workbook"),
    Col("email_consent", S, allowed=CONSENT, desc="EXTRACT-TIME snapshot of MARKETING consent; history in consent_change events"),
    Col("sms_consent", S, allowed=CONSENT), Col("whatsapp_consent", S, allowed=CONSENT),
    Col("do_not_market", B), Col("regime_first_seen", S, allowed=REGIME),
    Col("holdout_group", S, allowed=("control", "treated")), Col("holdout_assigned_at", TS),
    Col("holdout_share", F), Col("holdout_strategy", S, allowed=("random_hash",)),
    Col("los_customer_ref", S), Col("salesforce_lead_ref", S), Col("klaviyo_profile_ref", S),
    Col("razorpay_ref", S, True), Col("core_banking_ref", S, True, desc="Hashed CIF; set once a loan is disbursed"),
    Col("trackflow_user_id", S), Col("email_key", S, desc="HMAC of lowercased email"),
), "One row per person; also holds the identity map (one ref per system), marketing consent snapshot and holdout assignment. Leads live in events.")

events = TableSchema("events", (
    Col("event_id", S), Col("source_event_id", S, desc="object:id:status (brief rule 4)"),
    Col("event_type", S, allowed=EVENT_TYPES), Col("source_system", S, allowed=SOURCES),
    Col("person_key", S, True), Col("anonymous_id", S, True), Col("unit_id", S, True),
    Col("occurred_at", TS), Col("ingested_at", TS), Col("channel", S, True, CHANNELS),
    Col("campaign_id", S, True), Col("placement_id", S, True), Col("consent_status", S, True, CONSENT),
    Col("properties", J),
), "Canonical event stream. Leads, stage history, consent history, message status, decisions, risk-band updates and outcomes live here.")

applications = TableSchema("applications", (
    Col("application_ref", S), Col("unit_id", S), Col("product_code", S, allowed=("personal_loan",)),
    Col("application_kind", S, allowed=("new", "top_up", "win_back"), desc="Flagged extension"),
    Col("created_at", TS), Col("channel", S, True, CHANNELS), Col("campaign_id", S, True), Col("branch_code", S, True),
    Col("stage", S, allowed=STAGES, desc="Snapshot at extract time; offer_accepted and signed are additions to confirm"),
    Col("stage_changed_at", TS), Col("rejection_reason_category", S, True, ("policy", "income", "kyc", "fraud", "other")),
    Col("requested_amount_band", S), Col("sanctioned_amount_band", S, True), Col("disbursed_amount_band", S, True),
    Col("sanction_date", TS, True), Col("disbursal_date", TS, True),
    Col("decision_band", S, True, ("approve", "refer", "decline")),
    Col("risk_band", S, True, BANDS, "The lender's own band (noisy function of true risk); null until decided"),
    Col("decision_id", S, True, desc="Set only when the person clicked or was called after a decision (observable attribution)"),
), "One row per loan application. Stage history is in events (record_status_changed).")

application_steps = TableSchema("application_steps", (
    Col("step_id", S), Col("application_ref", S), Col("unit_id", S), Col("step_type", S, allowed=STEP_TYPES),
    Col("external_id", S, desc="verification_id, consent_id, session_id, envelope_id or token_id"),
    Col("method", S, True, ("ekyc_otp", "digilocker", "video_kyc", "manual_document", "account_aggregator", "docusign",
                            "upi_autopay", "emandate")),
    Col("status", S, allowed=STEP_STATUS, desc="Final status at extract time"), Col("attempt_no", I),
    Col("started_at", TS), Col("completed_at", TS, True),
    Col("reason_category", S, True, desc="KYC: document_quality, mismatch, timeout, other. AA: bank_timeout, denied, technical. Mandate: our own categories"),
    Col("amount_band", S, True, desc="Mandate max amount band"),
), "One row per KYC attempt, Account Aggregator consent, data fetch, e-sign envelope or mandate set-up. AA consent is NOT marketing consent.")

loans = TableSchema("loans", (
    Col("loan_id", S), Col("application_ref", S), Col("unit_id", S),
    Col("account_status", S, allowed=("active", "dormant", "closed", "defaulted"),
        desc="'defaulted' is a coarse lender flag (90+ days past due under the lender's rule): proposed extension, no days or balances"),
    Col("opened_at", TS), Col("closed_at", TS, True), Col("closure_type", S, True, ("matured", "prepaid", "foreclosed")),
    Col("defaulted_at", TS, True, desc="When the lender flag was set (a few days after 90 DPD). Never available before then"),
    Col("tenure_band", S, desc="Flagged: workbook marks tenure Skip; banded months"),
    Col("disbursed_amount_band", S),
    Col("lender_band_latest", S, True, BANDS, "EXTRACT-TIME snapshot of the lender band (leakage trap)"),
), "One row per disbursed loan (core banking view).")

emi_payments = TableSchema("emi_payments", (
    Col("payment_id", S), Col("loan_id", S), Col("unit_id", S), Col("instalment_no", I), Col("due_date", TS),
    Col("status", S, allowed=PAYST, desc="Final status of this attempt: captured or failed"),
    Col("method", S, allowed=("upi_autopay", "emandate", "manual_upi", "netbanking")),
    Col("amount_band", S), Col("created_at", TS),
    Col("error_category", S, True, ("insufficient_funds", "technical", "mandate_inactive", "bank_decline")),
    Col("attempt_no", I),
), "One row per EMI payment attempt.")

service_cases = TableSchema("service_cases", (
    Col("case_id", S), Col("unit_id", S), Col("status", S, allowed=("open", "in_progress", "resolved", "closed")),
    Col("category", S, allowed=("dispute", "complaint", "collections", "grievance")),
    Col("opened_at", TS), Col("closed_at", TS, True), Col("suppress_marketing", B),
), "One row per dispute, complaint or collections case. Suppression flag only: no money detail, no days past due.")

actions = TableSchema("actions", (
    Col("action_id", S), Col("unit_id", S), Col("person_key", S), Col("application_ref", S, True),
    Col("record_kind", S, allowed=("legacy_send", "decision", "transactional")),
    Col("regime", S, allowed=REGIME), Col("decided_at", TS), Col("state", S, True, STATES, "Filled from state_history"),
    Col("trigger", S, allowed=TRIGGERS),
    Col("chosen_action", S, allowed=ACTIONS), Col("channel", S, True, CHANNELS),
    Col("category", S, True, ("transactional", "regulatory", "promotional"),
        "regulatory = EMI reminders, pre-debit notices, statements, KFS: never held out, never chosen by the policy"),
    Col("template", S, True), Col("message_id", S, True), Col("campaign_id", S, True), Col("sent_at", TS, True),
    Col("final_status", S, True, MSG), Col("options_considered", J, True), Col("blocked_actions", J, True),
    Col("reason_codes", J, True), Col("propensity", F, True, desc="Exploration policy probability of the chosen action"),
    Col("expected_value", F, True, desc="Null: no trained model yet"), Col("model_versions", S, True),
    Col("rule_version", S, True), Col("needs_approval", B), Col("in_holdout", B),
    Col("holdout_group", S, True, ("control", "treated")),
    Col("task_id", S, True), Col("task_target", S, True, ("agent_call_list", "crm_task")),
    Col("task_status", S, True, ("open", "done", "ignored", "overridden")), Col("task_due_at", TS, True),
    Col("task_owner_id", S, True), Col("task_capacity_bucket", S, True),
    Col("disposition", S, True, ("connected", "not_reachable", "callback_requested", "not_interested", "application_completed")),
    Col("call_duration_s", I, True),
), "One row per decision point or send: messages, decisions, tasks and agent calls merged.")

state_history = TableSchema("state_history", (
    Col("unit_id", S), Col("state", S, allowed=STATES), Col("entered_at", TS), Col("exited_at", TS, True),
    Col("entered_by", S, allowed=("event", "silence")), Col("flags", J), Col("rule_version", S),
), "Output of the reference state engine run on the VISIBLE events.")

campaigns = TableSchema("campaigns", (
    Col("row_type", S, allowed=("map", "ad_daily")), Col("campaign_id", S), Col("system", S),
    Col("system_campaign_id", S), Col("name_hash", S), Col("channel", S), Col("date", TS, True),
    Col("cost", F, True), Col("clicks", I, True), Col("impressions", I, True),
), "campaign_map and ad_spend_daily merged (row_type).")

person_truth = TableSchema("person_truth", (
    Col("unit_id", S), Col("hidden_type", S), Col("type_changes", J), Col("employment_type", S, allowed=("salaried", "self_employed")),
    Col("age", I), Col("income_annual", F), Col("loan_to_income", F), Col("true_risk_z", F), Col("lender_band_true_noise", F),
    Col("kyc_friction", F), Col("doc_quality", F), Col("urgency", F), Col("shopping_around", F),
    Col("mandate_failure_propensity", F), Col("prepay_propensity", F), Col("topup_propensity", F),
    Col("uplift_nudge", F), Col("uplift_agent_call", F), Col("uplift_fee_waiver", F), Col("uplift_offer", F),
    Col("uplift_emi_nudge", F), Col("reacts_badly", B), Col("fraud_flag", B), Col("stacking", B),
    Col("shared_phone_with", S, True), Col("anon_ids", J), Col("geo_tier", S),
), "HIDDEN. True type, income and employment, true risk and planted true effect of each action.", hidden=True)

application_truth = TableSchema("application_truth", (
    Col("application_ref", S), Col("unit_id", S), Col("kind", S, allowed=("natural", "incremental")),
    Col("cause_decision_id", S, True), Col("requested_amount", F), Col("sanctioned_amount", F, True),
    Col("disbursed_amount", F, True), Col("apr", F, True), Col("tenure_months", I, True), Col("fee_pct", F, True),
    Col("emi_amount", F, True), Col("true_default", B, True, desc="90+ DPD within 12 months on book; null when not disbursed"),
    Col("label_final", B, desc="Loan old enough (15+ months) for the default label to be final"),
    Col("first_dpd90_at", TS, True), Col("pay_path", J, True, desc="Per instalment: state, days late"),
    Col("max_dpd", I, True), Col("prepay_month", I, True), Col("p_default_hint", F, True),
), "HIDDEN. Exact amounts, terms, days-past-due path and the true default label.", hidden=True)

state_truth = TableSchema("state_truth", (
    Col("unit_id", S), Col("state", S, allowed=STATES), Col("entered_at", TS), Col("exited_at", TS, True),
), "HIDDEN. Same state rules run on the clean, un-noised, fully linked event stream.", hidden=True)

noise_log = TableSchema("noise_log", (
    Col("event_id", S, True), Col("defect", S, allowed=("duplicate", "missing_field", "wrong_timestamp", "late",
                                                       "out_of_order", "bot", "shared_device", "tracking_gap")),
    Col("detail", J),
), "HIDDEN. Every injected defect.", hidden=True)

VISIBLE = {t.name: t for t in (borrowers, events, applications, application_steps, loans, emi_payments, service_cases,
                               actions, state_history, campaigns)}
HIDDEN = {t.name: t for t in (person_truth, application_truth, state_truth, noise_log)}
