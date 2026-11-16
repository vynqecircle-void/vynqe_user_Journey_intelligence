"""BFSI reference state engine. Reads EVENTS ONLY (never hidden truth). It runs on the visible, noisy events
and, in the generator, on the clean fully linked events to produce state_truth. Rules are proposals (rule_version)."""
from __future__ import annotations
import json
from collections import defaultdict
import numpy as np
import pandas as pd

from ...core.state_engine import to_sec, sessionize, _loads, DAY

OBJ = {"lead", "app", "kyc_check", "aa_fetch", "loan", "emi", "case"}


def run_bfsi_state_engine(ev: pd.DataFrame, borrowers: pd.DataFrame, p: dict, unit_col: str = "unit_id",
                          stitch: bool = True, end_sec: float | None = None) -> pd.DataFrame:
    ev = ev[[unit_col, "anonymous_id", "occurred_at", "event_type", "source_system", "source_event_id", "properties"]].copy()
    ev["t"] = to_sec(ev["occurred_at"])
    if end_sec is None:
        end_sec = float(ev["t"].max()) if len(ev) else 0.0
    if stitch:
        ident = ev[ev["event_type"] == "identify"]
        amap = {}
        for u, pr in zip(ident[unit_col], ident["properties"]):
            m = _loads(pr).get("merged")
            if m and isinstance(u, str):
                amap[m] = u
        need = ev[unit_col].isna() & ev["anonymous_id"].notna()
        if need.any() and amap:
            ev.loc[need, unit_col] = ev.loc[need, "anonymous_id"].map(amap)
    sigs = defaultdict(list)
    pv = ev[(ev["event_type"] == "page_view") & ev[unit_col].notna()][[unit_col, "t"]]
    if len(pv):
        vis = sessionize(pv, unit_col, p["timeout_min"])
        for u, t in zip(vis[unit_col], vis["start"]):
            sigs[u].append((t, "vis", None, None))
    rec = ev[ev["event_type"].isin(["record_created", "record_status_changed"]) & ev[unit_col].notna()
             & ev["source_event_id"].notna()]
    rec = rec[rec["source_event_id"].str.split(":", n=1).str[0].isin(OBJ)]
    rec = rec.sort_values("t", kind="mergesort").drop_duplicates([unit_col, "source_event_id"], keep="first")
    cases = defaultdict(list)
    cons = defaultdict(lambda: defaultdict(list))
    for u, t, seid, pr in zip(rec[unit_col], rec["t"], rec["source_event_id"], rec["properties"]):
        parts = seid.split(":")
        obj, st = parts[0], parts[-1]
        if obj == "emi":
            att = _loads(pr).get("attempt", 1)
            sigs[u].append((t, "emi", st, att))
        elif obj == "case":
            cases[u].append((t, st in ("open", "in_progress"), _loads(pr).get("case_category") or _loads(pr).get("category")))
        else:
            sigs[u].append((t, obj, st, None))
    cc = ev[(ev["event_type"] == "consent_change") & ev[unit_col].notna()]
    for u, t, pr in zip(cc[unit_col], cc["t"], cc["properties"]):
        d = _loads(pr)
        cons[u][d.get("channel")].append((t, d.get("status")))
    hold = {}
    if borrowers is not None and len(borrowers):
        hs = to_sec(borrowers["holdout_assigned_at"])
        hold = {u: (g, a) for u, g, a in zip(borrowers["unit_id"], borrowers["holdout_group"], hs)}

    def flags(u, t):
        coll = disp = False
        last = {}
        for tt, is_open, cat in sorted(cases.get(u, [])):
            if tt <= t:
                last[cat] = is_open
        coll, disp = last.get("collections", False), bool(last.get("dispute") or last.get("complaint"))
        granted = False
        for ch, lst in cons.get(u, {}).items():
            st_ = None
            for tt, st in sorted(lst):
                if tt <= t:
                    st_ = st
            granted = granted or st_ == "granted"
        h = hold.get(u)
        return json.dumps({"collections_open": bool(coll), "dispute_open": disp, "no_marketing_consent": not granted,
                           "in_holdout": bool(h and h[0] == "control" and t >= h[1])}, separators=(",", ":"))

    rows = []
    for u, lst in sigs.items():
        lst.sort(key=lambda x: x[0])
        for st, t0, t1, by in _unit_stays(lst, p, end_sec):
            rows.append((u, st, t0, t1, by, flags(u, t0)))
    out = pd.DataFrame(rows, columns=["unit_id", "state", "entered_s", "exited_s", "entered_by", "flags"])
    out["entered_at"] = pd.to_datetime(out["entered_s"], unit="s", utc=True)
    out["exited_at"] = pd.to_datetime(out["exited_s"], unit="s", utc=True)
    out["rule_version"] = p["rule_version"]
    return out.drop(columns=["entered_s", "exited_s"]).sort_values(["unit_id", "entered_at"]).reset_index(drop=True)


