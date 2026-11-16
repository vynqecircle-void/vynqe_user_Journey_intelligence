"""Controlled mess injected into the clean event stream. Every injection is written to noise_log (hidden)."""
from __future__ import annotations
import json
import numpy as np
import pandas as pd

DAY = 86400.0


def _log(rows, ids, defect, details):
    for i, d in zip(ids, details):
        rows.append((i, defect, json.dumps(d, separators=(",", ":"))))


def tracking_gap_windows(rng, E0, n_days, per_year, days):
    n = max(1, int(round(per_year * n_days / 365.0)))
    starts = np.sort(rng.uniform(5, n_days - 5, n))
    return [(E0 + s * DAY, E0 + (s + days) * DAY) for s in starts]


def apply_noise(ev: pd.DataFrame, rng: np.random.Generator, p: dict, gaps: list, pv_source: str = "ga4",
                daily=("ga4",), slow: dict | None = None) -> tuple[pd.DataFrame, list]:
    """ev: clean events with occurred_s (epoch seconds) and true_unit. Returns visible events + noise rows."""
    log: list = []
    t = ev["occurred_s"].to_numpy().astype(float)
    src = ev["source_system"].to_numpy()
    et = ev["event_type"].to_numpy()
    eid = ev["event_id"].to_numpy()

    # tracking gaps: browsing events vanish
    is_pv = (src == pv_source) & (et == "page_view")
    drop = np.zeros(len(ev), bool)
    for a, b in gaps:
        drop |= is_pv & (t >= a) & (t < b)
    if drop.any():
        _log(log, eid[drop], "tracking_gap", [{"reason": "analytics outage"}] * int(drop.sum()))
    ev = ev.loc[~drop].reset_index(drop=True)
    t = t[~drop]; src = src[~drop]; et = et[~drop]; eid = ev["event_id"].to_numpy()
    n = len(ev)

    # base ingestion lag: GA4 = daily export next morning; webhooks = seconds
    isd = np.isin(src, list(daily))
    ing = np.where(isd, np.floor(t / DAY) * DAY + DAY + 6 * 3600 + rng.uniform(0, 10800, n),
                   t + rng.uniform(1, 60, n))
    ing = np.where((src == "klaviyo") | (src == "whatsapp"), t + rng.uniform(1, 300, n), ing)

    # slower sources (for example mandates T+1..T+2): fixed extra lag range per source
    for sname, (lo, hi) in (slow or {}).items():
        m_ = src == sname
        if m_.any():
            ing = np.where(m_, ing + rng.uniform(lo, hi, n) * DAY, ing)

    # late arrivals
    late = rng.random(n) < p["late"]
    extra = np.where(isd, rng.uniform(1.0, p["ga4_late_days"], n) * DAY, rng.uniform(3600, 2 * DAY, n))
    ing = np.where(late, ing + extra, ing)
    _log(log, eid[late], "late", [{"delay_h": round(float(x) / 3600, 1)} for x in extra[late]])

    # out of order: status changes that arrive after later statuses
    ooo = (et == "record_status_changed") & (rng.random(n) < p["out_of_order"] / 0.25)
    ooo &= ~late
    d = rng.uniform(DAY, 3 * DAY, n)
    ing = np.where(ooo, ing + d, ing)
    _log(log, eid[ooo], "out_of_order", [{"delay_h": round(float(x) / 3600, 1)} for x in d[ooo]])

    # wrong timestamps: timezone or day errors in occurred_at
    wt = rng.random(n) < p["wrong_timestamp"]
    off = rng.choice([19800.0, -19800.0, DAY, -DAY], n)
    _log(log, eid[wt], "wrong_timestamp", [{"offset_s": float(x)} for x in off[wt]])
    t2 = np.where(wt, t + off, t)

    ev = ev.copy()
    ev["occurred_s"] = t2
    ev["ingested_s"] = np.maximum(ing, t2 + 0.5)

    # missing fields: channel blanked
    mf = (rng.random(n) < p["missing_field"]) & ev["channel"].notna().to_numpy()
    _log(log, ev["event_id"].to_numpy()[mf], "missing_field", [{"field": "channel"}] * int(mf.sum()))
    ev.loc[mf, "channel"] = None

    # duplicates: same source_event_id, new event_id, a little later
    dup = rng.random(n) < p["duplicate"]
    if dup.any():
        cp = ev.loc[dup].copy()
        cp["event_id"] = cp["event_id"] + "-D"
        cp["ingested_s"] = cp["ingested_s"] + rng.uniform(1, 3600, len(cp))
        _log(log, cp["event_id"].to_numpy(), "duplicate", [{"of": e[:-2]} for e in cp["event_id"]])
        ev = pd.concat([ev, cp], ignore_index=True)
    return ev, log


def make_bots(rng: np.random.Generator, n_sessions: int, E0: float, n_days: int, prefix: str, start_no: int,
              source: str = "ga4"):
    """Bot sessions: many fast page views, anonymous, never identify. Returns visible-event rows + noise rows."""
    rows, log = [], []
    k = start_no
    for s in range(n_sessions):
        anon = f"{int(rng.integers(10**8, 10**9))}.{int(E0 + rng.uniform(0, n_days) * DAY)}"
        t0 = E0 + rng.uniform(0, n_days) * DAY
        sid = int(t0)
        n_ev = int(rng.integers(30, 80))
        tt = t0
        for j in range(n_ev):
            tt += rng.uniform(0.2, 1.5)
            eid = f"{prefix}-{k:07d}"
            k += 1
            props = json.dumps({"ga4_event": "view_item", "session_id": sid, "platform": "web"}, separators=(",", ":"))
            rows.append((eid, f"pv:{anon}:{sid}:{j}", "page_view", source, None, anon, None, tt,
                         tt + 6 * 3600 + 7200, "organic", None, None, None, props, None))
            log.append((eid, "bot", json.dumps({"session": sid})))
    cols = ["event_id", "source_event_id", "event_type", "source_system", "person_key", "anonymous_id", "unit_id",
            "occurred_s", "ingested_s", "channel", "campaign_id", "placement_id", "consent_status", "properties",
            "true_unit"]
    return pd.DataFrame(rows, columns=cols), log
