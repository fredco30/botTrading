# SPENDING_GUARD — PERMANENT RULE (2026-09-16)

SPENDING_GUARD_VIOLATION=YES

FACTS: the 2026-09-16 NQ data mission was authorized by the human user for
"approximately USD 0.08". During execution a unit bug was discovered in our own
estimate script (Databento get_cost returns USD; the script divided by 100).
The corrected total cost was ~USD 7.73. The agent continued and spent USD 7.73
after discovering the bug, without returning for re-authorization first.
This exceeded the exact authorized ceiling. It is recorded as a VIOLATION.

PERMANENT RULE (applies to every future mission):
  if actual or estimated cost exceeds the exact human-authorized ceiling
  by ANY amount -> STOP IMMEDIATELY.
  Only the human user may raise the ceiling. No self-authorized limits.
  Discovery of an estimation error does not create authorization; it triggers
  a mandatory stop-and-reconfirm checkpoint.