def _unit_stays(sigs, p, end_sec):
    stays, cur = [], [None, None, None]
    S = dict(last_act=None, kyc_pend=None, disb_t=None, fail_since=None, streak=0, closed_t=None)

    def set_state(st, t, by):
        if cur[0] == st:
            return
        if cur[0] is not None and t > cur[1]:
            stays.append((cur[0], cur[1], t, cur[2]))
        cur[0], cur[1], cur[2] = st, t, by

    def timer():
        st, c = cur[0], []
        if st == "Application started" and S["last_act"] is not None:
            c.append((S["last_act"] + p["application_stall_days"] * DAY, "Lead"))
            if S["kyc_pend"] is not None:
                c.append((S["kyc_pend"] + p["kyc_wait_days"] * DAY, "KYC drop-off"))
        if st == "Activated" and S["disb_t"] is not None:
            c.append((S["disb_t"] + p["first_cycle_days"] * DAY, "Repaying"))
        if st in ("Repaying", "Top-up eligible", "Activated") and S["fail_since"] is not None:
            c.append((S["fail_since"] + 5 * DAY, "Late"))
        if S["closed_t"] is not None and st in ("Repaying", "Top-up eligible", "Activated"):
            c.append((S["closed_t"] + p["dormant_days"] * DAY, "Dormant"))
        return min(c) if c else None

    for t, kind, a, b in sigs + [(end_sec, "end", None, None)]:
        while cur[0] is not None:
            tm = timer()
            if tm is None or tm[0] >= t:
                break
            set_state(tm[1], max(tm[0], cur[1]), "silence")
        if kind == "end":
            break
        if kind == "vis":
            S["last_act"] = t
        elif kind == "lead":
            if cur[0] is None:
                set_state("Lead", t, "event")
        elif kind == "app":
            S["last_act"] = t
            if a == "applied":
                S["kyc_pend"] = None
                set_state("Application started", t, "event")
            elif a == "docs_pending":
                if cur[0] in (None, "Lead", "Rejected", "Dormant", "Repaying", "Top-up eligible", "Late"):
                    set_state("Application started", t, "event")
            elif a == "in_review":
                set_state("In review", t, "event")
            elif a == "approved":
                set_state("Offer pending", t, "event")
            elif a in ("offer_accepted", "signed"):
                set_state("Signing and mandate pending", t, "event")
            elif a == "rejected":
                set_state("Rejected", t, "event")
            elif a == "disbursed":
                S.update(disb_t=t, closed_t=None, fail_since=None, streak=0)
                set_state("Activated", t, "event")
        elif kind == "kyc_check":
            S["last_act"] = t
            if a == "pending":
                S["kyc_pend"] = t
                if cur[0] in (None, "KYC drop-off", "Lead"):
                    set_state("Application started", t, "event")
            elif a == "verified":
                S["kyc_pend"] = None
                if cur[0] in (None, "Lead", "Application started", "KYC drop-off"):
                    set_state("Consent pending", t, "event")
            else:
                S["kyc_pend"] = None
                set_state("KYC drop-off", t, "event")
        elif kind == "aa_fetch":
            S["last_act"] = t
            if a == "completed" and cur[0] in ("Consent pending", "Application started", "KYC drop-off"):
                set_state("In review", t, "event")
        elif kind == "emi":
            if cur[0] == "Activated":
                set_state("Repaying", t, "event")
            if a == "captured":
                S["fail_since"] = None
                S["streak"] = S["streak"] + 1 if b == 1 else 0
                if cur[0] == "Late":
                    set_state("Repaying", t, "event")
                if S["streak"] >= p["topup_after_ontime"] and cur[0] == "Repaying":
                    set_state("Top-up eligible", t, "event")
            elif a == "failed":
                S["streak"] = 0
                if S["fail_since"] is None:
                    S["fail_since"] = t
        elif kind == "loan":
            if a == "defaulted":
                S["fail_since"] = None
                set_state("Late", t, "event")
            elif a == "closed":
                S["closed_t"] = t
            elif a == "active" and cur[0] in (None, "Lead", "Signing and mandate pending"):
                S.update(disb_t=t, closed_t=None)
                set_state("Activated", t, "event")
    if cur[0] is not None:
        stays.append((cur[0], cur[1], None, cur[2]))
    return stays
