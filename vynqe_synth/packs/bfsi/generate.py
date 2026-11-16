"""Chunked generation loop for the BFSI personal-loan pack."""
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
from .simulate import build_context, simulate_person, DAY
from .state_engine import run_bfsi_state_engine

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
    ids += [("wa_optin", "whatsapp"), ("legacy_flow", "multi"), ("policy_stall", "multi"), ("policy_lead", "multi"),
            ("policy_emi_due", "multi"), ("policy_topup", "multi"), ("policy_winback", "multi")]
    days = pd.date_range(X.start, periods=X.T, freq="D")
    cpc, ctr = cfg.v("campaigns.cpc_inr"), cfg.v("campaigns.ctr")
    for cid, ch in ids:
        system = {"paid_social": "meta_ads", "paid_search": "google_ads", "partner": "partner_portal"}.get(ch, "klaviyo" if ch == "multi" else "whatsapp")
        rows.append(dict(row_type="map", campaign_id=cid, system=system, system_campaign_id=f"{system}_{int(hashlib.md5(cid.encode()).hexdigest()[:7], 16)}",
                         name_hash=hashlib.sha256(cid.encode()).hexdigest()[:16], channel=ch, date=None, cost=None, clicks=None, impressions=None))
        if ch in cp:
            base = rng.uniform(1500, 6000)
            for d, m in zip(days, X.mult):
                clicks = int(rng.poisson(base / cpc * m))
                rows.append(dict(row_type="ad_daily", campaign_id=cid, system=system, system_campaign_id="", name_hash="", channel=ch, date=d,
                                 cost=round(clicks * cpc * float(rng.uniform(0.85, 1.15)), 2), clicks=clicks, impressions=int(clicks / ctr)))
    return pd.DataFrame(rows)


