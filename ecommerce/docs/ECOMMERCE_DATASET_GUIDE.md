# Vynqe E-commerce Synthetic Dataset: Team Guide

**Version 0.1.0 · Generator: `vynqe_synth` · Pack: e-commerce · Sample: 1,000 customers, seed 42**

> **This data is SYNTHETIC.** No real customer, order or message exists in it. Every number comes from a configured assumption (see `parameters_report.md`). It is built to develop and test the Customer Lifecycle Intelligence pipeline. **It says nothing about how any model will perform on real customers, and no result from it should be quoted as real-world evidence.**

---

## 1. What this dataset is for

An Indian D2C online store (fashion, beauty, home, accessories) with two years of history. It simulates the data a real store would pull from its tools, so the lifecycle engine can be built and tested before any client data arrives.

| Real tool | What it provides here |
|---|---|
| Shopify | customers, orders, checkouts, refunds |
| GA4 | page views, identify events (browsing) |
| Razorpay | payment attempts |
| Shiprocket | shipment and delivery status |
| Zendesk | support tickets |
| Klaviyo, WhatsApp | messages and message status |
| Decision service (ours) | the action we chose, options, blocked actions, reasons |
| Outcome checker (ours) | confirmed outcomes (the only writer of `outcome_confirmed`) |

**What it lets you test:** state rules, features as of a point in time, labels with a finality buffer, guardrails, identity stitching, messy-data handling, and (in the randomised period only) measuring the real effect of each action.

---

## 2. Dataset at a glance (1,000-customer sample)

| Item | Value |
|---|---|
| Period | 1 Nov 2024 to 31 Oct 2026 (730 days) |
| Period 1, legacy targeting | 1 Nov 2024 to 31 Oct 2025 (messages sent to likely buyers, biased) |
| Period 2, randomised | 1 Nov 2025 to 31 Oct 2026 (logged random policy, 8% holdout, guardrails) |
| Customers | 1,000 |
| Events | 245,166 (about 245 per customer) |
| Orders | 2,448 (2.45 per customer; 3.38 per buyer; 72.4% of customers bought) |
| Payment attempts | 1,083 (1.08 per customer; 995 successful) |
| Tickets | 386 (0.39 per customer; 27% of customers raised one) |
| Sessions | about 28,300 identified, about 3,500 anonymous (28.3 identified per customer; median customer 13) |
| Actions | 19,916 |
| State stays | 5,209 |
| Currency | Indian rupees (amounts shown only as bands) |

Presets: `tiny` 1,000 customers, `dev` 10,000 (recommended for model work), `full` 100,000. Same seed gives identical data.

---

## 3. The 9 tables

```
customers ──< orders ──< payments
    │            │
    │            └── (checkout_id links to checkout events)
    ├──< tickets
    ├──< actions   (message_id, decision_id link to events)
    ├──< state_history
    └──< events    (unit_id, person_key, anonymous_id)

campaigns (campaign_id)   category_value (category, month)   : lookup tables
```

Join key everywhere: **`unit_id`** (pseudonymous, like `C0000042`). `person_key` is a keyed hash of the phone number and can be shared by two customers when they share a phone.

### 3.1 `customers` (1,000 rows): one row per person, plus identity map

**Why:** every other table points back here. It also holds the one-reference-per-tool identity map and the holdout assignment.

| Column | Meaning |
|---|---|
| `unit_id` | Customer key |
| `person_key` | HMAC-SHA-256 of the normalised phone (32 hex). Not unique if a phone is shared (about 1.5%) |
| `created_at`, `first_order_at` | First seen; first order (null for 27.6% who never bought) |
| `orders_count`, `spend_band` | **Extract-time snapshots: do not use as features** (they contain the future) |
| `device_class` | android 75%, web_mobile 12%, web_desktop 7%, ios 6% |
| `acquisition_channel` | paid_social 32%, organic 26%, paid_search 17%, whatsapp 11%, referral 7%, affiliate 6% |
| `campaign_id` | Acquisition campaign, if paid |
| `email_consent`, `sms_consent`, `whatsapp_consent` | granted / denied / unknown / withdrawn. Extract-time snapshot; history is in `consent_change` events. Email: 63% granted, 31% unknown |
| `geo_tier` | tier2 27%, metro 21%, tier1 20%, tier3 20%, rural 12% (extension, not in workbook) |
| `regime_first_seen` | legacy_targeting 43%, randomised_holdout 57% |
| `holdout_group`, `holdout_assigned_at`, `holdout_share`, `holdout_strategy` | 7.7% control (target 8%), salted-hash assignment. Control customers get no action after the assignment date |
| `shopify_customer_ref`, `klaviyo_profile_ref`, `razorpay_ref`, `zendesk_requester_ref`, `ga4_user_id` | One reference per tool. `razorpay_ref` and `zendesk_requester_ref` are null until the customer pays online or raises a ticket |
| `email_key` | HMAC of the lowercased email |

