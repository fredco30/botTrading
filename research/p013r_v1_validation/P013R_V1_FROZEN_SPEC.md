# P013R_V1_FROZEN_SPEC — critères de validation V1 (gelés AVANT exécution)

Statut : PRÉ-ENREGISTREMENT. Ce fichier est commité AVANT toute lecture de
données V1 (commit 1 de la branche `research/p013r-v1-validation` ; les
résultats viendront dans le commit 2). La règle P013R est gelée définitivement
; Discovery (2010-2018, classification WEAK) est terminée et ne peut plus
servir à modifier quoi que ce soit ci-dessous.

## Règle gelée (identique à hypothesis_ledger.csv P013R)

- Univers : USDJPY, EURJPY, GBPJPY (les trois, aucune sélection).
- Direction : LONG XJPY.
- Événement : DERNIER jour FX ouvré de chaque mois (calendrier daily de chaque
  paire, traité indépendamment puis dates communes intersectées).
- Entrée : close daily du dernier jour FX ouvré du mois.
- Sortie : close daily du jour de marché suivant.
- Coût NORMAL : 2 pips aller-retour ; sensibilité STRESS : 4 pips.
- Pooling : moyenne équipondérée des trois paires sur la table de dates
  COMMUNES ; aucune pondération optimisée.
- Aucun filtre, aucun seuil, aucune sélection d'année/paire, aucun changement
  de direction/horaire, pas de stop/TP, pas de money management.

## Fenêtre V1

[2019-01-01 00:00 UTC, 2023-01-01 00:00 UTC) — bornée par gate.py.
Censure de frontière OBLIGATOIRE : entrée ET sortie intégralement dans V1 ;
le dernier jour de marché de décembre 2022 NE PEUT PAS utiliser un close de
janvier 2023 → événement censuré (exclu). Aucun prix de V2 ne contribue à V1.

## Statistiques gelées

N_COMMON ; POOLED_GROSS / NET_NORMAL / NET_STRESS ; PAIRED_CI95_GROSS /
NET_NORMAL / NET_STRESS ; PAIRED_P_GROSS / P_NET_NORMAL ; MEDIAN_GROSS /
NET_NORMAL ; WIN_RATE_GROSS / NET_NORMAL ; REMOVE_BEST_EVENT_NET_NORMAL ;
REMOVE_BEST_3_EVENTS_NET_NORMAL ; BY_YEAR_POOLED_GROSS / NET_NORMAL ;
POSITIVE_YEARS_NET_NORMAL ; YEAR_BLOCK_CI95_GROSS / NET_NORMAL (bootstrap
apparié ET year-block : 2000 réplications, seed 42 ; unité de resampling =
l'EVENT_DATE entière — les trois paires sont toujours tirées ensemble ;
year-block = version corrigée à multiplicité). Résultats par paire rapportés
mais JAMAIS sélectionnés a posteriori.

## Critères de verdict — GELÉS AVANT CALCUL

- V1_STRONG_CONFIRMATION si :
  POOLED_NET_NORMAL > 0
  ET au moins 2/3 paires ont GROSS_MEAN > 0
  ET REMOVE_BEST_EVENT_NET_NORMAL > 0
  ET borne basse PAIRED_CI95_NET_NORMAL > 0.
- V1_SUPPORTIVE_BUT_WEAK si :
  POOLED_NET_NORMAL > 0
  ET au moins 2/3 paires ont GROSS_MEAN > 0
  ET REMOVE_BEST_EVENT_NET_NORMAL > 0
  MAIS l'IC95 net NORMAL croise zéro.
- V1_REJECT si l'un des critères structurels échoue :
  POOLED_NET_NORMAL <= 0 OU moins de 2/3 paires gross positives OU
  REMOVE_BEST_EVENT_NET_NORMAL <= 0.

Le coût STRESS est une information de robustesse, PAS un critère.

## Conséquences

Quel que soit le verdict : STOP après le rapport. V2 (2023-01-01 → 2026-04-08)
reste VERROUILLÉE — décision de revue humaine uniquement. OOS protégée
(2026-04-09 → 2026-07-24) interdite. Aucune tentative de sauvetage, aucun
ajustement après lecture des résultats.
