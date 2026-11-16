"""Chunked generation loop for the e-commerce pack."""
from __future__ import annotations
import json
import time
from pathlib import Path
import numpy as np
import pandas as pd

from ...core.config import Cfg, load_preset
from ...core.io import TableWriter
from ...core.noise import apply_noise, make_bots, tracking_gap_windows
from ...core.schema import conform, dump_schemas
from ...core.state_engine import run_state_engine
from . import schemas as S
from .simulate import build_context, simulate_customer, DAY

EV_COLS = ["event_id", "occurred_s", "event_type", "source_system", "source_event_id", "person_key", "anonymous_id",
           "unit_id", "channel", "campaign_id", "consent_status", "properties", "true_unit"]


def _ts(s):
    return pd.to_datetime(s, unit="s", utc=True)


def build_campaigns(X, cfg, rng):
    rows = []
    cp = cfg.v("campaigns.ad_campaigns")
    ids = [(f"{'meta' if ch == 'paid_social' else 'gads' if ch == 'paid_search' else 'aff'}_{k}", ch)
           for ch, n in cp.items() for k in range(1, n + 1)]
    ids += [("wa_optin", "whatsapp"), ("flow_cart_reminder", "email"), ("policy_weekly", "whatsapp"),
            ("legacy_flow_cart", "email"), ("legacy_weekly_blast", "email")]
    import hashlib
    days = pd.date_range(X.start, periods=X.T, freq="D")
    for cid, ch in ids:
        system = {"paid_social": "meta_ads", "paid_search": "google_ads"}.get(ch, "klaviyo" if ch == "email" else "whatsapp" if ch == "whatsapp" else "affiliate_net")
        rows.append(dict(row_type="map", campaign_id=cid, system=system, system_campaign_id=f"{system}_{abs(hash(cid)) % 10**8:08d}" if False else f"{system}_{int(hashlib.md5(cid.encode()).hexdigest()[:7], 16)}",
                         name_hash=hashlib.sha256(cid.encode()).hexdigest()[:16], channel=ch, date=None, cost=None, clicks=None, impressions=None))
        if ch in ("paid_social", "paid_search", "affiliate"):
            cpc, ctr = cfg.v("campaigns.cpc_inr"), cfg.v("campaigns.ctr")
            base = rng.uniform(1500, 6000)
            for d, m in zip(days, X.mult):
                clicks = int(rng.poisson(base / cpc * m * (1 + 0.8 * (d >= X.start + pd.Timedelta(days=int(X.reg2))) * 0)))
                rows.append(dict(row_type="ad_daily", campaign_id=cid, system=system, system_campaign_id="", name_hash="", channel=ch,
                                 date=d, cost=round(clicks * cpc * float(rng.uniform(0.85, 1.15)), 2), clicks=clicks,
                                 impressions=int(clicks / ctr)))
    return pd.DataFrame(rows)


def build_category_value(X):
    rows = []
    months = pd.date_range(X.start, periods=int(X.month_idx.max()) + 1, freq="MS")
    for c in X.cat_names:
        m = X.cats[c]["margin"]
        for k, mo in enumerate(months):
            rows.append(dict(category=c, month=mo, margin_band="<20%" if m < .2 else "20-30%" if m < .3 else "30-40%" if m < .4 else "40%+",
                             return_cost_band="low" if X.cats[c]["ret"] < 1 else "medium" if X.cats[c]["ret"] < 2 else "high",
                             stock_status=X.stock[c][k]))
    return pd.DataFrame(rows)


