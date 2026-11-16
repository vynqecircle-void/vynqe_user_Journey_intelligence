"""E-commerce visible and hidden table contracts. Status values follow the workbook Status_maps sheet."""
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
SOURCES = ("quiz", "game", "cms", "webhook", "trackflow", "ga4", "shopify", "razorpay", "shiprocket", "zendesk",
           "klaviyo", "whatsapp", "warehouse", "decision_service", "outcome_checker", "google_ads", "meta_ads")
FIN = ("placed", "paid", "partially_refunded", "refunded", "cancelled")
FUL = ("unfulfilled", "partial", "fulfilled", "returned_to_stock")
DELIV = ("delivered", "failed_delivery", "rto")
PAYST = ("created", "authorised", "captured", "failed", "refunded")
TICKET = ("new", "open", "pending", "solved", "closed")
MSG = ("sent", "delivered", "opened", "clicked", "bounced", "failed", "unsubscribed")
ACTIONS = ("do_nothing", "reminder", "discount", "free_shipping", "bundle", "agent_call", "transactional")
REASONS = ("no_consent", "unknown_consent", "open_ticket", "margin_floor", "out_of_stock", "cod_limit",
           "discount_budget", "offer_abuse", "approval_limit", "frequency_cap", "in_holdout")
STATES = ("New visitor", "Retarget", "New customer", "Active", "Re-engage", "Reactivate")
CATS = ("apparel_women", "apparel_men", "footwear", "accessories", "beauty", "home", "electronics_acc")
STOCK = ("in_stock", "low", "out_of_stock")

customers = TableSchema("customers", (
    Col("unit_id", S), Col("person_key", S, desc="HMAC-SHA-256 of normalised phone; not unique when a phone is shared"),
    Col("created_at", TS), Col("first_order_at", TS, True),
    Col("orders_count", I, desc="EXTRACT-TIME snapshot (leakage trap): use events for point-in-time"),
    Col("spend_band", S, desc="EXTRACT-TIME snapshot"), Col("device_class", S, allowed=DEVICE),
    Col("acquisition_channel", S), Col("campaign_id", S, True),
    Col("email_consent", S, allowed=CONSENT, desc="EXTRACT-TIME snapshot; history in consent_change events"),
    Col("sms_consent", S, allowed=CONSENT), Col("whatsapp_consent", S, allowed=CONSENT),
    Col("geo_tier", S, True, TIERS, "Flagged extension: not in workbook"),
    Col("regime_first_seen", S, allowed=REGIME),
    Col("holdout_group", S, allowed=("control", "treated")), Col("holdout_assigned_at", TS),
    Col("holdout_share", F), Col("holdout_strategy", S, allowed=("random_hash",)),
    Col("shopify_customer_ref", S), Col("klaviyo_profile_ref", S), Col("razorpay_ref", S, True),
    Col("zendesk_requester_ref", S, True), Col("ga4_user_id", S), Col("email_key", S, desc="HMAC of lowercased email"),
), "One row per customer; also holds the identity map (one ref per system) and holdout assignment.")

events = TableSchema("events", (
    Col("event_id", S), Col("source_event_id", S, desc="object:id:status (brief rule 4)"),
    Col("event_type", S, allowed=EVENT_TYPES), Col("source_system", S, allowed=SOURCES),
    Col("person_key", S, True), Col("anonymous_id", S, True), Col("unit_id", S, True),
    Col("occurred_at", TS), Col("ingested_at", TS), Col("channel", S, True, CHANNELS),
    Col("campaign_id", S, True), Col("placement_id", S, True), Col("consent_status", S, True, CONSENT),
    Col("properties", J),
), "Canonical event stream. Consent history, message status, decisions, outcomes and record lifecycles live here.")

orders = TableSchema("orders", (
    Col("order_id", S), Col("unit_id", S), Col("checkout_id", S), Col("created_at", TS), Col("processed_at", TS, True),
    Col("financial_status", S, allowed=FIN, desc="Snapshot at extract time"),
    Col("fulfilment_status", S, allowed=FUL), Col("amount_band", S), Col("item_count", I),
    Col("payment_mode", S, allowed=("prepaid", "cod")), Col("discount_code", S, True),
    Col("discount_band", S, True, ("0-10%", "10-20%", "20%+"), "Flagged extension"),
    Col("order_source", S, allowed=("web", "app", "pos")), Col("channel", S, True, CHANNELS), Col("campaign_id", S, True),
    Col("decision_id", S, True, desc="Set only when the customer clicked the message (observable attribution)"),
    Col("category_primary", S, allowed=CATS, desc="Flagged extension: needed for margin and stock guardrails"),
    Col("cancelled_at", TS, True), Col("paid_at", TS, True),
    Col("courier", S, True), Col("delivery_status", S, True, DELIV), Col("delivery_status_changed_at", TS, True),
    Col("delivered_at", TS, True), Col("attempt_count", I, True, desc="Flagged extension"),
    Col("rto_flag", B), Col("rto_reason_category", S, True, ("not_home", "refused", "address", "other")),
    Col("refund_created_at", TS, True), Col("refund_amount_band", S, True), Col("refund_status", S, True, ("refunded",)),
    Col("refund_reason_category", S, True, ("size_fit", "quality", "changed_mind", "damaged", "wrong_item"),
        "Flagged extension: not pulled by workbook"),
), "Orders with shipment and refund merged in (one shipment and at most one refund per order).")

