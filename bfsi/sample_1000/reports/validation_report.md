# BFSI validation report

SYNTHETIC data. 118/123 checks passed. Failed checks are listed first.


## FAILED (5)

| group | check | observed | expected | note |
|---|---|---|---|---|
| distribution | mandate first-try success (Q14/Q32: 85-92%) | 0.818 | 0.82-0.93 |  |
| distribution | default by lender band vs Q26 placeholders (1-2 / 4-6 / 10-15 / high) | {'band_1': 0.1, 'band_2': 0.0, 'band_3': 0.0, 'band_4': 0.0} | bands ordered, within loose ranges | Band 4 rests on few loans; read with the counts: {"band_1": 20, "band_2": 8, "band_3": 2, "band_4": 1} |
| distribution | EMI states on time / grace / late / missed (Q31: 80-85 / 8-10 / 5-8 / 1-3) | {'on_time': 0.824, 'grace': 0.077, 'late': 0.052, 'missed': 0.048} | Q31 | Missed share runs a little above Q31 because stress persists; flagged |
| guardrails | every reason code appears at least once | ['mandate_inactive'] | [] | Missing codes mean the rule never fired in this sample |
| guardrails | promotional sends while a collections or dispute case is open | 4 | ~0 | Cases that open between a decision and its send time can leak a few |

## PASSED (118)

