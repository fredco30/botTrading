# P032R FOMC Post-Reaction Continuation — V1 (FAIL-FAST)

**CLASSIFICATION = P032R_V1_REJECT → STOP IMMÉDIAT.**
Conformément au protocole fail-fast : aucune variante, aucun retrait
d'année, aucune modification de fenêtre, V2 non ouverte.

## Règle

Figée AVANT toute lecture des prix V1 : voir [P032R_FROZEN_SPEC.md](P032R_FROZEN_SPEC.md)
(commit `008a6a7` sur cette branche, avant tout accès aux parquets).
Hypothèse P032 (Discovery) : après une annonce FOMC programmée, la
direction des 30 premières minutes continue entre +30 et +120 min.
Direction connue à T30 (aucune information future), sortie T120.

## Événements

32 réunions FOMC programmées (8/an, 2019-2022), heures de release
exactes des communiqués officiels Federal Reserve
(`data_raw/official/fomc_decisions.json`, EST/EDT → UTC).
Exclusions (non programmées / hors calendrier) : 2019-10-11,
2020-03-03, 2020-03-23, 2020-03-31, 2020-08-27.
Note : 2020-03-15 est la réunion programmée mars 17-18 tenue en visio
(page officielle fomchistorical2020), communiqué 17:00 EDT.

## Résultats (N=31, une ligne = un FOMC, 3 jambes ensemble)

> FINAL FIX (même PR, aucune variante) : (1) 2020-03-15 retiré — la Fed
> classe officiellement le 15 mars 2020 comme réunion NON programmée et
> la réunion programmée mars 17-18 comme annulée ; (2) POOLED_GROSS
> corrigé en gross STRATÉGIE (direction × mouvement de prix, choisi à
> T30) ; POOLED_NET = POOLED_GROSS − coût, cohérence testée.

| Métrique | Valeur (pips) |
|---|---|
| POOLED_GROSS (stratégie) | −8.42 |
| POOLED_NET_NORMAL (2p) | **−10.42** |
| POOLED_NET_STRESS (4p) | −12.42 |
| MEDIAN_NET_NORMAL | −4.67 |
| WIN_RATE_NET_NORMAL | 0.4194 |
| EURUSD / USDJPY / GBPUSD NET | −9.60 / −8.42 / −13.22 (0/3 positifs) |
| BY_YEAR_NET_NORMAL | 2019 −1.12 · 2020 −9.95 · 2021 +1.01 · 2022 −31.54 (1/4 positifs) |
| REMOVE_BEST_EVENT_NET_NORMAL | −13.30 |
| CI95 NET (paired bootstrap, 2000, seed 42) | [−25.88, +4.52] |

Critères gelés : POOLED_NET_NORMAL < +5 ✓reject ; 0/3 paires positives
✓reject ; REMOVE_BEST ≤ 0 ✓reject → **P032R_V1_REJECT** sur les trois
conditions à la fois.

## Interprétation (une ligne, pas une recherche)

Le "drift" observé en Discovery (2015-2018, sous-puissant) ne survit pas
hors échantillon : la continuation stratégique moyenne est négative
(−8.4 pips brut) avant même les coûts.

## Fichiers

- `lib_v1.py` / `run_v1.py` — implémentation de la règle figée
- `test_v1.py` — 10 tests (timing causal, direction à T30, bornes V1,
  V2/OOS inaccessibles, appariement par événement, remove-best) — 8/8 pass
- `v1_table.csv` — table commune (32 lignes)
- `v1_results.json` — stats + classification

V2_ACCESSED=NO · OOS_ACCESSED=NO
