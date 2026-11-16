# Changelog
- 0.1.0 e-commerce pack: 9 visible tables, 4 hidden tables, state engine, noise, labels, validator, tests. BFSI and B2B SaaS packs NOT started.
- 0.1.1 Fixed: hidden `noise_log` logged every customer as a shared-phone case (a missing-value check was always true). It now logs only the real ones. No other table changed. Data regenerated: sample_1000 (87/88 checks, as before) and 10,000 customers (88/88).