def generate(pack: str, preset: str, seed: int, out: Path, csv: bool = False, n_override: int | None = None):
    t0 = time.time()
    cfg = Cfg.load(pack)
    pr = load_preset(preset)
    n = n_override or pr["n_customers"]
    chunk = pr["chunk_size"]
    X = build_context(cfg, seed)
    vis, hid = out / "visible", out / "hidden"
    W = {nm: TableWriter(vis, nm, s.arrow(), csv) for nm, s in S.VISIBLE.items()}
    W.update({nm: TableWriter(hid, nm, s.arrow(), False) for nm, s in S.HIDDEN.items()})
    dump_schemas(S.VISIBLE, out / "schemas" / "visible")
    dump_schemas(S.HIDDEN, out / "schemas" / "hidden")
    sp = {"timeout_min": cfg.v("sessions.timeout_minutes"), "rule_version": cfg.v("states.rule_version")}
    for k in ("default_usual_gap_days", "new_customer_window_days", "reengage_factor", "reactivate_days",
              "retarget_cooling_days", "retarget_sessions"):
        sp[k] = cfg.v(f"states.{k}")
    npar = cfg.v("noise")
    noise_p = {k: cfg.v(f"noise.{k}") for k in ("duplicate", "missing_field", "wrong_timestamp", "late", "out_of_order", "ga4_late_days")}
    gaps = tracking_gap_windows(np.random.default_rng([seed, 5]), X.E0, X.T, cfg.v("noise.tracking_gaps")["per_year"], cfg.v("noise.tracking_gaps")["days"])
    bot_share = cfg.v("noise.bot_share_of_anon_sessions")
    bot_no = 0
    for c0 in range(0, n, chunk):
        idx = range(c0, min(n, c0 + chunk))
        R = {k: [] for k in ("customer", "events", "orders", "payments", "tickets", "actions", "person_truth", "order_truth")}
        for i in idx:
            o = simulate_customer(i, X)
            R["customer"].append(o["customer"]); R["events"] += o["events"]
            for k in ("orders", "payments", "tickets", "actions", "order_truth"):
                R[k] += o[k]
            R["person_truth"].append(o["person_truth"])
        cust = pd.DataFrame(R["customer"])
        ev = pd.DataFrame(R["events"], columns=EV_COLS)
        ev["properties"] = [json.dumps(p, separators=(",", ":"), default=str) for p in ev["properties"]]
        rng = np.random.default_rng([seed, 3, c0])
        ev_clean = ev.copy()
        # bots
        n_anon_pv = int(((ev["source_system"] == "ga4") & ev["unit_id"].isna()).sum())
        nb = int(round(bot_share * n_anon_pv / cfg.v("sessions.mean_pages")))
        bots, blog = make_bots(rng, nb, X.E0, X.T, f"BOT{c0:07d}", bot_no)
        bot_no += len(bots)
        vis_ev, nlog = apply_noise(ev, rng, noise_p, gaps)
        vis_ev = pd.concat([vis_ev, bots], ignore_index=True)
        # shared phones logged
        pt = pd.DataFrame(R["person_truth"])
        for u, w in zip(pt["unit_id"], pt["shared_phone_with"]):
            if isinstance(w, str):
                nlog.append((None, "shared_device", json.dumps({"unit": u, "shares_with": w})))
        nlog += blog
        vis_ev["occurred_at"] = _ts(vis_ev["occurred_s"])
        vis_ev["ingested_at"] = _ts(vis_ev["ingested_s"])
        vis_ev["placement_id"] = None
        vis_ev = vis_ev.sort_values("occurred_at", kind="mergesort").reset_index(drop=True)
        # state engine: visible (noisy, partially linked) and truth (clean, fully linked)
        sh = run_state_engine(vis_ev, cust, sp, unit_col="unit_id", end_sec=X.END)
        ec = ev_clean.copy()
        ec["occurred_at"] = _ts(ec["occurred_s"])
        ec = ec.drop(columns=["unit_id"]).rename(columns={"true_unit": "unit_id"})
        st = run_state_engine(ec, cust, sp, unit_col="unit_id", stitch=False, end_sec=X.END)
        # actions with state
        act = pd.DataFrame(R["actions"])
        if len(act):
            for c in ("decided_at", "sent_at", "task_due_at"):
                act[c] = _ts(act[c]) if act[c].notna().any() else pd.NaT
            a = act.sort_values("decided_at")
            s2 = sh[["unit_id", "entered_at", "state"]].copy()
            s2["entered_at"] = pd.to_datetime(s2["entered_at"], utc=True).astype("datetime64[ns, UTC]")
            a["decided_at"] = a["decided_at"].astype("datetime64[ns, UTC]")
            m = pd.merge_asof(a.drop(columns=["state"], errors="ignore"), s2.sort_values("entered_at"), left_on="decided_at",
                              right_on="entered_at", by="unit_id", direction="backward")
            act = m.drop(columns=["entered_at"])
        else:
            act = pd.DataFrame(columns=S.actions.names)
        for c in ("sent_at", "task_due_at"):
            if c in act:
                act[c] = pd.to_datetime(act[c], utc=True)
        # tables
        def tsfix(df, cols):
            for c in cols:
                df[c] = pd.to_datetime(df[c], unit="s", utc=True) if df[c].dtype.kind in "fi" else df[c]
            return df
        od = tsfix(pd.DataFrame(R["orders"]), ["created_at", "processed_at", "cancelled_at", "paid_at",
                                               "delivery_status_changed_at", "delivered_at", "refund_created_at"])
        pay = tsfix(pd.DataFrame(R["payments"]), ["created_at"])
        tk = tsfix(pd.DataFrame(R["tickets"]), ["created_at", "updated_at", "solved_at"])
        cust = tsfix(cust, ["created_at", "first_order_at", "holdout_assigned_at"])
        ot = pd.DataFrame(R["order_truth"])
        for c in ("actions",):
            pass
        W["customers"].write(conform(S.customers, cust))
        W["events"].write(conform(S.events, vis_ev[S.events.names]))
        W["orders"].write(conform(S.orders, od))
        W["payments"].write(conform(S.payments, pay))
        W["tickets"].write(conform(S.tickets, tk))
        W["actions"].write(conform(S.actions, act[S.actions.names]))
        W["state_history"].write(conform(S.state_history, sh))
        W["person_truth"].write(conform(S.person_truth, pt))
        W["order_truth"].write(conform(S.order_truth, ot))
        W["state_truth"].write(conform(S.state_truth, st[S.state_truth.names]))
        nl = pd.DataFrame(nlog, columns=["event_id", "defect", "detail"])
        W["noise_log"].write(conform(S.noise_log, nl))
        print(f"  chunk {c0}-{idx[-1]}: events {len(vis_ev):,} orders {len(od):,} actions {len(act):,}  [{time.time()-t0:.0f}s]", flush=True)
    rng = np.random.default_rng([seed, 9])
    W["campaigns"].write(conform(S.campaigns, build_campaigns(X, cfg, rng)))
    W["category_value"].write(conform(S.category_value, build_category_value(X)))
    counts = {k: w.n for k, w in W.items()}
    for w in W.values():
        w.close()
    (out / "reports").mkdir(exist_ok=True)
    (out / "reports" / "row_counts.json").write_text(json.dumps({"n_customers": n, "seed": seed, "preset": preset, "rows": counts,
                                                                  "seconds": round(time.time() - t0, 1)}, indent=1))
    return counts
