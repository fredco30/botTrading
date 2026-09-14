# M1_RESULTS — Réplication stricte des deux bots EMA originaux (2010-2018)

Statut : exécution conforme à `M1_PREREGISTRATION.md` (figé avant tout run).
Aucun paramètre modifié, aucune optimisation, aucune sous-période choisie après coup.
Résultats HISTORICAL et REALISTIC strictement séparés.

## 0. Conformité

- 2019_PLUS_ACCESSED = NO (aucun accès ; store de ticks limité aux partitions year=2010..2018)
- PROTECTED_OOS_ACCESSED = NO
- OPTIMIZATION_EXECUTED = NO
- Aucune lecture de résultats avant gèle : les verdicts du §6 suivent les seuils écrits dans le pré-enregistrement.

## 1. Données

- DATA_SOURCE = `data_raw/EURUSD15_full.csv` (export MT4 M15 OHLC BID) → slice `research/legacy_bots_m1/data/EURUSD15_2010_2018.csv`
- DATA_START = 2010-01-04 00:00 (heure serveur) · DATA_END = 2018-12-31 22:45 (dernière barre du fichier dans la fenêtre)
- DATA_ROWS = 222,613 barres M15
- SHA256 slice = `a8276a959269b2cae9c45bd26370f51ff96c932c7cbea71a1ebd8b82b59b9bd0`
- H1 dérivé causalement des barres M15 (agrégation OHLC exacte).

## 2. Tests de cohérence (tous PASS)

```
BASE_SIGNAL_IDENTITY   = PASS   (438 événements pré-MM identiques baseline/pyramide)
TRADE_STREAM_MATCH     = PASS   (428 trades identiques, seuls les lots diffèrent)
NO_LOOKAHEAD           = PASS   (40 décisions recalculées sur données tronquées : 0 divergence)
NO_FUTURE_BAR_ACCESS   = PASS
SIGNAL_TIMING_AUDITED  = PASS
TRADE_ACCOUNTING       = PASS   (baseline & pyramide, somme(pnl) == balance finale − initiale)
PYRAMID_ACCOUNTING     = PASS   (lots, niveaux de streak et sorties re-vérifiés trade à trade)
```

Preuve de séparation stricte signal/MM : SUM_R est IDENTIQUE entre baseline et pyramide
(−22.46R en historique ; −57.84R en réaliste) — mêmes trades, mêmes sorties, seuls les
multiplicateurs de lot diffèrent.

## 3. HISTORICAL_MODE_RESULTS (bid-only, spread=0, sans commission, sans slippage)

### BOT A — BASELINE (EMA_Pullback_EA, preset EMA.set)

| Métrique | Valeur |
|---|---|
| TRADES | 428 |
| WIN_RATE | 35.51 % |
| NET_PROFIT | **−$2,528.29** |
| PROFIT_FACTOR | **0.8726** |
| MAX_DRAWDOWN_ABS / PCT | $4,044.14 / 38.47 % |
| EXPECTANCY_PER_TRADE | −$5.91 (−0.0525 R) |
| AVG_WIN / AVG_LOSS | $113.97 / −$71.93 |
| PAYOFF_RATIO | 1.584 |
| MAX_CONSECUTIVE_LOSSES | 12 |

Années positives : 3/9 (2011, 2015, 2018).

### BOT B — PYRAMID v1 SAFE (L0/L1/L2 = 1.0/4.0/2.5)

| Métrique | Valeur |
|---|---|
| TRADES | 428 (identiques au baseline) |
| WIN_RATE | 35.51 % |
| NET_PROFIT | **−$1,612.69** |
| PROFIT_FACTOR | **0.9570** |
| MAX_DRAWDOWN_ABS / PCT | $4,976.45 / **45.87 %** |
| EXPECTANCY_PER_TRADE | −$3.77 (−0.0525 R, identique au baseline) |
| MAX_CONSECUTIVE_LOSSES | 12 |

Décomposition pyramidale obligatoire :

| Niveau | TRADES | NET | PF |
|---|---|---|---|
| L0 | 276 | −$2,592.01 | 0.81 |
| L1 | 94 | **+$4,286.25** | 1.26 |
| L2 | 58 | −$3,306.93 | **0.58** |

