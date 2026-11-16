"""Chunked generation loop for the B2B SaaS pack."""
from __future__ import annotations
import hashlib
import json
import time
from pathlib import Path
import numpy as np
import pandas as pd

from ...core.config import Cfg, load_preset
from ...core.io import TableWriter
from ...core.noise import apply_noise, make_bots, tracking_gap_windows
from ...core.schema import conform, dump_schemas
from . import schemas as S
from .simulate import build_context, simulate_account, DAY
from .state_engine import run_b2b_state_engine

EV_COLS = ["event_id", "occurred_s", "event_type", "source_system", "source_event_id", "person_key", "anonymous_id",
           "unit_id", "channel", "campaign_id", "consent_status", "properties", "true_unit"]


def _ts(s):
    return pd.to_datetime(s, unit="s", utc=True)


def tsfix(df, cols):
    for c in cols:
        if c in df and df[c].dtype.kind in "fi":
            df[c] = pd.to_datetime(df[c], unit="s", utc=True)
    return df


def build_campaigns(X, cfg, rng):
    rows = []
    cp = cfg.v("campaigns.ad_campaigns")
    pref = {"paid_social": "meta", "paid_search": "gads", "partner": "partner"}
    ids = [(f"{pref[ch]}_{k}", ch) for ch, n in cp.items() for k in range(1, n + 1)]
    for trig in ("lead_stall", "opp_stall", "onboarding", "risk", "expansion", "winback"):
        ids += [(f"policy_{trig}", "email"), (f"legacy_{trig}", "email")]
    ids += [("policy_invoice", "email"), ("policy_renewal_notice", "email")]
    days = pd.date_range(X.start, periods=X.T, freq="D")
    cpc, ctr = cfg.v("campaigns.cpc_usd"), cfg.v("campaigns.ctr")
    for cid, ch in ids:
        system = {"paid_social": "meta_ads", "paid_search": "google_ads", "partner": "partner_portal"}.get(ch, "klaviyo")
        rows.append(dict(row_type="map", campaign_id=cid, system=system, system_campaign_id=f"{system}_{int(hashlib.md5(cid.encode()).hexdigest()[:7], 16)}",
                         name_hash=hashlib.sha256(cid.encode()).hexdigest()[:16], channel=ch, date=None, cost=None, clicks=None, impressions=None))
        if ch in cp:
            base = rng.uniform(40, 160)
            for d in days:
                clicks = int(rng.poisson(base * (0.35 if d.weekday() >= 5 else 1.0)))
                rows.append(dict(row_type="ad_daily", campaign_id=cid, system=system, system_campaign_id="", name_hash="", channel=ch, date=d,
                                 cost=round(clicks * cpc * float(rng.uniform(0.85, 1.15)), 2), clicks=clicks, impressions=int(clicks / ctr)))
    return pd.DataFrame(rows)


