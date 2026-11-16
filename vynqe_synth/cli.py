import argparse
from pathlib import Path


def main(argv=None):
    ap = argparse.ArgumentParser(prog="vynqe_synth")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate")
    g.add_argument("--pack", default="ecommerce")
    g.add_argument("--preset", default="tiny")
    g.add_argument("--seed", type=int, default=42)
    g.add_argument("--out", default="./out")
    g.add_argument("--csv", action="store_true")
    g.add_argument("--n", type=int, default=None, help="override customer count")
    v = sub.add_parser("validate")
    v.add_argument("--out", default="./out")
    a = ap.parse_args(argv)
    if a.cmd == "validate":
        if (Path(a.out) / "visible" / "borrowers.parquet").exists():
            from .validate.bfsi_report import write_report
        elif (Path(a.out) / "visible" / "product_usage_daily.parquet").exists():
            from .validate.b2b_report import write_report
        else:
            from .validate.report import write_report
        write_report(Path(a.out))
        return
    if a.cmd == "generate":
        if a.pack == "bfsi":
            from .packs.bfsi.generate import generate
        elif a.pack == "b2b_saas":
            from .packs.b2b_saas.generate import generate
        elif a.pack == "ecommerce":
            from .packs.ecommerce.generate import generate
        else:
            raise SystemExit("Packs available: ecommerce, bfsi, b2b_saas.")
        c = generate(a.pack, a.preset, a.seed, Path(a.out), a.csv, a.n)
        print(c)


if __name__ == "__main__":
    main()
