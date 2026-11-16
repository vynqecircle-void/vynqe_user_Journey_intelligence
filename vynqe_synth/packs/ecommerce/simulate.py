"""E-commerce customer simulator. One customer at a time (independent, deterministic per (seed, index)),
so generation is chunkable. Output of simulate_customer() is a dict of row lists for the visible tables
and the hidden truth tables. SYNTHETIC DATA: every number comes from config/ecommerce.yaml with a grade."""
from __future__ import annotations
import json
import math
from types import SimpleNamespace
import numpy as np
import pandas as pd

from ...core.ids import keyed_hash, hash_u

DAY = 86400.0
TIERS = ["metro", "tier1", "tier2", "tier3", "rural"]
ACTS = ["reminder", "discount", "free_shipping", "bundle", "agent_call"]
TEMPLATE = {"reminder": "cart_reminder", "discount": "promo_discount", "free_shipping": "free_ship_nudge",
            "bundle": "bundle_offer", "agent_call": "agent_call_script"}
COURIERS = ["delhivery", "bluedart", "ecom_express", "xpressbees"]
ELIG = ("New customer", "Re-engage", "Reactivate", "Retarget")
SRC_FOR = {"email": "klaviyo", "sms": "klaviyo", "whatsapp": "whatsapp"}


def dumps(o):
    return json.dumps(o, separators=(",", ":"))


def sigmoid(x):
    return 1.0 / (1.0 + math.exp(-x))


def cum(weights):
    a = np.array(weights, float)
    return np.cumsum(a / a.sum())


def build_context(cfg, seed: int) -> SimpleNamespace:
    X = SimpleNamespace()
    X.cfg, X.seed = cfg, seed
    v = cfg.v
    start = pd.Timestamp(v("run.start_date"), tz="UTC")
    X.start = start
    X.E0 = start.timestamp()
    X.T = int(v("run.n_days"))
    X.reg2 = float(v("run.regime2_day"))
    X.END = X.E0 + X.T * DAY
    X.secret = v("run.hash_secret").encode()
    X.salt = v("run.holdout_salt")
    X.share = float(v("run.holdout_share"))
    days = pd.date_range(start, periods=X.T, freq="D")
    dom = days.day.to_numpy()
    X.month_idx = ((days.year - start.year) * 12 + days.month - start.month).to_numpy()
    X.dom = dom
    mult = np.ones(X.T)
    mult[dom <= 7] *= v("orders.salary_day_mult")
    sale = np.zeros(X.T, bool)
    X.seasons = []
    for s in v("calendar.seasons"):
        a = max(0, (pd.Timestamp(s["start"], tz="UTC") - start).days)
        b = min(X.T - 1, (pd.Timestamp(s["end"], tz="UTC") - start).days)
        if b < a:
            continue
        mult[a:b + 1] *= s["mult"]
        X.seasons.append((a, b))
        if "sale_start" in s:
            sa = max(0, (pd.Timestamp(s["sale_start"], tz="UTC") - start).days)
            sb = min(X.T - 1, (pd.Timestamp(s["sale_end"], tz="UTC") - start).days)
            mult[sa:sb + 1] = s["sale_mult"]
            sale[sa:sb + 1] = True
    X.mult, X.mmax, X.is_sale = mult, float(mult.max()), sale
    w = (1 + v("population.growth_per_year")) ** (np.arange(X.T) / 365.0) * mult ** 0.5
    X.created_cdf = np.cumsum(w / w.sum())
    hw = np.array(v("sessions.hour_weights_ist"), float)
    X.hour_cdf = np.cumsum(hw / hw.sum())
    mix = v("population.acquisition_mix")
    X.acq_names = list(mix)
    X.acq_cum = cum(list(mix.values()))
    X.types = v("population.types")
    X.type_names = list(X.types)
    X.type_share = np.array([X.types[k]["share"] for k in X.type_names], float)
    X.cf = v("population.channel_type_factor")
    X.tier_cum = cum(v("population.tier_mix"))
    dm = v("population.device_mix")
    X.dev_names, X.dev_cum = list(dm), cum(list(dm.values()))
    cats = v("population.categories")
    X.cat_names = list(cats)
    X.cats = cats
    X.cat_cum = cum([cats[k]["weight"] for k in X.cat_names])
    X.rng_stock = np.random.default_rng([seed, 99])
    X.stock = {}
    for c in X.cat_names:
        st = []
        for m in range(int(X.month_idx.max()) + 1):
            r = X.rng_stock.random()
            st.append("out_of_stock" if r < 0.04 else "low" if r < 0.14 else "in_stock")
        X.stock[c] = st
    pm = v("payments.method_mix")
    X.pm_names, X.pm_cum = list(pm), cum(list(pm.values()))
    X.p = {k: v(k) for k in [
        "orders.p_cod_base", "orders.cod_tier_shift", "orders.items_extra_mean", "orders.item_price_median",
        "orders.item_price_sigma", "orders.amount_edges", "orders.abandon_rate", "orders.nonbuyer_carts",
        "orders.first_order_lag_median_days", "orders.discount_sale_prob_factor", "orders.cancel_before_ship",
        "payments.success", "payments.evening_drop", "payments.retry_prob", "payments.error_codes",
        "delivery.transit_median_days", "delivery.first_attempt_success", "delivery.rto_cod_by_tier",
        "delivery.rto_prepaid", "delivery.serial_rto_factor", "delivery.rto_reason_mix", "delivery.cod_remit_days",
        "delivery.return_prepaid", "delivery.return_cod_factor", "delivery.serial_return_factor",
        "delivery.return_median_days", "delivery.partial_refund_share", "tickets.p_issue",
        "tickets.solve_median_days", "tickets.closed_after_solved_days", "tickets.reopen_prob",
        "tickets.csat_response", "messaging.window_hours_ist", "messaging.channel_pref",
        "messaging.channel_stats", "messaging.legacy_p", "messaging.legacy_action_mix",
        "messaging.policy_do_nothing", "messaging.action_cost", "messaging.discount_pct",
        "messaging.freq_cap_7d", "messaging.margin_floor", "messaging.offer_abuse_returns_180d",
        "messaging.cod_limit_rto_count", "messaging.approval_basket_band_edge",
        "messaging.discount_budget_floor", "messaging.task_status_mix", "messaging.fatigue_k",
        "messaging.unsub_fatigue", "messaging.unsub_reacts_badly", "messaging.response_mean_days",
        "messaging.pull_forward_days", "messaging.agent_call_min_spend", "consent.initial",
        "consent.optin_at_order_prob", "sessions.mean_pages", "sessions.max_events", "sessions.gap_median_sec",
        "sessions.login_prob", "population.type_change_share", "population.serial_returner_share",
        "population.reacts_badly_share", "population.anon_visitors_per_customer",
        "population.prior_sessions_mean", "population.identify_link_prob", "orders.p_cod_base"]}
    X.amount_labels = ["0-500", "500-1000", "1000-1500", "1500-2500", "2500-5000", "5000+"]
    X.cod_cum = None
    return X


def band_amount(X, x):
    k = int(np.searchsorted(X.p["orders.amount_edges"], x, side="right")) - 1
    return X.amount_labels[min(max(k, 0), len(X.amount_labels) - 1)]


def band_spend(x):
    return "0" if x <= 0 else "0-1000" if x < 1000 else "1000-2500" if x < 2500 else "2500-5000" if x < 5000 else \
        "5000-10000" if x < 10000 else "10000+"


def band_mid(label):
    return {"0-500": 300, "500-1000": 750, "1000-1500": 1250, "1500-2500": 2000, "2500-5000": 3500,
            "5000+": 7000}.get(label, 1000)


def pick(rng, cumarr, names):
    return names[min(int(np.searchsorted(cumarr, rng.random())), len(names) - 1)]


