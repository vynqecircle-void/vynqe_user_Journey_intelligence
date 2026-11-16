"""BFSI personal-loan simulator. One person at a time (independent, deterministic per (seed, index)).
SYNTHETIC DATA: every number comes from config/bfsi.yaml with a grade. Times are epoch seconds (UTC)."""
from __future__ import annotations
import json
import math
from statistics import NormalDist
from types import SimpleNamespace
import numpy as np
import pandas as pd

from ...core.ids import keyed_hash, hash_u

DAY = 86400.0
TIERS = ["metro", "tier1", "tier2", "tier3", "rural"]
ACTS = ["nudge", "agent_call", "fee_waiver", "offer", "emi_nudge"]
TEMPLATE = {"nudge": "resume_application", "agent_call": "agent_call_script", "fee_waiver": "fee_waiver_offer",
            "offer": "preapproved_offer", "emi_nudge": "emi_helper_nudge"}
SRC_FOR = {"email": "klaviyo", "sms": "klaviyo", "whatsapp": "whatsapp"}
CH_MAP = {"existing_base": "in_app", "partner": "partner", "paid_social": "paid_social", "paid_search": "paid_search",
          "organic": "organic", "whatsapp": "whatsapp", "referral": "referral"}
STEP_MULT = {"nudge": {"kyc": 1.0, "consent": 0.8, "offer": 0.6, "sign": 0.9, "disburse": 0.5},
             "agent_call": {"kyc": 1.1, "consent": 1.0, "offer": 1.1, "sign": 1.2, "disburse": 1.0},
             "fee_waiver": {"kyc": 0.0, "consent": 0.0, "offer": 1.5, "sign": 0.8, "disburse": 0.4}}


def dumps(o):
    return json.dumps(o, separators=(",", ":"))


def sigmoid(x):
    return 1.0 / (1.0 + math.exp(-x))


def cum(weights):
    a = np.array(weights, float)
    return np.cumsum(a / a.sum())


def pick(rng, cumarr, names):
    return names[min(int(np.searchsorted(cumarr, rng.random())), len(names) - 1)]


def build_context(cfg, seed: int) -> SimpleNamespace:
    X = SimpleNamespace()
    X.cfg, X.seed = cfg, seed
    v = cfg.v
    start = pd.Timestamp(v("run.start_date"), tz="UTC")
    X.start, X.E0, X.T = start, start.timestamp(), int(v("run.n_days"))
    X.reg2 = float(v("run.regime2_day"))
    X.END = X.E0 + X.T * DAY
    X.REG2 = X.E0 + X.reg2 * DAY
    X.secret = v("run.hash_secret").encode()
    X.salt = v("run.holdout_salt")
    X.share = float(v("run.holdout_share"))
    days = pd.date_range(start, periods=X.T, freq="D")
    dom, dim = days.day.to_numpy(), days.days_in_month.to_numpy()
    mult = np.ones(X.T)
    mult[(dom <= 7) | (dom > dim - v("calendar.month_end_days"))] *= v("calendar.salary_day_mult")
    for a, b in v("calendar.festive_windows"):
        i0 = max(0, (pd.Timestamp(a, tz="UTC") - start).days)
        i1 = min(X.T - 1, (pd.Timestamp(b, tz="UTC") - start).days)
        if i1 >= i0:
            mult[i0:i1 + 1] *= v("calendar.festive_mult")
    ts = v("calendar.tax_season")
    mult[(days.month >= ts[0]) & (days.month <= ts[1])] *= 1.2
    X.mult, X.mmax, X.dom = mult, float(mult.max()), dom
    X.month_idx = ((days.year - start.year) * 12 + days.month - start.month).to_numpy()
    w = (1 + v("population.growth_per_year")) ** (np.arange(X.T) / 365.0) * mult ** 0.5
    X.created_cdf = np.cumsum(w / w.sum())
    hw = np.array(v("sessions.hour_weights_ist"), float)
    X.hour_cdf = np.cumsum(hw / hw.sum())
    mix = v("population.acquisition_mix")
    X.acq_names, X.acq_cum = list(mix), cum(list(mix.values()))
    X.types = v("population.types")
    X.type_names = list(X.types)
    X.type_share = np.array([X.types[k]["share"] for k in X.type_names], float)
    X.cf = v("population.channel_type_factor")
    X.tier_cum = cum(v("population.tier_mix"))
    dm = v("population.device_mix")
    X.dev_names, X.dev_cum = list(dm), cum(list(dm.values()))
    X.cut = [NormalDist().inv_cdf(c) for c in v("repayment.state_cuts")]
    X.p = {}
    for sec in ("population", "sessions", "funnel", "risk", "repayment", "messaging", "noise"):
        for k, node in cfg.data[sec].items():
            X.p[f"{sec}.{k}"] = node["value"] if isinstance(node, dict) and "grade" in node else node
    X.amount_labels = ["0-10k", "10k-25k", "25k-50k", "50k-100k", "100k-250k", "250k+"]
    X.tenure_labels = ["<=12m", "13-24m", "25-36m", "37-60m"]
    return X


def band_amount(X, x):
    e = X.p["population.amount_edges"]
    k = int(np.searchsorted(e, x, side="right")) - 1
    return X.amount_labels[min(max(k, 0), len(X.amount_labels) - 1)]


def band_tenure(X, n):
    e = X.p["population.tenure_band_edges"]
    k = int(np.searchsorted(e, n, side="left")) - 1
    return X.tenure_labels[min(max(k, 0), len(X.tenure_labels) - 1)]


