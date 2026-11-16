import hashlib, json
from pathlib import Path
import pandas as pd
import pyarrow.parquet as pq
import pytest
from vynqe_synth.packs.ecommerce.generate import generate
from vynqe_synth.packs.ecommerce import schemas as S
from vynqe_synth.core.labels import build_labels


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    a, b = tmp_path_factory.mktemp("a"), tmp_path_factory.mktemp("b")
    generate("ecommerce", "tiny", 7, a, n_override=200)
    generate("ecommerce", "tiny", 7, b, n_override=200)
    return a, b


def digest(root):
    out = {}
    for f in sorted(root.glob("*/*.parquet")):
        t = pq.read_table(f)
        out[f.name] = hashlib.sha256(pd.util.hash_pandas_object(t.to_pandas().astype(str), index=False).values.tobytes()).hexdigest()
    return out


def test_reproducible(run):
    assert digest(run[0]) == digest(run[1])


def test_different_seed_differs(run, tmp_path):
    generate("ecommerce", "tiny", 8, tmp_path, n_override=200)
    assert digest(tmp_path)["events.parquet"] != digest(run[0])["events.parquet"]


def test_schemas_match(run):
    for sub, reg in (("visible", S.VISIBLE), ("hidden", S.HIDDEN)):
        for n, s in reg.items():
            assert pq.read_schema(run[0] / sub / f"{n}.parquet").names == s.names


def test_hidden_not_in_visible_folder(run):
    assert not any(p.stem in S.HIDDEN for p in (run[0] / "visible").glob("*.parquet"))


def test_no_hidden_imports():
    root = Path(__file__).resolve().parent.parent / "vynqe_synth"
    import ast
    for f in [root / "core" / "state_engine.py", root / "core" / "labels.py", root / "core" / "noise.py"]:
        for n in ast.walk(ast.parse(f.read_text())):
            mod = getattr(n, "module", "") or ""
            assert "hidden" not in mod and "schemas" not in mod


def test_label_finality(run):
    d = run[0] / "visible"
    e, a = pd.read_parquet(d / "events.parquet"), pd.read_parquet(d / "actions.parquet")
    lab = build_labels(e, a, (7, 30), 45)
    ext = e.ingested_at.max()
    for H in (7, 30):
        should = lab.decided_at + pd.Timedelta(days=H + 45) <= ext
        assert (lab[f"final_{H}d"] == should).all()


def test_label_uses_only_future_orders(run):
    d = run[0] / "visible"
    e, a = pd.read_parquet(d / "events.parquet"), pd.read_parquet(d / "actions.parquet")
    lab = build_labels(e, a, (7,), 45)
    o = e[e.event_type == "record_created"]
    o = o[o.properties.str.contains('"object":"order"')].drop_duplicates("source_event_id")
    row = lab[lab.ordered_7d == 1].iloc[0]
    t = o[(o.unit_id == row.unit_id) & (o.occurred_at > row.decided_at) & (o.occurred_at <= row.decided_at + pd.Timedelta(days=7))]
    assert len(t) >= 1
    row0 = lab[lab.ordered_7d == 0].iloc[0]
    t0 = o[(o.unit_id == row0.unit_id) & (o.occurred_at > row0.decided_at) & (o.occurred_at <= row0.decided_at + pd.Timedelta(days=7))]
    assert len(t0) == 0


def test_holdout_control_gets_no_action(run):
    a = pd.read_parquet(run[0] / "visible" / "actions.parquet")
    r = a[(a.record_kind == "decision") & (a.holdout_group == "control")]
    assert (r.chosen_action == "do_nothing").all()
