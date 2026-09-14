# M1_PREREGISTRATION — figé AVANT toute exécution de backtest

Statut : SPÉCIFICATION GELÉE. Ce fichier est écrit avant le premier run du moteur.
Toute modification après la première exécution devra être documentée comme déviation
post-hoc. Aucun paramètre historique n'est modifié. Aucune sous-période ne sera
sélectionnée après lecture des résultats.

---

## 1. PÉRIODE TESTÉE (exacte)

- Données intrabar autorisées : du 2010-01-04 00:00 (server) au 2018-12-31 23:45 inclus.
- 2019+ : interdit. Protected OOS : interdit.
- Premières entrées possibles seulement après warm-up complet (§8).

## 2. SOURCE DE DONNÉES (exacte)

- Fichier : `data_raw/EURUSD15_full.csv` (export MT4 M15, OHLC **BID uniquement**, ticks/volume en dernière colonne — ignorés).
- SHA256 fichier complet : `8c2dd952d2a8f8d22d350549be714879db5bf06e024c44592e0c5dbfa6f81792`
- Slice 2010-2018 extrait vers `research/legacy_bots_m1/data/EURUSD15_2010_2018.csv` :
  222,613 lignes ; SHA256 `a8276a959269b2cae9c45bd26370f51ff96c932c7cbea71a1ebd8b82b59b9bd0`
- H1 dérivé causalement des barres M15 (agrégation OHLC exacte : open=1re M15, close=dernière M15, high=max, low=min). Un bucket H1 est « clos » dès qu'une barre M15 d'une nouvelle heure s'ouvre.
- Fuseau : timestamps serveur MT4 utilisés tels quels (tous les filtres horaires du code original sont en heure serveur).

## 3. TIMEFRAME

- Entrée/decision : M15. Tendance : H1. Identique à l'original (r_TrendTF=H1, r_EntryTF=M15).

## 4. SIGNAL EXACT (implémentation canonique unique, portage 1:1 du MQL4)

Les fonctions `GetTrendDirection()` et `CheckEntry()` sont identiques au caractère près
dans `EMA_Pullback_EA.mq4` et `EMA_Pullback_pyramid.mq4` (vérifié en M0). Une seule
implémentation Python canonique est appelée par les deux stratégies.

Évalué à l'OPEN de chaque nouvelle barre M15 b (prix de décision = open[b]) :

1. TENDANCE H1 (comportement « forming bar » historique CONSERVÉ, non corrigé) :
   - EMA50_H1 sur buckets H1 clos ; EMA à l'index B-1 = dernier bucket clos.
   - ema_now = EMA50_H1 forming(0) = EMA[B-1] + (2/51)×(prix_décision − EMA[B-1]).
   - ema_prev = EMA50_H1 au shift TrendBars=5 → valeur EMA du bucket clos B-5.
   - close_tf = prix_décision.
   - LONG si close_tf > ema_now ET ema_now > ema_prev ; SHORT si strictement miroir.
2. PULLBACK M15 (barre 2 = b-2) : LONG si low[b-2] <= EMA20_M15[b-2] ; SHORT si high[b-2] >= EMA20_M15[b-2] (EMA sur barres closes, série causale standard).
3. REJET M15 (barre 1 = b-1) :
   - ema20_forming = EMA20_M15[b-1] + (2/21)×(prix_décision − EMA20_M15[b-1])  ← comparaison historique « close[1] vs EMA20 forming » CONSERVÉE.
   - LONG : close[b-1] > ema20_forming ET close[b-1] > open[b-1].
   - SHORT : miroir strict.
   - body1/range1 >= 0.60 (si range1 > 0) ET body1 > body2 (corps = |close−open|).
