# Changelog
- 0.1.0 BFSI personal-loan pack: 10 visible tables, 4 hidden tables, BFSI state engine (13 states, rule version bfsi_rules_v0.1), noise, validator (125 checks), 12 tests. B2B SaaS pack NOT started. E-commerce pack unchanged (8 tests still pass).

## Deviations and gaps (read before use)
1. Window is 36 months (the brief says 36 for BFSI; the answers suggest 24). Regime 2 starts at month 19.
2. Unit is a person; people are leads the lender can see. Upstream drop-offs are not in the data.
3. Part-payments (3-5%) and restructuring (under 1%) are not modelled.
4. The pre-approved-offer holder share (Q42) is not modelled as a flag; offers are an action like the others.
5. A top-up is a separate loan; the old loan keeps running.
6. A cooling-off exit shows as `closure_type = foreclosed`.
7. `existing_customer_start_boost` is not applied separately; the existing-base start rate already includes it.
8. Defaults do not peak in months 3 to 9 (Q28): the monthly hazard is flat plus a small drift. 66% of defaulters' first missed instalment falls in months 3 to 9, but no peak is planted.
9. Q31 and Q33 disagree on bounce rates. First-attempt bounce is 14.7%, between Q33 (5-12%) and what Q31 implies (about 15%). Missed instalments run at 2.9% (Q31: 1-3%).
10. Default by band at 100,000 people: 2.1 / 3.6 / 12.8 / 25% against Q26 placeholders of 1-2 / 4-6 / 10-15 / high. Band 2 is slightly low and band 4 rests on few loans.
11. Prepaid loans are 24.9% of closed loans; Q34 says 10-20% of loans prepay before term (different denominators).
12. Legacy targeting is only mildly biased (78% of sends to lower bands against a 70% base).
13. Uplifts are planted illustrative truths (grade C). Randomised estimates for nudge and agent call come out below the planted means.
14. 246 promotional messages in 100,000 people were sent while a collections or dispute case was open (cases that opened between a decision and its send time). Under the 0.3% tolerance but not zero.
15. The status names for mandates, KYC and AA failures are ours where vendors publish none. Workbook extensions are flagged in `schemas/` (`geo_tier`, `application_kind`, `tenure_band`, coarse `defaulted` flag).
16. The 1,000-person sample fails 5 of 123 checks because it is small.
17. Fixed before release: the hidden `noise_log` first logged every person as a shared-phone case; it now logs only the real ones (1,512 at 100,000 people), and a validator check guards it. The same bug exists in the e-commerce pack's `noise_log` (not fixed in the e-commerce zip sent earlier).
