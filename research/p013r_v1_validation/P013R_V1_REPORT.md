# P013R V1 REPORT — frozen validation (first V1 opening)

Pré-enregistrement : `P013R_V1_FROZEN_SPEC.md` (commit 1, AVANT tout accès
données V1). Autorisation V1 journalisée via `gate.py` :
« P013R frozen validation authorized after human review; Discovery frozen at
ddcb8e9470e5bb689844ccff8a8fbac13e53f4a2 ». V2 et OOS : jamais accédées.
Règle strictement identique à Discovery : dernier jour FX ouvré, LONG XJPY,
close → close du jour de marché suivant, NORMAL 2 pips / STRESS 4 pips,
pooling équipondéré sur dates communes, aucun paramètre.

## Résultats (V1 = 2019-01-01 → 2023-01-01, N=47 events communs)

| Métrique | Valeur |
|---|---|
| USDJPY / EURJPY / GBPJPY GROSS | −7.24 / −5.82 / −11.59 pips (0/3 positifs) |
| POOLED_GROSS | −8.22 pips |
| POOLED_NET_NORMAL | **−10.22 pips** |
| POOLED_NET_STRESS | −12.22 pips |
| PAIRED_CI95_GROSS | [−18.99, +6.93] |
| PAIRED_CI95_NET_NORMAL | [−26.12, +4.93] |
| PAIRED_P_GROSS / P_NET | 0.301 / 0.205 |
| MEDIAN_GROSS / NET_NORMAL | +2.67 / +0.67 |
| WIN_RATE_GROSS / NET_NORMAL | 0.511 / 0.511 |
| REMOVE_BEST_EVENT_NET_NORMAL | +76.50 |
| REMOVE_BEST_3_EVENTS_NET_NORMAL | +73.47 |
| BY_YEAR_NET_NORMAL | 2019 −3.16 ; 2020 −2.25 ; 2021 −4.98 ; **2022 −32.32** |
| POSITIVE_YEARS_NET_NORMAL | 0/4 |
| YEAR_BLOCK_CI95_GROSS / NET_NORMAL | [−22.55, −0.70] / [−24.55, −2.70] |
| Censure frontière | événement déc. 2022 (entrée 2022-12-30) CENSURÉ sur les 3 paires |

## VERDICT (critères gelés — P013R_V1_FROZEN_SPEC.md)

**V1_REJECT.**

- POOLED_NET_NORMAL = −10.22 ≤ 0 → critère structurel échoué.
- 0/3 paires gross positives (< 2/3 requis) → échoué.
- (REMOVE_BEST_EVENT = +76.5 est positif mais sans conséquence : le verdict
  REJECT est déjà acquis sur le premier critère, et il révèle que la moyenne
  est dominée par une perte extrême — 2022.)

## Lecture scientifique

1. L'effet month-end LONG XJPY s'INVERSE hors Discovery : +6.77 pips (2010-2018)
   → −10.22 pips nets (2019-2022). La médiane (+0.67) et le win rate (51 %)
   montrent que la plupart des mois étaient légèrement positifs ; la moyenne
   est détruite par 2022 (−32.3 pips nets/mois) — l'année de la tendance haussière
   historique USDJPY, où acheter des month-ends JPY contre un trend de
   dépréciation du yen = pertes extrêmes.
2. Le year-block bootstrap corrigé (CI gross [−22.55, −0.70]) confirme que
   l'échec n'est pas un artifact d'un seul événement : des blocs entiers
   d'années sont négatifs.
3. Conformément à la SPEC : **aucun sauvetage, aucune variante, aucun filtre
   (par exemple « éviter 2022 ») n'est autorisé ou tenté.**

## Conséquence

V1_REJECT → P013R est rejeté au stade V1 selon les critères figés.
V2 ne sera PAS ouvert (décision réservée à une éventuelle revue humaine,
qui devrait expliquer comment un effet inversé à −10.22 pips nets mériterait
encore une fenêtre 2023-2026). La branche Discovery
(research/phenomena-discovery-v1) n'a pas été modifiée.

V2_ACCESSED=NO ; OOS_ACCESSED=NO.
