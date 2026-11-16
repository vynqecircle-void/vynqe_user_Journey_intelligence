# vynqe_synth: synthetic data generator, all three packs (v0.1.0)

**This data is synthetic.** Every number comes from a configured assumption. It is for building and testing the Customer Lifecycle Intelligence pipeline. **It makes no claim about how any model will perform on real customers, borrowers or accounts.**

This one zip replaces the three separate pack zips (e-commerce v0.1.1, BFSI v0.1.0, B2B SaaS v0.1.0). It holds the generator code once, because the packs share `vynqe_synth/core`, and each pack's samples and documents in its own folder.

## Layout
| Folder | What is in it |
|---|---|
| `vynqe_synth/`, `tests/`, `Makefile`, `pyproject.toml` | The generator, validators and tests for all three packs (32 tests) |
| `ecommerce/` | README, docs (parameters report, validation report, leakage rules, dataset guide, changelog), `sample_1000/` |
| `bfsi/` | README, docs (parameters report, table dictionary, 100k full report, validation reports, can/cannot-prove note, changelog), `sample_1000/` |
| `b2b_saas/` | README, docs (parameters report, table dictionary, dev full report, validation reports, can/cannot-prove note, changelog), `sample_1000/` |

Each sample folder has `visible/` (what a model may see), `hidden/` (truth tables, validation only), `schemas/` and `reports/`. **The samples are about 1,000 rows or accounts: use them to look at the shape of the data, not to estimate anything.**

## Get the full datasets
```
pip install pyarrow pyyaml pandas numpy scikit-learn pytest pydantic
python -m vynqe_synth generate --pack ecommerce --preset dev --seed 42 --out ./out_ecommerce
python -m vynqe_synth generate --pack bfsi      --preset dev --seed 42 --out ./out_bfsi
python -m vynqe_synth generate --pack b2b_saas  --preset dev --seed 42 --out ./out_b2b
python -m vynqe_synth validate --out ./out_ecommerce      # likewise for the others
python -m pytest tests
```
Add `--csv` for CSV copies. The same seed gives identical data. Approximate dev sizes: e-commerce 10,000 customers (about 80 s, 2.6M events); BFSI 100,000 people (about 2.5 min, 4.9M events); B2B 16,364 accounts (about 30 s, 324k events, 2.9M usage rows). Larger presets are in `vynqe_synth/config/presets.yaml`; the B2B `full` preset generates but its validator runs out of memory on a 7 GB machine, and the BFSI and e-commerce `full` presets were not run.

## Honest status of each pack
- **E-commerce:** see `ecommerce/README.md` and its docs. Known issue: the hidden `noise_log` logs every customer as a shared-phone case (not fixed).
- **BFSI:** dev run passes 125 of 125 checks; the 1,000-person sample passes 118 of 123 (small-sample effects). Same `noise_log` bug was fixed in BFSI only.
- **B2B SaaS:** dev run passes 150 of 150 checks; the 1,000-account sample passes 135 of 150 (only 29 customers). Only about 0.7% of leads become customers, so retention and uplift figures rest on few customers. NRR runs below the answers' targets.

Read each pack's `docs/what_this_data_can_and_cannot_prove.md` (BFSI, B2B) and `docs/CHANGELOG.md` before relying on any number.
