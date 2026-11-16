"""Point-in-time label builder. Uses VISIBLE events only. A label for a decision at time t and horizon H counts an
order created in (t, t+H]. A row is FINAL only when t + H + buffer <= extract time, so late and out-of-order
events (which arrive after occurrence) cannot flip the label after it was written."""
from __future__ import annotations
import json
import pandas as pd


def build_labels(events: pd.DataFrame, actions: pd.DataFrame, horizons=(7, 30), buffer_days=45, extract_at=None):
    ev = events[events["event_type"].isin(["record_created"])].copy()
    ev = ev[ev["properties"].str.contains('"object":"order"')]
    ev = ev.drop_duplicates("source_event_id")
    if extract_at is None:
        extract_at = events["ingested_at"].max()
    o = ev[["unit_id", "occurred_at"]].dropna().sort_values("occurred_at")
    a = actions[actions["record_kind"] == "decision"][["action_id", "unit_id", "decided_at", "chosen_action"]].copy()
    a = a.sort_values("decided_at")
    out = a.copy()
    import numpy as np
    o["tn"] = o["occurred_at"].dt.tz_convert("UTC").dt.tz_localize(None).astype("datetime64[ns]")
    grp = {u: np.sort(g["tn"].to_numpy()) for u, g in o.groupby("unit_id")}
    a["tn"] = a["decided_at"].dt.tz_convert("UTC").dt.tz_localize(None).astype("datetime64[ns]")
    ext = pd.Timestamp(extract_at).tz_convert("UTC").tz_localize(None).to_datetime64()
    for H in horizons:
        lab = np.zeros(len(a), int)
        for k, (u, t) in enumerate(zip(a["unit_id"].to_numpy(), a["tn"].to_numpy())):
            ts = grp.get(u)
            if ts is not None:
                lab[k] = int(np.searchsorted(ts, t + np.timedelta64(H, "D"), side="right") - np.searchsorted(ts, t, side="right") > 0)
        out[f"ordered_{H}d"] = lab
        out[f"final_{H}d"] = (a["tn"] + pd.Timedelta(days=H + buffer_days)).to_numpy() <= ext
    return out.drop(columns=["tn"], errors="ignore")
