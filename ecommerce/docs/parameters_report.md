# Parameters report: e-commerce pack

Every assumption in `vynqe_synth/config/ecommerce.yaml`. SYNTHETIC DATA: these are generator settings, not measurements of any real business.

Grades: **A** verified from an official source; **B** researched, secondary or vendor source; **C** our assumption or calibration, adjustable; **D** placeholder with no basis. `Q` is the question number in the e-commerce answers file (`-` = none).

Not verified at all: DPDP and TRAI timings, Diwali dates, festive-sale dates for 2024/2025 and the 8-9 Oct 2026 sale (secondary source).

Count by grade: A=3, B=14, C=83, D=6 (total 106)

| Parameter | Value | Grade | Q | Note |
|---|---|---|---|---|
| `run.start_date` | "2024-11-01" | C | 55 | 24-month window ending 31 Oct 2026 |
| `run.n_days` | 730 | C | 1 | Answers: 12 to 24 months |
| `run.regime2_day` | 365 | C | 44 | Regime 1 = months 1-12 (legacy targeting); regime 2 = months 13-24 (randomised holdout) |
| `run.holdout_share` | 0.08 | C | 44 | PDF F3: 5 to 10% of customers |
| `run.holdout_salt` | "vynqe-holdout-salt-v1" | C | 44 | Salted hash assignment (brief rule 15) |
| `run.hash_secret` | "dummy-per-client-secret-not-real" | C | - | Dummy HMAC secret (brief rule 8) |
| `population.growth_per_year` | 0.23 | B | 52 | Online retail growth 22-24% (Redseer via People Matters) |
| `population.acquisition_mix` | {"paid_social": 0.33, "paid_search": 0.15, "organic": 0.27, "affiliate": 0.06, "referral": 0.09, "whatsapp": 0.1} | D | 5 | Client-specific |
| `population.channel_type_factor` | {"paid_social": {"deal_seeker": 1.5, "window_shopper": 1.3}, "affiliate": {"deal_seeker": 2.0, "one_time_buyer": 1.2}, "referral": {"loyal_buyer": 1.6, "gift_bu | C | 5 | Heavy first-order discount channels repeat less (TopGrowth, vendor) |
| `population.types` | {"loyal_buyer": {"share": 0.1, "p_buy": 0.95, "gap_mean": 28, "gap_cv": 0.6, "lapse_q": 0.04, "sessions_pm": 5.0, "tail": 200, "ps": [2, 5], "uplift": {"reminde | C | 6,7,3 | Shares from RFM clustering in real data; one_time_buyer must be largest. gap in days; ps = beta(a,b) price sensitivity; tail = mean active days after last order; sessions_pm = mean sessions per month; uplift = true 7-day extra conversion probability per action (PDF illustrative +6 pts free shipping, +3 pts 10% discount) |
| `population.type_change_share` | 0.06 | C | 8 | Share of customers whose hidden type changes once (monthly switch 5-10% sensitivity to test later) |
| `population.tier_mix` | [0.22, 0.2, 0.25, 0.2, 0.13] | D | 35 | metro, tier1, tier2, tier3, rural |
| `population.device_mix` | {"android": 0.72, "ios": 0.07, "web_mobile": 0.13, "web_desktop": 0.08} | B | 23 | Android ~92% of India mobile web page views (StatCounter); buyer share unknown |
| `population.serial_returner_share` | 0.055 | C | 32 | Default 3 to 8% |
| `population.reacts_badly_share` | 0.04 | C | 46 | No India fatigue curve found |
| `population.anon_visitors_per_customer` | 2.0 | C | 21 | Anonymous-only visitors (never identify) |
| `population.prior_sessions_mean` | 1.5 | C | 21 | Anonymous sessions before first identification |
| `population.identify_link_prob` | 0.35 | C | 21 | Default: 60 to 80% of pre-login events stay anonymous |
| `population.categories` | {"apparel_women": {"weight": 0.3, "price": 1.0, "margin": 0.45, "ret": 1.6, "rto": 1.1}, "apparel_men": {"weight": 0.2, "price": 1.0, "margin": 0.42, "ret": 1.5 | C | 25,29 | Margins, return and RTO factors are client finance data (D); defaults only. price = relative item price |
| `consent.initial` | {"email": {"granted": 0.6, "denied": 0.03}, "sms": {"granted": 0.4, "denied": 0.05}, "whatsapp": {"granted": 0.55, "denied": 0.02}} | D | 47 | Rest = unknown. Unknown means hold |
| `consent.optin_at_order_prob` | 0.25 | C | 47 | Checkout opt-in for an unknown channel |
| `sessions.mean_pages` | 4.4 | B | 16,18 | Mobile e-commerce pages/session ~4.4 (Opensend, Q4 2022, global, weak) |
| `sessions.max_events` | 30 | C | 16 |  |
| `sessions.gap_median_sec` | 10 | C | 19 | Heavy-tailed, median 5 to 15 s |
| `sessions.timeout_minutes` | 30 | A | 20 | GA4 default, verified (Google support) |
| `sessions.hour_weights_ist` | [1.0, 0.6, 0.4, 0.3, 0.3, 0.5, 1.0, 2.0, 3.0, 4.0, 5.0, 5.5, 6.0, 6.0, 5.5, 5.0, 5.0, 5.0, 5.5, 6.5, 8.0, 9.0, 8.0, 5.0] | C | 14 | Two daily peaks: midday and 8-11 PM |
| `sessions.login_prob` | 0.3 | C | 21 | Share of identified sessions that carry a login event |
| `orders.p_cod_base` | 0.57 | C | 28 | Sources conflict: 50-70% D2C, 25-30% all e-commerce; default 55-60% D2C |
| `orders.cod_tier_shift` | [-0.12, -0.04, 0.04, 0.1, 0.12] | C | 28 | Higher COD in tier 2/3 |
| `orders.items_extra_mean` | 0.8 | C | 24 | Items = 1 + Poisson(0.8); answers: 1.5 to 2.5 fashion |
| `orders.item_price_median` | 650 | C | 4 | INR; lognormal |
| `orders.item_price_sigma` | 0.5 | C | 4 |  |
| `orders.amount_edges` | [0, 500, 1000, 1500, 2500, 5000] | C | 4 | Band edges in INR (brief rule 7) |
| `orders.abandon_rate` | 0.7 | B | 18 | Cart abandonment 70.19% across 49 studies (Baymard) |
| `orders.nonbuyer_carts` | 0.5 | C | 18 | Mean abandoned carts for customers who never order |
| `orders.first_order_lag_median_days` | 4.0 | C | 1 |  |
| `orders.salary_day_mult` | 1.15 | C | 13 | Days 1-7 of month; no public figure |
| `orders.discount_sale_prob_factor` | 0.6 | C | 26 | P(discount code) on sale days = ps * factor |
| `orders.cancel_before_ship` | 0.04 | C | 36 | Placeholder 2 to 6% |
| `payments.method_mix` | {"upi": 0.6, "card": 0.2, "netbanking": 0.08, "wallet": 0.12} | C | 34 |  |
| `payments.success` | {"upi": 0.965, "card": 0.87, "netbanking": 0.9, "wallet": 0.93} | B | 34 | UPI technical decline 0.8% vs business declines; cards 85-88% (PhonePe); blended 92-94% |
| `payments.evening_drop` | 0.08 | B | 14 | Payment success drops 8-12 points at 7-10 PM (Razorpay) |
| `payments.retry_prob` | 0.3 | B | 34 | ~70% quit after one failure (vendor claim); retries recover 15-20% |
| `payments.error_codes` | ["bank_decline", "insufficient_funds", "upi_timeout", "card_declined", "otp_failed", "technical"] | C | 34 | Names are ours |
| `delivery.transit_median_days` | [2.0, 3.0, 4.5, 5.0, 6.0] | B | 38 | 1-3 days metro, 3-7 business days tier 2/3 (Shipmozo) |
| `delivery.first_attempt_success` | [0.75, 0.7, 0.62, 0.52, 0.48] | B | 38 | 72-78% metro, 45-58% tier 3 (base.blog) |
| `delivery.rto_cod_by_tier` | [0.15, 0.19, 0.24, 0.29, 0.32] | C | 35 | Vendor-blog ranges were metros 18-24, tier1 24-30, tier2 30-38, tier3/rural 38-50. Scaled by ~0.7 because category and serial-RTO multipliers push the blended COD RTO to ~36%, above the 20-30% overall range in the answers. Our own calibration. |
| `delivery.rto_prepaid` | 0.025 | B | 29 | Prepaid RTO 2-3%; one source says 20-30%, treated as outlier |
| `delivery.serial_rto_factor` | 3.0 | C | 32 |  |
| `delivery.rto_reason_mix` | {"refused": 0.33, "not_home": 0.3, "address": 0.22, "other": 0.15} | B | 31 | Changed mind ~30%, customer unavailable ~25% (eGrow) |
| `delivery.cod_remit_days` | [2, 8] | C | 28 | COD marked paid after delivery |
| `delivery.return_prepaid` | 0.1 | B | 29 | COD returns run 1.8-2.3x prepaid |
| `delivery.return_cod_factor` | 2.0 | B | 29 |  |
| `delivery.serial_return_factor` | 3.5 | C | 32 |  |
| `delivery.return_median_days` | 6.0 | C | 30 | Return window 7-15 days |
| `delivery.partial_refund_share` | 0.25 | C | 29 |  |
| `delivery.finality_days` | 45 | C | 30 | Orders older than this are final for labels |
| `tickets.p_issue` | {"general": 0.03, "failed_delivery": 0.3, "refund": 0.18, "rto": 0.1, "payment": 0.15} | D | 39 | No India benchmark |
| `tickets.solve_median_days` | 1.5 | C | 41 |  |
| `tickets.closed_after_solved_days` | 4 | A | 41 | Zendesk default auto-close 4 days after Solved (verified) |
| `tickets.reopen_prob` | 0.05 | C | 41 |  |
| `tickets.csat_response` | 0.3 | C | 41 |  |
| `messaging.window_hours_ist` | [10, 21] | C | 46 | Promotional send window; vendor claim, TRAI rule NOT verified |
| `messaging.channel_pref` | {"whatsapp": 0.5, "email": 0.4, "sms": 0.1} | C | 42 |  |
| `messaging.channel_stats` | {"email": {"deliver": 0.97, "bounce": 0.02, "open": 0.258, "click_given_open": 0.32, "unsub": 0.0009}, "whatsapp": {"deliver": 0.94, "open": 0.68, "click_given_ | B | 42 | Email open 25.8%, click 8.2%, unsub 0.09% (GetResponse via CampaignHQ); WhatsApp read ~68% measured, click 15-25%; delivered-webhook can be skipped when read immediately (Meta docs) |
| `messaging.legacy_p` | {"a0": -2.1, "a_p7": 6.0, "a_orders": 0.35, "cart_flow_p": 0.6} | C | 43 | Biased targeting: send probability rises with purchase propensity and past orders |
| `messaging.legacy_action_mix` | {"reminder": 0.35, "discount": 0.3, "free_shipping": 0.1, "bundle": 0.25} | C | 43 |  |
| `messaging.policy_do_nothing` | 0.25 | C | 44 | Regime-2 exploration policy: do_nothing share; rest uniform over allowed actions; propensity logged |
| `messaging.action_cost` | {"reminder": 1, "discount": 100, "free_shipping": 60, "bundle": 40, "agent_call": 40, "do_nothing": 0} | C | 37 | INR; discount shown as 10% of a 1,000 basket |
| `messaging.discount_pct` | 10 | C | 48 |  |
| `messaging.freq_cap_7d` | 2 | C | 46 | Max marketing messages per rolling 7 days |
| `messaging.margin_floor` | 0.08 | C | 25 | Minimum margin after offer |
| `messaging.offer_abuse_returns_180d` | 2 | C | 32 |  |
| `messaging.cod_limit_rto_count` | 2 | C | 29 |  |
| `messaging.approval_basket_band_edge` | 2500 | C | 48 | Discounts on baskets at or above this need approval |
| `messaging.discount_budget_floor` | 0.3 | C | 48 | Stateless proxy: availability falls through the month to this floor |
| `messaging.task_status_mix` | {"done": 0.55, "ignored": 0.3, "open": 0.05, "overridden": 0.1} | D | - | Handoffs depend on client team |
| `messaging.fatigue_k` | 0.5 | C | 46 | uplift x 1/(1+k*max(0,msgs14d-1)) |
| `messaging.unsub_fatigue` | 0.004 | C | 46 | Added unsubscribe prob per message over 2 in 14 days |
| `messaging.unsub_reacts_badly` | 0.15 | C | 46 |  |
| `messaging.response_mean_days` | 1.3 | C | 45 | Exponential response delay (half-life about 0.9 day) |
| `messaging.pull_forward_days` | [5, 20] | C | 48 | Discount orders defer the next natural order |
| `messaging.agent_call_min_spend` | 5000 | C | - | PDF F7: handoff for high-value customers |
| `noise.duplicate` | 0.02 | C | 49 | Default 1-3% |
| `noise.missing_field` | 0.01 | C | 49 | Default 0.5-2% |
| `noise.wrong_timestamp` | 0.005 | C | 49 |  |
| `noise.late` | 0.02 | C | 22 | Late share 1-3% |
| `noise.out_of_order` | 0.015 | C | 22 |  |
| `noise.ga4_late_days` | 2.9 | A | 22 | GA4 daily tables update up to 2 calendar days plus today (verified, Google) |
| `noise.bot_share_of_anon_sessions` | 0.03 | C | 50 | Global 53% automated traffic is vendor telemetry; filtered shop far lower |
| `noise.shared_phone` | 0.015 | C | 50 | No public figure |
| `noise.tracking_gaps` | {"per_year": 2, "days": 1.5} | C | 52 | Browsing events dropped |
| `campaigns.ad_campaigns` | {"paid_social": 4, "paid_search": 4, "affiliate": 1} | D | 5 | Count per channel |
| `campaigns.cpa_inr` | {"paid_social": 450, "paid_search": 380, "affiliate": 220} | C | 5 |  |
| `campaigns.cpc_inr` | 18 | C | 5 |  |
| `campaigns.ctr` | 0.012 | C | 5 |  |
| `calendar.seasons` | [{"start": "2024-11-01", "end": "2024-11-06", "mult": 1.8}, {"start": "2025-09-23", "end": "2025-10-24", "mult": 1.8, "sale_start": "2025-09-23", "sale_end": "2 | C | 13,55 | Festive-sale dates for 2024/2025 are assumptions; 8-9 Oct 2026 from answers (secondary source); Diwali 1 Nov 2024, 20/21 Oct 2025, 8 Nov 2026 unverified |
| `states.new_customer_window_days` | 45 | C | - | PDF: thresholds are starting points |
| `states.reengage_factor` | 1.5 | C | - | Gap longer than 1.5 x usual gap |
| `states.default_usual_gap_days` | 30 | C | - |  |
| `states.reactivate_days` | 90 | C | 10 | No order or visit for 90 days; stays Reactivate beyond 180 (flagged gap) |
| `states.retarget_cooling_days` | 30 | C | - |  |
| `states.retarget_sessions` | 3 | C | - | Sessions without an order that count as 'viewed a product' |
| `states.rule_version` | "ecom_rules_v0.1" | C | - |  |
| `labels.horizons_days` | [7, 30] | C | 11 |  |
| `labels.final_buffer_days` | 45 | C | 30 | Q53 (own answer): see docs/q53_leakage.md |