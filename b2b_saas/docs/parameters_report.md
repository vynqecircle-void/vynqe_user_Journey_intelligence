# Parameters report: B2B SaaS pack

Every assumption in `vynqe_synth/config/b2b_saas.yaml`, generated from the file itself. SYNTHETIC DATA: these are generator settings, not measurements of any real company.

Grades: **A** verified from an official source; **B** researched, secondary or vendor/benchmark source (low confidence); **C** our assumption or calibration, adjustable; **D** placeholder with no basis (client-only data). `Q` is the question number in the B2B answers file (`-` = none).

## Not verified at all (or verified only from secondary sources)
- Salesforce and Okta default behaviours, the Zendesk `hold` status counting as live, Amplitude merged-ID handling: not confirmed from primary documentation.
- DPDP Rules: notified 14 Nov 2025 with main obligations phased in at about 18 months (not yet in force); no legitimate-interest basis. Whether business contacts are covered was not confirmed. Law-firm summaries only.
- GA4 30-minute session timeout, Stripe PaymentIntent statuses, DocuSign statuses, HubSpot lead statuses and CAN-SPAM B2B coverage: confirmed from secondary sources only.
- Verified from primary documentation: Stripe subscription statuses, `paused` versus `pause_collection`, the Stripe period-date move to subscription items, Stripe Smart Retries default, Amplitude export by `server_upload_time` with about 2 hours latency, Zendesk ticket statuses, Zuora `Expired` meaning an old version.

## Parameters tuned by running the generator (all grade C)
Adjusted until runs matched the answers-file targets. They are placeholders for a real company sample:
- Per-segment churn offsets (solved by Monte Carlo in `build_context`, target Q41 annual logo churn 15/10/5%).
- Funnel normalisers for lead to MQL, MQL to SQL, SQL to opportunity and opportunity to won (computed at build time from the configured rates).
- `retention.lapse_given_annual_churn` (raised to 1.0 so silent lapse is about 30-40% of voluntary churn, Q42) and `billing.customer_fix_prob`.
- Uplift tables `policy.uplift_prospect` and `policy.uplift_customer` (planted effect sizes, illustrative only).

Count by grade: A=7, B=28, C=134, D=9 (total 178)