def generate(pack: str, preset: str, seed: int, out: Path, csv: bool = False, n_override: int | None = None):
    t0 = time.time()
    cfg = Cfg.load("bfsi")
    pr = load_preset(preset, "bfsi")
    n = n_override or pr["n_customers"]
    chunk = pr["chunk_size"]
    X = build_context(cfg, seed)
    vis, hid = out / "visible", out / "hidden"
    W = {nm: TableWriter(vis, nm, s.arrow(), csv) for nm, s in S.VISIBLE.items()}
    W.update({nm: TableWriter(hid, nm, s.arrow(), False) for nm, s in S.HIDDEN.items()})
    dump_schemas(S.VISIBLE, out / "schemas" / "visible")
    dump_schemas(S.HIDDEN, out / "schemas" / "hidden")
    sp = {"timeout_min": cfg.v("sessions.timeout_minutes"), "rule_version": cfg.v("states.rule_version"),
          "application_stall_days": cfg.v("states.application_stall_days"), "kyc_wait_days": cfg.v("states.kyc_wait_days"),
          "first_cycle_days": cfg.v("states.first_cycle_days"), "dormant_days": cfg.v("states.dormant_days"),
          "topup_after_ontime": cfg.v("repayment.topup_after_ontime")}
    noise_p = {k: cfg.v(f"noise.{k}") for k in ("duplicate", "missing_field", "wrong_timestamp", "late", "out_of_order", "ga4_late_days")}
    slow = {"razorpay": tuple(cfg.v("noise.slow_sources")["razorpay"])}
    tg = cfg.v("noise.tracking_gaps")
    gaps = tracking_gap_windows(np.random.default_rng([seed, 5]), X.E0, X.T, tg["per_year"], tg["days"])
    bot_share, bot_no = cfg.v("noise.bot_share_of_anon_sessions"), 0
    for c0 in range(0, n, chunk):
        idx = range(c0, min(n, c0 + chunk))
        R = {k: [] for k in ("borrowers", "events", "applications", "steps", "loans", "emi", "cases", "actions", "person_truth", "app_truth", "noise_extra")}
        for i in idx:
            o = simulate_person(i, X)
            R["borrowers"].append(o["borrower"])
            R["person_truth"].append(o["person_truth"])
            for k in ("events", "applications", "steps", "loans", "emi", "cases", "actions", "app_truth", "noise_extra"):
                R[k] += o[k]
        bor = pd.DataFrame(R["borrowers"])
        ev = pd.DataFrame(R["events"], columns=EV_COLS)
        ev["properties"] = [json.dumps(p, separators=(",", ":"), default=str) for p in ev["properties"]]
        rng = np.random.default_rng([seed, 3, c0])
        ev_clean = ev.copy()
        n_anon_pv = int(((ev["source_system"] == "trackflow") & ev["unit_id"].isna() & (ev["event_type"] == "page_view")).sum())
        nb = int(round(bot_share * n_anon_pv / cfg.v("sessions.mean_pages")))
        bots, blog = make_bots(rng, nb, X.E0, X.T, f"BOT{c0:07d}", bot_no, source="trackflow")
        bot_no += len(bots)
        vis_ev, nlog = apply_noise(ev, rng, noise_p, gaps, pv_source="trackflow", daily=("core_banking",), slow=slow)
        vis_ev = pd.concat([vis_ev, bots], ignore_index=True)
        pt = pd.DataFrame(R["person_truth"])
        for u, w in zip(pt["unit_id"], pt["shared_phone_with"]):
            if isinstance(w, str):
                nlog.append((None, "shared_device", json.dumps({"unit": u, "shares_with": w})))
        nlog += blog + R["noise_extra"]
        vis_ev["occurred_at"] = _ts(vis_ev["occurred_s"])
        vis_ev["ingested_at"] = _ts(vis_ev["ingested_s"])
        vis_ev["placement_id"] = None
        vis_ev = vis_ev.sort_values("occurred_at", kind="mergesort").reset_index(drop=True)
        sh = run_bfsi_state_engine(vis_ev, bor, sp, unit_col="unit_id", end_sec=X.END)
        ec = ev_clean.copy()
        ec["occurred_at"] = _ts(ec["occurred_s"])
        ec = ec.drop(columns=["unit_id"]).rename(columns={"true_unit": "unit_id"})
        st = run_bfsi_state_engine(ec, bor, sp, unit_col="unit_id", stitch=False, end_sec=X.END)
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
        bor = tsfix(bor, ["created_at", "first_application_at", "holdout_assigned_at"])
        mk = lambda key, cols: pd.DataFrame(R[key]) if R[key] else pd.DataFrame(columns=cols)
        apps = tsfix(mk("applications", S.applications.names), ["created_at", "stage_changed_at", "sanction_date", "disbursal_date"])
        steps = tsfix(mk("steps", S.application_steps.names), ["started_at", "completed_at"])
        loans = tsfix(mk("loans", S.loans.names), ["opened_at", "closed_at", "defaulted_at"])
        emi = tsfix(mk("emi", S.emi_payments.names), ["due_date", "created_at"])
        cases = tsfix(mk("cases", S.service_cases.names), ["opened_at", "closed_at"])
        at = tsfix(mk("app_truth", S.application_truth.names), ["first_dpd90_at"])
        W["borrowers"].write(conform(S.borrowers, bor))
        W["events"].write(conform(S.events, vis_ev[S.events.names]))
        W["applications"].write(conform(S.applications, apps))
        W["application_steps"].write(conform(S.application_steps, steps))
        W["loans"].write(conform(S.loans, loans))
        W["emi_payments"].write(conform(S.emi_payments, emi))
        W["service_cases"].write(conform(S.service_cases, cases))
        W["actions"].write(conform(S.actions, act[S.actions.names]))
        W["state_history"].write(conform(S.state_history, sh))
        W["person_truth"].write(conform(S.person_truth, pt))
        W["application_truth"].write(conform(S.application_truth, at))
        W["state_truth"].write(conform(S.state_truth, st[S.state_truth.names]))
        W["noise_log"].write(conform(S.noise_log, pd.DataFrame(nlog, columns=["event_id", "defect", "detail"])))
        print(f"  chunk {c0}-{idx[-1]}: events {len(vis_ev):,} apps {len(apps):,} loans {len(loans):,} emi {len(emi):,} actions {len(act):,} [{time.time()-t0:.0f}s]", flush=True)
    W["campaigns"].write(conform(S.campaigns, build_campaigns(X, cfg, np.random.default_rng([seed, 9]))))
    counts = {k: w.n for k, w in W.items()}
    for w in W.values():
        w.close()
    (out / "reports").mkdir(exist_ok=True)
    (out / "reports" / "row_counts.json").write_text(json.dumps({"n_people": n, "seed": seed, "preset": preset, "rows": counts,
                                                                  "seconds": round(time.time() - t0, 1)}, indent=1))
    return counts