### 3.2 `events` (245,166 rows): the canonical event stream

**Why:** the state engine, features and labels are all built from this one stream. It keeps `occurred_at` (when it happened) separate from `ingested_at` (when we received it), so late and out-of-order data can be tested.

| Column | Meaning |
|---|---|
| `event_id` | Row ID (duplicates get a new ID) |
| `source_event_id` | `object:id:status`. **Use this to de-duplicate** |
| `event_type`, `source_system` | See the two tables below |
| `person_key`, `anonymous_id`, `unit_id` | Identity. Before login or identification, only `anonymous_id` is set |
| `occurred_at`, `ingested_at` | Event time; arrival time |
| `channel`, `campaign_id`, `placement_id` | Traffic or message channel. `placement_id` is always empty in this pack |
| `consent_status` | Set on consent events |
| `properties` | JSON; keys depend on the object (see below) |

**Event types in the sample:**

| event_type | Rows | Sources | What it is |
|---|---|---|---|
| page_view | 157,821 | ga4 | Browsing. Group into sessions with a 30-minute inactivity rule |
| message_status | 35,248 | klaviyo, whatsapp | sent / delivered / opened / clicked / bounced / failed / unsubscribed |
| record_status_changed | 19,270 | shopify, shiprocket, razorpay, zendesk | Order, shipment, payment and ticket status changes |
| decision_made | 12,421 | decision_service | One per decision point, including do_nothing |
| record_created | 12,169 | shopify, razorpay, zendesk | order, checkout, payment, ticket and refund created |
| outcome_confirmed | 3,957 | outcome_checker | Payment captured, order paid, shipment delivered |
| consent_change | 1,981 | shopify, klaviyo, warehouse | Consent history |
| identify | 1,024 | ga4 | Links an anonymous ID to a customer (`merged` is set for only about 35%) |
| link_click | 1,275 | klaviyo, whatsapp | Clicks on message links |

**`properties` keys by object:** `order` (order_id, status, amount_band, payment_mode, checkout_id, category, item_count, discount_code, decision_id) · `checkout` (checkout_id, status open/completed/abandoned, exit_reason) · `payment` (payment_id, method, order_id, error_code, attempt_no) · `shipment` (order_id, to, attempt_no, courier, rto_reason) · `ticket` (ticket_id, ticket_type, priority, tags, status, csat) · `refund` (order_id, amount_band, reason_category).

### 3.3 `orders` (2,448 rows): one row per order, shipment and refund merged in

**Why:** orders hold the outcomes the lifecycle engine cares about: repeat purchase, COD failure, returns.

| Column | Meaning and distribution |
|---|---|
| `order_id`, `unit_id`, `checkout_id` | Keys |
| `created_at`, `processed_at` | Placed; processed |
| `financial_status` | Snapshot: paid 68%, cancelled 17%, refunded 10%, partially_refunded 3%, placed 2% (placed means COD not yet remitted) |
| `fulfilment_status` | fulfilled 80%, returned_to_stock 16% (RTO), unfulfilled 4.5% |
| `amount_band` | Bands only: 0-500 18%, 500-1000 29%, 1000-1500 22%, 1500-2500 20%, 2500-5000 10%, 5000+ 0.4% |
| `item_count` | 1: 43%, 2: 38%, 3: 14%, 4+: 5% |
| `payment_mode` | cod 59%, prepaid 41% |
| `discount_code`, `discount_band` | Discount on 9% of orders (mostly 10%) |
| `order_source` | web 54%, app 46% |
| `channel`, `campaign_id` | Traffic source of the order: organic 68%, whatsapp 11%, paid_social 9%, email 6% |
| `decision_id` | Set **only if the customer clicked our message**. Real attribution sees only clicks |
| `category_primary` | apparel_women 31%, apparel_men 19%, footwear 15%, accessories 11%, beauty 11%, electronics_acc 7%, home 7% (extension) |
| `cancelled_at`, `paid_at` | `paid_at` for COD is the remittance date |
| `courier` | delhivery, bluedart, ecom_express, xpressbees (about 24% each) |
| `delivery_status`, `delivery_status_changed_at`, `delivered_at`, `attempt_count` | delivered 78%, rto 16%, failed_delivery 0.5%, null 6% (never shipped) |
| `rto_flag`, `rto_reason_category` | Return to origin: refused, not_home, address, other |
| `refund_created_at`, `refund_amount_band`, `refund_status`, `refund_reason_category` | 14% of orders have a refund: size_fit, quality, changed_mind, wrong_item, damaged |