payments = TableSchema("payments", (
    Col("payment_id", S), Col("checkout_id", S), Col("order_id", S, True, desc="Null when the checkout never became an order"),
    Col("unit_id", S), Col("status", S, allowed=PAYST), Col("method", S, allowed=("upi", "card", "netbanking", "wallet")),
    Col("amount_band", S), Col("created_at", TS), Col("error_code", S, True), Col("attempt_no", I),
), "One row per Razorpay payment attempt (final status). COD orders have no Razorpay payment.")

tickets = TableSchema("tickets", (
    Col("ticket_id", S), Col("unit_id", S), Col("created_at", TS), Col("updated_at", TS),
    Col("status", S, allowed=TICKET), Col("priority", S, allowed=("low", "normal", "high", "urgent")),
    Col("ticket_type", S, allowed=("question", "incident", "problem", "task")),
    Col("channel", S, allowed=("email", "web", "whatsapp", "call")),
    Col("tags", J, desc="Includes topic: delivery, product, payment, refund"),
    Col("solved_at", TS, True), Col("reopens", I), Col("csat", I, True),
), "Support tickets (Zendesk shape).")

actions = TableSchema("actions", (
    Col("action_id", S), Col("unit_id", S), Col("person_key", S),
    Col("record_kind", S, allowed=("legacy_send", "decision", "transactional")),
    Col("regime", S, allowed=REGIME), Col("decided_at", TS), Col("state", S, True, STATES, "Filled from state_history"),
    Col("trigger", S, allowed=("weekly", "cart", "legacy_weekly", "order_event")),
    Col("chosen_action", S, allowed=ACTIONS), Col("channel", S, True, CHANNELS),
    Col("category", S, True, ("transactional", "regulatory", "promotional")), Col("template", S, True),
    Col("message_id", S, True), Col("campaign_id", S, True), Col("sent_at", TS, True),
    Col("final_status", S, True, MSG), Col("options_considered", J, True), Col("blocked_actions", J, True),
    Col("reason_codes", J, True), Col("propensity", F, True, desc="Exploration policy probability of the chosen action"),
    Col("expected_value", F, True, desc="Null: no trained model yet"), Col("model_versions", S, True),
    Col("rule_version", S, True), Col("needs_approval", B), Col("in_holdout", B),
    Col("holdout_group", S, True, ("control", "treated")),
    Col("task_id", S, True), Col("task_target", S, True, ("agent_call_list", "crm_task")),
    Col("task_status", S, True, ("open", "done", "ignored", "overridden")), Col("task_due_at", TS, True),
    Col("task_owner_id", S, True), Col("task_capacity_bucket", S, True),
), "One row per decision point or send: messages, decisions and tasks merged. Regime 1 rows have no decision_id.")

state_history = TableSchema("state_history", (
    Col("unit_id", S), Col("state", S, allowed=STATES), Col("entered_at", TS), Col("exited_at", TS, True),
    Col("entered_by", S, allowed=("event", "silence")), Col("flags", J), Col("rule_version", S),
), "Output of the reference state engine run on the VISIBLE events.")

campaigns = TableSchema("campaigns", (
    Col("row_type", S, allowed=("map", "ad_daily")), Col("campaign_id", S), Col("system", S),
    Col("system_campaign_id", S), Col("name_hash", S), Col("channel", S), Col("date", TS, True),
    Col("cost", F, True), Col("clicks", I, True), Col("impressions", I, True),
), "campaign_map and ad_spend_daily merged (row_type).")

category_value = TableSchema("category_value", (
    Col("category", S, allowed=CATS), Col("month", TS), Col("margin_band", S), Col("return_cost_band", S),
    Col("stock_status", S, allowed=STOCK),
), "Client-supplied category economics (placeholder defaults, grade D).")

person_truth = TableSchema("person_truth", (
    Col("unit_id", S), Col("hidden_type", S), Col("type_changes", J), Col("order_gap_days_mean", F),
    Col("order_gap_cv", F), Col("sessions_per_month", F), Col("price_sensitivity", F), Col("cod_preference", F),
    Col("return_propensity", F), Col("refusal_propensity", F), Col("serial_returner", B), Col("reacts_badly", B),
    Col("baseline_p7", F), Col("would_act_anyway", B), Col("never_acts", B), Col("persuadable_actions", J),
    Col("uplift_reminder", F), Col("uplift_discount", F), Col("uplift_free_shipping", F), Col("uplift_bundle", F),
    Col("uplift_agent_call", F), Col("shared_phone_with", S, True), Col("anon_ids", J), Col("geo_tier", S),
), "HIDDEN. True type, latent attributes and the planted true effect of each action.", hidden=True)

order_truth = TableSchema("order_truth", (
    Col("order_id", S), Col("unit_id", S), Col("kind", S, allowed=("natural", "incremental")),
    Col("cause_decision_id", S, True), Col("exact_amount_gross", F), Col("exact_amount_net", F),
    Col("margin_pct", F), Col("margin_amount", F),
), "HIDDEN. Exact amounts and margins (visible tables carry bands only).", hidden=True)

state_truth = TableSchema("state_truth", (
    Col("unit_id", S), Col("state", S, allowed=STATES), Col("entered_at", TS), Col("exited_at", TS, True),
), "HIDDEN. Same state rules run on the clean, un-noised, fully-linked event stream.", hidden=True)

noise_log = TableSchema("noise_log", (
    Col("event_id", S, True), Col("defect", S, allowed=("duplicate", "missing_field", "wrong_timestamp", "late",
                                                       "out_of_order", "bot", "shared_device", "tracking_gap")),
    Col("detail", J),
), "HIDDEN. Every injected defect.", hidden=True)

VISIBLE = {t.name: t for t in (customers, events, orders, payments, tickets, actions, state_history, campaigns,
                               category_value)}
HIDDEN = {t.name: t for t in (person_truth, order_truth, state_truth, noise_log)}
