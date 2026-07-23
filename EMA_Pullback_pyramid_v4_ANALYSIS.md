# EMA Pullback Pyramid v4 — Champion Config + Validation Plan

## Résumé

`EMA_Pullback_pyramid_v4.mq4` = v2 + **config optimisée** (backtest Python 16 ans) +
**persistance d'état pyramide** + **kill-switch DD**. Compile : 0 erreur, 0 warning.

## Config championne (issue de ~40 000 backtests Python, EURUSD M15 2010-2026)

| Paramètre | Valeur | Note |
|-----------|--------|------|
| RiskPercent | 1.5 | vs 1.0 en SAFE |
| L0 / L1 / L2 | 0.25 / 6.0 / 3.0 | L0 = ticket d'entrée, L1+L2 = moteur |
| MinRR | 2.0 | vs 2.5 |
| SL (min/max) | 15 / 25 pips | inchangé |
| London | 8h-11h | fin avancée à 11h |
| New York | 13h-18h | étendu à 18h |
| ATR | 7-19 pips | **sensible** : ne pas mettre min=9 ni max=17 |
| SL_SwingBars | 2 | vs 3 |
| MaxTradesPerDay | 3 | vs 2 |
| RevMaxSL_Pips | 20 | resserré |
| RollingWR_Threshold | 25 | vs 40 |
| BE_Trigger_R | 2.0 | vs 1.5 |

## Résultats backtest (moteur Python, approximation M15-bar)

- **Balance : $417,859** (net +$407,859) sur $10k
- **Max DD : 37.0%**
- **PF : 1.83 | WR : 37.6% | 545 trades**
- **Années négatives : 2** (2010 -$899, 2021 -$23k) ; 14 positives
- Décomposition : L1 +$191k, L2 +$198k, L0 +$18k, REV +$0.7k

## Robustesse mesurée

- Walk-forward : 2010-2017 +$9k (DD 20%), 2018-2026 +$232k (DD 45%) → edge réel, renforcé post-2018.
- Sensible à ATR_Min=9, ATR_Max≤17, EMA50 dist≥35 → **ne pas modifier ces 3 paramètres**.
- Capital : $5k→DD 46% ; $25k→DD 21.6% ; $50k→DD 14%. **Viser ≥ $25k.**

## Nouveautés code (vs v2)

1. **Persistance** (`UsePersistence`) : streak, consecLosses, ticket, buffer rolling WR, equity peak
   sauvegardés dans des GlobalVariables (clé `EMP4_<SYMBOL>_<MAGIC>_`) à chaque changement et
   restaurés au démarrage. Évite la corruption du streak au restart du terminal/VPS.
2. **Kill-switch** (`UseKillSwitch`) :
   - `MaxDDPercent` (40) → halt total de l'EA si DD equity dépasse le seuil.
   - `DailyDDPercent` (5) → stop des nouvelles entrées pour la journée.

## ⚠️ À valider AVANT tout live (obligatoire)

Le moteur Python est une **approximation bar-par-bar M15**, pas un tick-test. À faire dans MT4 :

1. **Strategy Tester** : EURUSD M15, 2010-01 → 2026-03, "Every tick", spread réel (ou 2 pips).
2. Comparer PF / DD / nb trades / années négatives au tableau ci-dessus. Une divergence >20%
   signale un écart d'exécution à investiguer (slippage intra-barre, spread, BE).
3. **Reset des paramètres** après compilation (le cache MT4 garde les anciens inputs).
4. **Demo 4-8 semaines** avec Risk 1.0 (pas 1.5) avant tout live ; comparer chaque trade au backtest.
5. Capital live recommandé **≥ $25k**, Risk 1.0-1.5.

## Limites honnêtes

- **0 année négative n'existe pas sur ce signal** : le minimum mesuré avec >$100k est 2.
  2021 est structurellement perdant pour l'EMA pullback.
- **37% DD backtest ≈ 42-47% live** (slippage + spread). Au-delà du seuil "tradeable" de 30% à $10k.
- **Risque d'overfitting** : filtres calés sur 2019-2026. Le walk-forward rassure mais ne suffit pas.

## Fichiers

- `EMA_Pullback_pyramid_v4.mq4` — EA (compile OK)
- `champion_balanced.json` — config complète
- `bt_engine.py` / `bt_fast.py` — moteur de backtest (pure Python + Numba JIT 14ms)
- `optimize_fast.py` / `optimize_consistency.py` / `optimize_balanced.py` — optimiseurs
- `robustness.py` — sensibilité + walk-forward + capital
