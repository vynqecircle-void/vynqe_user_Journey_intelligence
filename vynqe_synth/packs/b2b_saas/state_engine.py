"""B2B reference state engine. Reads EVENTS ONLY (never hidden truth). One stay per state.
States: Lead, Opportunity, Competitor displacement, Onboarding, Active, Expansion, At-risk renewal, Churned, Lost.
Flags: rep_already_engaged, open_ticket, strategic_account, no_consent_reachable, champion_left, payment_failed, in_legal_review."""
from __future__ import annotations
import json
import numpy as np
import pandas as pd
from ...core.state_engine import to_sec

DAY = 86400.0
KEEP = ("record_created", "record_status_changed", "outcome_confirmed", "consent_change")


def _loads(s):
    try:
        return json.loads(s)
    except Exception:
        return {}


def run_b2b_state_engine(ev: pd.DataFrame, accounts: pd.DataFrame, p: dict, unit_col: str = "unit_id", end_sec: float | None = None) -> pd.DataFrame:
    ev = ev[ev["event_type"].isin(KEEP) & ev[unit_col].notna()][[unit_col, "occurred_at", "event_type", "source_system", "properties"]].copy()
    ev["t"] = to_sec(ev["occurred_at"])
    if end_sec is None:
        end_sec = float(ev["t"].max()) if len(ev) else 0.0
    strategic = {}
    if accounts is not None and len(accounts):
        strategic = dict(zip(accounts["account_id"], accounts["strategic_flag"]))
    ev = ev.sort_values([unit_col, "t"], kind="mergesort")
    rows = []
    for u, g in ev.groupby(unit_col, sort=False):
        items = [(t, et, _loads(pr)) for t, et, pr in zip(g["t"], g["event_type"], g["properties"])]
        for st, t0, t1, by, fl in _unit_stays(items, bool(strategic.get(u, False)), p, end_sec):
            rows.append((u, st, t0, t1, by, fl))
    out = pd.DataFrame(rows, columns=["unit_id", "state", "entered_s", "exited_s", "entered_by", "flags"])
    out["entered_at"] = pd.to_datetime(out["entered_s"], unit="s", utc=True)
    out["exited_at"] = pd.to_datetime(out["exited_s"], unit="s", utc=True)
    out["rule_version"] = p["rule_version"]
    return out.drop(columns=["entered_s", "exited_s"]).sort_values(["unit_id", "entered_at"]).reset_index(drop=True)


