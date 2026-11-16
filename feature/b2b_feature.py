"""
b2b_features.py  -  point-in-time feature engineering for the B2B SaaS vertical (M1 to M4).

Needs bfsi_features.py in the same folder (it provides the shared helpers: the (unit, time) index,
millisecond conversion, the split function). Reads the VISIBLE B2B tables only (never the hidden ones).

Writes, into --out-dir:

    b2b_m1.parquet               prospect account x month           y_won_90d  (+ y_won_90d_crm)
    b2b_m2.parquet               subscription term                  y_lapse
    b2b_m2_invoice.parquet       invoice at issue                   y_invoice_late (secondary)
    b2b_m3.parquet               randomised decision                outcomes by trigger + treatment columns
    b2b_m3_cohort_uplift.csv     COHORT-level uplift with bootstrap intervals (no per-account scores)
    b2b_m4.parquet               account-week                       y4_outcome (prospects and customers)
    b2b_m4_cohort_summary.csv    observed outcome shares by cohort with bootstrap intervals
    b2b_feature_dictionary.csv   column list with the family each feature belongs to

Run:
    python b2b_features.py --data-dir D:\\...\\out_b2b_saas\\visible --out-dir D:\\...\\features_b2b
    python b2b_features.py --data-dir ... --out-dir ... --only m1 m2        (subset)
    python b2b_features.py --data-dir ... --out-dir ... --no-events         (events.parquet not used)

Same rules as the BFSI code: every feature is computed as of prediction_time t from rows whose own
timestamp (ingested_at for events and usage) is <= t; extract-time snapshot columns are never read
(LEAKY_COLUMNS); a label is final only when its window plus a buffer has passed; missing history is NaN
with a has_* flag, never zero.
Needs only: pandas, numpy, pyarrow.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import warnings

import numpy as np
import pandas as pd

import bfsi_features as bf
from bfsi_features import Idx, ms, from_ms, days, ordinal, downcast, assign_split, DAY, BIG, NAT, EXTRACT

warnings.filterwarnings("ignore", category=pd.errors.PerformanceWarning)

# --------------------------------------------------------------------------- config
# Buffers after the label window. They reproduce the counts in the Feature Engineering Report:
# M1 snapshots end Jul 2026 (window 90 + 30), M2 term ends are final 45 days after end_at (the window itself).
BUFFER_M1 = 30
BUFFER_M2 = 0
BUFFER_M3 = 45
BUFFER_M4 = 45
M4_INACTIVE_SAMPLE = 0.05          # share of weeks kept for prospects with no event / state change / action
M4_HORIZON_DAYS = 90
M4_CHUNK = 300_000
BOOTSTRAP_REPS = 300
LATE_GRACE_DAYS = 1                # an invoice is late only if paid more than this many days after due (or never paid)
RANDOM_SEED = 7
W7, W30, W60, W90 = 7 * DAY, 30 * DAY, 60 * DAY, 90 * DAY

OPTIONAL_ACTIONS = ["rep_outreach", "email", "discount", "csm_task", "exec_call"]
STATES = ["Lead", "Opportunity", "Competitor displacement", "Onboarding", "Active", "Expansion",
          "At-risk renewal", "Churned", "Lost"]
JOURNEY_GROUP = {"Lead": "acquire", "Opportunity": "acquire", "Competitor displacement": "acquire",
                 "Onboarding": "grow_retain", "Active": "grow_retain", "Expansion": "grow_retain",
                 "At-risk renewal": "grow_retain", "Churned": "win_back_exit", "Lost": "win_back_exit"}
SOURCE_GROUP = {"inbound": "owned", "referral": "referral_partner", "partner": "referral_partner",
                "outbound": "sales_led", "competitor_displacement": "sales_led", "event": "event"}
BAND_EMPLOYEE = {"1-50": 1, "51-200": 2, "201-1000": 3, "1001+": 4}
BAND_MRR = {"<5k": 1, "5-10k": 2, "10-25k": 3, "25-50k": 4, "50-100k": 5, "100-250k": 6, "250k+": 7}
SENIORITY = {"ic": 1, "manager": 2, "director": 3, "vp": 4, "c_level": 5}
PAGES = ["pricing", "demo", "docs", "security", "integrations", "case_study", "blog", "home"]
USAGE_FEATURES = ["login", "dashboard", "report", "admin_settings", "api_call", "export", "integration_connected",
                  "invite_sent", "seat_added"]
FLAG_KEYS = ["rep_already_engaged", "open_ticket", "strategic_account", "no_consent_reachable", "champion_left",
             "payment_failed", "in_legal_review"]

# Columns that hold an extract-time snapshot or an outcome. Feature code never reads them.
LEAKY_COLUMNS = {
    "accounts": ["status", "current_plan", "arr_band", "renewal_at"],
    "contacts": ["email_consent", "lead_status", "lead_converted_at"],
    "opportunities": ["stage", "is_won", "esign_status", "esign_changed_at", "close_date"],   # closed_at only as of t
    "subscriptions": ["status", "status_changed_at", "cancel_requested", "pause_collection", "seats_active_band"],
    "invoices": ["status", "attempt_count", "error_code"],                                     # as of t from timestamps only
    "actions": ["final_status", "expected_value", "reason_codes", "propensity"],
}

TABLES = ["accounts", "contacts", "opportunities", "subscriptions", "invoices", "actions", "state_history",
          "product_usage_daily"]


# --------------------------------------------------------------------------- loading
def load_tables(data_dir: str, use_events: bool = True):
    t = {n: pd.read_parquet(os.path.join(data_dir, f"{n}.parquet")) for n in TABLES}
    ev = None
    p = os.path.join(data_dir, "events.parquet")
    if use_events and os.path.exists(p):
        ev = pd.read_parquet(p, columns=["event_id", "source_event_id", "event_type", "source_system", "unit_id",
                                         "occurred_at", "ingested_at", "channel", "consent_status", "properties"])
    return t, ev


def prep_events(ev: pd.DataFrame) -> pd.DataFrame:
    n0 = len(ev)
    ev = ev[ev["unit_id"].notna()].copy()
    ev = ev[~ev["event_id"].str.startswith("BOT")]                       # bot page views (the ones with no page)
    ev = ev[ev["occurred_at"] <= ev["ingested_at"]]
    ev = ev.sort_values("ingested_at", kind="stable").drop_duplicates("source_event_id", keep="first")
    p = ev["properties"].fillna("")

    def ex(pat):
        return p.str.extract(pat)[0]

    ev["obj"] = ex(r'"object":"([^"]*)"')
    ev["to"] = ex(r'"to":"([^"]*)"')
    ev["oid"] = ex(r'"id":"([^"]*)"')
    ev["page"] = ex(r'"page":"([^"]*)"')
    ev["session_id"] = ex(r'"session_id":\s*"?(\d+)')
    ev["pstatus"] = ex(r'"status":"([^"]*)"')
    ev["pchannel"] = ex(r'"channel":"([^"]*)"')
    ev["login_type"] = ex(r'"login_type":"([^"]*)"')
    ev["health_prev"] = ex(r'"health_band_prev":"([^"]*)"')
    ev["open_ctas"] = pd.to_numeric(ex(r'"open_ctas":\s*(\d+)'), errors="coerce")
    ev["csat"] = pd.to_numeric(ex(r'"csat":\s*(\d+)'), errors="coerce")
    ev["cancel_flag"] = p.str.contains('"cancel_flag":true').astype("float64")
    ev["superseded"] = p.str.contains('"superseded":true').astype("float64")
    ev = ev.drop(columns=["properties"])
    print(f"  events: {n0:,} rows -> {len(ev):,} after dedupe / bots / unlinked / bad timestamps")
    return ev


# --------------------------------------------------------------------------- context
class Ctx:
    def __init__(self, T: dict, events: pd.DataFrame | None):
        self.T = T
        acc = T["accounts"]
        self.units = pd.Index(acc["account_id"])
        self.acc = acc.set_index("account_id")
        self.acc_created = ms(acc["created_at"])
        self.acc_first_won = ms(acc["first_won_at"])
        self._contacts()
        self._opps()
        self._subs()
        self._invoices()
        self._usage()
        self._states()
        self._actions()
        self.has_events = events is not None
        if events is not None:
            self._events(events)

    def u(self, s) -> np.ndarray:
        return self.units.get_indexer(s).astype("int64")

    # ---- contacts ------------------------------------------------------------------------------
    def _contacts(self):
        c = self.T["contacts"].copy()
        c["u"] = self.u(c["account_id"])
        sen = c["seniority_band"].map(SENIORITY).to_numpy("float64")
        v = dict(one=np.ones(len(c)), champ=(c["role"] == "champion").to_numpy("float64"),
                 econ=(c["role"] == "economic_buyer").to_numpy("float64"),
                 personal=c["personal_email"].astype("float64").to_numpy(),
                 produser=c["is_product_user"].astype("float64").to_numpy(),
                 **{f"s{k}": (sen == k).astype("float64") for k in range(1, 6)})
        self.i_cont = Idx(c["u"], ms(c["first_seen_at"]), **v)
        self.i_cont_left = Idx(c["u"], ms(c["left_account_at"]), **v)
        ld = c[c["lead_created_at"].notna()]
        self.i_lead = Idx(ld["u"], ms(ld["lead_created_at"]), src=ld["lead_source"].fillna("unknown").to_numpy(dtype=object))

    # ---- opportunities -------------------------------------------------------------------------
    def _opps(self):
        o = self.T["opportunities"].copy()
        o["u"] = self.u(o["account_id"])
        o["created"] = ms(o["created_at"])
        o["closed"] = ms(o["closed_at"], nat=BIG - 1)               # still open = far future
        o["closed"] = np.maximum(o["closed"], o["created"])         # data defect: 2 rows close before they open
        won = o["is_won"].astype(str).str.lower().eq("true").to_numpy("float64")
        self.opps = o.assign(won=won)
        self.i_opp = Idx(o["u"], o["created"], amt=ordinal(o["amount_band"], BAND_MRR),
                         comp=o["competitor_flag"].astype("float64").to_numpy(),
                         inc=o["incumbent_vendor_band"].notna().to_numpy("float64"),
                         inc_end=ms(o["incumbent_contract_end"]).astype("float64"), legal=o["legal_review"].astype("float64").to_numpy(),
                         closed=o["closed"].to_numpy(), created=o["created"].to_numpy(),
                         otype=o["type"].fillna("").to_numpy(dtype=object), one=np.ones(len(o)))
        cl = o[o["closed_at"].notna()]
        w = won[o["closed_at"].notna().to_numpy()]
        self.i_opp_closed = Idx(cl["u"], cl["closed"], won=w, lost=1 - w, one=np.ones(len(cl)))
        lost = cl[w == 0]
        self.i_opp_lost = Idx(lost["u"], lost["closed"], cat=lost["loss_category"].fillna("unknown").to_numpy(dtype=object))
        won_o = cl[w == 1]
        self.i_opp_won = Idx(won_o["u"], won_o["closed"], otype=won_o["type"].to_numpy(dtype=object), one=np.ones(len(won_o)))
        self.i_opp_exp_won = Idx(won_o.loc[won_o["type"] == "expansion", "u"], won_o.loc[won_o["type"] == "expansion", "closed"])
        self.i_opp_ren_won = Idx(won_o.loc[won_o["type"] == "renewal", "u"], won_o.loc[won_o["type"] == "renewal", "closed"])

    # ---- subscriptions -------------------------------------------------------------------------
    def _subs(self):
        s = self.T["subscriptions"].copy()
        s["u"] = self.u(s["account_id"])
        s["st"] = ms(s["start_at"])
        s["en"] = ms(s["end_at"], nat=BIG - 1)
        term_start = s.groupby("subscription_id")["st"].transform("min")
        s["amend"] = (s["st"] > term_start).astype("float64")
        s["mrr_ord"] = ordinal(s["mrr_band"], BAND_MRR)
        self.subs = s
        self.i_sub = Idx(s["u"], s["st"], seats=s["seats_bought"].to_numpy("float64"),
                         plan=s["plan"].fillna("none").to_numpy(dtype=object),
                         interval=s["billing_interval"].fillna("none").to_numpy(dtype=object),
                         coll=s["collection_method"].fillna("none").to_numpy(dtype=object),
                         term=s["term_months"].to_numpy("float64"), auto=s["auto_renew_flag"].astype("float64").to_numpy(),
                         mrr=s["mrr_ord"].to_numpy(), version=s["version"].to_numpy("float64"),
                         end=s["en"].to_numpy(), amend=s["amend"].to_numpy())
        # terms (one row per subscription_id): start, end, account
        T = s.groupby("subscription_id").agg(account_id=("account_id", "first"), u=("u", "first"), st=("st", "min"),
                                             en=("en", "max"), interval=("billing_interval", "first")).reset_index()
        self.terms = T
        self.i_term = Idx(T["u"], T["st"], one=np.ones(len(T)))
        self.i_first_sub = Idx(T["u"], T["st"])                      # first subscription start of an account = min over terms

    # ---- invoices ------------------------------------------------------------------------------
    def _invoices(self):
        i = self.T["invoices"].copy()
        i["u"] = self.u(i["account_id"])
        i["iss"] = ms(i["issued_at"])
        i["due"] = ms(i["due_at"])
        i["paid"] = ms(i["paid_at"])
        i["late_days"] = np.where(i["paid"] != NAT, np.maximum((i["paid"] - i["due"]) / DAY, 0), np.nan)
        i["is_late"] = np.where(i["paid"] != NAT, (i["paid"] > i["due"] + LATE_GRACE_DAYS * DAY).astype("float64"), np.nan)   # auto-charge lands seconds after due: 1-day grace
        i["amt_ord"] = ordinal(i["amount_band"], BAND_MRR)
        self.inv = i
        self.i_inv_iss = Idx(i["u"], i["iss"], amt=i["amt_ord"].to_numpy(), one=np.ones(len(i)))
        p = i[i["paid"] != NAT]
        self.i_inv_paid = Idx(p["u"], p["paid"], late=p["is_late"].to_numpy(), days_late=p["late_days"].to_numpy(), one=np.ones(len(p)))
        f = i[i["status"] == "failed"]
        self.i_inv_fail = Idx(f["u"], f["due"], one=np.ones(len(f)))   # a failed invoice is known once it is due
        d = i[i["disputed"].astype(bool)]
        self.i_inv_disp = Idx(d["u"], d["due"], one=np.ones(len(d)))

    # ---- product usage -------------------------------------------------------------------------
    def _usage(self):
        p = self.T["product_usage_daily"]
        p = p[p["account_id"].notna()].copy()
        p["u"] = self.u(p["account_id"])
        p = p[p["u"] >= 0]
        p["i"] = ms(p["ingested_at"])
        self.usage = p
        ev_cols = {f"ev_{f}": np.where(p["feature"] == f, p["num_events"], 0).astype("float64") for f in USAGE_FEATURES}
        self.i_use = Idx(p["u"], p["i"], one=np.ones(len(p)), **ev_cols)
        self.i_use_feat = {f: Idx(p.loc[p["feature"] == f, "u"], p.loc[p["feature"] == f, "i"]) for f in USAGE_FEATURES}
        day = p.assign(d=p["day"].astype("int64") if False else ms(p["day"]) // DAY).groupby(["u", "d"])["i"].min().reset_index()
        self.i_use_day = Idx(day["u"], day["i"])                 # first ingest time of each active day
        pk = pd.factorize(p["person_key"].fillna("none"))[0]
        order = np.lexsort((p["i"].to_numpy(), p["u"].to_numpy()))
        self._use_u = p["u"].to_numpy()[order]
        self._use_t = p["i"].to_numpy()[order]
        self._use_p = pk[order]
        self._use_start = {}
        for uu in np.unique(self._use_u):
            lo = np.searchsorted(self._use_u, uu, "left")
            hi = np.searchsorted(self._use_u, uu, "right")
            self._use_start[uu] = (lo, hi)

    def distinct_users(self, u, t, w):
        out = np.zeros(len(u))
        cnt = self.i_use.count(u, t, w)
        for k in np.where(cnt > 0)[0]:
            lo, hi = self._use_start[u[k]]
            tt = self._use_t[lo:hi]
            sel = (tt > t[k] - w) & (tt <= t[k])
            out[k] = len(np.unique(self._use_p[lo:hi][sel]))
        return out

    # ---- state history -------------------------------------------------------------------------
    def _states(self):
        s = self.T["state_history"].copy()
        s["u"] = self.u(s["unit_id"])
        s["e"] = ms(s["entered_at"])
        sc = s["state"].map({k: i for i, k in enumerate(STATES)}).to_numpy("float64")
        flags = {f"f_{k}": bf.parse_flags(s["flags"], k) for k in FLAG_KEYS}
        self.i_state = Idx(s["u"], s["e"], state=s["state"].to_numpy(dtype=object), by=s["entered_by"].to_numpy(dtype=object),
                           **flags, **{f"s{i}": (sc == i).astype("float64") for i in range(len(STATES))})
        self.state_df = s

    # ---- actions -------------------------------------------------------------------------------
    def _actions(self):
        a = self.T["actions"].copy()
        a["u"] = self.u(a["unit_id"])
        a["d"] = ms(a["decided_at"])
        a["sent"] = ms(a["sent_at"])
        ch = a["chosen_action"].fillna("")
        dec = a["record_kind"] == "decision"
        a["is_dec"] = dec.astype("float64")
        a["is_dn"] = (dec & (ch == "do_nothing")).astype("float64")
        a["is_opt"] = ch.isin(OPTIONAL_ACTIONS).astype("float64")
        a["is_block"] = (dec & a["blocked_actions"].notna()).astype("float64")
        a["is_block_cons"] = a["blocked_actions"].fillna("").str.contains("consent").astype("float64")
        a["is_call"] = ((a["channel"] == "call") | ch.isin(["rep_outreach", "exec_call"])).astype("float64")
        disp = a["disposition"].fillna("")
        a["is_rep"] = (ch == "rep_outreach").astype("float64")
        a["is_meeting"] = (disp == "meeting_booked").astype("float64")
        a["is_connected"] = (disp == "connected").astype("float64")
        a["has_disp"] = (disp != "").astype("float64")
        a["is_csm"] = (ch == "csm_task").astype("float64")
        a["is_exec"] = (ch == "exec_call").astype("float64")
        a["is_risk"] = (dec & (a["trigger"] == "risk")).astype("float64")
        self.actions = a
        la = ch.map({k: i + 1 for i, k in enumerate(["do_nothing"] + OPTIONAL_ACTIONS)}).fillna(0).to_numpy("float64")
        self.last_action_names = ["none", "do_nothing"] + OPTIONAL_ACTIONS
        cols = ["is_dec", "is_dn", "is_opt", "is_block", "is_block_cons", "is_call", "is_rep", "is_csm", "is_exec", "is_risk"]
        self.i_act = Idx(a["u"], a["d"], last_action=la, **{k: a[k].to_numpy() for k in cols})
        # call outcomes (disposition) are known only after the call: a one-day lag is applied in the feature
        self.i_act_disp = Idx(a["u"], a["d"], meeting=a["is_meeting"].to_numpy(), conn=a["is_connected"].to_numpy(),
                              hasd=a["has_disp"].to_numpy(), rep=a["is_rep"].to_numpy())
        o = a[a["is_opt"] > 0]
        self.i_act_opt = Idx(o["u"], o["d"])
        ig = a[a["task_status"] == "ignored"]
        self.i_task_ign = Idx(ig["u"], ms(ig["task_due_at"]))
        s = a[a["sent"] != NAT]
        cat = s["category"].fillna("")
        self.i_sent = {"all": Idx(s["u"], s["sent"]),
                       "promo": Idx(s.loc[cat == "promotional", "u"], s.loc[cat == "promotional", "sent"]),
                       "reg": Idx(s.loc[cat.isin(["regulatory", "transactional"]), "u"], s.loc[cat.isin(["regulatory", "transactional"]), "sent"])}
        for chn in ["email", "call", "in_app"]:
            m = s["channel"] == chn
            self.i_sent[chn] = Idx(s.loc[m, "u"], s.loc[m, "sent"])

    # ---- events --------------------------------------------------------------------------------
    def _events(self, ev: pd.DataFrame):
        ev = ev.copy()
        ev["u"] = self.u(ev["unit_id"])
        ev["i"] = ms(ev["ingested_at"])
        ev = ev[ev["u"] >= 0]
        E = lambda m: ev[m]
        pv = E((ev["event_type"] == "page_view"))
        pages = {f"p_{p}": (pv["page"] == p).to_numpy("float64") for p in PAGES}
        self.i_pv = Idx(pv["u"], pv["i"], **pages)
        sess = pv.dropna(subset=["session_id"]).groupby(["u", "session_id"])["i"].min().reset_index()
        self.i_sess = Idx(sess["u"], sess["i"])
        co = E((ev["event_type"] == "consent_change") & (ev["pchannel"].fillna("email") == "email"))
        st = co["consent_status"].fillna(co["pstatus"]).fillna("none")
        self.i_consent = Idx(co["u"], co["i"], status=st.to_numpy(dtype=object), wd=(st == "withdrawn").to_numpy("float64"))
        km = E((ev["source_system"] == "klaviyo") & (ev["event_type"] == "message_status"))
        self.i_msg = {s_: Idx(km.loc[km["pstatus"] == s_, "u"], km.loc[km["pstatus"] == s_, "i"])
                      for s_ in ["sent", "delivered", "opened", "clicked", "bounced", "unsubscribed"]}
        self.i_reg = Idx(E((ev["source_system"] == "cvent") & (ev["event_type"] == "record_created"))["u"],
                         E((ev["source_system"] == "cvent") & (ev["event_type"] == "record_created"))["i"])
        att = E((ev["source_system"] == "cvent") & (ev["event_type"] == "record_status_changed") & (ev["to"] == "attended"))
        self.i_attend = Idx(att["u"], att["i"])
        hs = E((ev["source_system"] == "hubspot") & (ev["event_type"] == "record_created"))
        self.i_form = Idx(hs["u"], hs["i"])
        so = E((ev["source_system"] == "salesforce") & (ev["event_type"] == "record_status_changed") & (ev["obj"] == "opportunity"))
        self.i_opp_stage = Idx(so["u"], so["i"], stage=so["to"].fillna("none").to_numpy(dtype=object))
        ds = E((ev["source_system"] == "docusign") & (ev["event_type"] == "record_status_changed"))
        self.i_esign = Idx(ds["u"], ds["i"], stage=ds["to"].fillna("none").to_numpy(dtype=object))
        sb = E((ev["source_system"] == "stripe") & (ev["event_type"] == "record_status_changed") & (ev["obj"] == "subscription"))
        self.i_stripe = Idx(sb["u"], sb["i"], cancel=sb["cancel_flag"].to_numpy(), status=sb["to"].fillna("none").to_numpy(dtype=object))
        zd = ev[ev["source_system"] == "zendesk"]
        zc = zd[zd["event_type"] == "record_created"]
        self.i_tix = Idx(zc["u"], zc["i"])
        zs = zd[(zd["event_type"] == "record_status_changed") & zd["to"].isin(["solved", "closed"])]
        first_solved = zs.groupby(["u", "oid"])["i"].min().reset_index()
        self.i_tix_solved = Idx(first_solved["u"], first_solved["i"])
        self.i_tix_reopen = Idx(zd.loc[(zd["event_type"] == "record_status_changed") & (zd["to"] == "open"), "u"],
                                zd.loc[(zd["event_type"] == "record_status_changed") & (zd["to"] == "open"), "i"])
        cs = zd[zd["csat"].notna()]
        self.i_csat = Idx(cs["u"], cs["i"], csat=cs["csat"].to_numpy("float64"))
        gs = E((ev["source_system"] == "gainsight") & (ev["event_type"] == "record_status_changed") & (ev["obj"] == "health"))
        self.i_health = Idx(gs["u"], gs["i"], band=gs["to"].fillna("none").to_numpy(dtype=object), ctas=gs["open_ctas"].to_numpy("float64"))
        gc = E((ev["source_system"] == "gainsight") & (ev["event_type"] == "record_created"))
        self.i_cta = Idx(gc["u"], gc["i"])
        ok = E((ev["source_system"] == "okta") & (ev["event_type"] == "record_created"))
        self.i_login = Idx(ok["u"], ok["i"], sso=ok["login_type"].fillna("").str.contains("sso|saml", case=False).to_numpy("float64"))
        am = E((ev["source_system"] == "amplitude") & (ev["to"] == "first_value_reached"))
        self.i_firstvalue = Idx(am["u"], am["i"])


# --------------------------------------------------------------------------- feature blocks
def nanfill(names, n):
    return {k: np.full(n, np.nan) for k in names}


def block_account(c: Ctx, sp: dict) -> dict:
    t = sp["t"]
    b = c.acc.reindex(sp["unit_id"])
    created = ms(b["created_at"])
    f = {"segment": b["segment"].to_numpy(), "industry_band": b["industry_band"].to_numpy(),
         "employee_band": ordinal(b["employee_band"], BAND_EMPLOYEE), "region": b["region"].to_numpy(),
         "source": b["source"].to_numpy(), "acq__channel_group": b["source"].map(SOURCE_GROUP).fillna("other").to_numpy(),
         "strategic_flag": b["strategic_flag"].astype("float64").to_numpy(), "named_csm": b["named_csm"].astype("float64").to_numpy(),
         "regime_first_seen": b["regime_first_seen"].to_numpy(), "account_age_days": days(t, created)}
    f["tenure__log_days"] = np.log1p(np.maximum(f["account_age_days"], 0))
    return f


def block_time(c: Ctx, sp: dict) -> dict:                        # B2B: UTC
    loc = from_ms(sp["t"])
    h, wd = loc.dt.hour.to_numpy("float64"), loc.dt.weekday.to_numpy("float64")
    return {"time__weekday": wd, "time__day_of_month": loc.dt.day.to_numpy("float64"), "time__month": loc.dt.month.to_numpy("float64"),
            "time__is_month_end": loc.dt.is_month_end.to_numpy("float64"), "time__hour": h,
            "time__weekday_sin": np.sin(2 * np.pi * wd / 7), "time__weekday_cos": np.cos(2 * np.pi * wd / 7)}


def block_state(c: Ctx, sp: dict) -> dict:
    u, t = sp["u"], sp["t"]
    I = c.i_state
    pos, prev = I.last(u, t), I.last(u, t, back=1)
    st = I.get("state", pos, fill="no_state")
    f = {"state__current": st, "state__days_in": days(t, I.time_at(pos)), "state__entered_by": I.get("by", pos, fill="none"),
         "state__previous": I.get("state", prev, fill="none"), "state__changes__90d": I.count(u, t, W90),
         "state__journey_group": pd.Series(st).map(JOURNEY_GROUP).fillna("none").to_numpy()}
    for k in FLAG_KEYS:
        f[f"state__flag_{k}"] = I.get(f"f_{k}", pos)
    for i, name in enumerate(STATES):
        f["state__ever_" + name.lower().replace(" ", "_").replace("-", "_")] = (I.total(f"s{i}", u, t) > 0).astype("float64")
    return f


def block_contacts(c: Ctx, sp: dict) -> dict:
    u, t = sp["u"], sp["t"]
    F, L = c.i_cont, c.i_cont_left
    net = lambda col: F.total(col, u, t) - L.total(col, u, t)
    n = net("one")
    f = {"n_contacts": n, "n_contacts_90d": F.count(u, t, W90), "contacts_left": L.count(u, t)}
    f["has_champion"] = (net("champ") > 0).astype("float64")
    f["has_economic_buyer"] = (net("econ") > 0).astype("float64")
    mx = np.full(len(u), np.nan)
    for k in range(1, 6):
        mx = np.where(net(f"s{k}") > 0, k, mx)
    f["max_seniority"] = mx
    f["champion_left"] = (L.total("champ", u, t) > 0).astype("float64")
    with np.errstate(invalid="ignore", divide="ignore"):
        f["personal_email_share"] = np.where(n > 0, net("personal") / n, np.nan)
        f["is_product_user_share"] = np.where(n > 0, net("produser") / n, np.nan)
    lp = c.i_lead.last(u, t)
    f["lead_source"] = c.i_lead.get("src", lp, fill="none")
    f["days_since_lead"] = days(t, c.i_lead.time_at(lp))
    return f


def block_sales(c: Ctx, sp: dict) -> dict:
    u, t = sp["u"], sp["t"]
    O, C = c.i_opp, c.i_opp_closed
    created, closed = O.count(u, t), C.count(u, t)
    pos = O.last(u, t)
    cl_at = O.get("closed", pos)
    f = {"rf__opps_total": created, "rf__opps__90d": O.count(u, t, W90), "n_open_opps": created - closed,
         "has_opportunity": (created > 0).astype("float64"),
         "opp_age_days": days(t, O.time_at(pos)), "opp_latest_open": np.where(pos >= 0, (cl_at > t).astype("float64"), np.nan),
         "opp_amount_band": O.get("amt", pos), "competitor_flag": O.get("comp", pos),
         "has_incumbent": O.get("inc", pos), "legal_review": O.get("legal", pos),
         "days_to_incumbent_contract_end": days(O.get("inc_end", pos), t),
         "prior_lost_opps": C.total("lost", u, t), "prior_won_opps": C.total("won", u, t)}
    f["opp_type_latest"] = O.get("otype", pos, fill="none")
    lp = c.i_opp_lost.last(u, t)
    f["last_loss_category"] = c.i_opp_lost.get("cat", lp, fill="none")
    f["rf__days_since_last_opp"] = days(t, O.time_at(pos))
    # sales-rep activity (disposition known a day after the call)
    D, tt = c.i_act_disp, t - 1 - DAY
    f["rep_touches_30d"] = c.i_act.total("is_rep", u, t - 1, W30)
    f["meetings_booked_90d"] = D.total("meeting", u, tt, W90)
    conn, hasd = D.total("conn", u, tt, W30), D.total("hasd", u, tt, W30)
    with np.errstate(invalid="ignore", divide="ignore"):
        f["connect_rate_30d"] = np.where(hasd > 0, conn / hasd, np.nan)
    if c.has_events:
        sp_ = c.i_opp_stage.last(u, t)
        f["opp_stage_at_t"] = c.i_opp_stage.get("stage", sp_, fill="none")           # from events, not opportunities.stage
        f["esign_stage_at_t"] = c.i_esign.get("stage", c.i_esign.last(u, t), fill="none")
    else:
        f["opp_stage_at_t"] = np.full(len(u), None, dtype=object)
        f["esign_stage_at_t"] = np.full(len(u), None, dtype=object)
    return f


def block_actions(c: Ctx, sp: dict) -> dict:
    u, t = sp["u"], sp["t"] - 1
    I = c.i_act
    f = {"act__decisions__30d": I.total("is_dec", u, t, W30), "act__decisions__90d": I.total("is_dec", u, t, W90),
         "act__do_nothing__30d": I.total("is_dn", u, t, W30), "act__blocked__30d": I.total("is_block", u, t, W30),
         "act__blocked_consent__30d": I.total("is_block_cons", u, t, W30), "act__calls__30d": I.total("is_call", u, t, W30),
         "act__optional__30d": I.total("is_opt", u, t, W30), "act__tasks_ignored__90d": c.i_task_ign.count(u, t - 3 * DAY, W90),
         "csm_tasks_90d": I.total("is_csm", u, t, W90), "exec_calls_90d": I.total("is_exec", u, t, W90),
         "risk_triggers_90d": I.total("is_risk", u, t, W90)}
    pos = I.last(u, t)
    f["act__last_action"] = np.array(c.last_action_names, dtype=object)[np.nan_to_num(I.get("last_action", pos, fill=0.0)).astype(int)]
    f["act__days_since_last_optional"] = days(t, c.i_act_opt.time_at(c.i_act_opt.last(u, t)))
    for k, name in [("all", "all"), ("promo", "promo"), ("reg", "regulatory"), ("email", "email"), ("call", "call"), ("in_app", "in_app")]:
        f[f"msg__sent_{name}__30d"] = c.i_sent[k].count(u, t, W30)
    f["msg__sent_all__7d"] = c.i_sent["all"].count(u, t, W7)
    f["msg__days_since_last"] = days(t, c.i_sent["all"].time_at(c.i_sent["all"].last(u, t)))
    return f


def block_web_marketing(c: Ctx, sp: dict) -> dict:
    u, t = sp["u"], sp["t"]
    names = ["web__page_views__7d", "web__page_views__30d", "web__page_views__90d", "web__sessions__30d", "web__days_since_last_visit",
             "web__trend", "web__has_history"] + [f"web__{p}_views__30d" for p in PAGES] + \
            ["mkt__emails_delivered__30d", "mkt__emails_opened__30d", "mkt__emails_clicked__30d", "mkt__open_rate__30d",
             "mkt__click_rate__30d", "mkt__unsubscribed_ever", "mkt__event_registrations__90d", "mkt__events_attended__90d",
             "mkt__form_fills__30d", "consent__email_days_since_change", "consent__email_ever_withdrawn", "mkt__first_value_reached"]
    if not c.has_events:
        f = nanfill(names, len(u))
        f["consent__email"] = np.full(len(u), None, dtype=object)
        return f
    f = {}
    for w, lab in [(W7, "7d"), (W30, "30d"), (W90, "90d")]:
        f[f"web__page_views__{lab}"] = c.i_pv.count(u, t, w)
    f["web__sessions__30d"] = c.i_sess.count(u, t, W30)
    with np.errstate(invalid="ignore", divide="ignore"):
        f["web__trend"] = np.where(f["web__page_views__30d"] > 0, f["web__page_views__7d"] / (f["web__page_views__30d"] / 4.0), np.nan)
    f["web__days_since_last_visit"] = days(t, c.i_pv.time_at(c.i_pv.last(u, t)))
    f["web__has_history"] = (c.i_pv.count(u, t) > 0).astype("float64")
    for p in PAGES:
        f[f"web__{p}_views__30d"] = c.i_pv.total(f"p_{p}", u, t, W30)
    S = c.i_msg
    dlv, opn, clk = S["delivered"].count(u, t, W30), S["opened"].count(u, t, W30), S["clicked"].count(u, t, W30)
    f["mkt__emails_delivered__30d"], f["mkt__emails_opened__30d"], f["mkt__emails_clicked__30d"] = dlv, opn, clk
    with np.errstate(invalid="ignore", divide="ignore"):
        f["mkt__open_rate__30d"] = np.where(dlv > 0, opn / dlv, np.nan)
        f["mkt__click_rate__30d"] = np.where(dlv > 0, clk / dlv, np.nan)
    f["mkt__unsubscribed_ever"] = (S["unsubscribed"].count(u, t) > 0).astype("float64")
    f["mkt__event_registrations__90d"] = c.i_reg.count(u, t, W90)
    f["mkt__events_attended__90d"] = c.i_attend.count(u, t, W90)
    f["mkt__form_fills__30d"] = c.i_form.count(u, t, W30)
    cp = c.i_consent.last(u, t)
    f["consent__email"] = c.i_consent.get("status", cp, fill="none")            # no record = none = hold
    f["consent__email_days_since_change"] = days(t, c.i_consent.time_at(cp))
    f["consent__email_ever_withdrawn"] = (c.i_consent.total("wd", u, t) > 0).astype("float64")
    f["mkt__first_value_reached"] = (c.i_firstvalue.count(u, t) > 0).astype("float64")
    return f


def block_support_health(c: Ctx, sp: dict) -> dict:
    u, t = sp["u"], sp["t"]
    names = ["support__tickets__90d", "support__open_at_t", "support__last_csat", "support__reopens__90d", "health_band_at_t",
             "open_ctas_at_t", "ctas_created__90d", "logins__30d", "login_sso_share__30d", "sub__cancel_flag_at_t", "sub__stripe_status_at_t"]
    if not c.has_events:
        f = nanfill(names, len(u))
        for k in ["health_band_at_t", "sub__stripe_status_at_t"]:
            f[k] = np.full(len(u), None, dtype=object)
        return f
    f = {"support__tickets__90d": c.i_tix.count(u, t, W90)}
    f["support__open_at_t"] = ((c.i_tix.count(u, t) - c.i_tix_solved.count(u, t)) > 0).astype("float64")
    f["support__last_csat"] = c.i_csat.get("csat", c.i_csat.last(u, t))
    f["support__reopens__90d"] = c.i_tix_reopen.count(u, t, W90)
    hp = c.i_health.last(u, t)
    f["health_band_at_t"] = c.i_health.get("band", hp, fill="none")
    f["open_ctas_at_t"] = c.i_health.get("ctas", hp)
    f["ctas_created__90d"] = c.i_cta.count(u, t, W90)
    lg = c.i_login.count(u, t, W30)
    f["logins__30d"] = lg
    with np.errstate(invalid="ignore", divide="ignore"):
        f["login_sso_share__30d"] = np.where(lg > 0, c.i_login.total("sso", u, t, W30) / lg, np.nan)
    sp_ = c.i_stripe.last(u, t)
    f["sub__cancel_flag_at_t"] = c.i_stripe.get("cancel", sp_)
    f["sub__stripe_status_at_t"] = c.i_stripe.get("status", sp_, fill="none")
    return f


def block_subscription(c: Ctx, sp: dict) -> dict:
    u, t = sp["u"], sp["t"]
    I = c.i_sub
    pos, prev = I.last(u, t), I.last(u, t, back=1)
    end = I.get("end", pos)
    f = {"sub__has_term": (pos >= 0).astype("float64"),
         "sub__has_active_term": np.where(pos >= 0, (np.nan_to_num(end, nan=0) > t).astype("float64"), 0.0),
         "sub__plan": I.get("plan", pos, fill="none"), "sub__seats_bought": I.get("seats", pos),
         "sub__billing_interval": I.get("interval", pos, fill="none"), "sub__term_months": I.get("term", pos),
         "sub__collection_method": I.get("coll", pos, fill="none"), "sub__auto_renew_flag": I.get("auto", pos),
         "sub__mrr_band": I.get("mrr", pos), "sub__version_no": I.get("version", pos),
         "sub__n_amendments": I.total("amend", u, t),
         "sub__seats_change_prev": np.where(prev >= 0, I.get("seats", pos) - I.get("seats", prev), np.nan),
         "sub__n_prior_renewals": np.maximum(c.i_term.count(u, t) - 1, 0),
         "sub__days_to_term_end": days(end, t)}
    fw = c.acc_first_won[np.where(u >= 0, u, 0)]
    f["sub__tenure_days"] = np.where((fw != NAT) & (fw <= t) & (u >= 0), days(t, fw), np.nan)
    return f


def block_billing(c: Ctx, sp: dict) -> dict:
    u, t = sp["u"], sp["t"]
    P = c.i_inv_paid
    n_paid = P.count(u, t)
    with np.errstate(invalid="ignore", divide="ignore"):
        late_rate = np.where(n_paid > 0, P.total("late", u, t) / n_paid, np.nan)
        avg_late = np.where(n_paid > 0, P.total("days_late", u, t) / n_paid, np.nan)
    issued = c.i_inv_iss.count(u, t)
    return {"late_invoice_rate_prior": late_rate, "avg_days_late_prior": avg_late, "invoices_issued_by_t": issued,
            "failed_invoices_prior": c.i_inv_fail.count(u, t), "disputed_prior": c.i_inv_disp.count(u, t),
            "open_unpaid_at_t": issued - n_paid, "has_billing_history": (issued > 0).astype("float64")}


def block_usage(c: Ctx, sp: dict) -> dict:
    u, t = sp["u"], sp["t"]
    I = c.i_use
    d30, d60, d90 = c.i_use_day.count(u, t, W30), c.i_use_day.count(u, t, 2 * W30), c.i_use_day.count(u, t, W90)
    f = {"usage__active_days__30d": d30, "usage__active_days__90d": d90,
         "usage__has_usage": (I.count(u, t) > 0).astype("float64")}
    with np.errstate(invalid="ignore", divide="ignore"):
        f["usage__trend"] = np.where((d60 - d30) > 0, d30 / (d60 - d30), np.nan)
    au = c.distinct_users(u, t, W30)
    f["usage__active_users__30d"] = au
    seats = c.i_sub.get("seats", c.i_sub.last(u, t))
    with np.errstate(invalid="ignore", divide="ignore"):
        f["usage__seat_utilisation"] = np.where(np.nan_to_num(seats) > 0, au / np.where(np.nan_to_num(seats) > 0, seats, 1), np.nan)
    f["usage__feature_breadth__30d"] = sum((c.i_use_feat[k].count(u, t, W30) > 0).astype("float64") for k in USAGE_FEATURES)
    f["usage__api_calls__30d"] = I.total("ev_api_call", u, t, W30)
    f["usage__integrations__30d"] = I.total("ev_integration_connected", u, t, W30)
    f["usage__invites__30d"] = I.total("ev_invite_sent", u, t, W30)
    f["usage__seats_added__90d"] = I.total("ev_seat_added", u, t, W90)
    f["usage__days_since_last_login"] = days(t, c.i_use_feat["login"].time_at(c.i_use_feat["login"].last(u, t)))
    # usage features are NaN for accounts with no usage rows at all; has_usage marks the difference
    none = f["usage__has_usage"] == 0
    for k in list(f):
        if k not in ("usage__has_usage",):
            f[k] = np.where(none, np.nan, f[k])
    return f


ALL_BLOCKS = [block_account, block_time, block_state, block_contacts, block_sales, block_actions, block_web_marketing,
              block_support_health, block_subscription, block_billing, block_usage]
M1_BLOCKS = [block_account, block_time, block_state, block_contacts, block_sales, block_actions, block_web_marketing, block_support_health]
M2_BLOCKS = [block_account, block_time, block_state, block_contacts, block_sales, block_actions, block_support_health,
             block_subscription, block_billing, block_usage]


def build_block_features(c: Ctx, spine: pd.DataFrame, blocks=ALL_BLOCKS) -> pd.DataFrame:
    sp = {"unit_id": spine["unit_id"], "u": c.u(spine["unit_id"]), "t": ms(spine["t"])}
    out = {}
    for blk in blocks:
        out.update(blk(c, sp))
    return downcast(pd.DataFrame(out, index=spine.index))


# --------------------------------------------------------------------------- labels / splits
def final_flag(t: pd.Series, window: float, buffer: float) -> pd.Series:
    return (t + pd.Timedelta(days=window + buffer)) <= EXTRACT


def std_cols(df: pd.DataFrame, window: float, buffer: float, mode: str = "time") -> pd.DataFrame:
    df["label_final"] = final_flag(df["prediction_time"], window, buffer)
    df["split"] = assign_split(df, "prediction_time", mode=mode)
    return df


# --------------------------------------------------------------------------- M1
def build_m1(c: Ctx, split_mode: str) -> pd.DataFrame:
    acc = c.T["accounts"]
    months = pd.date_range("2024-06-01", "2026-07-01", freq="MS", tz="UTC")
    first_sub = c.terms.groupby("u")["st"].min()
    fs = np.full(len(acc), BIG, dtype="int64")
    fs[first_sub.index.to_numpy()] = first_sub.to_numpy()
    created = c.acc_created
    parts = []
    for t0 in months:
        t = ms(pd.Series([t0]))[0]
        m = (created <= t) & (fs > t)                       # open prospect: exists and has no subscription yet
        parts.append(pd.DataFrame({"unit_id": acc["account_id"].to_numpy()[m], "t": t0, "u": np.where(m)[0]}))
    sp = pd.concat(parts, ignore_index=True)
    sp["t"] = pd.to_datetime(sp["t"], utc=True)
    X = build_block_features(c, sp, M1_BLOCKS).reset_index(drop=True)
    t = ms(sp["t"])
    u = sp["u"].to_numpy("int64")
    out = pd.concat([sp[["unit_id"]].reset_index(drop=True), X], axis=1)
    out["prediction_time"] = sp["t"].to_numpy()
    out["y_won_90d"] = (c.i_first_sub.count(u, t + W90, W90) > 0).astype("int8")             # billing-confirmed first subscription
    fw = c.acc_first_won[u]
    out["y_won_90d_crm"] = ((fw != NAT) & (fw > t) & (fw <= t + W90)).astype("int8")         # CRM first-won date (comparison)
    out["holdout_group"] = c.acc["holdout_group"].reindex(out["unit_id"]).to_numpy()
    out = std_cols(out, 90, BUFFER_M1, split_mode)
    return out


# --------------------------------------------------------------------------- M2
def build_m2(c: Ctx, split_mode: str) -> pd.DataFrame:
    T = c.terms.copy()
    end_ts = pd.to_datetime(from_ms(T["en"].to_numpy()), utc=True)
    # successor term: another subscription of the account starting from one day before end_at to 45 days after it
    succ = c.i_term.count(T["u"].to_numpy(), T["en"].to_numpy() + 45 * DAY, 45 * DAY + DAY) > 0
    # t = end_at - 90 days, but never before the term itself starts (monthly terms are shorter than 90 days)
    t_ms = np.maximum(T["en"].to_numpy() - W90, T["st"].to_numpy())
    sp = pd.DataFrame({"unit_id": T["account_id"].to_numpy(), "t": from_ms(t_ms).to_numpy()})
    sp["t"] = pd.to_datetime(sp["t"], utc=True)
    X = build_block_features(c, sp, M2_BLOCKS).reset_index(drop=True)
    out = pd.concat([T[["subscription_id", "account_id"]].rename(columns={"account_id": "unit_id"}).reset_index(drop=True), X], axis=1)
    out["prediction_time"] = sp["t"].to_numpy()
    out["term_end_at"] = end_ts.to_numpy()
    out["y_lapse"] = (~succ).astype("int8")
    out["holdout_group"] = c.acc["holdout_group"].reindex(out["unit_id"]).to_numpy()
    out["label_final"] = ((end_ts + pd.Timedelta(days=45 + BUFFER_M2)) <= EXTRACT).to_numpy()
    out["split"] = assign_split(out, "prediction_time", mode=split_mode)
    return out


def build_m2_invoice(c: Ctx, split_mode: str) -> pd.DataFrame:
    i = c.inv.copy().reset_index(drop=True)
    sp = pd.DataFrame({"unit_id": i["account_id"].to_numpy(), "t": pd.to_datetime(i["issued_at"], utc=True).to_numpy()})
    sp["t"] = pd.to_datetime(sp["t"], utc=True)
    X = build_block_features(c, sp, [block_account, block_time, block_contacts, block_billing, block_subscription, block_usage]).reset_index(drop=True)
    out = pd.concat([i[["invoice_id", "account_id"]].rename(columns={"account_id": "unit_id"}), X], axis=1)
    out["inv_amount_band"] = i["amt_ord"].to_numpy("float32")
    out["collection_method"] = i["collection_method"].to_numpy()
    out["is_renewal"] = i["is_renewal"].astype("float32").to_numpy()
    out["prediction_time"] = sp["t"].to_numpy()
    out["y_invoice_late"] = ((i["paid"] == NAT) | (i["paid"] > i["due"] + LATE_GRACE_DAYS * DAY) | (i["status"] == "failed")).astype("int8").to_numpy()
    out["label_final"] = ((pd.to_datetime(i["due_at"], utc=True) + pd.Timedelta(days=45)) <= EXTRACT).to_numpy()
    out["split"] = assign_split(out, "prediction_time", mode=split_mode)
    return out


# --------------------------------------------------------------------------- M3 (cohort level)
def parse_blocked(s: pd.Series) -> pd.DataFrame:
    """allowed_<action> flags from the {action: [reasons]} JSON. A block for reason in_holdout is ignored: it is the
       treatment assignment, not eligibility."""
    out = {f"allowed_{a}": np.ones(len(s)) for a in OPTIONAL_ACTIONS}
    reasons: dict[str, np.ndarray] = {}
    for i, v in enumerate(s.fillna("{}").to_numpy()):
        if v in ("{}", "[]"):
            continue
        for a, rs in json.loads(v).items():
            rs = [r for r in rs if r != "in_holdout"]
            if not rs:
                continue
            if f"allowed_{a}" in out:
                out[f"allowed_{a}"][i] = 0.0
            for r in rs:
                reasons.setdefault(r, np.zeros(len(s)))[i] = 1.0
    for r, v in reasons.items():
        out[f"blocked_reason_{r}"] = v
    return pd.DataFrame(out, index=s.index).astype("float32")


def build_m3(c: Ctx, split_mode: str) -> pd.DataFrame:
    a = c.actions
    d = a[(a["record_kind"] == "decision") & (a["regime"] == "randomised_holdout")].copy().reset_index(drop=True)
    sp = pd.DataFrame({"unit_id": d["unit_id"], "t": pd.to_datetime(d["decided_at"], utc=True)})
    X = build_block_features(c, sp).reset_index(drop=True)
    u, t = c.u(sp["unit_id"]), ms(sp["t"])
    X["state_at_decision"] = d["state"].to_numpy()
    X["trigger"] = d["trigger"].to_numpy()
    X = pd.concat([X, parse_blocked(d["blocked_actions"]).reset_index(drop=True)], axis=1)
    out = pd.concat([d[["action_id", "unit_id"]], X], axis=1)
    out["prediction_time"] = sp["t"].to_numpy()
    ch = d["chosen_action"]
    out["w_any"] = (ch != "do_nothing").astype("int8").to_numpy()
    out["w_action"] = ch.to_numpy()
    out["propensity"] = d["propensity"].to_numpy("float32")
    out["in_holdout"] = d["in_holdout"].astype(bool).to_numpy()
    out["holdout_group"] = d["holdout_group"].to_numpy()
    forced = (ch == "do_nothing") & (d["propensity"] == 1.0) & (~d["in_holdout"].astype(bool))
    out["is_forced_do_nothing"] = forced.to_numpy()
    out["is_valid_control"] = ((ch == "do_nothing") & ~forced).to_numpy()
    out["keep_for_uplift"] = (~forced).to_numpy()
    out["ipw"] = np.where(out["in_holdout"] | out["propensity"].isna(), np.nan, np.clip(1.0 / out["propensity"], 1.0, 10.0)).astype("float32")
    n, trig = len(out), d["trigger"].to_numpy()
    nan = lambda: np.full(n, np.nan)
    # outcomes by trigger (confirmed in the owning system: CRM opportunities and billing subscriptions)
    y = {"y_opp_60d": nan(), "y_won_60d": nan(), "y_renewed": nan()}
    y["y_opp_60d"] = np.where(trig == "lead_stall", c.i_opp.count(u, t + W60, W60) > 0, np.nan)
    won = (c.i_opp_won.count(u, t + W60, W60) > 0) | (c.i_first_sub.count(u, t + W60, W60) > 0)
    y["y_won_60d"] = np.where(trig == "opp_stall", won, np.nan)
    # y_renewed: the term running at t, and whether a successor term starts within 45 days of its end
    pos = c.i_sub.last(u, t)
    end = c.i_sub.get("end", pos)
    has_term = (pos >= 0) & (np.nan_to_num(end, nan=0) > t) & (np.nan_to_num(end, nan=0) < BIG - 1)
    endv = np.where(has_term, np.nan_to_num(end, nan=0), 0).astype("int64")
    renewed = c.i_term.count(u, endv + 45 * DAY, 45 * DAY + DAY) > 0
    ret = np.isin(trig, ["risk", "expansion", "onboarding"]) & has_term
    y["y_renewed"] = np.where(ret, renewed, np.nan)
    for k, v in y.items():
        out[k] = v.astype("float32")
    out["term_end_at"] = pd.to_datetime(from_ms(endv), utc=True).where(has_term).to_numpy()
    fin_opp = final_flag(out["prediction_time"], 60, BUFFER_M3).to_numpy()
    out["final_y_opp_60d"] = fin_opp
    out["final_y_won_60d"] = fin_opp
    out["final_y_renewed"] = ((pd.to_datetime(out["term_end_at"], utc=True) + pd.Timedelta(days=45 + BUFFER_M3)) <= EXTRACT).to_numpy() & has_term
    lf = (trig == "lead_stall") & fin_opp
    lf |= (trig == "opp_stall") & fin_opp
    lf |= ret & out["final_y_renewed"].to_numpy()
    out["label_final"] = lf
    out["split"] = assign_split(out, "prediction_time", mode=split_mode)
    return out


COHORT_GROUPS = {"lead_stall": ("y_opp_60d", ["lead_stall"]), "opp_stall": ("y_won_60d", ["opp_stall"]),
                 "retention (risk + expansion + onboarding)": ("y_renewed", ["risk", "expansion", "onboarding"])}


def _boot_ci(counts: np.ndarray, fn, reps: int, rng) -> tuple:
    """counts: (reps, n_accounts) resampling multiplicities; fn maps a multiplicity vector to a statistic."""
    v = np.array([fn(counts[r]) for r in range(reps)], dtype=float)
    return (np.nanpercentile(v, 2.5), np.nanpercentile(v, 97.5)) if np.isfinite(v).any() else (np.nan, np.nan)


def cohort_uplift(m3: pd.DataFrame, accounts: pd.DataFrame, reps: int = BOOTSTRAP_REPS) -> pd.DataFrame:
    """Uplift by cohort, never by account. Treated = any optional action. Two comparisons:
         vs_holdout      treated against the random holdout (the clean randomised comparison);
         vs_policy_ctrl  treated against policy-chosen do_nothing (forced do_nothing removed), inverse-propensity weighted.
       The bootstrap resamples accounts (via per-account sums), so repeated decisions of one account stay together."""
    rng = np.random.default_rng(RANDOM_SEED)
    d = m3[m3["keep_for_uplift"]]
    rows = []
    for gname, (ycol, trigs) in COHORT_GROUPS.items():
        g = d[d["trigger"].isin(trigs) & d["label_final"] & d[ycol].notna()]
        cuts = [("all", None)] + [(dim, v) for dim in ["segment", "region"] for v in sorted(g[dim].dropna().unique())]
        for dim, val in cuts:
            h = g if dim == "all" else g[g[dim] == val]
            y = h[ycol].to_numpy("float64")
            tr = (h["w_any"] == 1).to_numpy()
            ho = h["in_holdout"].to_numpy()
            pc = (h["is_valid_control"] & ~h["in_holdout"]).to_numpy()
            w = h["ipw"].to_numpy("float64")
            w = np.where(np.isnan(w), 0.0, w)
            tr_w = tr & ~ho
            f = lambda m: m.astype("float64")
            agg = pd.DataFrame({"u": h["unit_id"].to_numpy(), "ntr": f(tr), "ytr": f(tr) * y, "nho": f(ho), "yho": f(ho) * y,
                                "wtr": f(tr_w) * w, "wytr": f(tr_w) * w * y, "wpc": f(pc) * w, "wypc": f(pc) * w * y}).groupby("u").sum()
            A = agg.to_numpy()
            ix = {k: i for i, k in enumerate(agg.columns)}

            def stat(m):
                s = m @ A if m.ndim == 2 else m @ A
                r_tr = s[ix["ytr"]] / s[ix["ntr"]] if s[ix["ntr"]] > 0 else np.nan
                r_ho = s[ix["yho"]] / s[ix["nho"]] if s[ix["nho"]] > 0 else np.nan
                p_tr = s[ix["wytr"]] / s[ix["wtr"]] if s[ix["wtr"]] > 0 else np.nan
                p_pc = s[ix["wypc"]] / s[ix["wpc"]] if s[ix["wpc"]] > 0 else np.nan
                return r_tr, r_ho, r_tr - r_ho, p_pc, p_tr - p_pc

            base = stat(np.ones(len(A)))
            lo = [np.nan, np.nan]; hi = [np.nan, np.nan]
            if len(A) >= 30:
                M = rng.multinomial(len(A), np.full(len(A), 1.0 / len(A)), size=reps).astype("float64")
                bs = np.array([stat(M[r]) for r in range(reps)], dtype=float)
                for j, col in enumerate([2, 4]):
                    if np.isfinite(bs[:, col]).any():
                        lo[j], hi[j] = np.nanpercentile(bs[:, col], [2.5, 97.5])
            rows.append({"group": gname, "outcome": ycol, "cohort_dim": dim, "cohort": val if val is not None else "all",
                         "n_rows": len(h), "n_treated": int(tr.sum()), "n_holdout": int(ho.sum()), "n_policy_control": int(pc.sum()),
                         "rate_treated": base[0], "rate_holdout": base[1], "uplift_vs_holdout": base[2],
                         "uplift_vs_holdout_ci_low": lo[0], "uplift_vs_holdout_ci_high": hi[0],
                         "rate_policy_control": base[3], "uplift_vs_policy_ctrl": base[4],
                         "uplift_vs_policy_ctrl_ci_low": lo[1], "uplift_vs_policy_ctrl_ci_high": hi[1]})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- M4 (cohort level)
OUT_PROSPECT = ["won", "lost"]
OUT_CUSTOMER = ["churns", "renews", "expands"]


def build_m4(c: Ctx, split_mode: str, path: str, horizon_days: int = M4_HORIZON_DAYS) -> pd.DataFrame:
    rng = np.random.default_rng(RANDOM_SEED)
    acc = c.T["accounts"]
    n = len(acc)
    WEEK = 7 * DAY
    H = horizon_days * DAY
    epoch_monday = 4 * DAY
    end_ms = ms(pd.Series([EXTRACT]))[0]
    first_sub = np.full(n, BIG, dtype="int64")
    fsr = c.terms.groupby("u")["st"].min()
    first_sub[fsr.index.to_numpy()] = fsr.to_numpy()
    sd = c.state_df
    lost_t = np.full(n, BIG, dtype="int64")
    ls = sd[sd["state"] == "Lost"].groupby("u")["e"].min()
    lost_t[ls.index[ls.index >= 0]] = ls[ls.index >= 0].to_numpy()
    churn_t = np.full(n, BIG, dtype="int64")
    cs = sd[sd["state"] == "Churned"].groupby("u")["e"].min()
    churn_t[cs.index[cs.index >= 0]] = cs[cs.index >= 0].to_numpy()
    # an "active" prospect has an event, a state change, an action or a contact in the data; the rest are sampled
    n_state = sd.groupby("u").size().reindex(range(n)).fillna(0).to_numpy()
    n_act = c.actions.groupby("u").size().reindex(range(n)).fillna(0).to_numpy()
    active = (n_state > 1) | (n_act > 0)
    if c.has_events:
        evu = np.unique(np.concatenate([c.i_pv.u, c.i_tix.u, c.i_form.u, c.i_msg["sent"].u, c.i_consent.u]))
        active[evu] = True
    created = c.acc_created
    first_w = lambda t0: ((t0 - epoch_monday + WEEK - 1) // WEEK) * WEEK + epoch_monday
    pops = []
    # prospects: from creation until first subscription or Lost
    p_start = first_w(created)
    p_stop = np.minimum(np.minimum(first_sub, lost_t), end_ms)
    # customers: from first subscription until Churned
    c_start = np.where(first_sub < BIG, first_w(first_sub), BIG)
    c_stop = np.minimum(churn_t, end_ms)
    for pop, st_, sp_ in [("prospect", p_start, p_stop), ("customer", c_start, c_stop)]:
        nw = np.where((st_ < sp_) & (st_ < BIG), (sp_ - st_ + WEEK - 1) // WEEK, 0)
        unit = np.repeat(np.arange(n), nw)
        k = np.arange(nw.sum()) - np.repeat(np.cumsum(nw) - nw, nw)
        wk = st_[unit] + k * WEEK
        keep = active[unit] if pop == "prospect" else np.ones(len(unit), bool)
        if pop == "prospect":
            keep = keep | (rng.random(len(unit)) < M4_INACTIVE_SAMPLE)
        wgt = np.where((pop == "prospect") & ~active[unit], 1.0 / M4_INACTIVE_SAMPLE, 1.0)
        pops.append(pd.DataFrame({"u": unit[keep], "wk": wk[keep], "w": wgt[keep], "population": pop}))
        print(f"  M4 {pop}: {int(nw.sum()):,} account-weeks, {int(keep.sum()):,} kept")
    sp_all = pd.concat(pops, ignore_index=True)
    sp_all = sp_all[sp_all["wk"] <= end_ms].reset_index(drop=True)
    ev = {"won": c.i_first_sub, "lost": Idx(sd.loc[sd["state"] == "Lost", "u"], sd.loc[sd["state"] == "Lost", "e"]),
          "churns": Idx(sd.loc[sd["state"] == "Churned", "u"], sd.loc[sd["state"] == "Churned", "e"]),
          "renews": Idx(c.terms["u"], c.terms["st"]), "expands": c.i_opp_exp_won}
    parts = []
    for s0 in range(0, len(sp_all), M4_CHUNK):
        ch = sp_all.iloc[s0:s0 + M4_CHUNK]
        uu, tt = ch["u"].to_numpy(), ch["wk"].to_numpy()
        sp = pd.DataFrame({"unit_id": acc["account_id"].to_numpy()[uu], "t": pd.to_datetime(from_ms(tt), utc=True).to_numpy()})
        sp["t"] = pd.to_datetime(sp["t"], utc=True)
        X = build_block_features(c, sp).reset_index(drop=True)
        X.insert(0, "unit_id", sp["unit_id"].to_numpy())
        X.insert(1, "week_start", sp["t"].to_numpy())
        X["prediction_time"] = sp["t"].to_numpy()
        X["population"] = ch["population"].to_numpy()
        X["sample_weight"] = ch["w"].to_numpy("float32")
        best_t = np.full(len(uu), np.inf)
        best_k = np.full(len(uu), "stay", dtype=object)
        isp = (ch["population"] == "prospect").to_numpy()
        for name in ["won", "lost", "churns", "renews", "expands"]:
            allowed = isp if name in OUT_PROSPECT else ~isp
            I = ev[name]
            pos = I.next_after(uu, tt)
            tn = I.time_at(pos)
            ok = allowed & (~np.isnan(tn)) & (tn <= tt + H)
            better = ok & (tn < best_t)
            best_t, best_k = np.where(better, tn, best_t), np.where(better, name, best_k)
        X["y4_outcome"] = best_k
        X["holdout_group"] = c.acc["holdout_group"].to_numpy()[uu]
        parts.append(X)
        print(f"    M4 rows built: {s0 + len(ch):,}")
    out = pd.concat(parts, ignore_index=True)
    out["label_final"] = ((out["prediction_time"] + pd.Timedelta(days=horizon_days + BUFFER_M4)) <= EXTRACT).to_numpy()
    out["split"] = assign_split(out, "prediction_time", mode="time")
    out.to_parquet(path, index=False)
    return out


def cohort_summary(m4: pd.DataFrame, accounts: pd.DataFrame, reps: int = BOOTSTRAP_REPS) -> pd.DataFrame:
    """Observed outcome shares by cohort (population x state / segment / region), weighted by sample_weight, with
       account-level bootstrap intervals. This is the cohort check M4 must pass: predicted shares should match these."""
    rng = np.random.default_rng(RANDOM_SEED)
    d = m4[m4["label_final"]]
    rows = []
    for pop in ["prospect", "customer"]:
        for dim in ["state__current", "segment", "region"]:
            g = d[d["population"] == pop]
            for val, h in g.groupby(dim, observed=True):
                w = h["sample_weight"].to_numpy("float64")
                codes, outs = pd.factorize(h["y4_outcome"])
                uc, ui = np.unique(h["unit_id"].to_numpy(), return_inverse=True)
                A = np.zeros((len(uc), len(outs) + 1))
                np.add.at(A, (ui, np.full(len(ui), len(outs))), w)
                np.add.at(A, (ui, codes), w)
                tot = A.sum(0)
                M = rng.multinomial(len(uc), np.full(len(uc), 1.0 / len(uc)), size=min(reps, 200)).astype("float64") if len(uc) >= 30 else None
                bs = None if M is None else (M @ A)
                for j, oc in enumerate(outs):
                    lo = hi = np.nan
                    if bs is not None:
                        sh = bs[:, j] / bs[:, -1]
                        lo, hi = np.nanpercentile(sh, [2.5, 97.5])
                    rows.append({"population": pop, "cohort_dim": dim, "cohort": val, "outcome": oc, "share": tot[j] / tot[-1],
                                 "ci_low": lo, "ci_high": hi, "n_rows": len(h), "n_accounts": len(uc)})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- feature dictionary
FAMILY_PREFIX = [("tenure__", "1 tenure"), ("account_age", "1 tenure"), ("acq__", "2 acquisition channel"), ("source", "2 acquisition channel"),
                 ("regime_first_seen", "3 regime"), ("consent__", "4 consent"), ("web__", "5 web behaviour"), ("mkt__", "5 marketing"),
                 ("msg__", "6 messaging"), ("act__", "7 action history"), ("state__", "8 lifecycle state"), ("support__", "9 support"),
                 ("late_invoice", "10 payment history"), ("avg_days_late", "10 payment history"), ("failed_invoices", "10 payment history"),
                 ("disputed", "10 payment history"), ("open_unpaid", "10 payment history"), ("invoices_issued", "10 payment history"),
                 ("has_billing", "10 payment history"), ("rf__", "11 recency and frequency"), ("n_open_opps", "11 recency and frequency"),
                 ("prior_", "11 recency and frequency"), ("opp_", "sales"), ("competitor", "sales"), ("legal_review", "sales"),
                 ("days_to_incumbent", "sales"), ("has_incumbent", "sales"), ("has_opportunity", "sales"), ("last_loss", "sales"),
                 ("esign_stage", "sales"), ("rep_touches", "sales (rep activity)"), ("meetings_booked", "sales (rep activity)"),
                 ("connect_rate", "sales (rep activity)"), ("n_contacts", "contacts"), ("contacts_left", "contacts"),
                 ("has_champion", "contacts"), ("has_economic", "contacts"), ("max_seniority", "contacts"), ("champion_left", "contacts"),
                 ("personal_email", "contacts"), ("is_product_user", "contacts"), ("lead_source", "contacts"), ("days_since_lead", "contacts"),
                 ("sub__", "subscription"), ("usage__", "usage"), ("health_band", "health"), ("open_ctas", "health"), ("ctas_", "health"),
                 ("logins__", "login"), ("login_", "login"), ("csm_tasks", "success actions"), ("exec_calls", "success actions"),
                 ("risk_triggers", "success actions"), ("time__", "13 time of prediction"), ("employee_band", "account"),
                 ("segment", "account"), ("industry_band", "account"), ("region", "account"), ("strategic_flag", "account"),
                 ("named_csm", "account"), ("allowed_", "M3 eligibility"), ("blocked_reason_", "M3 eligibility"),
                 ("inv_amount", "invoice"), ("collection_method", "invoice"), ("is_renewal", "invoice")]
META = {"unit_id", "subscription_id", "invoice_id", "action_id", "prediction_time", "week_start", "split", "label_final", "sample_weight",
        "holdout_group", "w_any", "w_action", "propensity", "in_holdout", "is_forced_do_nothing", "is_valid_control", "keep_for_uplift",
        "ipw", "population", "term_end_at", "trigger", "state_at_decision"}


def feature_dictionary(tables: dict) -> pd.DataFrame:
    rows = []
    for name, df in tables.items():
        for col in df.columns:
            role = "meta / treatment" if col in META else "label" if col.startswith(("y_", "y4_", "final_")) else "feature"
            fam = next((f for p, f in FAMILY_PREFIX if col.startswith(p)), "other") if role == "feature" else ""
            rows.append({"table": name, "column": col, "role": role, "family": fam, "dtype": str(df[col].dtype)})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", required=True, help="folder with the VISIBLE B2B parquet files")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--only", nargs="*", choices=["m1", "m2", "m3", "m4"], default=["m1", "m2", "m3", "m4"])
    ap.add_argument("--no-events", action="store_true")
    ap.add_argument("--split-mode", choices=["time", "unit_first_time"], default="time")
    a = ap.parse_args(argv)
    os.makedirs(a.out_dir, exist_ok=True)
    t0 = time.time()
    print("loading tables ...")
    tables, ev = load_tables(a.data_dir, use_events=not a.no_events)
    if ev is None:
        print("  events.parquet not used: web, marketing, support, health, login and Stripe-event features will be NaN")
    else:
        ev = prep_events(ev)
    print("building indexes ...")
    c = Ctx(tables, ev)
    del ev
    dicts = {}

    def save(name, df):
        df.to_parquet(os.path.join(a.out_dir, f"{name}.parquet"), index=False)
        dicts[name] = df.head(1)
        lab = [x for x in df.columns if x.startswith("y_")]
        info = ", ".join(f"{x}={df.loc[df['label_final'], x].mean():.4f}" for x in lab[:3])
        print(f"  {name}: {len(df):,} rows, {int(df['label_final'].sum()):,} final; {info}")

    if "m1" in a.only:
        print("M1 ..."); save("b2b_m1", build_m1(c, a.split_mode))
    if "m2" in a.only:
        print("M2 ..."); save("b2b_m2", build_m2(c, a.split_mode)); save("b2b_m2_invoice", build_m2_invoice(c, a.split_mode))
    if "m3" in a.only:
        print("M3 ...")
        m3 = build_m3(c, a.split_mode)
        save("b2b_m3", m3)
        cu = cohort_uplift(m3, tables["accounts"])
        cu.to_csv(os.path.join(a.out_dir, "b2b_m3_cohort_uplift.csv"), index=False)
        print(f"  b2b_m3_cohort_uplift.csv: {len(cu)} cohort rows")
    if "m4" in a.only:
        print("M4 ...")
        m4 = build_m4(c, a.split_mode, os.path.join(a.out_dir, "b2b_m4.parquet"))
        dicts["b2b_m4"] = m4.head(1)
        cs = cohort_summary(m4, tables["accounts"])
        cs.to_csv(os.path.join(a.out_dir, "b2b_m4_cohort_summary.csv"), index=False)
        print(f"  b2b_m4: {len(m4):,} rows, {int(m4['label_final'].sum()):,} final; b2b_m4_cohort_summary.csv: {len(cs)} rows")
    feature_dictionary(dicts).to_csv(os.path.join(a.out_dir, "b2b_feature_dictionary.csv"), index=False)
    print(f"done in {time.time() - t0:.0f}s -> {a.out_dir}")


if __name__ == "__main__":
    main()