- BASELINE_NET = −$2,528.29
- PYRAMID_NET = −$1,612.69
- PYRAMID_MINUS_BASELINE = **+$915.60**
- PYRAMID_OVERLAY_INCREMENTAL_NET = +$915.60 (l'overlay réduit la PERTE, il ne crée pas de gain)

### Comparaison temporelle (diagnostique, aucune exclusion) — voir `yearly_breakdown.csv`

| Année | Base trades | Base net | Base PF | Pyr net | Pyr PF |
|---|---|---|---|---|---|
| 2010 | 11 | −96 | 0.84 | −454 | 0.72 |
| 2011 | 6 | +136 | 1.39 | +767 | 2.81 |
| 2012 | 55 | −193 | 0.94 | −643 | 0.89 |
| 2013 | 64 | −1,436 | 0.61 | −807 | 0.87 |
| 2014 | 60 | −1,372 | 0.55 | −917 | 0.81 |
| 2015 | 51 | +1,063 | 1.55 | +739 | 1.15 |
| 2016 | 53 | −965 | 0.58 | −858 | 0.79 |
| 2017 | 66 | −300 | 0.88 | −1,407 | 0.75 |
| 2018 | 62 | +636 | 1.27 | +1,968 | 1.45 |

## 4. REALISTIC_EXECUTION_MODE (spread médian Dukascopy par année×heure, commission $7/lot RT, slippage 0.2 pip/côté — paramètres de stratégie inchangés)

### BOT A — BASELINE

| Métrique | Valeur |
|---|---|
| TRADES | 430 |
| WIN_RATE | 34.88 % |
| NET_PROFIT | **−$4,586.96** |
| PROFIT_FACTOR | **0.7475** |
| MAX_DRAWDOWN_ABS / PCT | $5,403.70 / 52.76 % |
| EXPECTANCY_PER_TRADE | −$10.67 (−0.1345 R) |
| MAX_CONSECUTIVE_LOSSES | 12 |

Années positives : 2/9 (2015, 2018).

### BOT B — PYRAMID v1 SAFE

| Métrique | Valeur |
|---|---|
| TRADES | 430 |
| NET_PROFIT | **−$5,492.81** |
| PROFIT_FACTOR | **0.8065** |
| MAX_DRAWDOWN_ABS / PCT | $6,909.04 / **67.46 %** |
| EXPECTANCY_PER_TRADE | −$12.77 (−0.1345 R) |

Décomposition : L0 = 280 trades, −$3,356.52, PF 0.68 · L1 = 94 trades, +$208.25, PF 1.02 · L2 = 56 trades, −$2,344.54, PF 0.57.
La commission (proportionnelle au lot ×4 en L1) absorbe la totalité du surplus L1 de la passe historique (+$4,286 → +$208).

- BASELINE_NET = −$4,586.96 · PYRAMID_NET = −$5,492.81 · **PYRAMID_MINUS_BASELINE = −$905.85**

## 5. Lecture scientifique (sans sauvetage)

1. **Le signal de base n'a pas d'edge sur 2010-2018** : −0.0525 R/trade en bid-only sans
   coûts ; −0.1345 R/trade en exécution réaliste. PF < 1 dans les deux modes, 2-3 années
   positives sur 9, DD 38-53 % pour un buy-&-hold de référence à perte.
2. **L'overlay pyramidal ne crée pas d'edge** : l'espérance en R est STRICTEMENT identique
   à celle du baseline (même signal, mêmes sorties). En historique il réduit la perte
   (+$916) parce que L1 (×4) tombe sur une séquence favorable — mais L2 (×2.5) est
   fortement perdant (PF 0.58). En réaliste, la commission proportionnelle au lot inverse
   l'avantage : l'overlay PERD $906 de plus que le baseline et porte le DD à 67.5 %.
3. **Cohérence avec l'historique M0** : les artefacts originaux montraient déjà
   « 2010-2018 ≈ flat, profit concentré 2019-2026 » (v2_ANALYSIS). La réplication 2010-2018
   montre pire que flat : négatif. La courbe historique +$34k (SAFE, 2020-2026) ne peut
   PAS être attribuée au signal sur 2010-2018 ; elle dépend de la fenêtre 2019+ (hors
   périmètre de cette mission).
4. Comportements historiques conservés (non corrigés) conformément à la mission :
   forming-H1 EMA50 pour la tendance, comparaison close[1] vs EMA20 forming, entrée à
   l'open de la barre suivante, mode bid-only sans coûts en passe historique.
   1 trade par passe fermé « eod » à la dernière barre de la fenêtre (documenté).

## 6. Verdicts (seuils gelés du pré-enregistrement, appliqués mécaniquement)

- HISTORICAL_MODE_VERDICT :
  - BASE_SIGNAL : PF 0.8726 < 1.00 → **BASE_SIGNAL_NO_EDGE**
  - PYRAMID : NET_pyr > NET_base ET DD%_pyr (45.87) <= 1.25 × DD%_base (48.09) →
    **PYRAMID_ADDS_ROBUST_VALUE** au sens LITTÉRAL du seuil gelé — avec la réserve
    explicite que les deux nets sont NÉGATIFS : « value » signifie ici « perte réduite
    de $916 », au prix d'un DD% plus élevé (38.5 → 45.9). Ce n'est pas une création
    d'edge (espérance R inchangée, PF < 1).
- REALISTIC_MODE_VERDICT :
  - BASE_SIGNAL : PF 0.7475 < 1.00 → **BASE_SIGNAL_NO_EDGE**
  - PYRAMID : NET_pyr < NET_base → **PYRAMID_RESULT_INCONCLUSIVE** (lettre du seuil) ;
    lecture factuelle : l'overlay dégrade strictement le résultat (−$906, DD 67.5 %).

## 7. Provenance

- Sources historiques et SHA : `M1_PREREGISTRATION.md` §14.
- Moteur : `research/legacy_bots_m1/m1_engine.py` ; tests : `test_m1_coherence.py`.
- Sorties : `results_baseline.csv`, `results_pyramid_safe.csv` (colonne `mode` = historical
  puis realistic, lignes historiques écrites AVANT le run réaliste et jamais modifiées),
  `yearly_breakdown.csv`, `m1_metrics_snapshot.json`, `spread_table_dukascopy.csv`
  (médianes Dukascopy, 209,682,628 ticks, partitions 2010-2018 uniquement).
- Rien n'est commité (validation finale pendante).
