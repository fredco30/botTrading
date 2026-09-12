# P013R V1 REPORT — frozen validation (first V1 opening)

Pré-enregistrement : P013R_V1_FROZEN_SPEC.md (commit 1, AVANT tout accès
données V1). Autorisation V1 journalisée via gate.py. V2 et OOS : jamais
accédées. Règle gelée : dernier jour FX ouvré, LONG XJPY, close → close du
jour de marché suivant, NORMAL 2 pips / STRESS 4 pips, pooling équipondéré
sur dates communes.

## Résultats (V1 = 2019-01-01 → 2023-01-01, N=47 events communs)

| Métrique | Valeur |
|---|---|
| USDJPY / EURJPY / GBPJPY GROSS | -7.24 / -5.82 / -11.59 pips (0/3 positifs) |
| POOLED_GROSS | -8.22 pips |
| POOLED_NET_NORMAL | **-10.22 pips** |
| POOLED_NET_STRESS | -12.22 pips |
| PAIRED_CI95_GROSS | [-24.12, 6.93] |
| PAIRED_CI95_NET_NORMAL | [-26.12, 4.93] |
| PAIRED_P_GROSS / P_NET_NORMAL | 0.301 / 0.205 |
| MEDIAN_GROSS / NET_NORMAL | 2.67 / 0.67 |
| WIN_RATE_GROSS / NET_NORMAL | 0.511 / 0.511 |
| REMOVE_BEST_EVENT_NET_NORMAL | -12.13 |
| REMOVE_BEST_3_EVENTS_NET_NORMAL | -16.15 |
| BY_YEAR_NET_NORMAL | {2019: -3.16, 2020: -2.25, 2021: -4.98, 2022: -32.32} |
| POSITIVE_YEARS_NET_NORMAL | 0/4 |
| YEAR_BLOCK_CI95_GROSS / NET_NORMAL | [-22.55, -0.7] / [-24.55, -2.7] |
| Censure frontière | événement déc. 2022 (entrée 2022-12-30) CENSURÉ sur les 3 paires |

## VERDICT (critères gelés — P013R_V1_FROZEN_SPEC.md)

**V1_REJECT**

POOLED_NET_NORMAL = -10.22 ≤ 0 et
0/3 paires
gross positives : deux critères structurels échoués indépendamment. Aucun
sauvetage, aucune variante, aucun filtre (par exemple « éviter 2022 »,
année 2022 : -32.32 pips nets) n'est autorisé ou tenté.

## Conséquence

V1_REJECT → P013R rejeté au stade V1 selon les critères figés. V2 non
ouverte (décision de revue humaine uniquement). La branche Discovery
(research/phenomena-discovery-v1) n'a pas été modifiée.

V2_ACCESSED=NO ; OOS_ACCESSED=NO.