4. RSI(14) Wilder M15 sur la barre close b-1 : pas d'achat si RSI > 70 ; pas de vente si RSI < 30.
5. SL : LONG sl = min(low[b-1..b-SL_SwingBars]) − 2 pips ; SHORT sl = max(high[b-1..b-SL_SwingBars]) + 2 pips.
6. slDist (en prix, depuis le prix d'entrée ask en mode réaliste, bid en mode historique) ; trade refusé si slDist_pips < 15 ou > 25.
7. TP = entrée ± MinRR × slDist (MinRR = 2.5).
8. Filtres actifs (tous deux EAs) : IsPullbackHealthy → OFF (UsePullbackSizeFilter=false) ; IsStructureIntact → OFF (UseStructureFilter=false).

Ordre des gates rejetant un trade (identique à OnTick→CheckEntry original) :
session → spread → jour bloqué → heure bloquée (+combos) → ATR → distance EMA50 →
trade ouvert existant (>=1 → skip) → compteur journalier (>=2 → skip) → signal.

## 5. PARAMÈTRES EXACTS (gelés, historiques — aucune modification)

Communs BOT A et BOT B (source : `EMA.set` + defaults `EMA_Pullback_pyramid.mq4` +
`presets/EMA_Pullback_pyramid_EURUSD.set`, tous concordants) :

| Paramètre | Valeur |
|---|---|
| RiskPercent | 1.0 |
| MaxSpreadPips | 3.0 |
| MinRR | 2.5 |
| MinSL_Pips / MaxSL_Pips | 15 / 25 |
| TrendEMA_Period / TrendBars | 50 / 5 |
| EntryEMA_Period | 20 |
| SL_SwingBars | 3 |
| RSI_Period / RSI_OB / RSI_OS | 14 / 70 / 30 |
| London / NY (heure serveur) | 8-12 / 13-17 |
| UseBreakeven / BE_Trigger_R | true / 1.5 |
| MaxTradesPerDay | 2 |
| UseATRFilter / ATR_Period / ATR_Min/MaxPips | true / 14 / 9 / 19 |
| UseEMA50DistFilter / MaxEMA50DistPips | true / 30 |
| UsePullbackSizeFilter / UseStructureFilter | false / false |
| BlockFriday / BlockHour13 / BlockedHours | true / true / "13" |
| BlockToxicCombos (14h×Mar, 11h×Lun, 14h×Jeu, 16h×Lun) | true |
| ReduceThursdayRisk / ThursdayRiskMult | true / 0.5 |

BOT A (baseline) : aucun multiplicateur (mult=1 partout). Magic 20250407 (irrelevant au replay).
BOT B (pyramid v1 SAFE) : MaxStreakLevel=2 ; L0=1.0, L1=4.0, L2=2.5 (PyramidMode=SAFE).

## 6. RÈGLES PYRAMIDALES (BOT B uniquement, portage de CheckPyramidClose)

- Win (pnl > 0) → streak = min(streak+1, 2). Loss (pnl <= 0) → streak = 0.
- Multiplicateur du prochain trade = L{streak} (streak évalué au moment de l'entrée).
- Le streak est mis à jour au moment de la clôture (tick-level à l'origine ; au replay :
  dès la simulation de sortie intra-barre, donc avant l'entrée de la barre suivante).
- Aucun reverse, aucun hedge (v1).

## 7. SIZING (portage de CalculateLotSize)

- riskMoney = AccountBalance(closed) × 1.0% × riskMult ; riskMult = ThursdayMult(0.5 si jeudi) × L{streak}.
- tickSize = 0.00001 ; tickValue = 1.0 USD (EURUSD 100k) ; lot = floor(riskMoney / (slDist_prix/0.00001 × 1.0) / 0.01) × 0.01, clamp [0.01, 100], arrondi 2 décimales.
- Dépôt initial 10 000 USD. Balance = balance clôturée (MT4 AccountBalance), pas l'equity.
- Pas de contrainte de marge modélisée (levier tester non enregistré ; documenté).

## 8. TIMING / WARM-UP

- Décision à l'open de la barre M15 b, une seule évaluation par barre (nouvelle-barre check original).
- Warm-up : première entrée admissible après >= 21 barres M15 ET >= 55 buckets H1 clos
  (convention EMA_BASE_CORE_V1 ; l'original MT4 avait l'historique 1971+, notre fenêtre
  ré-amorce l'EMA50 H1 au 1er bucket 2010 — déviation numérique négligeable après warm-up, documentée).

## 9. SPREAD FILTER & COMPORTEMENT BID-ONLY

- HISTORICAL_REPLICATION_MODE : données BID seules ; ask := bid partout (spread=0).
  Le filtre MaxSpreadPips=3 est évalué PASS (le spread tester original est inconnu —
  en-têtes des rapports supprimés avant commit ; pour tout spread tester <= 3 pips le
  filtre est sans effet). Entrées/sorties au prix BID. Aucune commission, aucun slippage.
  → reproduit la limite documentée « bid-only simulation » du M0, volontairement NON corrigée dans ce mode.
- REALISTIC_EXECUTION_MODE (§13) : les coûts sont ajoutés, les paramètres ne changent pas.

## 10. HYPOTHÈSES DE FILL (gelées, pessimistes, déclarées)

- Entrée : fill certain à open[b] (prix de décision).
- Sortie intra-barre, résolution d'ambiguïté OHLC PESSIMISTE (choix déclaré, pas le plus rentable) :
  1. Gap d'open au-delà du SL → sortie à l'open. (Gap d'open au-delà du TP → sortie à l'open.)
  2. SL et TP tous deux dans le range de la barre → SL d'abord (pessimiste).
  3. BE : si le trigger (profit >= 1.5R mesuré au BID pour un buy, à l'ASK pour un sell — ask=bid en mode historique) est atteint dans la barre et le TP n'est pas atteint, SL devient entry ± 1 pip ; si le range revenant touche ce nouveau SL dans la MÊME barre → sortie à entry ± 1 pip (pessimiste).
  4. TP atteint → sortie au TP (prix BID pour un buy, cf. code : TP buy déclenché sur Bid).
- BE modifie le SL à openPrice + 1 pip (buy) / openPrice − 1 pip (sell) — portage exact du code (`beSL = openPrice + 1*g_pipValue`).
- Un trade ouvert en début de barre peut être stoppé/TP dans cette même barre (comportement tick original).
- Un seul trade ouvert à la fois (CountOpenTrades >= 1 → skip).

## 11. MÉTRIQUES CALCULÉES (les deux modes, les deux bots)

TRADES, WIN_RATE, NET_PROFIT, PROFIT_FACTOR (somme des gains / |somme des pertes|),
MAX_DRAWDOWN_ABS et MAX_DRAWDOWN_PCT (courbe de balance clôturée, trade par trade),
EXPECTANCY_PER_TRADE (USD), AVG_WIN, AVG_LOSS, PAYOFF_RATIO (avg_win/|avg_loss|),
MAX_CONSECUTIVE_LOSSES ; et en R-multiples (R = slDist initial) : expectancy_R, somme R.
Pyramide : décomposition L0/L1/L2 (niveau au moment de l'entrée) : trades, net, PF.
PYRAMID_OVERLAY_INCREMENTAL_NET = PYRAMID_NET − BASELINE_NET.
Breakdown annuel 2010..2018 : trades, net, PF, DD (sans exclusion a posteriori).

## 12. CRITÈRES PASS / FAIL & VERDICTS (gels AVANT résultats)

Cohérence technique (tous requis) :
- NO_LOOKAHEAD / NO_FUTURE_BAR_ACCESS / SIGNAL_TIMING_AUDITED / BASE_SIGNAL_IDENTITY /
  TRADE_ACCOUNTING / PYRAMID_ACCOUNTING : PASS requis (tests automatisés + audit code).
- BASE_SIGNAL_IDENTITY : le flux d'événements (timestamp, direction, sl, tp) produit par
  l'adaptateur baseline et par l'adaptateur pyramide avant money management doit être
  strictement identique sur les mêmes barres → sinon FAIL et arrêt.
- Comparabilité L0 : séquence de trades baseline ≡ séquence de trades pyramide (mêmes
  barres/Directions/SL/TP ; seuls les lots diffèrent) ; R-multiples identiques trade à trade.

Verdicts (appliqués séparément à chaque mode, sans re-tuning) :
- BASE_SIGNAL (sur BASELINE) :
  - BASE_SIGNAL_EDGE_SUPPORTED : PF >= 1.15 ET NET > 0 ET >= 5/9 années net > 0.
  - BASE_SIGNAL_EDGE_WEAK : non SUPPORTED ET PF >= 1.00.
  - BASE_SIGNAL_NO_EDGE : PF < 1.00.
- PYRAMID overlay (PYR vs BASE, même mode) :
  - PYRAMID_ADDS_ROBUST_VALUE : NET_pyr > NET_base ET DD%_pyr <= 1.25 × DD%_base.
  - PYRAMID_ADDS_RISK_NOT_EDGE : NET_pyr > NET_base ET DD%_pyr > 1.25 × DD%_base.
  - PYRAMID_RESULT_INCONCLUSIVE : sinon (notamment NET_pyr <= NET_base).

## 13. REALISTIC_EXECUTION_MODE (modèle de coûts gelé MAINTENANT, exécuté seulement après sauvegarde des résultats HISTORICAL)

- Spread : médiane Dukascopy (source `E:\ResearchData\botTrading\ticks\parquet\EURUSD`,
  colonne spread_pips, partitions 2010-2018 UNIQUEMENT) agrégée par (année, heure UTC) ;
  conversion heure serveur→UTC via Europe/Helsinki (hypothèse serveur IC Markets EET/EEST,
  documentée). ask = bid + spread au moment de l'entrée ; les sorties sell et triggers BE
  sell utilisent ask = bid + spread ; sorties buy au BID (portage MT4).
- Commission : 7.0 USD / lot round-turn (IC Markets Raw ~3.5/side, documenté), déduite du PnL.
- Slippage : 0.2 pip / côté défavorable (entrée et sorties stop ; TP au prix exact).
- Signal, filtres, paramètres : STRICTEMENT inchangés vs mode historique.
- Les deux jeux de résultats restent séparés, jamais mélangés.

## 14. SHA / PROVENANCE DES SOURCES HISTORIQUES

| Fichier | SHA256 | Commit git |
|---|---|---|
| EMA_Pullback_EA.mq4 (main) | f3b9fc8934a28b3186fcad9d3b43ce3052614b39f204f7028ddd8a380f26513d | branche main @ 1ff680a (ligne ae1fa61 pour le fichier) |
| EMA_Pullback_pyramid.mq4 (main) | a6c36483a1158f0a8599b7387efe5e31579ae84d9a88c7d1393263131501118b | 08659f7 (2026-04-10, refactor EURUSD-only, champion ae1fa61) |
| EMA.set | 6bfedbc2d8a9a03c19e5d1ab29d644f5b12199c8d87ea44136ec699bc65ef0b6 | main |
| presets/EMA_Pullback_pyramid_EURUSD.set | (cross-check M0, concordant) | f9239be (2026-07-25) |
| data_raw/EURUSD15_full.csv | 8c2dd952d2a8f8d22d350549be714879db5bf06e024c44592e0c5dbfa6f81792 | main |
| slice 2010-2018 | a8276a959269b2cae9c45bd26370f51ff96c932c7cbea71a1ebd8b82b59b9bd0 | généré M1 |

## 15. AMBIGUÏTÉS ET LECTURES RETENUES (la plus fidèle au code, pas la plus rentable)

1. Spread tester inconnu → mode historique bid-only sans coût (fidèle à la limite
   documentée) ; filtre spread PASS. Ambiguïté documentée, non « corrigée ».
2. Ordre intra-barre SL/TP/BE inconnu (OHLC seul) → convention pessimiste déclarée (§10).
3. Forming H1 EMA50 & forming M15 EMA20 → CONSERVÉS en mode historique (bugs historiques
   documentés, non corrigés) ; ils seront corrigés seulement en LAYER 3 d'une mission
   future, jamais ici.
4. Amorçage EMA sur 2010 (vs 1971 dans le MT4 original) → documenté, warm-up §8.
5. Module Range présent dans EMA.set mais ABSENT du code `EMA_Pullback_EA.mq4` actuel →
   lignes inertes, ignorées (documenté M0).
