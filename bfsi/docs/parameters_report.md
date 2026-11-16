# Parameters report: BFSI personal-loan pack

Every assumption in `vynqe_synth/config/bfsi.yaml`. SYNTHETIC DATA: these are generator settings, not measurements of any real lender.

Grades: **A** verified from an official source; **B** researched, secondary or vendor source (low confidence); **C** our assumption or calibration, adjustable; **D** placeholder with no basis (client-only data). `Q` is the question number in the BFSI answers file (`-` = none).

## Not verified at all
- Account Aggregator 80% monthly success floor from 1 December 2026 (the article was not reachable); only the 74.4% figure from the answers file is used as a reference.
- TRAI promotional-message rules (the 10:00 to 19:00 window is our own assumption).
- DPDP consent-manager dates (law-firm summaries only; the Gazette was not checked).
- Diwali and festive dates in `calendar.festive_windows`.
- Mandate failure-reason names: Razorpay lists none, so the names are ours.

## Parameters tuned by running the generator (all grade C)
These were adjusted until a 30,000-person run matched the targets in the answers file. They are placeholders for a real lender sample:
- `population.p_start_application` (target: lead to disbursal 3-8%, Q7)
- `risk.z_norm`, `risk.band_cuts`, `risk.band_noise_sd` (target: band shares 30/40/20/10, Q23; band not near perfect, Q55)
- `repayment.risk_weight`, `repayment.stress_offset`, `repayment.missed_cure` (target: EMI states, Q31; default by band, Q26)
- `messaging.emi_nudge_shift` (planted effect size; illustrative)

Count by grade: A=4, B=18, C=133, D=6 (total 161)

