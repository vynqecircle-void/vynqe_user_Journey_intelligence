"""Reference state engine (PDF F1). Reads EVENTS ONLY and produces one stay per state.
It never imports hidden truth. The same code runs on the visible (noisy) events and, in the generator,
on the clean events to produce state_truth."""
from __future__ import annotations
import json
from bisect import bisect_right
from collections import defaultdict
import numpy as np
import pandas as pd

EPOCH = pd.Timestamp("1970-01-01", tz="UTC")
DAY = 86400.0


def to_sec(s: pd.Series) -> np.ndarray:
    return ((pd.to_datetime(s, utc=True) - EPOCH).dt.total_seconds()).to_numpy()


def sessionize(pv: pd.DataFrame, key: str, timeout_min: float = 30.0) -> pd.DataFrame:
    """30-minute inactivity rule (GA4 default). pv needs [key, t] where t is epoch seconds. Returns session table."""
    pv = pv.sort_values([key, "t"], kind="mergesort")
    k = pv[key].to_numpy()
    t = pv["t"].to_numpy()
    new = np.ones(len(pv), dtype=bool)
    if len(pv) > 1:
        new[1:] = (k[1:] != k[:-1]) | ((t[1:] - t[:-1]) > timeout_min * 60.0)
    sid = np.cumsum(new)
    g = pd.DataFrame({key: k, "t": t, "sid": sid}).groupby("sid")
    out = g.agg(**{key: (key, "first"), "start": ("t", "min"), "end": ("t", "max"), "n_events": ("t", "size")})
    return out.reset_index()


def _loads(s):
    try:
        return json.loads(s)
    except Exception:
        return {}


def run_state_engine(ev: pd.DataFrame, customers: pd.DataFrame, p: dict, unit_col: str = "unit_id",
                     stitch: bool = True, end_sec: float | None = None) -> pd.DataFrame:
    """ev columns: unit_col, anonymous_id, occurred_at, event_type, source_system, properties."""
    ev = ev[[unit_col, "anonymous_id", "occurred_at", "event_type", "source_system", "properties"]].copy()
    ev["t"] = to_sec(ev["occurred_at"])
    if end_sec is None:
        end_sec = float(ev["t"].max()) if len(ev) else 0.0

    # --- stitch anonymous pre-login events through identify.merged
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

    # --- visits (sessionised page views)
    pv = ev[(ev["event_type"] == "page_view") & ev[unit_col].notna()][[unit_col, "t"]]
    visits = sessionize(pv, unit_col, p["timeout_min"]) if len(pv) else pd.DataFrame(columns=[unit_col, "start"])
    acts = defaultdict(list)
    for u, t in zip(visits[unit_col], visits["start"]):
        acts[u].append((t, "v"))

    # --- records
    rec = ev[ev["event_type"].isin(["record_created", "record_status_changed"]) & ev[unit_col].notna()]
    tickets = defaultdict(list)
    risk = defaultdict(list)
    for u, t, et, pr in zip(rec[unit_col], rec["t"], rec["event_type"], rec["properties"]):
        d = _loads(pr)
        obj = d.get("object")
        if obj == "order" and et == "record_created":
            acts[u].append((t, "o"))
        elif obj == "checkout" and d.get("to") == "abandoned":
            acts[u].append((t, "c"))
        elif obj == "ticket":
            st = d.get("status") if et == "record_created" else d.get("to")
            tickets[u].append((t, st in ("new", "open", "pending")))
        elif obj == "refund" or (obj == "shipment" and d.get("to") == "rto"):
            risk[u].append(t)
    cons = defaultdict(lambda: defaultdict(list))
    cc = ev[(ev["event_type"] == "consent_change") & ev[unit_col].notna()]
    for u, t, pr in zip(cc[unit_col], cc["t"], cc["properties"]):
        d = _loads(pr)
        if d.get("purpose", "marketing") == "marketing":
            cons[u][d.get("channel")].append((t, d.get("status")))

    hold = {}
    if customers is not None and len(customers):
        hs = to_sec(customers["holdout_assigned_at"])
        hold = {u: (g, a) for u, g, a in zip(customers["unit_id"], customers["holdout_group"], hs)}

    def flags(u, t):
        tk = sorted(tickets.get(u, []))
        open_t = False
        for tt, is_open in tk:
            if tt <= t:
                open_t = is_open
        r = sorted(risk.get(u, []))
        hi = (bisect_right(r, t) - bisect_right(r, t - 180 * DAY)) >= 2
        granted = False
        for ch, lst in cons.get(u, {}).items():
            last = None
            for tt, st in sorted(lst):
                if tt <= t:
                    last = st
            granted = granted or last == "granted"
        h = hold.get(u)
        return json.dumps({"open_support_ticket": open_t, "high_return_risk": bool(hi), "no_consent": not granted,
                           "in_holdout": bool(h and h[0] == "control" and t >= h[1])}, separators=(",", ":"))

    rows = []
    for u, lst in acts.items():
        lst.sort()
        stays = _unit_stays(lst, p, end_sec)
        for i, (st, t0, t1, by) in enumerate(stays):
            rows.append((u, st, t0, t1, by, flags(u, t0)))
    out = pd.DataFrame(rows, columns=["unit_id", "state", "entered_s", "exited_s", "entered_by", "flags"])
    out["entered_at"] = pd.to_datetime(out["entered_s"], unit="s", utc=True)
    out["exited_at"] = pd.to_datetime(out["exited_s"], unit="s", utc=True)
    out["rule_version"] = p["rule_version"]
    return out.drop(columns=["entered_s", "exited_s"]).sort_values(["unit_id", "entered_at"]).reset_index(drop=True)


