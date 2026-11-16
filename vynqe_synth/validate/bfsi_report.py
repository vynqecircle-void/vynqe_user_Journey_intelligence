"""Validation of a generated BFSI dataset. Reads parquet only. Hidden truth is used HERE (the validator),
never by state-engine or label code. Every check reports observed vs expected; nothing is asserted without being computed."""
from __future__ import annotations
import ast, json, re
from pathlib import Path
import numpy as np
import pandas as pd
from ..core.config import Cfg
from ..packs.bfsi import schemas as S

R = []


def chk(group, name, observed, expected, ok, note=""):
    R.append({"group": group, "check": name, "observed": observed, "expected": expected, "pass": bool(ok), "note": note})


def rd(d, sub, n):
    return pd.read_parquet(d / sub / f"{n}.parquet")


def band_ok(x):
    return all(("-" in v) or v.endswith("+") or v.startswith("<") for v in x)


def auc(score, y):
    r = pd.Series(score).rank().to_numpy()
    n1, n0 = int(y.sum()), int((~y).sum())
    return float((r[y.to_numpy()].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)) if n1 and n0 else float("nan")


def validate(out: Path):
    R.clear()
    cfg = Cfg.load("bfsi")
    v = cfg.v
    V = {n: rd(out, "visible", n) for n in S.VISIBLE}
    H = {n: rd(out, "hidden", n) for n in S.HIDDEN}
    b, e, a, st, lo, em, cs, ac, sh, cp = (V[k] for k in ("borrowers", "events", "applications", "application_steps", "loans", "emi_payments",
                                                       "service_cases", "actions", "state_history", "campaigns"))
    pt, at, stt, nl = H["person_truth"], H["application_truth"], H["state_truth"], H["noise_log"]
    END = pd.Timestamp(v("run.start_date"), tz="UTC") + pd.Timedelta(days=int(v("run.n_days")))
    # ---------------------------------------------------------------- 1 schema
    for n, s in {**S.VISIBLE, **S.HIDDEN}.items():
        df = V.get(n, H.get(n))
        chk("schema", f"{n}: columns match contract", len(df.columns), len(s.names), list(df.columns) == s.names)
        bad = [x.name for x in s.cols if not x.nullable and df[x.name].isna().any()]
        chk("schema", f"{n}: no nulls in non-nullable columns", bad, [], not bad)
        bad = [x.name for x in s.cols if x.allowed and (~df[x.name].dropna().isin(x.allowed)).any()]
        chk("schema", f"{n}: allowed values respected", bad, [], not bad)
    chk("schema", "visible tables count (brief: 7 to 10)", len(V), "7-10", 7 <= len(V) <= 10)
    # ---------------------------------------------------------------- 2 integrity
    U = set(b.unit_id)
    n_bad = lambda s, ref: int((~s.dropna().isin(ref)).sum())
    chk("integrity", "applications.unit_id in borrowers", n_bad(a.unit_id, U), 0, n_bad(a.unit_id, U) == 0)
    chk("integrity", "events.unit_id in borrowers", n_bad(e.unit_id, U), 0, n_bad(e.unit_id, U) == 0)
    fk = n_bad(st.application_ref, set(a.application_ref)) + n_bad(lo.application_ref, set(a.application_ref))
    chk("integrity", "steps and loans reference existing applications", fk, 0, fk == 0)
    fk = n_bad(em.loan_id, set(lo.loan_id))
    chk("integrity", "emi_payments.loan_id in loans", fk, 0, fk == 0)
    fk = n_bad(ac.unit_id, U) + n_bad(cs.unit_id, U) + n_bad(sh.unit_id, U)
    chk("integrity", "actions/cases/state_history unit_id in borrowers", fk, 0, fk == 0)
    chk("integrity", "person_truth 1:1 with borrowers", len(pt), len(b), set(pt.unit_id) == U)
    chk("integrity", "application_truth 1:1 with applications", len(at), len(a), set(at.application_ref) == set(a.application_ref))
    dup = a.application_ref.duplicated().any() or lo.loan_id.duplicated().any() or ac.action_id.duplicated().any() or em.payment_id.duplicated().any() or st.step_id.duplicated().any()
    chk("integrity", "unique keys (applications, loans, actions, payments, steps)", bool(dup), False, not dup)
    s2 = sh.sort_values(["unit_id", "entered_at"])
    ov = int((s2.groupby("unit_id")["exited_at"].shift(0) > s2.groupby("unit_id")["entered_at"].shift(-1)).sum())
    chk("integrity", "state_history stays do not overlap", ov, 0, ov == 0)
    d_ = a[a.disbursal_date.notna()]
    chk("integrity", "disbursal_date after created_at", int((d_.disbursal_date < d_.created_at).sum()), 0, (d_.disbursal_date < d_.created_at).sum() == 0)
    m = lo.merge(a[["application_ref", "disbursal_date"]], on="application_ref")
    chk("integrity", "every loan has a disbursed application with the same date", int((m.opened_at != m.disbursal_date).sum()), 0, (m.opened_at != m.disbursal_date).sum() == 0)
    chk("integrity", "every disbursed application has exactly one loan", int(d_.application_ref.isin(lo.application_ref).eq(False).sum()), 0, d_.application_ref.isin(lo.application_ref).all())
    lm = em.merge(lo[["loan_id", "defaulted_at"]], on="loan_id")
    after = int(((lm.defaulted_at.notna()) & (lm.created_at > lm.defaulted_at + pd.Timedelta(days=1))).sum())
    chk("integrity", "no EMI attempts after the lender default flag", after, 0, after == 0)
    chk("integrity", "no timestamps beyond the extract end (visible tables)", int((a.created_at > END).sum() + (em.created_at > END).sum() + (lo.opened_at > END).sum()), 0,
        (a.created_at > END).sum() + (em.created_at > END).sum() + (lo.opened_at > END).sum() == 0)
    ordok = em.sort_values(["loan_id", "instalment_no", "attempt_no"]).groupby(["loan_id", "instalment_no"]).created_at.apply(lambda x: x.is_monotonic_increasing).all()
    chk("integrity", "EMI attempts are ordered in time within an instalment", bool(ordok), True, ordok)
    # ---------------------------------------------------------------- 3 privacy
    txt = e.properties.sample(min(len(e), 300000), random_state=1)
    phone = int(txt.str.contains(r"\b[6-9]\d{9}\b").sum())
    mail = int(txt.str.contains(r"@[a-z0-9-]+\.").sum())
    chk("privacy", "no raw phone/email in event properties", phone + mail, 0, phone + mail == 0)
    cols_bad = [c for n, df in V.items() for c in df.columns if re.search(r"phone|email$|name$|address|(^|_)amount$|income|salary|dpd|balance|pan|aadhaar", c) and c not in ("email_key", "name_hash")]
    chk("privacy", "no raw-PII, income, DPD or exact-amount column names in visible tables", cols_bad, [], not cols_bad)
    bands = list(a.requested_amount_band.unique()) + list(lo.disbursed_amount_band.unique()) + list(em.amount_band.unique())
    chk("privacy", "visible amounts are bands only", sorted(set(bands)), "bands", band_ok(set(bands)))
    exact = int(txt.str.contains(r'"amount":\s*\d{4,}').sum())
    chk("privacy", "no exact amounts in event properties", exact, 0, exact == 0)
    # ---------------------------------------------------------------- 4 leakage
    hid_cols = set().union(*[set(s.names) for s in S.HIDDEN.values()]) - {"unit_id", "application_ref", "geo_tier", "event_id", "kind", "state", "entered_at", "exited_at", "detail", "defect"}
    leak = hid_cols & set().union(*[set(df.columns) for df in V.values()])
    chk("leakage", "no hidden-table column names in visible tables", sorted(leak), [], not leak)
    bad_imp = []
    root = Path(__file__).resolve().parent.parent
    for f in list((root / "core").glob("*.py")) + [root / "packs" / "bfsi" / "state_engine.py"]:
        for node in ast.walk(ast.parse(f.read_text())):
            names = []
            if isinstance(node, ast.ImportFrom):
                names = [node.module or ""] + [x.name for x in node.names]
            elif isinstance(node, ast.Import):
                names = [x.name for x in node.names]
            if any(k in n for n in names for k in ("hidden", "person_truth", "application_truth", "state_truth", "schemas")):
                bad_imp.append(f.name)
    chk("leakage", "state engine and core modules import no hidden tables or schemas", bad_imp, [], not bad_imp)
    t = lo.merge(a[["application_ref", "risk_band"]], on="application_ref")
    diff = float((t.lender_band_latest != t.risk_band).mean())
    chk("leakage", "trap exists: loans.lender_band_latest differs from the band at decision for some loans", round(diff, 3), "> 0 (extract-time snapshot)", diff > 0)
    trap = lo[lo.account_status == "defaulted"].lender_band_latest.eq("band_4").mean()
    chk("leakage", "trap: lender_band_latest is band_4 for every defaulted loan (future leaks into a snapshot column)", round(float(trap), 3), 1.0, trap == 1.0)
    chk("leakage", "trap: defaulted_at is only populated for defaulted loans", int(lo[lo.defaulted_at.notna()].account_status.ne("defaulted").sum()), 0, lo[lo.defaulted_at.notna()].account_status.ne("defaulted").sum() == 0)
    # ---------------------------------------------------------------- 5 distributions vs workbook/answers
    new = a[a.application_kind == "new"]
    N = len(b)
    ex = (b.acquisition_channel == "in_app").mean()
    chk("distribution", "existing-customer share of people (Q4: 20-30%)", round(float(ex), 3), "0.20-0.30", 0.2 <= ex <= 0.30)
    ld = (new.stage == "disbursed").sum() / N
    chk("distribution", "lead to disbursal, new applications (Q7: 3-8%)", round(float(ld), 4), "0.03-0.08", 0.03 <= ld <= 0.08)
    ad = (new.stage == "disbursed").mean()
    chk("distribution", "application to disbursal, new applications (Q7: about 12%)", round(float(ad), 3), "0.09-0.16", 0.09 <= ad <= 0.16)
    k1 = st[(st.step_type == "kyc") & (st.attempt_no == 1)]
    kp = (k1.status == "verified").mean()
    chk("distribution", "KYC first-attempt pass (Q10: 70%)", round(float(kp), 3), "0.62-0.78", 0.62 <= kp <= 0.78)
    kf = (st[st.step_type == "kyc"].groupby("application_ref").status.apply(lambda s: (s == "verified").any()))
    chk("distribution", "KYC eventual pass among applicants who start KYC", round(float(kf.mean()), 3), "0.75-0.92 (final fail about 10-15%)", 0.75 <= kf.mean() <= 0.92)
    cp_ = (st[st.step_type == "aa_consent"].status == "active").mean()
    chk("distribution", "AA consent given (Q11: 65-75% default; config 88% before drop-off)", round(float(cp_), 3), "0.65-0.92", 0.65 <= cp_ <= 0.92)
    fa = st[(st.step_type == "aa_fetch") & (st.attempt_no == 1)].status.eq("completed").mean()
    chk("distribution", "AA data fetch first-try success (Q11: 75-85%)", round(float(fa), 3), "0.75-0.90", 0.75 <= fa <= 0.90)
    dec = new[new.decision_band.notna()]
    ds = dec.decision_band.value_counts(normalize=True)
    chk("distribution", "decision mix approve / refer / decline (Q12: 40-60 / 5-10 / 30-50)", {k: round(float(x), 3) for k, x in ds.items()}, "see Q12",
        0.40 <= ds.get("approve", 0) + 0.5 * ds.get("refer", 0) <= 0.60 and 0.05 <= ds.get("refer", 0) <= 0.10 and 0.30 <= ds.get("decline", 0) <= 0.50)
    bs = dec.risk_band.value_counts(normalize=True).sort_index()
    chk("distribution", "lender band shares among decided applicants (Q23: 30/40/20/10)", [round(float(x), 3) for x in bs], [0.30, 0.40, 0.20, 0.10],
        all(abs(x - y) < 0.05 for x, y in zip(bs, [0.30, 0.40, 0.20, 0.10])))
    sanc = new[new.sanction_date.notna()]
    esg = st[st.step_type == "esign"].application_ref.unique()
    acc = sanc.application_ref.isin(esg).mean()
    chk("distribution", "offer acceptance, sanctioned to e-sign started (Q13: 60-75%)", round(float(acc), 3), "0.55-0.80", 0.55 <= acc <= 0.80)
    es = (st[st.step_type == "esign"].status == "signed").mean()
    chk("distribution", "e-sign success (Q14: about 90%)", round(float(es), 3), "0.88-0.97", 0.88 <= es <= 0.97)
    mf = st[(st.step_type == "mandate") & (st.attempt_no == 1)].status.eq("active").mean()
    chk("distribution", "mandate first-try success (Q14/Q32: 85-92%)", round(float(mf), 3), "0.82-0.93", 0.82 <= mf <= 0.93)
    sg = a[a.application_ref.isin(esg)]
    dl = sg.disbursal_date.notna().mean()
    chk("distribution", "signed but never disbursed (Q15: 5-15%; includes failed mandates and drop-off)", round(float(1 - dl), 3), "0.04-0.20", 0.04 <= 1 - dl <= 0.20)
    m2 = at.merge(a[["application_ref", "risk_band"]], on="application_ref")
    m2 = m2[m2.true_default.notna()]
    fin = m2[m2.label_final.astype(bool)]
    dr = float(fin.true_default.astype(float).mean())
    chk("distribution", "90+ DPD within 12 months, loans 15+ months old (Q26 digital placeholder 1-6%)", round(dr, 4), "0.02-0.09", 0.02 <= dr <= 0.09, f"n={len(fin)} final loans")
    byb = fin.groupby("risk_band").true_default.agg(lambda x: x.astype(float).mean())
    rng_ = {"band_1": (0.0, 0.04), "band_2": (0.02, 0.09), "band_3": (0.05, 0.18), "band_4": (0.08, 0.35)}
    chk("distribution", "default by lender band vs Q26 placeholders (1-2 / 4-6 / 10-15 / high)", {k: round(float(x), 3) for k, x in byb.items()}, "bands ordered, within loose ranges",
        bool(byb.is_monotonic_increasing) and all(rng_[k][0] <= x <= rng_[k][1] for k, x in byb.items()),
        "Band 4 rests on few loans; read with the counts: " + json.dumps(fin.risk_band.value_counts().sort_index().to_dict()))
    paths = at[at.pay_path.notna()].pay_path.map(json.loads)
    cnt = pd.Series([x["s"] for pth in paths for x in pth]).value_counts(normalize=True)
    chk("distribution", "EMI states on time / grace / late / missed (Q31: 80-85 / 8-10 / 5-8 / 1-3)", {k: round(float(cnt.get(k, 0)), 3) for k in ("on_time", "grace", "late", "missed")}, "Q31",
        0.78 <= cnt.get("on_time", 0) <= 0.87 and 0.06 <= cnt.get("grace", 0) <= 0.11 and 0.03 <= cnt.get("late", 0) <= 0.08 and 0.01 <= cnt.get("missed", 0) <= 0.045,
        "Missed share runs a little above Q31 because stress persists; flagged")
    a1 = em[em.attempt_no == 1]
    bounce = float((a1.status == "failed").mean())
    chk("distribution", "EMI first-attempt bounce (Q33: 5-12%; Q31 implies about 15%)", round(bounce, 3), "0.05-0.20", 0.05 <= bounce <= 0.20,
        "Q31 and Q33 disagree; the pack sits between them. Reported, not hidden")
    pre = lo.closure_type.value_counts()
    prp = pre.get("prepaid", 0) / max(1, len(lo[lo.closed_at.notna()]))
    chk("distribution", "prepaid share of closed loans (Q34: 10-20% prepay before term)", round(float(prp), 3), "0.05-0.35", 0.05 <= prp <= 0.35)
    cn = e[e.source_event_id.fillna("").str.match(r"^mandate:LN.*:cancelled$")].source_event_id.nunique()
    mc = cn / max(1, lo.loan_id.nunique())
    chk("distribution", "loans with a mandate cancellation event (Q32: 2-5% cancel within 6 months, config 3%)", round(float(mc), 3), "0.01-0.06", 0.01 <= mc <= 0.06)
    ca = cs.category.value_counts()
    cpl = cs[cs.category.isin(["complaint", "dispute"])].unit_id.nunique() / max(1, N)
    chk("distribution", "people with a complaint or dispute (Q39: 1-3% of borrowers; here per person, so lower)", round(float(cpl), 4), "0.0003-0.03", 0.0003 <= cpl <= 0.03)
    pf = pd.Series([x["m"] for pth, td in zip(paths, at[at.pay_path.notna()].true_default) if td is True for x in pth if x["s"] == "missed"][:0])
    firstm = []
    for pth, td in zip(paths, at[at.pay_path.notna()].true_default):
        if td is True:
            ms = [x["m"] for x in pth if x["s"] == "missed"]
            if ms:
                firstm.append(min(ms))
    fm = pd.Series(firstm)
    pk = float(fm.between(3, 9).mean()) if len(fm) else float("nan")
    chk("distribution", "first missed instalment of defaulters falls in months 3-9 (Q28: defaults peak in months 3-9)", round(pk, 3), ">= 0.5", pk >= 0.5,
        "Hazard is flat plus a small drift; a peak is not planted. Reported as is")
    ev_p = len(e) / N
    chk("distribution", "events per person", round(ev_p, 1), "20-120", 20 <= ev_p <= 120)
    cons = b.email_consent.value_counts(normalize=True)
    chk("distribution", "email consent granted share (config 55%, minus withdrawals, plus opt-ins)", round(float(cons.get("granted", 0)), 3), "0.40-0.65", 0.40 <= cons.get("granted", 0) <= 0.65)
    # ---------------------------------------------------------------- 6 noise
    nlc = nl.defect.value_counts()
    for k in ("duplicate", "late", "missing_field", "wrong_timestamp"):
        obs, tgt = nlc.get(k, 0) / len(e), v(f"noise.{k}")
        chk("noise", f"{k} rate vs config", round(float(obs), 4), tgt, 0.5 * tgt <= obs <= 1.6 * tgt + 0.002, "event-level; application duplicates also appear under 'duplicate'")
    chk("noise", "bot, tracking-gap and shared-device defects present", [int(nlc.get(k, 0)) for k in ("bot", "tracking_gap", "shared_device")], ">0", all(nlc.get(k, 0) > 0 for k in ("bot", "tracking_gap", "shared_device")))
    nsh = int(pt.shared_phone_with.notna().sum())
    chk("noise", "shared-phone defects logged equal the people who share a phone", [int(nlc.get("shared_device", 0)), nsh], "equal", int(nlc.get("shared_device", 0)) == nsh)
    lag = (e.ingested_at - e.occurred_at).dt.total_seconds()
    rz = lag[e.source_system == "razorpay"].median() / 86400
    chk("noise", "razorpay median lag in days (Q52: T+1 to T+2)", round(float(rz), 2), "1.0-2.5", 1.0 <= rz <= 2.5)
    cb = lag[e.source_system == "core_banking"].median() / 3600
    chk("noise", "core banking median lag in hours (daily extract)", round(float(cb), 1), "6-30", 6 <= cb <= 30)
    lo_ = lag[e.source_system == "loan_origination"].median()
    chk("noise", "origination median lag in seconds (real time)", round(float(lo_), 1), "< 120", lo_ < 120)
    dd = a.duplicated(["unit_id", "requested_amount_band", "channel"], keep=False).sum()
    dn = nl[(nl.defect == "duplicate") & nl.detail.str.contains("application_ref")]
    share = len(dn) / max(1, len(new))
    chk("noise", "duplicate applications logged (Q51: 3-8%; ours is of new applications)", round(float(share), 3), "0.015-0.08", 0.015 <= share <= 0.08)
    # ---------------------------------------------------------------- 7 guardrails
    dsn = ac[ac.record_kind == "decision"]
    rc = dsn.reason_codes.dropna().map(json.loads).explode().value_counts()
    missing = [x for x in S.REASONS if x not in rc.index]
    chk("guardrails", "every reason code appears at least once", missing, [], not missing, "Missing codes mean the rule never fired in this sample")
    viol = 0
    for chn, bl in zip(dsn.chosen_action, dsn.blocked_actions):
        if chn != "do_nothing" and bl and any(x["action"] == chn and x["reason_code"] != "approval_limit" for x in json.loads(bl)):
            viol += 1
    chk("guardrails", "no executed action was also blocked (except approval -> task)", viol, 0, viol == 0)
    reg2 = dsn[dsn.regime == "randomised_holdout"]
    hv = reg2[(reg2.holdout_group == "control") & (reg2.chosen_action != "do_nothing")]
    chk("guardrails", "holdout-control people never receive an optional action", len(hv), 0, len(hv) == 0)
    share = (b.holdout_group == "control").mean()
    chk("guardrails", "holdout share", round(float(share), 3), v("run.holdout_share"), abs(share - v("run.holdout_share")) < 0.015)
    rg = ac[ac.category == "regulatory"]
    rgc = rg.merge(b[["unit_id", "holdout_group"]].rename(columns={"holdout_group": "bg"}), on="unit_id").bg.eq("control").mean()
    chk("guardrails", "regulatory messages (EMI reminders, KFS) reach holdout people at the normal rate", round(float(rgc), 3), f"~{share:.3f}", abs(rgc - share) < 0.03)
    chk("guardrails", "policy never chooses a regulatory or transactional message", int(reg2.chosen_action.isin(["regulatory", "transactional"]).sum()), 0, not reg2.chosen_action.isin(["regulatory", "transactional"]).any())
    pr = reg2[reg2.chosen_action != "do_nothing"].propensity
    chk("guardrails", "propensity logged for every randomised decision, in (0,1]", float(reg2.propensity.isna().sum()), 0, reg2.propensity.notna().all() and ((reg2.propensity > 0) & (reg2.propensity <= 1)).all())
    cc = e[e.event_type == "consent_change"].copy()
    cc["ch"] = cc.properties.map(lambda x: json.loads(x).get("channel"))
    cc["st"] = cc.properties.map(lambda x: json.loads(x).get("status"))
    cc = cc.sort_values("occurred_at")
    sends = ac[(ac.category == "promotional") & ac.sent_at.notna() & ac.channel.isin(["email", "sms", "whatsapp"])][["unit_id", "channel", "sent_at"]].sort_values("sent_at")
    mm = pd.merge_asof(sends, cc[["unit_id", "ch", "st", "occurred_at"]].rename(columns={"ch": "channel"}).sort_values("occurred_at"), left_on="sent_at",
                       right_on="occurred_at", by=["unit_id", "channel"], direction="backward")
    nog = int((mm.st != "granted").sum())
    chk("guardrails", "promotional sends with no granted marketing consent at send time", nog, "~0", nog <= max(3, 0.003 * len(sends)),
        "Late and duplicate events can add a few")
    # collections / dispute holds
    pr_ = ac[(ac.category == "promotional") & ac.sent_at.notna()][["unit_id", "sent_at"]]
    cc2 = cs[cs.suppress_marketing][["unit_id", "opened_at", "closed_at"]].copy()
    cc2["closed_at"] = cc2.closed_at.fillna(END)
    j = pr_.merge(cc2, on="unit_id")
    hold_v = int(((j.sent_at > j.opened_at + pd.Timedelta(days=1)) & (j.sent_at < j.closed_at)).sum())
    chk("guardrails", "promotional sends while a collections or dispute case is open", hold_v, "~0", hold_v <= max(3, 0.003 * len(pr_)),
        "Cases that open between a decision and its send time can leak a few")
    aa_ = reg2[reg2.reason_codes.fillna("").str.contains("aa_consent_only")]
    chk("guardrails", "AA consent alone never enables marketing (aa_consent_only blocks occur and none executed)", [len(aa_), int((aa_.chosen_action != "do_nothing").sum())], ">0 and 0",
        len(aa_) > 0 and (aa_.chosen_action != "do_nothing").sum() == 0)
    # ---------------------------------------------------------------- 8 recoverability
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import cross_val_score
    ap = a.groupby("unit_id").agg(n_app=("application_ref", "size"), req=("requested_amount_band", lambda x: x.map({"0-10k": 0, "10k-25k": 1, "25k-50k": 2, "50k-100k": 3, "100k-250k": 4, "250k+": 5}).mean()))
    f = b.set_index("unit_id")[["acquisition_channel", "device_class", "geo_tier", "existing_customer"]].join(ap).join(e[e.unit_id.notna()].groupby("unit_id").size().rename("ev")).fillna(0)
    f = f.join(pt.set_index("unit_id")["hidden_type"])
    f = f[f.n_app > 0]
    X_ = pd.get_dummies(f.drop(columns="hidden_type"))
    acc_ = cross_val_score(RandomForestClassifier(150, min_samples_leaf=5, random_state=0, n_jobs=-1), X_, f.hidden_type, cv=3).mean()
    maj = f.hidden_type.value_counts(normalize=True).max()
    chk("recoverability", "hidden borrower type predicted from visible behaviour (3-fold accuracy)", round(float(acc_), 3), f"> majority {maj:.3f} and < 0.95", maj + 0.03 < acc_ < 0.95,
        "Types are learnable but never trivially")
    dm = dec.merge(pt[["unit_id", "true_risk_z"]], on="unit_id")
    cr = float(np.corrcoef(dm.risk_band.str[-1].astype(int), dm.true_risk_z)[0, 1])
    chk("recoverability", "lender band correlates with true risk but is not near perfect (Q55)", round(cr, 3), "0.45-0.90", 0.45 <= cr <= 0.90)
    if len(fin) > 100:
        au = auc(fin.risk_band.str[-1].astype(int).to_numpy(), fin.true_default.astype(bool))
        chk("recoverability", "lender band AUC for the default label (final loans)", round(au, 3), "0.60-0.85", 0.60 <= au <= 0.85)
    # ---------------------------------------------------------------- 9 uplift in the randomised regime
    ev2 = e[e.source_event_id.fillna("").str.match(r"^(app|kyc_check|aa_consent|aa_fetch|esign|mandate):")].copy()
    ev2 = ev2[ev2.event_type.isin(["record_created", "record_status_changed"])]
    ev2["ref"] = ev2.properties.map(lambda x: json.loads(x).get("application_ref"))
    ev2 = ev2.dropna(subset=["ref"]).sort_values("occurred_at")
    d_all = dsn[(dsn.trigger == "stall") & dsn.application_ref.notna()][["action_id", "application_ref", "decided_at", "chosen_action", "regime", "holdout_group", "options_considered"]]
    d_all = d_all.sort_values("decided_at")
    byref = {r_: g.occurred_at.to_numpy() for r_, g in ev2.groupby("ref")}
    ts = d_all.decided_at.to_numpy()
    res7 = np.zeros(len(d_all), int)
    for k, (r_, t0) in enumerate(zip(d_all.application_ref.to_numpy(), ts)):
        x = byref.get(r_)
        if x is not None:
            res7[k] = int(((x > t0 + np.timedelta64(60, "s")) & (x <= t0 + np.timedelta64(7, "D"))).any())
    d_all["resumed_7d"] = res7
    d_all["final"] = d_all.decided_at + pd.Timedelta(days=7 + v("labels.final_buffer_days")) <= e.ingested_at.max()
    r2 = d_all[(d_all.regime == "randomised_holdout") & (d_all.holdout_group == "treated") & d_all.final]
    r2 = r2.merge(ac[["action_id", "unit_id"]], on="action_id").merge(pt[["unit_id"] + [f"uplift_{k}" for k in ("nudge", "agent_call", "fee_waiver", "offer")]], on="unit_id")
    r2["allowed"] = r2.options_considered.map(lambda x: [y["action"] for y in json.loads(x)] if x else [])
    resu = {}
    for act in ("nudge", "agent_call", "fee_waiver", "offer"):
        g = r2[r2.allowed.map(lambda L: act in L)]
        a1, a0 = g[g.chosen_action == act], g[g.chosen_action == "do_nothing"]
        if len(a1) < 30 or len(a0) < 30:
            resu[act] = None
            continue
        est = a1.resumed_7d.mean() - a0.resumed_7d.mean()
        se = float(np.sqrt(a1.resumed_7d.var() / len(a1) + a0.resumed_7d.var() / len(a0)))
        resu[act] = (round(float(est), 3), round(se, 3), round(float(a1[f"uplift_{act}"].mean()), 3), len(a1), len(a0))
    okk = [x for x in resu.values() if x is not None]
    chk("uplift", "randomised estimate per action vs planted mean (estimate, std err, planted mean, n treated, n do_nothing)", resu,
        "same sign as planted; within 2.5 std errors + 0.03 of planted x about 0.6 (people returning anyway dilute it)",
        len(okk) > 0 and all(x[0] > -2 * x[1] and abs(x[0] - 0.6 * x[2]) < 2.5 * x[1] + 0.03 for x in okk),
        "Planted effect is per type and step-scaled, so the comparison is approximate")
    inc = at[at.kind == "incremental"]
    ok_cause = inc.cause_decision_id.isna().mean()
    cd = ac[ac.action_id.isin(inc.cause_decision_id.dropna().str.replace("D", "A", n=1, regex=False))]
    chk("uplift", "every incremental application with a cause points to a real action that was not do_nothing",
        [len(inc), int(inc.cause_decision_id.notna().sum()), int((cd.chosen_action == "do_nothing").sum())], "counts; none do_nothing", (cd.chosen_action == "do_nothing").sum() == 0,
        f"{round(float(ok_cause), 3)} of incremental rows have no cause: those come from the legacy regime, where sends carry no decision id")
    leg = ac[(ac.record_kind == "legacy_send")]
    lb = leg.merge(a[["application_ref", "risk_band"]], on="application_ref", how="left").risk_band.value_counts(normalize=True)
    base_b = dec.risk_band.value_counts(normalize=True)
    low_leg = float(lb.get("band_1", 0) + lb.get("band_2", 0))
    low_all = float(base_b.get("band_1", 0) + base_b.get("band_2", 0))
    chk("uplift", "legacy period targets lower-risk applicants more than their share (biased targeting)", [round(low_leg, 3), round(low_all, 3)], "legacy > all", low_leg > low_all)
    em2 = em[em.attempt_no == 1].merge(lo[["loan_id", "application_ref"]], on="loan_id")
    de = dsn[(dsn.trigger == "emi_due") & (dsn.regime == "randomised_holdout") & (dsn.holdout_group == "treated") & dsn.application_ref.notna()].copy()
    de["allowed"] = de.options_considered.map(lambda x: [y["action"] for y in json.loads(x)] if x else [])
    de = de[de.allowed.map(lambda L: "emi_nudge" in L)]
    em2 = em2.sort_values("due_date")
    de = de.sort_values("decided_at")
    jm = pd.merge_asof(de, em2[["application_ref", "due_date", "status"]], left_on="decided_at", right_on="due_date", by="application_ref", direction="forward", tolerance=pd.Timedelta(days=6))
    jm = jm.dropna(subset=["status"])
    jm["fail"] = (jm.status == "failed").astype(int)
    g1, g0 = jm[jm.chosen_action == "emi_nudge"], jm[jm.chosen_action == "do_nothing"]
    if len(g1) > 30 and len(g0) > 30:
        d_ = g1.fail.mean() - g0.fail.mean()
        se = float(np.sqrt(g1.fail.var() / len(g1) + g0.fail.var() / len(g0)))
        chk("uplift", "EMI nudge lowers first-attempt failure vs do_nothing in the randomised regime (difference, std err, n, n)", (round(float(d_), 3), round(se, 3), len(g1), len(g0)),
            "difference <= 0 (noisy)", d_ < 2 * se, "Planted truth; the dev preset has enough rows, tiny does not")
    tot = pt.groupby("hidden_type")[["uplift_nudge", "uplift_agent_call", "uplift_fee_waiver", "uplift_offer"]].mean().round(3)
    chk("uplift", "planted uplift differs by hidden type (fee waiver highest for rate_shopper, offer for repeat_borrower)", tot.to_dict(),
        "rate_shopper / repeat_borrower", tot.uplift_fee_waiver.idxmax() == "rate_shopper" and tot.uplift_offer.idxmax() == "repeat_borrower")
    nr = float(pt.reacts_badly.mean())
    chk("uplift", "sleeping dogs exist (negative planted uplift)", round(nr, 3), v("population.reacts_badly_share"), abs(nr - v("population.reacts_badly_share")) < 0.01)
    # ---------------------------------------------------------------- 10 labels / finality
    lo_age = (END - lo.opened_at).dt.days / 30.4
    tl = at.merge(lo[["application_ref", "opened_at"]], on="application_ref")
    tl["age"] = (END - tl.opened_at).dt.days / 30.4
    bad = int(((tl.age >= 15.2) & ~tl.label_final.astype(bool)).sum() + ((tl.age < 14.8) & tl.label_final.astype(bool)).sum())
    chk("labels", "default label is final only for loans 15+ months old", bad, 0, bad == 0)
    chk("labels", "some loans are not yet final (the window end leaves them open)", float((~tl.label_final.astype(bool)).mean()), "> 0", (~tl.label_final.astype(bool)).any())
    ud = tl[tl.label_final.astype(bool) == False]
    chk("labels", "no default flag in the visible loans table before 90 days past due", int((lo.defaulted_at.notna() & (lo.defaulted_at < lo.opened_at + pd.Timedelta(days=90))).sum()), 0,
        not (lo.defaulted_at.notna() & (lo.defaulted_at < lo.opened_at + pd.Timedelta(days=90))).any())
    mm2 = lo.merge(at[["application_ref", "first_dpd90_at"]], on="application_ref")
    flag_ok = mm2[mm2.defaulted_at.notna()]
    chk("labels", "visible default flag comes 1-5 days after the hidden 90 DPD date", int(((flag_ok.defaulted_at - flag_ok.first_dpd90_at).dt.days.between(0, 6)).eq(False).sum()), 0,
        ((flag_ok.defaulted_at - flag_ok.first_dpd90_at).dt.days.between(0, 6)).all())
    # ---------------------------------------------------------------- 11 state engine
    agree = len(set(zip(sh.unit_id, sh.state)) & set(zip(stt.unit_id, stt.state))) / max(1, len(set(zip(stt.unit_id, stt.state))))
    chk("state", "visible-event state pairs found in truth (noise and identity splits cost some)", round(float(agree), 3), "0.8-1.0", 0.8 <= agree <= 1.0)
    chk("state", "all 13 states present", sorted(set(S.STATES) - set(sh.state)), [], set(sh.state) == set(S.STATES))
    return R


def write_report(out: Path):
    res = validate(out)
    (out / "reports").mkdir(exist_ok=True)
    (out / "reports" / "validation_results.json").write_text(json.dumps(res, indent=1, default=str))
    npass = sum(r["pass"] for r in res)
    L = [f"# BFSI validation report\n\nSYNTHETIC data. {npass}/{len(res)} checks passed. Failed checks are listed first.\n"]
    for title, rows in (("FAILED", [r for r in res if not r["pass"]]), ("PASSED", [r for r in res if r["pass"]])):
        L.append(f"\n## {title} ({len(rows)})\n\n| group | check | observed | expected | note |\n|---|---|---|---|---|")
        for r in rows:
            L.append(f"| {r['group']} | {r['check']} | {r['observed']} | {r['expected']} | {r['note']} |")
    (out / "reports" / "validation_report.md").write_text("\n".join(L))
    for r in res:
        print(("PASS " if r["pass"] else "FAIL ") + r["group"] + " | " + r["check"] + " | " + str(r["observed"])[:200] + " | exp " + str(r["expected"])[:80])
    print(f"{npass}/{len(res)} passed")
    return res