| Parameter | Value | Grade | Q | Note |
|---|---|---|---|---|
| `run.start_date` | "2023-11-01" | C | 2 | 36-month window ending 31 Oct 2026 (brief: 36 months for BFSI; answers suggest 24, but Q25 labels only loans 15+ months old) |
| `run.n_days` | 1096 | C | 2 | 36 months |
| `run.regime2_day` | 548 | C | 46 | Months 1-18 legacy targeting (about 1 May 2025); months 19-36 randomised policy |
| `run.holdout_share` | 0.08 | C | 49 | Q49: 5 to 10% of eligible borrowers, optional nudges only |
| `run.holdout_salt` | "vynqe-bfsi-holdout-salt-v1" | C | 49 | Salted hash (brief rule 15) |
| `run.hash_secret` | "dummy-bfsi-secret-not-real" | C | - | Dummy HMAC secret (brief rule 8) |
| `population.growth_per_year` | 0.2 | C | 5 | Lender-specific; no public figure |
| `population.acquisition_mix` | {"paid_social": 0.22, "paid_search": 0.15, "partner": 0.12, "organic": 0.13, "whatsapp": 0.05, "referral": 0.08, "existing_base": 0.25} | D | 4,5 | Q4: 20 to 30% existing-customer applicants; paid mix is lender data |
| `population.device_mix` | {"android": 0.7, "ios": 0.1, "web_mobile": 0.12, "web_desktop": 0.08} | D | 16 | Lender data |
| `population.tier_mix` | [0.17, 0.22, 0.27, 0.2, 0.14] | B | 3 | metro, tier1, tier2, tier3, rural. Semi-urban and rural about 61% of originations (CIBIL via FPJ) |
| `population.salaried_share` | 0.62 | B | 3 | Borrower survey, not a portfolio |
| `population.under30_share` | 0.6 | B | 3 | Over 60% of fintech borrowers under 30 (TransUnion CIBIL) |
| `population.income_monthly_median` | {"salaried": 30000, "self_employed": 34000} | D | 3 | INR; lender data |
| `population.income_sigma` | {"salaried": 0.55, "self_employed": 0.8} | C | 18 | Wide overlap so types are not trivially separable |
| `population.tier_income_mult` | [1.35, 1.15, 1.0, 0.85, 0.7] | C | 3 |  |
| `population.amount_edges` | [0, 10000, 25000, 50000, 100000, 250000] | C | 1 | Band edges in INR (brief rule 7) |
| `population.amount_clip` | [5000, 500000] | B | 1 | Digital NBFC average 18,802; traditional NBFC about 1 lakh; banks about 5 lakh |
| `population.tenure_choices` | [6, 12, 18, 24, 36, 48, 60] | B | 1 | Mostly 12 to 60 months |
| `population.tenure_band_edges` | [0, 12, 24, 36, 60] | C | 1 | Visible tenure band (workbook marks tenure Skip) |
| `population.apr_by_band` | [0.16, 0.22, 0.28, 0.34] | B | 1 | Banks 10.5-24%, NBFCs 10.5-36%; by lender band 1..4 |
| `population.fee_pct_by_band` | [0.02, 0.03, 0.045, 0.06] | B | 1 | Fees 1-3% banks, 2-9% some NBFCs |
| `population.existing_customer_start_boost` | 0.2 | C | 4 | Added to p(start application) |
| `population.p_start_application` | {"paid_social": 0.28, "paid_search": 0.34, "partner": 0.31, "organic": 0.34, "whatsapp": 0.34, "referral": 0.4, "existing_base": 0.45} | C | 7,16 | Lead to disbursal 3-8% (Q7). Persons are leads the lender can see; upstream drop-offs are not in the data |
| `population.anon_visitors_per_person` | 1.5 | C | 21 | Anonymous-only visitors (events only) |
| `population.prior_sessions_mean` | 1.6 | C | 21 | Pre-application sessions before first identification |
| `population.identify_link_prob` | 0.6 | C | 21 | Share of identify events that carry the merged anonymous id (phone OTP is deterministic, linking the anonymous id is not) |
| `population.type_change_share` | 0.1 | C | 22 | Types are not static |
| `population.type_change_to` | ["repeat_borrower", "one_time", "short_term_cash"] | C | 22 |  |
| `population.reacts_badly_share` | 0.04 | C | 50 | Complaint and do-not-disturb risk |
| `population.fraud_share` | 0.008 | C | 30 | Identity fraud 0.5-1% (default range) |
| `population.stacking_share` | 0.3 | B | 30 | About half of unsecured borrowers hold another live loan (RBI); we flag 30% as heavy stacking |
| `population.types` | {"short_term_cash": {"share": 0.35, "lti": [0.02, 0.1], "urgency": [5, 2], "shop": [2, 6], "kyc": [2, 6], "topup": [2, 5], "prepay": [2, 6], "repeat_p": 0.1, "calc_views": [1, 2], "uplift": {"nudge": 0.08, "agent_call": 0.12, "fee_waiver": 0.03, "offer": 0.02, "emi_nudge": 0.05}}, "planned_big_ticke | B | 17,18,19,20 | Shares from Q17 (B/C/D). Loan-to-income ranges from Q18 (C). Uplifts are illustrative planted truths (grade C), not measurements |
| `population.channel_type_factor` | {"existing_base": {"repeat_borrower": 3.0}, "paid_social": {"short_term_cash": 1.3}, "paid_search": {"rate_shopper": 2.0, "planned_big_ticket": 1.3}, "partner": {"debt_consolidation": 1.5}} | C | 17 |  |
| `population.consent_initial` | {"email": {"granted": 0.55, "denied": 0.03}, "sms": {"granted": 0.5, "denied": 0.05}, "whatsapp": {"granted": 0.55, "denied": 0.03}} | D | 47 | Rest = unknown. Unknown means hold. Set at lead capture / application |
| `population.optin_at_application_prob` | 0.3 | C | 47 | Unknown channel opts in at application |
| `population.do_not_market_share` | 0.02 | C | 47 | Core-banking do_not_market flag |
| `sessions.mean_pages` | 4.0 | C | 20 | Pages per session |
| `sessions.max_events` | 25 | C | 20 |  |
| `sessions.gap_median_sec` | 12 | C | 20 |  |
| `sessions.timeout_minutes` | 30 | A | - | GA4 default 30-minute inactivity (verified in e-commerce pack); our own tracker follows the same rule |
| `sessions.hour_weights_ist` | [1.0, 0.6, 0.4, 0.3, 0.3, 0.5, 1.0, 2.0, 3.0, 4.0, 5.0, 5.5, 6.0, 6.0, 5.5, 5.0, 5.0, 5.0, 5.5, 6.5, 8.0, 9.0, 8.0, 5.0] | C | 19 | Cash-need borrowers apply late evening (Q19) |
| `sessions.login_prob` | 0.3 | C | 21 |  |
| `sessions.borrower_sessions_per_month` | 1.2 | C | 20 | Post-disbursal app visits |
| `calendar.salary_day_mult` | 1.5 | C | 6 | Days 1-7 and last 2 days of month: 1.3 to 2x (default) |
| `calendar.month_end_days` | 2 | C | 6 |  |
| `calendar.festive_mult` | 1.4 | C | 6 | Festive weeks (Oct-Nov) and March tax season |
| `calendar.festive_windows` | [["2023-11-01", "2023-11-20"], ["2024-10-15", "2024-11-10"], ["2025-10-01", "2025-11-05"], ["2026-10-08", "2026-10-31"]] | C | 6 | Diwali dates unverified |
| `calendar.tax_season` | [3, 3] | C | 6 | March |
| `funnel.p_proceed_kyc` | 0.6 | C | 7,10 | KYC loses 40-60% (Q7); this and the pass rates below give about 50% from application started |
| `funnel.kyc_first_pass` | 0.7 | B | 10 | Multiplied down by kyc_friction |
| `funnel.kyc_retry_prob` | 0.75 | C | 10 |  |
| `funnel.kyc_retry_success` | 0.6 | C | 10 |  |
| `funnel.kyc_check_mix` | {"ekyc_otp": 0.4, "digilocker": 0.35, "video_kyc": 0.08, "manual_document": 0.17} | C | 10 |  |
| `funnel.kyc_minutes` | {"ekyc_otp": 4, "digilocker": 3, "video_kyc": 45, "manual_document": 1440} | C | 8 | Median minutes; sigma below |
| `funnel.kyc_fail_reasons` | {"document_quality": 0.4, "mismatch": 0.3, "timeout": 0.2, "other": 0.1} | C | 10 |  |
| `funnel.time_sigma` | 1.0 | C | 8 | Lognormal sigma for step times (P90 about 3.6x median) |
| `funnel.p_consent` | 0.88 | B | 11 | AA consent 65-75% overall default; split into consent and fetch |
| `funnel.p_fetch_ok` | 0.85 | B | 11 | Fetch success 75-85% |
| `funnel.fetch_retry_prob` | 0.5 | C | 11 |  |
| `funnel.fetch_retry_success` | 0.6 | C | 11 |  |
| `funnel.aa_revoke_prob` | 0.02 | C | 11 | Withdrawn later |
| `funnel.aa_fail_reasons` | {"bank_timeout": 0.5, "denied": 0.2, "technical": 0.3} | C | 11 | Our category names |
| `funnel.decision_minutes_auto` | 20 | C | 8,12 | Median; auto decisions take seconds to hours |
| `funnel.manual_review_days` | [1, 3] | C | 12 |  |
| `funnel.approve_by_band` | [0.8, 0.5, 0.3, 0.15] | C | 24 | Q24 low 80 / medium 50 / high 15; band 3 interpolated |
| `funnel.refer_share` | 0.08 | C | 12 | Manual review 5-10% |
| `funnel.refer_approve` | 0.45 | C | 12 |  |
| `funnel.reject_reasons` | {"policy": 0.35, "income": 0.3, "kyc": 0.1, "fraud": 0.05, "other": 0.2} | C | 24 | Categories only, no bureau detail |
| `funnel.accept_base` | 0.7 | C | 13 | 60-75%; falls when sanctioned below request or APR high |
| `funnel.accept_ratio_slope` | 0.5 | C | 13 | Subtract slope x (1 - sanctioned/requested) |
| `funnel.accept_apr_slope` | 1.0 | C | 13 | Subtract slope x max(0, apr - 0.28) |
| `funnel.accept_shop_slope` | 0.25 | C | 13 | Rate shoppers decline more (shopping_around) |
| `funnel.accept_hours` | 6 | C | 8 | Median hours to accept |
| `funnel.esign_success` | 0.93 | B | 14 | E-sign about 90% |
| `funnel.mandate_first_success` | 0.88 | B | 14 | Mandate 85-92% first try (vendor claim, not independent) |
| `funnel.mandate_retry_prob` | 0.7 | C | 14 |  |
| `funnel.mandate_retry_success` | 0.75 | C | 14 |  |
| `funnel.mandate_fail_proceed` | 0.4 | C | 14 | Share who still disburse with manual repayment after final mandate failure |
| `funnel.mandate_cancel_6m` | 0.03 | C | 32 | Cancel within 6 months 2-5% |
| `funnel.mandate_error_mix` | {"rejected_by_bank": 0.4, "technical": 0.3, "limit_too_low": 0.2, "other": 0.1} | C | 32 | Razorpay docs list no failure-reason values; names are ours |
| `funnel.p_disburse` | 0.93 | C | 15 | Approved but never disbursed 5-15% |
| `funnel.disburse_hours` | 18 | B | 15 | Median hours; industry average 7-10 days; digital aims minutes to a day |
| `funnel.disburse_sigma` | 1.4 | C | 8 | P90 about 6x median |
| `funnel.abandon_return_7d` | 0.15 | C | 9 | 10-20% of abandoners return within 7 days |
| `funnel.abandon_return_mean_days` | 2.0 | C | 9 |  |
| `funnel.duplicate_application` | 0.04 | C | 51 | 3-8% duplicate applications (rate shoppers resubmit) |
| `funnel.kyc_wait_days` | 2 | C | 10 | KYC pending beyond this = KYC drop-off |
| `funnel.stall_days` | 14 | C | 9 | No activity for this long = application stalled |
| `risk.band_shares` | [0.3, 0.4, 0.2, 0.1] | C | 23 | Applicants by lender band 1..4 |
| `risk.band_noise_sd` | 0.7 | C | 23,55 | Lender band is a noisy function of true risk (Q55: not near perfect) |
| `risk.z_coefs` | {"small_amount": 0.25, "under30": 0.25, "tier": 0.12, "self_employed": 0.25, "existing": -0.35, "stacking": 0.3, "lti": 0.8, "fraud": 1.2, "noise_sd": 0.8} | C | 29 | Correlated drivers of true risk (small tickets, young, small towns, self-employed higher; existing customers lower) |
| `risk.z_norm` | [0.17, 0.9] | C | 23 | Mean and sd of the raw risk score, calibrated from a 30,000-person run |
| `risk.band_cuts` | [-0.64, 0.63, 1.53] | C | 23 | Cut points on the lender score (true risk plus noise) giving shares 30/40/20/10 across all people; calibrated from a 30,000-person run |
| `repayment.rho` | 0.6 | C | 22,31 | Persistence of monthly repayment stress |
| `repayment.risk_weight` | 0.55 | C | 29,31 | Weight of true risk in monthly stress |
| `repayment.state_cuts` | [0.85, 0.93, 0.98] | C | 31 | Baseline shares: on time 85%, grace 8%, late 5%, missed 2% (Q31 for mandate borrowers) |
| `repayment.stress_offset` | 0.1 | C | 31 | Added to monthly latent stress so that the disbursed book (tilted to lower-risk bands) still shows the Q31 state shares |
| `repayment.month_drift` | 0.02 | C | 31 | Worse in later months |
| `repayment.grace_days` | [1, 5] | C | 31 |  |
| `repayment.late_days` | [6, 29] | C | 31 |  |
| `repayment.missed_cure` | {"d30_59": 0.35, "d60_89": 0.3} | C | 27,28 | Share of missed instalments cured in each window; the rest reach 90+ days (default) |
| `repayment.fail_error_mix` | {"insufficient_funds": 0.72, "technical": 0.15, "bank_decline": 0.08, "mandate_inactive": 0.05} | B | 33 | Split technical codes from insufficient funds |
| `repayment.autopay_methods` | {"upi_autopay": 0.65, "emandate": 0.35} | C | 32 |  |
| `repayment.manual_methods` | {"manual_upi": 0.7, "netbanking": 0.3} | C | 31 |  |
| `repayment.default_flag_delay_days` | [1, 5] | C | 52 | Core-banking extract is daily; lender flags default a few days after 90 DPD |
| `repayment.prepay_share` | 0.15 | C | 34 | 10-20% prepay before term |
| `repayment.cooling_off_share` | 0.012 | A | 34 | RBI Digital Lending Directions para 10: exit within a cooling-off period of at least 1 day without penalty; share is ours |
| `repayment.part_pay_share` | 0.04 | C | 35 | 3-5% part-payments: NOT modelled in v0.1 (gap); restructuring under 1% also not modelled |
| `repayment.complaint_share` | 0.02 | C | 39 | 1-3% raise a complaint |
| `repayment.complaint_late_mult` | 3.0 | C | 39 |  |
| `repayment.complaint_days` | [3, 20] | C | 39 |  |
| `repayment.collections_first_contact_days` | [1, 3] | C | 38 |  |
| `repayment.topup_after_ontime` | 6 | C | 41 | Top-up eligible after 6 on-time EMIs |
| `repayment.topup_hazard_month` | 0.04 | C | 41 | Natural monthly top-up application probability x topup_propensity x 2 |
| `repayment.winback_return` | {"m6": 0.1, "m12": 0.18, "m24": 0.25} | C | 44 | Closed customers returning (cumulative) |
| `repayment.dormant_after_days` | 90 | C | 44 | Closed with no activity for this long = Dormant |
| `repayment.preapproved_hold_share` | 0.4 | C | 42 | 30-50% of good-standing customers hold a pre-approved offer |
| `messaging.window_hours_ist` | [10, 19] | C | 40 | Promotional window; TRAI rules NOT verified |
| `messaging.channel_pref` | {"whatsapp": 0.45, "sms": 0.3, "email": 0.25} | C | 45 |  |
| `messaging.channel_stats` | {"email": {"deliver": 0.97, "open": 0.258, "click_given_open": 0.32, "unsub": 0.0009}, "whatsapp": {"deliver": 0.94, "open": 0.68, "click_given_open": 0.25, "skip_delivered_when_read": 0.1, "unsub": 0.0}, "sms": {"deliver": 0.95, "open": 0.0, "click_given_open": 0.0, "unsub": 0.0}} | B | 45 | Email open 25.8%, click 8.2%, unsubscribe 0.09% (GetResponse via CampaignHQ); WhatsApp read about 68% |
| `messaging.legacy_p` | {"a0": -1.4, "a_band": -0.45, "a_value": 0.25} | C | 46 | Biased targeting: lower-risk and higher-value borrowers receive more nudges and offers |
| `messaging.legacy_action_mix` | {"nudge": 0.5, "offer": 0.25, "fee_waiver": 0.1, "emi_nudge": 0.15} | C | 46 |  |
| `messaging.policy_do_nothing` | 0.25 | C | 49 | Regime-2 exploration policy: do_nothing share; rest uniform over allowed actions; propensity logged |
| `messaging.action_cost` | {"nudge": 1, "agent_call": 60, "fee_waiver": 400, "offer": 2, "emi_nudge": 1, "do_nothing": 0} | C | 37 | INR |
| `messaging.freq_cap_7d` | 2 | C | 45 | Marketing frequency cap per rolling 7 days (max 4 a month, Q45) |
| `messaging.rep_engaged_days` | 7 | C | - | No other marketing within 7 days of an agent-call task |
| `messaging.fee_waiver_approval_amount` | 100000 | C | - | Fee waivers on loans at or above this need approval (task) |
| `messaging.suitability_band_max` | 4 | C | - | Offers are not sent to band 4 or to anyone late in the last 90 days |
| `messaging.capacity_floor` | 0.35 | C | - | Stateless proxy for agent-call capacity: availability falls through the month to this floor |
| `messaging.task_status_mix` | {"done": 0.55, "ignored": 0.25, "open": 0.05, "overridden": 0.15} | D | - |  |
| `messaging.call_disposition_mix` | {"connected": 0.45, "not_reachable": 0.3, "callback_requested": 0.1, "not_interested": 0.1, "application_completed": 0.05} | C | 37 |  |
| `messaging.fatigue_k` | 0.5 | C | 50 | uplift x 1/(1+k*max(0,msgs14d-1)) |
| `messaging.unsub_fatigue` | 0.004 | C | 50 |  |
| `messaging.unsub_reacts_badly` | 0.15 | C | 50 |  |
| `messaging.response_mean_days` | 1.5 | C | 45 | Exponential delay of an incremental response |
| `messaging.stall_decision_days` | [1, 4, 10] | C | 9 | Decision points after a stall |
| `messaging.lead_decision_days` | [1, 5] | C | 9 | Decision points for a lead who has not applied |
| `messaging.emi_nudge_days_before` | 4 | C | 36 | Optional nudge point before the due date; mandatory reminders are separate and never held out |
| `messaging.emi_nudge_shift` | 0.7 | C | 36 | Latent-stress reduction (sd units) when an emi_nudge works, scaled by planted uplift / 0.05 |
| `noise.duplicate` | 0.02 | C | 51 | Generic duplicate events (application duplicates are separate, see funnel.duplicate_application) |
| `noise.missing_field` | 0.01 | C | 51 | 1-3% missing fields |
| `noise.wrong_timestamp` | 0.005 | C | 51 |  |
| `noise.late` | 0.02 | C | 52 |  |
| `noise.out_of_order` | 0.02 | C | 52 | 1-3% out of order |
| `noise.ga4_late_days` | 2.9 | C | 52 | Used as the late-arrival cap for all sources (naming kept from the shared core) |
| `noise.slow_sources` | {"razorpay": [1.0, 2.0], "core_banking": [0.2, 1.0]} | B | 52 | Mandate debit results T+1 to T+2; core banking daily extract |
| `noise.bot_share_of_anon_sessions` | 0.03 | C | 51 |  |
| `noise.shared_phone` | 0.015 | C | 51 |  |
| `noise.tracking_gaps` | {"per_year": 2, "days": 1.5} | C | 53 | Browsing events dropped |
| `campaigns.ad_campaigns` | {"paid_social": 4, "paid_search": 4, "partner": 2} | D | 5 |  |
| `campaigns.cpc_inr` | 14 | C | 5 |  |
| `campaigns.ctr` | 0.015 | C | 5 |  |
| `states.application_stall_days` | 14 | C | 9 | Application started with no activity for this long falls back to Lead |
| `states.kyc_wait_days` | 2 | C | 10 |  |
| `states.first_cycle_days` | 35 | C | - | Activated until the first EMI cycle begins (days after disbursal) |
| `states.dormant_days` | 90 | C | 44 |  |
| `states.rule_version` | "bfsi_rules_v0.1" | C | - | All states marked Added in the brief are proposals |
| `labels.horizons_days` | [7, 30] | C | 11 | Funnel and nudge outcomes |
| `labels.default_window_months` | 12 | A | 25 | Default label: 90+ days past due within 12 months on book |
| `labels.min_loan_age_months` | 15 | A | 25,28 | Label only loans 15+ months old |
| `labels.final_buffer_days` | 45 | C | 54 | Same finality buffer as e-commerce for funnel labels |