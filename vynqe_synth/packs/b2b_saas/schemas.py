"""B2B SaaS visible and hidden table contracts. Status values follow the workbook Status_maps sheet (plus flagged additions)."""
from ...core.schema import Col, TableSchema

TS, S, I, F, B, J = "timestamp", "string", "int", "float", "bool", "json"
SEGMENTS = ("SMB", "MM", "ENT")
REGIONS = ("north_america", "emea", "apac", "india")
SOURCES_ACC = ("inbound", "outbound", "partner", "event", "referral", "competitor_displacement")
ACC_STATUS = ("prospect", "customer", "churned", "lost")
ROLES = ("champion", "economic_buyer", "technical", "end_user")
CONSENT = ("granted", "denied", "unknown", "withdrawn")
REGIME = ("legacy_targeting", "randomised_holdout")
LEAD_STATUS = ("new", "contacted", "qualified", "converted", "lost")
OPP_TYPES = ("new", "expansion", "renewal", "win_back")
STAGES = ("discovery", "evaluation", "proposal", "negotiation", "closed_won", "closed_lost")
LOSS = ("price", "competitor", "no_decision", "timing", "product_gap", "champion_left")
ESIGN = ("created", "sent", "delivered", "signed", "completed", "declined", "voided")
SUB_STATUS = ("trialing", "active", "past_due", "paused", "pending", "cancelled", "expired")
PAYST = ("created", "authorised", "captured", "failed", "refunded")
MSG = ("sent", "delivered", "opened", "clicked", "bounced", "failed", "unsubscribed")
CHANNELS = ("web", "email", "call", "meeting", "in_app", "paid_search", "paid_social", "partner", "event", "referral",
            "organic", "direct", "webinar")
EVENT_TYPES = ("identify", "consent_change", "link_click", "page_view", "decision_made", "message_status",
               "record_created", "record_status_changed", "outcome_confirmed")
SOURCE_SYS = ("ga4", "hubspot", "salesforce", "stripe", "zendesk", "gainsight", "docusign", "cvent", "amplitude",
              "okta", "klaviyo", "decision_service", "outcome_checker", "google_ads", "meta_ads")
ACTIONS = ("do_nothing", "email", "rep_outreach", "discount", "exec_call", "csm_task", "transactional", "regulatory")
REASONS = ("no_consent", "unknown_consent", "open_opportunity", "open_ticket", "renewal_within_14d", "rep_engaged",
           "frequency_cap", "capacity_full", "approval_limit", "in_holdout", "in_legal_review", "payment_failed")
STATES = ("Lead", "Opportunity", "Competitor displacement", "Onboarding", "Active", "Expansion", "At-risk renewal",
          "Churned", "Lost")
TRIGGERS = ("lead_stall", "opp_stall", "onboarding", "risk", "expansion", "winback", "invoice", "renewal_notice",
            "security", "legacy")
BANDS_ARR = ("<5k", "5-10k", "10-25k", "25-50k", "50-100k", "100-250k", "250k+")
HEALTH = ("red", "yellow", "green")
PLANS = ("starter", "team", "business", "enterprise")

accounts = TableSchema("accounts", (
    Col("account_id", S), Col("segment", S, allowed=SEGMENTS), Col("industry_band", S), Col("employee_band", S),
    Col("region", S, allowed=REGIONS), Col("source", S, allowed=SOURCES_ACC), Col("created_at", TS),
    Col("first_won_at", TS, True), Col("status", S, allowed=ACC_STATUS, desc="EXTRACT-TIME snapshot (leakage trap)"),
    Col("current_plan", S, True, PLANS, "EXTRACT-TIME snapshot"), Col("arr_band", S, True, BANDS_ARR, "EXTRACT-TIME snapshot"),
    Col("renewal_at", TS, True, desc="EXTRACT-TIME snapshot of the current term end"),
    Col("strategic_flag", B), Col("named_csm", B), Col("regime_first_seen", S, allowed=REGIME),
    Col("holdout_group", S, allowed=("control", "treated")), Col("holdout_assigned_at", TS), Col("holdout_share", F),
    Col("holdout_strategy", S, allowed=("random_hash",)), Col("crm_ref", S), Col("billing_ref", S, True),
    Col("cs_ref", S, True), Col("domain_key", S, desc="HMAC of the company domain; no company names"),
), "One row per account: bands only. Also the identity map (one ref per system) and the whole-account holdout assignment.")

contacts = TableSchema("contacts", (
    Col("person_key", S, desc="HMAC-SHA-256 of normalised work or personal email"), Col("account_id", S, True, desc="Null when unmatched"),
    Col("contact_ref", S), Col("role", S, allowed=ROLES), Col("seniority_band", S, allowed=("ic", "manager", "director", "vp", "c_level")),
    Col("email_consent", S, allowed=CONSENT, desc="EXTRACT-TIME snapshot of marketing email consent; history in consent_change events"),
    Col("personal_email", B), Col("first_seen_at", TS), Col("left_account_at", TS, True),
    Col("lead_status", S, True, LEAD_STATUS, "Set for the contact that came in as a lead"), Col("lead_source", S, True),
    Col("lead_created_at", TS, True), Col("lead_converted_at", TS, True), Col("is_product_user", B),
), "One row per person. Leads are merged in here (lead_* columns).")

