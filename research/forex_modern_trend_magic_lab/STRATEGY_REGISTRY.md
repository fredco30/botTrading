# STRATEGY_REGISTRY — FOREX_MODERN_STRATEGY_LAB_M1

| STRATEGY_ID | mechanism | pairs | tf | status |
|-------------|-----------|-------|----|--------|
| FX_PDH_001 | prior-day-high upside continuation (stop 1 ATR / trail 3 ATR / 48h hold) | USDJPY | H1 | FROZEN_CANDIDATE — STRICT V1 canonical |

Canonical spec: candidates/FX_PDH_001/FROZEN_SPEC_STRICT_V1.md (causal
correction of the original freeze — see audit/FX_PDH_001_STRICT_AUDIT.md).
Only STRICT V1 is eligible for the protected 2026 test.

Frozen candidates: 1.

TREND_MAGIC_FINAL_STATUS = DEAD_AND_CLOSED (permanent; see
REJECTED_FAMILIES.md). Trend Magic Enhanced archived with no STRATEGY_ID.

Cross-pair replication (2020-2025, strict frozen rules): 1_OF_6 robust —
USDJPY only (see cross_pair_replication/CROSS_PAIR_RESULTS.md). Mechanism is
USDJPY-specific; no generalization. EURJPY = weak near miss, not rescued.