### 3.4 `payments` (1,083 rows): one row per Razorpay attempt

**Why:** failed and retried payments signal friction and abandoned checkouts. **COD orders have no payment row** (59% of orders), so payments per customer look low.

| Column | Meaning |
|---|---|
| `payment_id`, `checkout_id` | Keys |
| `order_id` | Null when the checkout never became an order |
| `status` | captured 79%, refunded 13%, failed 8% |
| `method` | upi 63%, card 20%, wallet 11%, netbanking 7% |
| `amount_band`, `created_at`, `attempt_no` | |
| `error_code` | card_declined, insufficient_funds, bank_decline, technical, upi_timeout, otp_failed |

### 3.5 `tickets` (386 rows): one row per support ticket (Zendesk shape)

**Why:** an open ticket blocks marketing to that customer (a guardrail). It also tests the ticket lifecycle.

| Column | Meaning |
|---|---|
| `ticket_id`, `unit_id`, `created_at`, `updated_at`, `solved_at` | |
| `status` | Snapshot: closed 98%, solved, open. Lifecycle new → open → pending → solved → closed (auto-closed 4 days after solved) |
| `priority` | normal 78%, high 17%, urgent 3%, low 2% |
| `ticket_type` | incident 70%, question 30% |
| `channel` | email 48%, web 21%, whatsapp 21%, call 11% |
| `tags` | JSON topic: delivery 67%, product 17%, refund 12%, payment 4% |
| `reopens`, `csat` | CSAT 1 to 5 on about a third of solved tickets |

### 3.6 `actions` (19,916 rows): every decision and every send

**Why:** the record of what the system did and why. The logged `propensity` (probability of the chosen action) is what makes each action's effect measurable in the randomised period.

| Column | Meaning |
|---|---|
| `action_id`, `unit_id`, `person_key` | |
| `record_kind` | legacy_send (Period 1), decision (Period 2), transactional (order confirmations and shipping updates) |
| `regime` | legacy_targeting or randomised_holdout |
| `decided_at`, `state` | When; lifecycle state at that time (filled from `state_history`) |
| `trigger` | weekly, cart (abandoned cart), legacy_weekly, order_event |
| `chosen_action` | do_nothing, reminder, discount, free_shipping, bundle, agent_call, transactional |
| `channel`, `category`, `template` | whatsapp 32%, email 31%, sms 11%; templates such as cart_reminder, promo_discount, free_ship_nudge, bundle_offer |
| `message_id`, `campaign_id`, `sent_at` | `sent_at` is null when nothing was sent |
| `final_status` | delivered, opened, clicked, failed, bounced, unsubscribed (null when nothing was sent) |
| `options_considered`, `blocked_actions`, `reason_codes` | JSON. What was allowed, what was blocked, and why |
| `propensity` | Probability of the chosen action under the policy (Period 2 only) |
| `expected_value`, `uplift` inside options | **Always empty: no trained model exists yet** |
| `model_versions`, `rule_version` | exploration_policy_v0, ecom_rules_v0.1 |
| `needs_approval`, `in_holdout`, `holdout_group` | |
| `task_id`, `task_target`, `task_status`, `task_due_at`, `task_owner_id`, `task_capacity_bucket` | For agent calls and discounts above the approval limit. Status: done / ignored / overridden / open |

**Period 2 policy:** do_nothing 25% of the time, otherwise uniform among the allowed actions. Period 1 sends to people likely to buy and has **no propensity and no decision ID**: do not use it to estimate effects.

**Guardrail reason codes (counts in the sample):** discount_budget 3,018 · margin_floor 1,043 · in_holdout 952 · unknown_consent 767 · cod_limit 736 · frequency_cap 595 · out_of_stock 482 · approval_limit 135 · offer_abuse 65 · open_ticket 39 · no_consent 26. The discount budget is a simple stateless proxy, not a real running budget.

### 3.7 `state_history` (5,209 rows): lifecycle state stays

**Why:** output of the reference state engine run on the **visible, messy** events. Compare your own engine against it.

Columns: `unit_id`, `state`, `entered_at`, `exited_at` (null = current), `entered_by` (event or silence), `flags` (JSON: open_support_ticket, high_return_risk, no_consent, in_holdout), `rule_version`.