def generate(pack: str, preset: str, seed: int, out: Path, csv: bool = False, n_override: int | None = None):
    t0 = time.time()
    cfg = Cfg.load("b2b_saas")
    pr = load_preset(preset, "b2b_saas")
    n_base, n_new = pr["n_base"], (n_override if n_override else pr["n_new"])
    if n_override:
        n_base = max(10, int(round(pr["n_base"] * n_override / pr["n_new"])))
    n = n_base + n_new
    chunk = pr["chunk_size"]
    X = build_context(cfg, seed, n_base, n_new)
    vis, hid = out / "visible", out / "hidden"
    W = {nm: TableWriter(vis, nm, s.arrow(), csv) for nm, s in S.VISIBLE.items()}
    W.update({nm: TableWriter(hid, nm, s.arrow(), False) for nm, s in S.HIDDEN.items()})
    dump_schemas(S.VISIBLE, out / "schemas" / "visible")
    dump_schemas(S.HIDDEN, out / "schemas" / "hidden")
    sp = {"rule_version": cfg.v("states.rule_version"), "onboarding_max_days": cfg.v("states.onboarding_max_days"),
          "at_risk_window_days": cfg.v("states.at_risk_window_days"), "cooling_off_days": cfg.v("states.cooling_off_days")}
    noise_p = {k: cfg.v(f"noise.{k}") for k in ("duplicate", "missing_field", "wrong_timestamp", "late", "out_of_order", "ga4_late_days")}
    tg = cfg.v("noise.tracking_gaps")
    gaps = tracking_gap_windows(np.random.default_rng([seed, 5]), X.E0, X.T, tg["per_year"], tg["days"])
    bot_share, bot_no = cfg.v("noise.bot_share_of_anon_sessions"), 0
    for c0 in range(0, n, chunk):
        idx = range(c0, min(n, c0 + chunk))
        R = {k: [] for k in ("accounts", "contacts", "events", "opps", "subs", "invs", "actions", "account_truth", "contact_truth", "opp_truth", "noise_extra")}
        usage = []
        for i in idx:
            o = simulate_account(i, X)
            for k in R:
                R[k] += o[k]
            if o["usage"] is not None:
                usage.append(o["usage"])
        acc = pd.DataFrame(R["accounts"])
        ev = pd.DataFrame(R["events"], columns=EV_COLS)
        ev["properties"] = [json.dumps(p, separators=(",", ":"), default=str) for p in ev["properties"]]
        rng = np.random.default_rng([seed, 3, c0])
        ev_clean = ev.copy()
        n_anon_pv = int(((ev["source_system"] == "ga4") & ev["person_key"].isna() & (ev["event_type"] == "page_view")).sum())
        nb = int(round(bot_share * n_anon_pv / cfg.v("sessions.mean_pages")))
        bots, blog = make_bots(rng, nb, X.E0, X.T, f"BOT{c0:07d}", bot_no, source="ga4")
        bot_no += len(bots)
        vis_ev, nlog = apply_noise(ev, rng, noise_p, gaps, pv_source="ga4", daily=("ga4", "amplitude"))
        vis_ev = pd.concat([vis_ev, bots], ignore_index=True)
        nlog += blog + R["noise_extra"]
        vis_ev["occurred_at"] = _ts(vis_ev["occurred_s"])
        vis_ev["ingested_at"] = _ts(vis_ev["ingested_s"])
        vis_ev["placement_id"] = None
        vis_ev = vis_ev.sort_values("occurred_at", kind="mergesort").reset_index(drop=True)
        sh = run_b2b_state_engine(vis_ev, acc, sp, unit_col="unit_id", end_sec=X.END)
        ec = ev_clean.copy()
        ec["occurred_at"] = _ts(ec["occurred_s"])
        ec = ec.drop(columns=["unit_id"]).rename(columns={"true_unit": "unit_id"})
        st = run_b2b_state_engine(ec, acc, sp, unit_col="unit_id", end_sec=X.END)
        act = pd.DataFrame(R["actions"]) if R["actions"] else pd.DataFrame(columns=[c for c in S.actions.names if c != "state"])
        if len(act):
            act = tsfix(act, ["decided_at", "sent_at", "task_due_at"])
            for c in ("decided_at", "sent_at", "task_due_at"):
                act[c] = pd.to_datetime(act[c], utc=True)
            a = act.sort_values("decided_at")
            s2 = sh[["unit_id", "entered_at", "state"]].copy()
            s2["entered_at"] = pd.to_datetime(s2["entered_at"], utc=True).astype("datetime64[ns, UTC]")
            a["decided_at"] = a["decided_at"].astype("datetime64[ns, UTC]")
            m = pd.merge_asof(a, s2.sort_values("entered_at"), left_on="decided_at", right_on="entered_at", by="unit_id", direction="backward")
            act = m.drop(columns=["entered_at"])
        else:
            act["state"] = None
        mk = lambda key, cols: pd.DataFrame(R[key]) if R[key] else pd.DataFrame(columns=cols)
        acc = tsfix(acc, ["created_at", "first_won_at", "renewal_at", "holdout_assigned_at"])
        con = tsfix(mk("contacts", S.contacts.names), ["first_seen_at", "left_account_at", "lead_created_at", "lead_converted_at"])
        opp = tsfix(mk("opps", S.opportunities.names), ["created_at", "close_date", "closed_at", "incumbent_contract_end", "esign_changed_at"])
        sub = tsfix(mk("subs", S.subscriptions.names), ["start_at", "end_at", "status_changed_at", "trial_end"])
        inv = tsfix(mk("invs", S.invoices.names), ["issued_at", "due_at", "paid_at"])
        use = pd.concat(usage, ignore_index=True) if usage else pd.DataFrame(columns=S.product_usage_daily.names)
        use = tsfix(use, ["day", "ingested_at"])
        at = tsfix(pd.DataFrame(R["account_truth"]), ["churn_at", "champion_left_at"])
        ct = mk("contact_truth", S.contact_truth.names)
        ot = mk("opp_truth", S.opportunity_truth.names)
        W["accounts"].write(conform(S.accounts, acc))
        W["contacts"].write(conform(S.contacts, con))
        W["events"].write(conform(S.events, vis_ev[S.events.names]))
        W["opportunities"].write(conform(S.opportunities, opp))
        W["product_usage_daily"].write(conform(S.product_usage_daily, use[S.product_usage_daily.names]))
        W["subscriptions"].write(conform(S.subscriptions, sub))
        W["invoices"].write(conform(S.invoices, inv))
        W["actions"].write(conform(S.actions, act[S.actions.names]))
        W["state_history"].write(conform(S.state_history, sh))
        W["account_truth"].write(conform(S.account_truth, at))
        W["contact_truth"].write(conform(S.contact_truth, ct))
        W["opportunity_truth"].write(conform(S.opportunity_truth, ot))
        W["state_truth"].write(conform(S.state_truth, st[S.state_truth.names]))
        W["noise_log"].write(conform(S.noise_log, pd.DataFrame(nlog, columns=["event_id", "defect", "detail"])))
        print(f"  chunk {c0}-{idx[-1]}: events {len(vis_ev):,} usage {len(use):,} opps {len(opp):,} subs {len(sub):,} invoices {len(inv):,} actions {len(act):,} [{time.time()-t0:.0f}s]", flush=True)
    W["campaigns"].write(conform(S.campaigns, build_campaigns(X, cfg, np.random.default_rng([seed, 9]))))
    counts = {k: w.n for k, w in W.items()}
    for w in W.values():
        w.close()
    (out / "reports").mkdir(exist_ok=True)
    (out / "reports" / "row_counts.json").write_text(json.dumps({"n_accounts": n, "n_base": n_base, "n_new": n_new, "seed": seed, "preset": preset,
                                                                  "rows": counts, "seconds": round(time.time() - t0, 1)}, indent=1))
    return counts