def _unit_stays(acts, p, end_sec):
    stays = []
    cur = [None, None, None]
    orders = []
    last_order = None
    last_act = None
    nv = 0

    def set_state(st, t, by):
        nonlocal cur, nv
        if cur[0] == st:
            return
        if cur[0] is not None and t > cur[1]:
            stays.append((cur[0], cur[1], t, cur[2]))
        cur = [st, t, by]
        if st == "New visitor":
            nv = 0

    def usual():
        if len(orders) >= 2:
            d = np.median(np.diff(orders)) / DAY
            return float(min(120.0, max(7.0, d)))
        return float(p["default_usual_gap_days"])

    def timer(st):
        if st == "New customer":
            return last_order + p["new_customer_window_days"] * DAY, "Re-engage"
        if st == "Active":
            return last_order + p["reengage_factor"] * usual() * DAY, "Re-engage"
        if st == "Re-engage":
            return last_act + p["reactivate_days"] * DAY, "Reactivate"
        if st == "Retarget":
            return last_act + p["retarget_cooling_days"] * DAY, "New visitor"
        return None

    for t, kind in acts + [(end_sec, "end")]:
        while cur[0] is not None:
            tm = timer(cur[0])
            if tm is None or tm[0] >= t:
                break
            set_state(tm[1], max(tm[0], cur[1]), "silence")
        if kind == "end":
            break
        if kind == "o":
            orders.append(t)
            last_order = t
            last_act = t
            if cur[0] in (None, "New visitor", "Retarget"):
                set_state("New customer", t, "event")
            elif cur[0] in ("New customer", "Re-engage", "Reactivate"):
                set_state("Active", t, "event")
        elif kind == "v":
            last_act = t
            if cur[0] is None:
                set_state("New visitor", t, "event")
                nv = 1
            elif cur[0] == "New visitor":
                nv += 1
                if nv >= p["retarget_sessions"] and not orders:
                    set_state("Retarget", t, "event")
        elif kind == "c":
            last_act = t
            if cur[0] is None:
                set_state("New visitor", t, "event")
                set_state("Retarget", t, "event")
            elif cur[0] == "New visitor":
                set_state("Retarget", t, "event")
    if cur[0] is not None:
        stays.append((cur[0], cur[1], None, cur[2]))
    return stays