def simulate_person(i: int, X) -> dict:
    p = X.p
    rng = np.random.default_rng([X.seed, 1, i])
    E0, T, END, REG2 = X.E0, X.T, X.END, X.REG2
    unit = f"B{i:07d}"
    ep = lambda d: E0 + d * DAY
    LN = lambda med, sg: float(rng.lognormal(math.log(max(med, 1e-9)), sg))

    def tod():
        h = int(np.searchsorted(X.hour_cdf, rng.random()))
        sec = (min(h, 23) * 3600 + rng.uniform(0, 3600) - 19800) % DAY
        return sec / DAY

    # ------------------------------------------------------------ static attributes
    created = float(np.searchsorted(X.created_cdf, rng.random())) + rng.random()
    created = min(created, T - 2.0)
    created_t = ep(int(created) + tod())
    acq = pick(rng, X.acq_cum, X.acq_names)
    tw = X.type_share.copy()
    for k, f in X.cf.get(acq, {}).items():
        tw[X.type_names.index(k)] *= f
    ty = X.type_names[int(np.searchsorted(cum(tw), rng.random()))]
    tp = X.types[ty]
    tier = min(int(np.searchsorted(X.tier_cum, rng.random())), 4)
    dev = pick(rng, X.dev_cum, X.dev_names)
    salaried = rng.random() < p["population.salaried_share"]
    emp = "salaried" if salaried else "self_employed"
    u30 = rng.random() < p["population.under30_share"]
    age = 21 + int(rng.integers(0, 9)) if u30 else 30 + int(rng.integers(0, 26))
    income = 12.0 * p["population.income_monthly_median"][emp] * p["population.tier_income_mult"][tier] * LN(1.0, p["population.income_sigma"][emp])
    existing = acq == "existing_base"
    bt = lambda ab: float(rng.beta(*ab))
    urgency, shop, kyc_fr, topup_pr, prepay_pr = bt(tp["urgency"]), bt(tp["shop"]), bt(tp["kyc"]), bt(tp["topup"]), bt(tp["prepay"])
    mfp, doc_q = float(rng.beta(2, 8)), float(rng.beta(5, 2))
    reacts_badly = rng.random() < p["population.reacts_badly_share"]
    fraud = rng.random() < p["population.fraud_share"]
    stacking = rng.random() < p["population.stacking_share"]
    u_true = {}
    for a in ACTS:
        u = tp["uplift"][a] * float(rng.lognormal(0, 0.35)) + float(rng.normal(0, 0.008))
        if reacts_badly:
            u = -float(rng.uniform(0.01, 0.05))
        u_true[a] = float(np.clip(u, -0.08, 0.35))
    type_changes, ty2, t_change = [], None, None
    if rng.random() < p["population.type_change_share"]:
        ty2 = p["population.type_change_to"][int(rng.integers(0, 3))]
        t_change = created_t + float(rng.uniform(60, 500)) * DAY
        type_changes.append({"to": ty2, "day": round((t_change - E0) / DAY, 1)})
    u_true2 = None
    if ty2:
        r2 = np.random.default_rng([X.seed, 2, i])
        u_true2 = {a: float(np.clip(X.types[ty2]["uplift"][a] * r2.lognormal(0, 0.35), -0.08, 0.35)) if not reacts_badly else u_true[a] for a in ACTS}

    def uu(a, t):
        return u_true2[a] if (u_true2 is not None and t >= t_change) else u_true[a]
    lti = float(rng.uniform(*tp["lti"]))
    lo_c, hi_c = p["population.amount_clip"]

    def draw_amount(scale=1.0):
        return float(np.clip(round(lti * income * scale * float(rng.lognormal(0, 0.15)), -2), lo_c, hi_c))

    req0 = draw_amount()
    zc = p["risk.z_coefs"]
    s_amt = float(np.clip(-(math.log(req0) - math.log(40000)) / 0.9, -2, 2))
    zraw = (zc["small_amount"] * s_amt + zc["under30"] * u30 + zc["tier"] * (tier - 2) + zc["self_employed"] * (not salaried)
            + zc["existing"] * existing + zc["stacking"] * stacking + zc["lti"] * (lti - 0.2) + zc["fraud"] * fraud
            + float(rng.normal(0, zc["noise_sd"])))
    zs = (zraw - p["risk.z_norm"][0]) / p["risk.z_norm"][1]
    lnoise = float(rng.normal(0, p["risk.band_noise_sd"]))
    band = int(np.searchsorted(p["risk.band_cuts"], zs + lnoise)) + 1           # lender band 1..4

    # identity
    def phone_of(j):
        return int(np.random.default_rng([X.seed, 7, j]).integers(6_000_000_000, 10_000_000_000))
    shared_with = None
    if rng.random() < p["noise.shared_phone"] and i > 0:
        shared_with, phone = f"B{i - 1:07d}", phone_of(i - 1)
    else:
        phone = phone_of(i)
    pk = keyed_hash(X.secret, f"91{phone}")
    email_key = keyed_hash(X.secret, f"user{i}@example.test")
    anon_ids = [f"{int(rng.integers(10**8, 10**9))}.{int(created_t - 3 * DAY)}" for _ in range(1 + int(rng.random() < 0.3))]
    anon0 = anon_ids[0]
    camp_pool = {"paid_social": [f"meta_{k}" for k in range(1, 5)], "paid_search": [f"gads_{k}" for k in range(1, 5)],
                 "partner": ["partner_1", "partner_2"]}
    camp = camp_pool[acq][int(rng.integers(0, len(camp_pool[acq])))] if acq in camp_pool else ("wa_optin" if acq == "whatsapp" else None)
    chan = CH_MAP[acq]
    control = hash_u(X.salt, unit) < X.share
    hold_assigned = max(created_t, REG2)

    # ------------------------------------------------------------ buffers
    EV, A_ROWS, STEP_ROWS, LOANS, EMI, CASES, ACT, ATRUTH = [], [], [], [], [], [], [], []
    cnt = {"app": 0, "step": 0, "task": 0, "msg": 0, "act": 0, "case": 0, "loan": 0, "pay": 0, "lead": 0}
    refs = {"razorpay": None, "core": None}
    noise_extra = []

    def add(t, et, src, seid, props, ch=None, cmp_=None, cons=None, anon=None, known=True):
        if t >= END or t < E0 - 20 * DAY:
            return
        EV.append((t, et, src, seid, pk if known else None, anon, unit if known else None, ch, cmp_, cons, props,
                   unit if (known or anon in anon_ids) else None))

    # ------------------------------------------------------------ consent (marketing only)
    ci = p["population.consent_initial"]
    cons, cons_k = {}, [0]
    for chn in ("email", "sms", "whatsapp"):
        r = rng.random()
        g, d_ = ci[chn]["granted"], ci[chn]["denied"]
        cons[chn] = "granted" if r < g else "denied" if r < g + d_ else "unknown"
        if cons[chn] != "unknown":
            add(created_t + 5, "consent_change", "salesforce" if chn != "whatsapp" else "warehouse",
                f"consent:{unit}:{chn}:{cons[chn]}:0", {"channel": chn, "purpose": "marketing", "status": cons[chn]}, ch=chn, cons=cons[chn])
    do_not_market = rng.random() < p["population.do_not_market_share"]
    if do_not_market:
        for chn in cons:
            if cons[chn] == "granted":
                cons[chn] = "withdrawn"

    def set_consent(chn, st, t):
        cons[chn] = st
        cons_k[0] += 1
        add(t, "consent_change", SRC_FOR[chn], f"consent:{unit}:{chn}:{st}:{cons_k[0]}",
            {"channel": chn, "purpose": "marketing", "status": st}, ch=chn, cons=st)

    # ------------------------------------------------------------ session helpers
    def n_pages():
        return int(min(p["sessions.max_events"], rng.geometric(1.0 / p["sessions.mean_pages"])))

    def session_events(start_t, n_ev, known, anon, ch, cmp_, features=(), login=False):
        gm = math.log(p["sessions.gap_median_sec"])
        t, sid = start_t, int(start_t)
        for j in range(n_ev):
            if features and j >= n_ev - len(features):
                ft = features[j - (n_ev - len(features))]
            elif login and j == 0:
                ft = "login"
            else:
                ft = "home" if rng.random() < 0.5 else "product_info"
            add(t, "page_view", "trackflow", f"pv:{anon}:{sid}:{j}",
                {"feature": ft, "session_id": sid, "platform": "app" if dev in ("android", "ios") and rng.random() < 0.6 else "web",
                 "device": dev}, ch=ch, cmp_=cmp_, anon=anon, known=known)
            t += min(600.0, float(rng.lognormal(gm, 1.0)))
        return t

    # ------------------------------------------------------------ lead record
    cnt["lead"] += 1
    lead_id = f"L{i:07d}"
    add(created_t, "record_created", "salesforce", f"lead:{lead_id}:new",
        {"object": "lead", "lead_id": lead_id, "status": "new", "lead_source": acq}, ch=chan, cmp_=camp)
    n_pre = int(rng.poisson(p["population.prior_sessions_mean"]))
    for s_ in range(n_pre):
        d = created_t - float(rng.uniform(0.02, 8)) * DAY
        feats = ["emi_calculator"] * int(rng.integers(*tp["calc_views"])) if s_ == 0 else []
        session_events(d, n_pages() + len(feats), False, anon0, chan, camp, features=tuple(feats))
    n_vis = int(rng.poisson(p["population.anon_visitors_per_person"]))
    for _ in range(n_vis):
        aid = f"{int(rng.integers(10**8, 10**9))}.{int(E0 + rng.uniform(0, T) * DAY)}"
        for _s in range(int(rng.geometric(1 / 2.5))):
            d = float(rng.uniform(0, T - 0.1))
            if rng.random() * X.mmax > X.mult[int(d)]:
                continue
            session_events(ep(int(d) + tod()), n_pages(), False, aid, ["organic", "paid_social", "paid_search", "referral"][int(rng.integers(0, 4))], None)

    # ------------------------------------------------------------ messaging helpers
    mkt_times, tasks_t, aa_active, late_ivals, coll_ivals, disp_ivals = [], [], [False], [], [], []

    def pick_channel():
        granted = [c for c in ("whatsapp", "sms", "email") if cons[c] == "granted"]
        if not granted:
            return None
        if len(granted) == 1:
            return granted[0]
        w = [p["messaging.channel_pref"][c] for c in granted]
        return granted[int(np.searchsorted(cum(w), rng.random()))]

    def mk_msg_times(chn, t, force_click):
        st = p["messaging.channel_stats"][chn]
        ev = [(t, "sent")]
        if rng.random() >= st["deliver"]:
            f = "bounced" if chn == "email" else "failed"
            ev.append((t + float(rng.uniform(1, 60)), f))
            return ev, f, False
        td = t + float(rng.uniform(2, 120))
        opened = rng.random() < st["open"] or force_click
        if chn == "sms":
            ev.append((td, "delivered"))
            if rng.random() < 0.03 or force_click:
                ev.append((td + float(rng.uniform(30, 3000)), "clicked"))
                return ev, "clicked", True
            return ev, "delivered", False
        if not (chn == "whatsapp" and opened and rng.random() < st.get("skip_delivered_when_read", 0)):
            ev.append((td, "delivered"))
        final, clicked = "delivered", False
        if opened:
            to = td + float(rng.lognormal(math.log(600 if chn == "whatsapp" else 2400), 1.2))
            ev.append((to, "opened"))
            final = "opened"
            if force_click or rng.random() < st["click_given_open"]:
                ev.append((to + float(rng.uniform(5, 600)), "clicked"))
                final, clicked = "clicked", True
        return ev, final, clicked

    def new_act_id():
        cnt["act"] += 1
        return f"A{i:07d}-{cnt['act']:04d}"

    def log_action(**kw):
        base = dict(action_id=None, unit_id=unit, person_key=pk, application_ref=None, record_kind="decision",
                    regime="randomised_holdout", decided_at=None, trigger="stall", chosen_action="do_nothing", channel=None,
                    category=None, template=None, message_id=None, campaign_id=None, sent_at=None, final_status=None,
                    options_considered=None, blocked_actions=None, reason_codes=None, propensity=None, expected_value=None,
                    model_versions=None, rule_version=None, needs_approval=False, in_holdout=False, holdout_group=None,
                    task_id=None, task_target=None, task_status=None, task_due_at=None, task_owner_id=None,
                    task_capacity_bucket=None, disposition=None, call_duration_s=None)
        base.update(kw)
        base["action_id"] = base["action_id"] or new_act_id()
        ACT.append(base)

    def send_service(t, chn, tpl, category, app_ref=None, src=None, trig="service"):
        """Transactional or regulatory message: never held out, never chosen by the policy."""
        if t >= END:
            return
        cnt["msg"] += 1
        mid = f"M{i:07d}-{cnt['msg']:04d}"
        st = p["messaging.channel_stats"].get(chn, p["messaging.channel_stats"]["sms"])
        ev = [(t, "sent")]
        if rng.random() < st["deliver"]:
            ev.append((t + float(rng.uniform(2, 120)), "delivered"))
            final = "delivered"
        else:
            final = "bounced" if chn == "email" else "failed"
            ev.append((t + float(rng.uniform(1, 60)), final))
        s_ = src or SRC_FOR.get(chn, "klaviyo")
        for tt, s2 in ev:
            add(tt, "message_status", s_, f"msg:{mid}:{s2}", {"message_id": mid, "status": s2, "channel": chn, "template": tpl}, ch=chn)
        log_action(application_ref=app_ref, record_kind="transactional", regime="legacy_targeting" if t < REG2 else "randomised_holdout",
                   decided_at=t, trigger=trig, chosen_action="regulatory" if category == "regulatory" else "transactional",
                   channel=chn, category=category, template=tpl, message_id=mid, sent_at=t, final_status=final)
        return final

    def svc_channel():
        return pick(rng, cum([0.45, 0.30, 0.25]), ["whatsapp", "sms", "email"])

    # ------------------------------------------------------------ case helpers
    def open_case(cat, t_open, t_close, suppress=True):
        cnt["case"] += 1
        cid = f"CS{i:07d}-{cnt['case']:02d}"
        tl = [(t_open, "open")]
        if t_close is not None:
            tl += [(t_open + (t_close - t_open) * 0.4, "in_progress"), (t_close, "resolved"), (t_close + 2 * DAY, "closed")]
        last_st, upd = None, t_open
        for tt, st in tl:
            if tt >= END:
                break
            if last_st is None:
                add(tt, "record_created", "service_collections", f"case:{cid}:{st}", {"object": "case", "case_id": cid, "case_category": cat, "status": st})
            else:
                add(tt, "record_status_changed", "service_collections", f"case:{cid}:{st}",
                    {"object": "case", "case_id": cid, "case_category": cat, "from": last_st, "to": st})
            last_st, upd = st, tt
        if last_st is None:
            return
        closed_at = t_close + 2 * DAY if (t_close is not None and t_close + 2 * DAY < END) else None
        CASES.append({"case_id": cid, "unit_id": unit, "status": last_st, "category": cat, "opened_at": t_open, "closed_at": closed_at,
                      "suppress_marketing": bool(suppress)})
        if suppress:
            (coll_ivals if cat == "collections" else disp_ivals).append((t_open, t_close))

    def in_iv(ivals, t):
        return any(a <= t and (b is None or t < b) for a, b in ivals)

    # ------------------------------------------------------------ marketing effect + send
    def fatigue(t):
        n14 = sum(1 for d in mkt_times if t - 14 * DAY <= d < t)
        return n14, 1.0 / (1.0 + p["messaging.fatigue_k"] * max(0, n14 - 1))

    def in_window(t):
        h0, h1 = p["messaging.window_hours_ist"]
        sec = (t + 19800) % DAY
        if h0 * 3600 <= sec <= h1 * 3600:
            return t
        return (math.floor((t + 19800) / DAY)) * DAY + float(rng.uniform(h0 * 3600, h1 * 3600)) - 19800 + (DAY if sec > h1 * 3600 else 0)

    def send_promo(t, action, chn, trig, dec_id, app_ref, nat_t, mult, trig_name):
        """Send a promotional message and apply the planted true effect. Returns dict(mid, final, t, converts_at, clicked, works)."""
        t = in_window(t)
        if t >= END:
            return None
        n14, fat = fatigue(t)
        u = uu(action, t) * fat * mult
        converts = u > 0 and (nat_t is None or nat_t > t + 7 * DAY) and rng.random() < min(0.6, u)
        works = u > 0 and rng.random() < min(0.6, u * 6.0)           # emi_nudge effect probability among at-risk instalments
        force_click = bool(converts and rng.random() < 0.75)
        mev, final, clicked = mk_msg_times(chn, t, force_click)
        cnt["msg"] += 1
        mid = f"M{i:07d}-{cnt['msg']:04d}"
        st = p["messaging.channel_stats"][chn]
        pun = st["unsub"] + p["messaging.unsub_fatigue"] * max(0, n14 - 2) + (p["messaging.unsub_reacts_badly"] if reacts_badly else 0)
        if final not in ("bounced", "failed") and rng.random() < pun:
            tu = max(tt for tt, _ in mev) + float(rng.uniform(5, 600))
            mev.append((tu, "unsubscribed"))
            final = "unsubscribed"
            set_consent(chn, "withdrawn", tu + 1)
        for tt, s_ in mev:
            add(tt, "message_status", SRC_FOR[chn], f"msg:{mid}:{s_}",
                {"message_id": mid, "status": s_, "channel": chn, "template": TEMPLATE[action], "decision_id": dec_id}, ch=chn)
            if s_ == "clicked":
                add(tt + 1, "link_click", SRC_FOR[chn], f"click:{mid}", {"message_id": mid, "target": "resume_link", "channel": chn, "decision_id": dec_id}, ch=chn)
        mkt_times.append(t)
        delay = None
        if converts:
            delay = min(6.9, float(rng.exponential(p["messaging.response_mean_days"]))) + 0.02
        elif u < 0 and nat_t is not None and rng.random() < min(0.8, -u * 10):
            pass  # sleeping dog: handled by caller via 'pushes_back'
        return {"mid": mid, "final": final, "t": t, "converts_at": (t + delay * DAY) if converts else None, "clicked": clicked or force_click,
                "works": works, "pushes_back": bool(u < 0 and rng.random() < min(0.8, -u * 10))}

    def do_call(t, dec_id, app_ref, converts):
        """Agent call: Salesforce task + contact-centre call. Returns (disposition, duration)."""
        t = in_window(t)
        cm = p["messaging.call_disposition_mix"]
        disp = "application_completed" if converts else pick(rng, cum(list(cm.values())), [k for k in cm if k != "application_completed"] if False else list(cm))
        if converts and rng.random() < 0.3:
            disp = "connected"
        dur = int(LN(180, 0.6)) if disp in ("connected", "callback_requested", "application_completed") else int(rng.integers(0, 20))
        cnt["task"] += 1
        tid = f"TK{i:07d}-{cnt['task']:03d}"
        tasks_t.append(t)
        add(t - 60, "record_created", "salesforce", f"task:{tid}:open", {"object": "task", "task_id": tid, "status": "open", "decision_id": dec_id})
        add(t, "record_created", "contact_centre", f"call:{tid}", {"object": "call", "call_id": tid, "disposition": disp, "duration": dur, "direction": "outbound"}, ch="call")
        add(t + dur + 30, "record_status_changed", "salesforce", f"task:{tid}:completed", {"object": "task", "task_id": tid, "from": "open", "to": "completed", "disposition": disp})
        if disp == "connected" or disp == "application_completed":
            add(t + dur + 40, "record_status_changed", "salesforce", f"lead:{lead_id}:contacted", {"object": "lead", "lead_id": lead_id, "from": "new", "to": "contacted"})
        return disp, dur, t

    def guard(t, cands, ctx):
        """Return (allowed list, blocked list of dicts, chn)."""
        chn = pick_channel()
        blocked = []
        reason_all = None
        if do_not_market or chn is None:
            if aa_active[0] and ctx.get("aa", True):
                reason_all = "aa_consent_only"
            elif any(v == "unknown" for v in cons.values()) and not do_not_market:
                reason_all = "unknown_consent"
            else:
                reason_all = "no_consent"
        elif in_iv(coll_ivals, t):
            reason_all = "collections_hold"
        elif in_iv(disp_ivals, t):
            reason_all = "dispute_hold"
        elif any(t - p["messaging.rep_engaged_days"] * DAY <= d <= t for d in tasks_t):
            reason_all = "rep_engaged"
        elif sum(1 for d in mkt_times if t - 7 * DAY <= d <= t) >= p["messaging.freq_cap_7d"]:
            reason_all = "frequency_cap"
        if reason_all:
            return [], [{"action": a, "reason_code": reason_all} for a in cands], chn
        for a in cands:
            if a == "offer":
                if ctx.get("mandate_inactive"):
                    blocked.append({"action": a, "reason_code": "mandate_inactive"})
                elif band >= p["messaging.suitability_band_max"] or any(s_ >= t - 90 * DAY and (e_ is None or e_ > s_) and s_ <= t for s_, e_ in late_ivals):
                    blocked.append({"action": a, "reason_code": "suitability_failed"})
            elif a == "agent_call":
                dm = int(X.dom[min(int((t - E0) // DAY), T - 1)])
                avail = 1 - (1 - p["messaging.capacity_floor"]) * ((min(dm, 28) - 1) / 27.0) ** 2
                if hash_u(f"cap{int((t - E0) // (7 * DAY))}", unit) > avail:
                    blocked.append({"action": a, "reason_code": "capacity_full"})
        bl_acts = {b["action"] for b in blocked}
        return [a for a in cands if a not in bl_acts], blocked, chn

    def decide(t, trig, cands, ctx):
        """One decision point. ctx: app, step, nat_t, mult_key, trig_mult, mandate_inactive. Returns dict with effect info (or None)."""
        app = ctx.get("app")
        app_ref = app["ref"] if app else None
        legacy = t < REG2
        t_ep = t
        if legacy:
            lp = p["messaging.legacy_p"]
            val = ctx.get("value", 20000.0)
            if rng.random() >= sigmoid(lp["a0"] + lp["a_band"] * (band - 2.5) + lp["a_value"] * math.log(max(val, 1000) / 20000.0)):
                return None
            if in_iv(coll_ivals, t) or in_iv(disp_ivals, t):
                return None
            lm = {k: w for k, w in p["messaging.legacy_action_mix"].items() if k in cands}
            if not lm:
                return None
            action = pick(rng, cum(list(lm.values())), list(lm))
            chn = pick_channel()
            if chn is None or do_not_market:
                return None
            r = send_promo(t_ep + float(rng.uniform(0, 0.8 * DAY)), action, chn, trig, None, app_ref, ctx.get("nat_t"),
                           STEP_MULT.get(action, {}).get(ctx.get("mult_key"), 1.0) * ctx.get("trig_mult", 1.0), trig)
            if r:
                r["action"] = action
                log_action(application_ref=app_ref, decided_at=r["t"], record_kind="legacy_send", regime="legacy_targeting", trigger="legacy",
                           chosen_action=action, channel=chn, category="promotional", template=TEMPLATE[action], message_id=r["mid"],
                           campaign_id="legacy_flow", sent_at=r["t"], final_status=r["final"])
                r["dec_id"] = None
            return r
        cnt["act"] += 1
        dec_id = f"D{i:07d}-{cnt['act']:04d}"
        aid = dec_id.replace("D", "A", 1)
        allowed, blocked, chn = guard(t, cands, ctx)
        kw = dict(application_ref=app_ref, decided_at=t, trigger=trig, regime="randomised_holdout",
                  holdout_group="control" if control else "treated", model_versions="exploration_policy_v0",
                  rule_version="bfsi_rules_v0.1", in_holdout=False)
        if allowed and control:
            blocked += [{"action": a, "reason_code": "in_holdout"} for a in allowed]
            allowed, kw["in_holdout"] = [], True
        reasons = sorted({b["reason_code"] for b in blocked})
        opts = [{"action": a, "action_cost": p["messaging.action_cost"][a], "uplift": None, "expected_value": None} for a in allowed]
        add(t, "decision_made", "decision_service", f"decision:{dec_id}", {"decision_id": dec_id, "action": "do_nothing" if not allowed else "pending"})
        if not allowed:
            log_action(action_id=aid, chosen_action="do_nothing", options_considered=dumps(opts), blocked_actions=dumps(blocked),
                       reason_codes=dumps(reasons), propensity=1.0, **kw)
            return None
        pdn = p["messaging.policy_do_nothing"]
        choice = "do_nothing" if rng.random() < pdn else allowed[int(rng.integers(0, len(allowed)))]
        prop = pdn if choice == "do_nothing" else (1 - pdn) / len(allowed)
        if choice == "do_nothing":
            log_action(action_id=aid, chosen_action="do_nothing", options_considered=dumps(opts), blocked_actions=dumps(blocked),
                       reason_codes=dumps(reasons), propensity=prop, **kw)
            return None
        need_appr = choice == "fee_waiver" and ctx.get("value", 0) >= p["messaging.fee_waiver_approval_amount"]
        task, executes = {}, True
        if need_appr or choice == "agent_call":
            if need_appr:
                blocked.append({"action": choice, "reason_code": "approval_limit"})
                reasons = sorted({b["reason_code"] for b in blocked})
            sm = p["messaging.task_status_mix"]
            tst = pick(rng, cum(list(sm.values())), list(sm))
            executes = tst == "done"
            task = dict(task_id=f"TKA{i:07d}-{cnt['act']:04d}", task_target="crm_task" if need_appr else "agent_call_list", task_status=tst,
                        task_due_at=t + float(rng.uniform(0.2, 2)) * DAY, task_owner_id=f"owner_{int(rng.integers(1, 9))}",
                        task_capacity_bucket=pick(rng, cum([0.5, 0.35, 0.15]), ["low", "medium", "high"]))
        mult = STEP_MULT.get(choice, {}).get(ctx.get("mult_key"), 1.0) * ctx.get("trig_mult", 1.0)
        res = None
        t_send = t + float(rng.uniform(0.01, 0.9) * DAY)
        if executes:
            if task:
                t_send = task["task_due_at"] + float(rng.uniform(0.05, 0.5)) * DAY
            if choice == "agent_call":
                n14, fat = fatigue(t_send)
                u = uu("agent_call", t_send) * mult * fat
                nat_t = ctx.get("nat_t")
                converts = u > 0 and (nat_t is None or nat_t > t_send + 7 * DAY) and rng.random() < min(0.6, u)
                disp, dur, tc = do_call(t_send, dec_id, app_ref, converts)
                res = {"mid": None, "final": None, "t": tc, "converts_at": (tc + min(6.0, float(rng.exponential(1.5))) * DAY) if converts else None,
                       "clicked": bool(converts), "works": bool(u > 0 and rng.random() < min(0.6, u * 6.0)), "pushes_back": False,
                       "disposition": disp, "duration": dur}
                mkt_times.append(tc)
            elif chn:
                res = send_promo(t_send, choice, chn, trig, dec_id, app_ref, ctx.get("nat_t"), mult, trig)
        log_action(action_id=aid, chosen_action=choice,
                   channel=("call" if choice == "agent_call" else chn) if executes else None,
                   category="promotional" if (res and (res.get("mid") or choice == "agent_call")) else None,
                   template=TEMPLATE[choice] if res else None, message_id=res["mid"] if res else None,
                   campaign_id=("policy_" + trig) if res else None, sent_at=res["t"] if res else None,
                   final_status=res["final"] if res else None, options_considered=dumps(opts), blocked_actions=dumps(blocked),
                   reason_codes=dumps(reasons), propensity=prop, needs_approval=bool(need_appr),
                   disposition=res.get("disposition") if res else None, call_duration_s=res.get("duration") if res else None,
                   **task, **kw)
        if res:
            res["action"], res["dec_id"] = choice, dec_id
        return res

    # ============================================================ application machinery
    apps = []
    kyc_mix = p["funnel.kyc_check_mix"]
    kyc_cum, kyc_names = cum(list(kyc_mix.values())), list(kyc_mix)
    cfgv = X.cfg.v
    mand = {"razorpay": None}

    def stage(app, st, t):
        if t >= END:
            return False
        prev = app["stage"]
        if prev is None:
            add(t, "record_created", "loan_origination", f"app:{app['ref']}:{st}",
                {"object": "application", "application_ref": app["ref"], "status": st, "kind": app["kind"]}, ch=app["channel"], cmp_=app["camp"])
        else:
            add(t, "record_status_changed", "loan_origination", f"app:{app['ref']}:{st}",
                {"object": "application", "application_ref": app["ref"], "from": prev, "to": st}, ch=app["channel"], cmp_=app["camp"])
        app["stage"], app["stage_t"] = st, t
        return True

    def new_app(t, kind, req, chn_, cmp2):
        cnt["app"] += 1
        app = dict(ref=f"APP{i:07d}-{cnt['app']:02d}", t0=t, kind=kind, stage=None, stage_t=t, req=req, sanc=None, disb=None, ten=None,
                   apr=None, fee=None, emi=None, band_dec=None, risk_b=None, rej=None, sanc_t=None, disb_t=None, dec_attr=None,
                   cause=None, channel=chn_, camp=cmp2, kyc_ok=(kind != "new"), aa_ok=False, aa_active=False, decided=False,
                   accepted=False, signed=False, manual=False, mandate_ok=False, path=None, max_dpd=None, prepay_m=None,
                   first90=None, label_final=False, true_def=None, hint=None, aa_row=None, dup=False, incr=False)
        apps.append(app)
        stage(app, "applied", t)
        return app

    def step_row(app, stype, ext, method, t0, t1, status, attempt, src, obj, reason=None, amt=None, pend="pending"):
        if t0 >= END:
            return None
        cnt["step"] += 1
        sid = f"STP{i:07d}-{cnt['step']:03d}"
        done = t1 is not None and t1 < END
        add(t0, "record_created", src, f"{obj}:{ext}:{pend}",
            {"object": obj, "external_id": ext, "application_ref": app["ref"], "status": pend, "method": method, "attempt": attempt}, ch=app["channel"])
        if done:
            add(t1, "record_status_changed", src, f"{obj}:{ext}:{status}",
                {"object": obj, "external_id": ext, "application_ref": app["ref"], "from": pend, "to": status, "reason": reason}, ch=app["channel"])
        row = dict(step_id=sid, application_ref=app["ref"], unit_id=unit, step_type=stype, external_id=ext, method=method,
                   status=status if done else pend, attempt_no=attempt, started_at=t0, completed_at=t1 if done else None,
                   reason_category=reason if done else None, amount_band=amt)
        STEP_ROWS.append(row)
        return row

    def ext_id(stype):
        return f"{stype}_{i:07d}_{cnt['step'] + 1:03d}"

    # ------------------------------------------------------------ steps
    def do_kyc(app, t, resumed):
        if app["kyc_ok"]:
            return "ok", t
        if t >= END:
            return "end", t
        if not resumed:
            pp = float(np.clip(p["funnel.p_proceed_kyc"] * (0.7 + 0.6 * urgency) + (0.1 if existing else 0.0), 0.05, 0.97))
            if rng.random() > pp:
                return "stall", t
        t += float(rng.uniform(60, 600))
        for att in (1, 2):
            if t >= END:
                return "end", t
            meth = pick(rng, kyc_cum, kyc_names) if att == 1 or rng.random() > 0.3 else "manual_document"
            if att == 1:
                stage(app, "docs_pending", t)
            dur = LN(p["funnel.kyc_minutes"][meth], p["funnel.time_sigma"]) * 60.0
            if att == 1:
                pass_p = p["funnel.kyc_first_pass"] * (1 - 0.5 * (kyc_fr - 0.25)) + 0.15 * (doc_q - 0.7)
            else:
                pass_p = p["funnel.kyc_retry_success"] * (1 - 0.3 * (kyc_fr - 0.25))
            if fraud:
                pass_p *= 0.7
            ok = rng.random() < float(np.clip(pass_p, 0.05, 0.97))
            ext = ext_id("kyc")
            if ok:
                step_row(app, "kyc", ext, meth, t, t + dur, "verified", att, "kyc", "kyc_check")
                app["kyc_ok"] = True
                return "ok", t + dur
            rs = p["funnel.kyc_fail_reasons"]
            reason = pick(rng, cum(list(rs.values())), list(rs))
            step_row(app, "kyc", ext, meth, t, t + dur, "expired" if reason == "timeout" else "failed", att, "kyc", "kyc_check", reason)
            t += dur
            if att == 1 and rng.random() < p["funnel.kyc_retry_prob"]:
                t += LN(4, 1.0) * 3600.0
                continue
            return "stall", t
        return "stall", t

    def do_consent(app, t, resumed):
        if app["aa_ok"]:
            return "ok", t
        if t >= END:
            return "end", t
        t += float(rng.uniform(30, 600))
        if not app["aa_active"]:
            ext = ext_id("aa")
            dur = LN(3, 1.0) * 60.0
            if rng.random() < p["funnel.p_consent"]:
                row = step_row(app, "aa_consent", ext, "account_aggregator", t, t + dur, "active", 1, "account_aggregator", "aa_consent")
                app["aa_active"], app["aa_row"] = True, row
                aa_active[0] = True
                t += dur
            else:
                rs = p["funnel.aa_fail_reasons"]
                reason = pick(rng, cum(list(rs.values())), list(rs))
                st = {"denied": "rejected", "bank_timeout": "expired", "technical": "failed"}[reason]
                step_row(app, "aa_consent", ext, "account_aggregator", t, t + dur, st, 1, "account_aggregator", "aa_consent", reason)
                return "stall", t + dur
        else:
            aa_active[0] = True
        for att in (1, 2):
            if t >= END:
                return "end", t
            ext = ext_id("aa")
            dur = LN(2, 1.0) * 60.0
            ok = rng.random() < (p["funnel.p_fetch_ok"] if att == 1 else p["funnel.fetch_retry_success"])
            if ok:
                step_row(app, "aa_fetch", ext, "account_aggregator", t, t + dur, "completed", att, "account_aggregator", "aa_fetch")
                t += dur
                app["aa_ok"] = True
                stage(app, "in_review", t)
                if app["aa_row"] is not None and rng.random() < p["funnel.aa_revoke_prob"]:
                    tr = t + float(rng.uniform(1, 60)) * DAY
                    if tr < END:
                        add(tr, "record_status_changed", "account_aggregator", f"aa_consent:{app['aa_row']['external_id']}:revoked",
                            {"object": "aa_consent", "external_id": app["aa_row"]["external_id"], "application_ref": app["ref"], "from": "active", "to": "revoked"})
                        app["aa_row"]["status"], app["aa_row"]["completed_at"] = "revoked", tr
                return "ok", t
            reason = "bank_timeout" if rng.random() < 0.6 else "technical"
            step_row(app, "aa_fetch", ext, "account_aggregator", t, t + dur, "failed", att, "account_aggregator", "aa_fetch", reason)
            t += dur
            if att == 1 and rng.random() < p["funnel.fetch_retry_prob"]:
                t += LN(10, 1.0) * 60.0
                continue
            return "stall", t
        return "stall", t

    def do_decision(app, t, resumed):
        if app["decided"]:
            return "ok", t
        if t >= END:
            return "end", t
        manual = rng.random() < p["funnel.refer_share"]
        dt = float(rng.uniform(*p["funnel.manual_review_days"])) * DAY if manual else LN(p["funnel.decision_minutes_auto"], 1.0) * 60.0
        td_ = t + dt
        if td_ >= END:
            return "end", t
        pa = p["funnel.approve_by_band"][band - 1] + (0.15 if app["kind"] != "new" else 0.0)
        if fraud and rng.random() < 0.8:
            ap, fr_reason = False, "fraud"
        else:
            ap, fr_reason = (rng.random() < p["funnel.refer_approve"]) if manual else (rng.random() < min(0.95, pa)), None
        app["decided"] = True
        app["band_dec"] = "refer" if manual else ("approve" if ap else "decline")
        app["risk_b"] = f"band_{band}"
        add(td_, "record_status_changed", "loan_origination", f"riskband:{app['ref']}:{band}",
            {"object": "risk_band", "application_ref": app["ref"], "band": f"band_{band}"})
        if not ap:
            rj = p["funnel.reject_reasons"]
            app["rej"] = fr_reason or pick(rng, cum(list(rj.values())), list(rj))
            stage(app, "rejected", td_)
            return "reject", td_
        full = rng.random() < 0.7
        sanc = app["req"] if full else float(max(5000.0, round(app["req"] * float(rng.uniform(0.5, 0.95)), -2)))
        sanc = float(np.clip(sanc, lo_c, hi_c))
        k_ = int(np.clip(round(2.4 * math.log10(max(sanc, 5000) / 5000.0) + float(rng.normal(0, 0.8))), 0, 6))
        ten = int(p["population.tenure_choices"][k_])
        apr = float(p["population.apr_by_band"][band - 1] + rng.uniform(-0.02, 0.02))
        fee = float(p["population.fee_pct_by_band"][band - 1])
        r_ = apr / 12.0
        emi = sanc * r_ / (1 - (1 + r_) ** (-ten))
        app.update(sanc=sanc, ten=ten, apr=apr, fee=fee, emi=emi, sanc_t=td_)
        stage(app, "approved", td_)
        send_service(td_ + float(rng.uniform(60, 900)), svc_channel(), "key_fact_statement", "regulatory", app["ref"])
        return "ok", td_

    def do_offer(app, t, resumed):
        if app["accepted"]:
            return "ok", t
        if t >= END:
            return "end", t
        acc = (p["funnel.accept_base"] - p["funnel.accept_ratio_slope"] * (1 - app["sanc"] / app["req"])
               - p["funnel.accept_apr_slope"] * max(0.0, app["apr"] - 0.28) - p["funnel.accept_shop_slope"] * (shop - 0.3))
        if not resumed and rng.random() > float(np.clip(acc, 0.05, 0.95)):
            return "stall", t
        t_acc = t + LN(p["funnel.accept_hours"], 1.0) * 3600.0 if not resumed else t + float(rng.uniform(300, 7200))
        if t_acc >= END:
            return "end", t
        session_events(t_acc - 240, n_pages() + 1, True, anon0, chan, None, features=("offer_page",), login=True)
        app["accepted"] = True
        stage(app, "offer_accepted", t_acc)
        return "ok", t_acc

    def do_sign(app, t, resumed):
        if t >= END:
            return "end", t
        if not app["signed"]:
            t += float(rng.uniform(60, 900))
            ext = ext_id("esign")
            dur = LN(20, 0.9) * 60.0
            if rng.random() < p["funnel.esign_success"]:
                step_row(app, "esign", ext, "docusign", t, t + dur, "signed", 1, "docusign", "esign", pend="created")
                add(t + 20, "record_status_changed", "docusign", f"esign:{ext}:sent", {"object": "esign", "external_id": ext, "application_ref": app["ref"], "from": "created", "to": "sent"})
                t += dur
                app["signed"] = True
                stage(app, "signed", t)
            else:
                st = "declined" if rng.random() < 0.7 else "voided"
                step_row(app, "esign", ext, "docusign", t, t + dur, st, 1, "docusign", "esign", pend="created")
                return "stall", t + dur
        if t >= END:
            return "end", t
        if app["mandate_ok"] or app["manual"]:
            return "ok", t
        me = p["funnel.mandate_error_mix"]
        am = p["repayment.autopay_methods"]
        meth = pick(rng, cum(list(am.values())), list(am))
        mb = band_amount(X, app["emi"] * 2.0)
        for att in (1, 2):
            if t >= END:
                return "end", t
            t += float(rng.uniform(60, 900))
            ext = ext_id("mandate")
            dur = LN(12, 1.0) * 60.0
            ps = (p["funnel.mandate_first_success"] if att == 1 else p["funnel.mandate_retry_success"]) * (1 - 0.25 * (mfp - 0.2))
            if rng.random() < ps:
                step_row(app, "mandate", ext, meth, t, t + dur, "active", att, "razorpay", "mandate", amt=mb, pend="created")
                mand["razorpay"] = True
                app["mandate_ok"], app["mandate_meth"] = True, meth
                return "ok", t + dur
            reason = pick(rng, cum(list(me.values())), list(me))
            step_row(app, "mandate", ext, meth, t, t + dur, "failed" if reason == "technical" else "rejected", att, "razorpay", "mandate",
                     reason, amt=mb, pend="created")
            t += dur
            if att == 1 and rng.random() < p["funnel.mandate_retry_prob"]:
                continue
            break
        if rng.random() < p["funnel.mandate_fail_proceed"]:
            app["manual"] = True
            return "ok", t
        return "stall", t

    def do_disburse(app, t, resumed):
        if t >= END:
            return "end", t
        if not resumed and rng.random() > p["funnel.p_disburse"]:
            return "stall", t
        td_ = t + LN(p["funnel.disburse_hours"], p["funnel.disburse_sigma"]) * 3600.0
        if td_ >= END:
            return "end", t
        app["disb"], app["disb_t"] = app["sanc"], td_
        stage(app, "disbursed", td_)
        run_loan(app, td_)
        return "ok", td_

    STALL_C = {"kyc": ["nudge", "agent_call"], "consent": ["nudge", "agent_call"], "offer": ["nudge", "agent_call", "fee_waiver", "offer"],
               "sign": ["nudge", "agent_call", "fee_waiver"], "disburse": ["nudge", "agent_call"]}

    def handle_stall(app, key, t_stall, cands, value, days=None, nat_t="draw", trig="stall", extra=None):
        if isinstance(nat_t, str):
            nat_t = None
            if rng.random() < p["funnel.abandon_return_7d"]:
                nat_t = t_stall + (min(6.9, float(rng.exponential(p["funnel.abandon_return_mean_days"]))) + 0.02) * DAY
        clicked = None
        for d in (days or p["messaging.stall_decision_days"]):
            td_ = t_stall + d * DAY
            if nat_t is not None and nat_t < td_:
                break
            if td_ >= END:
                break
            res = decide(td_, trig, cands, dict(app=app, step=key, nat_t=nat_t, mult_key=key, value=value, **(extra or {})))
            if not res:
                continue
            if res.get("clicked") and res.get("dec_id"):
                clicked = (res["dec_id"], res["t"])
            if res.get("pushes_back"):
                nat_t = None
                if reacts_badly and rng.random() < 0.15:
                    open_case("complaint", res["t"] + float(rng.uniform(1, 4)) * DAY, res["t"] + float(rng.uniform(6, 15)) * DAY)
            if res.get("converts_at") is not None and res["converts_at"] < END:
                return res["converts_at"], "incremental", res, clicked
        if nat_t is not None and nat_t < END:
            return nat_t, "natural", None, clicked
        return None, None, None, clicked

    def run_journey(app, t):
        steps = [("kyc", do_kyc), ("consent", do_consent), ("decision", do_decision), ("offer", do_offer), ("sign", do_sign), ("disburse", do_disburse)]
        k, resumed, n_st = 0, False, 0
        while k < len(steps):
            key, fn = steps[k]
            stt, t = fn(app, t, resumed)
            if stt == "ok":
                k, resumed = k + 1, False
                continue
            if stt in ("reject", "end"):
                break
            n_st += 1
            if n_st > 3:
                break
            t2, how, res, clk = handle_stall(app, key, t, STALL_C[key], app["sanc"] or app["req"])
            if t2 is None:
                break
            resumed = True
            if clk and 0 <= t2 - clk[1] <= 7 * DAY:
                app["dec_attr"] = clk[0]
            if how == "incremental":
                app["incr"] = True
                if app["cause"] is None:
                    app["cause"] = res["dec_id"]
            t = t2
            if t >= END:
                break
            session_events(t, n_pages() + 1, True, anon0, chan, None, features=("resume_application",), login=True)
        aa_active[0] = False

    def start_app(t, kind, req, chn_, cmp2, cause=None, attr=None, incr=False, dup_ok=True):
        app = new_app(t, kind, req, chn_, cmp2)
        app["cause"], app["dec_attr"], app["incr"] = cause, attr, incr
        session_events(t - 180, n_pages() + 1, True, anon0, chn_, cmp2, features=("apply_form",), login=existing or rng.random() < p["sessions.login_prob"])
        if kind == "new":
            for chn in ("email", "sms", "whatsapp"):
                if cons[chn] == "unknown" and not do_not_market and rng.random() < p["population.optin_at_application_prob"]:
                    set_consent(chn, "granted", t + 30)
            t_dup = t + float(rng.uniform(1, 48)) * 3600.0
            if dup_ok and t_dup < END and rng.random() < p["funnel.duplicate_application"] * (0.5 + 2.0 * shop):
                a2 = new_app(t_dup, "new", req, chn_, cmp2)
                a2["dup"] = True
                noise_extra.append((None, "duplicate", dumps({"application_ref": a2["ref"], "duplicate_of": app["ref"]})))
        run_journey(app, t + float(rng.uniform(60, 300)))
        return app

    # ------------------------------------------------------------ loan, repayment, collections, top-up, win-back
    def topup_flow(t_el, loan_end, mandate_inactive=False):
        h = max(1e-4, p["repayment.topup_hazard_month"] * topup_pr * 2.0)
        t_nat = t_el + float(rng.exponential(1.0 / h)) * 30.4 * DAY
        if t_nat >= min(loan_end, END):
            t_nat = None
        t_s, how, res, clk = handle_stall(None, "topup", t_el, ["nudge", "offer", "agent_call"], 30000.0, nat_t=t_nat, trig="topup",
                                          extra={"mandate_inactive": mandate_inactive})
        if t_s is None or t_s >= END or t_s >= loan_end:
            return
        attr = clk[0] if (clk and 0 <= t_s - clk[1] <= 7 * DAY) else None
        start_app(t_s, "top_up", draw_amount(0.6), "in_app", None, cause=res["dec_id"] if how == "incremental" else None,
                  attr=attr, incr=(how == "incremental"), dup_ok=False)

    def winback_flow(t_close):
        wr = p["repayment.winback_return"]
        u = rng.random()
        mo = (rng.uniform(0.5, 6) if u < wr["m6"] else rng.uniform(6, 12) if u < wr["m12"] else rng.uniform(12, 24) if u < wr["m24"] else None)
        t_nat = t_close + mo * 30.4 * DAY if mo else None
        t_s, how, res, clk = handle_stall(None, "winback", t_close, ["nudge", "offer", "agent_call"], 30000.0, days=[30, 90, 180], nat_t=t_nat, trig="winback")
        if t_s is None or t_s >= END:
            return
        attr = clk[0] if (clk and 0 <= t_s - clk[1] <= 7 * DAY) else None
        start_app(t_s, "win_back", draw_amount(), "in_app", None, cause=res["dec_id"] if how == "incremental" else None,
                  attr=attr, incr=(how == "incremental"), dup_ok=False)

    def run_loan(app, t_d):
        cnt["loan"] += 1
        lid = f"LN{i:07d}-{cnt['loan']:02d}"
        n, apr, emi = app["ten"], app["apr"], app["emi"]
        manual = app["manual"]
        add(t_d, "record_created", "core_banking", f"loan:{lid}:active",
            {"object": "loan", "loan_id": lid, "application_ref": app["ref"], "status": "active"})
        send_service(t_d + float(rng.uniform(300, 3600)), svc_channel(), "loan_agreement_copy", "regulatory", app["ref"])
        loan = dict(loan_id=lid, application_ref=app["ref"], unit_id=unit, account_status="active", opened_at=t_d, closed_at=None,
                    closure_type=None, defaulted_at=None, tenure_band=band_tenure(X, n), disbursed_amount_band=band_amount(X, app["disb"]),
                    lender_band_latest=None)
        LOANS.append(loan)
        am = p["repayment.autopay_methods"]
        lm = app.get("mandate_meth") or pick(rng, cum(list(am.values())), list(am))
        mm = p["repayment.manual_methods"]
        mmeth = lambda: pick(rng, cum(list(mm.values())), list(mm))
        cancel_m = int(rng.integers(1, 7)) if (not manual and rng.random() < p["funnel.mandate_cancel_6m"]) else None
        prepay_m = None
        if n > 6 and rng.random() < min(0.6, p["repayment.prepay_share"] * prepay_pr / 0.25):
            prepay_m = int(rng.integers(6, n))
        c_m = int(rng.integers(1, n + 1)) if rng.random() < p["repayment.complaint_share"] else None
        amt_b = band_amount(X, emi)
        fe = p["repayment.fail_error_mix"]
        fe_cum, fe_names = cum(list(fe.values())), list(fe)
        day0 = math.floor(t_d / DAY) * DAY
        first_due = day0 + int(rng.integers(30, 45)) * DAY + 6 * 3600.0
        due_of = lambda m_: first_due + (m_ - 1) * 30.4 * DAY
        loan_end = due_of(n)
        # cooling-off exit
        if rng.random() < p["repayment.cooling_off_share"]:
            tc = t_d + float(rng.uniform(1, 3)) * DAY
            if tc < END:
                loan.update(account_status="closed", closed_at=tc, closure_type="foreclosed")
                add(tc, "record_status_changed", "core_banking", f"loan:{lid}:closed",
                    {"object": "loan", "loan_id": lid, "from": "active", "to": "closed", "closure_type": "foreclosed"})
            app["path"], app["max_dpd"], app["true_def"], app["label_final"] = [], 0, False, (t_d + 15 * 30.4 * DAY <= END)
            return
        stress_prev = float(rng.normal())
        zs_eff = zs + 0.5 * (mfp - 0.2)
        rho, rw, drift = p["repayment.rho"], p["repayment.risk_weight"], p["repayment.month_drift"]
        cure1, cure2 = p["repayment.missed_cure"]["d30_59"], p["repayment.missed_cure"]["d60_89"]
        path, streak, track, first90, def_t, max_dpd = [], 0, None, None, None, 0
        last_state, last_paid, topup_done, complained = 0, t_d, False, False
        closed_at, ctype, finished = None, None, True
        for m in range(1, n + 1):
            due = due_of(m)
            if due >= END:
                finished = False
                break
            if track is not None and due >= first90:
                finished = False
                break
            if prepay_m == m and track is None:
                closed_at, ctype = max(last_paid + DAY, due - float(rng.uniform(2, 20)) * DAY), "prepaid"
                finished = False
                break
            auto = (not manual) and not (cancel_m and m > cancel_m)
            if cancel_m and m == cancel_m + 1:
                add(due - 20 * DAY, "record_status_changed", "razorpay", f"mandate:{lid}:cancelled",
                    {"object": "mandate", "loan_id": lid, "from": "active", "to": "cancelled", "reason": "borrower_request"})
            for _ in range(int(rng.poisson(p["sessions.borrower_sessions_per_month"]))):
                session_events(due - float(rng.uniform(0, 30)) * DAY, n_pages(), True, anon0, "app", None, features=("emi_schedule",), login=True)
            send_service(due - 3 * DAY, svc_channel(), "emi_reminder", "regulatory", app["ref"], trig="emi_due")
            if auto:
                send_service(due - 1 * DAY, svc_channel(), "pre_debit_notice", "regulatory", app["ref"], trig="emi_due")
            eps = float(rng.normal())
            stress = rho * stress_prev + math.sqrt(1 - rho * rho) * eps
            stress_prev = stress
            lat = (stress + rw * zs_eff + drift * m + p["repayment.stress_offset"] + (0.5 if not auto else 0.0)) / math.sqrt(1 + rw * rw)
            if track is None and ((m > 1 and last_state != 0) or band >= 3):
                ctx = dict(app=app, step="emi", nat_t=None, mult_key="emi", value=emi * 12.0, mandate_inactive=not auto)
                res = decide(due - p["messaging.emi_nudge_days_before"] * DAY, "emi_due", ["emi_nudge"], ctx)
                if res and res.get("action") == "emi_nudge":
                    if res.get("works"):
                        lat -= p["messaging.emi_nudge_shift"] * (uu("emi_nudge", due) / 0.05)
                    if res.get("pushes_back"):
                        lat += 0.2
                        if reacts_badly and rng.random() < 0.25:
                            open_case("complaint", res["t"] + float(rng.uniform(1, 3)) * DAY, res["t"] + float(rng.uniform(5, 15)) * DAY)
            k = 3 if track is not None else int(np.searchsorted(X.cut, lat))
            err = (lambda: "mandate_inactive" if not auto else pick(rng, fe_cum, fe_names))

            def pay(att, status, t_, method, e=None):
                if t_ >= END:
                    return
                cnt["pay"] += 1
                pid = f"PAY{i:07d}-{cnt['pay']:03d}"
                EMI.append(dict(payment_id=pid, loan_id=lid, unit_id=unit, instalment_no=m, due_date=due, status=status, method=method,
                                amount_band=amt_b, created_at=t_, error_category=e, attempt_no=att))
                add(t_, "record_created", "razorpay" if method in ("upi_autopay", "emandate") else "core_banking", f"emi:{pid}:{status}",
                    {"object": "emi_payment", "payment_id": pid, "loan_id": lid, "instalment_no": m, "status": status, "method": method,
                     "error_category": e, "attempt": att})
                if status == "failed":
                    send_service(t_ + 600, svc_channel(), "emi_failed_notice", "transactional", app["ref"], trig="emi_due")
            paid_t, dpd = None, 0
            if k == 0:
                paid_t = due + float(rng.uniform(0, 4 * 3600)) if auto else due - float(rng.uniform(0, 2 * DAY))
                pay(1, "captured", paid_t, lm if auto else mmeth())
            elif k == 1:
                dpd = int(rng.integers(p["repayment.grace_days"][0], p["repayment.grace_days"][1] + 1))
                paid_t = due + dpd * DAY + float(rng.uniform(0, 0.5)) * DAY
                if auto:
                    pay(1, "failed", due + float(rng.uniform(0, 4 * 3600)), lm, err())
                    pay(2, "captured", paid_t, mmeth())
                else:
                    pay(1, "captured", paid_t, mmeth())
            elif k == 2:
                dpd = int(rng.integers(p["repayment.late_days"][0], p["repayment.late_days"][1] + 1))
                paid_t = due + dpd * DAY + float(rng.uniform(0, 0.5)) * DAY
                if auto:
                    pay(1, "failed", due + float(rng.uniform(0, 4 * 3600)), lm, err())
                    a_ = 2
                    if rng.random() < 0.5:
                        pay(2, "failed", due + 3 * DAY, lm, err())
                        a_ = 3
                    pay(a_, "captured", paid_t, mmeth())
                else:
                    pay(1, "captured", paid_t, mmeth())
            else:
                forced = track is not None
                if auto:
                    pay(1, "failed", due + float(rng.uniform(0, 4 * 3600)), lm, err())
                    if not forced:
                        pay(2, "failed", due + 3 * DAY, lm, err())
                if not forced:
                    u_ = rng.random()
                    if u_ < cure1:
                        dpd = int(rng.integers(30, 60))
                    elif u_ < cure1 + cure2:
                        dpd = int(rng.integers(60, 90))
                    else:
                        dpd = None
                    if dpd is not None:
                        paid_t = due + dpd * DAY + float(rng.uniform(0, 0.5)) * DAY
                        pay(3 if auto else 1, "captured", paid_t, mmeth())
                    else:
                        track, first90 = due, due + 90 * DAY
                        def_t = first90 + float(rng.uniform(*p["repayment.default_flag_delay_days"])) * DAY
                        dpd = 0
            if track is not None and paid_t is None:
                max_dpd = max(max_dpd, int((END - track) / DAY))
            else:
                max_dpd = max(max_dpd, dpd)
            path.append({"m": m, "s": ["on_time", "grace", "late", "missed"][k], "d": dpd if paid_t else None})
            if k >= 2:
                had_t = paid_t if paid_t is not None else None
                late_ivals.append((due, had_t))
                tc = due + float(rng.uniform(*p["repayment.collections_first_contact_days"])) * DAY
                if had_t is None or tc < had_t:
                    open_case("collections", tc, had_t)
                if not complained and rng.random() < p["repayment.complaint_share"] * p["repayment.complaint_late_mult"]:
                    complained = True
                    to_ = due + float(rng.uniform(*p["repayment.complaint_days"])) * DAY
                    open_case("complaint" if rng.random() < 0.6 else "dispute", to_, to_ + float(rng.uniform(3, 15)) * DAY)
            if c_m == m and not complained:
                complained = True
                to_ = due + float(rng.uniform(1, 20)) * DAY
                open_case("complaint" if rng.random() < 0.6 else "dispute", to_, to_ + float(rng.uniform(3, 15)) * DAY)
            if paid_t is not None:
                last_paid = max(last_paid, paid_t)
            last_state = k
            if k == 0:
                streak += 1
                if streak == p["repayment.topup_after_ontime"] and not topup_done and track is None and cnt["app"] < 5 and paid_t < END:
                    topup_done = True
                    topup_flow(paid_t + DAY, loan_end, mandate_inactive=not auto)
            else:
                streak = 0
        if finished and track is None:
            closed_at, ctype = last_paid + float(rng.uniform(1, 3)) * DAY, "matured"
        if closed_at is not None and closed_at >= END:
            closed_at, ctype = None, None
        if closed_at is not None:
            loan.update(account_status="closed", closed_at=closed_at, closure_type=ctype)
            add(closed_at, "record_status_changed", "core_banking", f"loan:{lid}:closed",
                {"object": "loan", "loan_id": lid, "from": "active", "to": "closed", "closure_type": ctype})
        defaulted_at = def_t if (def_t is not None and def_t < END) else None
        if defaulted_at is not None:
            loan.update(account_status="defaulted", defaulted_at=defaulted_at)
            add(defaulted_at, "record_status_changed", "core_banking", f"loan:{lid}:defaulted",
                {"object": "loan", "loan_id": lid, "from": "active", "to": "defaulted"})
        bl = band
        if defaulted_at is not None:
            bl = 4
        elif max_dpd >= 30:
            bl = min(4, band + 1)
        loan["lender_band_latest"] = f"band_{bl}"
        app["path"], app["max_dpd"] = path, max_dpd
        app["prepay_m"] = prepay_m if ctype == "prepaid" else None
        app["first90"] = first90 if (first90 is not None and first90 < END) else None
        app["label_final"] = bool(t_d + p_label_age * 30.4 * DAY <= END)
        app["true_def"] = bool(first90 is not None and first90 <= t_d + 365 * DAY and first90 < END)
        app["hint"] = sigmoid(-3.2 + 0.9 * zs_eff)
        if ctype in ("matured", "prepaid") and closed_at is not None and cnt["app"] < 5 and ctype and rng.random() < 1.0:
            winback_flow(closed_at)

    p_label_age = cfgv("labels.min_loan_age_months")

    # ============================================================ main flow
    linked = rng.random() < p["population.identify_link_prob"]
    add(created_t + 30, "identify", "trackflow", f"identify:{unit}", {"merged": anon0 if linked else None, "method": "phone_otp"}, anon=anon0, ch=chan)
    p_start = float(np.clip(p["population.p_start_application"][acq] * (0.7 + 0.6 * urgency), 0.05, 0.95))
    t_first, how0, res0, clk0 = None, None, None, None
    if rng.random() < p_start:
        t_first, how0 = created_t + min(3.0 * DAY, LN(0.04, 1.0) * DAY), "immediate"
    else:
        t_first, how0, res0, clk0 = handle_stall(None, "lead", created_t, ["nudge", "agent_call"] + (["offer"] if existing else []), req0,
                                                 days=p["messaging.lead_decision_days"], nat_t="draw", trig="lead")
    if t_first is not None and t_first < END:
        attr = clk0[0] if (clk0 and 0 <= t_first - clk0[1] <= 7 * DAY) else None
        start_app(t_first, "new", req0, chan, camp, cause=res0["dec_id"] if how0 == "incremental" else None, attr=attr, incr=(how0 == "incremental"))
    aa_active[0] = False

    # ============================================================ finalise rows
    for app in apps:
        st_t = app["stage_t"]
        A_ROWS.append(dict(
            application_ref=app["ref"], unit_id=unit, product_code="personal_loan", application_kind=app["kind"], created_at=app["t0"],
            channel=app["channel"], campaign_id=app["camp"], branch_code=None, stage=app["stage"], stage_changed_at=st_t,
            rejection_reason_category=app["rej"], requested_amount_band=band_amount(X, app["req"]),
            sanctioned_amount_band=band_amount(X, app["sanc"]) if app["sanc"] and app["sanc_t"] and app["sanc_t"] < END else None,
            disbursed_amount_band=band_amount(X, app["disb"]) if app["disb"] else None,
            sanction_date=app["sanc_t"] if app["sanc_t"] and app["sanc_t"] < END else None,
            disbursal_date=app["disb_t"] if app["disb_t"] and app["disb_t"] < END else None,
            decision_band=app["band_dec"], risk_band=app["risk_b"], decision_id=app["dec_attr"]))
        disb = bool(app["disb"])
        ATRUTH.append(dict(
            application_ref=app["ref"], unit_id=unit, kind="incremental" if app["incr"] else "natural", cause_decision_id=app["cause"],
            requested_amount=round(app["req"], 2), sanctioned_amount=round(app["sanc"], 2) if app["sanc"] else None,
            disbursed_amount=round(app["disb"], 2) if disb else None, apr=round(app["apr"], 4) if app["apr"] else None,
            tenure_months=app["ten"], fee_pct=app["fee"], emi_amount=round(app["emi"], 2) if app["emi"] else None,
            true_default=app["true_def"] if disb else None, label_final=bool(app["label_final"]) if disb else False,
            first_dpd90_at=app["first90"], pay_path=dumps(app["path"]) if app["path"] is not None else None,
            max_dpd=app["max_dpd"], prepay_month=app["prepay_m"], p_default_hint=app["hint"]))
    n_loans = len(LOANS)
    first_app = min((a["t0"] for a in apps), default=None)
    borrower = dict(
        unit_id=unit, person_key=pk, created_at=created_t, first_application_at=first_app, applications_count=len(apps), loans_count=n_loans,
        existing_customer=bool(existing), acquisition_channel=chan, device_class=dev, geo_tier=TIERS[tier],
        email_consent=cons["email"], sms_consent=cons["sms"], whatsapp_consent=cons["whatsapp"], do_not_market=bool(do_not_market),
        regime_first_seen="legacy_targeting" if created_t < REG2 else "randomised_holdout",
        holdout_group="control" if control else "treated", holdout_assigned_at=hold_assigned, holdout_share=X.share,
        holdout_strategy="random_hash", los_customer_ref=f"LOS{i:07d}", salesforce_lead_ref=lead_id, klaviyo_profile_ref=f"01K{i:07d}",
        razorpay_ref=f"cust_{i:07d}" if mand["razorpay"] else None,
        core_banking_ref=keyed_hash(X.secret, f"CIF{i}") if n_loans else None, trackflow_user_id=f"u_{i:07d}", email_key=email_key)
    truth = dict(
        unit_id=unit, hidden_type=ty, type_changes=dumps(type_changes), employment_type=emp, age=age, income_annual=round(income, 2),
        loan_to_income=round(lti, 4), true_risk_z=round(zs, 4), lender_band_true_noise=round(lnoise, 4), kyc_friction=round(kyc_fr, 4),
        doc_quality=round(doc_q, 4), urgency=round(urgency, 4), shopping_around=round(shop, 4), mandate_failure_propensity=round(mfp, 4),
        prepay_propensity=round(prepay_pr, 4), topup_propensity=round(topup_pr, 4), uplift_nudge=u_true["nudge"],
        uplift_agent_call=u_true["agent_call"], uplift_fee_waiver=u_true["fee_waiver"], uplift_offer=u_true["offer"],
        uplift_emi_nudge=u_true["emi_nudge"], reacts_badly=bool(reacts_badly), fraud_flag=bool(fraud), stacking=bool(stacking),
        shared_phone_with=shared_with, anon_ids=dumps(anon_ids), geo_tier=TIERS[tier])
    ev_rows = []
    EV.sort(key=lambda r: r[0])
    for n_, r in enumerate(EV):
        ev_rows.append((f"E{i:07d}-{n_:05d}",) + r)
    return dict(borrower=borrower, events=ev_rows, applications=A_ROWS, steps=STEP_ROWS, loans=LOANS, emi=EMI, cases=CASES, actions=ACT,
                person_truth=truth, app_truth=ATRUTH, noise_extra=noise_extra)