def simulate_customer(i: int, X) -> dict:
    p = X.p
    rng = np.random.default_rng([X.seed, 1, i])
    E0, T, END = X.E0, X.T, X.END
    ep = lambda d: E0 + d * DAY
    unit = f"C{i:07d}"

    def tod():  # fraction of a UTC day for an IST hour-of-day draw
        h = int(np.searchsorted(X.hour_cdf, rng.random()))
        sec = (min(h, 23) * 3600 + rng.uniform(0, 3600) - 19800) % DAY
        return sec / DAY

    # ---------------- static attributes
    created = float(np.searchsorted(X.created_cdf, rng.random())) + rng.random()
    created = min(created, T - 1.5)
    acq = pick(rng, X.acq_cum, X.acq_names)
    tw = X.type_share.copy()
    for k, f in X.cf.get(acq, {}).items():
        tw[X.type_names.index(k)] *= f
    ty = X.type_names[int(np.searchsorted(cum(tw), rng.random()))]
    tp = X.types[ty]
    tier = int(np.searchsorted(X.tier_cum, rng.random()))
    tier = min(tier, 4)
    dev = pick(rng, X.dev_cum, X.dev_names)
    ps = float(rng.beta(*tp["ps"]))
    cod_pref = float(np.clip(rng.beta(2, 2) + p["orders.cod_tier_shift"][tier] * 0.5, 0, 1))
    p_cod = float(np.clip(p["orders.p_cod_base"] + p["orders.cod_tier_shift"][tier] + 0.3 * (cod_pref - 0.5), 0.05, 0.95))
    ret_factor = float(rng.lognormal(0, 0.35))
    serial = rng.random() < p["population.serial_returner_share"]
    reacts_badly = rng.random() < p["population.reacts_badly_share"]
    gap_mu = tp["gap_mean"] * float(rng.lognormal(0, 0.35))
    gap_cv = tp["gap_cv"]
    sess_pm = tp["sessions_pm"] * float(rng.lognormal(0, 0.6))
    interest_cat = pick(rng, X.cat_cum, X.cat_names)
    p7 = min(0.9, 7.0 / gap_mu) if tp["p_buy"] > 0 else 0.0
    # true uplift per action (planted)
    u_true = {}
    for a in ACTS:
        base = tp["uplift"][a]
        u = base * float(rng.lognormal(0, 0.35)) + float(rng.normal(0, 0.008))
        if reacts_badly:
            u = -float(rng.uniform(0.01, 0.05))
        u_true[a] = float(np.clip(u, -0.08, 0.35))
    type_changes = []
    ty2, gap_mu2, t_change = None, None, None
    if rng.random() < p["population.type_change_share"]:
        ty2 = X.type_names[int(rng.integers(0, len(X.type_names)))]
        t_change = created + float(rng.uniform(30, 400))
        gap_mu2 = X.types[ty2]["gap_mean"] * float(rng.lognormal(0, 0.35))
        type_changes.append({"to": ty2, "day": round(t_change, 1)})

    # identity (raw values exist only in memory)
    def phone_of(j):
        return int(np.random.default_rng([X.seed, 7, j]).integers(6_000_000_000, 10_000_000_000))
    shared_with = None
    if rng.random() < X.cfg.v("noise.shared_phone") and i > 0:
        shared_with = f"C{i - 1:07d}"
        phone = phone_of(i - 1)
    else:
        phone = phone_of(i)
    pk = keyed_hash(X.secret, f"91{phone}")
    email_key = keyed_hash(X.secret, f"user{i}@example.test")
    anon_ids = [f"{int(rng.integers(10**8, 10**9))}.{int(ep(created) - 3 * DAY)}" for _ in range(1 + int(rng.random() < 0.3))]
    anon0 = anon_ids[0]
    camp_pool = {"paid_social": [f"meta_{k}" for k in range(1, 5)], "paid_search": [f"gads_{k}" for k in range(1, 5)],
                 "affiliate": ["aff_1"]}
    camp = camp_pool[acq][int(rng.integers(0, len(camp_pool[acq])))] if acq in camp_pool else (
        "wa_optin" if acq == "whatsapp" else None)
    u_hold = hash_u(X.salt, unit)
    control = u_hold < X.share
    hold_assigned = max(created, X.reg2)

    # ---------------- buffers
    EV = []                      # events
    orders, order_rows, pay_rows, tick_rows, act_rows, ot_rows, cart_list = [], [], [], [], [], [], []
    tickets_open = []            # (start_day, end_day)
    mkt_days = []                # marketing send days
    counters = {"o": 0, "k": 0, "p": 0, "t": 0, "m": 0, "a": 0}
    razorpay_ref = [None]
    zendesk_ref = [None]

    def add(t_ep, et, src, seid, props, ch=None, cmp_=None, cons=None, anon=None, known=True):
        if t_ep >= END or t_ep < E0 - 20 * DAY:
            return
        EV.append((t_ep, et, src, seid, pk if known else None, anon, unit if known else None, ch,
                   cmp_, cons, props, unit if (known or anon in anon_ids) else None))

    # ---------------- consent
    ci = p["consent.initial"]
    cons = {}
    for chn in ("email", "sms", "whatsapp"):
        r = rng.random()
        g, d_ = ci[chn]["granted"], ci[chn]["denied"]
        cons[chn] = "granted" if r < g else "denied" if r < g + d_ else "unknown"
        if cons[chn] != "unknown":
            src = "shopify" if chn in ("email", "sms") else "warehouse"
            add(ep(created) + 5, "consent_change", src, f"consent:{unit}:{chn}:{cons[chn]}:0",
                {"channel": chn, "purpose": "marketing", "status": cons[chn]},
                ch=chn, cons=cons[chn])
    cons_k = [0]

    def set_consent(chn, st, t_ep):
        cons[chn] = st
        cons_k[0] += 1
        src = SRC_FOR[chn] if chn != "whatsapp" else "warehouse"
        add(t_ep, "consent_change", src, f"consent:{unit}:{chn}:{st}:{cons_k[0]}",
            {"channel": chn, "purpose": "marketing", "status": st}, ch=chn, cons=st)

    # ---------------- natural order stubs
    stubs = []

    def snap(t):
        for _ in range(8):
            d = int(t)
            if d >= T:
                return t
            if rng.random() * X.mmax <= X.mult[d]:
                return t
            t += float(rng.exponential(2.0))
        return t

    def with_tod(t):
        return int(t) + tod()

    if rng.random() < tp["p_buy"]:
        if ty == "festival_only_buyer":
            for (a, b) in X.seasons:
                if b > created and rng.random() < 0.7:
                    lo = max(a, int(created) + 1)
                    if lo <= b:
                        stubs.append({"t": with_tod(float(rng.integers(lo, b + 1))), "kind": "natural"})
        else:
            t = created + min(90.0, float(rng.lognormal(math.log(p["orders.first_order_lag_median_days"]), 1.0)))
            t = snap(t)
            n_o = 0
            while t < T - 0.2 and n_o < 60:
                stubs.append({"t": with_tod(t), "kind": "natural"})
                n_o += 1
                mu = gap_mu2 if (t_change is not None and t > t_change) else gap_mu
                if rng.random() < tp["lapse_q"]:
                    if rng.random() < 0.5:           # fade: gaps lengthen 1.3-1.6x then stop
                        for _k in range(int(rng.integers(1, 3))):
                            mu *= float(rng.uniform(1.3, 1.6))
                            t = snap(t + float(rng.gamma(1 / gap_cv ** 2, mu * gap_cv ** 2)))
                            if t < T - 0.2:
                                stubs.append({"t": with_tod(t), "kind": "natural"})
                    break
                t = snap(t + float(rng.gamma(1 / gap_cv ** 2, mu * gap_cv ** 2)))
    stubs.sort(key=lambda s: s["t"])

    # ---------------- abandoned carts (pre-generated)
    n_nat = len(stubs)
    lam = (1.0 / max(1e-6, 1 - p["orders.abandon_rate"]) - 1.0) * n_nat + (p["orders.nonbuyer_carts"] if n_nat == 0 else 0)
    n_carts = int(rng.poisson(lam))
    last_nat = stubs[-1]["t"] if stubs else created + 20
    for _ in range(n_carts):
        if stubs and rng.random() < 0.4:
            base = stubs[int(rng.integers(0, len(stubs)))]["t"] - float(rng.uniform(0.02, 3))
        else:
            base = float(rng.uniform(created, min(T - 0.3, last_nat + 30)))
        base = max(created + 0.01, base)
        if base >= T - 0.2:
            continue
        cat = interest_cat if rng.random() < 0.5 else pick(rng, X.cat_cum, X.cat_names)
        items = 1 + int(rng.poisson(p["orders.items_extra_mean"]))
        gross = float(sum(rng.lognormal(math.log(p["orders.item_price_median"] * X.cats[cat]["price"]),
                                         p["orders.item_price_sigma"], items)))
        counters["k"] += 1
        cart_list.append({"t": with_tod(base), "cat": cat, "items": items, "gross": gross,
                          "id": f"K{i:07d}-{counters['k']:02d}", "converted": False, "emitted": False})
    cart_list.sort(key=lambda c: c["t"])

    # ---------------- helpers: channels, sessions
    def traffic_channel():
        r = rng.random()
        if r < 0.45:
            return "organic", None
        if r < 0.70:
            return acq if acq in ("paid_social", "paid_search", "affiliate", "referral", "organic", "whatsapp") else "organic", camp
        if r < 0.80 and cons["email"] == "granted":
            return "email", None
        if r < 0.90 and cons["whatsapp"] == "granted":
            return "whatsapp", None
        return "organic", None

    def session_events(start_ep, n_ev, known, anon, chn, cmp_, extra=None, login=False):
        gm = math.log(p["sessions.gap_median_sec"])
        t = start_ep
        sid = int(start_ep)
        for j in range(n_ev):
            if extra and j >= n_ev - len(extra):
                ga = extra[j - (n_ev - len(extra))]
            elif login and j == 0:
                ga = "login"
            else:
                ga = ("view_item" if rng.random() < 0.7 else "search" if rng.random() < 0.5 else
                      "add_to_wishlist" if rng.random() < 0.3 else "home")
            pr = {"ga4_event": ga, "session_id": sid, "platform": "app" if dev in ("android", "ios") and rng.random() < 0.55 else "web",
                  "device": dev}
            add(t, "page_view", "ga4", f"pv:{anon}:{sid}:{j}", pr, ch=chn, cmp_=cmp_, anon=anon, known=known)
            t += min(600.0, float(rng.lognormal(gm, 1.0)))
        return t

    def n_pages():
        return int(min(p["sessions.max_events"], rng.geometric(1.0 / p["sessions.mean_pages"])))

    # ---------------- checkout/order/lifecycle
    ticket_ev = []

    def make_ticket(topic, t0_ep):
        """Create a Zendesk-shaped ticket and its events. Returns nothing; guardrails read tickets_open."""
        counters["t"] += 1
        tid = f"T{i:07d}-{counters['t']:02d}"
        t_c = t0_ep + float(rng.uniform(0.02, 1.5)) * DAY
        t_open = t_c + float(rng.lognormal(math.log(3 * 3600), 0.8))
        t_sol = t_c + float(rng.lognormal(math.log(p["tickets.solve_median_days"]), 0.9)) * DAY
        t_sol = max(t_sol, t_open + 600)
        pend = rng.random() < 0.35
        tl = [(t_c, "new"), (t_open, "open")]
        if pend:
            tl.append((t_open + (t_sol - t_open) * 0.4, "pending"))
        tl.append((t_sol, "solved"))
        reopens = 0
        if rng.random() < p["tickets.reopen_prob"]:
            reopens = 1
            tr = t_sol + float(rng.uniform(0.2, 3)) * DAY
            tl += [(tr, "open"), (tr + float(rng.uniform(0.5, 3)) * DAY, "solved")]
            t_sol2 = tl[-1][0]
        else:
            t_sol2 = t_sol
        tl.append((t_sol2 + p["tickets.closed_after_solved_days"] * DAY, "closed"))
        tickets_open.append(((t_c - E0) / DAY, (t_sol2 - E0) / DAY))
        pri = pick(rng, cum([0.02, 0.75, 0.2, 0.03]), ["low", "normal", "high", "urgent"])
        ttype = {"delivery": "incident", "payment": "incident", "refund": "question", "product": "problem",
                 "general": "question"}[topic]
        tag_topic = "product" if topic == "general" else topic
        chn = pick(rng, cum([0.5, 0.2, 0.2, 0.1]), ["email", "web", "whatsapp", "call"])
        csat = None
        if rng.random() < p["tickets.csat_response"]:
            csat = int(rng.choice([1, 2, 3, 4, 5], p=[0.1, 0.1, 0.15, 0.3, 0.35] if topic != "delivery" else [0.2, 0.15, 0.2, 0.25, 0.2]))
        prev = None
        final_status, upd, solved_at = None, t_c, None
        for (tt, st) in tl:
            if tt >= END:
                break
            props = {"object": "ticket", "ticket_id": tid, "ticket_type": ttype, "priority": pri, "tags": [tag_topic]}
            if prev is None:
                props["status"] = st
                add(tt, "record_created", "zendesk", f"ticket:{tid}:{st}", props, ch=chn)
            else:
                props["from"], props["to"] = prev, st
                if st == "solved" and csat is not None:
                    props["csat"] = csat
                add(tt, "record_status_changed", "zendesk", f"ticket:{tid}:{st}:{int(tt)}", props, ch=chn)
            prev = st
            final_status, upd = st, tt
            if st == "solved":
                solved_at = tt
        if final_status is None:
            return
        zendesk_ref[0] = zendesk_ref[0] or f"zd_{i:07d}"
        tick_rows.append({"ticket_id": tid, "unit_id": unit, "created_at": t_c, "updated_at": upd,
                          "status": final_status, "priority": pri, "ticket_type": ttype, "channel": chn,
                          "tags": dumps([tag_topic]), "solved_at": solved_at, "reopens": reopens,
                          "csat": csat if final_status in ("solved", "closed") else None})

    def run_payments(t_ep, chk):
        att, prev = [], None
        while len(att) < 3:
            method = prev if (prev and rng.random() < 0.5) else pick(rng, X.pm_cum, X.pm_names)
            hr = int(((t_ep + 19800) % DAY) // 3600)
            ps_ = p["payments.success"][method] - (p["payments.evening_drop"] if 19 <= hr <= 22 else 0.0)
            ok = rng.random() < ps_
            att.append({"method": method, "ok": ok, "err": None if ok else p["payments.error_codes"][int(rng.integers(0, len(p["payments.error_codes"])))]})
            prev = method
            if ok or rng.random() > p["payments.retry_prob"]:
                break
        n = len(att)
        for k, a in enumerate(att):
            a["t"] = t_ep - 8 - (n - 1 - k) * float(rng.uniform(60, 300))
        return att[-1]["ok"], att

    def record_payments(att, chk, oid, band):
        razorpay_ref[0] = razorpay_ref[0] or f"cust_{i:07d}"
        for k, a in enumerate(att):
            counters["p"] += 1
            pid = f"pay_{i:07d}{counters['p']:02d}"
            a["pid"] = pid
            ta = a["t"]
            add(ta, "record_created", "razorpay", f"payment:{pid}:created",
                {"object": "payment", "payment_id": pid, "status": "created", "method": a["method"], "checkout_id": chk,
                 "order_id": oid, "amount_band": band, "attempt_no": k + 1}, ch="web")
            if a["ok"]:
                if a["method"] in ("card", "netbanking"):
                    add(ta + 3, "record_status_changed", "razorpay", f"payment:{pid}:authorised",
                        {"object": "payment", "payment_id": pid, "from": "created", "to": "authorised"}, ch="web")
                add(ta + 6, "record_status_changed", "razorpay", f"payment:{pid}:captured",
                    {"object": "payment", "payment_id": pid, "from": "created", "to": "captured", "order_id": oid}, ch="web")
                add(ta + 6, "outcome_confirmed", "outcome_checker", f"outcome:payment:{pid}:captured",
                    {"object": "payment", "system": "razorpay", "status": "captured", "order_id": oid,
                     "amount_band": band}, ch="web")
                a["final"], a["t_final"] = "captured", ta + 6
            else:
                add(ta + 20, "record_status_changed", "razorpay", f"payment:{pid}:failed",
                    {"object": "payment", "payment_id": pid, "from": "created", "to": "failed", "error_code": a["err"]}, ch="web")
                a["final"], a["t_final"] = "failed", ta + 20
            pay_rows.append({"payment_id": pid, "checkout_id": chk, "order_id": oid, "unit_id": unit, "status": a["final"],
                             "method": a["method"], "amount_band": band, "created_at": ta, "error_code": a["err"],
                             "attempt_no": k + 1})

    def emit_checkout(chk, t_c, cat, items, band, status, t_end, oid=None, reason=None):
        pr = {"object": "checkout", "checkout_id": chk, "status": "open", "item_count": items, "amount_band": band, "category": cat}
        add(t_c, "record_created", "shopify", f"checkout:{chk}:open", pr, ch="web")
        pr2 = {"object": "checkout", "checkout_id": chk, "from": "open", "to": status}
        if reason:
            pr2["exit_reason"] = reason
        add(t_end, "record_status_changed", "shopify", f"checkout:{chk}:{status}", pr2, ch="web")

    def try_order(stub):
        t = stub["t"]
        cart = stub.get("cart")
        if cart:
            cat, items, gross, chk = cart["cat"], cart["items"], cart["gross"], cart["id"]
        else:
            cat = pick(rng, X.cat_cum, X.cat_names)
            items = 1 + int(rng.poisson(p["orders.items_extra_mean"]))
            gross = float(sum(rng.lognormal(math.log(p["orders.item_price_median"] * X.cats[cat]["price"]),
                                             p["orders.item_price_sigma"], items)))
            counters["k"] += 1
            chk = f"K{i:07d}-{counters['k']:02d}"
        disc = stub.get("disc", 0)
        d_i = min(int(t), T - 1)
        if disc == 0:
            if X.is_sale[d_i] and rng.random() < ps * p["orders.discount_sale_prob_factor"]:
                disc = int(rng.choice([10, 15, 20]))
            elif rng.random() < ps * 0.12:
                disc = 10
        net = gross * (1 - disc / 100.0)
        band = band_amount(X, net)
        cod = rng.random() < p_cod
        t_ep = ep(t)
        chn, cmp_ = traffic_channel()
        if not cod:
            ok, att = run_payments(t_ep, chk)
            if not ok:
                record_payments(att, chk, None, band)
                emit_checkout(chk, att[0]["t"] - 120, cat, items, band, "abandoned", att[-1]["t_final"] + 600, reason="payment_failed")
                if rng.random() < p["tickets.p_issue"]["payment"]:
                    make_ticket("payment", att[-1]["t_final"])
                if cart:
                    cart["emitted"] = True
                return None
            t_ep = att[-1]["t"] + 9
        counters["o"] += 1
        oid = f"O{i:06d}-{counters['o']:02d}"
        o = {"id": oid, "t_ep": t_ep, "cat": cat, "items": items, "gross": gross, "net": net, "disc": disc, "band": band,
             "cod": cod, "chk": chk, "chn": chn, "camp": cmp_, "kind": stub["kind"], "tl": [], "cart": cart}
        if not cod:
            record_payments(att, chk, oid, band)
            o["pay_id"] = att[-1]["pid"]
            o["paid_t"] = att[-1]["t_final"]
            n_failed_pay = len(att) - 1
        else:
            n_failed_pay = 0
        # decision attribution: observable only if the customer clicked the message
        dec = None
        if stub["kind"] == "incremental" and stub.get("clicked"):
            dec = stub.get("dec")
        elif stub.get("exposed_dec") and stub.get("exposed_clicked"):
            dec = stub["exposed_dec"]
        o["dec"] = dec
        o["cause_dec"] = stub.get("dec") if stub["kind"] == "incremental" else None
        # ---- lifecycle timeline (epoch seconds)
        tl = o["tl"]
        fulfil = t_ep + float(rng.lognormal(math.log(0.8), 0.6)) * DAY
        o["processed"] = t_ep + (6.0 if not cod else float(rng.uniform(0.5, 12)) * 3600)
        courier = COURIERS[int(rng.integers(0, 4))]
        o["courier"] = courier
        has_issue = None
        if rng.random() < p["orders.cancel_before_ship"]:
            ct = t_ep + float(rng.uniform(0.05, max(0.1, (fulfil - t_ep) / DAY))) * DAY
            o["cancel_t"] = ct
            tl.append((ct, "fin", "cancelled" if cod else "refunded"))
            if not cod:
                tl.append((ct + float(rng.uniform(1, 3)) * DAY, "pay_refund", None))
        else:
            tl.append((fulfil, "ful", "fulfilled"))
            tr = float(rng.lognormal(math.log(p["delivery.transit_median_days"][tier]), 0.35))
            catf = X.cats[cat]
            if cod:
                prto = p["delivery.rto_cod_by_tier"][tier] * catf["rto"]
            else:
                prto = p["delivery.rto_prepaid"] * (1 + 0.15 * tier)
            if serial:
                prto *= p["delivery.serial_rto_factor"]
            rto = rng.random() < min(0.9, prto)
            t_first = fulfil + tr * DAY
            if rto:
                k_f = int(rng.choice([1, 2, 3], p=[0.5, 0.3, 0.2]))
                for k in range(k_f):
                    tl.append((t_first + k * DAY, "del", ("failed_delivery", k + 1)))
                t_rto = t_first + (k_f - 1) * DAY + float(rng.uniform(2, 6)) * DAY
                reason = pick(rng, cum(list(p["delivery.rto_reason_mix"].values())), list(p["delivery.rto_reason_mix"]))
                tl.append((t_rto, "del", ("rto", k_f, reason)))
                tl.append((t_rto + DAY, "ful", "returned_to_stock"))
                if cod:
                    tl.append((t_rto, "fin", "cancelled"))
                else:
                    tl.append((t_rto + float(rng.uniform(1, 5)) * DAY, "fin", "refunded"))
                    tl.append((t_rto + float(rng.uniform(1, 5)) * DAY, "pay_refund", None))
                has_issue = "rto"
                o["rto_t"] = t_rto
            else:
                pa = p["delivery.first_attempt_success"][tier]
                fails = 0 if rng.random() < pa else (1 if rng.random() < 0.7 else 2)
                for k in range(fails):
                    tl.append((t_first + k * DAY, "del", ("failed_delivery", k + 1)))
                t_del = t_first + fails * DAY
                tl.append((t_del, "del", ("delivered", fails + 1)))
                o["delivered_t"] = t_del
                if fails:
                    has_issue = "failed_delivery"
                if cod:
                    t_paid = t_del + float(rng.uniform(*p["delivery.cod_remit_days"])) * DAY
                    tl.append((t_paid, "fin", "paid"))
                    o["paid_t"] = t_paid
                # returns
                pr_ = p["delivery.return_prepaid"] * (p["delivery.return_cod_factor"] if cod else 1.0) * catf["ret"] * ret_factor
                if serial:
                    pr_ *= p["delivery.serial_return_factor"]
                if rng.random() < min(0.85, pr_):
                    t_ref = t_del + float(rng.lognormal(math.log(p["delivery.return_median_days"]), 0.5)) * DAY
                    part = rng.random() < p["delivery.partial_refund_share"]
                    frac = float(rng.uniform(0.3, 0.7)) if part else 1.0
                    cats_sf = ["size_fit", "quality", "changed_mind", "damaged", "wrong_item"]
                    wts = [0.45, 0.2, 0.2, 0.05, 0.1] if cat.startswith(("apparel", "footwear")) else [0.05, 0.3, 0.2, 0.3, 0.15]
                    reason = pick(rng, cum(wts), cats_sf)
                    tl.append((t_ref, "refund", (frac, reason)))
                    tl.append((t_ref, "fin", "partially_refunded" if part else "refunded"))
                    if not cod and not part:
                        tl.append((t_ref + float(rng.uniform(0.5, 2)) * DAY, "pay_refund", None))
                    o["refund_t"] = t_ref
                    has_issue = has_issue or "refund"
        # tickets
        pi = p["tickets.p_issue"]
        topic = None
        if has_issue and rng.random() < pi.get(has_issue, 0.1):
            topic = "delivery" if has_issue in ("failed_delivery", "rto") else "refund"
        elif n_failed_pay and rng.random() < pi["payment"]:
            topic = "payment"
        elif rng.random() < pi["general"]:
            topic = "general"
        if topic:
            ref_t = next((x[0] for x in sorted(tl) if x[1] in ("refund", "del")), t_ep + DAY)
            make_ticket(topic, ref_t if topic in ("delivery", "refund") else t_ep)
        # first-order consent opt-in
        if len([x for x in orders]) == 0:
            for chn_ in ("email", "sms", "whatsapp"):
                if cons[chn_] == "unknown" and rng.random() < p["consent.optin_at_order_prob"]:
                    set_consent(chn_, "granted", t_ep + 20)
        # checkout events
        if cart:
            cart["converted"], cart["emitted"] = True, True
        emit_checkout(chk, min(t_ep - 120, (cart["t"] * DAY + E0) if cart else t_ep - 120), cat, items, band, "completed", t_ep - 2, oid)
        # purchase-linked session
        s_end = t_ep - 30
        dur = float(np.clip(rng.lognormal(math.log(420), 0.6), 90, 1700))
        n_ev = int(max(4, items + 3))
        extra = ["add_to_cart"] * min(items, 2) + ["begin_checkout"]
        session_events(s_end - dur, n_ev, True, anon_ids[0], chn, cmp_, extra=extra)
        # order record + transactional messages
        pr = {"object": "order", "order_id": oid, "status": "placed", "amount_band": band, "payment_mode": "cod" if cod else "prepaid",
              "checkout_id": chk, "category": cat, "item_count": items}
        if disc:
            pr["discount_code"] = f"DISC{disc}"
        if dec:
            pr["decision_id"] = dec
        add(t_ep, "record_created", "shopify", f"order:{oid}:placed", pr, ch=chn, cmp_=cmp_)
        for tpl, dt in (("order_confirmation", 10.0), ("shipped_update", None)):
            if dt is None:
                if "cancel_t" in o:
                    continue
                dt = fulfil + 600 - t_ep
            tch = pick(rng, cum([0.4, 0.4, 0.2]), ["whatsapp", "email", "sms"])
            send_transactional(t_ep + dt, tch, tpl)
        orders.append(o)
        return o

    # ---------------- messaging
    def send_transactional(t_ep, chn, tpl):
        if t_ep >= END:
            return
        counters["m"] += 1
        mid = f"M{i:07d}-{counters['m']:03d}"
        counters["a"] += 1
        st = p["messaging.channel_stats"][chn]
        events = [(t_ep, "sent")]
        final = "sent"
        if rng.random() < st["deliver"]:
            events.append((t_ep + float(rng.uniform(2, 120)), "delivered"))
            final = "delivered"
        else:
            final = "bounced" if chn == "email" else "failed"
            events.append((t_ep + float(rng.uniform(1, 60)), final))
        for (tt, s_) in events:
            add(tt, "message_status", SRC_FOR[chn], f"msg:{mid}:{s_}", {"message_id": mid, "status": s_, "channel": chn, "template": tpl}, ch=chn)
        reg = "legacy_targeting" if t_ep < ep(X.reg2) else "randomised_holdout"
        act_rows.append(dict(action_id=f"A{i:07d}-{counters['a']:03d}", unit_id=unit, person_key=pk, record_kind="transactional",
                             regime=reg, decided_at=t_ep, trigger="order_event", chosen_action="transactional", channel=chn,
                             category="transactional", template=tpl, message_id=mid, campaign_id=None, sent_at=t_ep,
                             final_status=final, options_considered=None, blocked_actions=None, reason_codes=None,
                             propensity=None, expected_value=None, model_versions=None, rule_version=None,
                             needs_approval=False, in_holdout=False, holdout_group=None, task_id=None, task_target=None,
                             task_status=None, task_due_at=None, task_owner_id=None, task_capacity_bucket=None))

    def pick_channel():
        granted = [c for c in ("whatsapp", "email", "sms") if cons[c] == "granted"]
        if not granted:
            return None
        w = [p["messaging.channel_pref"][c] for c in granted]
        return granted[int(np.searchsorted(cum(w), rng.random()))] if len(granted) > 1 else granted[0]

    def mk_msg_times(chn, t_ep, force_click):
        st = p["messaging.channel_stats"][chn]
        ev = [(t_ep, "sent")]
        if rng.random() >= st["deliver"]:
            f = "bounced" if chn == "email" else "failed"
            ev.append((t_ep + float(rng.uniform(1, 60)), f))
            return ev, f, False
        td = t_ep + float(rng.uniform(2, 120))
        final, clicked = "delivered", False
        opened = rng.random() < st["open"] or force_click
        if chn == "sms":
            if rng.random() < 0.03 or force_click:
                ev.append((td, "delivered"))
                ev.append((td + float(rng.uniform(30, 3000)), "clicked"))
                return ev, "clicked", True
            ev.append((td, "delivered"))
            return ev, "delivered", False
        skip = chn == "whatsapp" and opened and rng.random() < st.get("skip_delivered_when_read", 0)
        if not skip:
            ev.append((td, "delivered"))
        if opened:
            med = 600 if chn == "whatsapp" else 2400
            to = td + float(rng.lognormal(math.log(med), 1.2))
            ev.append((to, "opened"))
            final = "opened"
            if force_click or rng.random() < st["click_given_open"]:
                ev.append((to + float(rng.uniform(5, 600)), "clicked"))
                final, clicked = "clicked", True
        return ev, final, clicked

    def send_marketing(t, action, chn, trig, regime, dec_id, cart, task=None, trig_mult=1.0):
        """Create a promotional message at day t and apply the planted true effect. Returns (message_id, final_status)."""
        t_ep = ep(t)
        hmin, hmax = p["messaging.window_hours_ist"]
        sec = ((t_ep + 19800) % DAY)
        if not (hmin * 3600 <= sec <= hmax * 3600):
            t_ep = (t_ep - sec) + hmin * 3600 + float(rng.uniform(0, (hmax - hmin) * 3600 * 0.9)) - 19800 + 19800
            t_ep = (math.floor((t_ep + 19800) / DAY)) * DAY + float(rng.uniform(hmin * 3600, hmax * 3600)) - 19800
        t = (t_ep - E0) / DAY
        if t_ep >= END:
            return None, None
        # --- effect (planted truth): extra 7-day conversion probability among those who would not order anyway
        n14 = sum(1 for d in mkt_days if t - 14 <= d < t)
        fat = 1.0 / (1.0 + p["messaging.fatigue_k"] * max(0, n14 - 1))
        u = u_true[action] * fat * trig_mult
        nat = [s for s in stubs if t < s["t"] <= t + 7 and s["kind"] == "natural"]
        converts = False
        if u > 0 and not nat and rng.random() < min(0.6, u):
            converts = True
        force_click = converts and rng.random() < 0.75
        mev, final, clicked = mk_msg_times(chn, t_ep, force_click)
        counters["m"] += 1
        mid = f"M{i:07d}-{counters['m']:03d}"
        # unsubscribe
        st = p["messaging.channel_stats"][chn]
        pun = st["unsub"] + p["messaging.unsub_fatigue"] * max(0, n14 - 2) + (p["messaging.unsub_reacts_badly"] if reacts_badly else 0)
        if final not in ("bounced", "failed") and rng.random() < pun:
            tu = max(tt for tt, _ in mev) + float(rng.uniform(5, 600))
            mev.append((tu, "unsubscribed"))
            final = "unsubscribed"
            set_consent(chn, "withdrawn", tu + 1)
        for (tt, s_) in mev:
            add(tt, "message_status", SRC_FOR[chn], f"msg:{mid}:{s_}",
                {"message_id": mid, "status": s_, "channel": chn, "template": TEMPLATE[action], "decision_id": dec_id}, ch=chn)
            if s_ == "clicked":
                add(tt + 1, "link_click", SRC_FOR[chn], f"click:{mid}",
                    {"message_id": mid, "target": "resume_link" if cart else "offer", "channel": chn, "decision_id": dec_id}, ch=chn)
        mkt_days.append(t)
        if converts:
            delay = min(6.9, float(rng.exponential(p["messaging.response_mean_days"]))) + 0.02
            stubs.append({"t": t + delay, "kind": "incremental", "cart": cart, "dec": dec_id, "clicked": force_click,
                          "disc": p["messaging.discount_pct"] if action == "discount" else 0})
            if cart:
                cart["converted"] = True
            if action == "discount":
                lo, hi = p["messaging.pull_forward_days"]
                for s in stubs:
                    if s["kind"] == "natural" and t + delay < s["t"] <= t + delay + 30:
                        s["t"] += float(rng.uniform(lo, hi))
                        break
        elif u > 0 and nat:
            nat[0].setdefault("exposed_dec", dec_id)
            nat[0].setdefault("exposed_clicked", clicked)
        elif u < 0 and nat and rng.random() < min(0.8, -u * 10):
            nat[0]["t"] += float(rng.uniform(14, 60))
        stubs.sort(key=lambda s: s["t"])
        return mid, final, t_ep

    # ---------------- decision loop
    def materialize_until(t):
        while stubs and stubs[0]["t"] <= t:
            s = stubs.pop(0)
            if s["t"] >= T:
                continue
            try_order(s)

    def est_state(t):
        ots = sorted(o["t_ep"] for o in orders if o["t_ep"] <= ep(t))
        if not ots:
            pend = [c for c in cart_list if not c["converted"] and t - 14 <= c["t"] <= t]
            return "Retarget" if pend else "New visitor"
        gap = (ep(t) - ots[-1]) / DAY
        if len(ots) == 1:
            return "New customer" if gap <= 45 else "Re-engage" if gap < 90 else "Reactivate"
        u = float(np.clip(np.median(np.diff(ots)) / DAY, 7, 120))
        return "Active" if gap <= 1.5 * u else "Re-engage" if gap < 90 else "Reactivate"

    def new_act_id():
        counters["a"] += 1
        return f"A{i:07d}-{counters['a']:03d}"

    def log_action(**kw):
        base = dict(action_id=None, unit_id=unit, person_key=pk, record_kind="decision", regime="randomised_holdout",
                    decided_at=None, trigger="weekly", chosen_action="do_nothing", channel=None, category=None,
                    template=None, message_id=None, campaign_id=None, sent_at=None, final_status=None,
                    options_considered=None, blocked_actions=None, reason_codes=None, propensity=None,
                    expected_value=None, model_versions=None, rule_version=None, needs_approval=False,
                    in_holdout=False, holdout_group=None, task_id=None, task_target=None, task_status=None,
                    task_due_at=None, task_owner_id=None, task_capacity_bucket=None)
        base.update(kw)
        base["action_id"] = base["action_id"] or new_act_id()
        act_rows.append(base)

    def refund_count(t):
        return sum(1 for o in orders if o.get("refund_t") and t - 180 <= (o["refund_t"] - E0) / DAY <= t)

    def rto_count(t):
        return sum(1 for o in orders if o.get("rto_t") and (o["rto_t"] - E0) / DAY <= t)

    def tickets_open_at(t):
        return any(a <= t < b for a, b in tickets_open)

    def decide_v2(t, trig, cart, state):
        t_ep = ep(t)
        counters["a"] += 1
        dec_id = f"D{i:07d}-{counters['a']:03d}"
        cat = cart["cat"] if cart else (orders[-1]["cat"] if orders else interest_cat)
        basket = cart["gross"] if cart else (orders[-1]["net"] if orders else 1000.0)
        m = X.cats[cat]["margin"]
        spend = sum(o["gross"] for o in orders)
        cands = ["reminder", "discount", "free_shipping", "bundle"]
        if spend >= p["messaging.agent_call_min_spend"] and state in ("Re-engage", "Reactivate"):
            cands.append("agent_call")
        blocked = []
        chn = pick_channel()
        granted_any = chn is not None
        if not granted_any:
            reason = "unknown_consent" if any(v == "unknown" for v in cons.values()) else "no_consent"
            blocked = [{"action": a, "reason_code": reason} for a in cands]
        elif tickets_open_at(t):
            blocked = [{"action": a, "reason_code": "open_ticket"} for a in cands]
        elif sum(1 for d in mkt_days if t - 7 <= d <= t) >= p["messaging.freq_cap_7d"]:
            blocked = [{"action": a, "reason_code": "frequency_cap"} for a in cands]
        else:
            fl = p["messaging.margin_floor"]
            for a in cands:
                if a == "discount":
                    if m - p["messaging.discount_pct"] / 100.0 < fl:
                        blocked.append({"action": a, "reason_code": "margin_floor"})
                    elif refund_count(t) >= p["messaging.offer_abuse_returns_180d"] and serial:
                        blocked.append({"action": a, "reason_code": "offer_abuse"})
                    else:
                        wk = min(3, (int(X.dom[min(int(t), T - 1)]) - 1) // 7)
                        avail = 1 - (1 - p["messaging.discount_budget_floor"]) * (wk / 3.0) ** 2
                        if hash_u(f"budget{int(t // 7)}", unit) > avail:
                            blocked.append({"action": a, "reason_code": "discount_budget"})
                elif a == "free_shipping":
                    if basket * m - 60 < basket * fl:
                        blocked.append({"action": a, "reason_code": "margin_floor"})
                    elif rto_count(t) >= p["messaging.cod_limit_rto_count"]:
                        blocked.append({"action": a, "reason_code": "cod_limit"})
                    elif refund_count(t) >= p["messaging.offer_abuse_returns_180d"] and serial:
                        blocked.append({"action": a, "reason_code": "offer_abuse"})
                elif a in ("bundle", "reminder"):
                    if X.stock[cat][int(X.month_idx[min(int(t), T - 1)])] == "out_of_stock":
                        blocked.append({"action": a, "reason_code": "out_of_stock"})
        allowed = [a for a in cands if a not in [b["action"] for b in blocked]]
        hold_g = "control" if control else "treated"
        kw = dict(decided_at=t_ep, trigger=trig, regime="randomised_holdout", holdout_group=hold_g,
                  model_versions="exploration_policy_v0", rule_version="ecom_rules_v0.1", in_holdout=False)
        if allowed and control:
            blocked += [{"action": a, "reason_code": "in_holdout"} for a in allowed]
            kw["in_holdout"] = True
            allowed = []
        reasons = sorted({b["reason_code"] for b in blocked})
        opts = [{"action": a, "action_cost": p["messaging.action_cost"][a], "uplift": None, "expected_value": None} for a in allowed]
        pdn = p["messaging.policy_do_nothing"]
        if not allowed:
            log_action(action_id=dec_id.replace("D", "A", 1), chosen_action="do_nothing", options_considered=dumps(opts),
                       blocked_actions=dumps(blocked), reason_codes=dumps(reasons), propensity=1.0, **kw)
            add(t_ep, "decision_made", "decision_service", f"decision:{dec_id}",
                {"decision_id": dec_id, "action": "do_nothing", "reason_code": reasons[0] if reasons else None}, ch=None)
            return
        choice = "do_nothing" if rng.random() < pdn else allowed[int(rng.integers(0, len(allowed)))]
        prop = pdn if choice == "do_nothing" else (1 - pdn) / len(allowed)
        need_appr = choice == "discount" and basket >= p["messaging.approval_basket_band_edge"]
        task = {}
        executes = choice != "do_nothing"
        if need_appr or choice == "agent_call":
            blocked.append({"action": choice, "reason_code": "approval_limit"}) if need_appr else None
            reasons = sorted({b["reason_code"] for b in blocked})
            sm = p["messaging.task_status_mix"]
            tst = pick(rng, cum(list(sm.values())), list(sm))
            executes = tst == "done"
            task = dict(task_id=f"TK{i:07d}-{counters['a']:03d}", task_target="crm_task" if need_appr else "agent_call_list",
                        task_status=tst, task_due_at=t_ep + float(rng.uniform(0.2, 2)) * DAY,
                        task_owner_id=f"owner_{int(rng.integers(1, 9))}", task_capacity_bucket=pick(rng, cum([0.5, 0.35, 0.15]), ["low", "medium", "high"]))
        mid = final = sent_at = None
        t_send = t + (float(rng.uniform(0.01, 0.15)) if trig == "cart" else float(rng.uniform(0, 0.9)))
        if choice == "agent_call" and executes:
            if rng.random() < 0.8:
                t_task = (task["task_due_at"] - E0) / DAY
                if rng.random() < max(0.0, u_true["agent_call"]):
                    stubs.append({"t": t_task + min(6.0, float(rng.exponential(1.5))), "kind": "incremental", "cart": None,
                                  "dec": dec_id, "clicked": False, "disc": 0})
                    stubs.sort(key=lambda s: s["t"])
        elif choice != "do_nothing" and executes:
            if need_appr:
                t_send = (task["task_due_at"] - E0) / DAY + float(rng.uniform(0.05, 0.5))
            res = send_marketing(t_send, choice, chn, trig, "randomised_holdout", dec_id, cart,
                                 trig_mult=2.0 if trig == "cart" else 1.0)
            if res and res[0]:
                mid, final, sent_at = res
        log_action(action_id=dec_id.replace("D", "A", 1), chosen_action=choice, channel=chn if choice not in ("do_nothing", "agent_call") else ("call" if choice == "agent_call" else None),
                   category="promotional" if mid else None, template=TEMPLATE.get(choice) if mid else None, message_id=mid,
                   campaign_id=("flow_cart_reminder" if trig == "cart" else "policy_weekly") if mid else None,
                   sent_at=sent_at, final_status=final, options_considered=dumps(opts), blocked_actions=dumps(blocked),
                   reason_codes=dumps(reasons), propensity=prop, expected_value=None, needs_approval=bool(need_appr),
                   **task, **kw)
        add(t_ep, "decision_made", "decision_service", f"decision:{dec_id}",
            {"decision_id": dec_id, "action": choice, "reason_code": reasons[0] if reasons else None}, ch=None)

    def decide_legacy(t, trig, cart):
        lp = p["messaging.legacy_p"]
        if trig == "cart":
            if rng.random() >= lp["cart_flow_p"]:
                return
            action = "reminder"
        else:
            lin = lp["a0"] + lp["a_p7"] * p7 + lp["a_orders"] * math.log1p(len(orders))
            if rng.random() >= sigmoid(lin):
                return
            lm = p["messaging.legacy_action_mix"]
            action = pick(rng, cum(list(lm.values())), list(lm))
        chn = pick_channel()
        if chn is None:
            return
        res = send_marketing(t + float(rng.uniform(0.0, 0.8)), action, chn, trig, "legacy_targeting", None, cart,
                             trig_mult=2.0 if trig == "cart" else 1.0)
        if res and res[0]:
            mid, final, sent_at = res
            log_action(decided_at=sent_at, record_kind="legacy_send", regime="legacy_targeting", trigger="cart" if trig == "cart" else "legacy_weekly",
                       chosen_action=action, channel=chn, category="promotional", template=TEMPLATE[action], message_id=mid,
                       campaign_id="legacy_flow_cart" if trig == "cart" else "legacy_weekly_blast", sent_at=sent_at, final_status=final)

    # points: weekly ticks + cart triggers
    points = []
    t0 = created + float(rng.uniform(0.5, 7))
    k = 0
    while t0 + 7 * k < T:
        points.append((t0 + 7 * k, "tick", None, k))
        k += 1
    for c in cart_list:
        points.append((c["t"] + float(rng.uniform(0.04, 0.12)), "cart", c, -1))
    points.sort(key=lambda x: x[0])
    for (t, kind, cart, kk) in points:
        if t >= T:
            break
        materialize_until(t)
        regime = 1 if t < X.reg2 else 2
        if kind == "cart" and cart["converted"]:
            continue
        if regime == 1:
            decide_legacy(t, "cart" if kind == "cart" else "tick", cart)
        else:
            state = est_state(t)
            if kind == "tick":
                if state not in ELIG or (state == "Reactivate" and kk % 4):
                    continue
                if state == "Retarget" and not any(not c["converted"] and t - 14 <= c["t"] <= t for c in cart_list):
                    continue
            decide_v2(t, "cart" if kind == "cart" else "weekly", cart, state)
    materialize_until(T)

    # ---------------- remaining checkouts (abandoned carts)
    for c in cart_list:
        if not c["emitted"]:
            if c["converted"]:
                continue
            band = band_amount(X, c["gross"])
            m_i = int(X.month_idx[min(int(c["t"]), T - 1)])
            reason = "sold_out" if X.stock[c["cat"]][m_i] == "out_of_stock" and rng.random() < 0.2 else None
            t_c = ep(c["t"])
            chn, cmp_ = traffic_channel()
            session_events(t_c - float(rng.uniform(120, 900)), n_pages() + 2, True, anon_ids[0], chn, cmp_,
                           extra=["add_to_cart", "begin_checkout"])
            emit_checkout(c["id"], t_c, c["cat"], c["items"], band, "abandoned", t_c + float(rng.uniform(1, 12)) * 3600, reason=reason)

    # ---------------- ambient sessions
    last_o = max([o["t_ep"] for o in orders], default=None)
    base_end = max(ep(created), last_o if last_o else ep(created))
    span_end = min(ep(T), base_end + (float(rng.exponential(tp["tail"])) + 10) * DAY)
    span_days = max(0.0, (span_end - ep(created)) / DAY)
    n_amb = int(rng.poisson(sess_pm * span_days / 30.0))
    if n_amb:
        cand = created + rng.uniform(0, span_days, size=n_amb * 3)
        cand = cand[(cand < T) & (rng.random(len(cand)) * X.mmax <= X.mult[np.minimum(cand.astype(int), T - 1)])][:n_amb]
    else:
        cand = np.array([])
    pre_sess = list(cand)
    if orders:  # ensure pre-purchase browsing before the first order
        o1 = min(o["t_ep"] for o in orders)
        pre_sess += [(o1 - float(rng.uniform(0.1, 8)) * DAY - E0) / DAY for _ in range(2)]
    for dday in sorted(pre_sess):
        if dday < 0 or dday >= T:
            continue
        chn, cmp_ = traffic_channel()
        st = ep(int(dday) + tod())
        session_events(st, n_pages(), True, anon_ids[0], chn, cmp_, login=rng.random() < p["sessions.login_prob"])

    # pre-identification anonymous sessions and identify event
    n_pre = int(rng.poisson(p["population.prior_sessions_mean"]))
    for _ in range(n_pre):
        d = created - float(rng.uniform(0.02, 10))
        if d < 0:
            continue
        session_events(ep(d), n_pages(), False, anon0, acq if acq != "whatsapp" else "organic", camp)
    linked = rng.random() < p["population.identify_link_prob"]
    add(ep(created), "identify", "ga4", f"identify:{unit}",
        {"via": ["checkout", "login", "otp"][int(rng.integers(0, 3))], "merged": anon0 if linked else None},
        ch=acq if acq != "whatsapp" else "organic", cmp_=camp, anon=anon0)

    # anonymous-only visitors
    n_vis = int(rng.poisson(p["population.anon_visitors_per_customer"]))
    for _ in range(n_vis):
        aid = f"{int(rng.integers(10**8, 10**9))}.{int(E0 + rng.uniform(0, T) * DAY)}"
        for _s in range(int(rng.geometric(1 / 3.2))):
            d = float(rng.uniform(0, T - 0.1))
            if rng.random() * X.mmax > X.mult[int(d)]:
                continue
            chn = ["organic", "paid_social", "paid_search", "referral"][int(rng.integers(0, 4))]
            session_events(ep(int(d) + tod()), n_pages(), False, aid, chn, None)

    # ---------------- snapshot rows
    ENDEP = END
    first_order_at = min((o["t_ep"] for o in orders), default=None)
    spend_total = 0.0
    for o in orders:
        fin = "paid" if (not o["cod"]) else "placed"
        ful, dl, att, rto_f, rto_r = "unfulfilled", None, None, False, None
        dl_t = dlv_t = canc_t = ref_t = None
        ref_amt = ref_reason = None
        paid_t = o.get("paid_t") if not o["cod"] else None
        n_fail = 0
        # event emission + snapshot, in time order
        pr_state = {"fin": fin}
        for (tt, kind, val) in sorted(o["tl"], key=lambda x: x[0]):
            if tt >= ENDEP:
                continue
            if kind == "fin":
                add(tt, "record_status_changed", "shopify", f"order:{o['id']}:{val}",
                    {"object": "order", "order_id": o["id"], "field": "financial", "from": pr_state["fin"], "to": val}, ch=o["chn"])
                pr_state["fin"] = val
                fin = val
                if val == "paid":
                    paid_t = tt
                    add(tt, "outcome_confirmed", "outcome_checker", f"outcome:order:{o['id']}:paid",
                        {"object": "order", "system": "shopify", "status": "paid", "order_id": o["id"],
                         "amount_band": o["band"], "decision_id": o["dec"]}, ch=o["chn"])
                if val in ("cancelled", "refunded") and "cancel_t" in o and tt == o["cancel_t"]:
                    canc_t = tt
                if val == "cancelled" and "rto_t" in o:
                    canc_t = tt
            elif kind == "ful":
                add(tt, "record_status_changed", "shopify", f"order:{o['id']}:{val}",
                    {"object": "order", "order_id": o["id"], "field": "fulfilment", "from": ful, "to": val}, ch=o["chn"])
                ful = val
            elif kind == "del":
                st_ = val[0]
                pr = {"object": "shipment", "order_id": o["id"], "to": st_, "attempt_no": val[1], "courier": o["courier"],
                      "payment_mode": "cod" if o["cod"] else "prepaid"}
                if st_ == "rto":
                    pr["rto_reason"] = val[2]
                    rto_f, rto_r = True, val[2]
                add(tt, "record_status_changed", "shiprocket", f"shipment:{o['id']}:{st_}:{val[1]}", pr, ch=o["chn"])
                dl, dl_t = st_, tt
                att = val[1]
                if st_ == "delivered":
                    dlv_t = tt
                    add(tt, "outcome_confirmed", "outcome_checker", f"outcome:shipment:{o['id']}:delivered",
                        {"object": "shipment", "system": "shiprocket", "status": "delivered", "order_id": o["id"],
                         "amount_band": o["band"], "decision_id": o["dec"]}, ch=o["chn"])
            elif kind == "refund":
                frac, reason = val
                ref_t, ref_reason = tt, reason
                ref_amt = band_amount(X, o["net"] * frac)
                add(tt, "record_created", "shopify", f"refund:{o['id']}:refunded",
                    {"object": "refund", "order_id": o["id"], "status": "refunded", "amount_band": ref_amt, "reason_category": reason}, ch=o["chn"])
            elif kind == "pay_refund":
                add(tt, "record_status_changed", "razorpay", f"payment:{o.get('pay_id')}:refunded",
                    {"object": "payment", "payment_id": o.get("pay_id"), "from": "captured", "to": "refunded"}, ch="web")
                for pr_ in pay_rows:
                    if pr_["payment_id"] == o.get("pay_id"):
                        pr_["status"] = "refunded"
        if o["cod"] and paid_t is not None and paid_t >= ENDEP:
            paid_t = None
        disc_b = None if not o["disc"] else ("0-10%" if o["disc"] <= 10 else "10-20%" if o["disc"] <= 20 else "20%+")
        order_rows.append({
            "order_id": o["id"], "unit_id": unit, "checkout_id": o["chk"], "created_at": o["t_ep"],
            "processed_at": o["processed"] if o["processed"] < ENDEP else None, "financial_status": fin,
            "fulfilment_status": ful, "amount_band": o["band"], "item_count": o["items"],
            "payment_mode": "cod" if o["cod"] else "prepaid", "discount_code": f"DISC{o['disc']}" if o["disc"] else None,
            "discount_band": disc_b, "order_source": "app" if dev in ("android", "ios") and rng.random() < 0.55 else "web",
            "channel": o["chn"], "campaign_id": o["camp"], "decision_id": o["dec"], "category_primary": o["cat"],
            "cancelled_at": canc_t, "paid_at": paid_t, "courier": o["courier"] if ful != "unfulfilled" else None,
            "delivery_status": dl, "delivery_status_changed_at": dl_t, "delivered_at": dlv_t, "attempt_count": att,
            "rto_flag": rto_f, "rto_reason_category": rto_r, "refund_created_at": ref_t, "refund_amount_band": ref_amt,
            "refund_status": "refunded" if ref_t else None, "refund_reason_category": ref_reason})
        mp = float(np.clip(X.cats[o["cat"]]["margin"] * rng.lognormal(0, 0.3), 0.03, 0.8))
        ot_rows.append({"order_id": o["id"], "unit_id": unit, "kind": o["kind"], "cause_decision_id": o["cause_dec"],
                        "exact_amount_gross": round(o["gross"], 2), "exact_amount_net": round(o["net"], 2),
                        "margin_pct": round(mp, 4), "margin_amount": round(o["net"] * mp, 2)})
        spend_total += o["net"] if fin not in ("cancelled", "refunded") else 0.0

    # holdout assignment applies to everyone at max(created, regime-2 start); customers created after END do not exist
    cust = {
        "unit_id": unit, "person_key": pk, "created_at": ep(created), "first_order_at": first_order_at,
        "orders_count": len(orders), "spend_band": band_spend(spend_total), "device_class": dev,
        "acquisition_channel": acq, "campaign_id": camp, "email_consent": cons["email"], "sms_consent": cons["sms"],
        "whatsapp_consent": cons["whatsapp"], "geo_tier": TIERS[tier],
        "regime_first_seen": "legacy_targeting" if created < X.reg2 else "randomised_holdout",
        "holdout_group": "control" if control else "treated", "holdout_assigned_at": ep(hold_assigned),
        "holdout_share": X.share, "holdout_strategy": "random_hash",
        "shopify_customer_ref": str(7_000_000_000_000 + i), "klaviyo_profile_ref": f"01K{i:07d}",
        "razorpay_ref": razorpay_ref[0], "zendesk_requester_ref": zendesk_ref[0], "ga4_user_id": f"u_{i:07d}",
        "email_key": email_key}
    persuadable = [a for a in ACTS if u_true[a] >= 0.03]
    truth = {"unit_id": unit, "hidden_type": ty, "type_changes": dumps(type_changes), "order_gap_days_mean": gap_mu,
             "order_gap_cv": gap_cv, "sessions_per_month": sess_pm, "price_sensitivity": ps, "cod_preference": cod_pref,
             "return_propensity": ret_factor, "refusal_propensity": X.cats[interest_cat]["rto"], "serial_returner": bool(serial),
             "reacts_badly": bool(reacts_badly), "baseline_p7": p7, "would_act_anyway": bool(p7 > 0.35 and max(u_true.values()) < 0.03),
             "never_acts": bool(p7 < 0.02 and max(u_true.values()) < 0.01), "persuadable_actions": dumps(persuadable),
             "uplift_reminder": u_true["reminder"], "uplift_discount": u_true["discount"],
             "uplift_free_shipping": u_true["free_shipping"], "uplift_bundle": u_true["bundle"],
             "uplift_agent_call": u_true["agent_call"], "shared_phone_with": shared_with, "anon_ids": dumps(anon_ids),
             "geo_tier": TIERS[tier]}
    ev_rows = []
    EV.sort(key=lambda r: r[0])
    for n, r in enumerate(EV):
        ev_rows.append((f"E{i:07d}-{n:05d}",) + r)
    return {"customer": cust, "events": ev_rows, "orders": order_rows, "payments": pay_rows, "tickets": tick_rows,
            "actions": act_rows, "person_truth": truth, "order_truth": ot_rows}
