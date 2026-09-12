# P032R_FROZEN_SPEC.md — FOMC Post-Reaction Continuation V1

Règle exacte, figée et committée AVANT toute lecture des prix V1
(2019-01-01 → 2023-01-01 exclusif).

## Hypothèse testée (issue de Discovery P032)

Après une annonce FOMC programmée, la direction du mouvement des
30 premières minutes continue entre +30 min et +120 min.

## Événements

- Réunions FOMC PROGRAMMÉES uniquement (calendrier officiel des réunions
  du Federal Reserve : 8 réunions/an).
- Exclure les réunions/annonces d'urgence NON programmées
  (ex. 2019-10-11, 2020-03-03, 2020-03-15, 2020-03-23, 2020-03-31,
  2020-08-27 — hors calendrier programmé).
- Source des timestamps : sources officielles Federal Reserve uniquement
  (`data_raw/official/fomc_decisions.json`, heures exactes "For release
  at ..." des communiqués, EST/EDT honoré ; dates des réunions : page
  officielle `fomccalendars.htm`).

## Paires

EURUSD, USDJPY, GBPUSD (données 5 min Dukascopy, ts = barre OPEN, UTC).

## Timing (par paire, par annonce)

- `T0`   = premier OPEN de barre 5 min >= release_ts (UTC).
- `T30`  = OPEN de la première barre >= T0 + 30 minutes.
- `T120` = OPEN de la première barre >= T0 + 120 minutes.

## Règle de trade (aucune information future)

- `INITIAL_MOVE = T30 - T0`.
- Si `INITIAL_MOVE > 0` : LONG la paire à T30.
- Si `INITIAL_MOVE < 0` : SHORT la paire à T30.
- Si `INITIAL_MOVE == 0` : aucun trade.
- Sortie à T120.
- La direction est connue AVANT l'entrée (T30 précède T120).

## Coûts

- NORMAL = 2 pips round-trip.
- STRESS = 4 pips round-trip.
- Aucun autre coût testé.

## Fenêtre V1

- 2019-01-01 → 2023-01-01 EXCLUS.
- Entrée ET sortie doivent être dans V1, sinon l'événement est exclu
  pour la paire concernée.
- Aucune donnée 2023+. V2_ACCESSED=NO. OOS_ACCESSED=NO.

## Table commune

Une ligne = une réunion FOMC. Colonnes : EVENT_DATE, RELEASE_TS,
EURUSD_INITIAL_30M, USDJPY_INITIAL_30M, GBPUSD_INITIAL_30M,
{pair}_CONT_30_120_GROSS, puis NET_NORMAL / NET_STRESS par paire.
POOLED = moyenne équipondérée des trois paires. Les trois jambes du même
FOMC restent ensemble (unité = événement) dans toutes les statistiques.

## Statistiques (calculées UNE FOIS)

N_EVENTS ; gross/net moyen par paire ; POOLED_GROSS ;
POOLED_NET_NORMAL ; POOLED_NET_STRESS ; MEDIAN_NET_NORMAL ;
WIN_RATE_NET_NORMAL ; BY_YEAR_NET_NORMAL ;
REMOVE_BEST_EVENT_NET_NORMAL (moyenne POOLED net après retrait du
meilleur événement) ; paired bootstrap par événement (2000 tirages,
seed 42) → PAIRED_CI95_NET_NORMAL (percentile 2.5/97.5).

## Critères gelés

P032R_V1_STRONG si :
- POOLED_NET_NORMAL >= +5 pips/événement, ET
- au moins 2/3 paires moyenne NETTE positive, ET
- REMOVE_BEST_EVENT_NET_NORMAL > 0, ET
- au moins 3/4 années positives (NET_NORMAL), ET
- borne basse CI95 net > 0.

P032R_V1_SUPPORTIVE si les trois premiers critères sont remplis
mais la CI croise zéro.

P032R_V1_REJECT si :
- POOLED_NET_NORMAL < +5 pips, OU
- moins de 2/3 paires nettes positives, OU
- REMOVE_BEST_EVENT_NET_NORMAL <= 0.

+1/+2 pips statistiquement intéressants ne comptent pas : seuil
économique +5 pips.

## Fail fast

En cas de REJECT : STOP immédiat. Aucune variante, aucun retrait
d'année, aucune modification de fenêtre, pas de V2, pas d'audit
supplémentaire. Un bug pouvant changer le verdict est corrigé ; un
détail cosmétique est documenté et STOP.
