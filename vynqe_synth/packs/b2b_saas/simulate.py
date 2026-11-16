"""B2B SaaS account simulator. One account at a time: hidden types first, then time forward, then visible rows.
Every decision draws its outcome from a FIXED uniform, so the planted uplift is exactly the probability shift
(counterfactual probabilities are stored in the hidden truth tables)."""
from __future__ import annotations
import json
import math
import numpy as np
import pandas as pd

from ...core.ids import keyed_hash, hash_u
from . import schemas as S

DAY = 86400.0
MONTH = 30.4375 * DAY
EDGES_NAMES = S.BANDS_ARR


def expit(x):
    return 1.0 / (1.0 + np.exp(-x))


def logit(p):
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def pick(rng, mapping):
    keys = list(mapping)
    p = np.array([mapping[k] for k in keys], float)
    return keys[int(rng.choice(len(keys), p=p / p.sum()))]


def band(x, edges):
    i = int(np.searchsorted(edges, x, side="right")) - 1
    return EDGES_NAMES[max(0, min(i, len(EDGES_NAMES) - 1))]


def iso(t):
    return None if t is None else pd.Timestamp(t, unit="s", tz="UTC").isoformat()


class Ctx:
    pass


def prospect_draw(rng, X):
    c = X.cfg
    ptype = pick(rng, c.v("population.prospect_types"))
    fit = float(rng.beta(2.5, 2.5))
    src = pick(rng, c.v("population.source_mix"))
    comp = bool(rng.random() < c.v("population.competitor_in_deal") or src == "competitor_displacement")
    lock = "none"
    if comp:
        lock = pick(rng, c.v("population.incumbent_lock_in"))
    if ptype == "locked_in":
        comp = True
        lock = "hard" if rng.random() < 0.6 else "soft"
    m = c.v("population.prospect_intent_mult")[ptype]
    lockf = {"none": 1.15, "soft": 0.85, "hard": 0.5}[lock]
    f = dict(mql=m ** 0.8 * (0.5 + fit), sql=m ** 0.6 * (0.5 + fit), opp=m ** 0.4,
             win=c.v("population.source_win_mult")[src] * m ** 0.3 * (0.4 + 1.2 * fit) * lockf)
    return dict(ptype=ptype, fit=fit, src=src, comp=comp, lock=lock, f=f)


def churn_components(rng, X, seg, ctype):
    """Latent log-odds shifts for one renewal cycle (before the segment offset)."""
    c = X.cfg
    shift = c.v("population.type_churn_shift")[ctype]
    decay = float(rng.beta(1.5, 5.0))
    left = float(rng.random() < 1 - math.exp(-c.v("population.champion_exit_per_year") * float(rng.lognormal(0, 0.5))))
    sev = float(rng.random() < 0.15)
    inactive = float(rng.random() > c.v("retention.onboarding_activation")[ctype])
    integ = float(rng.random() < c.v("retention.integration_share"))
    return shift, decay, left, sev, inactive, integ


def churn_logit(X, comp, disc=0.0):
    c = X.cfg
    shift, decay, left, sev, inactive, integ = comp
    return (shift + c.v("retention.decay_churn_lift") * decay + c.v("retention.champion_churn_lift") * left
            + c.v("retention.ticket_churn_lift") * sev + 1.0 * inactive + 0.3 * disc
            + math.log(1 - c.v("retention.integration_churn_cut")) * integ)


def build_context(cfg, seed, n_base, n_new):
    X = Ctx()
    X.cfg, X.seed, X.n_base, X.n_new, X.n_total = cfg, seed, n_base, n_new, n_base + n_new
    X.start = pd.Timestamp(cfg.v("run.start_date"), tz="UTC")
    X.E0 = X.start.timestamp()
    X.T = int(cfg.v("run.n_days"))
    X.END = X.E0 + X.T * DAY
    X.reg2 = X.E0 + cfg.v("run.regime2_day") * DAY
    X.secret = cfg.v("run.hash_secret").encode()
    days = pd.date_range(X.start, periods=X.T, freq="D")
    g = cfg.v("population.lead_growth_per_year")
    seas = np.array([1.1, 1.1, 1.15, 1.0, 1.0, 1.0, 0.9, 0.85, 1.05, 1.1, 1.05, 0.8])[days.month - 1]
    w = (1 + g * np.arange(X.T) / 365.0) * seas
    w[days.weekday >= 5] *= 0.35
    X.arr_cdf = np.cumsum(w) / w.sum()
    cal = np.array(cfg.v("usage.weekday_mult"))[days.weekday].astype(float)
    for a, b in cfg.v("usage.holiday_weeks"):
        m = (days >= pd.Timestamp(a, tz="UTC")) & (days <= pd.Timestamp(b, tz="UTC"))
        cal[m] *= cfg.v("usage.holiday_mult")
    cal[days.day >= days.days_in_month - 2] *= cfg.v("usage.month_end_lift")
    X.cal = cal
    X.dow = days.weekday.to_numpy()
    X.hour_w = np.array(cfg.v("sessions.hour_weights"), float)
    X.hour_w /= X.hour_w.sum()
    X.edges = cfg.v("population.acv_band_edges")
    # normalisers for the funnel factors, by Monte Carlo
    r = np.random.default_rng(12345)
    fs = [prospect_draw(r, X)["f"] for _ in range(20000)]
    A = {k: np.array([f[k] for f in fs]) for k in ("mql", "sql", "opp", "win")}
    # means are taken over the population that actually reaches each stage, so the chain averages hold
    X.fmean = {"mql": float(A["mql"].mean()),
               "sql": float((A["mql"] * A["sql"]).mean() / A["mql"].mean()),
               "opp": float((A["mql"] * A["sql"] * A["opp"]).mean() / (A["mql"] * A["sql"]).mean()),
               "win": float((A["mql"] * A["sql"] * A["opp"] * A["win"]).mean() / (A["mql"] * A["sql"] * A["opp"]).mean())}
    # per-segment churn offsets so the average voluntary churn hits the target
    X.churn_off, X.inv_exp = {}, {}
    ctypes = cfg.v("population.customer_types")
    target_all = cfg.v("retention.annual_churn")
    for seg in S.SEGMENTS:
        # expected involuntary churn per year for this segment (analytic), taken out of the target
        card = cfg.v("subscription.card_share")[seg]
        ann = cfg.v("subscription.annual_share")[seg]
        pf = cfg.v("billing.card_fail_rate")
        rec = 1 - (1 - cfg.v("billing.hard_decline_share")) * (1 - (1 - cfg.v("billing.retry_recover_each")) ** len(cfg.v("billing.retry_days")))
        rec = rec + (1 - rec) * cfg.v("billing.customer_fix_prob")
        # hard decline share is recovered only by the customer fix
        inv = card * (ann * 1 + (1 - ann) * 12) * pf * (1 - rec)
        X.inv_exp[seg] = inv
        tgt = max(0.01, target_all[seg] - inv)
        comps = [churn_components(r, X, seg, pick(r, ctypes)) for _ in range(6000)]
        base = np.array([churn_logit(X, k) for k in comps])
        lo, hi = -8.0, 4.0
        for _ in range(40):
            mid = (lo + hi) / 2
            if expit(base + mid).mean() > tgt:
                hi = mid
            else:
                lo = mid
        X.churn_off[seg] = (lo + hi) / 2
    return X


