import ast, hashlib, json
from pathlib import Path
import pandas as pd
import pyarrow.parquet as pq
import pytest
from vynqe_synth.packs.bfsi.generate import generate
from vynqe_synth.packs.bfsi import schemas as S
from vynqe_synth.packs.bfsi.state_engine import run_bfsi_state_engine


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    a, b = tmp_path_factory.mktemp("a"), tmp_path_factory.mktemp("b")
    generate("bfsi", "tiny", 7, a, n_override=1500)
    generate("bfsi", "tiny", 7, b, n_override=1500)
    return a, b


def digest(root):
    out = {}
    for f in sorted(root.glob("*/*.parquet")):
        out[f.name] = hashlib.sha256(pd.util.hash_pandas_object(pq.read_table(f).to_pandas().astype(str), index=False).values.tobytes()).hexdigest()
    return out


def test_reproducible(run):
    assert digest(run[0]) == digest(run[1])


def test_different_seed_differs(run, tmp_path):
    generate("bfsi", "tiny", 8, tmp_path, n_override=300)
    assert digest(tmp_path)["events.parquet"] != digest(run[0])["events.parquet"]


def test_schemas_match(run):
    for sub, reg in (("visible", S.VISIBLE), ("hidden", S.HIDDEN)):
        for n, s in reg.items():
            assert pq.read_schema(run[0] / sub / f"{n}.parquet").names == s.names


def test_visible_table_count():
    assert 7 <= len(S.VISIBLE) <= 10


def test_hidden_not_in_visible_folder(run):
    assert not any(p.stem in S.HIDDEN for p in (run[0] / "visible").glob("*.parquet"))


def test_no_hidden_imports():
    root = Path(__file__).resolve().parent.parent / "vynqe_synth"
    for f in list((root / "core").glob("*.py")) + [root / "packs" / "bfsi" / "state_engine.py"]:
        for n in ast.walk(ast.parse(f.read_text())):
            names = [getattr(n, "module", "") or ""] + [x.name for x in getattr(n, "names", [])] if isinstance(n, (ast.Import, ast.ImportFrom)) else []
            assert not any(k in m for m in names for k in ("hidden", "schemas", "truth")), f.name


def test_holdout_control_gets_no_optional_action(run):
    a = pd.read_parquet(run[0] / "visible" / "actions.parquet")
    r = a[(a.record_kind == "decision") & (a.holdout_group == "control") & (a.regime == "randomised_holdout")]
    assert (r.chosen_action == "do_nothing").all()


def test_regulatory_never_held_out_and_never_chosen(run):
    a = pd.read_parquet(run[0] / "visible" / "actions.parquet")
    assert (a[a.category == "regulatory"].record_kind == "transactional").all()
    assert not a[(a.record_kind == "decision")].chosen_action.isin(["regulatory", "transactional"]).any()
    assert (a.category == "regulatory").sum() > 0


def test_no_raw_pii_or_exact_amounts(run):
    v = run[0] / "visible"
    e = pd.read_parquet(v / "events.parquet")
    assert not e.properties.str.contains(r"\b[6-9]\d{9}\b|@[a-z0-9-]+\.").any()
    for n in S.VISIBLE:
        assert not [c for c in pd.read_parquet(v / f"{n}.parquet").columns if "phone" in c or c.endswith("income") or "dpd" in c]


def test_default_label_final_only_when_old_enough(run):
    h, v = run[0] / "hidden", run[0] / "visible"
    at = pd.read_parquet(h / "application_truth.parquet").merge(pd.read_parquet(v / "loans.parquet")[["application_ref", "opened_at"]], on="application_ref")
    end = pd.Timestamp("2023-11-01", tz="UTC") + pd.Timedelta(days=1096)
    age = (end - at.opened_at).dt.days / 30.4
    assert (at[age >= 15.2].label_final.astype(bool)).all()
    assert not (at[age < 14.8].label_final.astype(bool)).any()


def test_default_flag_not_before_90_days(run):
    lo = pd.read_parquet(run[0] / "visible" / "loans.parquet")
    d = lo[lo.defaulted_at.notna()]
    assert ((d.defaulted_at - d.opened_at).dt.days >= 90).all()


def test_state_engine_deterministic_and_events_only(run):
    v = run[0] / "visible"
    e, b = pd.read_parquet(v / "events.parquet"), pd.read_parquet(v / "borrowers.parquet")
    sp = {"timeout_min": 30, "rule_version": "x", "application_stall_days": 14, "kyc_wait_days": 2, "first_cycle_days": 35, "dormant_days": 90, "topup_after_ontime": 6}
    end = (pd.Timestamp("2023-11-01", tz="UTC") + pd.Timedelta(days=1096)).timestamp()
    s1 = run_bfsi_state_engine(e, b, sp, end_sec=end)
    s2 = run_bfsi_state_engine(e.sample(frac=1, random_state=3), b, sp, end_sec=end)
    pd.testing.assert_frame_equal(s1[["unit_id", "state", "entered_at"]].reset_index(drop=True), s2[["unit_id", "state", "entered_at"]].reset_index(drop=True))
