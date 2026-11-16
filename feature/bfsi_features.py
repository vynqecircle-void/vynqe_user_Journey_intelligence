"""
bfsi_features.py  -  point-in-time feature engineering for the BFSI vertical (M1 to M4).

Reads the VISIBLE BFSI tables only (never the hidden tables) and writes training tables:

    bfsi_m1_lead.parquet        one row per person at lead creation          y_disbursed_60d (+ y_apply_30d)
    bfsi_m1_stall.parquet       one row per stall decision                   y_resume_7d (+ y_disbursed_60d)
    bfsi_m2.parquet             one row per instalment, 3 days before due    y_first_attempt_fail
    bfsi_m2_default12m.parquet  one row per loan at disbursal                y_default_12m (calibration check only)
    bfsi_m3.parquet             one row per randomised decision              outcomes per trigger + treatment columns
    bfsi_m4_funnel.parquet      one row per person-week (reduced + weighted) y4_outcome  (before disbursal)
    bfsi_m4_servicing.parquet   one row per borrower-week with a live loan   y4_outcome  (after disbursal)
    bfsi_m4_servicing_summary.csv  observed outcome shares by cohort with bootstrap intervals (M4 calibration check)
    bfsi_feature_dictionary.csv column list with the family each feature belongs to

Run:
    python bfsi_features.py --data-dir D:\\...\\out_bfsi\\visible --out-dir D:\\...\\features_bfsi
    python bfsi_features.py --data-dir ... --out-dir ... --only m1 m2        (subset)
    python bfsi_features.py --data-dir ... --out-dir ... --no-events         (if events.parquet is missing)

Rules enforced everywhere (see the Feature Engineering Report):
    * every feature is computed as of prediction_time t from rows whose own timestamp
      (or ingested_at for events) is <= t;
    * extract-time snapshot columns are never read (see LEAKY_COLUMNS);
    * a label is final only if t + window + 45 days <= extract date; non-final rows keep
      label_final = False and are not labelled zero;
    * amounts are ordinal bands; missing history is NaN with a has_* flag, not zero.

Needs only: pandas, numpy, pyarrow.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=pd.errors.PerformanceWarning)

# --------------------------------------------------------------------------- config
EXTRACT = pd.Timestamp("2026-10-31", tz="UTC")      # extract date of the supplied data
BUFFER_DAYS = 45                                    # late-arrival buffer for labels
RESULT_LAG_DAYS = 2                                 # EMI/mandate results reach the warehouse 1-2 days late
DECISION_LAG_DAYS = 1                               # credit decision becomes visible a day after it is made
LOCAL_TZ = "Asia/Kolkata"                           # BFSI is India: hour/weekday features in local time
M4_LEAD_ONLY_SAMPLE = 0.10                          # share of Lead-only person-weeks kept in M4
M4_CHUNK = 400_000                                  # rows of M4 processed at a time
SPLIT_FRACTIONS = (0.70, 0.15, 0.15)                # train / validation / test by prediction_time
RANDOM_SEED = 7

DAY = 86_400_000                                    # ms
BIG = 1 << 42                                       # time stride for (unit, time) keys; > any ms timestamp
NAT = np.iinfo("int64").min

OPTIONAL_ACTIONS = ["nudge", "agent_call", "offer", "fee_waiver", "emi_nudge"]
STATES = ["Lead", "Application started", "KYC drop-off", "Consent pending", "In review", "Offer pending",
          "Signing and mandate pending", "Rejected", "Activated", "Repaying", "Late", "Top-up eligible", "Dormant"]
JOURNEY_GROUP = {
    "Lead": "acquire", "Application started": "acquire", "KYC drop-off": "acquire", "Consent pending": "acquire",
    "In review": "acquire", "Offer pending": "acquire", "Signing and mandate pending": "acquire",
    "Activated": "grow_retain", "Repaying": "grow_retain", "Late": "grow_retain", "Top-up eligible": "grow_retain",
    "Rejected": "win_back_exit", "Dormant": "win_back_exit",
}
BANDS_AMOUNT = {"0-10k": 1, "10k-25k": 2, "25k-50k": 3, "50k-100k": 4, "100k-250k": 5, "250k+": 6}
BANDS_TENURE = {"<=12m": 1, "13-24m": 2, "25-36m": 3, "37-60m": 4}
BANDS_RISK = {"band_1": 1, "band_2": 2, "band_3": 3, "band_4": 4}

# Columns that hold an extract-time snapshot or an outcome. Feature code never reads them.
LEAKY_COLUMNS = {
    "borrowers": ["applications_count", "loans_count", "email_consent", "sms_consent", "whatsapp_consent",
                  "do_not_market", "first_application_at"],
    "applications": ["stage", "stage_changed_at", "rejection_reason_category", "sanctioned_amount_band",
                     "disbursed_amount_band", "decision_band"],
    "loans": ["account_status", "closed_at", "closure_type", "defaulted_at", "lender_band_latest"],
    "emi_payments": ["status", "error_category"],          # of the instalment being predicted
    "actions": ["final_status", "expected_value", "reason_codes", "propensity"],
}
# (borrowers.first_application_at is only used to define the M4 population, never as a feature.)


# --------------------------------------------------------------------------- small helpers
def ms(s: pd.Series, nat: int | None = None) -> np.ndarray:
    """tz-aware datetime Series -> int64 milliseconds. NaT -> `nat` (default NAT sentinel)."""
    s = pd.to_datetime(s, utc=True)
    arr = s.dt.tz_localize(None).to_numpy(dtype="datetime64[ms]").astype("int64")
    mask = s.isna().to_numpy()
    arr = arr.copy()
    arr[mask] = NAT if nat is None else nat
    return arr


def from_ms(a: np.ndarray) -> pd.Series:
    return pd.to_datetime(pd.Series(a, dtype="int64"), unit="ms", utc=True)


class Idx:
    """Sorted (unit, time) index with vectorised window counts, sums and 'latest row at or before t'."""

    def __init__(self, unit: np.ndarray, t: np.ndarray, **vals):
        unit = np.asarray(unit, dtype="int64")
        t = np.asarray(t, dtype="int64")
        keep = (unit >= 0) & (t != NAT)
        order = np.lexsort((t[keep], unit[keep]))
        self.u = unit[keep][order]
        self.t = t[keep][order]
        self.key = self.u * BIG + self.t
        self.vals = {k: np.asarray(v)[keep][order] for k, v in vals.items()}
        self._cs: dict[str, np.ndarray] = {}

    def _hi(self, u, t):
        return np.searchsorted(self.key, np.asarray(u, "int64") * BIG + np.asarray(t, "int64"), side="right")

    def count(self, u, t, w=None):
        """rows of the unit with t-w < time <= t  (w=None: all history)."""
        hi = self._hi(u, t)
        lo = self._lo(u) if w is None else self._hi(u, np.maximum(np.asarray(t, "int64") - w, 0))
        return (hi - lo).astype("float64")

    def _lo(self, u):
        return np.searchsorted(self.key, np.asarray(u, "int64") * BIG, side="left")

    def total(self, col, u, t, w=None):
        if col not in self._cs:
            self._cs[col] = np.concatenate([[0.0], np.cumsum(self.vals[col].astype("float64"))])
        cs = self._cs[col]
        hi = self._hi(u, t)
        lo = self._lo(u) if w is None else self._hi(u, np.maximum(np.asarray(t, "int64") - w, 0))
        return cs[hi] - cs[lo]

    def last(self, u, t, back: int = 0):
        """position of the latest row (back=1: the one before it) at or before t for the same unit, else -1."""
        pos = self._hi(u, t) - 1 - back
        ok = (pos >= 0) & (self.u[np.clip(pos, 0, len(self.u) - 1)] == np.asarray(u, "int64")) if len(self.u) else pos < 0
        return np.where(ok, pos, -1)

    def get(self, col, pos, fill=np.nan):
        v = self.vals[col]
        out = np.full(len(pos), fill, dtype=object if v.dtype == object or v.dtype.kind in "US" else "float64")
        ok = pos >= 0
        out[ok] = v[pos[ok]]
        return out

    def time_at(self, pos):
        out = np.full(len(pos), np.nan)
        ok = pos >= 0
        out[ok] = self.t[pos[ok]]
        return out

    def next_after(self, u, t):
        """position of the first row strictly after t for the same unit, else -1."""
        pos = self._hi(u, t)
        ok = (pos < len(self.u)) & (self.u[np.clip(pos, 0, max(len(self.u) - 1, 0))] == np.asarray(u, "int64")) if len(self.u) else pos < 0
        return np.where(ok, pos, -1)


def days(a_ms, b_ms):
    """(a - b) in days with NaN propagation."""
    a = np.asarray(a_ms, "float64")
    b = np.asarray(b_ms, "float64")
    return (a - b) / DAY


def ordinal(series: pd.Series, mapping: dict) -> np.ndarray:
    return series.map(mapping).to_numpy(dtype="float64")


def parse_flags(s: pd.Series, key: str) -> np.ndarray:
    pat = re.compile(r'"%s":\s*(true|false)' % key)
    out = s.fillna("").str.extract(pat)[0]
    return (out == "true").to_numpy(dtype="float64")


# --------------------------------------------------------------------------- data loading
TABLES = ["borrowers", "applications", "application_steps", "loans", "emi_payments", "service_cases",
          "state_history", "actions"]


def load_tables(data_dir: str, use_events: bool = True) -> tuple[dict, pd.DataFrame | None]:
    t = {}
    for name in TABLES:
        path = os.path.join(data_dir, f"{name}.parquet")
        t[name] = pd.read_parquet(path)
    ev = None
    ev_path = os.path.join(data_dir, "events.parquet")
    if use_events and os.path.exists(ev_path):
        cols = ["event_id", "source_event_id", "event_type", "source_system", "unit_id", "occurred_at",
                "ingested_at", "channel", "consent_status", "properties"]
        ev = pd.read_parquet(ev_path, columns=cols)
    return t, ev


def prep_events(ev: pd.DataFrame) -> pd.DataFrame:
    """Dedupe, drop bots / unlinked rows / impossible timestamps, parse the few properties the features need."""
    n0 = len(ev)
    ev = ev[ev["unit_id"].notna()].copy()                                   # only identified rows belong to a unit
    ev = ev[~ev["event_id"].str.startswith("BOT")]                          # bot traffic
    ev = ev[ev["occurred_at"] <= ev["ingested_at"]]                         # occurred_at after ingested_at = invalid
    ev = ev.sort_values("ingested_at", kind="stable").drop_duplicates("source_event_id", keep="first")
    ex = lambda pat, col="properties": ev[col].fillna("").str.extract(pat)[0]
    ev["session_id"] = ex(r'"session_id":\s*"?(\d+)')
    ev["feature"] = ex(r'"feature":\s*"([^"]*)"')
    ev["prop_channel"] = ex(r'"channel":\s*"([^"]*)"')
    ev["prop_purpose"] = ex(r'"purpose":\s*"([^"]*)"')
    ev["prop_status"] = ex(r'"status":\s*"([^"]*)"')
    ev["message_id"] = ex(r'"message_id":\s*"([^"]*)"')
    ev = ev.drop(columns=["properties"])
    print(f"  events: {n0:,} rows -> {len(ev):,} after dedupe / bots / unlinked / bad timestamps")
    return ev


# --------------------------------------------------------------------------- context: all indexes, built once
class Ctx:
    def __init__(self, tables: dict, events: pd.DataFrame | None):
        self.T = tables
        b = tables["borrowers"]
        self.units = pd.Index(b["unit_id"])
        self.borrowers = b.set_index("unit_id")
        self._build_apps()
        self._build_steps()
        self._build_loans_emi()
        self._build_cases()
        self._build_states()
        self._build_actions()
        self.has_events = events is not None
        self.ev = events
        if events is not None:
            self._build_events(events)

    def u(self, s: pd.Series) -> np.ndarray:
        return self.units.get_indexer(s).astype("int64")

    # ---- applications ----------------------------------------------------------------------
    def _build_apps(self):
        a = self.T["applications"].copy()
        a["u"] = self.u(a["unit_id"])
        a["req_ord"] = ordinal(a["requested_amount_band"], BANDS_AMOUNT)
        a["kind_code"] = a["application_kind"].map({"new": 0, "top_up": 1, "win_back": 2}).astype("float64")
        # credit decision becomes visible when it is made. We never read applications.stage; the decision time comes from
        # sanction_date (approved) or stage_changed_at of a rejected application. Plus a one-day ingestion lag.
        dec = a["sanction_date"].copy()
        rej = (a["stage"] == "rejected") & dec.isna()
        dec[rej] = a.loc[rej, "stage_changed_at"]
        a["decision_ms"] = ms(dec) + DECISION_LAG_DAYS * DAY
        a.loc[dec.isna(), "decision_ms"] = NAT
        a["risk_ord"] = ordinal(a["risk_band"], BANDS_RISK)
        a["rejected_flag"] = rej.astype("float64")
        self.apps = a.set_index("application_ref", drop=False)
        self.i_app = Idx(a["u"], ms(a["created_at"]), kind=a["kind_code"].to_numpy(), req=a["req_ord"].to_numpy(),
                         created=ms(a["created_at"]), dec=a["decision_ms"].to_numpy(),
                         risk=a["risk_ord"].to_numpy(), rej=a["rejected_flag"].to_numpy())
        d = a[a["decision_ms"] != NAT]
        self.i_app_rej = Idx(d["u"], d["decision_ms"].to_numpy(), rej=d["rejected_flag"].to_numpy())
        self.i_app_dec = Idx(d["u"], d["decision_ms"].to_numpy(), risk=d["risk_ord"].to_numpy())

    # ---- application steps -----------------------------------------------------------------
    def _build_steps(self):
        s = self.T["application_steps"].copy()
        s["u"] = self.u(s["unit_id"])
        s["st"] = ms(s["started_at"])
        s["ct"] = ms(s["completed_at"])
        z = np.zeros(len(s))
        self.steps = s

        def ix(mask, tcol, **v):
            m = mask.to_numpy()
            return Idx(s.loc[m, "u"], s.loc[m, tcol], **{k: f(s.loc[m]) for k, f in v.items()})

        method = lambda d: d["method"].fillna("").to_numpy(dtype=object)
        reason = lambda d: d["reason_category"].fillna("").to_numpy(dtype=object)
        status = lambda d: d["status"].fillna("").to_numpy(dtype=object)
        T = s["step_type"]
        S = s["status"]
        self.i_kyc_start = ix(T == "kyc", "st", method=method)
        self.i_kyc_failed = ix((T == "kyc") & (S == "failed"), "ct", reason=reason, method=method)
        self.i_kyc_ok = ix((T == "kyc") & (S == "verified"), "ct")
        self.i_aa_on = ix((T == "aa_consent") & (S == "active"), "ct")
        self.i_aa_off = ix((T == "aa_consent") & (S == "revoked"), "ct")
        self.i_aa_fail = ix((T == "aa_fetch") & (S == "failed"), "ct")
        self.i_es_start = ix(T == "esign", "st")
        self.i_es_decl = ix((T == "esign") & (S == "declined"), "ct")
        self.i_mand_start = ix(T == "mandate", "st", method=method)
        self.i_mand_fail = ix((T == "mandate") & (S.isin(["failed", "rejected", "revoked"])), "ct")
        self.i_mand_done = ix(T == "mandate", "ct", status=status, method=method)
        both = pd.concat([s[["u", "st"]].rename(columns={"st": "t"}), s[["u", "ct"]].rename(columns={"ct": "t"})])
        self.i_step_any = Idx(both["u"], both["t"])

    # ---- loans and instalments -------------------------------------------------------------
    def _build_loans_emi(self):
        l = self.T["loans"].copy()
        l["u"] = self.u(l["unit_id"])
        l["open_ms"] = ms(l["opened_at"])
        l["close_ms"] = ms(l["closed_at"], nat=BIG - 1)             # still open = far future
        l["tenure_ord"] = ordinal(l["tenure_band"], BANDS_TENURE)
        l["disb_ord"] = ordinal(l["disbursed_amount_band"], BANDS_AMOUNT)
        l["code"] = np.arange(len(l))
        self.loans = l.set_index("loan_id", drop=False)
        self.loan_by_app = l.drop_duplicates("application_ref").set_index("application_ref")["loan_id"]
        self.i_loan_open = Idx(l["u"], l["open_ms"], one=np.ones(len(l)))
        self.i_loan_close = Idx(l["u"], np.where(l["close_ms"] == BIG - 1, NAT, l["close_ms"]), one=np.ones(len(l)))

        e = self.T["emi_payments"].copy()
        e["due_ms"] = ms(e["due_date"])
        e["cr_ms"] = ms(e["created_at"])
        e = e.merge(l[["loan_id", "code", "open_ms", "application_ref"]], on="loan_id", how="left")
        # one row per instalment: attempt 1
        a1 = e[e["attempt_no"] == 1].sort_values(["loan_id", "instalment_no"]).reset_index(drop=True)
        a1["fail"] = (a1["status"] == "failed").astype("float64")
        a1["manual"] = a1["method"].isin(["manual_upi", "netbanking"]).astype("float64")
        # capture time of the instalment: the captured attempt (any attempt number)
        cap = e[e["status"] == "captured"].groupby(["loan_id", "instalment_no"])["cr_ms"].min().rename("cap_ms")
        a1 = a1.merge(cap, on=["loan_id", "instalment_no"], how="left")
        a1["days_to_capture"] = (a1["cap_ms"] - a1["due_ms"]) / DAY
        self.inst = a1
        self.i_inst = Idx(a1["code"], a1["cr_ms"] + RESULT_LAG_DAYS * DAY, fail=a1["fail"].to_numpy(),
                          manual=a1["manual"].to_numpy(), one=np.ones(len(a1)),
                          err=a1["error_category"].fillna("").to_numpy(dtype=object),
                          failt=np.where(a1["fail"] > 0, a1["cr_ms"], NAT))
        # days-to-capture is known only when the capture itself has happened (it can be a later retry), so it has its own clock
        cp = a1[a1["cap_ms"].notna()]
        self.i_cap = Idx(cp["code"], cp["cap_ms"].to_numpy("int64") + RESULT_LAG_DAYS * DAY,
                         dtc=cp["days_to_capture"].to_numpy(), one=np.ones(len(cp)))

    # ---- service cases ---------------------------------------------------------------------
    def _build_cases(self):
        c = self.T["service_cases"].copy()
        c["u"] = self.u(c["unit_id"])
        c["o"] = ms(c["opened_at"])
        c["c"] = ms(c["closed_at"])
        self.i_case_open = Idx(c["u"], c["o"], one=np.ones(len(c)))
        self.i_case_close = Idx(c["u"], c["c"], one=np.ones(len(c)))
        for cat in ["collections", "dispute", "complaint"]:
            m = c["category"] == cat
            setattr(self, f"i_case_o_{cat}", Idx(c.loc[m, "u"], c.loc[m, "o"]))
            setattr(self, f"i_case_c_{cat}", Idx(c.loc[m, "u"], c.loc[m, "c"]))
        m = c["suppress_marketing"].astype(bool)
        self.i_sup_o = Idx(c.loc[m, "u"], c.loc[m, "o"])
        self.i_sup_c = Idx(c.loc[m, "u"], c.loc[m, "c"])

    # ---- state history ---------------------------------------------------------------------
    def _build_states(self):
        s = self.T["state_history"].copy()
        s["u"] = self.u(s["unit_id"])
        s["e"] = ms(s["entered_at"])
        sc = s["state"].map({k: i for i, k in enumerate(STATES)}).to_numpy("float64")
        one_hot = {f"s{i}": (sc == i).astype("float64") for i in range(len(STATES))}
        self.i_state = Idx(s["u"], s["e"], state=s["state"].to_numpy(dtype=object),
                           by=s["entered_by"].to_numpy(dtype=object),
                           coll=parse_flags(s["flags"], "collections_open"), disp=parse_flags(s["flags"], "dispute_open"),
                           nomkt=parse_flags(s["flags"], "no_marketing_consent"), **one_hot)
        self.state_df = s

    # ---- actions ---------------------------------------------------------------------------
    def _build_actions(self):
        a = self.T["actions"].copy()
        a["u"] = self.u(a["unit_id"])
        a["d"] = ms(a["decided_at"])
        a["sent"] = ms(a["sent_at"])
        ch = a["chosen_action"].fillna("")
        a["is_dec"] = (a["record_kind"] == "decision").astype("float64")
        a["is_dn"] = ((a["record_kind"] == "decision") & (ch == "do_nothing")).astype("float64")
        a["is_opt"] = ch.isin(OPTIONAL_ACTIONS).astype("float64")
        a["is_block"] = ((a["record_kind"] == "decision") & a["blocked_actions"].notna() & (a["blocked_actions"] != "[]")).astype("float64")
        a["is_block_cons"] = a["blocked_actions"].fillna("").str.contains("consent").astype("float64")
        a["is_call"] = ((a["channel"] == "call") | (ch == "agent_call")).astype("float64")
        self.actions = a
        self.msg_cat = a.dropna(subset=["message_id"]).drop_duplicates("message_id").set_index("message_id")["category"]
        la = ch.map({k: i + 1 for i, k in enumerate(["do_nothing"] + OPTIONAL_ACTIONS)}).fillna(0).to_numpy("float64")
        self.last_action_names = ["none", "do_nothing"] + OPTIONAL_ACTIONS
        self.i_act = Idx(a["u"], a["d"], dec=a["is_dec"].to_numpy(), dn=a["is_dn"].to_numpy(), opt=a["is_opt"].to_numpy(),
                         block=a["is_block"].to_numpy(), blockc=a["is_block_cons"].to_numpy(), call=a["is_call"].to_numpy(),
                         last_action=la, one=np.ones(len(a)))
        o = a[(a["is_opt"] > 0)]
        self.i_act_opt = Idx(o["u"], o["d"])
        ig = a[a["task_status"] == "ignored"]
        self.i_task_ign = Idx(ig["u"], ms(ig["task_due_at"]))          # a task counts only once its due date has passed
        s = a[a["sent"] != NAT]
        cat = s["category"].fillna("")
        self.i_sent = {
            "all": Idx(s["u"], s["sent"]),
            "promo": Idx(s.loc[cat == "promotional", "u"], s.loc[cat == "promotional", "sent"]),
            "reg": Idx(s.loc[cat.isin(["regulatory", "transactional"]), "u"], s.loc[cat.isin(["regulatory", "transactional"]), "sent"]),
        }
        for chn in ["email", "sms", "whatsapp"]:
            m = s["channel"] == chn
            self.i_sent[chn] = Idx(s.loc[m, "u"], s.loc[m, "sent"])
        pre = s[(s["trigger"] == "emi_due") & (cat == "regulatory")]
        self.i_predebit = Idx(pre["u"], pre["sent"], mid=pre["message_id"].to_numpy(dtype=object))

    # ---- events ----------------------------------------------------------------------------
    def _build_events(self, ev: pd.DataFrame):
        ev = ev.copy()
        ev["u"] = self.u(ev["unit_id"])
        ev["i"] = ms(ev["ingested_at"])
        pv = ev[ev["event_type"] == "page_view"]
        self.i_pv = Idx(pv["u"], pv["i"], emi=(pv["feature"] == "emi_calculator").to_numpy("float64"))
        sess = pv.dropna(subset=["session_id"]).groupby(["u", "session_id"])["i"].min().reset_index()
        self.i_sess = Idx(sess["u"], sess["i"])
        day = pv.assign(day=pv["i"] // DAY).groupby(["u", "day"])["i"].min().reset_index()
        self.i_pvday = Idx(day["u"], day["i"])                       # first ingest time of each active day
        co = ev[(ev["event_type"] == "consent_change") & (ev["prop_purpose"].fillna("marketing") == "marketing")]
        st = co["consent_status"].fillna(co["prop_status"]).fillna("none")
        self.i_consent = {}
        for chn in ["email", "sms", "whatsapp"]:
            m = (co["prop_channel"] == chn).to_numpy()
            self.i_consent[chn] = Idx(co.loc[m, "u"], co.loc[m, "i"], status=st[m].to_numpy(dtype=object),
                                      wd=(st[m] == "withdrawn").to_numpy("float64"))
        ms_ = ev[ev["event_type"] == "message_status"]
        self.i_msg = {s_: Idx(ms_.loc[ms_["prop_status"] == s_, "u"], ms_.loc[ms_["prop_status"] == s_, "i"])
                      for s_ in ["sent", "delivered", "opened", "clicked", "bounced", "failed", "unsubscribed"]}
        self.i_msg_mid = {s_: ms_.loc[ms_["prop_status"] == s_, ["message_id", "i"]].drop_duplicates("message_id").set_index("message_id")["i"]
                          for s_ in ["delivered"]}


# --------------------------------------------------------------------------- feature blocks
W7, W30, W90 = 7 * DAY, 30 * DAY, 90 * DAY


def block_profile(c: Ctx, sp: dict) -> dict:
    b = c.borrowers.reindex(sp["unit_id"])
    t, u = sp["t"], sp["u"]
    created = ms(b["created_at"])
    f = {
        "acquisition_channel": b["acquisition_channel"].fillna("unknown").to_numpy(),
        "device_class": b["device_class"].fillna("unknown").to_numpy(),
        "geo_tier": b["geo_tier"].fillna("unknown").to_numpy(),
        "existing_customer": b["existing_customer"].astype("float64").to_numpy(),
        "regime_first_seen": b["regime_first_seen"].to_numpy(),
        "tenure__days": days(t, created),
    }
    f["tenure__log_days"] = np.log1p(np.maximum(f["tenure__days"], 0))
    lead_local = pd.to_datetime(b["created_at"], utc=True).dt.tz_convert(LOCAL_TZ)
    f["lead_hour"] = lead_local.dt.hour.to_numpy("float64")
    f["lead_weekday"] = lead_local.dt.weekday.to_numpy("float64")
    f["lead_age_days"] = f["tenure__days"]
    return f


def block_time(c: Ctx, sp: dict) -> dict:
    loc = from_ms(sp["t"]).dt.tz_convert(LOCAL_TZ)
    h, wd, dom = loc.dt.hour.to_numpy("float64"), loc.dt.weekday.to_numpy("float64"), loc.dt.day.to_numpy("float64")
    return {
        "time__hour": h, "time__weekday": wd, "time__day_of_month": dom, "time__month": loc.dt.month.to_numpy("float64"),
        "time__is_month_end": loc.dt.is_month_end.to_numpy("float64"),
        "time__hour_sin": np.sin(2 * np.pi * h / 24), "time__hour_cos": np.cos(2 * np.pi * h / 24),
        "time__weekday_sin": np.sin(2 * np.pi * wd / 7), "time__weekday_cos": np.cos(2 * np.pi * wd / 7),
    }


def block_state(c: Ctx, sp: dict) -> dict:
    u, t = sp["u"], sp["t"]
    I = c.i_state
    pos = I.last(u, t)
    prev = I.last(u, t, back=1)
    st = I.get("state", pos, fill="no_state")
    f = {
        "state__current": st,
        "state__days_in": days(t, I.time_at(pos)),
        "state__entered_by": I.get("by", pos, fill="none"),
        "state__previous": I.get("state", prev, fill="none"),
        "state__changes__90d": I.count(u, t, W90),
        "state__journey_group": pd.Series(st).map(JOURNEY_GROUP).fillna("none").to_numpy(),
        "state__collections_open": I.get("coll", pos), "state__dispute_open": I.get("disp", pos),
        "state__no_marketing_consent": I.get("nomkt", pos),
    }
    for i, name in enumerate(STATES):
        f["state__ever_" + name.lower().replace(" ", "_").replace("-", "_")] = (I.total(f"s{i}", u, t) > 0).astype("float64")
    return f


def block_funnel(c: Ctx, sp: dict) -> dict:
    u, t = sp["u"], sp["t"]
    A = c.i_app
    pos = A.last(u, t)
    f = {
        "apps_started_by_t": A.count(u, t),
        "app_kind": np.array(["none", "new", "top_up", "win_back"], dtype=object)[np.nan_to_num(A.get("kind", pos), nan=-1).astype(int) + 1],
        "requested_amount_band": A.get("req", pos),
        "hours_since_app_start": days(t, A.time_at(pos)) * 24,
    }
    f["has_application"] = (f["apps_started_by_t"] > 0).astype("float64")
    f["apps_rejected_by_t"] = c.i_app_rej.total("rej", u, t)
    last_step = c.i_step_any.last(u, t)
    f["hours_since_last_step"] = days(t, c.i_step_any.time_at(last_step)) * 24
    f["kyc_attempts"] = c.i_kyc_start.count(u, t)
    f["kyc_failed"] = c.i_kyc_failed.count(u, t)
    f["kyc_verified"] = c.i_kyc_ok.count(u, t)
    f["kyc_method_last"] = c.i_kyc_start.get("method", c.i_kyc_start.last(u, t), fill="none")
    f["kyc_reason_last"] = c.i_kyc_failed.get("reason", c.i_kyc_failed.last(u, t), fill="none")
    f["aa_consent_given"] = ((c.i_aa_on.count(u, t) - c.i_aa_off.count(u, t)) > 0).astype("float64")
    f["aa_fetch_failed"] = c.i_aa_fail.count(u, t)
    f["esign_started"] = c.i_es_start.count(u, t)
    f["esign_declined"] = c.i_es_decl.count(u, t)
    f["mandate_attempts"] = c.i_mand_start.count(u, t)
    f["mandate_failed"] = c.i_mand_fail.count(u, t)
    # credit decision, visible only after it was made
    dp = c.i_app_dec.last(u, t)
    f["risk_band_at_decision"] = c.i_app_dec.get("risk", dp)
    return f


def block_service(c: Ctx, sp: dict) -> dict:
    u, t = sp["u"], sp["t"]
    opened = c.i_case_open.count(u, t)
    closed = c.i_case_close.count(u, t)
    f = {"support__cases__90d": c.i_case_open.count(u, t, W90), "support__open_at_t": ((opened - closed) > 0).astype("float64"),
         "support__hold": ((c.i_sup_o.count(u, t) - c.i_sup_c.count(u, t)) > 0).astype("float64")}
    for cat in ["collections", "dispute", "complaint"]:
        f[f"{cat}_open"] = ((getattr(c, f"i_case_o_{cat}").count(u, t) - getattr(c, f"i_case_c_{cat}").count(u, t)) > 0).astype("float64")
    return f


def block_actions(c: Ctx, sp: dict) -> dict:
    u = sp["u"]
    t = sp["t"] - 1                       # strictly before the prediction time: a decision never sees itself
    I = c.i_act
    f = {
        "act__decisions__30d": I.total("dec", u, t, W30), "act__decisions__90d": I.total("dec", u, t, W90),
        "act__do_nothing__30d": I.total("dn", u, t, W30), "act__blocked__30d": I.total("block", u, t, W30),
        "act__blocked_consent__30d": I.total("blockc", u, t, W30), "act__calls__30d": I.total("call", u, t, W30),
        "act__optional__30d": I.total("opt", u, t, W30),
        "act__tasks_ignored__90d": c.i_task_ign.count(u, t - 3 * DAY, W90),
    }
    pos = I.last(u, t)
    la = np.nan_to_num(I.get("last_action", pos, fill=0.0)).astype(int)
    f["act__last_action"] = np.array(c.last_action_names, dtype=object)[la]
    lo = c.i_act_opt.last(u, t)
    f["act__days_since_last_optional"] = days(t, c.i_act_opt.time_at(lo))
    return f


def block_messaging(c: Ctx, sp: dict) -> dict:
    u = sp["u"]
    t = sp["t"] - 1
    f = {}
    for k, name in [("all", "all"), ("promo", "promo"), ("reg", "regulatory")]:
        f[f"msg__sent_{name}__7d"] = c.i_sent[k].count(u, t, W7)
        f[f"msg__sent_{name}__30d"] = c.i_sent[k].count(u, t, W30)
    for chn in ["email", "sms", "whatsapp"]:
        f[f"msg__sent_{chn}__30d"] = c.i_sent[chn].count(u, t, W30)
    f["msg__days_since_last"] = days(t, c.i_sent["all"].time_at(c.i_sent["all"].last(u, t)))
    names = ["msg__ev_sent__30d", "msg__delivered__30d", "msg__opened__30d", "msg__clicked__30d", "msg__bounced__30d",
             "msg__unsubscribed_ever", "msg__delivered_rate__30d", "msg__open_rate__30d", "msg__click_rate__30d"]
    if not c.has_events:                     # keep the schema stable, values unavailable
        for n in names:
            f[n] = np.full(len(u), np.nan)
        return f
    tt = sp["t"]
    S = c.i_msg
    sent = S["sent"].count(u, tt, W30)
    dlv, opn, clk = S["delivered"].count(u, tt, W30), S["opened"].count(u, tt, W30), S["clicked"].count(u, tt, W30)
    f["msg__ev_sent__30d"], f["msg__delivered__30d"], f["msg__opened__30d"], f["msg__clicked__30d"] = sent, dlv, opn, clk
    f["msg__bounced__30d"] = S["bounced"].count(u, tt, W30) + S["failed"].count(u, tt, W30)
    f["msg__unsubscribed_ever"] = (S["unsubscribed"].count(u, tt) > 0).astype("float64")
    with np.errstate(invalid="ignore", divide="ignore"):
        f["msg__delivered_rate__30d"] = np.where(sent > 0, dlv / sent, np.nan)
        f["msg__open_rate__30d"] = np.where(dlv > 0, opn / dlv, np.nan)
        f["msg__click_rate__30d"] = np.where(dlv > 0, clk / dlv, np.nan)
    return f


def block_consent(c: Ctx, sp: dict) -> dict:
    u, t = sp["u"], sp["t"]
    f = {}
    for chn in ["email", "sms", "whatsapp"]:
        if not c.has_events:
            f[f"consent__{chn}"] = np.full(len(u), None, dtype=object)
            f[f"consent__{chn}_days_since_change"] = np.full(len(u), np.nan)
            f[f"consent__{chn}_ever_withdrawn"] = np.full(len(u), np.nan)
            continue
        I = c.i_consent[chn]
        pos = I.last(u, t)
        f[f"consent__{chn}"] = I.get("status", pos, fill="none")            # no record = none = treated as hold
        f[f"consent__{chn}_days_since_change"] = days(t, I.time_at(pos))
        f[f"consent__{chn}_ever_withdrawn"] = (I.total("wd", u, t) > 0).astype("float64")
    return f


def block_web(c: Ctx, sp: dict) -> dict:
    u, t = sp["u"], sp["t"]
    names = ["web__page_views__7d", "web__page_views__30d", "web__page_views__90d", "web__sessions__7d", "web__sessions__30d",
             "web__sessions__90d", "web__active_days__30d", "web__pages_per_session__30d", "web__days_since_last_visit",
             "web__trend", "web__emi_calc_views__30d", "web__has_history"]
    if not c.has_events:
        return {n: np.full(len(u), np.nan) for n in names}
    f = {}
    for w, lab in [(W7, "7d"), (W30, "30d"), (W90, "90d")]:
        f[f"web__page_views__{lab}"] = c.i_pv.count(u, t, w)
        f[f"web__sessions__{lab}"] = c.i_sess.count(u, t, w)
    f["web__active_days__30d"] = c.i_pvday.count(u, t, W30)
    with np.errstate(invalid="ignore", divide="ignore"):
        f["web__pages_per_session__30d"] = np.where(f["web__sessions__30d"] > 0, f["web__page_views__30d"] / f["web__sessions__30d"], np.nan)
        f["web__trend"] = np.where(f["web__page_views__30d"] > 0, f["web__page_views__7d"] / (f["web__page_views__30d"] / 4.0), np.nan)
    f["web__days_since_last_visit"] = days(t, c.i_pv.time_at(c.i_pv.last(u, t)))
    f["web__emi_calc_views__30d"] = c.i_pv.total("emi", u, t, W30)
    f["web__has_history"] = (c.i_pv.count(u, t) > 0).astype("float64")
    return f


def block_portfolio(c: Ctx, sp: dict) -> dict:
    u, t = sp["u"], sp["t"]
    opened = c.i_loan_open.count(u, t)
    closed = c.i_loan_close.count(u, t)
    return {"loans_opened_by_t": opened, "loans_active_at_t": opened - closed}


FUNNEL_BLOCKS = [block_profile, block_time, block_state, block_funnel, block_service, block_actions, block_messaging,
                 block_consent, block_web, block_portfolio]


def build_block_features(c: Ctx, spine: pd.DataFrame, blocks=FUNNEL_BLOCKS) -> pd.DataFrame:
    """spine needs columns unit_id and t (UTC datetime)."""
    sp = {"unit_id": spine["unit_id"], "u": c.u(spine["unit_id"]), "t": ms(spine["t"])}
    out = {}
    for blk in blocks:
        out.update(blk(c, sp))
    df = pd.DataFrame(out, index=spine.index)
    return downcast(df)


def downcast(df: pd.DataFrame) -> pd.DataFrame:
    for col in df.columns:
        if df[col].dtype == "float64":
            df[col] = df[col].astype("float32")
    return df


# --------------------------------------------------------------------------- labels / splits
def finalize(df: pd.DataFrame, t_col: str, window_days: float) -> pd.Series:
    return (df[t_col] + pd.Timedelta(days=window_days + BUFFER_DAYS)) <= EXTRACT


def assign_split(df: pd.DataFrame, t_col: str, final_col: str = "label_final", mode: str = "time") -> pd.Series:
    """Time-based split on prediction_time. Cut points come from the final rows only.
       mode='time'            : strict time order (default).
       mode='unit_first_time' : a unit goes to the split of its FIRST prediction_time (keeps a unit on one side)."""
    base = df.loc[df[final_col], t_col] if df[final_col].any() else df[t_col]
    c1, c2 = base.quantile(SPLIT_FRACTIONS[0]), base.quantile(SPLIT_FRACTIONS[0] + SPLIT_FRACTIONS[1])
    key = df[t_col]
    if mode == "unit_first_time":
        key = df.groupby("unit_id")[t_col].transform("min")
    return pd.Series(np.where(key <= c1, "train", np.where(key <= c2, "validation", "test")), index=df.index)


def std_columns(df: pd.DataFrame, t_col: str, window_days: float, split_mode: str = "time") -> pd.DataFrame:
    df["prediction_time"] = df[t_col]
    df["label_final"] = finalize(df, "prediction_time", window_days)
    df["split"] = assign_split(df, "prediction_time", mode=split_mode)
    return df


def any_in_window(c_idx: Idx, u, t, w):
    return c_idx.count(u, t + w, w) > 0          # rows in (t, t+w]


# --------------------------------------------------------------------------- M1
def build_m1_lead(c: Ctx, split_mode: str) -> pd.DataFrame:
    b = c.T["borrowers"]
    sp = pd.DataFrame({"unit_id": b["unit_id"].to_numpy(), "t": b["created_at"].to_numpy()})
    sp["t"] = pd.to_datetime(sp["t"], utc=True)
    X = build_block_features(c, sp)
    u, t = c.u(sp["unit_id"]), ms(sp["t"])
    out = pd.concat([sp.rename(columns={"t": "t0"}).reset_index(drop=True), X.reset_index(drop=True)], axis=1)
    out["regime_filter"] = out["regime_first_seen"]
    out["holdout_group"] = b["holdout_group"].to_numpy()
    out["y_disbursed_60d"] = (c.i_loan_open.count(u, t + 60 * DAY, 60 * DAY) > 0).astype("int8")
    out["y_apply_30d"] = (c.i_app.count(u, t + 30 * DAY, 30 * DAY) > 0).astype("int8")
    out = std_columns(out, "t0", 60, split_mode)
    out["label_final_apply_30d"] = finalize(out, "prediction_time", 30)
    return out.drop(columns=["t0"])


def build_m1_stall(c: Ctx, split_mode: str) -> pd.DataFrame:
    a = c.actions
    d = a[(a["record_kind"] == "decision") & (a["trigger"] == "stall")]
    sp = pd.DataFrame({"unit_id": d["unit_id"].to_numpy(), "t": d["decided_at"].to_numpy(), "action_id": d["action_id"].to_numpy()})
    sp["t"] = pd.to_datetime(sp["t"], utc=True)
    X = build_block_features(c, sp)
    u, t = c.u(sp["unit_id"]), ms(sp["t"])
    out = pd.concat([sp.rename(columns={"t": "t0"}).reset_index(drop=True), X.reset_index(drop=True)], axis=1)
    # steps started (any step of the person) in the 7 days after the stall decision
    out["y_resume_7d"] = (c.i_step_any.count(u, t + 7 * DAY, 7 * DAY) > 0).astype("int8")
    out["y_disbursed_60d"] = (c.i_loan_open.count(u, t + 60 * DAY, 60 * DAY) > 0).astype("int8")
    out["holdout_group"] = d["holdout_group"].to_numpy()
    out = std_columns(out, "t0", 7, split_mode)
    out["label_final_disbursed_60d"] = finalize(out, "prediction_time", 60)
    return out.drop(columns=["t0"])


# --------------------------------------------------------------------------- M2
def loan_features(c: Ctx, inst: pd.DataFrame, t_ms: np.ndarray) -> dict:
    """Instalment-level features. `inst` rows need loan_id, code (loan), instalment_no, due_ms."""
    code = inst["code"].to_numpy("int64")
    I = c.i_inst
    cnt = I.count(code, t_ms)
    fails = I.total("fail", code, t_ms)
    with np.errstate(invalid="ignore", divide="ignore"):
        rate = np.where(cnt > 0, fails / cnt, np.nan)
        ncap = c.i_cap.total("one", code, t_ms)
        dtc = np.where(ncap > 0, c.i_cap.total("dtc", code, t_ms) / ncap, np.nan)
        manual = np.where(cnt > 0, I.total("manual", code, t_ms) / cnt, np.nan)
    pos = I.last(code, t_ms)
    # most recent run of failed first attempts: walk back over the previous results
    run = np.zeros(len(code))
    alive = np.ones(len(code), dtype=bool)
    for k in range(0, 12):
        p = I.last(code, t_ms, back=k)
        ok = alive & (p >= 0)
        isf = np.zeros(len(code), dtype=bool)
        isf[ok] = I.vals["fail"][p[ok]] > 0
        alive = ok & isf
        run += alive
        if not alive.any():
            break
    # last failure reason: latest failed first attempt
    failpos = np.full(len(code), -1)
    f_idx = np.where(I.vals["fail"] > 0)[0]
    if len(f_idx):
        sub = Idx(I.u[f_idx], I.t[f_idx], err=I.vals["err"][f_idx], failt=I.vals["failt"][f_idx])
        fp = sub.last(code, t_ms)
        last_err = sub.get("err", fp, fill="none")
        days_since_fail = days(t_ms, sub.time_at(fp) - RESULT_LAG_DAYS * DAY)
    else:
        last_err, days_since_fail = np.full(len(code), "none", dtype=object), np.full(len(code), np.nan)
    return {
        "prior_instalments": cnt, "has_repayment_history": (cnt > 0).astype("float64"),
        "prior_first_attempt_fails": fails, "prior_first_attempt_fail_rate": rate, "consecutive_fails": run,
        "avg_days_to_capture_prior": dtc, "last_error_category": last_err, "prior_manual_share": manual,
        "days_since_last_first_attempt_fail": days_since_fail,
    }


def build_m2(c: Ctx, split_mode: str) -> pd.DataFrame:
    inst = c.inst.copy()
    inst["t"] = from_ms(inst["due_ms"].to_numpy() - 3 * DAY).to_numpy()
    t_ms = inst["due_ms"].to_numpy() - 3 * DAY
    inst["t"] = pd.to_datetime(inst["t"], utc=True)
    loans = c.loans.reindex(inst["loan_id"])
    sp = pd.DataFrame({"unit_id": inst["unit_id"].to_numpy(), "t": inst["t"].to_numpy()})
    sp["t"] = pd.to_datetime(sp["t"], utc=True)
    blocks = [block_profile, block_time, block_state, block_service, block_portfolio]
    X = build_block_features(c, sp, blocks).reset_index(drop=True)
    uu, tt = c.u(sp["unit_id"]), t_ms
    # funnel facts that still apply once the loan exists: e-sign / mandate as of t, applications, risk band at origination
    F = block_funnel(c, {"unit_id": sp["unit_id"], "u": uu, "t": tt})
    keep = ["apps_started_by_t", "app_kind", "esign_started", "esign_declined", "mandate_attempts", "mandate_failed"]
    for k in keep:
        X[k] = F[k] if not isinstance(F[k], np.ndarray) or F[k].dtype == object else F[k].astype("float32")
    app = c.apps.reindex(loans["application_ref"].to_numpy())
    X["lender_band_at_origination"] = app["risk_ord"].to_numpy("float32")        # applications.risk_band, NOT lender_band_latest
    X["instalment_no"] = inst["instalment_no"].to_numpy("float32")
    X["loan_age_days"] = days(t_ms, loans["open_ms"].to_numpy()).astype("float32")
    X["tenure_band"] = loans["tenure_ord"].to_numpy("float32")
    X["disbursed_amount_band"] = loans["disb_ord"].to_numpy("float32")
    X["emi_amount_band"] = ordinal(inst["amount_band"], BANDS_AMOUNT).astype("float32")
    X["due_weekday"] = pd.to_datetime(inst["due_date"], utc=True).dt.tz_convert(LOCAL_TZ).dt.weekday.to_numpy("float32")
    X["due_day_of_month"] = pd.to_datetime(inst["due_date"], utc=True).dt.tz_convert(LOCAL_TZ).dt.day.to_numpy("float32")
    for k, v in loan_features(c, inst, t_ms).items():
        X[k] = v if getattr(v, "dtype", None) == object else np.asarray(v, dtype="float32")
    # mandate as of t: method and latest status from the application's mandate steps
    Mi = c.i_mand_done
    mpos = Mi.last(uu, tt)
    X["mandate_method"] = Mi.get("method", mpos, fill="none")
    X["mandate_status_at_t"] = Mi.get("status", mpos, fill="none")
    # pre-debit regulatory notice in the 7 days before t
    P = c.i_predebit
    X["predebit_notice_sent_7d"] = P.count(uu, tt - 1, W7).astype("float32")
    if c.has_events:
        dl = c.i_msg_mid["delivered"]
        n = np.zeros(len(uu))
        lo = P._hi(uu, np.maximum(tt - 1 - W7, 0))
        hi = P._hi(uu, tt - 1)
        for i in np.where(hi > lo)[0]:
            mids = P.vals["mid"][lo[i]:hi[i]]
            ing = dl.reindex(mids).to_numpy()
            n[i] = np.sum(ing <= tt[i])
        X["predebit_notice_delivered_7d"] = (n > 0).astype("float32")
    else:
        X["predebit_notice_delivered_7d"] = np.nan
    out = pd.concat([inst[["loan_id", "unit_id"]].reset_index(drop=True), X], axis=1)
    out["y_first_attempt_fail"] = inst["fail"].to_numpy("int8")
    out["t0"] = inst["t"].to_numpy()
    out["due_date"] = inst["due_date"].to_numpy()
    out["holdout_group"] = c.borrowers["holdout_group"].reindex(out["unit_id"]).to_numpy()
    # label final: first attempts due 30+ days before the extract (the attempt row exists and its result is settled)
    out["prediction_time"] = pd.to_datetime(out["t0"], utc=True)
    out["label_final"] = (pd.to_datetime(out["due_date"], utc=True) + pd.Timedelta(days=30)) <= EXTRACT
    out["split"] = assign_split(out, "prediction_time", mode=split_mode)
    return out.drop(columns=["t0", "due_date"])


def build_m2_default12m(c: Ctx) -> pd.DataFrame:
    """One row per loan at disbursal. Secondary label to CHECK that the lender band is calibrated; not a credit model."""
    l = c.loans.copy()
    app = c.apps.reindex(l["application_ref"].to_numpy())
    df = pd.DataFrame({
        "loan_id": l["loan_id"].to_numpy(), "unit_id": l["unit_id"].to_numpy(),
        "prediction_time": pd.to_datetime(l["opened_at"], utc=True).to_numpy(),
        "lender_band_at_origination": app["risk_ord"].to_numpy("float32"),
        "tenure_band": l["tenure_ord"].to_numpy("float32"), "disbursed_amount_band": l["disb_ord"].to_numpy("float32"),
        "requested_amount_band": app["req_ord"].to_numpy("float32"),
    })
    d = pd.to_datetime(l["defaulted_at"], utc=True)
    df["y_default_12m"] = ((d.notna()) & (d <= pd.to_datetime(l["opened_at"], utc=True) + pd.Timedelta(days=365))).to_numpy("int8")
    df["label_final"] = (df["prediction_time"] + pd.DateOffset(months=15)) <= EXTRACT      # loans 15+ months old
    return df


# --------------------------------------------------------------------------- M3
def parse_blocked(s: pd.Series) -> pd.DataFrame:
    """allowed_<action> flags. A block for reason 'in_holdout' is ignored: it is the treatment assignment, not eligibility."""
    out = {f"allowed_{a}": np.ones(len(s)) for a in OPTIONAL_ACTIONS}
    sv = s.fillna("[]").to_numpy()
    reasons = {}
    for i, v in enumerate(sv):
        if v == "[]":
            continue
        for item in json.loads(v):
            if item.get("reason_code") == "in_holdout":
                continue
            a = item.get("action")
            if f"allowed_{a}" in out:
                out[f"allowed_{a}"][i] = 0.0
            reasons.setdefault(item.get("reason_code"), np.zeros(len(s)))[i] = 1.0
    for k, v in reasons.items():
        out[f"blocked_reason_{k}"] = v
    return pd.DataFrame(out, index=s.index)


def build_m3(c: Ctx, split_mode: str) -> pd.DataFrame:
    a = c.actions
    d = a[(a["record_kind"] == "decision") & (a["regime"] == "randomised_holdout")].copy().reset_index(drop=True)
    sp = pd.DataFrame({"unit_id": d["unit_id"], "t": pd.to_datetime(d["decided_at"], utc=True)})
    X = build_block_features(c, sp).reset_index(drop=True)
    u, t = c.u(sp["unit_id"]), ms(sp["t"])
    # the action row itself says what the policy could choose (state at decision is recorded on the row)
    X["state_at_decision"] = d["state"].to_numpy()
    X["trigger"] = d["trigger"].to_numpy()
    X = pd.concat([X, parse_blocked(d["blocked_actions"]).reset_index(drop=True).astype("float32")], axis=1)
    # repayment features for emi_due decisions (loan of the decision's application, as of t)
    lid = d["application_ref"].map(c.loan_by_app)
    code = c.loans.reindex(lid.to_numpy())["code"].to_numpy(dtype="float64")
    has = ~np.isnan(code)
    tmp = pd.DataFrame({"code": np.where(has, code, 0).astype("int64")})
    rf = loan_features(c, tmp, t)
    for k in ["prior_first_attempt_fail_rate", "prior_first_attempt_fails", "consecutive_fails", "days_since_last_first_attempt_fail"]:
        v = np.asarray(rf[k], dtype="float32")
        v[~has] = np.nan
        X[f"emi__{k}"] = v
    out = pd.concat([d[["action_id", "unit_id"]], X], axis=1)
    out["prediction_time"] = sp["t"].to_numpy()
    # ---- treatment columns (propensity is a weight / stratum, never a feature)
    ch = d["chosen_action"]
    out["w_any"] = (ch != "do_nothing").astype("int8").to_numpy()
    out["w_action"] = ch.to_numpy()
    out["propensity"] = d["propensity"].to_numpy("float32")
    out["in_holdout"] = d["in_holdout"].astype(bool).to_numpy()
    out["holdout_group"] = d["holdout_group"].to_numpy()
    forced = (ch == "do_nothing") & (d["propensity"] == 1.0) & (~d["in_holdout"].astype(bool))
    out["is_forced_do_nothing"] = forced.to_numpy()                      # every other action was blocked; not comparable
    out["is_valid_control"] = ((ch == "do_nothing") & ~forced).to_numpy()  # holdout rows + policy-chosen do_nothing
    out["keep_for_uplift"] = (~forced).to_numpy()
    out["ipw"] = np.where(out["in_holdout"], np.nan, np.clip(1.0 / out["propensity"], 1.0, 10.0)).astype("float32")
    # ---- outcomes per trigger
    n = len(out)
    nan = lambda: np.full(n, np.nan)
    y = {k: nan() for k in ["y_disbursed_60d", "y_apply_30d", "y_resume_7d", "y_paid_first_attempt", "y_topup_60d", "y_winback_60d"]}
    trig = d["trigger"].to_numpy()
    disb = c.i_loan_open.count(u, t + 60 * DAY, 60 * DAY) > 0
    y["y_disbursed_60d"] = np.where(np.isin(trig, ["lead", "stall"]), disb, np.nan)
    y["y_apply_30d"] = np.where(trig == "lead", c.i_app.count(u, t + 30 * DAY, 30 * DAY) > 0, np.nan)
    y["y_resume_7d"] = np.where(trig == "stall", c.i_step_any.count(u, t + 7 * DAY, 7 * DAY) > 0, np.nan)
    for kind, col, code_k in [("top_up", "y_topup_60d", "topup"), ("win_back", "y_winback_60d", "winback")]:
        ap = c.apps[(c.apps["application_kind"] == kind)]
        ld = c.loans[c.loans["application_ref"].isin(ap["application_ref"])]
        ix = Idx(ld["u"], ld["open_ms"])
        y[col] = np.where(trig == code_k, ix.count(u, t + 60 * DAY, 60 * DAY) > 0, np.nan)
    # emi_due: first instalment of the loan due after t, within 10 days, captured on attempt 1
    inst = c.inst
    ix_due = Idx(inst["code"], inst["due_ms"], pay=(inst["status"] == "captured").to_numpy("float64"), due=inst["due_ms"].to_numpy())
    cc = np.where(has, code, -1).astype("int64")
    nx = ix_due.next_after(cc, t)
    due_next = ix_due.get("due", nx)
    pay = ix_due.get("pay", nx)
    near = (~np.isnan(due_next)) & ((due_next - t) <= 10 * DAY) & (trig == "emi_due")
    y["y_paid_first_attempt"] = np.where(near, pay, np.nan)
    y_due_ms = np.where(near, due_next, np.nan)
    for k, v in y.items():
        out[k] = pd.array(np.where(np.isnan(v.astype("float64")), np.nan, v), dtype="Float32").astype("float32") if False else v.astype("float32")
    # finality per outcome: window + 45 days before the extract
    win = {"y_disbursed_60d": 60, "y_apply_30d": 30, "y_resume_7d": 7, "y_topup_60d": 60, "y_winback_60d": 60}
    for k, w in win.items():
        out[f"final_{k}"] = finalize(out, "prediction_time", w).to_numpy()
    out["final_y_paid_first_attempt"] = ((pd.to_datetime(from_ms(np.nan_to_num(y_due_ms).astype("int64")), utc=True) + pd.Timedelta(days=30)) <= EXTRACT).to_numpy() & near
    # primary label_final: the outcome that applies to the row's trigger
    prim = {"lead": "y_disbursed_60d", "stall": "y_disbursed_60d", "topup": "y_topup_60d", "winback": "y_winback_60d",
            "emi_due": "y_paid_first_attempt", "service": None}
    lf = np.zeros(n, dtype=bool)
    for tr, col in prim.items():
        if col:
            lf |= (trig == tr) & out[f"final_{col}"].to_numpy()
    out["label_final"] = lf
    out["split"] = assign_split(out, "prediction_time", mode=split_mode)
    return out


# --------------------------------------------------------------------------- M4
OUTCOME_ORDER = ["disbursed", "rejected", "drop_kyc", "drop_signing"]      # tie-break order


def build_m4_funnel(c: Ctx, split_mode: str, out_path: str, horizon_days: int = 60) -> int:
    rng = np.random.default_rng(RANDOM_SEED)
    b = c.T["borrowers"]
    u_all = c.u(b["unit_id"])
    created = ms(b["created_at"])
    H = horizon_days * DAY
    WEEK = 7 * DAY
    first_state_nonlead = c.state_df[c.state_df["state"] != "Lead"].groupby("u").size()
    progress = np.zeros(len(b), dtype=bool)
    progress[b["first_application_at"].notna().to_numpy()] = True          # population definition only, never a feature
    progress[first_state_nonlead.index.to_numpy()[first_state_nonlead.index.to_numpy() >= 0]] = True
    # terminal event of the funnel: first disbursal or first Rejected state
    rej = c.state_df[c.state_df["state"] == "Rejected"].groupby("u")["e"].min()
    dis = c.loans.groupby("u")["open_ms"].min()
    act = c.state_df[c.state_df["state"] == "Activated"].groupby("u")["e"].min()
    term = pd.Series(np.full(len(b), BIG), index=np.arange(len(b)))
    for ser in (rej, dis, act):
        ser = ser[ser.index >= 0]
        term.loc[ser.index] = np.minimum(term.loc[ser.index].to_numpy(), ser.to_numpy())
    term = term.to_numpy()
    # weekly grid: Mondays 00:00 UTC. First row = first Monday on or after lead creation.
    epoch_monday = 4 * DAY                                      # 1970-01-05 is a Monday
    first_w = ((created - epoch_monday + WEEK - 1) // WEEK) * WEEK + epoch_monday
    last_w = ms(pd.Series([EXTRACT]))[0]
    n_weeks = np.maximum(((np.minimum(term, last_w) - first_w + WEEK - 1) // WEEK), 0)
    n_weeks = np.where(first_w < np.minimum(term, last_w), n_weeks, 0)
    total = int(n_weeks.sum())
    print(f"  M4: {total:,} person-weeks before sampling")
    unit_rep = np.repeat(np.arange(len(b)), n_weeks)
    k = np.arange(total) - np.repeat(np.cumsum(n_weeks) - n_weeks, n_weeks)
    wk = first_w[unit_rep] + k * WEEK
    keep_p = progress[unit_rep]
    r = rng.random(total)
    keep = keep_p | (r < M4_LEAD_ONLY_SAMPLE)
    weight = np.where(keep_p, 1.0, 1.0 / M4_LEAD_ONLY_SAMPLE)
    unit_rep, wk, weight = unit_rep[keep], wk[keep], weight[keep]
    print(f"  M4: {len(wk):,} rows kept (all weeks for people with progress; {M4_LEAD_ONLY_SAMPLE:.0%} of Lead-only weeks, weighted)")
    # ---- outcome event indexes (confirmed outcomes only: loans table, state transitions, step results)
    s = c.steps
    sig = s[(s["step_type"].isin(["esign", "mandate"])) & (s["status"].isin(["declined", "expired", "voided", "failed", "rejected", "revoked"]))]
    ev_idx = {
        "disbursed": Idx(c.loans["u"], c.loans["open_ms"]),
        "rejected": Idx(c.state_df.loc[c.state_df["state"] == "Rejected", "u"], c.state_df.loc[c.state_df["state"] == "Rejected", "e"]),
        "drop_kyc": Idx(c.state_df.loc[c.state_df["state"] == "KYC drop-off", "u"], c.state_df.loc[c.state_df["state"] == "KYC drop-off", "e"]),
        "drop_signing": Idx(sig["u"], sig["ct"]),
    }
    import pyarrow as pa
    import pyarrow.parquet as pq
    writer = None
    written = 0
    for s0 in range(0, len(wk), M4_CHUNK):
        sl = slice(s0, s0 + M4_CHUNK)
        uu, tt, ww = unit_rep[sl], wk[sl], weight[sl]
        sp = pd.DataFrame({"unit_id": b["unit_id"].to_numpy()[uu], "t": from_ms(tt).to_numpy()})
        sp["t"] = pd.to_datetime(sp["t"], utc=True)
        X = build_block_features(c, sp).reset_index(drop=True)
        X.insert(0, "unit_id", sp["unit_id"].to_numpy())
        X.insert(1, "week_start", sp["t"].to_numpy())
        X["prediction_time"] = sp["t"].to_numpy()
        X["sample_weight"] = ww.astype("float32")
        # first outcome inside the horizon
        best_t = np.full(len(uu), np.inf)
        best_k = np.full(len(uu), "stay", dtype=object)
        for name in OUTCOME_ORDER:
            I = ev_idx[name]
            pos = I.next_after(uu, tt)
            tn = I.time_at(pos)
            ok = (~np.isnan(tn)) & (tn <= tt + H)
            better = ok & (tn < best_t)
            best_t = np.where(better, tn, best_t)
            best_k = np.where(better, name, best_k)
        X["y4_outcome"] = best_k
        X["label_final"] = ((X["prediction_time"] + pd.Timedelta(days=horizon_days + BUFFER_DAYS)) <= EXTRACT).to_numpy()
        X["holdout_group"] = b["holdout_group"].to_numpy()[uu]
        X["split"] = assign_split(X, "prediction_time", mode="time")
        tbl = pa.Table.from_pandas(X, preserve_index=False)
        if writer is None:
            writer = pq.ParquetWriter(out_path, tbl.schema)
            schema = tbl.schema
        else:
            tbl = tbl.cast(schema, safe=False)
        writer.write_table(tbl)
        written += len(X)
        print(f"    M4 rows written: {written:,}")
    if writer:
        writer.close()
    return written


# --------------------------------------------------------------------------- feature dictionary
# --------------------------------------------------------------------------- M4, loan servicing (borrowers with a loan)
SERV_HORIZON = 90
SERV_OUTCOMES = ["defaulted", "prepaid_closed", "matured", "new_loan", "dormant"]     # tie-break order
SERV_CHUNK = 200_000


def borrower_indexes(c: Ctx) -> dict:
    """Repayment history keyed by borrower (the existing indexes are keyed by loan)."""
    a = c.inst.copy()
    a["u"] = c.u(a["unit_id"])
    a["t"] = a["cr_ms"] + RESULT_LAG_DAYS * DAY                  # result reaches the warehouse 1-2 days late
    cap = a[a["cap_ms"].notna()]
    L = c.loans
    first_open = L.groupby("u")["open_ms"].transform("min")
    later = L[L["open_ms"] > first_open]                         # a loan opened after the borrower's first loan
    cl = L[L["closed_at"].notna()]
    ct = cl["closure_type"].fillna("")
    d = L[L["defaulted_at"].notna()]
    sd = c.state_df
    dor = sd[sd["state"] == "Dormant"]
    return {
        "inst": Idx(a["u"], a["t"], fail=a["fail"].to_numpy(), manual=a["manual"].to_numpy(), one=np.ones(len(a))),
        "cap": Idx(cap["u"] if "u" in cap else c.u(cap["unit_id"]), cap["cap_ms"].to_numpy("int64") + RESULT_LAG_DAYS * DAY,
                   dtc=cap["days_to_capture"].to_numpy()),
        "defaulted": Idx(d["u"], ms(d["defaulted_at"])),
        "prepaid": Idx(cl.loc[ct.isin(["prepaid", "foreclosed"]), "u"], cl.loc[ct.isin(["prepaid", "foreclosed"]), "close_ms"]),
        "matured": Idx(cl.loc[ct == "matured", "u"], cl.loc[ct == "matured", "close_ms"]),
        "new_loan": Idx(later["u"], later["open_ms"]),
        "dormant": Idx(dor["u"], dor["e"]),
    }


def block_repayment(c: Ctx, sp: dict, bi: dict) -> dict:
    u, t = sp["u"], sp["t"]
    I = bi["inst"]
    n, f = I.count(u, t), I.total("fail", u, t)
    n90, f90 = I.count(u, t, W90), I.total("fail", u, t, W90)
    n30, f30 = I.count(u, t, W30), I.total("fail", u, t, W30)
    ncap = bi["cap"].count(u, t)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = {"emi__instalments_seen": n, "emi__has_history": (n > 0).astype("float64"), "emi__fails_total": f,
               "emi__fail_rate": np.where(n > 0, f / n, np.nan), "emi__fail_rate_90d": np.where(n90 > 0, f90 / n90, np.nan),
               "emi__fail_rate_30d": np.where(n30 > 0, f30 / n30, np.nan),
               "emi__manual_share": np.where(n > 0, I.total("manual", u, t) / n, np.nan),
               "emi__avg_days_to_capture": np.where(ncap > 0, bi["cap"].total("dtc", u, t) / np.maximum(ncap, 1), np.nan)}
    # most recent failed first attempt
    fi = np.where(I.vals["fail"] > 0)[0]
    if len(fi):
        sub = Idx(I.u[fi], I.t[fi])
        out["emi__days_since_last_fail"] = days(t, sub.time_at(sub.last(u, t)) - RESULT_LAG_DAYS * DAY)
    else:
        out["emi__days_since_last_fail"] = np.full(len(u), np.nan)
    return out


def block_loans(c: Ctx, sp: dict) -> dict:
    """Facts about the loans the borrower has opened by t. Closed / defaulted flags come from timestamps <= t only."""
    u, t = sp["u"], sp["t"]
    L = c.loans
    opens = Idx(L["u"], L["open_ms"], ten=L["tenure_ord"].to_numpy("float64"), amt=L["disb_ord"].to_numpy("float64"),
                lender=L["lender_band_latest"].fillna("none").to_numpy(dtype=object), one=np.ones(len(L)))
    pos = opens.last(u, t)
    n_open = opens.count(u, t)
    first_t = np.where(n_open > 0, opens.t[np.clip(opens._lo(u), 0, len(opens.t) - 1)], np.nan)
    d = Idx(L["u"], ms(L["defaulted_at"]))
    return {"loan__latest_age_days": days(t, opens.time_at(pos)), "loan__first_age_days": days(t, first_t),
            "loan__latest_tenure_band": opens.get("ten", pos), "loan__latest_amount_band": opens.get("amt", pos),
            "loan__latest_lender_band": opens.get("lender", pos, fill="none"),
            "loan__ever_defaulted": (d.count(u, t) > 0).astype("float64"),
            "loan__loans_total_amount_bands": opens.total("amt", u, t)}


def build_m4_servicing(c: Ctx, split_mode: str, out_path: str) -> pd.DataFrame:
    b = c.T["borrowers"]
    n = len(b)
    L = c.loans
    WEEK = 7 * DAY
    H = SERV_HORIZON * DAY
    end_ms = ms(pd.Series([EXTRACT]))[0]
    first_open = np.full(n, BIG, dtype="int64")
    fo = L.groupby("u")["open_ms"].min()
    first_open[fo.index[fo.index >= 0].to_numpy()] = fo[fo.index >= 0].to_numpy()
    first_def = np.full(n, BIG, dtype="int64")
    dd = L[L["defaulted_at"].notna()].groupby("u").apply(lambda g: ms(g["defaulted_at"]).min(), include_groups=False)
    first_def[dd.index[dd.index >= 0].to_numpy()] = dd[dd.index >= 0].to_numpy()
    g = L.groupby("u")
    all_closed = (g["close_ms"].max() < BIG - 1)                  # every loan has a closing date
    all_close_t = np.full(n, BIG, dtype="int64")
    ac = g["close_ms"].max()[all_closed]
    all_close_t[ac.index[ac.index >= 0].to_numpy()] = ac[ac.index >= 0].to_numpy()
    stop = np.minimum(np.minimum(first_def, all_close_t), end_ms)
    epoch_monday = 4 * DAY
    first_w = np.where(first_open < BIG, ((first_open - epoch_monday + WEEK - 1) // WEEK) * WEEK + epoch_monday, BIG)
    nw = np.where(first_w < stop, (stop - first_w + WEEK - 1) // WEEK, 0)
    total = int(nw.sum())
    print(f"  servicing M4: {total:,} borrower-weeks for {int((nw > 0).sum()):,} borrowers")
    uu_all = np.repeat(np.arange(n), nw)
    k = np.arange(total) - np.repeat(np.cumsum(nw) - nw, nw)
    wk_all = first_w[uu_all] + k * WEEK
    bi = borrower_indexes(c)
    ev = {"defaulted": bi["defaulted"], "prepaid_closed": bi["prepaid"], "matured": bi["matured"],
          "new_loan": bi["new_loan"], "dormant": bi["dormant"]}
    blocks = FUNNEL_BLOCKS + [block_loans]
    parts = []
    for s0 in range(0, total, SERV_CHUNK):
        uu, tt = uu_all[s0:s0 + SERV_CHUNK], wk_all[s0:s0 + SERV_CHUNK]
        sp = pd.DataFrame({"unit_id": b["unit_id"].to_numpy()[uu], "t": from_ms(tt).to_numpy()})
        sp["t"] = pd.to_datetime(sp["t"], utc=True)
        X = build_block_features(c, sp, blocks).reset_index(drop=True)
        spd = {"unit_id": sp["unit_id"], "u": uu, "t": tt}
        R = pd.DataFrame(block_repayment(c, spd, bi))
        X = pd.concat([X, downcast(R)], axis=1)
        X.insert(0, "unit_id", sp["unit_id"].to_numpy())
        X.insert(1, "week_start", sp["t"].to_numpy())
        X["prediction_time"] = sp["t"].to_numpy()
        best_t = np.full(len(uu), np.inf)
        best_k = np.full(len(uu), "stay", dtype=object)
        for name in SERV_OUTCOMES:
            I = ev[name]
            tn = I.time_at(I.next_after(uu, tt))
            ok = (~np.isnan(tn)) & (tn <= tt + H)
            better = ok & (tn < best_t)
            best_t, best_k = np.where(better, tn, best_t), np.where(better, name, best_k)
        X["y4_outcome"] = best_k
        X["holdout_group"] = b["holdout_group"].to_numpy()[uu]
        parts.append(X)
        print(f"    rows built: {s0 + len(uu):,}")
    out = pd.concat(parts, ignore_index=True)
    out["label_final"] = ((out["prediction_time"] + pd.Timedelta(days=SERV_HORIZON + BUFFER_DAYS)) <= EXTRACT).to_numpy()
    out["split"] = assign_split(out, "prediction_time", mode=split_mode)
    out.to_parquet(out_path, index=False)
    return out


def servicing_summary(m4: pd.DataFrame, reps: int = 200) -> pd.DataFrame:
    rng = np.random.default_rng(RANDOM_SEED)
    d = m4[m4["label_final"]]
    rows = []
    for dim in ["state__current", "loan__latest_tenure_band"]:
        for val, h in d.groupby(dim, observed=True):
            codes, outs = pd.factorize(h["y4_outcome"])
            uc, ui = np.unique(h["unit_id"].to_numpy(), return_inverse=True)
            A = np.zeros((len(uc), len(outs) + 1))
            np.add.at(A, (ui, np.full(len(ui), len(outs))), 1.0)
            np.add.at(A, (ui, codes), 1.0)
            tot = A.sum(0)
            bs = rng.multinomial(len(uc), np.full(len(uc), 1.0 / len(uc)), size=reps).astype("float64") @ A if len(uc) >= 30 else None
            for j, oc in enumerate(outs):
                lo, hi = (np.nanpercentile(bs[:, j] / bs[:, -1], [2.5, 97.5]) if bs is not None else (np.nan, np.nan))
                rows.append({"cohort_dim": dim, "cohort": val, "outcome": oc, "share": tot[j] / tot[-1], "ci_low": lo, "ci_high": hi,
                             "n_rows": len(h), "n_borrowers": len(uc)})
    return pd.DataFrame(rows)




FAMILY_PREFIX = [("tenure__", "1 tenure"), ("acquisition_channel", "2 acquisition channel"), ("regime_first_seen", "3 regime"),
                 ("consent__", "4 consent"), ("web__", "5 web behaviour"), ("msg__", "6 messaging"), ("act__", "7 action history"),
                 ("state__", "8 lifecycle state"), ("support__", "9 support and service"), ("collections_open", "9 support and service"),
                 ("dispute_open", "9 support and service"), ("complaint_open", "9 support and service"),
                 ("prior_", "10 payment history"), ("consecutive_fails", "10 payment history"), ("avg_days_to_capture", "10 payment history"),
                 ("last_error", "10 payment history"), ("days_since_last_first", "10 payment history"), ("has_repayment", "10 payment history"),
                 ("emi__", "10 payment history"), ("loan__", "loan (servicing)"), ("apps_", "11 recency and frequency"), ("loans_", "11 recency and frequency"),
                 ("requested_amount_band", "12 amount band"), ("disbursed_amount_band", "12 amount band"), ("emi_amount_band", "12 amount band"),
                 ("time__", "13 time of prediction"), ("kyc_", "funnel (BFSI)"), ("aa_", "funnel (BFSI)"), ("esign_", "funnel (BFSI)"),
                 ("mandate_", "funnel (BFSI)"), ("risk_band", "funnel (BFSI)"), ("hours_since", "funnel (BFSI)"), ("allowed_", "M3 eligibility"),
                 ("blocked_reason_", "M3 eligibility"), ("lender_band", "loan (M2)"), ("instalment_no", "loan (M2)"), ("loan_age", "loan (M2)"),
                 ("tenure_band", "loan (M2)"), ("due_", "loan (M2)"), ("predebit", "notice (M2)")]
LABEL_PREFIX = ("y_", "y4_", "final_")


def feature_dictionary(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    meta = {"unit_id", "loan_id", "action_id", "prediction_time", "week_start", "split", "label_final", "sample_weight", "holdout_group",
            "w_any", "w_action", "propensity", "in_holdout", "is_forced_do_nothing", "is_valid_control", "keep_for_uplift", "ipw", "regime_filter"}
    rows = []
    for name, df in tables.items():
        for col in df.columns:
            if col in meta or col.startswith("label_final"):
                role = "meta / treatment"
            elif col.startswith(LABEL_PREFIX):
                role = "label"
            else:
                role = "feature"
            fam = next((f for p, f in FAMILY_PREFIX if col.startswith(p)), "other")
            rows.append({"table": name, "column": col, "role": role, "family": fam if role == "feature" else "", "dtype": str(df[col].dtype)})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", required=True, help="folder with the VISIBLE BFSI parquet files (out_bfsi/visible)")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--only", nargs="*", choices=["m1", "m2", "m3", "m4"], default=["m1", "m2", "m3", "m4"])
    ap.add_argument("--no-events", action="store_true", help="skip events.parquet (consent / web / message-status features become NaN)")
    ap.add_argument("--split-mode", choices=["time", "unit_first_time"], default="time")
    a = ap.parse_args(argv)
    os.makedirs(a.out_dir, exist_ok=True)
    t0 = time.time()
    print("loading tables ...")
    tables, ev = load_tables(a.data_dir, use_events=not a.no_events)
    if ev is None:
        print("  events.parquet not used: consent / web / message-status features will be NaN")
    else:
        ev = prep_events(ev)
    print("building indexes ...")
    c = Ctx(tables, ev)
    del ev
    dicts = {}

    def save(name, df):
        df.to_parquet(os.path.join(a.out_dir, f"{name}.parquet"), index=False)
        dicts[name] = df.head(1)
        lab = [x for x in df.columns if x.startswith("y_") and x != "y4_outcome"]
        info = ", ".join(f"{x}={df.loc[df['label_final'], x].mean():.4f}" for x in lab[:3]) if "label_final" in df else ""
        print(f"  {name}: {len(df):,} rows, {df['label_final'].sum():,} final; {info}")

    if "m1" in a.only:
        print("M1 ..."); save("bfsi_m1_lead", build_m1_lead(c, a.split_mode)); save("bfsi_m1_stall", build_m1_stall(c, a.split_mode))
    if "m2" in a.only:
        print("M2 ..."); save("bfsi_m2", build_m2(c, a.split_mode)); save("bfsi_m2_default12m", build_m2_default12m(c))
    if "m3" in a.only:
        print("M3 ..."); save("bfsi_m3", build_m3(c, a.split_mode))
    if "m4" in a.only:
        print("M4 funnel ...")
        p = os.path.join(a.out_dir, "bfsi_m4_funnel.parquet")
        build_m4_funnel(c, a.split_mode, p)
        dicts["bfsi_m4_funnel"] = pd.read_parquet(p).head(1)
        print("M4 servicing ...")
        sv = build_m4_servicing(c, a.split_mode, os.path.join(a.out_dir, "bfsi_m4_servicing.parquet"))
        dicts["bfsi_m4_servicing"] = sv.head(1)
        fin = sv[sv["label_final"]]
        print(f"  bfsi_m4_servicing: {len(sv):,} rows, {len(fin):,} final")
        print(fin["y4_outcome"].value_counts(normalize=True).round(4).to_string())
        servicing_summary(sv).to_csv(os.path.join(a.out_dir, "bfsi_m4_servicing_summary.csv"), index=False)
    feature_dictionary(dicts).to_csv(os.path.join(a.out_dir, "bfsi_feature_dictionary.csv"), index=False)
    print(f"done in {time.time() - t0:.0f}s -> {a.out_dir}")


if __name__ == "__main__":
    main()