events = TableSchema("events", (
    Col("event_id", S), Col("source_event_id", S, desc="object:id:status (brief rule 4)"),
    Col("event_type", S, allowed=EVENT_TYPES), Col("source_system", S, allowed=SOURCE_SYS),
    Col("person_key", S, True), Col("anonymous_id", S, True), Col("unit_id", S, True, desc="account_id"),
    Col("occurred_at", TS), Col("ingested_at", TS), Col("channel", S, True, CHANNELS),
    Col("campaign_id", S, True), Col("placement_id", S, True), Col("consent_status", S, True, CONSENT),
    Col("properties", J),
), "Canonical event stream. Web, forms, consent, messages, CRM, e-sign, tickets, CTAs, health bands, registrations, billing and outcomes.")

opportunities = TableSchema("opportunities", (
    Col("opp_id", S), Col("account_id", S), Col("type", S, allowed=OPP_TYPES), Col("stage", S, allowed=STAGES, desc="EXTRACT-TIME snapshot; history in events"),
    Col("amount_band", S, allowed=BANDS_ARR), Col("discount_band", S, True, ("none", "1-10", "10-20", "20+")),
    Col("created_at", TS), Col("close_date", TS, True, desc="Expected close while open, actual when closed"),
    Col("closed_at", TS, True, desc="EXTRACT-TIME snapshot"), Col("is_won", B, True, desc="EXTRACT-TIME snapshot"),
    Col("loss_category", S, True, LOSS), Col("competitor_flag", B), Col("incumbent_vendor_band", S, True, ("known", "unknown")),
    Col("incumbent_contract_end", TS, True), Col("rep_id", S), Col("legal_review", B),
    Col("esign_status", S, True, ESIGN, "DocuSign envelope status (EXTRACT-TIME)"), Col("esign_changed_at", TS, True),
), "One row per deal: new, expansion, renewal and win-back. E-sign envelope merged in. Stage history is in events.")

product_usage_daily = TableSchema("product_usage_daily", (
    Col("account_id", S, True, desc="Null for unmatched users"), Col("person_key", S), Col("feature", S), Col("day", TS),
    Col("num_events", I), Col("num_minutes", F), Col("session_count", I), Col("source_system", S, allowed=("amplitude", "pendo")),
    Col("ingested_at", TS),
), "Account x person x feature x day, active days only. Logins are rows with feature=login.")

subscriptions = TableSchema("subscriptions", (
    Col("subscription_id", S), Col("account_id", S), Col("version", I), Col("plan", S, allowed=PLANS), Col("seats_bought", I),
    Col("seats_active_band", S, allowed=("<25%", "25-50%", "50-75%", "75%+"), desc="EXTRACT-TIME snapshot (leakage trap)"),
    Col("billing_interval", S, allowed=("monthly", "annual")), Col("term_months", I), Col("start_at", TS), Col("end_at", TS),
    Col("auto_renew_flag", B), Col("cancel_requested", B), Col("status", S, allowed=SUB_STATUS, desc="EXTRACT-TIME snapshot"),
    Col("status_changed_at", TS), Col("pause_collection", B), Col("collection_method", S, allowed=("charge_automatically", "send_invoice")),
    Col("trial_end", TS, True), Col("mrr_band", S, allowed=BANDS_ARR),
), "One row per plan period (amendments create a new version; Zuora-style Expired marks an old version). A term that ends with no successor is a lapse.")

invoices = TableSchema("invoices", (
    Col("invoice_id", S), Col("subscription_id", S), Col("account_id", S), Col("amount_band", S, allowed=BANDS_ARR),
    Col("issued_at", TS), Col("due_at", TS), Col("paid_at", TS, True), Col("status", S, allowed=PAYST, desc="EXTRACT-TIME snapshot"),
    Col("collection_method", S, allowed=("charge_automatically", "send_invoice")), Col("attempt_count", I),
    Col("error_code", S, True), Col("disputed", B), Col("is_renewal", B),
), "One row per invoice with payment outcome and dunning attempts.")