def _unit_stays(items, strategic, p, end_sec):
    stays, cur = [], [None, None, None, None]
    F = dict(open=set(), last_act=-1e18, champ=False, payfail=set(), legal=False, consent={}, band="green", drop=False)
    S = dict(renewal_at=None, ever_sub=False, ever_lost=False, t_lost=None, timers=[])

    def flags(t):
        reach = any(v == "granted" for v in F["consent"].values())
        return json.dumps({"rep_already_engaged": bool(t - F["last_act"] <= 14 * DAY), "open_ticket": bool(F["open"]), "strategic_account": strategic,
                           "no_consent_reachable": not reach, "champion_left": F["champ"], "payment_failed": bool(F["payfail"]),
                           "in_legal_review": F["legal"]}, separators=(",", ":"))

    def setst(st, t, by):
        if cur[0] == st:
            return
        if cur[0] is not None and t > cur[1]:
            stays.append((cur[0], cur[1], t, cur[2], cur[3]))
        elif cur[0] is not None:
            pass
        cur[0], cur[1], cur[2], cur[3] = st, t, by, flags(t)

    def risk_eval(t, by="event"):
        ra = S["renewal_at"]
        if cur[0] in ("Active", "Expansion") and ra is not None and ra - p["at_risk_window_days"] * DAY <= t < ra + 60 * DAY:
            if F["band"] == "red" or F["drop"] or F["payfail"] or F["champ"]:
                setst("At-risk renewal", t, by)

    def run_timers(upto):
        while S["timers"] and min(S["timers"])[0] <= upto:
            tm = min(S["timers"])
            S["timers"].remove(tm)
            if tm[1] == "onb" and cur[0] == "Onboarding":
                setst("Active", tm[0], "clock")
            elif tm[1] == "risk":
                risk_eval(tm[0], "clock")

    for t, et, d in items + [(end_sec, "end", {})]:
        run_timers(t)
        if et == "end":
            break
        obj = d.get("object")
        to = d.get("to") or d.get("status")
        if et == "consent_change":
            F["consent"][d.get("id")] = d.get("status")
            continue
        if obj in ("lead", "registration", "demo_request"):
            if cur[0] is None and obj != "lead" or (obj == "lead" and to == "new" and cur[0] is None):
                setst("Lead", t, "event")
            elif obj == "lead" and to == "lost" and cur[0] == "Lead":
                setst_end = t
                stays.append((cur[0], cur[1], t, cur[2], cur[3]))
                cur[0] = None
        elif obj == "opportunity":
            typ = d.get("type")
            if to == "discount_offered":
                continue
            if et == "record_created":
                if typ in ("new", "win_back") and cur[0] in (None, "Lead", "Lost", "Churned"):
                    comp = d.get("competitor_flag") and d.get("incumbent_contract_end")
                    setst("Competitor displacement" if comp else "Opportunity", t, "event")
                    F["legal"] = False
                elif typ == "expansion" and cur[0] == "Active":
                    setst("Expansion", t, "event")
            elif to in ("evaluation", "proposal", "negotiation"):
                F["legal"] = bool(d.get("legal_review"))
            elif to in ("closed_won", "closed_lost"):
                F["legal"] = False
                if typ in ("new", "win_back") and to == "closed_lost" and cur[0] in ("Opportunity", "Competitor displacement"):
                    setst("Lost" if not S["ever_sub"] else "Churned", t, "event")
                elif typ == "expansion" and cur[0] == "Expansion":
                    setst("Active", t, "event")
        elif obj == "subscription":
            ra = d.get("renewal_at")
            if ra:
                S["renewal_at"] = pd.Timestamp(ra).timestamp()
            if et == "record_created":
                if cur[0] in (None, "Lead", "Opportunity", "Competitor displacement", "Churned", "Lost"):
                    setst("Onboarding", t, "event")
                    S["timers"].append((t + p["onboarding_max_days"] * DAY, "onb"))
                elif cur[0] in ("At-risk renewal", "Expansion"):
                    setst("Active", t, "event")
                S["ever_sub"] = True
                F["payfail"].clear()
                F["drop"] = False
                if S["renewal_at"]:
                    S["timers"].append((S["renewal_at"] - p["at_risk_window_days"] * DAY, "risk"))
            elif d.get("snapshot") and cur[0] is None:
                setst("Active", t, "event")
                S["ever_sub"] = True
                if S["renewal_at"]:
                    S["timers"].append((S["renewal_at"] - p["at_risk_window_days"] * DAY, "risk"))
            elif d.get("final") and to in ("cancelled", "expired", "past_due", "paused"):
                setst("Churned", t, "event")
        elif obj == "onboarding" and to == "first_value_reached" and cur[0] == "Onboarding":
            setst("Active", t, "event")
        elif obj == "health":
            order = {"red": 0, "yellow": 1, "green": 2}
            F["band"] = to
            F["drop"] = order.get(d.get("health_band_prev"), 2) - order.get(to, 2) >= 2
            risk_eval(t)
        elif obj == "ticket":
            if to in ("new", "open", "pending"):
                F["open"].add(d.get("id"))
            else:
                F["open"].discard(d.get("id"))
        elif obj == "activity":
            F["last_act"] = t
        elif obj == "contact" and to == "left_account":
            F["champ"] = True
            risk_eval(t)
        elif obj == "invoice":
            if to == "failed":
                F["payfail"].add(d.get("id"))
                risk_eval(t)
            elif to == "captured":
                F["payfail"].discard(d.get("id"))
    if cur[0] is not None:
        stays.append((cur[0], cur[1], None, cur[2], cur[3]))
    return stays