| Parameter | Value | Grade | Q | Note |
|---|---|---|---|---|
| `run.start_date` | "2024-05-01" | C | 1 | 30-month window ending 31 Oct 2026 (answers: 24-36 months; brief default 24) |
| `run.n_days` | 914 | C | 1 | 30 months |
| `run.regime2_day` | 457 | C | 66 | Months 1-15 legacy targeting; months 16-30 randomised policy |
| `run.holdout_share` | 0.08 | C | 70 | Q70: 5 to 10% of whole accounts, optional nudges only |
| `run.holdout_salt` | "vynqe-b2b-holdout-salt-v1" | C | 70 | Salted hash (brief rule 15) |
| `run.hash_secret` | "dummy-b2b-secret-not-real" | C | - | Dummy HMAC secret (brief rule 8) |
| `population.segment_mix` | {"SMB": 0.6, "MM": 0.3, "ENT": 0.1} | B | 2 | Account share by ACV; revenue share inverted |
| `population.acv_median_usd` | {"SMB": 9000, "MM": 48000, "ENT": 180000} | C | 4 | Lognormal; cut-offs SMB<25K, MM 25-100K, ENT>100K. Hidden exact; visible only as bands |
| `population.acv_sigma` | {"SMB": 0.45, "MM": 0.45, "ENT": 0.55} | C | 4 |  |
| `population.acv_band_edges` | [0, 5000, 10000, 25000, 50000, 100000, 250000] | C | 4 | USD band edges (brief rule 7) |
| `population.seats_median` | {"SMB": 9, "MM": 40, "ENT": 150} | C | 1 | Median users per account 10-25 overall, P90 about 100 |
| `population.seats_sigma` | 0.6 | C | 1 |  |
| `population.seats_clip` | {"SMB": [2, 40], "MM": [10, 150], "ENT": [50, 600]} | C | 1 |  |
| `population.tracked_users_cap` | 40 | C | 1 | Named users simulated per account in usage tables (large accounts are sampled; seats_active_band keeps the full picture) |
| `population.industry_bands` | ["software_it", "financial_services", "healthcare", "manufacturing_retail", "other_services"] | D | 2 | Company data |
| `population.industry_probs` | [0.28, 0.17, 0.12, 0.23, 0.2] | D | 2 |  |
| `population.region_probs` | {"north_america": 0.35, "emea": 0.2, "apac": 0.15, "india": 0.3} | D | 2 | India-based seller (answers header); company data |
| `population.employee_bands` | {"SMB": ["1-50", "51-200"], "MM": ["51-200", "201-1000"], "ENT": ["201-1000", "1001+"]} | C | 2 |  |
| `population.source_mix` | {"inbound": 0.34, "outbound": 0.24, "partner": 0.12, "event": 0.1, "referral": 0.12, "competitor_displacement": 0.08} | C | 5 | Referral added beyond brief list (Q5 names referrals); competitor displacement from Q19 |
| `population.source_win_mult` | {"inbound": 1.25, "outbound": 0.45, "partner": 1.0, "event": 0.9, "referral": 1.7, "competitor_displacement": 0.8} | B | 5 | Referral 30-50% win, inbound about 50% vs outbound about 10%; normalised so the average chain holds |
| `population.prospect_types` | {"browser": 0.5, "researcher": 0.25, "evaluator": 0.15, "locked_in": 0.1} | C | 24 |  |
| `population.prospect_intent_mult` | {"browser": 0.35, "researcher": 1.0, "evaluator": 2.6, "locked_in": 0.8} | C | 12 | Hypothesis: pricing visits, demo requests and repeat visits separate buyers from browsers. Normalised in code so the funnel averages hold |
| `population.customer_types` | {"power": 0.1, "steady": 0.3, "shallow": 0.25, "shelfware": 0.15, "project_based": 0.08, "champion_dependent": 0.07, "price_sensitive": 0.05} | C | 24 |  |
| `population.active_share` | {"power": [0.85, 0.95], "steady": [0.65, 0.8], "shallow": [0.3, 0.5], "shelfware": [0.05, 0.25], "project_based": [0.3, 0.7], "champion_dependent": [0.4, 0.75], "price_sensitive": [0.45, 0.75]} | C | 25 | Wide overlap so types are not trivially separable |
| `population.sessions_per_week` | {"power": [4, 7], "steady": [2, 5], "shallow": [1, 2.5], "shelfware": [0.3, 1], "project_based": [0.5, 5], "champion_dependent": [1.5, 4], "price_sensitive": [1.5, 4]} | C | 32 | Median 3-5 a week for daily-use tools |
| `population.type_churn_shift` | {"power": -0.9, "steady": -0.3, "shallow": 0.4, "shelfware": 1.1, "project_based": 0.5, "champion_dependent": 0.4, "price_sensitive": 0.7} | C | 41 | Log-odds shift on renewal churn, before normalisation |
| `population.incumbent_lock_in` | {"none": 0.45, "soft": 0.35, "hard": 0.2} | C | 20 | Only for accounts with a competitor; prospects only |
| `population.competitor_known_share` | 0.4 | D | 20 | Current vendor known for 30-50% of accounts |
| `population.competitor_in_deal` | 0.65 | C | 19 | A competitor appears in 60-70% of deals |
| `population.champion_exit_per_year` | 0.17 | C | 26 | 15 to 20% of champions change role each year |
| `population.contacts_per_lead` | {"SMB": [1, 2], "MM": [2, 4], "ENT": [3, 6]} | B | 11 | Buying groups 6-10 for large deals; visible contacts are those that touched us |
| `population.personal_email_share` | 0.12 | C | 74 | 10 to 15% personal-email users |
| `population.named_csm_share` | {"SMB": 0.08, "MM": 0.65, "ENT": 1.0} | C | 54 |  |
| `population.strategic_share` | 0.06 | D | - | Strategic flag; mostly enterprise |
| `population.lead_growth_per_year` | 0.15 | C | 1 |  |
| `population.installed_base_age_days` | [30, 900] | C | 1 | Installed base accounts started paying up to this many days before window start |
| `funnel.p_lead_to_mql` | 0.3 | B | 9 |  |
| `funnel.p_mql_to_sql` | 0.25 | C | 9 | Answers conflict: 13% vs 38% |
| `funnel.p_sql_to_opp` | 0.42 | B | 9 |  |
| `funnel.p_opp_to_won` | 0.25 | B | 9 | 22 to 39% |
| `funnel.junk_lead_share` | 0.15 | C | 8 | 10-20% duplicates, fakes, bots, out of profile; they never progress |
| `funnel.stage_names` | ["discovery", "evaluation", "proposal", "negotiation"] | C | 10 | Client-defined in Salesforce |
| `funnel.cycle_median_days` | {"SMB": 30, "MM": 75, "ENT": 150} | B | 10 | Answers conflict (40-190 days); mid values by segment |
| `funnel.cycle_sigma` | 0.55 | C | 10 |  |
| `funnel.displacement_cycle_mult` | 1.6 | C | 19 | 1.3 to 2x longer |
| `funnel.lead_to_mql_days` | 10 | C | 30 | Median |
| `funnel.mql_to_sql_days` | 9 | C | 30 |  |
| `funnel.sql_to_opp_days` | 7 | C | 30 |  |
| `funnel.lead_quiet_days` | 60 | A | - | State rule from the brief: Lead lost after 60 days quiet |
| `funnel.loss_categories` | {"price": 0.22, "competitor": 0.28, "no_decision": 0.25, "timing": 0.12, "product_gap": 0.1, "champion_left": 0.03} | C | 19 |  |
| `funnel.sessions_before_demo` | [3, 6] | C | 30 | 3 to 6 sessions over 2 to 4 weeks |
| `funnel.pages` | ["home", "pricing", "docs", "blog", "case_study", "demo", "integrations", "security"] | C | 30 |  |
| `funnel.trial_share_smb` | 0.3 | B | 16 | Product-led trial for part of SMB |
| `funnel.trial_days` | 14 | B | 16 |  |
| `funnel.trial_to_paid` | 0.8 | C | 16 | Applied after the deal is won; non-converting trials cancel |
| `funnel.never_live_share` | 0.05 | C | 22 | 3 to 8% never go live or never pay |
| `funnel.first_invoice_days` | [0, 30] | C | 22 |  |
| `funnel.security_legal_days` | [14, 45] | C | 21 |  |
| `funnel.legal_review_share` | {"SMB": 0.05, "MM": 0.3, "ENT": 0.8} | C | 21 | Drives the in_legal_review flag |
| `subscription.annual_share` | {"SMB": 0.55, "MM": 0.85, "ENT": 1.0} | B | 3 | Remaining SMB accounts bill monthly |
| `subscription.term_months_ent_multi` | 0.25 | C | 3 | Share of enterprise on 24-month terms (renewal clock still 12 or 24 months) |
| `subscription.card_share` | {"SMB": 0.85, "MM": 0.45, "ENT": 0.05} | C | 3 | Rest pay by invoice (send_invoice) |
| `subscription.plans` | {"SMB": ["starter", "team"], "MM": ["team", "business"], "ENT": ["business", "enterprise"]} | D | 2 |  |
| `subscription.auto_renew` | {"SMB": 0.85, "MM": 0.6, "ENT": 0.3} | C | 42 | Auto-renew has far fewer silent lapses |
| `subscription.annual_discount_note` | 0.2 | B | 3 | Annual plans at 15 to 25% off; documented only, amounts are banded |
| `subscription.price_rise` | 0.1 | B | 50 | 8 to 12% a year on renewal list price (documented; amounts banded) |
| `subscription.renewal_open_days` | 120 | B | 47 | Renewal opportunity opens 90-120 days before term end |
| `subscription.late_renewal_share` | 0.12 | B | 47 | 10 to 15% close after term end |
| `retention.annual_churn` | {"SMB": 0.15, "MM": 0.1, "ENT": 0.05} | B | 41 | Logo churn per year. Answers also give a mid-market renewal split summing to 17% churn; this setting wins and the split is used for the cancel:lapse ratio only (flagged) |
| `retention.cancel_vs_lapse` | {"cancelled": 0.59, "silent_lapse": 0.41} | C | 42 | 10:7 from the renewal split |
| `retention.lapse_given_annual_churn` | 1.0 | C | 42 | Share of annual-contract churners that lapse silently (no cancel request), before the auto-renew reduction. Monthly plans cannot lapse. Tuned so silent lapse is roughly 30-40% of churn overall (mid-market split 10:7) |
| `retention.contraction_prob` | {"SMB": 0.08, "MM": 0.08, "ENT": 0.08} | C | 42 | 8% at renewal; 5-10% a year (Q51) |
| `retention.contraction_size` | [0.1, 0.35] | C | 51 | Share of seats or ARR dropped |
| `retention.expansion_prob_year` | {"SMB": 0.3, "MM": 0.38, "ENT": 0.4} | C | 61 | Share of accounts expanding in a year; 15-25% gives about 18 points of expansion in mid-market |
| `retention.expansion_at_renewal_share` | 0.4 | B | 28 | 40% of expansions at renewal |
| `retention.expansion_size` | {"SMB": [0.15, 0.6], "MM": [0.2, 0.7], "ENT": [0.2, 0.9]} | C | 61 | Seat growth range |
| `retention.usage_decay_gradual` | 0.6 | C | 38 | 60% gradual over 4-8 weeks, 40% sudden |
| `retention.decay_weeks` | [4, 8] | C | 38 |  |
| `retention.sudden_lead_days` | [0, 45] | C | 38 | Sudden stop happens this many days before term end |
| `retention.win_back_return` | 0.1 | B | 53 | 8 to 12% of churned accounts return |
| `retention.lost_return` | 0.07 | C | 63 | 5 to 10% of lost deals return within 12 months |
| `retention.churn_reason_mix` | {"competitor": 0.4, "closed_or_no_need": 0.3, "internal_build": 0.2, "price": 0.1} | C | 64 | 35-45 / 25-35 / 20-30 |
| `retention.champion_churn_lift` | 0.9 | C | 26 | Log-odds lift when the champion left and no backup (vendor claim 40% churn, illustrative) |
| `retention.decay_churn_lift` | 1.3 | C | 43 | Log-odds lift per unit usage decay |
| `retention.ticket_churn_lift` | 0.5 | C | 57 | Unresolved or escalated tickets lower renewal odds, fading over 60-90 days |
| `retention.integration_churn_cut` | 0.45 | C | 39 | 30-50% lower churn for connected accounts; unproven, labelled so |
| `retention.integration_share` | 0.38 | C | 39 | 30 to 45% |
| `retention.onboarding_activation` | {"power": 0.95, "steady": 0.88, "shallow": 0.65, "shelfware": 0.45, "project_based": 0.75, "champion_dependent": 0.8, "price_sensitive": 0.8} | C | 23 | Reaches first value event within 90 days |
| `retention.first_value_days` | {"SMB": 7, "MM": 14, "ENT": 35} | C | 23 | Median days to first value |
| `retention.early_churn_share` | 0.7 | B | 23 | Vendor claim, unverified: used only to bias hazard to first 90 days for never-activated accounts |
| `usage.features` | ["dashboard", "report", "export", "integration_connected", "api_call", "invite_sent", "seat_added", "admin_settings"] | C | 33 | Also login and feature_used events; names are the client's own |
| `usage.feature_probs` | [0.34, 0.22, 0.1, 0.04, 0.12, 0.04, 0.02, 0.12] | C | 34 | Core feature in 70% of active accounts; advanced 20-30% |
| `usage.features_per_active_day` | [1, 3] | C | 32 |  |
| `usage.weekday_mult` | [1.15, 1.25, 1.25, 1.2, 0.95, 0.12, 0.08] | C | 36 | Mon..Sun; Tue-Thu peak |
| `usage.holiday_weeks` | [["2024-12-23", "2025-01-03"], ["2025-12-22", "2026-01-02"], ["2024-10-28", "2024-11-03"], ["2025-10-20", "2025-10-26"], ["2026-11-08", "2026-11-14"]] | C | 36 | 30-40% dip in holiday weeks; Diwali dates unverified |
| `usage.holiday_mult` | 0.65 | C | 36 |  |
| `usage.month_end_lift` | 1.12 | C | 36 | Last 3 days of month, finance and sales tools |
| `usage.events_per_feature_day` | [3, 25] | C | 32 | Event count per feature per day |
| `usage.minutes_per_feature_day` | [2, 25] | C | 32 |  |
| `usage.unmatched_user_share` | 0.08 | C | 37 | 5 to 15% of product users unmatched to an account |
| `usage.login_fail_rate` | 0.045 | C | 35 | 3 to 6% failed logins |
| `usage.sso_share` | 0.3 | C | 35 | 20-40% of MM and ENT |
| `usage.amplitude_late_hours` | [1, 6] | B | 76 | Usage reaches the warehouse by upload time |
| `billing.card_fail_rate` | 0.04 | B | 48 | 3 to 5% of card charges; initial failure |
| `billing.retry_days` | [1, 3, 5, 7] | C | 48 | Client reminder and retry cadence (Stripe Smart Retries default is up to 8 retries in 2 weeks; verified) |
| `billing.retry_recover_each` | 0.22 | B | 48 | About 48% recovered over the sequence (median 47.6%); 61% of recoveries in week 1 |
| `billing.customer_fix_prob` | 0.5 | C | 48 | Customer updates the card after the dunning email. Reconciles 3-5% failures and about 48% retry recovery with 20-40% involuntary share of churn |
| `billing.hard_decline_share` | 0.25 | C | 48 | Hard declines are not retried |
| `billing.invoice_late_share` | 0.3 | C | 49 | 25 to 35% pay late |
| `billing.invoice_late_days` | [10, 15] | C | 49 | Median days late |
| `billing.dispute_share` | 0.03 | C | 49 | 2 to 4% disputed |
| `billing.net_terms_days` | 30 | C | 22 | Net 30 for invoice accounts |
| `billing.refund_share` | 0.01 | C | 49 |  |
| `billing.after_retries` | {"cancelled": 0.6, "unpaid": 0.2, "past_due": 0.1, "paused": 0.1} | C | 48 | Subscription state after retries fail (Stripe docs list these four) |
| `billing.involuntary_target` | [0.2, 0.4] | B | 42 | 20-40% of churn; used by the validator, not a driver |
| `support.tickets_per_month` | [0.5, 1.0] | C | 56 | Median 0.5-1 a month per account (scaled by seats) |
| `support.ticket_topics` | ["bug", "how_to", "billing", "integration"] | C | 56 |  |
| `support.ticket_topic_probs` | [0.3, 0.35, 0.15, 0.2] | C | 56 |  |
| `support.solve_days_median` | 2.0 | C | 56 | 1 to 3 days |
| `support.csat_response` | 0.35 | C | 58 |  |
| `support.reopen_prob` | 0.08 | C | 56 |  |
| `support.pre_churn_ticket_lift` | 1.8 | C | 43 | Ticket rate multiplier in the 90 days before a cancellation |
| `cs.health_cuts` | [40, 70] | C | 44 | red < 40, yellow < 70, else green (client-defined; banded) |
| `cs.health_noise_sd` | 12 | C | 44 | Scores predict churn only moderately |
| `cs.cta_response_days` | [2, 5] | C | 55 |  |
| `cs.cta_save_rate` | 0.25 | C | 55 | 20 to 35%; vendor claims unverified |
| `cs.cta_statuses` | ["new", "work_in_progress", "closed_success", "closed_no_action", "closed_invalid"] | A | 55 | Gainsight defaults (verified, step 2) |
| `cs.review_share` | {"SMB": 0.0, "MM": 0.12, "ENT": 0.6} | C | 60 | Executive or quarterly business reviews |
| `messaging.consent_initial` | {"granted": 0.5, "withdrawn": 0.02} | D | 67 | Rest unknown, which means hold. Per contact, per channel (email) |
| `messaging.optin_at_form` | 0.55 | C | 67 | Form-fill opt-in for inbound leads |
| `messaging.unsub_rate` | 0.0012 | B | 67 | About 0.12% |
| `messaging.bounce_rate` | 0.015 | B | 71 | Under 2% |
| `messaging.open_rate` | 0.3 | B | 65 | Inflated by Apple Mail privacy |
| `messaging.click_rate` | 0.045 | B | 65 |  |
| `messaging.reply_rate` | 0.035 | B | 65 | Cold email 3.43% |
| `messaging.frequency_cap_days` | 14 | C | 71 | At most 2 discretionary touches in this window |
| `messaging.frequency_cap_n` | 2 | C | 71 |  |
| `messaging.hold_renewal_days` | 14 | A | 59 | Rule: open opportunity or renewal inside 14 days or open ticket holds automated messages |
| `policy.actions` | ["email", "rep_outreach", "discount", "exec_call", "csm_task"] | C | 46 | Plus do_nothing; transactional and regulatory sends are logged but never chosen |
| `policy.exploration_do_nothing` | 0.25 | C | 70 |  |
| `policy.legacy_base_touch` | 0.3 | C | 66 | Legacy: chance of any touch rises with ARR and engagement |
| `policy.legacy_fit_slope` | 1.6 | C | 66 |  |
| `policy.legacy_arr_slope` | 0.9 | C | 66 |  |
| `policy.decision_scale` | {"lead_stall": 0.6, "opp_stall": 1.0, "onboarding": 0.8, "risk": 1.0, "expansion": 0.8, "winback": 0.5} | C | 62 | Scales planted uplift by decision kind |
| `policy.reacts_badly_share` | 0.05 | C | 71 | Complaint risk; negative response to any discretionary touch |
| `policy.reacts_badly_effect` | -0.06 | C | 71 |  |
| `policy.uplift_prospect` | {"browser": {"email": 0.03, "rep_outreach": 0.02, "discount": 0.01, "exec_call": 0.0, "csm_task": 0.0}, "researcher": {"email": 0.05, "rep_outreach": 0.07, "discount": 0.03, "exec_call": 0.02, "csm_task": 0.0}, "evaluator": {"email": 0.02, "rep_outreach": 0.11, "discount": 0.06, "exec_call": 0.09, "csm_task": 0.0}, "locked_in": {"email": -0.01, "rep_outreach": 0.04, "discount": 0.02, "exec_call... | C | 46,62 | Planted true effect on the decision outcome probability (absolute). Illustrative, not measurements |
| `policy.uplift_customer` | {"power": {"email": 0.01, "rep_outreach": 0.02, "discount": -0.01, "exec_call": 0.01, "csm_task": 0.01}, "steady": {"email": 0.02, "rep_outreach": 0.04, "discount": 0.01, "exec_call": 0.03, "csm_task": 0.04}, "shallow": {"email": 0.01, "rep_outreach": 0.03, "discount": 0.0, "exec_call": 0.02, "csm_task": 0.08}, "shelfware": {"email": 0.0, "rep_outreach": 0.01, "discount": -0.03, "exec_call": 0.... | C | 46,62 | Discount is negative for several types: leading with a discount trains customers to churn and return (Q46). Sleeping dogs are negative cells |
| `policy.capacity` | {"exec_call_arr_floor": 25000} | D | 54 | Executive calls only for accounts above this ARR |
| `noise.duplicate` | 0.004 | C | 74 | Duplicate events |
| `noise.missing_field` | 0.012 | C | 74 | Channel blanked |
| `noise.wrong_timestamp` | 0.004 | C | 76 |  |
| `noise.late` | 0.02 | C | 76 |  |
| `noise.out_of_order` | 0.02 | A | 76 | 1 to 3% out of order |
| `noise.ga4_late_days` | 3 | C | 76 |  |
| `noise.duplicate_account_share` | 0.075 | C | 74 | 5 to 10% duplicate accounts (split identities) |
| `noise.duplicate_event_share` | 0.45 | C | 74 | Share of an account's pre-win events carried by the duplicate id |
| `noise.wrongly_matched_share` | 0.03 | C | 75 | 2 to 5% of users wrongly matched (logged in noise_log) |
| `noise.test_account_share` | 0.004 | C | 74 | Internal test accounts, flagged only in noise_log |
| `noise.multi_account_user_share` | 0.05 | C | 74 | 3 to 8% of users in several accounts |
| `noise.bot_share_of_anon_sessions` | 0.04 | C | 37 |  |
| `noise.tracking_gaps` | {"per_year": 2, "days": 3} | C | 78 |  |
| `noise.anon_visit_unlinked` | 0.55 | C | 13 | Share of web sessions never matched to an account (company match 30-65%) |
| `sessions.timeout_minutes` | 30 | B | 37 | GA4 default 30 minutes (verified, secondary source) |
| `sessions.mean_pages` | 3.5 | C | 30 |  |
| `sessions.hour_weights` | [0.2, 0.1, 0.1, 0.1, 0.1, 0.3, 0.8, 2.0, 4.0, 6.0, 7.0, 7.0, 6.0, 6.5, 7.0, 7.0, 6.0, 4.0, 2.5, 1.5, 1.0, 0.8, 0.5, 0.3] | C | 35 | Business hours in the account time zone (simplified to one clock) |
| `states.rule_version` | "b2b-v1" | C | - |  |
| `states.onboarding_max_days` | 90 | A | 23 | Brief: Onboarding until first value or day 90 |
| `states.at_risk_window_days` | 120 | A | 43 | Renewal within 120 days and risk signals |
| `states.cooling_off_days` | 90 | A | 63 | Lost to new opportunity cooling off |
| `states.expansion_window_days` | 120 | C | 62 |  |
| `states.usage_decay_threshold` | 0.5 | C | 45 | Usage down 30-40% vs baseline or seat use under 50% is at risk; engine reads the health band |
| `labels.renewal_buffer_days` | 45 | C | 47 | Renewal label final this many days after term end (late renewals 10-15%) |
| `labels.win_horizon_days` | 180 | C | 10 |  |
| `labels.churn_horizon_days` | 90 | C | 43 |  |
| `campaigns.ad_campaigns` | {"paid_search": 4, "paid_social": 3, "partner": 3} | D | 5 | Count per channel |
| `campaigns.cpc_usd` | 6.5 | C | 5 |  |
| `campaigns.ctr` | 0.03 | C | 5 |  |
