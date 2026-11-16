"""
ecom_features.py  -  point-in-time feature engineering for the E-COMMERCE vertical (M1 to M4).

Needs bfsi_features.py in the same folder (it provides the shared helpers: the (unit, time) index, millisecond
conversion, the time-based split). Reads the VISIBLE e-commerce tables only. Writes, into --out-dir:

    ecom_m1.parquet                 customer x month          y_order_30d  (+ y_order_created_30d)
    ecom_m2.parquet                 order at creation         y_rto        (+ y_refund_45d)
    ecom_m3.parquet                 randomised decision       y_order_7d (cart) / y_order_30d (weekly) + treatment columns
    ecom_m3_uplift_check.csv        raw treated-vs-holdout and treated-vs-policy-control gaps with bootstrap intervals
    ecom_m4.parquet                 customer x week           y4_outcome  (kept_order / lapse / stay, 30 days)
    ecom_m4_cohort_summary.csv      observed outcome shares by cohort with bootstrap intervals (the M4 cohort check)
    ecom_feature_dictionary.csv     every column with its role and family (so a table is never used by mistake)

Run:
    python ecom_features.py --data-dir D:\\...\\out_ecom\\visible --out-dir D:\\...\\features_ecom
    python ecom_features.py --data-dir ... --out-dir ... --only m1 m2        (subset)
    python ecom_features.py --data-dir ... --out-dir ... --no-events         (events.parquet not used)

The data folder must hold: customers, orders, payments, tickets, actions, state_history, category_value (.parquet),
and events.parquet unless --no-events. Same rules as the BFSI and B2B code: features as of t only (ingested_at for
events); extract-time snapshot columns are never read (LEAKY_COLUMNS); a label is final only after its window plus a
buffer; missing history is NaN with a has_* flag, never zero; time-based split.
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
from bfsi_features import Idx, ms, from_ms, days, ordinal, downcast, assign_split, parse_flags, DAY, BIG, NAT, EXTRACT

warnings.filterwarnings("ignore", category=pd.errors.PerformanceWarning)

# --------------------------------------------------------------------------- config
LOCAL_TZ = "Asia/Kolkata"
DELIVERY_BUFFER = 45          # label buffer after the window (delivery resolves a median 5 days after the order, 99% by 25)
M3_FINAL_DAYS = 55            # a randomised decision is final once decided 55+ days before the extract (30-day window + 25 days delivery)
M1_FIRST_MONTH, M1_LAST_MONTH = "2025-01-01", "2026-09-01"
BOOTSTRAP_REPS = 300
RANDOM_SEED = 7
W7, W30, W90 = 7 * DAY, 30 * DAY, 90 * DAY

OPTIONAL_ACTIONS = ["reminder", "discount", "free_shipping", "bundle", "agent_call"]
STATES = ["New visitor", "Retarget", "New customer", "Active", "Re-engage", "Reactivate"]
JOURNEY_GROUP = {"New visitor": "acquire", "Retarget": "acquire", "New customer": "grow_retain", "Active": "grow_retain",
                 "Re-engage": "grow_retain", "Reactivate": "win_back_exit"}
CATEGORIES = ["apparel_women", "apparel_men", "footwear", "accessories", "beauty", "home", "electronics_acc"]
BAND_AMOUNT = {"0-500": 1, "500-1000": 2, "1000-1500": 3, "1500-2500": 4, "2500-5000": 5, "5000+": 6}
BAND_DISCOUNT = {"0-10%": 1, "10-20%": 2}
BAND_MARGIN = {"<20%": 1, "30-40%": 2, "40%+": 3}
BAND_RETURN_COST = {"low": 1, "medium": 2}
STOCK = {"out_of_stock": 0, "low": 1, "in_stock": 2}
FLAG_KEYS = ["open_support_ticket", "high_return_risk", "no_consent"]     # in_holdout is the treatment assignment, never a feature
CHANNELS = ["email", "sms", "whatsapp"]

# Columns that hold an extract-time snapshot or an outcome. Feature code never reads them.
LEAKY_COLUMNS = {
    "customers": ["first_order_at", "orders_count", "spend_band", "email_consent", "sms_consent", "whatsapp_consent"],
    "orders": ["financial_status", "fulfilment_status", "courier", "attempt_count", "delivered_at (only through its own timestamp)",
               "rto_reason_category", "refund_* (only through refund_created_at)", "paid_at (a COD order is paid on delivery)",
               "processed_at", "decision_id", "campaign_id"],
    "actions": ["final_status", "expected_value", "reason_codes", "task_status (only through task_due_at)"],
    "tickets": ["status"],
    "payments": ["status refunded (only failed is known at created_at)"],
}

TABLES = ["customers", "orders", "payments", "tickets", "actions", "state_history", "category_value"]


# --------------------------------------------------------------------------- loading
def load_tables(data_dir: str, use_events: bool = True):
    T = {n: pd.read_parquet(os.path.join(data_dir, f"{n}.parquet")) for n in TABLES}
    ev = None
    p = os.path.join(data_dir, "events.parquet")
    if use_events and os.path.exists(p):
        ev = pd.read_parquet(p, columns=["event_id", "source_event_id", "event_type", "source_system", "person_key", "unit_id",
                                         "occurred_at", "ingested_at", "channel", "consent_status", "properties"])
    return T, ev


def prep_events(ev: pd.DataFrame) -> pd.DataFrame:
    n0 = len(ev)
    ev = ev[ev["unit_id"].notna()].copy()                       # anonymous-only visitors cannot be tied to a customer
    ev = ev[~ev["event_id"].str.startswith("BOT")]
    ev = ev[ev["occurred_at"] <= ev["ingested_at"]]
    ev = ev.sort_values("ingested_at", kind="stable").drop_duplicates("source_event_id", keep="first")
    p = ev["properties"].fillna("")

    def ex(pat):
        return p.str.extract(pat)[0]

    ev["ga4_event"] = ex(r'"ga4_event":\s*"([^"]*)"')
    ev["session_id"] = ex(r'"session_id":\s*"?([^",}]+)')
    ev["pstatus"] = ex(r'"status":\s*"([^"]*)"')
    ev["pchannel"] = ex(r'"channel":\s*"([^"]*)"')
    ev = ev.drop(columns=["properties"])
    print(f"  events: {n0:,} rows -> {len(ev):,} after unlinked / bots / bad timestamps / duplicates")
    return ev


# --------------------------------------------------------------------------- context
class Ctx:
    def __init__(self, T: dict, events: pd.DataFrame | None):
        self.T = T
        cu = T["customers"]
        self.units = pd.Index(cu["unit_id"])
        self.cust = cu.set_index("unit_id")
        self.created = ms(cu["created_at"])
        self._orders()
        self._payments()
        self._tickets()
        self._states()
        self._actions()
        self._value()
        self.has_events = events is not None
        if events is not None:
            self._events(events)

    def u(self, s) -> np.ndarray:
        return self.units.get_indexer(s).astype("int64")

    # ---- orders --------------------------------------------------------------------------------
    def _orders(self):
        o = self.T["orders"].copy()
        o["u"] = self.u(o["unit_id"])
        o["cr"] = ms(o["created_at"])
        o["can"] = ms(o["cancelled_at"])
        o["dlv"] = ms(o["delivered_at"])
        o["dsc"] = ms(o["delivery_status_changed_at"])
        o["rfd"] = ms(o["refund_created_at"])
        o["amt"] = ordinal(o["amount_band"], BAND_AMOUNT)
        o["cod"] = (o["payment_mode"] == "cod").astype("float64")
        o["disc"] = o["discount_band"].notna().astype("float64")
        o["catc"] = o["category_primary"].map({k: i for i, k in enumerate(CATEGORIES)}).fillna(-1).astype("int64")
        o["kept"] = ((o["dlv"] != NAT) & (o["can"] == NAT)).astype("float64")        # delivered and not cancelled (confirmed outcome)
        o["rto"] = (o["delivery_status"] == "rto").astype("float64")
        o["resolved"] = o["delivery_status"].isin(["delivered", "rto", "failed_delivery"]) & (o["dsc"] != NAT)
        self.orders = o
        cat_flags = {f"cat{i}": (o["catc"] == i).astype("float64").to_numpy() for i in range(len(CATEGORIES))}
        self.i_ord = Idx(o["u"], o["cr"], amt=o["amt"].to_numpy(), cod=o["cod"].to_numpy(), disc=o["disc"].to_numpy(),
                         one=np.ones(len(o)), **cat_flags)
        k = o[o["kept"] > 0]
        self.i_kept = Idx(k["u"], k["cr"])                                         # kept order, keyed by its creation time (label)
        cn = o[o["can"] != NAT]
        self.i_cancel = Idx(cn["u"], cn["can"], one=np.ones(len(cn)))
        r = o[o["resolved"]]
        self.i_res = Idx(r["u"], r["dsc"], rto=r["rto"].to_numpy(), one=np.ones(len(r)))
        d = o[o["dlv"] != NAT]
        self.i_deliv = Idx(d["u"], d["dlv"], one=np.ones(len(d)))
        f = o[o["rfd"] != NAT]
        self.i_refund = Idx(f["u"], f["rfd"], size=f["refund_reason_category"].fillna("").str.contains("size").to_numpy("float64"),
                            one=np.ones(len(f)))
        # population rolling rates keyed by group (category, payment mode): resolved earlier orders only
        self.i_cat_res = Idx(r["catc"], r["dsc"], rto=r["rto"].to_numpy(), one=np.ones(len(r)))
        self.i_cod_res = Idx(r["cod"].astype("int64"), r["dsc"], rto=r["rto"].to_numpy(), one=np.ones(len(r)))

    # ---- payments ------------------------------------------------------------------------------
    def _payments(self):
        p = self.T["payments"].copy()
        p["u"] = self.u(p["unit_id"])
        p["cr"] = ms(p["created_at"])
        fail = (p["status"] == "failed").astype("float64")
        card = (p["method"] == "card").astype("float64")
        self.i_pay = Idx(p["u"], p["cr"], fail=fail.to_numpy(), cardfail=(fail * card).to_numpy(), one=np.ones(len(p)))
        ck = pd.factorize(p["checkout_id"].fillna("none"))
        self.checkout_codes = {k: i for i, k in enumerate(ck[1])}
        self.i_pay_ck = Idx(ck[0], p["cr"], fail=fail.to_numpy(), one=np.ones(len(p)))

    # ---- tickets -------------------------------------------------------------------------------
    def _tickets(self):
        t = self.T["tickets"].copy()
        t["u"] = self.u(t["unit_id"])
        t["cr"] = ms(t["created_at"])
        t["sv"] = ms(t["solved_at"])
        t["up"] = ms(t["updated_at"])
        dl = t["tags"].fillna("").str.contains("delivery").to_numpy("float64")
        self.i_tix = Idx(t["u"], t["cr"], deliv=dl, one=np.ones(len(t)))
        s = t[t["sv"] != NAT]
        self.i_tix_solved = Idx(s["u"], s["sv"])
        cs = t[t["csat"].notna()]
        self.i_csat = Idx(cs["u"], cs["up"], csat=cs["csat"].to_numpy("float64"))   # a rating is known from the last update

    # ---- state history -------------------------------------------------------------------------
    def _states(self):
        s = self.T["state_history"].copy()
        s["u"] = self.u(s["unit_id"])
        s["e"] = ms(s["entered_at"])
        sc = s["state"].map({k: i for i, k in enumerate(STATES)}).to_numpy("float64")
        flags = {f"f_{k}": parse_flags(s["flags"], k) for k in FLAG_KEYS}
        self.i_state = Idx(s["u"], s["e"], state=s["state"].to_numpy(dtype=object), by=s["entered_by"].to_numpy(dtype=object),
                           **flags, **{f"s{i}": (sc == i).astype("float64") for i in range(len(STATES))})
        re = s[s["state"] == "Reactivate"]
        self.i_reactivate = Idx(re["u"], re["e"])                                    # M4 lapse outcome

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
        a["is_block"] = (dec & (a["blocked_actions"].fillna("[]") != "[]")).astype("float64")
        a["is_agent"] = (ch == "agent_call").astype("float64")
        self.actions = a
        la = ch.map({k: i + 1 for i, k in enumerate(["do_nothing"] + OPTIONAL_ACTIONS)}).fillna(0).to_numpy("float64")
        self.last_action_names = ["none", "do_nothing"] + OPTIONAL_ACTIONS
        d = a[dec]
        lad = la[dec.to_numpy()]
        self.i_dec = Idx(d["u"], d["d"], last_action=lad, is_dn=d["is_dn"].to_numpy(), is_opt=d["is_opt"].to_numpy(),
                         is_block=d["is_block"].to_numpy(), is_agent=d["is_agent"].to_numpy(), one=np.ones(len(d)))
        o = d[d["is_opt"] > 0]
        self.i_opt = Idx(o["u"], o["d"])
        s = a[a["sent"] != NAT]
        cat = s["category"].fillna("")
        self.i_sent = {"all": Idx(s["u"], s["sent"]), "promo": Idx(s.loc[cat == "promotional", "u"], s.loc[cat == "promotional", "sent"]),
                       "txn": Idx(s.loc[cat == "transactional", "u"], s.loc[cat == "transactional", "sent"])}
        for chn in CHANNELS:
            m = s["channel"] == chn
            self.i_sent[chn] = Idx(s.loc[m, "u"], s.loc[m, "sent"])

    # ---- category value ------------------------------------------------------------------------
    def _value(self):
        v = self.T["category_value"].copy()
        v["m"] = ms(v["month"])
        v["margin"] = ordinal(v["margin_band"], BAND_MARGIN)
        v["rcost"] = ordinal(v["return_cost_band"], BAND_RETURN_COST)
        v["stock"] = ordinal(v["stock_status"], STOCK)
        self.value = v.set_index(["category", "m"])[["margin", "rcost", "stock"]]

    def lookup_value(self, cat_names: np.ndarray, t_ms: np.ndarray) -> pd.DataFrame:
        """margin / return cost / stock of a category in the calendar month of t (the table is monthly)."""
        month = from_ms(t_ms).dt.tz_convert("UTC").dt.strftime("%Y-%m-01")
        mm = ms(pd.to_datetime(month, utc=True))
        idx = pd.MultiIndex.from_arrays([pd.Series(cat_names, dtype=object).fillna("none").to_numpy(), mm])
        pos = self.value.index.get_indexer(idx)
        out = np.full((len(pos), 3), np.nan)
        ok = pos >= 0
        out[ok] = self.value.to_numpy()[pos[ok]]
        return pd.DataFrame(out, columns=["margin", "rcost", "stock"])

    # ---- events --------------------------------------------------------------------------------
    def _events(self, ev: pd.DataFrame):
        ev = ev.copy()
        ev["u"] = self.u(ev["unit_id"])
        ev["i"] = ms(ev["ingested_at"])
        ev = ev[ev["u"] >= 0]
        ga = ev[ev["source_system"] == "ga4"]
        g = ga["ga4_event"].fillna("")
        pv = ga[(ga["event_type"] == "page_view") | (g == "page_view")]
        self.i_pv = Idx(pv["u"], pv["i"])
        ss = pv.dropna(subset=["session_id"]).groupby(["u", "session_id"])["i"].min().reset_index()
        self.i_sess = Idx(ss["u"], ss["i"])
        self.i_view_item = Idx(ga.loc[g == "view_item", "u"], ga.loc[g == "view_item", "i"])
        self.i_cart = Idx(ga.loc[g.str.contains("cart"), "u"], ga.loc[g.str.contains("cart"), "i"])
        self.i_checkout = Idx(ga.loc[g.str.contains("checkout"), "u"], ga.loc[g.str.contains("checkout"), "i"])
        co = ev[ev["event_type"] == "consent_change"]
        chn = co["pchannel"].fillna(co["channel"])
        stt = co["consent_status"].fillna(co["pstatus"]).fillna("none")
        self.i_consent = {}
        for ch in CHANNELS:
            m = (chn == ch).to_numpy()
            self.i_consent[ch] = Idx(co.loc[m, "u"], co.loc[m, "i"], status=stt[m].to_numpy(dtype=object),
                                     wd=(stt[m] == "withdrawn").to_numpy("float64"))
        ms_ = ev[(ev["event_type"] == "message_status") & ev["source_system"].isin(["klaviyo", "whatsapp"])]
        self.i_msg = {s_: Idx(ms_.loc[ms_["pstatus"] == s_, "u"], ms_.loc[ms_["pstatus"] == s_, "i"])
                      for s_ in ["delivered", "opened", "clicked", "bounced", "unsubscribed"]}


# --------------------------------------------------------------------------- feature blocks
def nanfill(names, n):
    return {k: np.full(n, np.nan) for k in names}


def block_profile(c: Ctx, sp: dict) -> dict:
    t = sp["t"]
    b = c.cust.reindex(sp["unit_id"])
    created = c.created[sp["u"]]
    f = {"device_class": b["device_class"].to_numpy(), "acquisition_channel": b["acquisition_channel"].to_numpy(),
         "geo_tier": b["geo_tier"].to_numpy(), "regime_first_seen": b["regime_first_seen"].to_numpy(),
         "tenure__days": days(t, created)}
    f["tenure__log_days"] = np.log1p(np.maximum(f["tenure__days"], 0))
    return f


def block_time(c: Ctx, sp: dict) -> dict:
    loc = from_ms(sp["t"]).dt.tz_convert(LOCAL_TZ)
    h, wd = loc.dt.hour.to_numpy("float64"), loc.dt.weekday.to_numpy("float64")
    return {"time__hour": h, "time__weekday": wd, "time__day_of_month": loc.dt.day.to_numpy("float64"),
            "time__month": loc.dt.month.to_numpy("float64"), "time__is_month_end": loc.dt.is_month_end.to_numpy("float64"),
            "time__hour_sin": np.sin(2 * np.pi * h / 24), "time__hour_cos": np.cos(2 * np.pi * h / 24),
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
        f["state__ever_" + name.lower().replace(" ", "_")] = (I.total(f"s{i}", u, t) > 0).astype("float64")
    return f


def top_category(c: Ctx, u, t):
    cnt = np.stack([c.i_ord.total(f"cat{i}", u, t) for i in range(len(CATEGORIES))], axis=1)
    mx = cnt.max(axis=1)
    names = np.array(CATEGORIES, dtype=object)[cnt.argmax(axis=1)]
    names[mx <= 0] = None
    return names, (cnt > 0).sum(axis=1).astype("float64")


def block_orders(c: Ctx, sp: dict) -> dict:
    u, t = sp["u"], sp["t"]
    O = c.i_ord
    n = O.count(u, t)
    pos = O.last(u, t)
    lo = O._lo(u)
    first_t = np.where(n > 0, O.t[np.clip(lo, 0, max(len(O.t) - 1, 0))] if len(O.t) else np.nan, np.nan)
    last_t = O.time_at(pos)
    f = {"orders_total": n, "orders_30d": O.count(u, t, W30), "orders_90d": O.count(u, t, W90), "has_order": (n > 0).astype("float64"),
         "days_since_last_order": days(t, last_t), "days_since_first_order": days(t, first_t)}
    with np.errstate(invalid="ignore", divide="ignore"):
        gap = np.where(n > 1, (last_t - first_t) / np.maximum(n - 1, 1) / DAY, np.nan)
        f["recency_ratio"] = np.where(gap > 0, f["days_since_last_order"] / gap, np.nan)
        f["cancel_rate_prior"] = np.where(n > 0, c.i_cancel.count(u, t) / n, np.nan)
        f["cod_share_prior"] = np.where(n > 0, O.total("cod", u, t) / n, np.nan)
        f["discount_share_prior"] = np.where(n > 0, O.total("disc", u, t) / n, np.nan)
        f["avg_amount_band_prior"] = np.where(n > 0, O.total("amt", u, t) / n, np.nan)
    f["last_amount_band"] = O.get("amt", pos)
    f["top_category"], f["n_categories_prior"] = top_category(c, u, t)
    f["n_categories_prior"] = np.where(n > 0, f["n_categories_prior"], np.nan)
    # returns and refunds, each only once its own status timestamp is <= t
    R, F = c.i_res, c.i_refund
    res = R.count(u, t)
    rto = R.total("rto", u, t)
    nref = F.count(u, t)
    with np.errstate(invalid="ignore", divide="ignore"):
        f["rto_count_prior"] = rto
        f["rto_rate_prior"] = np.where(res > 0, rto / res, np.nan)
        f["refund_count_prior"] = nref
        f["refund_rate_prior"] = np.where(n > 0, nref / n, np.nan)
        f["refund_size_fit_share"] = np.where(nref > 0, F.total("size", u, t) / np.maximum(nref, 1), np.nan)
    f["orders_delivered_prior"] = c.i_deliv.count(u, t)
    return f


def block_payments(c: Ctx, sp: dict) -> dict:
    u, t = sp["u"], sp["t"]
    P = c.i_pay
    fails90, att90 = P.total("fail", u, t, W90), P.count(u, t, W90)
    att = P.count(u, t)
    with np.errstate(invalid="ignore", divide="ignore"):
        return {"failed_payments_90d": fails90, "payment_attempts_90d": att90,
                "card_failure_share": np.where(fails90 > 0, P.total("cardfail", u, t, W90) / np.maximum(fails90, 1), np.nan),
                "payment_fail_rate_prior": np.where(att > 0, P.total("fail", u, t) / np.maximum(att, 1), np.nan),
                "has_payment_history": (att > 0).astype("float64")}


def block_support(c: Ctx, sp: dict) -> dict:
    u, t = sp["u"], sp["t"]
    T = c.i_tix
    created = T.count(u, t)
    return {"tickets__90d": T.count(u, t, W90), "delivery_tickets__90d": T.total("deliv", u, t, W90),
            "tickets_total": created, "open_ticket_at_t": ((created - c.i_tix_solved.count(u, t)) > 0).astype("float64"),
            "last_csat": c.i_csat.get("csat", c.i_csat.last(u, t))}


def block_messaging(c: Ctx, sp: dict) -> dict:
    u, t = sp["u"], sp["t"]
    S = c.i_sent
    f = {"msgs_sent_7d": S["all"].count(u, t, W7), "msgs_sent_30d": S["all"].count(u, t, W30),
         "msgs_promo_30d": S["promo"].count(u, t, W30), "msgs_txn_30d": S["txn"].count(u, t, W30),
         "msgs_days_since_last": days(t, S["all"].time_at(S["all"].last(u, t)))}
    for ch in CHANNELS:
        f[f"msgs_{ch}_30d"] = S[ch].count(u, t, W30)
    if c.has_events:
        M = c.i_msg
        dlv, opn, clk = M["delivered"].count(u, t, W30), M["opened"].count(u, t, W30), M["clicked"].count(u, t, W30)
        f.update({"opened_30d": opn, "clicked_30d": clk, "delivered_30d": dlv, "bounced_30d": M["bounced"].count(u, t, W30),
                  "unsubscribed": (M["unsubscribed"].count(u, t) > 0).astype("float64")})
        with np.errstate(invalid="ignore", divide="ignore"):
            f["open_rate_30d"] = np.where(dlv > 0, opn / dlv, np.nan)
            f["click_rate_30d"] = np.where(dlv > 0, clk / dlv, np.nan)
    else:
        f.update(nanfill(["opened_30d", "clicked_30d", "delivered_30d", "bounced_30d", "unsubscribed", "open_rate_30d", "click_rate_30d"], len(u)))
    return f


def block_actions(c: Ctx, sp: dict) -> dict:
    u, t = sp["u"], sp["t"]
    I = c.i_dec
    f = {"act__decisions__30d": I.total("one", u, t, W30), "act__decisions__90d": I.total("one", u, t, W90),
         "act__do_nothing__30d": I.total("is_dn", u, t, W30), "act__blocked__30d": I.total("is_block", u, t, W30),
         "act__optional__7d": I.total("is_opt", u, t, W7), "act__optional__30d": I.total("is_opt", u, t, W30),
         "act__optional__90d": I.total("is_opt", u, t, W90), "act__agent_calls__90d": I.total("is_agent", u, t, W90)}
    pos = I.last(u, t)
    f["act__last_action"] = np.array(c.last_action_names, dtype=object)[np.nan_to_num(I.get("last_action", pos, fill=0.0)).astype(int)]
    f["act__days_since_last_optional"] = days(t, c.i_opt.time_at(c.i_opt.last(u, t)))
    return f


def block_web(c: Ctx, sp: dict) -> dict:
    u, t = sp["u"], sp["t"]
    names = ["web__page_views__7d", "web__page_views__30d", "web__sessions__7d", "web__sessions__30d", "web__days_since_last_visit",
             "web__has_history", "view_item_7d", "cart_events_7d", "abandoned_checkout_7d"]
    if not c.has_events:
        return nanfill(names, len(u))
    f = {"web__page_views__7d": c.i_pv.count(u, t, W7), "web__page_views__30d": c.i_pv.count(u, t, W30),
         "web__sessions__7d": c.i_sess.count(u, t, W7), "web__sessions__30d": c.i_sess.count(u, t, W30),
         "web__days_since_last_visit": days(t, c.i_pv.time_at(c.i_pv.last(u, t))),
         "web__has_history": (c.i_pv.count(u, t) > 0).astype("float64"),
         "view_item_7d": c.i_view_item.count(u, t, W7), "cart_events_7d": c.i_cart.count(u, t, W7)}
    f["abandoned_checkout_7d"] = ((c.i_checkout.count(u, t, W7) > 0) & (c.i_ord.count(u, t, W7) == 0)).astype("float64")
    return f


def block_consent(c: Ctx, sp: dict) -> dict:
    u, t = sp["u"], sp["t"]
    f = {}
    for ch in CHANNELS:
        if not c.has_events:
            f.update({f"consent__{ch}": np.full(len(u), None, dtype=object), f"consent__{ch}_days_since_change": np.full(len(u), np.nan),
                      f"consent__{ch}_ever_withdrawn": np.full(len(u), np.nan)})
            continue
        I = c.i_consent[ch]
        p = I.last(u, t)
        f[f"consent__{ch}"] = I.get("status", p, fill="none")            # no record = none = treat as unknown / hold
        f[f"consent__{ch}_days_since_change"] = days(t, I.time_at(p))
        f[f"consent__{ch}_ever_withdrawn"] = (I.total("wd", u, t) > 0).astype("float64")
    return f


def block_value(c: Ctx, sp: dict) -> dict:
    cat, _ = top_category(c, sp["u"], sp["t"])
    v = c.lookup_value(cat, sp["t"])
    return {"value__margin_band_top_category": v["margin"].to_numpy(), "value__return_cost_top_category": v["rcost"].to_numpy(),
            "value__stock_top_category": v["stock"].to_numpy()}


ALL_BLOCKS = [block_profile, block_time, block_state, block_orders, block_payments, block_support, block_messaging,
              block_actions, block_web, block_consent, block_value]


def build_block_features(c: Ctx, spine: pd.DataFrame, blocks=ALL_BLOCKS) -> pd.DataFrame:
    sp = {"unit_id": spine["unit_id"], "u": c.u(spine["unit_id"]), "t": ms(spine["t"])}
    out = {}
    for blk in blocks:
        out.update(blk(c, sp))
    return downcast(pd.DataFrame(out, index=spine.index))


def mk_spine(unit, t) -> pd.DataFrame:
    sp = pd.DataFrame({"unit_id": np.asarray(unit), "t": pd.to_datetime(np.asarray(t), utc=True)})
    sp["t"] = pd.to_datetime(sp["t"], utc=True)
    return sp


def std_cols(df: pd.DataFrame, t_col: str, mode: str) -> pd.DataFrame:
    # population: "lead" = no order before the prediction time, "customer" = at least one earlier order.
    # One table serves both because the outcome is the same event; filter on this column to train them separately.
    if "orders_total" in df:
        df.insert(1, "population", np.where(df["orders_total"].fillna(0) > 0, "customer", "lead"))
    df["split"] = assign_split(df, t_col, mode=mode)
    return df


# --------------------------------------------------------------------------- M1
def build_m1(c: Ctx, split_mode: str) -> pd.DataFrame:
    months = pd.date_range(pd.Timestamp(M1_FIRST_MONTH, tz="UTC"), pd.Timestamp(M1_LAST_MONTH, tz="UTC"), freq="MS")
    cu = c.T["customers"]
    parts = []
    for t0 in months:
        m = c.created <= ms(pd.Series([t0]))[0]
        parts.append(pd.DataFrame({"unit_id": cu["unit_id"].to_numpy()[m], "t": t0}))
    sp = pd.concat(parts, ignore_index=True)
    sp["t"] = pd.to_datetime(sp["t"], utc=True)
    X = build_block_features(c, sp).reset_index(drop=True)
    u, t = c.u(sp["unit_id"]), ms(sp["t"])
    out = pd.concat([sp[["unit_id"]].reset_index(drop=True), X], axis=1)
    out["prediction_time"] = sp["t"].to_numpy()
    out["y_order_30d"] = (c.i_kept.count(u, t + W30, W30) > 0).astype("int8")            # delivered and not cancelled
    out["y_order_created_30d"] = (c.i_ord.count(u, t + W30, W30) > 0).astype("int8")    # any order created (comparison only)
    out["holdout_group"] = c.cust["holdout_group"].reindex(out["unit_id"]).to_numpy()
    out["label_final"] = ((out["prediction_time"] + pd.Timedelta(days=30 + DELIVERY_BUFFER)) <= EXTRACT).to_numpy()
    return std_cols(out, "prediction_time", split_mode)


# --------------------------------------------------------------------------- M2
def build_m2(c: Ctx, split_mode: str) -> pd.DataFrame:
    o = c.orders.reset_index(drop=True)
    t = o["cr"].to_numpy()
    sp = mk_spine(o["unit_id"], from_ms(t - 1).to_numpy())            # customer history strictly before this order
    X = build_block_features(c, sp).reset_index(drop=True)
    u = c.u(o["unit_id"])
    n_prior = X["orders_total"].to_numpy()
    f = pd.DataFrame(index=X.index)
    f["is_first_order"] = (n_prior == 0).astype("float32")
    f["payment_mode_cod"] = o["cod"].to_numpy("float32")
    f["amount_band"] = o["amt"].to_numpy("float32")
    f["item_count"] = o["item_count"].to_numpy("float32")
    f["discount_band"] = ordinal(o["discount_band"], BAND_DISCOUNT)
    f["has_discount"] = o["disc"].to_numpy("float32")
    f["order_source"] = o["order_source"].to_numpy()
    f["order_channel"] = o["channel"].to_numpy()
    f["category_primary"] = o["category_primary"].to_numpy()
    loc = from_ms(t).dt.tz_convert(LOCAL_TZ)
    f["order_hour"] = loc.dt.hour.to_numpy("float32")
    f["order_weekday"] = loc.dt.weekday.to_numpy("float32")
    f["cod_x_amount"] = (o["cod"] * o["amt"]).to_numpy("float32")
    # rolling population RTO rates from orders whose delivery status was already known at this order's time
    cr, cn = c.i_cat_res, c.i_cod_res
    cc, tt = o["catc"].to_numpy(), t - 1
    r_cat, n_cat = cr.total("rto", cc, tt), cr.count(cc, tt)
    r_cod, n_cod = cn.total("rto", o["cod"].to_numpy().astype("int64"), tt), cn.count(o["cod"].to_numpy().astype("int64"), tt)
    with np.errstate(invalid="ignore", divide="ignore"):
        f["category_rto_rate"] = np.where(n_cat >= 30, r_cat / np.maximum(n_cat, 1), np.nan).astype("float32")
        f["payment_mode_rto_rate"] = np.where(n_cod >= 30, r_cod / np.maximum(n_cod, 1), np.nan).astype("float32")
    v = c.lookup_value(o["category_primary"].to_numpy(dtype=object), t)
    f["margin_band"], f["return_cost_band"] = v["margin"].to_numpy("float32"), v["rcost"].to_numpy("float32")
    # attempts at this order's own checkout before it was created
    ck = pd.Series(o["checkout_id"]).map(c.checkout_codes).fillna(-1).to_numpy("int64")
    f["checkout_attempts_before"] = c.i_pay_ck.count(ck, tt).astype("float32")
    f["checkout_failed_before"] = c.i_pay_ck.total("fail", ck, tt).astype("float32")
    out = pd.concat([o[["order_id"]].reset_index(drop=True), o[["unit_id"]].reset_index(drop=True), X, f], axis=1)
    out["prediction_time"] = from_ms(t).to_numpy()
    out["y_rto"] = o["rto_flag"].astype("int8").to_numpy()
    out["y_refund_45d"] = ((o["rfd"] != NAT) & (o["rfd"] <= o["cr"] + 45 * DAY)).astype("int8").to_numpy()
    out["holdout_group"] = c.cust["holdout_group"].reindex(out["unit_id"]).to_numpy()
    out["label_final"] = ((out["prediction_time"] + pd.Timedelta(days=45)) <= EXTRACT).to_numpy()
    return std_cols(out, "prediction_time", split_mode)


# --------------------------------------------------------------------------- M3
def parse_blocked(s: pd.Series) -> pd.DataFrame:
    """allowed_<action> flags and blocked_reason_<code> flags from the list of {action, reason_code}. A block with reason
       in_holdout is the treatment assignment, not eligibility, so it is ignored."""
    n = len(s)
    out = {f"allowed_{a}": np.ones(n) for a in OPTIONAL_ACTIONS}
    reasons: dict[str, np.ndarray] = {}
    for i, v in enumerate(s.fillna("[]").to_numpy()):
        if v in ("[]", ""):
            continue
        for it in json.loads(v):
            r = it.get("reason_code")
            if r == "in_holdout":
                continue
            a = it.get("action")
            if f"allowed_{a}" in out:
                out[f"allowed_{a}"][i] = 0.0
            reasons.setdefault(r, np.zeros(n))[i] = 1.0
    for r, v in reasons.items():
        out[f"blocked_reason_{r}"] = v
    return pd.DataFrame(out, index=s.index).astype("float32")


def build_m3(c: Ctx, split_mode: str) -> pd.DataFrame:
    a = c.actions
    d = a[(a["record_kind"] == "decision") & (a["regime"] == "randomised_holdout")].copy().reset_index(drop=True)
    t = d["d"].to_numpy()
    sp = mk_spine(d["unit_id"], from_ms(t - 1).to_numpy())            # the decision itself is not history
    X = build_block_features(c, sp).reset_index(drop=True)
    X["trigger"] = d["trigger"].to_numpy()
    X["state_at_decision"] = d["state"].to_numpy()
    X = pd.concat([X, parse_blocked(d["blocked_actions"]).reset_index(drop=True)], axis=1)
    out = pd.concat([d[["action_id", "unit_id"]], X], axis=1)
    out["prediction_time"] = from_ms(t).to_numpy()
    ch = d["chosen_action"]
    out["w_any"] = ch.isin(OPTIONAL_ACTIONS).astype("int8").to_numpy()
    out["w_action"] = ch.to_numpy()
    out["propensity"] = d["propensity"].to_numpy("float32")
    out["in_holdout"] = d["in_holdout"].astype(bool).to_numpy()
    out["holdout_group"] = d["holdout_group"].to_numpy()
    forced = (ch == "do_nothing") & (d["propensity"] == 1.0) & (~d["in_holdout"].astype(bool))
    out["is_forced_do_nothing"] = forced.to_numpy()                       # every other action was blocked: not comparable
    out["is_valid_control"] = ((ch == "do_nothing") & ~forced).to_numpy() # holdout rows + policy-chosen do_nothing
    out["keep_for_uplift"] = (~forced).to_numpy()
    out["ipw"] = np.where(out["in_holdout"], np.nan, np.clip(1.0 / out["propensity"], 1.0, 10.0)).astype("float32")
    u = c.u(d["unit_id"])
    cart = (d["trigger"] == "cart").to_numpy()
    weekly = (d["trigger"] == "weekly").to_numpy()
    out["y_order_7d"] = np.where(cart, c.i_kept.count(u, t + W7, W7) > 0, np.nan).astype("float32")
    out["y_order_30d"] = np.where(weekly, c.i_kept.count(u, t + W30, W30) > 0, np.nan).astype("float32")
    out["y_order"] = np.where(cart, out["y_order_7d"], out["y_order_30d"]).astype("float32")          # the window of the trigger
    fin = ((out["prediction_time"] + pd.Timedelta(days=M3_FINAL_DAYS)) <= EXTRACT).to_numpy()
    out["final_y_order_7d"] = fin & cart
    out["final_y_order_30d"] = fin & weekly
    out["label_final"] = fin
    return std_cols(out, "prediction_time", split_mode)


def _boot(h: pd.DataFrame, ycol: str, arm: np.ndarray, reps: int, rng) -> dict:
    """Treated arm against the random holdout and against the policy-chosen do_nothing (inverse-propensity weighted).
       The bootstrap resamples customers, using per-customer sums."""
    y = h[ycol].to_numpy("float64")
    ho = h["in_holdout"].to_numpy()
    pc = (h["is_valid_control"] & ~h["in_holdout"]).to_numpy()
    w = np.nan_to_num(h["ipw"].to_numpy("float64"), nan=0.0)
    f = lambda m: m.astype("float64")
    arm_w = arm & ~ho
    agg = pd.DataFrame({"u": h["unit_id"].to_numpy(), "ntr": f(arm), "ytr": f(arm) * y, "nho": f(ho), "yho": f(ho) * y,
                        "wtr": f(arm_w) * w, "wytr": f(arm_w) * w * y, "wpc": f(pc) * w, "wypc": f(pc) * w * y}).groupby("u").sum()
    A = agg.to_numpy()
    ix = {k: i for i, k in enumerate(agg.columns)}

    def stat(m):
        s = m @ A
        dv = lambda a, b: s[ix[a]] / s[ix[b]] if s[ix[b]] > 0 else np.nan
        r_tr, r_ho, p_tr, p_pc = dv("ytr", "ntr"), dv("yho", "nho"), dv("wytr", "wtr"), dv("wypc", "wpc")
        return r_tr, r_ho, r_tr - r_ho, p_pc, p_tr - p_pc

    base = stat(np.ones(len(A)))
    lo = [np.nan, np.nan]; hi = [np.nan, np.nan]
    if len(A) >= 30:
        M = rng.multinomial(len(A), np.full(len(A), 1.0 / len(A)), size=reps).astype("float64")
        bs = np.array([stat(M[r]) for r in range(reps)], dtype=float)
        for j, col in enumerate([2, 4]):
            if np.isfinite(bs[:, col]).any():
                lo[j], hi[j] = np.nanpercentile(bs[:, col], [2.5, 97.5])
    return {"n_treated": int(arm.sum()), "n_holdout": int(ho.sum()), "n_policy_control": int(pc.sum()),
            "rate_treated": base[0], "rate_holdout": base[1], "uplift_vs_holdout": base[2],
            "uplift_vs_holdout_ci_low": lo[0], "uplift_vs_holdout_ci_high": hi[0],
            "rate_policy_control": base[3], "uplift_vs_policy_ctrl": base[4],
            "uplift_vs_policy_ctrl_ci_low": lo[1], "uplift_vs_policy_ctrl_ci_high": hi[1]}


def m3_uplift_check(m3: pd.DataFrame, reps: int = BOOTSTRAP_REPS) -> pd.DataFrame:
    """Raw gaps by trigger and action. These are plain averages with intervals, not the M3 model: use them to see where
       the signal is and to sanity-check M3. Final randomised rows only; forced do_nothing rows are dropped."""
    rng = np.random.default_rng(RANDOM_SEED)
    d = m3[m3["keep_for_uplift"] & m3["label_final"]]
    rows = []
    for trig, ycol in [("cart", "y_order_7d"), ("weekly", "y_order_30d")]:
        g = d[(d["trigger"] == trig) & d[ycol].notna()]
        arms = [("any action", (g["w_any"] == 1).to_numpy())] + [(a, (g["w_action"] == a).to_numpy()) for a in OPTIONAL_ACTIONS]
        for name, arm in arms:
            if arm.sum() == 0:
                continue
            rows.append({"trigger": trig, "outcome": ycol, "action": name, "n_rows": len(g), **_boot(g, ycol, arm, reps, rng)})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- M4
def build_m4(c: Ctx, split_mode: str, horizon_days: int = 30) -> pd.DataFrame:
    cu = c.T["customers"]
    n = len(cu)
    WEEK, H = 7 * DAY, horizon_days * DAY
    epoch_monday = 4 * DAY
    end_ms = ms(pd.Series([EXTRACT]))[0]
    first_w = ((c.created - epoch_monday + WEEK - 1) // WEEK) * WEEK + epoch_monday
    nw = np.where(first_w <= end_ms, (end_ms - first_w) // WEEK + 1, 0)
    unit = np.repeat(np.arange(n), nw)
    k = np.arange(nw.sum()) - np.repeat(np.cumsum(nw) - nw, nw)
    wk = first_w[unit] + k * WEEK
    print(f"  M4: {len(wk):,} customer-weeks")
    sp = mk_spine(cu["unit_id"].to_numpy()[unit], from_ms(wk).to_numpy())
    parts = []
    for s0 in range(0, len(sp), 250_000):
        parts.append(build_block_features(c, sp.iloc[s0:s0 + 250_000]).reset_index(drop=True))
        print(f"    rows built: {min(s0 + 250_000, len(sp)):,}")
    X = pd.concat(parts, ignore_index=True)
    X.insert(0, "unit_id", sp["unit_id"].to_numpy())
    X.insert(1, "week_start", sp["t"].to_numpy())
    X["prediction_time"] = sp["t"].to_numpy()
    # outcome: the first of a kept order or entering Reactivate inside the horizon
    best_t = np.full(len(wk), np.inf)
    best_k = np.full(len(wk), "stay", dtype=object)
    for name, I in [("kept_order", c.i_kept), ("lapse", c.i_reactivate)]:
        tn = I.time_at(I.next_after(unit, wk))
        ok = (~np.isnan(tn)) & (tn <= wk + H)
        better = ok & (tn < best_t)
        best_t, best_k = np.where(better, tn, best_t), np.where(better, name, best_k)
    X["y4_outcome"] = best_k
    X["treat_any_next7d"] = (c.i_opt.count(unit, wk + W7, W7) > 0).astype("int8")     # treatment during the week; NOT a feature
    X["holdout_group"] = c.cust["holdout_group"].to_numpy()[unit]
    X["label_final"] = ((X["prediction_time"] + pd.Timedelta(days=horizon_days + DELIVERY_BUFFER)) <= EXTRACT).to_numpy()
    return std_cols(X, "prediction_time", "time")


def cohort_summary(m4: pd.DataFrame, reps: int = BOOTSTRAP_REPS) -> pd.DataFrame:
    """Observed outcome shares by cohort with bootstrap intervals over customers: the M4 cohort check (predicted shares
       should match these)."""
    rng = np.random.default_rng(RANDOM_SEED)
    d = m4[m4["label_final"]]
    rows = []
    for dim in ["state__current", "acquisition_channel", "geo_tier", "regime_first_seen"]:
        for val, h in d.groupby(dim, observed=True):
            codes, outs = pd.factorize(h["y4_outcome"])
            uc, ui = np.unique(h["unit_id"].to_numpy(), return_inverse=True)
            A = np.zeros((len(uc), len(outs) + 1))
            np.add.at(A, (ui, np.full(len(ui), len(outs))), 1.0)
            np.add.at(A, (ui, codes), 1.0)
            tot = A.sum(0)
            bs = rng.multinomial(len(uc), np.full(len(uc), 1.0 / len(uc)), size=min(reps, 200)).astype("float64") @ A if len(uc) >= 30 else None
            for j, oc in enumerate(outs):
                lo, hi = (np.nanpercentile(bs[:, j] / bs[:, -1], [2.5, 97.5]) if bs is not None else (np.nan, np.nan))
                rows.append({"cohort_dim": dim, "cohort": val, "outcome": oc, "share": tot[j] / tot[-1], "ci_low": lo, "ci_high": hi,
                             "n_rows": len(h), "n_customers": len(uc)})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- feature dictionary
FAMILY_PREFIX = [("tenure__", "1 tenure"), ("acquisition_channel", "2 acquisition channel"), ("regime_first_seen", "3 regime"),
                 ("consent__", "4 consent"), ("web__", "5 web behaviour"), ("view_item", "5 web behaviour"), ("cart_events", "5 web behaviour"),
                 ("abandoned_checkout", "5 web behaviour"), ("msgs_", "6 messaging"), ("opened_", "6 messaging"), ("clicked_", "6 messaging"),
                 ("delivered_30d", "6 messaging"), ("bounced_", "6 messaging"), ("unsubscribed", "6 messaging"), ("open_rate", "6 messaging"),
                 ("click_rate", "6 messaging"), ("act__", "7 action history"), ("state__", "8 lifecycle state"), ("tickets", "9 support"),
                 ("delivery_tickets", "9 support"), ("open_ticket", "9 support"), ("last_csat", "9 support"),
                 ("failed_payments", "10 payment history"), ("payment_", "10 payment history"), ("card_failure", "10 payment history"),
                 ("has_payment", "10 payment history"), ("checkout_", "10 payment history"), ("orders_", "11 recency and frequency"),
                 ("days_since_", "11 recency and frequency"), ("recency_ratio", "11 recency and frequency"), ("has_order", "11 recency and frequency"),
                 ("cancel_rate", "11 recency and frequency"), ("cod_share", "11 recency and frequency"), ("discount_share", "11 recency and frequency"),
                 ("n_categories", "11 recency and frequency"), ("top_category", "11 recency and frequency"), ("rto_", "returns"),
                 ("refund_", "returns"), ("avg_amount", "12 amount band"), ("last_amount", "12 amount band"), ("amount_band", "12 amount band"),
                 ("cod_x_amount", "12 amount band"), ("time__", "13 time of prediction"), ("order_", "order (M2)"), ("is_first_order", "order (M2)"),
                 ("item_count", "order (M2)"), ("discount_band", "order (M2)"), ("has_discount", "order (M2)"), ("category_", "order (M2)"),
                 ("margin_band", "value"), ("return_cost_band", "value"), ("value__", "value"), ("allowed_", "M3 eligibility"),
                 ("blocked_reason_", "M3 eligibility"), ("device_class", "profile"), ("geo_tier", "profile"), ("stock", "value")]
META = {"population", "unit_id", "order_id", "action_id", "prediction_time", "week_start", "split", "label_final", "holdout_group", "w_any", "w_action",
        "propensity", "in_holdout", "is_forced_do_nothing", "is_valid_control", "keep_for_uplift", "ipw", "treat_any_next7d",
        "trigger", "state_at_decision"}


def feature_dictionary(tables: dict) -> pd.DataFrame:
    rows = []
    for name, df in tables.items():
        for col in df.columns:
            role = "meta / treatment" if (col in META or col.startswith("label_final")) else \
                   "label" if col.startswith(("y_", "y4_", "final_")) else "feature"
            fam = next((f for p, f in FAMILY_PREFIX if col.startswith(p)), "other") if role == "feature" else ""
            rows.append({"table": name, "column": col, "role": role, "family": fam, "dtype": str(df[col].dtype)})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", required=True, help="folder with the VISIBLE e-commerce parquet files")
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
        print("  events.parquet not used: consent, web, cart/checkout and message-status features will be NaN / none")
    else:
        ev = prep_events(ev)
    print("building indexes ...")
    c = Ctx(tables, ev)
    del ev
    dicts = {}

    def save(name, df):
        df.to_parquet(os.path.join(a.out_dir, f"{name}.parquet"), index=False)
        dicts[name] = df.head(1)
        lab = [x for x in df.columns if x.startswith("y_") and x != "y_order"]
        info = ", ".join(f"{x}={df.loc[df['label_final'], x].mean():.4f}" for x in lab[:3])
        print(f"  {name}: {len(df):,} rows, {int(df['label_final'].sum()):,} final; {info}")

    if "m1" in a.only:
        print("M1 ..."); save("ecom_m1", build_m1(c, a.split_mode))
    if "m2" in a.only:
        print("M2 ..."); save("ecom_m2", build_m2(c, a.split_mode))
    if "m3" in a.only:
        print("M3 ...")
        m3 = build_m3(c, a.split_mode)
        save("ecom_m3", m3)
        chk = m3_uplift_check(m3)
        chk.to_csv(os.path.join(a.out_dir, "ecom_m3_uplift_check.csv"), index=False)
        print(f"  ecom_m3_uplift_check.csv: {len(chk)} rows")
    if "m4" in a.only:
        print("M4 ...")
        m4 = build_m4(c, a.split_mode)
        save("ecom_m4", m4)
        print(m4.loc[m4["label_final"], "y4_outcome"].value_counts(normalize=True).round(4).to_string())
        cohort_summary(m4).to_csv(os.path.join(a.out_dir, "ecom_m4_cohort_summary.csv"), index=False)
    feature_dictionary(dicts).to_csv(os.path.join(a.out_dir, "ecom_feature_dictionary.csv"), index=False)
    print(f"done in {time.time() - t0:.0f}s -> {a.out_dir}")


if __name__ == "__main__":
    main()
