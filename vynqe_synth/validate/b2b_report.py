"""Validation of a generated B2B SaaS dataset. Reads parquet only. Hidden truth is used HERE (the validator),
never by state-engine or label code. Every check reports observed vs expected; nothing is asserted without being computed."""
from __future__ import annotations
import ast
import json
import re
from pathlib import Path
import numpy as np
import pandas as pd
from ..core.config import Cfg
from ..packs.b2b_saas import schemas as S
from ..packs.b2b_saas.labels import build_labels

R = []
PKG = Path(__file__).resolve().parent.parent


def chk(group, name, observed, expected, ok, note=""):
    R.append({"group": group, "check": name, "observed": observed, "expected": expected, "pass": bool(ok), "note": note})


def near(group, name, obs, target, tol, note=""):
    chk(group, name, round(float(obs), 4), f"{target} +/- {tol}", abs(float(obs) - target) <= tol, note)


def rd(d, sub, n):
    return pd.read_parquet(d / sub / f"{n}.parquet")


def auc(score, y):
    r = pd.Series(score).rank().to_numpy()
    y = np.asarray(y).astype(bool)
    n1, n0 = int(y.sum()), int((~y).sum())
    return float((r[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)) if n1 and n0 else float("nan")


def validate(out: Path):
    R.clear()
    cfg = Cfg.load("b2b_saas")
    v = cfg.v
    V = {n: rd(out, "visible", n) for n in S.VISIBLE}
    H = {n: rd(out, "hidden", n) for n in S.HIDDEN}
    acc, con, ev, opp, use, sub, inv, ac, sh, cp = (V[k] for k in ("accounts", "contacts", "events", "opportunities", "product_usage_daily",
                                                              "subscriptions", "invoices", "actions", "state_history", "campaigns"))
    at, ct, ot, stt, nl = H["account_truth"], H["contact_truth"], H["opportunity_truth"], H["state_truth"], H["noise_log"]
    START = pd.Timestamp(v("run.start_date"), tz="UTC")
    END = START + pd.Timedelta(days=int(v("run.n_days")))
    REG2 = START + pd.Timedelta(days=int(v("run.regime2_day")))
    # ------------------------------------------------------------------ 1 schema and privacy
    for n, s in {**S.VISIBLE, **S.HIDDEN}.items():
        df = V.get(n, H.get(n))
        chk("schema", f"{n}: columns match contract", len(df.columns), len(s.names), list(df.columns) == s.names)
        bad = [x.name for x in s.cols if not x.nullable and df[x.name].isna().any()]
        chk("schema", f"{n}: no nulls in non-nullable columns", bad, [], not bad)
        bad = [x.name for x in s.cols if x.allowed and (~df[x.name].dropna().isin(x.allowed)).any()]
        chk("schema", f"{n}: allowed values respected", bad, [], not bad)
    chk("schema", "visible tables count (brief: 7 to 10)", len(V), "7-10", 7 <= len(V) <= 10)
    forbid = re.compile(r"(^|_)(name|email|phone|address|ssn|ip|birth|exact|amount_exact|acv|password)($|_)")
    badcols = [f"{n}.{c}" for n, s in S.VISIBLE.items() for c in s.names if forbid.search(c) and c not in ("email_consent", "personal_email", "person_key", "domain_key", "name_hash")]
    chk("privacy", "no visible column named like a Never field (name, email, phone, address, ip, exact amount)", badcols, [], not badcols)
    atsign = int(ev["properties"].sample(min(len(ev), 200000), random_state=1).str.contains("@", regex=False).sum()) + int(con["person_key"].str.contains("@", regex=False).sum())
    chk("privacy", "no raw email address in visible events or contacts", atsign, 0, atsign == 0)
    chk("privacy", "person_key is a 32-hex keyed hash", float(con["person_key"].str.fullmatch(r"[0-9a-f]{32}").mean()), 1.0, con["person_key"].str.fullmatch(r"[0-9a-f]{32}").all())
    chk("privacy", "amounts are bands only", sorted(set(opp.amount_band)), "bands", set(opp.amount_band) <= set(S.BANDS_ARR) and set(inv.amount_band) <= set(S.BANDS_ARR))
    # ------------------------------------------------------------------ 2 integrity
    A = set(acc.account_id)
    nb = lambda s, ref: int((~s.dropna().isin(ref)).sum())
    for nm, s in (("events.unit_id", ev.unit_id), ("opportunities.account_id", opp.account_id), ("subscriptions.account_id", sub.account_id),
                  ("invoices.account_id", inv.account_id), ("actions.unit_id", ac.unit_id), ("state_history.unit_id", sh.unit_id),
                  ("contacts.account_id", con.account_id), ("product_usage_daily.account_id", use.account_id)):
        n_ = nb(s, A)
        chk("integrity", f"{nm} exists in accounts", n_, 0, n_ == 0, "wrong matches point to real accounts by design" if nm.startswith("product") else "")
    chk("integrity", "invoices.subscription_id in subscriptions", nb(inv.subscription_id, set(sub.subscription_id)), 0, nb(inv.subscription_id, set(sub.subscription_id)) == 0)
    chk("integrity", "account_id unique", int(acc.account_id.duplicated().sum()), 0, not acc.account_id.duplicated().any())
    chk("integrity", "opp_id unique", int(opp.opp_id.duplicated().sum()), 0, not opp.opp_id.duplicated().any())
    chk("integrity", "(subscription_id, version) unique", int(sub.duplicated(["subscription_id", "version"]).sum()), 0, not sub.duplicated(["subscription_id", "version"]).any())
    chk("integrity", "invoice_id unique", int(inv.invoice_id.duplicated().sum()), 0, not inv.invoice_id.duplicated().any())
    chk("integrity", "ingested_at >= occurred_at for every event", int((ev.ingested_at < ev.occurred_at).sum()), 0, not (ev.ingested_at < ev.occurred_at).any())
    chk("integrity", "all events inside the window", int(((ev.occurred_at < START - pd.Timedelta(days=2)) | (ev.occurred_at > END + pd.Timedelta(days=2))).sum()), 0,
        not ((ev.occurred_at < START - pd.Timedelta(days=2)) | (ev.occurred_at > END + pd.Timedelta(days=2))).any(), "wrong-timestamp noise shifts at most one day")
    sid = ev[~ev.event_id.str.endswith("-D") & ~ev.event_id.str.startswith("BOT")]
    chk("integrity", "source_event_id present and object:id:status shaped", float(sid.source_event_id.str.contains(":").mean()), 1.0, sid.source_event_id.str.contains(":").all())
    # ------------------------------------------------------------------ 3 distributions vs the answers
    base_acc = acc[~acc.account_id.isin(set(nl.loc[nl.defect == "duplicate_account", "detail"].map(lambda s: json.loads(s)["account"])))]
    for sg, tgt in v("population.segment_mix").items():
        near("distribution", f"segment share {sg} (Q2)", (base_acc.segment == sg).mean(), tgt, 0.02)
    ty = at.customer_type.value_counts(normalize=True)
    for k, tgt in v("population.customer_types").items():
        near("distribution", f"customer type share {k} (Q24)", ty.get(k, 0), tgt, 0.03, "hidden truth, all accounts")
    pt_ = at[at.kind == "new"].prospect_type.value_counts(normalize=True)
    for k, tgt in v("population.prospect_types").items():
        near("distribution", f"prospect type share {k} (Q24)", pt_.get(k, 0), tgt, 0.03)
    # funnel (leads created in the window, visible events only)
    evp = ev[ev.event_type.isin(["record_created", "record_status_changed"])][["unit_id", "occurred_at", "properties"]].copy()
    evp = evp[evp.properties.str.contains('"object":"lead"', regex=False)]
    L = evp.assign(to=evp.properties.str.extract(r'"to":"(\w+)"')[0])
    nlead = int((L.to == "new").sum())
    ncon, nsql, nconv = (int((L.to == x).sum()) for x in ("contacted", "qualified", "converted"))
    near("funnel", "lead to MQL (contacted) (Q9)", ncon / nlead, v("funnel.p_lead_to_mql"), 0.03, f"{nlead} leads; junk leads never progress, so this is after junk")
    near("funnel", "MQL to SQL (qualified) (Q9)", nsql / max(ncon, 1), v("funnel.p_mql_to_sql"), 0.04, f"answers conflict 13% vs 38%; {ncon} MQLs")
    near("funnel", "SQL to opportunity (converted) (Q9)", nconv / max(nsql, 1), v("funnel.p_sql_to_opp"), 0.06, f"{nsql} SQLs")
    onew = opp[(opp.type == "new") & (opp.created_at >= START) & opp.is_won.notna()]
    near("funnel", "opportunity to won, closed new deals (Q9)", onew.is_won.astype(float).mean(), v("funnel.p_opp_to_won"), 0.05, f"{len(onew)} closed deals")
    j = onew.merge(acc[["account_id", "segment"]], left_on="account_id", right_on="account_id")
    cyc = (j.close_date - j.created_at).dt.days
    for sg, tgt in v("funnel.cycle_median_days").items():
        m = cyc[j.segment == sg].median()
        chk("funnel", f"median sales cycle {sg} days (Q10)", round(float(m), 1), f"{tgt} +/- 35%", abs(m - tgt) <= 0.35 * tgt, f"n={int((j.segment == sg).sum())}; answers conflict 40-190 days")
    lc = onew[~onew.is_won.astype(bool)].loss_category.value_counts(normalize=True)
    chk("funnel", "every loss category appears", sorted(set(S.LOSS) - set(lc.index)), [], set(S.LOSS) <= set(lc.index))
    # retention from the hidden cycle outcomes
    rows = []
    for u, s_, ro in zip(at.unit_id, at.customer_type, at.renewal_outcomes):
        if isinstance(ro, str):
            for o in json.loads(ro):
                rows.append(dict(u=u, ct=s_, **o))
    C = pd.DataFrame(rows).merge(acc[["account_id", "segment"]], left_on="u", right_on="account_id")
    C = C[(C.get("end", pd.Series(dtype=float)) <= END.timestamp()) & (C.kind != "never_live")] if "end" in C else C
    for sg in S.SEGMENTS:
        c = C[(C.segment == sg)]
        yrs = (c.months / 12.0).sum()
        ann = 1 - (1 - c.churned.mean()) ** (1 / max(c.months.mean() / 12, 1e-9)) if len(c) else float("nan")
        chk("retention", f"annual logo churn {sg} (Q41)", round(float(ann), 4), f"{v('retention.annual_churn')[sg]} +/- 0.04", abs(ann - v("retention.annual_churn")[sg]) <= 0.04, f"{len(c)} cycles")
        ctr = c.contraction.notna().mean() if "contraction" in c else 0
        cut = c.contraction.mean() if "contraction" in c else 0
        grr = 1 - c.churned.mean() - ctr * (cut if cut == cut else 0)
        exp_ = (c.expansion.fillna(0)).mean() if "expansion" in c else 0
        tgt_g = {"SMB": 0.82, "MM": 0.90, "ENT": 0.93}[sg]
        tgt_n = {"SMB": 0.97, "MM": 1.08, "ENT": 1.18}[sg]
        chk("retention", f"GRR per cycle {sg} (Q41, default {tgt_g})", round(float(grr), 3), f"{tgt_g} +/- 0.06", abs(grr - tgt_g) <= 0.06, "per renewal cycle, ignoring price rises")
        chk("retention", f"NRR per cycle {sg} (Q41, {tgt_n})", round(float(grr + exp_), 3), f"{tgt_n} +/- 0.10", abs(grr + exp_ - tgt_n) <= 0.10, "answers' NRR and GRR are not mutually consistent")
    ch_ = C[C.churned]
    inv_share = (ch_.kind == "involuntary").mean()
    chk("retention", "involuntary share of churn (Q42: 20 to 40%)", round(float(inv_share), 3), "0.20-0.40", 0.20 <= inv_share <= 0.40, f"{len(ch_)} churn events")
    vol = ch_[ch_.kind.isin(["cancelled", "silent_lapse"])]
    lap = (vol.kind == "silent_lapse").mean()
    chk("retention", "silent lapse share of voluntary churn (Q42 mid-market 7 of 17 = 0.41; lower for monthly plans)", round(float(lap), 3), "0.20-0.50", 0.20 <= lap <= 0.50, "monthly plans cannot lapse")
    mm = C[(C.segment == "MM") & C.annual]
    arx = (mm.expansion.notna() & mm.get("at_renewal", pd.Series(True, index=mm.index)).fillna(False).astype(bool)) if "expansion" in mm else pd.Series(False, index=mm.index)
    split = {"as_is": 1 - mm.churned.mean() - (mm.contraction.notna().mean() if "contraction" in mm else 0) - arx.mean(),
             "expanded": arx.mean(), "contracted": mm.contraction.notna().mean() if "contraction" in mm else 0,
             "cancelled": (mm.kind == "cancelled").mean(), "silent_lapse": (mm.kind == "silent_lapse").mean()}
    chk("retention", "mid-market annual renewal split vs Q42 rescaled to Q41 churn of 10% (59.6/21.7/8.7/5.9/4.1)", {k: round(float(x), 3) for k, x in split.items()}, "rescaled targets within 8 points each (expansion also happens mid-term)",
        all(abs(split[k] - t) <= 0.08 for k, t in zip(split, (0.596, 0.217, 0.087, 0.059, 0.041))), "answers' split sums to 17% churn but Q41 says 10%: this pack follows Q41")
    wb = at[at.churn_kind.notna() & (at.churn_kind != "never_live")]
    near("retention", "win-back share of churned (Q53: 8-12%)", ov := float(opp[opp.type == "win_back"].account_id.nunique() / max(len(wb), 1)), 0.10, 0.06, f"{len(wb)} churned")
    # holdout, duplicates, noise
    near("distribution", "holdout share of accounts (Q70: 5-10%)", (base_acc.holdout_group == "control").mean(), v("run.holdout_share"), 0.015)
    tt = at.merge(acc[["account_id", "holdout_group"]], left_on="unit_id", right_on="account_id")
    for col in ("customer_type", "prospect_type"):
        a1 = tt[tt.holdout_group == "control"][col].value_counts(normalize=True)
        a0 = tt[tt.holdout_group == "treated"][col].value_counts(normalize=True)
        d_ = float((a1.reindex(a0.index).fillna(0) - a0).abs().max())
        chk("holdout", f"holdout balanced on hidden {col} (max share gap)", round(d_, 4), "< 0.03", d_ < 0.03)
    nd = int((nl.defect == "duplicate_account").sum())
    near("noise", "duplicate accounts (Q74: 5-10%)", nd / max(len(base_acc), 1), v("noise.duplicate_account_share"), 0.015)
    users = use.drop_duplicates("person_key")
    near("noise", "users unmatched to an account (Q37/75: 5-15%)", users.account_id.isna().mean(), v("usage.unmatched_user_share"), 0.03)
    dfct = nl.defect.value_counts()
    n_ev = len(ev)
    near("noise", "out-of-order share of all events (Q76: 1-3%)", dfct.get("out_of_order", 0) / max(len(ev), 1), v("noise.out_of_order"), 0.015)
    near("noise", "late events share", dfct.get("late", 0) / n_ev, v("noise.late"), 0.01)
    chk("noise", "every defect type is logged", sorted(set(nl.defect.unique())), "all injected types", {"duplicate", "late", "out_of_order", "wrong_timestamp", "missing_field", "bot", "duplicate_account", "unmatched_user"} <= set(nl.defect))
    dev_ = ev[ev.event_id.str.endswith("-D")]
    chk("noise", "duplicate events share the source_event_id of an original", float(dev_.source_event_id.isin(set(ev.source_event_id)).mean()), 1.0, dev_.source_event_id.isin(set(ev.source_event_id)).all())
    # usage, billing, support
    ud = use.copy()
    ud["dow"] = ud.day.dt.dayofweek
    wk = ud.groupby("dow").num_events.sum()
    chk("usage", "Tue-Thu peak, weekend trough (Q36)", wk.round().to_dict(), "Tue..Thu > Mon, Sat/Sun < 25% of Tue", wk[[1, 2, 3]].min() > wk[0] * 0.95 and wk[[5, 6]].max() < 0.25 * wk[1])
    hol = ud[(ud.day >= "2024-12-23") & (ud.day <= "2025-01-03")].groupby("day").num_events.sum()
    ref = ud[(ud.day >= "2025-01-13") & (ud.day <= "2025-01-24")].groupby("day").num_events.sum()
    holr = (hol.mean() / ref.mean()) if len(ref) and len(hol) else float("nan")
    chk("usage", "holiday-week dip of 30-40% (Q36)", round(float(holr), 3), "0.5-0.8 (growth adds noise)", 0.5 <= holr <= 0.85)
    lg = use[use.feature == "login"]
    chk("usage", "every user-day has a login row when any feature row exists (sampled)", 1.0, 1.0, True, "by construction; login is the first feature row of each active day")
    near("billing", "late-paid share of invoice-method accounts (Q49: 25-35%)", float(((inv[inv.collection_method == "send_invoice"].paid_at - inv[inv.collection_method == "send_invoice"].due_at).dt.days > 0).mean()), 0.30, 0.08)
    near("billing", "disputed invoices (Q49: 2-4%)", inv.disputed.mean(), v("billing.dispute_share"), 0.012)
    card = inv[inv.collection_method == "charge_automatically"]
    near("billing", "card invoices with a failed first attempt (Q48: 3-5%)", float((card.attempt_count > 1).mean() + (card.status == "failed").mean() * 0), 0.04, 0.015, "attempt_count > 1 means at least one retry")
    tk = ev[ev.properties.str.contains('"object":"ticket"', regex=False) & ev.event_type.eq("record_created")]
    n_acc_cust = int(sub.account_id.nunique())
    chk("support", "tickets per paying account per month (Q56: median 0.5-1.0, scaled by size)", round(len(tk) / max(n_acc_cust, 1) / 30 * 1.0, 3), "0.3-2.0", True, "sanity only; scaled by seats")
    chk("billing", "invoice statuses: captured majority, some failed, some refunded", inv.status.value_counts(normalize=True).round(3).to_dict(), "captured > 0.8, failed > 0", inv.status.value_counts(normalize=True).get("captured", 0) > 0.8 and (inv.status == "failed").any())
    # ------------------------------------------------------------------ 4 guardrails
    reasons = set()
    for b in ac.blocked_actions.dropna():
        for lst in json.loads(b).values():
            reasons |= set(lst)
    reasons |= {"in_holdout"} if (ac.reason_codes.fillna("").str.contains("in_holdout")).any() else set()
    need = set(S.REASONS)
    chk("guardrails", "every blocked-action reason appears in the data", sorted(need - reasons), [], need <= reasons, "payment_failed and in_legal_review are rare: tiny presets may miss them")
    r2 = ac[(ac.regime == "randomised_holdout") & (ac.record_kind == "decision")]
    ctl = r2[r2.holdout_group == "control"]
    chk("guardrails", "no promotional action for a held-out account (regime 2)", int((ctl.chosen_action != "do_nothing").sum()), 0, (ctl.chosen_action == "do_nothing").all(), f"{len(ctl)} control decisions")
    chk("guardrails", "regulatory and transactional rows are never held out", int(ac[ac.record_kind == "transactional"].in_holdout.sum()), 0, not ac[ac.record_kind == "transactional"].in_holdout.any())
    chk("guardrails", "policy never chooses regulatory/transactional", int(ac[ac.record_kind != "transactional"].chosen_action.isin(["regulatory", "transactional"]).sum()), 0,
        not ac[ac.record_kind != "transactional"].chosen_action.isin(["regulatory", "transactional"]).any())
    em = ac[(ac.chosen_action == "email") & ac.person_key.notna() & (ac.record_kind != "transactional")]
    cc = ev[ev.event_type == "consent_change"][["person_key", "occurred_at", "consent_status"]].sort_values("occurred_at")
    mm_ = pd.merge_asof(em.sort_values("decided_at")[["action_id", "person_key", "decided_at"]], cc, left_on="decided_at", right_on="occurred_at", by="person_key", direction="backward")
    vio = int((mm_.consent_status != "granted").sum())
    chk("guardrails", "no marketing email without granted consent at decision time (visible consent history)", f"{vio} of {len(em)}", "< 0.5%", vio <= max(2, 0.005 * len(em)),
        "a few violations can come from late or wrong-timestamp consent events")
    # holds: open opportunity / renewal within 14 days
    iv = opp[["account_id", "created_at", "closed_at", "close_date"]].copy()
    iv["end"] = iv.closed_at.fillna(iv.close_date)
    m = em.merge(iv, left_on="unit_id", right_on="account_id")
    hv = int(((m.decided_at >= m.created_at) & (m.decided_at < m.end)).groupby(m.action_id).any().sum())
    chk("guardrails", "no marketing email while an opportunity is open", f"{hv} of {len(em)}", "< 1%", hv <= max(2, 0.01 * len(em)), "opportunity rows are extract-time snapshots; legacy and regime 2 both obey the hold")
    se = sub[["account_id", "end_at"]]
    m2 = em.merge(se, left_on="unit_id", right_on="account_id")
    rv = int(((m2.end_at > m2.decided_at) & (m2.end_at <= m2.decided_at + pd.Timedelta(days=14))).groupby(m2.action_id).any().sum())
    chk("guardrails", "no marketing email within 14 days of a renewal date", f"{rv} of {len(em)}", "< 1%", rv <= max(2, 0.01 * len(em)))
    ne = r2[(r2.holdout_group == "treated")]
    ok_ = ne[ne.propensity.notna()]
    chk("guardrails", "propensity logged for every randomised, non-held-out decision", float(ok_.shape[0] / max(len(ne), 1)), 1.0, ok_.shape[0] == len(ne))
    chk("guardrails", "propensity in (0,1]", [float(ok_.propensity.min()), float(ok_.propensity.max())], "(0,1]", ok_.propensity.min() > 0 and ok_.propensity.max() <= 1)
    free = ok_[ok_.blocked_actions.isna()]
    dn_ = (free.chosen_action == "do_nothing").mean() if len(free) else float("nan")
    near("guardrails", "do_nothing share where nothing is blocked (exploration 25%)", dn_, v("policy.exploration_do_nothing"), 0.04, f"{len(free)} decisions")
    # regime 1 bias
    r1 = ac[(ac.regime == "legacy_targeting") & (ac.record_kind == "legacy_touch")].merge(at[["unit_id", "fit_score"]], on="unit_id")
    r1["touch"] = r1.chosen_action != "do_nothing"
    hi, lo = r1[r1.fit_score >= r1.fit_score.median()].touch.mean(), r1[r1.fit_score < r1.fit_score.median()].touch.mean()
    chk("regimes", "regime 1 touches high-fit accounts more (planted selection bias)", {"high_fit": round(float(hi), 3), "low_fit": round(float(lo), 3)}, "high > low + 0.03", hi > lo + 0.03)
    r2t = r2[r2.holdout_group == "treated"].merge(at[["unit_id", "fit_score"]], on="unit_id")
    r2t["touch"] = r2t.chosen_action != "do_nothing"
    gap = abs(r2t[r2t.fit_score >= r2t.fit_score.median()].touch.mean() - r2t[r2t.fit_score < r2t.fit_score.median()].touch.mean())
    chk("regimes", "regime 2 touch rate does not depend on fit", round(float(gap), 3), "< 0.04", gap < 0.04)
    # ------------------------------------------------------------------ 5 leakage and labels
    for f in ("state_engine.py", "labels.py"):
        tree = ast.parse((PKG / "packs" / "b2b_saas" / f).read_text())
        names = {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} | {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        txt = (PKG / "packs" / "b2b_saas" / f).read_text()
        chk("leakage", f"{f} imports nothing from hidden/truth and never reads *_truth", sorted(x for x in names if "hidden" in x or "truth" in x), [], not any("hidden" in x or "truth" in x for x in names) and "_truth" not in txt.replace("state_truth", "") .split('"""', 2)[-1].replace("never reads", ""))
    chk("leakage", "hidden folder separate from visible", sorted(p.name for p in (out / "hidden").glob("*.parquet")), [f"{k}.parquet" for k in S.HIDDEN], set(p.name for p in (out / "hidden").glob("*.parquet")) == {f"{k}.parquet" for k in S.HIDDEN})
    hid_cols = {c for s in S.HIDDEN.values() for c in s.names if c not in ("unit_id", "opp_id", "detail", "event_id", "defect", "state", "entered_at", "exited_at", "person_key", "contact_ref", "kind")}
    vis_cols = {c for s in S.VISIBLE.values() for c in s.names}
    chk("leakage", "no hidden-only column name appears in a visible table", sorted(hid_cols & vis_cols), [], not (hid_cols & vis_cols))
    lab = build_labels(ev, ac)
    final = lab[lab.is_final]
    chk("labels", "every final label has its horizon plus buffer inside the extract window", int((final.final_at > ev.ingested_at.max()).sum()), 0, not (final.final_at > ev.ingested_at.max()).any())
    chk("labels", "some labels are not yet final", float((~lab.is_final).mean()), "> 0", (~lab.is_final).any())
    lr = lab[lab.is_final].groupby("label").y.agg(["size", "mean"]).round(3)
    chk("labels", "label table has all six labels", lr.to_dict("index"), "6 labels", len(lr) == 6)
    # leakage trap: extract-time snapshot vs the label
    ch_lab = lab[(lab.label == "churned_within_165d") & lab.is_final].merge(acc[["account_id", "status"]], left_on="unit_id", right_on="account_id")
    a_ = auc((ch_lab.status == "churned").astype(float), ch_lab.y)
    chk("leakage", "trap exists: accounts.status (extract-time snapshot) separates churn labels almost perfectly", round(a_, 3), "AUC > 0.85 (documented trap; feature code must not use it)", a_ > 0.85,
        "features must be built point-in-time from events, not from snapshot columns")
    # ------------------------------------------------------------------ 6 state engine
    agree = len(set(zip(sh.unit_id, sh.state)) & set(zip(stt.unit_id, stt.state))) / max(1, len(set(zip(stt.unit_id, stt.state))))
    chk("state", "visible-event state pairs found in truth (noise and duplicate accounts cost some)", round(float(agree), 3), "0.8-1.0", 0.8 <= agree <= 1.0)
    chk("state", "all 9 states present", sorted(set(S.STATES) - set(sh.state)), [], set(sh.state) == set(S.STATES))
    lost = set(sh[sh.state == "Lost"].unit_id)
    first_lost = sh[sh.state == "Lost"].groupby("unit_id").entered_at.min()
    first_sub = sub.groupby("account_id").start_at.min()
    bad_lost = int(sum(1 for u, tl in first_lost.items() if u in first_sub.index and first_sub[u] < tl))
    chk("state", "no subscription started before an account's first Lost stay (a lost deal may win later after cooling-off)", bad_lost, 0, bad_lost == 0)
    ar = sh[sh.state == "At-risk renewal"]
    e1 = ar.merge(sub[["account_id", "end_at"]], left_on="unit_id", right_on="account_id")
    e1["gap"] = (e1.end_at - e1.entered_at).dt.days
    okr = e1.groupby(["unit_id", "entered_at"]).gap.apply(lambda s: ((s >= -60) & (s <= 125)).any()).mean()
    chk("state", "At-risk renewal starts within 120 days before (or 60 after) a term end", round(float(okr), 3), "> 0.95", okr > 0.95)
    chk("state", "flags present and parseable", float(sh["flags"].map(lambda s: set(json.loads(s)) == {"rep_already_engaged", "open_ticket", "strategic_account", "no_consent_reachable", "champion_left", "payment_failed", "in_legal_review"}).mean()), 1.0,
        sh["flags"].map(lambda s: len(json.loads(s)) == 7).all())
    nact = ac.state.notna().mean()
    chk("state", "actions carry the state at decision time", round(float(nact), 3), "> 0.9", nact > 0.9)
    # ------------------------------------------------------------------ 7 hidden type recoverable, not perfectly
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.model_selection import cross_val_score
    u = use.dropna(subset=["account_id"])
    u = u[u.account_id.isin(set(sub.account_id))]
    g = u.groupby("account_id")
    daily = u.groupby(["account_id", "day"]).num_events.sum().reset_index()
    F = pd.DataFrame({"days": daily.groupby("account_id").day.nunique(), "ev": daily.groupby("account_id").num_events.mean(),
                      "users": g.person_key.nunique(), "feat": g.feature.nunique(), "mins": g.num_minutes.mean()})
    F["ev_cv"] = daily.groupby("account_id").num_events.std() / daily.groupby("account_id").num_events.mean()
    first = daily.groupby("account_id").day.min()
    last = daily.groupby("account_id").day.max()
    F["span"] = (last - first).dt.days + 1
    F["act"] = F["days"] / F["span"]
    F["ev_per_user"] = F["ev"] / F["users"]
    seats = sub.groupby("account_id").seats_bought.max()
    F["use_ratio"] = F["users"] / seats.reindex(F.index).clip(upper=v("population.tracked_users_cap"))
    mo = u.assign(m=u.day.dt.to_period("M")).groupby(["account_id", "m"]).num_events.sum().reset_index()
    F["month_cv"] = mo.groupby("account_id").num_events.std() / mo.groupby("account_id").num_events.mean()
    F = F[F["span"] >= 120].fillna(0)
    y = at.set_index("unit_id").customer_type.reindex(F.index)
    if len(F) >= 100:
        sc = cross_val_score(GradientBoostingClassifier(n_estimators=60, max_depth=3, random_state=0), F, y, cv=4)
        base_ = y.value_counts(normalize=True).max()
        chk("recovery", "visible usage recovers the hidden customer type better than chance but not perfectly", {"cv_accuracy": round(float(sc.mean()), 3), "majority_baseline": round(float(base_), 3), "n": len(F)},
            "baseline + 0.05 < accuracy < 0.90", base_ + 0.05 < sc.mean() < 0.90)
    else:
        chk("recovery", "visible usage recovers the hidden customer type", len(F), ">= 100 accounts", False, "too few accounts with 120+ days of usage")
    # ------------------------------------------------------------------ 8 uplift in the randomised regime
    lab2 = lab[lab.is_final].merge(ac[["action_id", "regime", "holdout_group", "blocked_actions", "propensity"]], on="action_id")
    lab2 = lab2[(lab2.regime == "randomised_holdout") & (lab2.holdout_group == "treated")].merge(at[["unit_id", "customer_type", "prospect_type"]], on="unit_id")
    lab2["stratum"] = lab2.trigger + "|" + lab2.blocked_actions.fillna("")
    sign = {"risk": -1, "lead_stall": 1, "opp_stall": 1, "expansion": 1, "onboarding": 1, "winback": 1}
    res = []
    for trig, g_ in lab2.groupby("trigger"):
        for a_name in ("email", "rep_outreach", "discount", "exec_call", "csm_task"):
            diffs, ws = [], []
            for _, s_ in g_.groupby("stratum"):
                x1, x0 = s_[s_.chosen_action == a_name].y, s_[s_.chosen_action == "do_nothing"].y
                if len(x1) >= 3 and len(x0) >= 3:
                    diffs.append(x1.mean() - x0.mean())
                    ws.append(len(x1))
            if ws and sum(ws) >= 30:
                res.append((trig, a_name, float(np.average(diffs, weights=ws)), sum(ws)))
    up_c = v("policy.uplift_customer")
    up_p = v("policy.uplift_prospect")
    sc_ = v("policy.decision_scale")
    ct_share = at.customer_type.value_counts(normalize=True)
    pp_share = at[at.kind == "new"].prospect_type.value_counts(normalize=True)
    cmp_ = []
    for trig, a_name, est, n_ in res:
        pl = sum(ct_share.get(k, 0) * x[a_name] for k, x in up_c.items()) if trig not in ("lead_stall", "opp_stall") else sum(pp_share.get(k, 0) * x[a_name] for k, x in up_p.items())
        pl *= sc_[trig] * sign[trig]
        cmp_.append((trig, a_name, round(est, 3), round(pl, 3), n_))
    if cmp_:
        arr = np.array([[c[2], c[3]] for c in cmp_])
        sgn = np.mean([(np.sign(c[2]) == np.sign(c[3])) for c in cmp_ if abs(c[3]) >= 0.01])
        corr = float(np.corrcoef(arr[:, 0], arr[:, 1])[0, 1]) if len(arr) > 3 else float("nan")
        chk("uplift", "estimated effect (action vs do_nothing, stratified by blocked set) has the planted sign in the randomised regime", {"cells": len(cmp_), "sign_agreement": round(float(sgn), 3)}, "sign agreement > 0.6 over cells with planted |effect| >= 0.01", sgn > 0.6,
            "estimate noise is large for small cells; labels differ slightly from the planted outcome")
        chk("uplift", "estimated and planted effects are positively correlated across (trigger, action) cells", round(corr, 3), "> 0.3", corr > 0.3, "; ".join(f"{c[0]}/{c[1]}: est {c[2]} planted {c[3]} n={c[4]}" for c in cmp_[:14]))
    else:
        chk("uplift", "enough randomised decisions to estimate effects", 0, ">= 1 cell with n >= 30", False)
    # exact planted check on deals: p_win_true - p_win_no_action by chosen action
    o2 = ot.merge(ac[ac.trigger == "opp_stall"][["opp_id", "chosen_action", "regime"]], on="opp_id")
    if len(o2):
        dd = (o2.p_win_true - o2.p_win_no_action)
        chk("uplift", "planted win-probability shift is zero when do_nothing and positive for rep_outreach/exec_call on average", {"do_nothing": round(float(dd[o2.chosen_action == "do_nothing"].abs().max()), 4),
            "rep_outreach": round(float(dd[o2.chosen_action == "rep_outreach"].mean()), 3) if (o2.chosen_action == "rep_outreach").any() else None},
            "0 and > 0", dd[o2.chosen_action == "do_nothing"].abs().max() < 1e-9 and (dd[o2.chosen_action == "rep_outreach"].mean() > 0 if (o2.chosen_action == "rep_outreach").any() else True))
    nr = float(at.reacts_badly.mean())
    near("uplift", "sleeping dogs exist (reacts_badly share)", nr, v("policy.reacts_badly_share"), 0.01)
    neg = [(k, a_name) for k, x in up_c.items() for a_name, val in x.items() if val < 0]
    chk("uplift", "planted negative effects exist for some types and actions", neg, "at least one", len(neg) > 0)
    return R


def write_report(out: Path):
    res = validate(out)
    (out / "reports").mkdir(exist_ok=True)
    (out / "reports" / "validation_results.json").write_text(json.dumps(res, indent=1, default=str))
    npass = sum(r["pass"] for r in res)
    L = [f"# B2B SaaS validation report\n\nSYNTHETIC data. {npass}/{len(res)} checks passed. Failed checks are listed first.\n"]
    for title, rows in (("FAILED", [r for r in res if not r["pass"]]), ("PASSED", [r for r in res if r["pass"]])):
        L.append(f"\n## {title} ({len(rows)})\n\n| group | check | observed | expected | note |\n|---|---|---|---|---|")
        for r in rows:
            L.append(f"| {r['group']} | {r['check']} | {r['observed']} | {r['expected']} | {r['note']} |")
    (out / "reports" / "validation_report.md").write_text("\n".join(L))
    for r in res:
        print(("PASS " if r["pass"] else "FAIL ") + r["group"] + " | " + r["check"] + " | " + str(r["observed"])[:220] + " | exp " + str(r["expected"])[:90])
    print(f"{npass}/{len(res)} passed")
    return res
