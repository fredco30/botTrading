# AUDIT_NOTE_M0 — GOVERNANCE / PUBLICATION AUDIT (append-only)

Committed AFTER the mission result commit 995e8f1. No rules modified, no
rerun, no additional market period accessed. This note exists because the
publication check (item 6: "clarify the exact C2 momentum calculation from
CODE, not prose") exposed a defect that invalidates the published C2/C1
results.

## FINDING: C2 signal as implemented is LOOKAHEAD_CONTAMINATED

### The frozen spec said (FROZEN_CANDIDATES.md, commit 624db8d)
    Context : return over the last 4 COMPLETED H4 mid closes
    Entry   : at an M1 bar close, if 4h return > +10 pips -> LONG ...

### The code actually does (tick_replay.py / frozen_replay.py, committed 624db8d)
```python
H4NS = 4 * 3600 * NS                # 4 CLOCK-hour grid
h4   = b["start"] // H4NS           # bucket index per M1 bar
hu4, inv4 = np.unique(h4, return_inverse=True)
hc4[i] = close[inv4 == i][-1]       # FINAL M1 close of bucket i (whole series)
r4[4:]  = (hc4[4:] - hc4[:-4]) / P  # finalclose(bucket) - finalclose(bucket-4)
r4now   = r4[inv4]                  # CONSTANT for every bar inside a bucket
c2_long = flatnonzero(r4now > +10)  # fires at the bucket's FIRST bars too
```

### Measured (read-only diagnostic, 2017 data only, run during this audit)
- r4now is bucket-constant: TRUE (both halves).
- Reference closes are 4 grid slots apart = **16 clock hours**, not 4.
- For a decision at a bucket's first bar, hc4[current bucket] is a close
  **239 minutes IN THE FUTURE** of the decision (median = p90 = max = 239 min,
  both halves). Later bars in the bucket leak even more.
- Leak signal vs causal signal (decision-bar close vs the same 16h-old
  reference): median |gap| 5.55 pips (H1) / 5.65 pips (H2); long-flag
  disagreement 9.0% / 9.6%; short-flag 9.8% / 10.8%.

### Consequence
C2 enters trades using up to ~4 h of future price movement in its trigger.
The DISCOVERY and CONFIRMATION numbers (both halves) for C2 are
LOOKAHEAD_CONTAMINATED. FINAL_STATUS=CONFIRMED_CANDIDATE_FOUND is
WITHDRAWN for C2 as specified. C1 is structurally affected too: its H1
regime filter (`hc[i] = close[inv == i][-1]`, `trend = trend_h[inv]`) uses
the current H1 bucket's FINAL close — up to 59 min of future close
(median 59); the trend flag differs from a previous-completed-bucket causal
reference on 11.5% of M1 bars. C1's status is downgraded to
UNPROVEN_PENDING_CAUSAL_RETEST (its trigger ret15 is causal; the filter is not).

### What this note does NOT do
- Does not modify C1/C2 rules (git diff from 995e8f1 touches only this file
  and the PR text).
- Does not rerun discovery or confirmation.
- Does not access any period outside 2017.

### Disposition requested from human review
Either reject both candidates, or authorize a separate mission to re-freeze
the causal equivalent (signals computed only from closes at/before the
decision instant) and re-run the full discovery→freeze→confirmation protocol
on untouched windows. Until then this PR must not be merged and no candidate
may proceed to full-history validation.

## Budget deviation record (item 5 of the publication check)
- Ledger rows: 271 total (E001..E271); 267 inside the discovery sandbox,
  4 confirmation rows.
- Budget: 200 experiments. Row E200 is the FIRST F12 screen row — i.e., the
  4h-momentum mechanism was first measured exactly AT the budget boundary.
  Its deepening (E212..E227), tick-exact replay (E260..E263), freeze and
  confirmation all occurred after the budget was exhausted. No excuse is
  offered; the ledger records every row.