# --------------------------------------------------------------------------------------------------------------
def simulate_account(i, X):
    cfg = X.cfg
    v = cfg.v
    rng = np.random.default_rng([X.seed, 1, i])
    E0, END, T = X.E0, X.END, X.T
    aid = f"A{i:07d}"
    kind = "base" if i < X.n_base else "new"
    seg = pick(rng, v("population.segment_mix"))
    industry = v("population.industry_bands")[int(rng.choice(5, p=v("population.industry_probs")))]
    region = pick(rng, v("population.region_probs"))
    emp = v("population.employee_bands")[seg][int(rng.integers(2))]
    P = prospect_draw(rng, X)
    src = P["src"]
    ctype = pick(rng, v("population.customer_types"))
    acv = float(v("population.acv_median_usd")[seg] * rng.lognormal(0, v("population.acv_sigma")[seg]))
    sc = v("population.seats_clip")[seg]
    seats0 = int(np.clip(round(v("population.seats_median")[seg] * rng.lognormal(0, v("population.seats_sigma"))), sc[0], sc[1]))
    is_test = bool(rng.random() < v("noise.test_account_share"))
    reacts_badly = bool(rng.random() < v("policy.reacts_badly_share"))
    champ_hazard = v("population.champion_exit_per_year") / 12 * float(rng.lognormal(0, 0.5))
    budget_m = int(rng.choice(np.arange(1, 13), p=np.array([1.4, 1, 1, 1.1, 0.9, 1, 0.8, 0.8, 1.1, 1.2, 1, 1.3]) / 12.6))
    headroom = float(rng.beta(2, 4))
    integ = bool(rng.random() < v("retention.integration_share") + (0.1 if ctype == "power" else 0))
    named_csm = bool(rng.random() < v("population.named_csm_share")[seg])
    strategic = bool(seg == "ENT" and rng.random() < 0.5 or rng.random() < 0.01)
    decay_rate = float(rng.beta(1.5, 5.0))
    pay_card = bool(rng.random() < v("subscription.card_share")[seg])
    annual = bool(rng.random() < v("subscription.annual_share")[seg])
    term_months = 12
    if seg == "ENT" and rng.random() < v("subscription.term_months_ent_multi"):
        term_months = 24
    interval = "annual" if annual else "monthly"
    plan = v("subscription.plans")[seg][int(rng.integers(2))]
    auto_renew = bool(rng.random() < v("subscription.auto_renew")[seg])
    holdout = "control" if hash_u(v("run.holdout_salt"), aid) < v("run.holdout_share") else "treated"
    dup_id = f"A{X.n_total + i:07d}" if rng.random() < v("noise.duplicate_account_share") else None
    sec = X.secret
    seg_edges = X.edges
    uplift_p = v("policy.uplift_prospect")[P["ptype"]]
    uplift_c = v("policy.uplift_customer")[ctype]
    scale = v("policy.decision_scale")
    hour_cdf = np.cumsum(X.hour_w)

    # ---------------- outputs
    ev, contacts, opps, subs, invs, acts, usage = [], [], [], [], [], [], []
    optruth, noise_extra = [], []
    cnt = {"e": 0, "c": 0, "o": 0, "s": 0, "i": 0, "a": 0, "t": 0, "m": 0, "x": 0}
    st = {"pre": kind == "new", "won": None}

    def nid(k, pref):
        cnt[k] += 1
        return f"{pref}{i:07d}-{cnt[k]:03d}"

    def hash_email(local, personal):
        return keyed_hash(sec, f"{local}.{i}@{'mail.example' if personal else f'acct{i}.example'}")

    def E(t, et, src_sys, props, person=None, anon=None, ch=None, camp=None, consent=None, sid=None):
        if t is None or t < E0 or t >= END:
            return
        cnt["e"] += 1
        eid = f"E{i:07d}-{cnt['e']:05d}"
        unit = aid
        if st["pre"] and dup_id and rng.random() < v("noise.duplicate_event_share") and et != "decision_made":
            unit = dup_id
        if sid is None:
            o = props.get("object")
            sid = f"{o}:{props.get('id')}:{props.get('to') or props.get('status')}"
        ev.append((eid, float(t), et, src_sys, sid, person, anon, unit, ch, camp, consent, props, aid))

    # ---------------- contacts
    people = []

    def mk_contact(role, t_first, lead=False, user=False, optin=None):
        j = len(people)
        personal = bool(rng.random() < v("population.personal_email_share"))
        pk = hash_email(f"p{j}", personal)
        if optin is None:
            optin = v("messaging.optin_at_form") if (lead and src in ("inbound", "event", "referral")) else v("messaging.consent_initial")["granted"] * 0.6
        u = rng.random()
        init = "granted" if u < optin else ("withdrawn" if u > 0.985 else "unknown")
        tl = [(t_first, init)] if init != "unknown" else []
        if init == "granted" and rng.random() < v("messaging.unsub_rate") * 40:
            tl.append((t_first + float(rng.uniform(20, 400)) * DAY, "withdrawn"))
        c = dict(pk=pk, ref=f"C{i:07d}-{j:02d}", role=role, personal=personal, t_first=t_first, left=None, consent=tl,
                 lead=lead, user=user, seniority=pick(rng, {"ic": 0.35, "manager": 0.3, "director": 0.2, "vp": 0.1, "c_level": 0.05}),
                 anon=None, lead_info=None, wrong=None, other=None)
        people.append(c)
        for t, s_ in tl:
            t = max(t, E0 + 5) if t_first < E0 else t
            E(t, "consent_change", "hubspot" if src in ("inbound", "event", "referral") else "salesforce",
              {"object": "consent", "id": c["pk"][:10], "channel": "email", "purpose": "marketing", "status": s_},
              person=pk, consent=s_, sid=f"consent:{pk[:12]}:{int(t)}:{s_}")
        return c

    def consent_at(c, t):
        s_ = "unknown"
        for tt, ss in c["consent"]:
            if tt <= t:
                s_ = ss
        return s_

    # ---------------- guards and decisions
    iv = {"opp": [], "ticket": [], "legal": [], "renew": [], "payfail": []}
    touches = []
    act_times = []

    def in_iv(k, t):
        return any(a <= t < b for a, b in iv[k])

    def guard(action, t):
        r = []
        champ = people[0] if people else None
        if action == "email":
            cs = consent_at(champ, t) if champ else "unknown"
            if cs in ("withdrawn", "denied"):
                r.append("no_consent")
            elif cs == "unknown":
                r.append("unknown_consent")
            if in_iv("opp", t):
                r.append("open_opportunity")
            if in_iv("ticket", t):
                r.append("open_ticket")
            if in_iv("renew", t):
                r.append("renewal_within_14d")
        if action == "discount":
            if in_iv("ticket", t):
                r.append("open_ticket")
            if in_iv("renew", t):
                r.append("renewal_within_14d")
        if action == "rep_outreach" and any(t - 7 * DAY <= x < t for x in act_times):
            r.append("rep_engaged")
        if action == "csm_task" and not named_csm:
            r.append("capacity_full")
        if action == "exec_call" and acv < v("policy.capacity")["exec_call_arr_floor"]:
            r.append("approval_limit")
        if action != "csm_task" and in_iv("legal", t):
            r.append("in_legal_review")
        if in_iv("payfail", t) and action in ("email", "discount"):
            r.append("payment_failed")
        if action != "csm_task" and sum(1 for x in touches if t - v("messaging.frequency_cap_days") * DAY <= x < t) >= v("messaging.frequency_cap_n"):
            r.append("frequency_cap")
        return r

    CANDS = {"lead_stall": ["email", "rep_outreach"], "opp_stall": ["email", "rep_outreach", "discount", "exec_call"],
             "onboarding": ["email", "csm_task"], "risk": ["email", "rep_outreach", "discount", "exec_call", "csm_task"],
             "expansion": ["email", "rep_outreach", "discount", "csm_task"], "winback": ["email", "rep_outreach", "discount"]}

    def message_events(t, mid, camp, person):
        sys_ = "klaviyo"
        E(t, "message_status", sys_, {"object": "message", "id": mid, "status": "sent", "channel": "email"}, person=person, ch="email", camp=camp)
        if rng.random() < v("messaging.bounce_rate"):
            E(t + 30, "message_status", sys_, {"object": "message", "id": mid, "status": "bounced", "channel": "email"}, person=person, ch="email", camp=camp)
            return "bounced"
        E(t + 60, "message_status", sys_, {"object": "message", "id": mid, "status": "delivered", "channel": "email"}, person=person, ch="email", camp=camp)
        last = "delivered"
        if rng.random() < v("messaging.open_rate"):
            E(t + float(rng.uniform(600, 86400)), "message_status", sys_, {"object": "message", "id": mid, "status": "opened", "channel": "email"}, person=person, ch="email", camp=camp)
            last = "opened"
            if rng.random() < v("messaging.click_rate") / v("messaging.open_rate"):
                E(t + float(rng.uniform(700, 90000)), "message_status", sys_, {"object": "message", "id": mid, "status": "clicked", "channel": "email"}, person=person, ch="email", camp=camp)
                last = "clicked"
        return last

    def notice(t, trig, template, cat="regulatory"):
        if t < E0 or t >= END:
            return
        did = nid("a", "N")
        mid = nid("m", "M")
        pk = people[0]["pk"] if people else None
        last = message_events(t, mid, f"policy_{trig}", pk)
        acts.append(dict(action_id=did, unit_id=aid, person_key=pk, opp_id=None, record_kind="transactional",
                         regime="legacy_targeting" if t < X.reg2 else "randomised_holdout", decided_at=t, trigger=trig,
                         chosen_action="regulatory" if cat == "regulatory" else "transactional", channel="email", category=cat,
                         template=template, message_id=mid, campaign_id=f"policy_{trig}", sent_at=t, final_status=last,
                         options_considered=None, blocked_actions=None, reason_codes=None, propensity=None, expected_value=None,
                         model_versions=None, rule_version=None, needs_approval=False, in_holdout=False, holdout_group=None,
                         task_id=None, task_target=None, task_status=None, task_due_at=None, task_owner_id=None,
                         disposition=None, call_duration_s=None))

    def decide(trig, t, base_p, opp_id=None, fit=0.5, size=1.0):
        """Returns (action, delta, decision_id). Positive delta raises the probability of the good outcome."""
        if t < E0 or t >= END:
            return "do_nothing", 0.0, None
        regime = "legacy_targeting" if t < X.reg2 else "randomised_holdout"
        cands = CANDS[trig]
        blocked = {a: guard(a, t) for a in cands}
        blocked = {a: r for a, r in blocked.items() if r}
        allowed = [a for a in cands if a not in blocked]
        did = nid("a", "D")
        propensity, chosen, reasons, in_ho = None, "do_nothing", [], False
        if regime == "randomised_holdout" and holdout == "control":
            in_ho, reasons = True, ["in_holdout"]
        elif regime == "legacy_targeting":
            p_touch = expit(logit(v("policy.legacy_base_touch")) + v("policy.legacy_fit_slope") * (fit - 0.5)
                            + v("policy.legacy_arr_slope") * math.log(size))
            if allowed and rng.random() < p_touch:
                w = np.array([2.0 if (a in ("rep_outreach", "exec_call") and size > 1.5) else 1.0 for a in allowed])
                chosen = allowed[int(rng.choice(len(allowed), p=w / w.sum()))]
        else:
            if not allowed:
                propensity = 1.0
            elif rng.random() < v("policy.exploration_do_nothing"):
                propensity = v("policy.exploration_do_nothing")
            else:
                chosen = allowed[int(rng.integers(len(allowed)))]
                propensity = (1 - v("policy.exploration_do_nothing")) / len(allowed)
        for a, r in blocked.items():
            reasons += [f"{a}:{x}" for x in r]
        delta = 0.0
        if chosen != "do_nothing":
            up = (uplift_p if trig in ("lead_stall", "opp_stall") else uplift_c)[chosen]
            delta = (up + (v("policy.reacts_badly_effect") if reacts_badly else 0.0)) * scale[trig]
        pk = people[0]["pk"] if people else None
        E(t, "decision_made", "decision_service", {"object": "decision", "id": did, "trigger": trig, "chosen_action": chosen, "regime": regime}, person=pk)
        row = dict(action_id=did, unit_id=aid, person_key=pk, opp_id=opp_id, record_kind="decision" if regime == "randomised_holdout" else "legacy_touch",
                   regime=regime, decided_at=t, trigger=trig, chosen_action=chosen, channel=None, category="promotional" if chosen != "do_nothing" else None,
                   template=None, message_id=None, campaign_id=None, sent_at=None, final_status=None,
                   options_considered=json.dumps(cands), blocked_actions=json.dumps(blocked) if blocked else None,
                   reason_codes=json.dumps(reasons) if reasons else None, propensity=propensity, expected_value=None, model_versions=None,
                   rule_version=v("states.rule_version") if regime == "randomised_holdout" else None,
                   needs_approval=bool(chosen in ("discount", "exec_call")), in_holdout=in_ho, holdout_group=holdout if regime == "randomised_holdout" else None,
                   task_id=None, task_target=None, task_status=None, task_due_at=None, task_owner_id=None, disposition=None, call_duration_s=None)
        if chosen != "do_nothing":
            touches.append(t)
            ts = t + float(rng.uniform(300, 4 * 3600))
            if chosen == "email":
                mid = nid("m", "M")
                row.update(channel="email", message_id=mid, campaign_id=f"{'legacy' if regime.startswith('leg') else 'policy'}_{trig}", sent_at=ts,
                           template=f"{trig}_email", final_status=message_events(ts, mid, f"policy_{trig}", pk))
            else:
                tid = nid("t", "T")
                target = "csm_cta" if chosen == "csm_task" else "crm_task"
                sd = rng.random()
                row.update(task_id=tid, task_target=target, channel="call" if chosen in ("rep_outreach", "exec_call") else "in_app",
                           task_due_at=t + float(rng.uniform(1, 5)) * DAY, task_owner_id=f"rep_{int(rng.integers(1, 25)):02d}",
                           task_status="done" if sd < 0.72 else ("ignored" if sd < 0.9 else "overridden"), sent_at=ts)
                if chosen == "csm_task":
                    E(ts, "record_created", "gainsight", {"object": "cta", "id": tid, "to": "new", "cta_type": {"onboarding": "lifecycle", "expansion": "expansion"}.get(trig, "risk"),
                                                           "priority": "high", "decision_id": did, "due_at": iso(row["task_due_at"])}, person=pk)
                else:
                    act_times.append(ts)
                    d = pick(rng, {"connected": 0.45, "not_reachable": 0.3, "meeting_booked": 0.1, "not_interested": 0.1, "replied": 0.05})
                    dur = int(rng.integers(120, 1800)) if d in ("connected", "meeting_booked") else None
                    row.update(disposition=d, call_duration_s=dur)
                    E(ts, "record_created", "salesforce", {"object": "activity", "id": tid, "to": "completed", "type": "exec_call" if chosen == "exec_call" else "call",
                                                           "disposition": d, "decision_id": did}, person=pk, ch="call")
                    if chosen == "discount":
                        E(ts, "record_status_changed", "salesforce", {"object": "opportunity", "id": opp_id or aid, "to": "discount_offered", "decision_id": did}, person=pk)
        acts.append(row)
        return chosen, delta, did

    # ---------------- opportunity emitter (outcome decided by the caller)
    def amount_of(x):
        return band(x, seg_edges)

    def plan_opp(t_open, t_close, typ, legal):
        span = max(t_close - t_open, DAY)
        stage_t = {s_: t_open + span * f * float(rng.uniform(0.9, 1.05)) for f, s_ in zip((0.25, 0.55, 0.8), ("evaluation", "proposal", "negotiation"))}
        n_act = int(min(8, max(1, span / (12 * DAY)))) if typ in ("new", "win_back") else (1 if typ == "expansion" else 0)
        acts_t = [t_open + span * (k + 1) / (n_act + 1) for k in range(n_act)]
        leg = None
        if legal:
            leg = (stage_t["proposal"], min(stage_t["proposal"] + float(rng.uniform(*v("funnel.security_legal_days"))) * DAY, t_close))
            iv["legal"].append(leg)
        act_times.extend(acts_t)
        return dict(stage_t=stage_t, acts_t=acts_t, legal=legal)

    def emit_opp(typ, t_open, t_close, won, amount, loss=None, comp=False, lock="none", disc=0.0, legal=False, esign=True, open_=False,
                 stage_frac=(0.25, 0.55, 0.8), cause=None, p_true=None, p_noact=None, cyc=None, oid=None, plan=None):
        oid = oid or nid("o", "O")
        if plan is None:
            plan = plan_opp(t_open, t_close, typ, legal)
        rep = f"rep_{int(rng.integers(1, 25)):02d}"
        inc_end = None
        if comp and lock != "none" and rng.random() < v("population.competitor_known_share") + 0.3:
            inc_end = t_open + float(rng.uniform(30, 300)) * DAY
        pk = people[0]["pk"] if people else None
        props0 = {"object": "opportunity", "id": oid, "to": "discovery", "type": typ, "amount_band": amount_of(amount), "competitor_flag": comp,
                  "incumbent_contract_end": iso(inc_end), "legal_review": False}
        E(t_open, "record_created", "salesforce", props0, person=pk, sid=f"opportunity:{oid}:created")
        span = max(t_close - t_open, DAY)
        last_stage, t_last = "discovery", t_open
        for s_ in ("evaluation", "proposal", "negotiation"):
            ts = plan["stage_t"][s_]
            if open_ and ts >= END:
                break
            leg = bool(plan["legal"]) and s_ == "proposal"
            E(ts, "record_status_changed", "salesforce", {**props0, "to": s_, "legal_review": leg}, person=pk)
            last_stage, t_last = s_, ts
        for ta in plan["acts_t"]:
            tid = nid("t", "T")
            E(ta, "record_created", "salesforce", {"object": "activity", "id": tid, "to": "completed", "type": pick(rng, {"call": 0.5, "meeting": 0.25, "email_task": 0.25}),
                                                   "disposition": pick(rng, {"connected": 0.5, "not_reachable": 0.35, "meeting_booked": 0.15})}, person=pk, ch="call")
        iv["opp"].append((t_open, t_close if not open_ or t_close < END else END + DAY))
        es_status = None
        es_t = None
        if esign and (won or (not won and last_stage == "negotiation" and rng.random() < 0.15)):
            envid = nid("x", "X")
            te = t_close - float(rng.uniform(2, 7)) * DAY if won else t_close - 3 * DAY
            seq = ["created", "sent", "delivered", "signed", "completed"] if won else ["created", "sent", "delivered", pick(rng, {"declined": 0.6, "voided": 0.4})]
            for s_ in seq:
                E(te, "record_status_changed", "docusign", {"object": "envelope", "id": envid, "to": s_, "opp_id": oid}, person=pk)
                es_status, es_t = s_, te
                te += float(rng.uniform(3600, 2 * DAY)) * (0.5 if won else 1)
            if won and es_t is not None and es_t > t_close:
                es_t = t_close
        disc_band = "none" if disc <= 0 else "1-10" if disc < 0.1 else "10-20" if disc < 0.2 else "20+"
        closed_at = None if (open_ and t_close >= END) else t_close
        if closed_at is not None:
            E(t_close, "record_status_changed", "salesforce", {**props0, "to": "closed_won" if won else "closed_lost", "loss_category": None if won else loss}, person=pk)
            if won:
                E(t_close, "outcome_confirmed", "salesforce", {"object": "opportunity", "id": oid, "to": "won", "amount_band": amount_of(amount)}, person=pk, sid=f"opportunity:{oid}:won")
        stage_now = "closed_won" if (closed_at is not None and won) else "closed_lost" if closed_at is not None else last_stage
        opps.append(dict(opp_id=oid, account_id=aid, type=typ, stage=stage_now, amount_band=amount_of(amount), discount_band=disc_band,
                         created_at=t_open, close_date=t_close, closed_at=closed_at if closed_at is not None and closed_at < END else None,
                         is_won=(bool(won) if closed_at is not None and closed_at < END else None), loss_category=loss if (closed_at is not None and not won) else None,
                         competitor_flag=comp, incumbent_vendor_band=("known" if inc_end else "unknown") if comp else None, incumbent_contract_end=inc_end,
                         rep_id=rep, legal_review=bool(legal), esign_status=es_status, esign_changed_at=es_t))
        optruth.append(dict(opp_id=oid, unit_id=aid, p_win_true=p_true, p_win_no_action=p_noact, cycle_days_true=(t_close - t_open) / DAY, amount=amount,
                            discount_pct=disc, true_won=bool(won), true_loss_category=None if won else loss,
                            label_final=bool(t_close + v("labels.renewal_buffer_days") * DAY <= END), cause_decision_id=cause))
        return oid

    # ---------------- web sessions
    def web_session(t, pk, anon, camp, ch, pages_hint=None, linked=True):
        sid = int(t)
        n = 1 + rng.poisson(v("sessions.mean_pages") - 1)
        tt = t
        pages = v("funnel.pages")
        for j in range(n):
            p = pages_hint[j] if pages_hint and j < len(pages_hint) else pages[int(rng.choice(len(pages), p=[.2, .18, .17, .13, .1, .08, .08, .06]))]
            E(tt, "page_view", "ga4", {"ga4_event": "page_view", "session_id": sid, "page": p, "utm_source": camp, "platform": "web"},
              person=pk if linked else None, anon=anon, ch=ch, camp=camp, sid=f"pv:{anon}:{sid}:{j}")
            tt += float(rng.lognormal(3.2, 0.7))
        return sid

    def day_time(day_s):
        h = int(np.searchsorted(hour_cdf, rng.random()))
        return day_s + min(h, 23) * 3600 + float(rng.uniform(0, 3600))

    # =============================================================================================================
    # PROSPECT PIPELINE (new accounts) -----------------------------------------------------------------------
    won = False
    t_won = None
    p_win_noact = p_win_true = None
    cause_opp = None
    lost_final = False
    lead_info = {}
    first_won_at = None
    seats = seats0
    if kind == "new":
        u = float(np.searchsorted(X.arr_cdf, rng.random()))
        t_lead = day_time(E0 + u * DAY)
        junk = bool(rng.random() < v("funnel.junk_lead_share")) or is_test
        ch = {"inbound": pick(rng, {"organic": 0.35, "paid_search": 0.3, "paid_social": 0.2, "direct": 0.15}), "outbound": "email", "partner": "partner",
              "event": "event", "referral": "referral", "competitor_displacement": pick(rng, {"paid_search": 0.4, "email": 0.4, "organic": 0.2})}[src]
        camp = None
        cp = v("campaigns.ad_campaigns")
        if ch == "paid_search":
            camp = f"gads_{int(rng.integers(1, cp['paid_search'] + 1))}"
        elif ch == "paid_social":
            camp = f"meta_{int(rng.integers(1, cp['paid_social'] + 1))}"
        elif ch == "partner":
            camp = f"partner_{int(rng.integers(1, cp['partner'] + 1))}"
        crm = "hubspot" if src in ("inbound", "event", "referral") else "salesforce"
        nct = int(rng.integers(v("population.contacts_per_lead")[seg][0], v("population.contacts_per_lead")[seg][1] + 1))
        roles = ["champion", "technical", "economic_buyer", "end_user", "end_user", "end_user"]
        c0 = mk_contact("champion", t_lead, lead=True)
        c0["anon"] = f"{int(rng.integers(10**8, 10**9))}.{int(t_lead)}"
        for k in range(1, nct):
            mk_contact(roles[k], t_lead + float(rng.uniform(1, 30)) * DAY, optin=0.3)
        lead_id = nid("o", "L")
        # web sessions before the form (inbound-like sources)
        if src in ("inbound", "event", "referral", "competitor_displacement") and not is_test:
            n_s = int(rng.integers(*[int(x) for x in v("funnel.sessions_before_demo")])) if P["ptype"] != "browser" else int(rng.integers(1, 3))
            pre = np.sort(rng.uniform(0, 28, n_s))[::-1]
            if ch in ("paid_search", "paid_social"):
                E(t_lead - pre[0] * DAY - 5, "link_click", "google_ads" if ch == "paid_search" else "meta_ads", {"object": "click", "id": f"{c0['anon']}", "to": "clicked", "gclid": f"g{int(rng.integers(10**9))}"},
                  anon=c0["anon"], ch=ch, camp=camp, sid=f"click:{c0['anon']}")
            for k, d in enumerate(pre):
                web_session(day_time(t_lead - d * DAY - (t_lead % DAY) + 0) if False else t_lead - d * DAY, c0["pk"], c0["anon"], camp, ch,
                            pages_hint=["pricing"] if P["ptype"] in ("evaluator",) and k == len(pre) - 1 else None, linked=False)
        linked = rng.random() < 0.6
        E(t_lead, "record_created", crm, {"object": "lead", "id": lead_id, "to": "new", "lead_source": src}, person=c0["pk"], ch=ch, camp=camp)
        E(t_lead + 1, "identify", crm, {"object": "identify", "id": c0["pk"][:10], "to": "identified", "merged": c0["anon"] if linked else None},
          person=c0["pk"], anon=c0["anon"], sid=f"identify:{c0['pk'][:12]}")
        if P["ptype"] in ("evaluator", "researcher") and src in ("inbound", "event") and rng.random() < 0.6:
            E(t_lead + 2, "record_created", crm, {"object": "demo_request", "id": nid("x", "R"), "to": "submitted"}, person=c0["pk"], ch="web", camp=camp)
        if src == "event":
            rid = nid("x", "R")
            E(t_lead - 3600, "record_created", "cvent", {"object": "registration", "id": rid, "to": "registered", "event_id": f"EV{int(rng.integers(1, 12)):02d}"}, person=c0["pk"], ch="event")
            E(t_lead, "record_status_changed", "cvent", {"object": "registration", "id": rid, "to": "attended" if rng.random() < 0.6 else "no_show", "event_id": "EV"}, person=c0["pk"], ch="event")
        status_now, t_last = "new", t_lead
        lead_conv_at = None
        # --- stage 1: lead -> MQL, decision at day 7 when still stalled
        fit = P["fit"]
        p_mql0 = min(0.95, v("funnel.p_lead_to_mql") * P["f"]["mql"] / X.fmean["mql"] / (1 - v("funnel.junk_lead_share")))
        u_m, d1 = float(rng.random()), float(rng.lognormal(math.log(v("funnel.lead_to_mql_days")), 0.7)) * DAY
        p_mql, did_l = p_mql0, None
        if d1 > 7 * DAY or junk or True:
            if junk or u_m >= p_mql0 or d1 > 7 * DAY:
                ch_a, dl, did_l = decide("lead_stall", t_lead + 7 * DAY, p_mql0, fit=fit, size=math.log1p(acv / 5000.0) / 2)
                p_mql = min(0.97, max(0.0, p_mql0 + dl))
        mql = (not junk) and u_m < p_mql
        if mql:
            t1 = t_lead + max(d1, 1 * DAY)
            E(t1, "record_status_changed", crm, {"object": "lead", "id": lead_id, "to": "contacted", "lead_source": src}, person=c0["pk"], ch=ch)
            status_now, t_last = "contacted", t1
            p_sql = min(0.95, v("funnel.p_mql_to_sql") * P["f"]["sql"] / X.fmean["sql"])
            if rng.random() < p_sql:
                t2 = t1 + float(rng.lognormal(math.log(v("funnel.mql_to_sql_days")), 0.6)) * DAY
                E(t2, "record_status_changed", crm, {"object": "lead", "id": lead_id, "to": "qualified", "lead_source": src}, person=c0["pk"], ch=ch)
                status_now, t_last = "qualified", t2
                p_opp = min(0.95, v("funnel.p_sql_to_opp") * P["f"]["opp"] / X.fmean["opp"])
                if rng.random() < p_opp:
                    t3 = t2 + float(rng.lognormal(math.log(v("funnel.sql_to_opp_days")), 0.6)) * DAY
                    status_now, t_last, lead_conv_at = "converted", t3, t3
                    E(t3, "record_status_changed", crm, {"object": "lead", "id": lead_id, "to": "converted", "lead_source": src, "converted": True}, person=c0["pk"], ch=ch)
                    # ---- opportunity
                    cyc_days = float(v("funnel.cycle_median_days")[seg] * rng.lognormal(0, v("funnel.cycle_sigma")))
                    if P["comp"] and P["lock"] != "none":
                        cyc_days *= v("funnel.displacement_cycle_mult")
                    t_close = t3 + cyc_days * DAY
                    if rng.random() < 0.35:  # budget cycle: close waits for the budget month
                        d = pd.Timestamp(t_close, unit="s", tz="UTC")
                        nxt = pd.Timestamp(year=d.year if d.month <= budget_m else d.year + 1, month=budget_m, day=1, tz="UTC").timestamp()
                        if 0 < nxt - t_close < 90 * DAY:
                            t_close = nxt
                    p_w0 = min(0.9, v("funnel.p_opp_to_won") * P["f"]["win"] / X.fmean["win"])
                    u_w = float(rng.random())
                    p_win_noact = p_w0
                    t_dec = t3 + cyc_days * DAY * 0.75
                    plan_new = plan_opp(t3, t_close, "new", bool(rng.random() < v("funnel.legal_review_share")[seg]))
                    iv["opp"].append((t3, t_close))
                    oid_pre = nid("o", "O")
                    ca, dw, did_o = decide("opp_stall", t_dec, p_w0, opp_id=oid_pre, fit=fit, size=math.log1p(acv / 5000.0) / 2)
                    p_win_true = min(0.95, max(0.01, p_w0 + dw))
                    disc = 0.0
                    if ca == "discount":
                        disc = float(rng.uniform(0.10, 0.20))
                    won = u_w < p_win_true
                    loss = None
                    if not won:
                        lm = dict(v("funnel.loss_categories"))
                        if P["comp"]:
                            lm["competitor"] *= 2.0
                        if ca == "discount":
                            lm["price"] *= 0.5
                        loss = pick(rng, lm)
                    open_ = t_close >= END
                    if won:
                        t_won = t_close
                    cause_opp = emit_opp("new", t3, t_close, won, acv * (1 - disc), loss, comp=P["comp"], lock=P["lock"], disc=disc,
                                         legal=plan_new["legal"], open_=open_, p_true=p_win_true,
                                         p_noact=p_win_noact, cause=did_o, oid=oid_pre, plan=plan_new)
                    if open_:
                        won = False
                        t_won = None
                    if won:
                        acv = acv * (1 - disc)
                        st["disc"] = disc
                    elif not open_:
                        lost_final = True
        # lead lost after quiet
        if status_now in ("new", "contacted", "qualified") and t_last + v("funnel.lead_quiet_days") * DAY < END:
            E(t_last + v("funnel.lead_quiet_days") * DAY, "record_status_changed", crm, {"object": "lead", "id": lead_id, "to": "lost", "lead_source": src}, person=c0["pk"], ch=ch)
            status_now = "lost"
        c0["lead_info"] = dict(status=status_now, source=src, created=t_lead, converted=lead_conv_at)
        # a lost deal may come back after the cooling off
        if lost_final and rng.random() < v("retention.lost_return"):
            tr = t_close + float(rng.uniform(90, 365)) * DAY
            cy2 = cyc_days * 0.6 * DAY
            u2 = rng.random()
            w2 = u2 < min(0.9, p_win_noact * 1.1)
            if tr < END:
                st["pre"] = True
                emit_opp("new", tr, tr + cy2, w2, acv, None if w2 else "no_decision", comp=P["comp"], lock=P["lock"], open_=tr + cy2 >= END,
                         p_true=p_win_noact * 1.1, p_noact=p_win_noact * 1.1)
                if w2 and tr + cy2 < END:
                    won, t_won, lost_final = True, tr + cy2, False
        st["pre"] = False
        first_won_at = t_won if won else None
    else:
        # installed base: won before the window
        age = float(rng.uniform(*v("population.installed_base_age_days"))) * DAY
        t_won = E0 - age
        won = True
        first_won_at = t_won
        c0 = mk_contact("champion", t_won - 30 * DAY, lead=False, optin=0.55)
        c0["t_first"] = t_won - 30 * DAY
        for k, role in enumerate(["economic_buyer", "technical"]):
            mk_contact(role, t_won - 20 * DAY, optin=0.4)
        P["f"] = P["f"]
        ptp = None
        oid_h = nid("o", "O")
        opps.append(dict(opp_id=oid_h, account_id=aid, type="new", stage="closed_won", amount_band=amount_of(acv), discount_band="none", created_at=t_won - 45 * DAY,
                         close_date=t_won, closed_at=t_won, is_won=True, loss_category=None, competitor_flag=False, incumbent_vendor_band=None,
                         incumbent_contract_end=None, rep_id=f"rep_{int(rng.integers(1, 25)):02d}", legal_review=False, esign_status="completed", esign_changed_at=t_won - 3 * DAY))
        c0["lead_info"] = None
        lead_info = {}

    # =============================================================================================================
    # CUSTOMER LIFECYCLE ------------------------------------------------------------------------------------------
    churn_info = dict(kind=None, at=None, outcomes=[])
    seat_d = np.zeros(T)
    lvl = np.ones(T)
    mask = np.zeros(T, bool)
    champ_left_at = None
    users = []
    first_value_t = None
    sub_ver = [0]
    sub_ctr = [0]
    sub_id = f"S{i:07d}-01"
    p_card_fail = v("billing.card_fail_rate")
    rt = v("billing.retry_days")

    def dn(t):
        return int(min(max((t - E0) // DAY, 0), T))

    def set_mask(a, b, val):
        a_, b_ = dn(a), dn(b)
        if b_ > a_:
            mask[a_:b_] = val

    def sub_emit(version, s, e, seats_, status, cancel_req, auto, mrr, trial_end=None, collection="charge_automatically", superseded=False, t_change=None):
        subs.append(dict(subscription_id=sub_id, account_id=aid, version=version, plan=plan, seats_bought=seats_,
                         seats_active_band="50-75%", billing_interval=interval, term_months=term_months, start_at=s, end_at=e,
                         auto_renew_flag=auto, cancel_requested=cancel_req, status=status, status_changed_at=t_change or s, pause_collection=False,
                         collection_method=collection, trial_end=trial_end, mrr_band=amount_of(mrr * 1.0 / 1.0)))

    def charge(t_issue, amount, is_renewal, first=False):
        """Issue one invoice, run payment and dunning. Returns (final_status, paid_at, involuntary_final_time)."""
        invid = nid("i", "I")
        method = "charge_automatically" if pay_card else "send_invoice"
        due = t_issue + (0 if pay_card else v("billing.net_terms_days") * DAY)
        if first and not pay_card:
            due = t_issue + float(rng.uniform(30, 60)) * DAY
        pk = people[0]["pk"] if people else None
        props = {"object": "invoice", "id": invid, "to": "created", "amount_band": amount_of(amount), "collection_method": method}
        E(t_issue, "record_created", "stripe", props, person=pk)
        notice(t_issue + 60, "invoice", "invoice_issued")
        attempts, err, status, paid_at, inv_final = 0, None, "captured", None, None
        disputed = bool(rng.random() < v("billing.dispute_share"))
        if pay_card:
            attempts = 1
            if rng.random() < p_card_fail:
                err = pick(rng, {"insufficient_funds": 0.4, "expired_card": 0.3, "card_declined": 0.3})
                hard = rng.random() < v("billing.hard_decline_share")
                E(t_issue + 30, "record_status_changed", "stripe", {**props, "to": "failed", "attempt": 1, "error_code": err}, person=pk)
                iv["payfail"].append((t_issue, t_issue + 14 * DAY))
                rec_t = None
                notice(t_issue + 600, "invoice", "payment_failed", "transactional")
                for d in rt:
                    attempts += 1
                    if not hard and rng.random() < v("billing.retry_recover_each"):
                        rec_t = t_issue + d * DAY
                        break
                    E(t_issue + d * DAY, "record_status_changed", "stripe", {**props, "to": "failed", "attempt": attempts, "error_code": err}, person=pk)
                if rec_t is None and rng.random() < v("billing.customer_fix_prob"):
                    rec_t = t_issue + float(rng.uniform(rt[-1] + 1, rt[-1] + 12)) * DAY
                if rec_t is None:
                    status = "failed"
                    inv_final = t_issue + (rt[-1] + float(rng.uniform(1, 4))) * DAY
                else:
                    paid_at = rec_t
            else:
                paid_at = t_issue + float(rng.uniform(5, 90))
        else:
            late = rng.random() < v("billing.invoice_late_share")
            paid_at = due + (float(rng.lognormal(math.log(v("billing.invoice_late_days")[0] + 2), 0.5)) * DAY if late else -float(rng.uniform(0, 5)) * DAY)
            if disputed:
                paid_at += 20 * DAY
            paid_at = max(paid_at, t_issue + DAY)
        if paid_at is not None:
            E(paid_at, "record_status_changed", "stripe", {**props, "to": "captured", "attempt": attempts}, person=pk)
            E(paid_at + 5, "outcome_confirmed", "stripe", {"object": "invoice", "id": invid, "to": "paid", "amount_band": amount_of(amount)}, person=pk, sid=f"invoice:{invid}:paid")
            if rng.random() < v("billing.refund_share"):
                status = "refunded"
                E(paid_at + 3 * DAY, "record_status_changed", "stripe", {**props, "to": "refunded"}, person=pk)
        invs.append(dict(invoice_id=invid, subscription_id=sub_id, account_id=aid, amount_band=amount_of(amount), issued_at=t_issue, due_at=due,
                         paid_at=paid_at if paid_at is not None and paid_at < END else None,
                         status=status if (paid_at is None or paid_at < END or status == "failed") else "created", collection_method=method,
                         attempt_count=attempts, error_code=err, disputed=disputed, is_renewal=is_renewal))
        return status, paid_at, inv_final

    ticket_base = []

    def gen_tickets(a, b, rate_mult=1.0, extra=False):
        r = rng.uniform(*v("support.tickets_per_month")) * (max(seats0, 4) / 20.0) ** 0.5 * rate_mult
        n = rng.poisson(r * max(b - a, 0) / MONTH)
        out = []
        for _ in range(n):
            t = a + float(rng.uniform(0, max(b - a, 1)))
            tid = nid("t", "K")
            topic = v("support.ticket_topics")[int(rng.choice(4, p=v("support.ticket_topic_probs")))]
            prio = pick(rng, {"low": 0.3, "normal": 0.5, "high": 0.15, "urgent": 0.05})
            solved = t + float(rng.lognormal(math.log(v("support.solve_days_median")), 0.8)) * DAY
            reopen = int(rng.random() < v("support.reopen_prob"))
            pk = people[int(rng.integers(len(people)))]["pk"]
            props = {"object": "ticket", "id": tid, "to": "new", "priority": prio, "ticket_type": topic, "channel": pick(rng, {"email": 0.6, "web": 0.3, "chat": 0.1}),
                     "tags": [topic]}
            E(t, "record_created", "zendesk", props, person=pk)
            E(t + float(rng.uniform(300, 7200)), "record_status_changed", "zendesk", {**props, "to": "open"}, person=pk)
            if rng.random() < 0.4:
                E(t + (solved - t) * 0.5, "record_status_changed", "zendesk", {**props, "to": "pending"}, person=pk)
            csat = None
            if rng.random() < v("support.csat_response"):
                csat = int(np.clip(round(rng.normal(4.0 - (1.0 if extra else 0), 1.0)), 1, 5))
            E(solved, "record_status_changed", "zendesk", {**props, "to": "solved", "csat": csat, "reopens": reopen}, person=pk)
            E(solved + 4 * DAY, "record_status_changed", "zendesk", {**props, "to": "closed", "csat": csat, "reopens": reopen}, person=pk)
            iv["ticket"].append((t, solved))
            out.append((t, solved, prio, reopen))
        return out

    def usage_users(n_tr):
        for j in range(len(users), n_tr):
            c = mk_contact("end_user", E0 - 10 * DAY if kind == "base" else (t_won or E0) + float(rng.uniform(0, 20)) * DAY, user=True, optin=0.2)
            users.append(c)

    # ---- the customer run
    def run_customer(t0, first_cycle=True, allow_winback=True, disc=0.0, ctype_now=None):
        nonlocal seats, sub_id, champ_left_at, first_value_t, interval, annual, first_won_at, acv
        sub_idx = len(subs)
        ct = ctype_now or ctype
        pk0 = people[0]["pk"]
        cyc_m = 12 if interval == "monthly" else term_months
        s = t0
        mrr0 = acv / 12.0
        # trial
        trial_end = None
        if first_cycle and kind == "new" and seg == "SMB" and rng.random() < v("funnel.trial_share_smb"):
            trial_end = t0 + v("funnel.trial_days") * DAY
        # activation
        act_p = v("retention.onboarding_activation")[ct]
        activated = bool(rng.random() < act_p)
        fv_days = float(v("retention.first_value_days")[seg] * rng.lognormal(0, 0.6))
        never_live = first_cycle and kind == "new" and rng.random() < v("funnel.never_live_share")
        if never_live:
            activated = False
        if first_cycle and t0 + 90 * DAY > E0:
            if activated and fv_days <= 90:
                first_value_t = t0 + fv_days * DAY
                E(first_value_t, "record_status_changed", "amplitude", {"object": "onboarding", "id": aid, "to": "first_value_reached"}, person=pk0)
            if named_csm or seg != "SMB":
                _, dl, _ = decide("onboarding", t0 + 30 * DAY, act_p, fit=P["fit"], size=math.log1p(acv / 5000.0) / 2)
                if dl and not activated and rng.random() < abs(dl) * 4 and dl > 0:
                    activated = True
                    first_value_t = t0 + 40 * DAY
                    E(first_value_t, "record_status_changed", "amplitude", {"object": "onboarding", "id": aid, "to": "first_value_reached"}, person=pk0)
                    activated_flag[0] = True
        ver = 0
        e_final, kind_final = None, None
        k_cycle = 0
        while s < END:
            k_cycle += 1
            e = s + cyc_m * MONTH
            comp = churn_components(rng, X, seg, ct)
            shift, d_, left, sev, inact, integ_ = comp
            # champion exit within the cycle is drawn from the hidden hazard
            t_left = None
            if champ_left_at is None and rng.random() < 1 - math.exp(-champ_hazard * cyc_m):
                t_left = s + float(rng.uniform(0.1, 1.0)) * (e - s)
            left = 1.0 if t_left is not None else 0.0
            inact = 0.0 if activated else 1.0
            comp = (shift, decay_rate, left, sev, inact, 1.0 if integ else 0.0)
            lg = churn_logit(X, comp, disc if k_cycle == 1 else 0.0) + X.churn_off[seg]
            p_ann = float(expit(lg))
            p_cyc = 1 - (1 - p_ann) ** (cyc_m / 12.0)
            u_c = float(rng.random())
            t_dec = max(e - v("subscription.renewal_open_days") * DAY, s + 30 * DAY)
            need_opp = (seg in ("MM", "ENT") or not auto_renew) and annual
            t_o_plan = e - float(rng.uniform(90, 105)) * DAY
            if need_opp:
                iv["opp"].append((t_o_plan, e + 40 * DAY))
            ca, dl, _ = decide("risk", t_dec, p_cyc, fit=P["fit"], size=math.log1p(acv / 5000.0) / 2)
            _c2, dl2, _ = decide("risk", t_dec + 4 * DAY, p_cyc, fit=P["fit"], size=math.log1p(acv / 5000.0) / 2)  # second check-in; effects add
            dl += dl2
            p_after = float(np.clip(p_cyc - dl, 0.002, 0.98))
            churns = u_c < p_after
            u_k = float(rng.random())
            churn_lapse = bool(annual and rng.random() < v("retention.lapse_given_annual_churn") * (1 - 0.6 * auto_renew))
            if (first_cycle and k_cycle == 1 and (never_live or (trial_end and rng.random() > v("funnel.trial_to_paid")))):
                churns, churn_lapse = True, False
            if t_left is not None:
                champ_left_at = t_left
                pkl = people[0]["pk"]
                E(t_left, "record_status_changed", "salesforce", {"object": "contact", "id": people[0]["ref"], "to": "left_account"}, person=pkl)
                people[0]["left"] = t_left
            # voluntary churn timing
            t_end_eff, vol_churn_at = e, None
            if churns:
                if annual:
                    vol_churn_at = e
                else:
                    mc = 1 + int(rng.integers(0, cyc_m)) if activated else min(cyc_m, 1 + int(rng.geometric(0.3)))
                    vol_churn_at = s + mc * MONTH
                    t_end_eff = vol_churn_at
            # ---- subscription version rows and billing
            ver += 1
            sub_ctr[0] += 1
            sub_id = f"S{i:07d}-{sub_ctr[0]:02d}"
            coll = "charge_automatically" if pay_card else "send_invoice"
            seat_c = seats
            mrr = acv / 12.0
            involuntary_t, inv_status = None, None
            if annual:
                st_, pa, inv_final = charge(s if k_cycle > 1 or kind == "base" else s + float(rng.uniform(*v("funnel.first_invoice_days"))) * DAY,
                                            acv * (cyc_m / 12.0), is_renewal=k_cycle > 1, first=(k_cycle == 1 and kind == "new"))
                if inv_final is not None:
                    involuntary_t = inv_final
            else:
                j = 0
                while True:
                    ts_ = s + j * MONTH
                    if ts_ >= t_end_eff or ts_ >= END + 40 * DAY:
                        break
                    st_, pa, inv_final = charge(ts_ + (float(rng.uniform(*v("funnel.first_invoice_days"))) * DAY if (j == 0 and kind == "new" and k_cycle == 1) else 0),
                                                acv / 12.0, is_renewal=(j == 0 and k_cycle > 1), first=(j == 0 and k_cycle == 1 and kind == "new"))
                    if inv_final is not None:
                        involuntary_t = inv_final
                        break
                    j += 1
            # card-failure or never-pay -> involuntary churn
            if involuntary_t is not None and (vol_churn_at is None or involuntary_t < vol_churn_at):
                vol_churn_at, churns, kind_end = involuntary_t, True, "involuntary"
                final_status = pick(rng, v("billing.after_retries"))
                final_status = {"cancelled": "cancelled", "unpaid": "past_due", "past_due": "past_due", "paused": "paused"}[final_status]
                t_end_eff = min(t_end_eff, involuntary_t)
            else:
                kind_end = "silent_lapse" if (churns and churn_lapse) else "cancelled" if churns else None
                final_status = "cancelled" if kind_end == "cancelled" else "expired" if kind_end == "silent_lapse" else None
            if never_live and k_cycle == 1:
                kind_end = "never_live"
            # ---- usage level for this cycle
            a_d, b_d = dn(max(s, E0)), dn(min(t_end_eff, END))
            if b_d > a_d:
                seat_d[a_d:b_d] = seat_c
                mask[a_d:b_d] = True
                lvl[a_d:b_d] = 1.0
                if t_left is not None and ct == "champion_dependent":
                    lvl[dn(t_left):b_d] *= 0.5
                elif t_left is not None:
                    lvl[dn(t_left):b_d] *= 0.9
                # onboarding ramp
                if k_cycle == 1:
                    ramp = np.clip(np.arange(b_d - a_d) / (fv_days if activated else 120.0), 0.15, 1.0)
                    lvl[a_d:b_d] *= ramp if activated else np.minimum(ramp, 0.3)
                if ct == "project_based":
                    blocks = np.repeat(rng.random((b_d - a_d) // 30 + 2) < 0.55, 30)[: b_d - a_d]
                    lvl[a_d:b_d] *= np.where(blocks, 1.0, 0.1)
                if ct == "shelfware":
                    lvl[a_d:b_d] *= np.linspace(1.0, 0.7, b_d - a_d)
            # pre-churn decay
            pre_churn = churns and kind_end in ("cancelled", "silent_lapse", "never_live") and kind_end != "involuntary"
            if pre_churn and kind_end != "never_live":
                mode = "gradual" if rng.random() < v("retention.usage_decay_gradual") else "sudden"
                decay_state["mode"] = mode
                if mode == "gradual":
                    w_ = float(rng.uniform(*v("retention.decay_weeks"))) * 7 * DAY
                    a2, b2 = dn(t_end_eff - w_), dn(t_end_eff)
                    if b2 > a2:
                        lvl[a2:b2] *= np.linspace(1.0, 0.12, b2 - a2)
                else:
                    t_stop = t_end_eff - float(rng.uniform(*v("retention.sudden_lead_days"))) * DAY
                    lvl[dn(t_stop):dn(t_end_eff)] *= 0.03
                if kind_end == "silent_lapse":
                    lvl[dn(t_end_eff - 30 * DAY):dn(t_end_eff)] *= 0.3
                extra = gen_tickets(t_end_eff - 90 * DAY, t_end_eff, v("support.pre_churn_ticket_lift") - 1.0, extra=True)
            # ---- subscription rows (this term) and events
            status_row = final_status if kind_end in ("cancelled", "silent_lapse", "involuntary") else ("cancelled" if kind_end == "never_live" else "active")
            if kind_end == "never_live":
                status_row = "cancelled"
                t_end_eff = min(t_end_eff, s + 60 * DAY)
            end_at = t_end_eff if kind_end else e
            renew_ok = not kind_end
            if renew_ok and e <= END:
                status_row = "expired"
            if status_row == "active" and end_at <= END and False:
                status_row = "expired"
            props_s = {"object": "subscription", "id": sub_id, "to": "trialing" if (trial_end and k_cycle == 1) else "active", "renewal_at": iso(end_at), "plan": plan,
                       "auto_renew": auto_renew, "version": ver, "superseded": False, "cancel_flag": False, "returning": not first_cycle}
            E(s, "record_created", "stripe", props_s, person=pk0)
            if s < E0 < end_at:
                E(E0 + 60, "record_status_changed", "stripe", {**props_s, "snapshot": True}, person=pk0)
            if trial_end and k_cycle == 1:
                E(trial_end, "record_status_changed", "stripe", {**props_s, "to": "active"}, person=pk0)
            if kind_end in ("cancelled", "involuntary", "never_live") and end_at < END + 400 * DAY:
                if kind_end == "cancelled":
                    E(end_at - float(rng.uniform(1, 25)) * DAY, "record_status_changed", "stripe", {**props_s, "to": "active", "cancel_flag": True}, person=pk0)
                final_ev = "cancelled" if status_row == "cancelled" else status_row
                if kind_end == "involuntary":
                    E(end_at - 2 * DAY, "record_status_changed", "stripe", {**props_s, "to": "past_due"}, person=pk0)
                E(end_at, "record_status_changed", "stripe", {**props_s, "to": final_ev, "superseded": False, "final": True}, person=pk0)
            elif kind_end == "silent_lapse":
                E(end_at, "record_status_changed", "stripe", {**props_s, "to": "expired", "superseded": False, "final": True}, person=pk0)
            elif renew_ok and e <= END:
                E(e, "record_status_changed", "stripe", {**props_s, "to": "expired", "superseded": True}, person=pk0)
            sub_row_status = status_row
            if sub_row_status == "active" and end_at > END:
                sub_row_status = "active"
            if kind_end in ("cancelled", "silent_lapse", "involuntary", "never_live") and end_at > END:
                sub_row_status = "active"
            sub_emit(ver, s, end_at, seat_c, sub_row_status, kind_end == "cancelled", auto_renew, mrr, trial_end if k_cycle == 1 else None, coll,
                     t_change=min(end_at, END) if sub_row_status != "active" else s)
            # ---- renewal notices, renewal opportunity, health
            notice(end_at - 90 * DAY, "renewal_notice", "renewal_notice")
            if e - 14 * DAY < END:
                iv["renew"].append((e - 14 * DAY, e + DAY))
            if need_opp:
                t_o = t_o_plan
                late_close = (renew_ok and rng.random() < v("subscription.late_renewal_share"))
                t_c = e + (float(rng.uniform(3, 40)) * DAY if late_close else 0.0)
                if kind_end in ("cancelled", "involuntary"):
                    t_c = min(end_at, e)
                    emit_opp("renewal", t_o, t_c, False, acv, pick(rng, {"competitor": 0.4, "no_decision": 0.2, "price": 0.15, "timing": 0.1, "product_gap": 0.1, "champion_left": 0.05}) if t_left is None else "champion_left",
                             comp=False, esign=False, open_=t_c >= END, p_true=1 - p_after, p_noact=1 - p_cyc, cause=None, stage_frac=(0.3, 0.6, 0.85))
                elif kind_end == "silent_lapse":
                    emit_opp("renewal", t_o, e + 30 * DAY, False, acv, "no_decision", esign=False, open_=e + 30 * DAY >= END, p_true=1 - p_after, p_noact=1 - p_cyc, stage_frac=(0.4, 0.7, 0.9))
                else:
                    emit_opp("renewal", t_o, t_c, True, acv * (1 + v("subscription.price_rise")), esign=seg != "SMB", open_=t_c >= END, p_true=1 - p_after, p_noact=1 - p_cyc,
                             stage_frac=(0.3, 0.6, 0.85))
            churn_info["outcomes"].append(dict(cycle=k_cycle, p_churn=round(p_cyc, 4), p_after=round(p_after, 4), churned=bool(kind_end), kind=kind_end, end=float(end_at), months=cyc_m, annual=bool(annual)))
            # tickets and health for the cycle are generated outside
            if kind_end:
                e_final, kind_final = end_at, kind_end
                break
            # ---- renewal-time changes
            u_r = float(rng.random())
            cur_seats = seats
            p_exp = v("retention.expansion_prob_year")[seg] * (0.6 + headroom) * (cyc_m / 12.0)
            _, dx, _ = decide("expansion", e - 110 * DAY if annual else s + 6 * MONTH, p_exp, fit=P["fit"], size=math.log1p(acv / 5000.0) / 2)
            if rng.random() < p_exp + dx:
                at_renewal = rng.random() < v("retention.expansion_at_renewal_share")
                g_ = float(rng.uniform(*v("retention.expansion_size")[seg]))
                t_x = e if at_renewal else s + float(rng.uniform(0.2, 0.8)) * (e - s)
                emit_opp("expansion", t_x - 45 * DAY, t_x, True, acv * g_, esign=seg != "SMB", open_=t_x >= END, p_true=p_exp + dx, p_noact=p_exp)
                if t_x < END or True:
                    new_seats = int(math.ceil(cur_seats * (1 + g_)))
                    if not at_renewal and t_x < e:
                        sub_emit(ver + 1, t_x, e, new_seats, "active" if e > END else "expired", False, auto_renew, acv * (1 + g_) / 12.0, collection=coll)
                        seat_d[dn(t_x):dn(e)] = new_seats
                        E(t_x, "record_status_changed", "stripe", {**props_s, "to": "active", "version": ver + 1, "superseded": False, "amendment": "expansion"}, person=pk0)
                    seats = new_seats
                    acv *= (1 + g_)
                    churn_info["outcomes"][-1]["expansion"] = round(g_, 3)
                    churn_info["outcomes"][-1]["at_renewal"] = bool(at_renewal)
            elif u_r < v("retention.contraction_prob")[seg]:
                cut = float(rng.uniform(*v("retention.contraction_size")))
                seats = max(2, int(seats * (1 - cut)))
                acv *= (1 - cut)
                churn_info["outcomes"][-1]["contraction"] = round(cut, 3)
            elif annual:
                acv *= (1 + v("subscription.price_rise") * 0.5)
            s = e + (float(rng.uniform(3, 40)) * DAY if (annual and rng.random() < v("subscription.late_renewal_share") and False) else 0.0)
        return e_final, kind_final

    decay_state = {"mode": "none"}
    activated_flag = [False]

    # ---- account-level run
    t_churn_first, churn_kind = None, None
    ret_acv = acv
    if won:
        sub_start = (t_won + float(rng.uniform(0, 14)) * DAY) if kind == "new" else t_won
        usage_users(int(min(v("population.tracked_users_cap"), max(2, seats0))))
        # tickets for the life of the account
        ticket_base = gen_tickets(max(sub_start, E0), END, 1.0)
        e1, k1 = run_customer(sub_start, True, True, st.get("disc", 0.0))
        if k1:
            t_churn_first, churn_kind = e1, k1
            # win-back
            if k1 != "never_live" and e1 < END:
                p_wb = v("retention.win_back_return")
                t_dw = e1 + float(rng.uniform(90, 180)) * DAY
                _, dw2, _ = decide("winback", t_dw, p_wb, fit=P["fit"], size=math.log1p(acv / 5000.0) / 2)
                if rng.random() < p_wb + dw2 and t_dw < END:
                    t_back = t_dw + float(rng.uniform(20, 60)) * DAY
                    emit_opp("win_back", t_dw, t_back, True, acv, comp=False, open_=t_back >= END, p_true=p_wb + dw2, p_noact=p_wb)
                    if t_back < END:
                        seats = seats0
                        run_customer(t_back, False, False)
    # ---- usage rows (vectorised)
    if won and mask.any():
        n_tr = len(users)
        share = float(rng.uniform(*v("population.active_share")[ctype]))
        spw = rng.uniform(*v("population.sessions_per_week")[ctype])
        act_user = rng.random(n_tr) < share
        p_u = np.where(act_user, np.clip(spw / 5.0 * rng.uniform(0.6, 1.3, n_tr), 0.04, 0.95), 0.015)
        days = np.nonzero(mask)[0]
        if len(days):
            max_seats = max(seat_d.max(), 1)
            n_up = np.clip(np.ceil(seat_d[days] * n_tr / max_seats), 1, n_tr)
            uid = np.arange(n_tr)[:, None]
            allowed = uid < n_up[None, :]
            pm = p_u[:, None] * (lvl[days] * X.cal[days])[None, :] * allowed
            act = rng.random(pm.shape) < np.clip(pm, 0, 0.98)
            uu, dd = np.nonzero(act)
            if len(uu):
                feats = v("usage.features")
                fp = np.array(v("usage.feature_probs"), float)
                fp /= fp.sum()
                k_per = rng.integers(v("usage.features_per_active_day")[0], v("usage.features_per_active_day")[1] + 1, len(uu))
                ru = np.repeat(uu, k_per + 1)
                rd = np.repeat(dd, k_per + 1)
                first = np.zeros(len(ru), bool)
                starts = np.concatenate([[0], np.cumsum(k_per + 1)[:-1]])
                first[starts] = True
                fi = rng.choice(len(feats), len(ru), p=fp)
                names = np.array(feats + ["login"])
                fname = np.where(first, "login", names[fi])
                ne = rng.integers(v("usage.events_per_feature_day")[0], v("usage.events_per_feature_day")[1] + 1, len(ru))
                ne = np.where(first, 1, ne)
                nm = np.round(rng.uniform(*v("usage.minutes_per_feature_day"), len(ru)), 1)
                nm = np.where(first, 0.0, nm)
                sess = np.where(first, 1, 0) + rng.integers(0, 2, len(ru)) * (~first)
                # failed logins as separate login rows are carried as events only (below)
                df = pd.DataFrame({"u": ru, "d": days[rd], "feature": fname, "num_events": ne, "num_minutes": nm, "session_count": np.maximum(sess, 1)})
                df = df.groupby(["u", "d", "feature"], as_index=False).agg(num_events=("num_events", "sum"), num_minutes=("num_minutes", "sum"), session_count=("session_count", "max"))
                src_sys = "amplitude" if (i % 5) < 3 else "pendo"
                unm = rng.random(n_tr) < v("usage.unmatched_user_share")
                wrong = rng.random(n_tr) < v("noise.wrongly_matched_share")
                pk_arr = np.array([u_["pk"] for u_ in users])
                acc_arr = np.where(unm, None, aid).astype(object)
                for j in np.nonzero(wrong & ~unm)[0]:
                    acc_arr[j] = f"A{int(rng.integers(0, X.n_total)):07d}"
                    noise_extra.append((None, "wrongly_matched", json.dumps({"person": users[j]["ref"], "true": aid, "shown": acc_arr[j]})))
                for j in np.nonzero(unm)[0]:
                    noise_extra.append((None, "unmatched_user", json.dumps({"person": users[j]["ref"], "true": aid})))
                    users[j]["unmatched"] = True
                for j in np.nonzero(wrong & ~unm)[0]:
                    users[j]["wrong"] = acc_arr[j]
                dayts = E0 + df["d"].to_numpy() * DAY
                lag = rng.uniform(*v("usage.amplitude_late_hours"), len(df)) * 3600 if src_sys == "amplitude" else np.full(len(df), 30 * 3600.0)
                fr = pd.DataFrame({"account_id": acc_arr[df["u"].to_numpy()], "person_key": pk_arr[df["u"].to_numpy()], "feature": df["feature"],
                                   "day": dayts, "num_events": df["num_events"].astype(int), "num_minutes": df["num_minutes"].astype(float),
                                   "session_count": df["session_count"].astype(int), "source_system": src_sys,
                                   "ingested_at": dayts + DAY + lag})
                usage.append(fr)
                # failed logins as events
                nfail = rng.poisson(len(df[df.feature == "login"]) * v("usage.login_fail_rate"))
                if nfail:
                    lf = df[df.feature == "login"].sample(min(nfail, 60), random_state=int(i) % 2**31) if len(df[df.feature == "login"]) else df.iloc[:0]
                    for _, r_ in lf.iterrows():
                        E(E0 + r_["d"] * DAY + 9 * 3600, "record_created", "okta", {"object": "login", "id": nid("x", "G"), "to": "failed", "login_type": "sso" if rng.random() < v("usage.sso_share") else "password"},
                          person=users[int(r_["u"])]["pk"])
        # ---- health scores every 30 days and CTAs
        cuts = v("cs.health_cuts")
        prev, open_cta = "green", 0
        t_first_sub = max(sub_start if kind == "new" else E0, E0)
        t_h = t_first_sub + 30 * DAY
        k = 0
        end_life = (t_churn_first if t_churn_first is not None else END)
        base_lv = float(np.mean(v("population.active_share")[ctype]))
        while t_h < min(END, end_life + 30 * DAY) and t_h < END:
            d0 = dn(t_h - 30 * DAY)
            d1 = dn(t_h)
            mm = mask[d0:d1]
            level = float(lvl[d0:d1][mm].mean()) if mm.any() else 0.0
            tk_open = sum(1 for a, b in iv["ticket"] if a <= t_h < b)
            score = 100.0 * min(level * (0.35 + 0.8 * base_lv), 1.1) - 6 * tk_open + rng.normal(0, v("cs.health_noise_sd"))
            band_ = "red" if score < cuts[0] else "yellow" if score < cuts[1] else "green"
            k += 1
            hid = f"{aid}:{k:03d}"
            E(t_h, "record_status_changed", "gainsight", {"object": "health", "id": hid, "to": band_, "health_band_prev": prev, "open_ctas": open_cta,
                                                          "tenure_months": int((t_h - t_first_sub) // MONTH) + (0 if kind == "new" else 6)}, person=None)
            if band_ == "red" and prev != "red" and rng.random() < 0.8:
                cid = nid("t", "G")
                due = t_h + float(rng.uniform(*v("cs.cta_response_days"))) * DAY
                E(t_h + 60, "record_created", "gainsight", {"object": "cta", "id": cid, "to": "new", "cta_type": "risk", "priority": "high" if seg != "SMB" else "medium", "due_at": iso(due)})
                E(due, "record_status_changed", "gainsight", {"object": "cta", "id": cid, "to": "work_in_progress", "cta_type": "risk"})
                E(due + float(rng.uniform(2, 15)) * DAY, "record_status_changed", "gainsight", {"object": "cta", "id": cid, "to": "closed_success" if rng.random() < v("cs.cta_save_rate") else "closed_no_action", "cta_type": "risk"})
            prev = band_
            t_h += 30 * DAY

    # ---------------- visible rows
    contact_rows, ct_truth = [], []
    for c in people:
        li = c["lead_info"]
        cs_now = consent_at(c, END)
        hidden_acc = aid
        vis_acc = aid
        if c.get("unmatched"):
            vis_acc = None
        if c.get("wrong"):
            vis_acc = c["wrong"]
        if li is None:
            lead_kw = dict(lead_status=None, lead_source=None, lead_created_at=None, lead_converted_at=None)
        else:
            lead_kw = dict(lead_status=li["status"], lead_source=li["source"], lead_created_at=li["created"], lead_converted_at=li["converted"])
        contact_rows.append(dict(person_key=c["pk"], account_id=vis_acc, contact_ref=c["ref"], role=c["role"], seniority_band=c["seniority"],
                                 email_consent=cs_now, personal_email=c["personal"], first_seen_at=c["t_first"], left_account_at=c["left"], is_product_user=c["user"], **lead_kw))
        ct_truth.append(dict(person_key=c["pk"], contact_ref=c["ref"], true_account=aid, visible_account=vis_acc, is_champion=c["role"] == "champion",
                             wrongly_matched=bool(c.get("wrong")), also_in_account=None))
    if dup_id:
        noise_extra.append((None, "duplicate_account", json.dumps({"account": dup_id, "of": aid})))
        for c in people[:1]:
            contact_rows.append(dict(person_key=c["pk"], account_id=dup_id, contact_ref=c["ref"] + "-D", role=c["role"], seniority_band=c["seniority"],
                                     email_consent=consent_at(c, END), personal_email=c["personal"], first_seen_at=c["t_first"], left_account_at=None, is_product_user=False,
                                     lead_status=None, lead_source=None, lead_created_at=None, lead_converted_at=None))
            ct_truth.append(dict(person_key=c["pk"], contact_ref=c["ref"] + "-D", true_account=aid, visible_account=dup_id, is_champion=False, wrongly_matched=False, also_in_account=aid))
    if is_test:
        noise_extra.append((None, "test_account", json.dumps({"account": aid})))

    # account status snapshot
    last_sub = subs[-1] if subs else None
    if won and (churn_kind is None or (subs and subs[-1]["status"] == "active")):
        status = "customer"
    elif won and churn_kind:
        status = "churned"
    elif lost_final:
        status = "lost"
    else:
        status = "prospect"
    if won and subs and subs[-1]["status"] != "active" and subs[-1]["end_at"] <= END:
        status = "churned" if churn_kind or subs[-1]["status"] in ("cancelled", "expired", "past_due", "paused") else "customer"
    created = (t_lead if kind == "new" else (t_won - 45 * DAY))
    regime_first = "legacy_targeting" if created < X.reg2 else "randomised_holdout"
    cur = subs[-1] if subs else None
    acc = dict(account_id=aid, segment=seg, industry_band=industry, employee_band=emp, region=region, source=src if kind == "new" else pick(rng, v("population.source_mix")),
               created_at=created, first_won_at=first_won_at if (first_won_at is not None and first_won_at < END) else None, status=status,
               current_plan=plan if won else None, arr_band=amount_of(acv) if won else None, renewal_at=cur["end_at"] if cur and status == "customer" else None,
               strategic_flag=strategic, named_csm=named_csm, regime_first_seen=regime_first, holdout_group=holdout,
               holdout_assigned_at=max(created, X.reg2) if True else created, holdout_share=v("run.holdout_share"), holdout_strategy="random_hash",
               crm_ref=f"sf_{keyed_hash(sec, aid)[:14]}", billing_ref=f"cus_{keyed_hash(sec, 'b' + aid)[:14]}" if won else None,
               cs_ref=f"gs_{keyed_hash(sec, 'g' + aid)[:12]}" if won else None, domain_key=keyed_hash(sec, f"acct{i}.example"))
    acc_rows = [acc]
    if dup_id:
        d_ = dict(acc)
        d_.update(account_id=dup_id, status="prospect", first_won_at=None, current_plan=None, arr_band=None, renewal_at=None, billing_ref=None, cs_ref=None,
                  created_at=created + float(rng.uniform(1, 20)) * DAY, crm_ref=f"sf_{keyed_hash(sec, dup_id)[:14]}")
        acc_rows.append(d_)
    usage_df = pd.concat(usage, ignore_index=True) if usage else None
    truth = dict(unit_id=aid, kind=kind, prospect_type=P["ptype"], customer_type=ctype, fit_score=P["fit"],
                 intent_stage={"browser": "cold", "researcher": "researching", "evaluator": "evaluating", "locked_in": "researching"}[P["ptype"]],
                 incumbent_lock_in=P["lock"], champion_exit_hazard=champ_hazard * 12, usage_decay_rate=decay_rate, decay_mode=decay_state["mode"],
                 budget_cycle_month=budget_m, competitor_win_prob=float(np.clip(1 - P["fit"] * 0.8, 0, 1) * (1.2 if P["comp"] else 0.3)), expansion_headroom=headroom,
                 acv=ret_acv, seats_true=seats0, integration_connected=integ, reacts_badly=reacts_badly, uplift_prospect=json.dumps(uplift_p),
                 uplift_customer=json.dumps(uplift_c), p_win_base=p_win_noact if p_win_noact is not None else None, will_win=bool(won),
                 churn_kind=churn_kind, churn_at=t_churn_first, renewal_outcomes=json.dumps(churn_info["outcomes"]) if churn_info["outcomes"] else None,
                 is_test_account=is_test, duplicate_of=None, champion_left_at=champ_left_at)
    truths = [truth]
    return dict(accounts=acc_rows, contacts=contact_rows, events=ev, opps=opps, usage=usage_df, subs=subs, invs=invs, actions=acts,
                account_truth=truths, contact_truth=ct_truth, opp_truth=optruth, noise_extra=noise_extra)