actions = TableSchema("actions", (
    Col("action_id", S), Col("unit_id", S), Col("person_key", S, True), Col("opp_id", S, True),
    Col("record_kind", S, allowed=("legacy_touch", "decision", "transactional")), Col("regime", S, allowed=REGIME),
    Col("decided_at", TS), Col("state", S, True, STATES, "Filled from state_history"), Col("trigger", S, allowed=TRIGGERS),
    Col("chosen_action", S, allowed=ACTIONS), Col("channel", S, True, CHANNELS),
    Col("category", S, True, ("transactional", "regulatory", "promotional"),
        "regulatory = billing notices, security alerts, legal terms: never held out, never chosen by the policy"),
    Col("template", S, True), Col("message_id", S, True), Col("campaign_id", S, True), Col("sent_at", TS, True),
    Col("final_status", S, True, MSG), Col("options_considered", J, True), Col("blocked_actions", J, True),
    Col("reason_codes", J, True), Col("propensity", F, True, desc="Exploration policy probability of the chosen action"),
    Col("expected_value", F, True, desc="Null: no trained model yet"), Col("model_versions", S, True),
    Col("rule_version", S, True), Col("needs_approval", B), Col("in_holdout", B), Col("holdout_group", S, True, ("control", "treated")),
    Col("task_id", S, True), Col("task_target", S, True, ("csm_cta", "crm_task")),
    Col("task_status", S, True, ("open", "done", "ignored", "overridden")), Col("task_due_at", TS, True),
    Col("task_owner_id", S, True), Col("disposition", S, True, ("connected", "not_reachable", "meeting_booked", "not_interested", "replied")),
    Col("call_duration_s", I, True),
), "One row per decision point or send: messages, decisions, rep and CSM tasks merged.")

state_history = TableSchema("state_history", (
    Col("unit_id", S), Col("state", S, allowed=STATES), Col("entered_at", TS), Col("exited_at", TS, True),
    Col("entered_by", S, allowed=("event", "silence", "clock")), Col("flags", J), Col("rule_version", S),
), "Output of the reference state engine run on the VISIBLE events.")

campaigns = TableSchema("campaigns", (
    Col("row_type", S, allowed=("map", "ad_daily")), Col("campaign_id", S), Col("system", S),
    Col("system_campaign_id", S), Col("name_hash", S), Col("channel", S), Col("date", TS, True),
    Col("cost", F, True), Col("clicks", I, True), Col("impressions", I, True),
), "campaign_map and ad_spend_daily merged (row_type).")

account_truth = TableSchema("account_truth", (
    Col("unit_id", S), Col("kind", S, allowed=("base", "new")), Col("prospect_type", S), Col("customer_type", S),
    Col("fit_score", F), Col("intent_stage", S), Col("incumbent_lock_in", S), Col("champion_exit_hazard", F),
    Col("usage_decay_rate", F), Col("decay_mode", S, allowed=("none", "gradual", "sudden")), Col("budget_cycle_month", I),
    Col("competitor_win_prob", F), Col("expansion_headroom", F), Col("acv", F, True), Col("seats_true", I, True),
    Col("integration_connected", B), Col("reacts_badly", B), Col("uplift_prospect", J), Col("uplift_customer", J),
    Col("p_win_base", F, True), Col("will_win", B), Col("churn_kind", S, True, desc="cancelled, silent_lapse, involuntary or null"),
    Col("churn_at", TS, True), Col("renewal_outcomes", J, True), Col("is_test_account", B), Col("duplicate_of", S, True),
    Col("champion_left_at", TS, True),
), "HIDDEN. True types, drivers, exact ACV, planted effect of each action and the true outcomes.", hidden=True)

contact_truth = TableSchema("contact_truth", (
    Col("person_key", S), Col("contact_ref", S), Col("true_account", S), Col("visible_account", S, True),
    Col("is_champion", B), Col("wrongly_matched", B), Col("also_in_account", S, True),
), "HIDDEN. Which account a person really belongs to.", hidden=True)

opportunity_truth = TableSchema("opportunity_truth", (
    Col("opp_id", S), Col("unit_id", S), Col("p_win_true", F), Col("p_win_no_action", F), Col("cycle_days_true", F),
    Col("amount", F), Col("discount_pct", F), Col("true_won", B), Col("true_loss_category", S, True),
    Col("label_final", B, desc="Old enough for the outcome to be final"), Col("cause_decision_id", S, True),
), "HIDDEN. Exact amounts, true win probability with and without the action, and the true label.", hidden=True)

state_truth = TableSchema("state_truth", (
    Col("unit_id", S), Col("state", S, allowed=STATES), Col("entered_at", TS), Col("exited_at", TS, True),
), "HIDDEN. Same state rules run on the clean, un-noised, fully linked event stream.", hidden=True)

noise_log = TableSchema("noise_log", (
    Col("event_id", S, True), Col("defect", S, allowed=("duplicate", "missing_field", "wrong_timestamp", "late",
        "out_of_order", "bot", "tracking_gap", "duplicate_account", "unmatched_user", "wrongly_matched", "test_account",
        "multi_account_user")), Col("detail", J),
), "HIDDEN. Every injected defect.", hidden=True)

VISIBLE = {t.name: t for t in (accounts, contacts, events, opportunities, product_usage_daily, subscriptions, invoices,
                               actions, state_history, campaigns)}
HIDDEN = {t.name: t for t in (account_truth, contact_truth, opportunity_truth, state_truth, noise_log)}