| State | Rule (starting thresholds, grade C) |
|---|---|
| New visitor | Browsing, no order, fewer than 3 sessions |
| Retarget | 3+ sessions or an abandoned checkout, no order |
| New customer | First order, within 45 days |
| Active | Repeat buyer within 1.5 times their usual gap |
| Re-engage | Past 1.5 times their usual gap (or 45 days after a first order) |
| Reactivate | 90 days with no order or visit after Re-engage |

Stays in the sample: New visitor 1,230 · Re-engage 1,032 · Retarget 1,017 · Active 898 · New customer 709 · Reactivate 323.

### 3.8 `campaigns` (6,584 rows): two kinds of row (`row_type`)

- `map` (14 rows): campaign_id, system, system campaign ID, hashed name, channel. Campaigns: meta_1 to 4, gads_1 to 4, aff_1, wa_optin, flow_cart_reminder, policy_weekly, legacy_flow_cart, legacy_weekly_blast.
- `ad_daily` (6,570 rows): `date`, `cost`, `clicks`, `impressions` per paid campaign per day, with festival peaks.

**Why:** links orders to marketing spend.

### 3.9 `category_value` (168 rows): category by month

Columns: `category`, `month`, `margin_band` (40%+, 30-40%, <20%), `return_cost_band` (low, medium), `stock_status` (in_stock 84%, low 12%, out_of_stock 4%).
**Why:** the margin-floor and out-of-stock guardrails need it. **These are placeholder values (grade D)**: the real client supplies them.

---

## 4. Built-in mess (on purpose)

| Defect | Rate | How to spot it |
|---|---|---|
| Duplicate events | about 2% | Repeated `source_event_id` |
| Missing channel | about 1% | Null `channel` |
| Wrong timestamp (timezone or day shift) | about 0.5% | `occurred_at` off by 5.5 hours or 1 day |
| Late arrivals | about 2% | `ingested_at` days after `occurred_at` |
| Out-of-order status changes | about 1.5% | A later status arrives first |
| GA4 daily export lag | all browsing | `ingested_at` is the next morning, median about 20 hours; webhooks arrive in seconds |
| Bots | about 3% of anonymous sessions | Many page views within seconds, never identified |
| Tracking gaps | 2 per year, 1.5 days each | Browsing events vanish |
| Shared phones | about 1.5% | Two customers with the same `person_key` |
| Split identities | only about 35% of identifies link | Anonymous browsing not tied to a customer |

---

## 5. Rules for using the data safely

1. **Features as of time t** use only events with `occurred_at <= t` **and** `ingested_at <= t`.
2. **Never use** `orders_count`, `spend_band` or the three consent columns in `customers`: they are extract-time snapshots.
3. **Labels:** "ordered within 7 or 30 days after the decision". A row is final only when decision time + horizon + **45 days** has passed. Train only on final rows.
4. **Effects of actions:** use Period 2 only, and compare customers where the action was allowed. Period 1 is biased targeting, so a naive comparison there is wrong.
5. **De-duplicate** on `source_event_id` before counting anything.
6. Rules 1 to 3 are our own (the answers file had no usable Q53 answer). Replace them when the client answers.

---

## 6. What this data can and cannot prove

**Can:** the pipeline runs end to end; the code copes with messy, late and duplicated data; labels are point-in-time safe; guardrails are enforced and logged; an uplift method can recover planted effects from Period 2 (at 10,000 customers the measured lifts were within about 1 point of the planted ones).

**Cannot:** that real customers behave this way; that any particular lift, margin, RTO or return rate is right; that a model that works here will work in production. Of 106 parameters only 3 are verified (grade A) and 14 researched (grade B); 83 are our assumptions (C) and 6 are placeholders (D).

**Known limits:** the 1,000-customer sample is too small to recover per-action uplift reliably (use the 10,000 preset); about 0.1% of promotional sends show no granted consent in visible events (believed to be timestamp noise, not verified); festival and sale dates and DPDP/TRAI timings are unverified config values; COD RTO base rates were scaled down by about 0.7 from vendor-blog ranges (our own calibration).

**Not included in this hand-over:** a separate hidden folder holds the answer key (true customer types, planted uplift per action, exact amounts, true states, an injected-defect log). It is for validation only and must never be used to build features or models.

---

## 7. Files delivered with the dataset

| File | Purpose |
|---|---|
| `visible/*.parquet` and `*.csv` | The 9 tables |
| `schemas/visible/*.json` | Column contracts: type, nullable, allowed values |
| `parameters_report.md` | Every assumption with grade A to D |
| `validation_report_10k.md` | Test results on 10,000 customers (88 of 88 pass) |
| `q53_leakage.md` | Leakage and point-in-time rules |
| `README.md` | How to regenerate: `python -m vynqe_synth generate --pack ecommerce --preset dev --seed 42 --out ./out` |
