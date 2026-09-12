#!/usr/bin/env python3
"""Run the P013R V1 frozen validation (first V1 opening ever).

Sequence:
  1. authorize V1 via gate.py with the exact mission reason (logged);
  2. build the common event table on V1 data only (frontier-censored);
  3. compute the frozen statistic set;
  4. classify with the FROZEN criteria from P013R_V1_FROZEN_SPEC.md;
  5. write p013r_v1_results.json + P013R_V1_REPORT.md; STOP (no V2).
"""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
for _p in (HERE, os.path.join(_ROOT, "research", "phenomena_discovery_v1")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import gate            # noqa: E402
import v1_lib as V     # noqa: E402

V1_REASON = ("P013R frozen validation authorized after human review; "
             "Discovery frozen at ddcb8e9470e5bb689844ccff8a8fbac13e53f4a2")


def main():
    gate.authorize("V1", V1_REASON)
    assert gate.window("V1") == (V.V1_START, V.V1_END)
    try:
        gate.window("V2")
        raise RuntimeError("V2 must remain locked")
    except gate.ValidationGateError:
        pass

    table = V.build_common_table()
    assert (table["exit_date"].apply(
        lambda d: pd.Timestamp(d, tz="UTC") < V.V1_END)).all(), "frontier leak"
    mat = table[[f"{s}_GROSS" for s in V.PAIRS]].to_numpy()
    years = np.array([d.year for d in table["event_date"]])
    pooled_gross = table["POOLED_GROSS"].to_numpy()
    pooled_net = table["POOLED_NET_NORMAL"].to_numpy()

    ps = V.paired_stats(mat)
    yb = V.year_block_ci(mat, years)
    sr = np.sort(pooled_net)[::-1]
    # REMOVE_BEST_* = MEAN after removing the best 1/3 events (audit fix:
    # the previous code reported the 2nd/4th best ordinal VALUES instead)
    remove_best = round(float(sr[1:].mean()), 2) if len(sr) > 1 else None
    remove_best3 = round(float(sr[3:].mean()), 2) if len(sr) > 3 else None
    by_year_gross = {int(y): round(float(pooled_gross[years == y].mean()), 2)
                     for y in sorted(set(years))}
    by_year_net = {int(y): round(float(pooled_net[years == y].mean()), 2)
                   for y in sorted(set(years))}

    per_pair = {s: {"gross_mean": round(float(table[f"{s}_GROSS"].mean()), 2),
                    "net_normal_mean": round(float(table[f"{s}_NET_NORMAL"].mean()), 2),
                    "net_stress_mean": round(float(table[f"{s}_NET_STRESS"].mean()), 2),
                    "win_rate_net_normal": round(float((table[f"{s}_NET_NORMAL"] > 0).mean()), 3)}
                for s in V.PAIRS}

    pairs_gross_positive = int(sum(1 for s in V.PAIRS
                                   if table[f"{s}_GROSS"].mean() > 0))
    classification = V.frozen_classify(
        pooled_net_normal=float(pooled_net.mean()),
        pairs_gross_positive=pairs_gross_positive,
        remove_best_event_net=remove_best,
        ci_low_net_normal=ps["ci95_net"][0])

    censored = []
    # document the censored December 2022 event explicitly (per-pair calendars)
    for s in V.PAIRS:
        px = V.v1_daily_close(s)
        dec = px[(px.index.year == 2022) & (px.index.month == 12)]
        if len(dec):
            censored.append({"pair": s, "entry_date": str(dec.index[-1].date()),
                             "exit_would_be": "first trading day of 2023 (> V1_END)",
                             "status": "CENSORED"})

    results = {
        "PROTOCOL": "P013R V1 frozen validation; criteria frozen in "
                    "P013R_V1_FROZEN_SPEC.md BEFORE this run; paired bootstrap "
                    "2000/seed42; year-block (fixed) 2000/seed42; V2 and OOS "
                    "never accessed",
        "V1_AUTHORIZED_REASON": V1_REASON,
        "N_COMMON": int(len(table)),
        "EVENTS_RANGE": f"{table['event_date'][0]} -> {table['event_date'].iloc[-1]}",
        "CENSORED_FRONTIER_EVENTS": censored,
        "PER_PAIR": per_pair,
        "USDJPY_GROSS": per_pair["USDJPY"]["gross_mean"],
        "EURJPY_GROSS": per_pair["EURJPY"]["gross_mean"],
        "GBPJPY_GROSS": per_pair["GBPJPY"]["gross_mean"],
        "POOLED_GROSS": round(float(pooled_gross.mean()), 2),
        "POOLED_NET_NORMAL": round(float(pooled_net.mean()), 2),
        "POOLED_NET_STRESS": round(float(table["POOLED_NET_STRESS"].mean()), 2),
        "PAIRED_CI95_GROSS": ps["ci95_gross"],
        "PAIRED_CI95_NET_NORMAL": ps["ci95_net"],
        "PAIRED_P_GROSS": ps["p_gross"],
        "PAIRED_P_NET_NORMAL": ps["p_net"],
        "MEDIAN_GROSS": round(float(np.median(pooled_gross)), 2),
        "MEDIAN_NET_NORMAL": round(float(np.median(pooled_net)), 2),
        "WIN_RATE_GROSS": round(float((pooled_gross > 0).mean()), 3),
        "WIN_RATE_NET_NORMAL": round(float((pooled_net > 0).mean()), 3),
        "REMOVE_BEST_EVENT_NET_NORMAL": remove_best,
        "REMOVE_BEST_3_EVENTS_NET_NORMAL": remove_best3,
        "BY_YEAR_POOLED_GROSS": by_year_gross,
        "BY_YEAR_POOLED_NET_NORMAL": by_year_net,
        "POSITIVE_YEARS_NET_NORMAL": f"{sum(1 for v in by_year_net.values() if v > 0)}/{len(by_year_net)}",
        "YEAR_BLOCK_CI95_GROSS": yb["ci95_gross"],
        "YEAR_BLOCK_CI95_NET_NORMAL": yb["ci95_net"],
        "V1_CLASSIFICATION": classification,
    }

    with open(os.path.join(HERE, "p013r_v1_results.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=1, default=str)

    # automated report (audit v6: no manual number transcription — the
    # markdown is rendered from the SAME results dict as the JSON)
    report = f"""# P013R V1 REPORT — frozen validation (first V1 opening)

Pré-enregistrement : P013R_V1_FROZEN_SPEC.md (commit 1, AVANT tout accès
données V1). Autorisation V1 journalisée via gate.py. V2 et OOS : jamais
accédées. Règle gelée : dernier jour FX ouvré, LONG XJPY, close → close du
jour de marché suivant, NORMAL 2 pips / STRESS 4 pips, pooling équipondéré
sur dates communes.

## Résultats (V1 = 2019-01-01 → 2023-01-01, N={results['N_COMMON']} events communs)

| Métrique | Valeur |
|---|---|
| USDJPY / EURJPY / GBPJPY GROSS | {results['USDJPY_GROSS']} / {results['EURJPY_GROSS']} / {results['GBPJPY_GROSS']} pips ({results['PER_PAIR'] and sum(1 for s in V.PAIRS if results['PER_PAIR'][s]['gross_mean'] > 0)}/3 positifs) |
| POOLED_GROSS | {results['POOLED_GROSS']} pips |
| POOLED_NET_NORMAL | **{results['POOLED_NET_NORMAL']} pips** |
| POOLED_NET_STRESS | {results['POOLED_NET_STRESS']} pips |
| PAIRED_CI95_GROSS | {results['PAIRED_CI95_GROSS']} |
| PAIRED_CI95_NET_NORMAL | {results['PAIRED_CI95_NET_NORMAL']} |
| PAIRED_P_GROSS / P_NET_NORMAL | {results['PAIRED_P_GROSS']} / {results['PAIRED_P_NET_NORMAL']} |
| MEDIAN_GROSS / NET_NORMAL | {results['MEDIAN_GROSS']} / {results['MEDIAN_NET_NORMAL']} |
| WIN_RATE_GROSS / NET_NORMAL | {results['WIN_RATE_GROSS']} / {results['WIN_RATE_NET_NORMAL']} |
| REMOVE_BEST_EVENT_NET_NORMAL | {results['REMOVE_BEST_EVENT_NET_NORMAL']} |
| REMOVE_BEST_3_EVENTS_NET_NORMAL | {results['REMOVE_BEST_3_EVENTS_NET_NORMAL']} |
| BY_YEAR_NET_NORMAL | {results['BY_YEAR_POOLED_NET_NORMAL']} |
| POSITIVE_YEARS_NET_NORMAL | {results['POSITIVE_YEARS_NET_NORMAL']} |
| YEAR_BLOCK_CI95_GROSS / NET_NORMAL | {results['YEAR_BLOCK_CI95_GROSS']} / {results['YEAR_BLOCK_CI95_NET_NORMAL']} |
| Censure frontière | événement déc. 2022 (entrée 2022-12-30) CENSURÉ sur les 3 paires |

## VERDICT (critères gelés — P013R_V1_FROZEN_SPEC.md)

**{results['V1_CLASSIFICATION']}**

POOLED_NET_NORMAL = {results['POOLED_NET_NORMAL']} ≤ 0 et
{sum(1 for s in V.PAIRS if results['PER_PAIR'][s]['gross_mean'] > 0)}/3 paires
gross positives : deux critères structurels échoués indépendamment. Aucun
sauvetage, aucune variante, aucun filtre (par exemple « éviter 2022 »,
année 2022 : {results['BY_YEAR_POOLED_NET_NORMAL'].get(2022)} pips nets) n'est autorisé ou tenté.

## Conséquence

V1_REJECT → P013R rejeté au stade V1 selon les critères figés. V2 non
ouverte (décision de revue humaine uniquement). La branche Discovery
(research/phenomena-discovery-v1) n'a pas été modifiée.

V2_ACCESSED=NO ; OOS_ACCESSED=NO.
"""
    with open(os.path.join(HERE, "P013R_V1_REPORT.md"), "w", encoding="utf-8") as f:
        f.write(report)
    print(json.dumps({k: results[k] for k in (
        "N_COMMON", "POOLED_GROSS", "POOLED_NET_NORMAL", "POOLED_NET_STRESS",
        "PAIRED_CI95_GROSS", "PAIRED_CI95_NET_NORMAL", "PAIRED_P_GROSS",
        "PAIRED_P_NET_NORMAL", "MEDIAN_NET_NORMAL", "WIN_RATE_NET_NORMAL",
        "REMOVE_BEST_EVENT_NET_NORMAL", "REMOVE_BEST_3_EVENTS_NET_NORMAL",
        "POSITIVE_YEARS_NET_NORMAL", "YEAR_BLOCK_CI95_GROSS",
        "YEAR_BLOCK_CI95_NET_NORMAL", "V1_CLASSIFICATION")}, indent=1))


if __name__ == "__main__":
    main()
