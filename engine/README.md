# Moteur Python bar-par-bar — EMA_Pullback_pyramid

Réimplémentation du signal de `EMA_Pullback_pyramid.mq4` **à partir des bougies brutes**,
pas à partir d'une liste de trades MT4 déjà figée.

## Pourquoi ce moteur existe

`CLAUDE.md` note :

> Les simulations Python sur trades existants sont UNRELIABLE pour le pyramid
> (l'ordre des trades change avec les filtres, ce qui casse le streak).

C'est exact, et c'est précisément le problème que ce moteur résout. Les scripts
`simul_*.py` / `analyze_*.py` rejouent un fichier `resultats_*.txt` et
réappliquent des multiplicateurs par-dessus. Ça suppose que la séquence de trades
est invariante — elle ne l'est pas. Changer un filtre change l'ordre win/loss,
donc chaque streak, donc chaque lot en aval.

Ici le streak est une **variable d'état dans la boucle**. Un changement de filtre
se propage correctement.

## Fidélité mesurée

Calibré contre trois runs MT4 distincts, sur les trois paires :

| Paire | Rapport MT4 | Trades | Écart net |
|-------|-------------|--------|-----------|
| EURUSD | `resultats_martingale_EMAPullback3ans.txt` | 113/113 | **0.000 %** |
| GBPUSD | `historique trade gbpusd 3ansV4.txt` | 78/78 | **0.024 %** |
| USDJPY | `historique trade usdjpy 3ansV2.txt` | 89/89 | 2 bougies ambiguës |

Sur EURUSD, avec le ré-export complet, la fenêtre du rapport est couverte en
entier (113 trades au lieu de 101) et l'écart tombe à zéro :

| Métrique | Moteur | MT4 | Écart |
|----------|--------|-----|-------|
| Trades | 113 | 113 | 0 |
| Net | 9 568.90 | 9 568.93 | **0.000 %** |
| PF | 2.19 | 2.19 | 0.0 % |
| WR | 56.44 % | 56.44 % | 0.0 % |
| DD max | 4.77 % | 4.77 % | 0.0 % |

- 101/101 trades appariés, **0** trade en trop ou manquant
- Prix d'entrée : erreur max **0.00 pip**
- SL placé : erreur max **0.00 pip**
- Lots : erreur max **0.00**
- Même issue (win/loss) sur **101/101**

Résidu restant ≤ $1.22 par trade, dû à l'arrondi au centime du swap par MT4 et
à `NormalizeDouble` sur le TP.

Régression : `python3 calibrate_pullback_pyramid.py --tolerance 0.1` renvoie un
code de sortie non nul si le moteur dérive.

## Modèle d'exécution (rétro-ingénieré depuis le rapport MT4)

| Élément | Valeur |
|---------|--------|
| Prix d'entrée | **open exact** de la bougie M15 |
| Spread | 2 points (0.2 pip), payé par les buys |
| Déclenchement SL/TP | sur le bid pour les buys, sur l'**ask** pour les sells |
| P&L | `(exit − entry) × dir × lots × tick_value / tick_size` |
| Commission | **aucune** (85 trades intraday réconciliés à $0.0000) |
| Swap | **−8.3433 $/lot/nuit en long, +2.5357 $/lot/nuit en short**, ×3 le jeudi |

### Le swap n'est pas négligeable

Aucun script Python du repo ne modélisait le swap. Sur ce run de 3 ans il coûte
~$110 et surtout il **retourne un trade** (2025.09.29) d'un win breakeven
(+$8.90) en perte (−$5.95). Ce trade resetait le streak, ce qui décalait tous
les niveaux de pyramide suivants. Sans le swap, le moteur affichait
`same outcome 100/101` et +0.8 % de net ; avec, on tombe à 0.006 %.

C'est aussi un biais réel sur ta stratégie : les configs qui gardent les
positions overnight sont surévaluées de ~0.83 pip/nuit en long.

### Détails MT4 reproduits

Le point technique qui casse le plus souvent une réimplémentation : l'EA lit
plusieurs valeurs H1 au **shift 0**, donc sur la bougie H1 **en cours de
formation** :

```mql4
iMA(Symbol(), PERIOD_H1, 50, 0, MODE_EMA, PRICE_CLOSE, 0)
iClose(Symbol(), PERIOD_H1, 0)
iATR(Symbol(), PERIOD_H1, 14, 0)
```

Au premier tick de la bougie M15 `i`, cette bougie H1 partielle a pour close le
prix courant, c'est-à-dire l'open de la bougie M15 `i`. Idem pour
`iMA(..., PERIOD_M15, 20, ..., 0)`. Ignorer ça décale l'EMA20 d'une bougie et
change quels pullbacks passent le filtre.

Sont aussi reproduits fidèlement :

- `iMA(MODE_EMA)` : seeding `buf[0] = price[0]` (pas un `ewm` pandas générique)
- `iRSI` : lissage Wilder amorcé par une moyenne simple
- `iATR` : **SMA** du True Range — MT4 n'utilise pas le lissage Wilder ici
- Sizing : `floor` au pas de lot, risque calculé sur la balance **clôturée**
- Breakeven à 1.5R → SL à `entry ± 1 pip`, un exit BE compte comme **win**
  et fait donc monter le streak
- Réduction de risque du jeudi (×0.5) appliquée **avant** le multiplicateur pyramide

## Utilisation

```bash
# 1. Vérifier que le moteur colle toujours à MT4
python3 calibrate_pullback_pyramid.py --tolerance 0.1

# 2. Récupérer les multiplicateurs L0/L1/L2 d'un rapport MT4 quelconque
python3 calibrate_pullback_pyramid.py --report resultats_XXX.txt --infer-mults

# 3. Balayer des paramètres, avec walk-forward automatique
python3 optimize_pullback_pyramid.py \
    --grid l1_mult=1,1.5,2,3,4,5,6,7 --grid l2_mult=1,1.5,2,2.5,3,4

python3 optimize_pullback_pyramid.py \
    --grid min_sl_pips=12,14,15,16,18 --grid max_sl_pips=22,25,28,30 \
    --grid atr_min_pips=7,9,11 --grid be_trigger_r=1.0,1.5,2.0
```

### En API

```python
from engine import core, data, report
from engine.params import Params

md = data.build("EURUSD15_cut.csv", "EURUSD60_cut.csv")
p = Params().with_mode("SAFE")           # SAFE / AGGRESSIVE / GEOMETRIC15 / FLAT
trades = core.run(md, p)                 # matrice numpy, colonnes T_* dans core
print(report.metrics(trades[:, core.T_PNL],
                     trades[:, core.T_BALANCE], p.initial_balance))
print(report.level_breakdown(trades))    # table L0 / L1 / L2
```

## Performance

**0.7 ms par backtest** sur 65 534 bougies M15, une fois le JIT chaud
(compilation ~2.5 s, mise en cache par numba).

- 864 configurations × 3 backtests (full + IS + OOS) = **2 592 backtests en 1.5 s**
- Le même balayage dans l'optimiseur MT4 : plusieurs heures

## Walk-forward intégré

`optimize_pullback_pyramid.py` classe par défaut sur `robust` =
`min(return/DD sur la 1ère moitié, return/DD sur la 2ème moitié)`.

Une config qui ne brille que sur une moitié score près de zéro. C'est la
discipline que `CLAUDE.md` réclame ("toujours tester sur 2 périodes séparées"),
appliquée mécaniquement plutôt qu'à la main.

## Limites à connaître

1. **Ordonnancement intra-bougie inconnu.** Voir la section « Bougies ambiguës »
   ci-dessus. Rare (0-3 % des trades) mais coûteux quand ça arrive : toujours
   vérifier la colonne `amb%` avant de retenir une config.

2. **Le régime domine tout, et la fenêtre de données le cache.** Avec le
   ré-export complet (`EURUSD15.csv`, M15 depuis 1999), le signal fait
   **PF 0.74 sur 2010-2019** et **PF 1.19 sur 2020-2026**, filtres retirés des
   deux côtés. Un balayage fait sur 2023-2026 optimise donc un régime, pas un
   edge intemporel. GBPUSD (2021-2026) et USDJPY (2023-2025) sont tous deux
   entièrement dans le régime favorable : leurs résultats ne sont pas des
   confirmations indépendantes.
   → Ré-exporter `GBPUSD15` et `USDJPY15` sur toute l'historique : MT4, Outils >
   Options > Graphiques > "Max. de barres dans l'historique" à 999999999,
   redémarrer, F2 pour recharger, puis exporter.

3. **Spread constant.** Le tester tournait à spread fixe 2 points. Le spread
   réel varie (rollover, news). Les configs à SL serré sont donc optimistes.

4. **Swap constant.** MT4 applique un swap unique sur tout le backtest, donc le
   moteur aussi. En réalité le différentiel de taux EUR/USD a beaucoup bougé
   entre 2020 et 2026 ; les valeurs par défaut sont calées sur 2023-2025.

5. **USDJPY : trou de 207 jours** dans `USDJPY15_cut.csv` entre 2025.09.12 et
   2026.04.07. La paire ne couvre donc que **2.6 ans exploitables**, pas 3.2.
   GBPUSD est propre sur 5.3 ans sans aucun trou.

6. **Asymétrie long/short sur USDJPY** : shorts PF 3.87 vs longs PF 1.44 (hors
   pyramide). 2023-2025 = forte hausse puis retournement ; cette asymétrie est
   probablement spécifique au régime et peut ne pas se reproduire.

## Support multi-paires

`Params.for_pair("GBPUSD")` charge un preset complet. La microstructure de
chaque paire (spread, tick value, swap) n'est **pas devinée** : elle est
extraite des rapports MT4 en réconciliant chaque lot et chaque P&L.

| | EURUSD | GBPUSD | USDJPY |
|---|---|---|---|
| Spread tester | 2 pts (0.2 pip) | 10 pts (1.0 pip) | 9 pts (0.9 pip) |
| Tick value | 1.0 | 1.0 | **0.63046** (constant) |
| Swap long $/lot/nuit | −8.3433 | −3.5088 | **+7.7671** |
| Swap short $/lot/nuit | +2.5357 | −3.8000 | −12.4791 |

Deux quirks JPY reproduits :

- Le P&L s'accumule en JPY et MT4 le convertit **au prix de sortie**
  (`inverse_quote=True`).
- Mais le dimensionnement des lots utilise un `MarketInfo(MODE_TICKVALUE)`
  **constant**, pris sur le symbole live au moment où le test a été lancé, pas
  sur le prix de la bougie historique. Vérifié : la même valeur 0.6304 dimensionne
  le trade de 2023 et celui de 2025.

## Bougies ambiguës SL+TP

Quand une bougie touche le SL **et** le TP, l'ordre des ticks est inconnu.
Trois modèles (`intrabar_model`) :

| Modèle | EURUSD | GBPUSD | USDJPY |
|---|---|---|---|
| `pessimistic` (SL gagne) | ✅ 0.0 % | ✅ 0.0 % | ❌ −37.7 % |
| `nearest` (**défaut**) | ✅ 0.0 % | ✅ 0.0 % | −20.1 % |
| `optimistic` (TP gagne) | +3.7 % | ✅ 0.0 % | ✅ 0.0 % |

Sur les 3 bougies ambiguës du corpus, MT4 en a résolu 2 en TP et 1 en SL :
aucun modèle n'est universellement correct. `nearest` (l'extrême le plus proche
de l'open est atteint en premier) est le défaut parce qu'il est le seul des
trois qu'un optimiseur ne peut pas exploiter systématiquement.

**Garde-fou** : chaque trade porte un flag `T_CONFLICT`, et
`optimize_pullback_pyramid.py` affiche la colonne `amb%` plus
`--max-conflict`. Toutes les configs champion retenues sont à **0 %** — leur
résultat ne repose sur aucun tirage au sort.

## Fichiers

| Fichier | Rôle |
|---------|------|
| `engine/indicators.py` | EMA / RSI / ATR fidèles à MT4, seeding compris |
| `engine/data.py` | Chargement CSV, alignement H1↔M15, bougie H1 en formation, poids de rollover |
| `engine/params.py` | Dataclass des inputs de l'EA + presets pyramide |
| `engine/core.py` | Boucle de simulation numba (état pyramide inclus) |
| `engine/report.py` | Parsing des rapports MT4, métriques, comparaison |
| `calibrate_pullback_pyramid.py` | Moteur vs MT4, trade par trade |
| `optimize_pullback_pyramid.py` | Grid search + walk-forward |
| `validate_pair.py` | Dossier complet d'une config : année par année, IS/OOS, niveaux, ambiguïté |
| `engine/debug.py` | Explique filtre par filtre pourquoi une bougie a été rejetée |