| group | check | observed | expected | note |
|---|---|---|---|---|
| schema | borrowers: columns match contract | 26 | 26 |  |
| schema | borrowers: no nulls in non-nullable columns | [] | [] |  |
| schema | borrowers: allowed values respected | [] | [] |  |
| schema | events: columns match contract | 14 | 14 |  |
| schema | events: no nulls in non-nullable columns | [] | [] |  |
| schema | events: allowed values respected | [] | [] |  |
| schema | applications: columns match contract | 19 | 19 |  |
| schema | applications: no nulls in non-nullable columns | [] | [] |  |
| schema | applications: allowed values respected | [] | [] |  |
| schema | application_steps: columns match contract | 12 | 12 |  |
| schema | application_steps: no nulls in non-nullable columns | [] | [] |  |
| schema | application_steps: allowed values respected | [] | [] |  |
| schema | loans: columns match contract | 11 | 11 |  |
| schema | loans: no nulls in non-nullable columns | [] | [] |  |
| schema | loans: allowed values respected | [] | [] |  |
| schema | emi_payments: columns match contract | 11 | 11 |  |
| schema | emi_payments: no nulls in non-nullable columns | [] | [] |  |
| schema | emi_payments: allowed values respected | [] | [] |  |
| schema | service_cases: columns match contract | 7 | 7 |  |
| schema | service_cases: no nulls in non-nullable columns | [] | [] |  |
| schema | service_cases: allowed values respected | [] | [] |  |
| schema | actions: columns match contract | 35 | 35 |  |
| schema | actions: no nulls in non-nullable columns | [] | [] |  |
| schema | actions: allowed values respected | [] | [] |  |
| schema | state_history: columns match contract | 7 | 7 |  |
| schema | state_history: no nulls in non-nullable columns | [] | [] |  |
| schema | state_history: allowed values respected | [] | [] |  |
| schema | campaigns: columns match contract | 10 | 10 |  |
| schema | campaigns: no nulls in non-nullable columns | [] | [] |  |
| schema | campaigns: allowed values respected | [] | [] |  |
| schema | person_truth: columns match contract | 27 | 27 |  |
| schema | person_truth: no nulls in non-nullable columns | [] | [] |  |
| schema | person_truth: allowed values respected | [] | [] |  |
| schema | application_truth: columns match contract | 18 | 18 |  |
| schema | application_truth: no nulls in non-nullable columns | [] | [] |  |
| schema | application_truth: allowed values respected | [] | [] |  |
| schema | state_truth: columns match contract | 4 | 4 |  |
| schema | state_truth: no nulls in non-nullable columns | [] | [] |  |
| schema | state_truth: allowed values respected | [] | [] |  |
| schema | noise_log: columns match contract | 3 | 3 |  |
| schema | noise_log: no nulls in non-nullable columns | [] | [] |  |
| schema | noise_log: allowed values respected | [] | [] |  |
| schema | visible tables count (brief: 7 to 10) | 10 | 7-10 |  |
| integrity | applications.unit_id in borrowers | 0 | 0 |  |
| integrity | events.unit_id in borrowers | 0 | 0 |  |
| integrity | steps and loans reference existing applications | 0 | 0 |  |
| integrity | emi_payments.loan_id in loans | 0 | 0 |  |
| integrity | actions/cases/state_history unit_id in borrowers | 0 | 0 |  |
| integrity | person_truth 1:1 with borrowers | 1000 | 1000 |  |
| integrity | application_truth 1:1 with applications | 507 | 507 |  |
| integrity | unique keys (applications, loans, actions, payments, steps) | False | False |  |
| integrity | state_history stays do not overlap | 0 | 0 |  |
| integrity | disbursal_date after created_at | 0 | 0 |  |
| integrity | every loan has a disbursed application with the same date | 0 | 0 |  |
| integrity | every disbursed application has exactly one loan | 0 | 0 |  |
| integrity | no EMI attempts after the lender default flag | 0 | 0 |  |
| integrity | no timestamps beyond the extract end (visible tables) | 0 | 0 |  |
| integrity | EMI attempts are ordered in time within an instalment | True | True |  |
| privacy | no raw phone/email in event properties | 0 | 0 |  |
| privacy | no raw-PII, income, DPD or exact-amount column names in visible tables | [] | [] |  |
| privacy | visible amounts are bands only | ['0-10k', '100k-250k', '10k-25k', '250k+', '25k-50k', '50k-100k'] | bands |  |
| privacy | no exact amounts in event properties | 0 | 0 |  |
| leakage | no hidden-table column names in visible tables | [] | [] |  |
| leakage | state engine and core modules import no hidden tables or schemas | [] | [] |  |
| leakage | trap exists: loans.lender_band_latest differs from the band at decision for some loans | 0.141 | > 0 (extract-time snapshot) |  |
| leakage | trap: lender_band_latest is band_4 for every defaulted loan (future leaks into a snapshot column) | 1.0 | 1.0 |  |
| leakage | trap: defaulted_at is only populated for defaulted loans | 0 | 0 |  |
| distribution | existing-customer share of people (Q4: 20-30%) | 0.244 | 0.20-0.30 |  |
| distribution | lead to disbursal, new applications (Q7: 3-8%) | 0.062 | 0.03-0.08 |  |
| distribution | application to disbursal, new applications (Q7: about 12%) | 0.127 | 0.09-0.16 |  |
| distribution | KYC first-attempt pass (Q10: 70%) | 0.678 | 0.62-0.78 |  |
| distribution | KYC eventual pass among applicants who start KYC | 0.871 | 0.75-0.92 (final fail about 10-15%) |  |
| distribution | AA consent given (Q11: 65-75% default; config 88% before drop-off) | 0.852 | 0.65-0.92 |  |
| distribution | AA data fetch first-try success (Q11: 75-85%) | 0.889 | 0.75-0.90 |  |
| distribution | decision mix approve / refer / decline (Q12: 40-60 / 5-10 / 30-50) | {'decline': 0.488, 'approve': 0.421, 'refer': 0.091} | see Q12 |  |
| distribution | lender band shares among decided applicants (Q23: 30/40/20/10) | [0.318, 0.401, 0.157, 0.124] | [0.3, 0.4, 0.2, 0.1] |  |
| distribution | offer acceptance, sanctioned to e-sign started (Q13: 60-75%) | 0.661 | 0.55-0.80 |  |
| distribution | e-sign success (Q14: about 90%) | 0.885 | 0.88-0.97 |  |
| distribution | signed but never disbursed (Q15: 5-15%; includes failed mandates and drop-off) | 0.165 | 0.04-0.20 |  |
| distribution | 90+ DPD within 12 months, loans 15+ months old (Q26 digital placeholder 1-6%) | 0.0645 | 0.02-0.09 | n=31 final loans |
| distribution | EMI first-attempt bounce (Q33: 5-12%; Q31 implies about 15%) | 0.157 | 0.05-0.20 | Q31 and Q33 disagree; the pack sits between them. Reported, not hidden |
| distribution | prepaid share of closed loans (Q34: 10-20% prepay before term) | 0.286 | 0.05-0.35 |  |
| distribution | loans with a mandate cancellation event (Q32: 2-5% cancel within 6 months, config 3%) | 0.014 | 0.01-0.06 |  |
| distribution | people with a complaint or dispute (Q39: 1-3% of borrowers; here per person, so lower) | 0.006 | 0.0003-0.03 |  |
| distribution | first missed instalment of defaulters falls in months 3-9 (Q28: defaults peak in months 3-9) | 0.667 | >= 0.5 | Hazard is flat plus a small drift; a peak is not planted. Reported as is |
| distribution | events per person | 47.8 | 20-120 |  |
| distribution | email consent granted share (config 55%, minus withdrawals, plus opt-ins) | 0.588 | 0.40-0.65 |  |
| noise | duplicate rate vs config | 0.0171 | 0.02 | event-level; application duplicates also appear under 'duplicate' |
| noise | late rate vs config | 0.0165 | 0.02 | event-level; application duplicates also appear under 'duplicate' |
| noise | missing_field rate vs config | 0.008 | 0.01 | event-level; application duplicates also appear under 'duplicate' |
| noise | wrong_timestamp rate vs config | 0.0043 | 0.005 | event-level; application duplicates also appear under 'duplicate' |
| noise | bot, tracking-gap and shared-device defects present | [6891, 157, 16] | >0 |  |
| noise | shared-phone defects logged equal the people who share a phone | [16, 16] | equal |  |
| noise | razorpay median lag in days (Q52: T+1 to T+2) | 1.53 | 1.0-2.5 |  |
| noise | core banking median lag in hours (daily extract) | 19.8 | 6-30 |  |
| noise | origination median lag in seconds (real time) | 32.5 | < 120 |  |
| noise | duplicate applications logged (Q51: 3-8%; ours is of new applications) | 0.035 | 0.015-0.08 |  |
| guardrails | no executed action was also blocked (except approval -> task) | 0 | 0 |  |
| guardrails | holdout-control people never receive an optional action | 0 | 0 |  |
| guardrails | holdout share | 0.07 | 0.08 |  |
| guardrails | regulatory messages (EMI reminders, KFS) reach holdout people at the normal rate | 0.047 | ~0.070 |  |
| guardrails | policy never chooses a regulatory or transactional message | 0 | 0 |  |
| guardrails | propensity logged for every randomised decision, in (0,1] | 0.0 | 0 |  |
| guardrails | promotional sends with no granted marketing consent at send time | 0 | ~0 | Late and duplicate events can add a few |
| guardrails | AA consent alone never enables marketing (aa_consent_only blocks occur and none executed) | [10, 0] | >0 and 0 |  |
| recoverability | hidden borrower type predicted from visible behaviour (3-fold accuracy) | 0.524 | > majority 0.389 and < 0.95 | Types are learnable but never trivially |
| recoverability | lender band correlates with true risk but is not near perfect (Q55) | 0.756 | 0.45-0.90 |  |
| uplift | randomised estimate per action vs planted mean (estimate, std err, planted mean, n treated, n do_nothing) | {'nudge': (-0.019, 0.032, 0.057, 173, 109), 'agent_call': (0.066, 0.048, 0.093, 99, 82), 'fee_waiver': None, 'offer': None} | same sign as planted; within 2.5 std errors + 0.03 of planted x about 0.6 (people returning anyway dilute it) | Planted effect is per type and step-scaled, so the comparison is approximate |
| uplift | every incremental application with a cause points to a real action that was not do_nothing | [44, 36, 0] | counts; none do_nothing | 0.182 of incremental rows have no cause: those come from the legacy regime, where sends carry no decision id |
| uplift | legacy period targets lower-risk applicants more than their share (biased targeting) | [0.917, 0.719] | legacy > all |  |
| uplift | planted uplift differs by hidden type (fee waiver highest for rate_shopper, offer for repeat_borrower) | {'uplift_nudge': {'debt_consolidation': 0.038, 'one_time': 0.019, 'planned_big_ticket': 0.039, 'rate_shopper': 0.018, 'repeat_borrower': 0.052, 'short_term_cash': 0.08}, 'uplift_agent_call': {'debt_consolidation': 0.09, 'one_time': 0.028, 'planned_big_ticket': 0.101, 'rate_shopper': 0.041, 'repeat_borrower': 0.057, 'short_term_cash': 0.121}, 'uplift_fee_waiver': {'debt_consolidation': 0.06, 'one_time': 0.01, 'planned_big_ticket': 0.077, 'rate_shopper': 0.124, 'repeat_borrower': 0.029, 'short_term_cash': 0.028}, 'uplift_offer': {'debt_consolidation': 0.036, 'one_time': 0.01, 'planned_big_ticket': 0.03, 'rate_shopper': 0.029, 'repeat_borrower': 0.122, 'short_term_cash': 0.018}} | rate_shopper / repeat_borrower |  |
| uplift | sleeping dogs exist (negative planted uplift) | 0.041 | 0.04 |  |
| labels | default label is final only for loans 15+ months old | 0 | 0 |  |
| labels | some loans are not yet final (the window end leaves them open) | 0.5633802816901409 | > 0 |  |
| labels | no default flag in the visible loans table before 90 days past due | 0 | 0 |  |
| labels | visible default flag comes 1-5 days after the hidden 90 DPD date | 0 | 0 |  |
| state | visible-event state pairs found in truth (noise and identity splits cost some) | 0.998 | 0.8-1.0 |  |
| state | all 13 states present | [] | [] |  |