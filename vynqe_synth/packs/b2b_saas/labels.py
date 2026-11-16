"""B2B point-in-time label builder. Uses VISIBLE events and the visible actions table only (never hidden truth).
A decision at time t with horizon H is labelled from events in (t, t+H]. A row is FINAL only when t + H + buffer <= extract
time, so late and out-of-order events (which arrive after they occurred) cannot flip a label after it is written."""
from __future__ import annotations
import json
from collections import defaultdict
import numpy as np
import pandas as pd

KIND = {  # trigger -> (label name, horizon days)
    "lead_stall": ("lead_progressed_30d", 30), "opp_stall": ("deal_won_180d", 180), "onboarding": ("first_value_90d", 90),
    "risk": ("churned_within_165d", 165), "expansion": ("expansion_won_120d", 120), "winback": ("resubscribed_180d", 180)}


def _loads(s):
    try:
        return json.loads(s)
    except Exception:
        return {}


def build_labels(events: pd.DataFrame, actions: pd.DataFrame, buffer_days: int = 45, extract_at=None) -> pd.DataFrame:
    ev = events[events["event_type"].isin(["record_created", "record_status_changed"]) & events["unit_id"].notna()]
    ev = ev[ev["source_system"].isin(["salesforce", "hubspot", "stripe", "amplitude"])]
    if extract_at is None:
        extract_at = events["ingested_at"].max()
    out = defaultdict(lambda: defaultdict(list))   # kind -> unit -> [times]
    opp_won = defaultdict(list)
    for u, t, et, pr in zip(ev["unit_id"], ev["occurred_at"], ev["event_type"], ev["properties"]):
        if '"object":"' not in pr:
            continue
        d = _loads(pr)
        o, to = d.get("object"), d.get("to")
        if o == "lead" and to in ("contacted", "qualified", "converted"):
            out["lead_progressed_30d"][u].append(t)
        elif o == "opportunity" and to == "closed_won":
            opp_won[d.get("id")].append(t)
            if d.get("type") == "expansion":
                out["expansion_won_120d"][u].append(t)
        elif o == "onboarding" and to == "first_value_reached":
            out["first_value_90d"][u].append(t)
        elif o == "subscription":
            if d.get("final") and to in ("cancelled", "expired", "past_due", "paused"):
                out["churned_within_165d"][u].append(t)
            elif et == "record_created" and d.get("returning"):
                out["resubscribed_180d"][u].append(t)
    rows = []
    a = actions[actions["trigger"].isin(KIND)]
    for aid, u, t, trig, opp, act in zip(a["action_id"], a["unit_id"], a["decided_at"], a["trigger"], a["opp_id"], a["chosen_action"]):
        name, H = KIND[trig]
        if trig == "opp_stall":
            ts = opp_won.get(opp, [])
        else:
            ts = out[name].get(u, [])
        y = any(t < x <= t + pd.Timedelta(days=H) for x in ts)
        final = bool(t + pd.Timedelta(days=H + buffer_days) <= extract_at)
        rows.append((aid, u, t, trig, act, name, H, int(y), final, t + pd.Timedelta(days=H + buffer_days)))
    return pd.DataFrame(rows, columns=["action_id", "unit_id", "decided_at", "trigger", "chosen_action", "label", "horizon_days", "y", "is_final", "final_at"])
