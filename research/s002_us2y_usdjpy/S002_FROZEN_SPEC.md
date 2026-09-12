# S002_FROZEN_SPEC — US 2Y RATE SHOCK → USDJPY DIRECTIONAL TRADE

Discovery only. Fail fast. Une seule règle, une seule exécution, aucun paramètre alternatif.

## Origine
Piste P026 (research/phenomena_discovery_v1/hypothesis_catalog.md) : choc DGS2 >= 3 bp →
réaction USDJPY même direction, ~ +3.9 pips J+1, ~ +8.2 pips J+5.

## Fenêtre
Discovery : 2010-01-01 inclus → 2019-01-01 exclus. 2019+ interdit. Protected OOS interdit.

## Données
- FX : USDJPY15.csv (dépôt officiel).
- Taux : data_raw/official/DGS2.csv (US Treasury 2Y CMT, FRED).

## Causalité (bloquante)
Le signal d'une entrée FX provient EXCLUSIVEMENT du dernier changement DGS2 dont la date
est STRICTEMENT antérieure au jour d'entrée. Aucun same-day lookahead. Jamais de valeur
DGS2 du jour utilisée avant publication.

## Signal
Deux observations DGS2 consécutives :
RATE_CHANGE_BP = (DGS2_latest - DGS2_previous) × 100.
- >= +3 bp → LONG USDJPY
- <= -3 bp → SHORT USDJPY
- sinon → NO TRADE
Seuil exactement 3 bp (P026). Aucun autre seuil.

## Entrée
ENTRY = OPEN de la première journée FX STRICTEMENT postérieure à la date du RATE_CHANGE.
Premier open disponible de cette journée (barres 15m). Pas d'entrée rétroactive.

## Sortie
EXIT = OPEN de la 5e journée FX suivant l'entrée (jours FX avec données uniquement).
Pas de stop, pas de TP, pas de trailing, pas de pyramide. Horizon temporel J+5.

## Coûts
GROSS. NORMAL = 2 pips round-trip. STRESS = 4 pips round-trip. Pip USDJPY = 0.01.

## Conflits
Une seule position à la fois. Signal pendant position ouverte → IGNORÉ. Pas de flip,
pas d'empilement.

## Métriques (exhaustif, rien d'autre)
N_TRADES, TRADES_PER_YEAR, GROSS_MEAN_PIPS, NET_NORMAL_MEAN_PIPS, NET_STRESS_MEAN_PIPS,
MEDIAN_NET, WIN_RATE, AVG_WIN, AVG_LOSS, PROFIT_FACTOR_NORMAL, TOTAL_NET_PIPS,
MAX_DRAWDOWN_PIPS, MAX_CONSECUTIVE_LOSSES, BY_YEAR (N, NET_PIPS, MEAN_NET, PF),
POSITIVE_YEARS, REMOVE_BEST_1_PERCENT_NET_MEAN, bootstrap par trade (2000, seed 42)
→ CI95_MEAN_NET_NORMAL.

## Critères S002_DISCOVERY_PROMISING (TOUS requis)
- NET_NORMAL_MEAN_PIPS >= +5
- PROFIT_FACTOR_NORMAL >= 1.20
- POSITIVE_YEARS >= 6/9
- REMOVE_BEST_1_PERCENT_NET_MEAN > 0
- TOTAL_NET_PIPS > 0
CI informative seulement.

## Fail fast
Si NET_NORMAL_MEAN <= 0 OU PF <= 1.0 OU REMOVE_BEST <= 0 → REJECT et STOP immédiat.
Aucune variante (seuils 2/4 bp, J+1/J+3/J+10, autres paires, filtres, stop, target,
inversion, pyramide) ne sera testée.

## Bug policy
Corrections autorisées uniquement : lookahead DGS2, alignement dates, sens LONG/SHORT,
pip USDJPY, coûts, frontière Discovery, erreur changeant le verdict. Pas de cosmétique.
