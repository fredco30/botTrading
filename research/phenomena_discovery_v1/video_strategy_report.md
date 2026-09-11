# P000 — VIDEO STRATEGY REPORT (phenomena-discovery-v1)

Source : https://youtu.be/tLEcVa1FxzM — PBInvesting, « This ONLY
One-Trade-Per-Day Strategy Works Everyday For Me » (18:14, 2026-07-26).
Règles reconstruites : video_strategy_spec.md (transcript archivé).
Marché original : actions US ; testé sur proxy index S&P 500 CFD
(USA500IDXUSD, 2011-09-19 → 2026-04-08, hors OOS). Résultats bruts :
video_strategy_results.json ; réplication : p000_replication_usatech.json.

## 1. Ce qui a été testé

| Variante | Description | Événements (Disc/V1/V2) |
|---|---|---|
| P000A LEVEL_RETEST | cassure PMH/PML confirmée par clôture 5 min, entrée au retest avec reprise, stop sur clôture dans la zone, trim 50 % au nouvel extrême du jour, reliquat EMA8, flat en fin de journée | 337 / 280 / 215 |
| P000B VWAP_RETEST | même mécanique mais retest de VWAP quand VWAP a déjà franchi le niveau pre-market (règle explicite de la vidéo) | 96 / 71 / 66 |
| P000C TRANSFER FX | range asiatique [23:00-07:00 UTC] → cassure London + retest (transposition session), EURUSD/GBPUSD/USDJPY | ≈530-590 / 240-290 / 200-235 par paire |

Zéro optimisation. Règles EXTERNALLY_PREREGISTERED. Coûts : voir
methodology.md (FX 2 pips, US 1.0 pt aller-retour en NORMAL).

## 2. Signal brut (fill → open futur), P000A sur USA500 (points d'indice)

| Split | h5m | h15m | h30m | h60m | h120m |
|---|---|---|---|---|---|
| DISCOVERY | +0.23 (P=.001) | +0.22 (P=.03) | −0.03 (P=.92) | −0.36 (P=.11) | +0.02 (P=.79) |
| V1 | +0.94 (P=.00) | +1.02 (P=.00) | +1.23 (P=.04) | +1.55 (P=.14) | +1.04 (P=.39) |
| V2 | +0.89 (P=.01) | +1.12 (P=.00) | +0.76 (P=.04) | +2.30 (P=.00) | +0.42 (P=.64) |

Lecture : un micro-momentum de quelques minutes après le fill existe partout
(+0.2 à +1.1 en 5-15 min), mais il est QUASI NUL sur Discovery aux horizons
30-120 min et devient positif en V1/V2 → instabilité temporelle, pas un
phénomène stable. Réplication USATECH : DISCOVERY h60m +0.83 (P=.70),
V1 +0.26 (P=.97) → NON RÉPLIQUÉ ; le V2 « +13.6 » est un artefact de régime
(tendance tech 2023-2026, sensibilité outlier forte).

## 3. Stratégie (net de coûts), P000A USA500

Gross moyen/trade : DISCOVERY +0.04 pt → NET −0.46 (LOW) / −0.96 (NORMAL).
V1 gross +1.01 → NET ≈ 0.00 à NORMAL. V2 gross +1.43 → NET +0.43 à NORMAL,
−1.07 à STRESS. ~50 % des trades sortent au breakeven (BE_STOP), le
« profit engine » revendiqué ne se matérialise pas : le profil win rate
rapporté (~70 %) et les RR 1:5/1:7 de la vidéo NE SE REPRODUISENT PAS
(WR stratégie 21-44 % selon coûts ; sorties EMA8 majoritairement modestes).

## 4. P000B (VWAP) — meilleure sur Discovery, non robuste

RAW : DISCOVERY +0.42→+1.56 (P≤.006), V1 +0.94→+6.01 (P≤.005), V2 signes
mêlés (h120m −0.77, P=.10) → INCONCLUSIVE/instable. STRATEGY net : positif
en V1 à LOW/NORMAL (+1.54/+1.04), négatif ailleurs. La variante VWAP de la
vidéo est MEILLEURE que le retest de niveau sur 2012-2021 mais s'effondre en
2023-2026 → non robuste.

## 5. P000C (transfer FX) — micro-momentum 5 min seulement

RAW h5m positif 3/3 paires, tous splits (+0.16 à +1.30 pip, P≈.00) — même
signature que P021/P008 (traces de microstructure). À 30-120 min ≈ 0
(EURUSD/USDJPY) et GBPUSD V2 DEVIENT NÉGATIF (−2.3 à −2.9 pips, P=.005).
STRATEGY net à NORMAL : négatif 3/3 paires sur Discovery et V1/V2.
→ VIDEO_STRATEGY_TRANSFER_TO_FX = NOT_PROMISING.

## 6. VERDICTS

VIDEO_STRATEGY_RAW_EDGE=INCONCLUSIVE
 (Discovery plat aux horizons utiles ; positif V1/V2 mais instable, non répliqué cross-marché)
VIDEO_STRATEGY_NET_EDGE=NO
 (net ≤ 0 à NORMAL sur Discovery ; ≈0 V1 ; +0.43 V2 fragile au coût STRESS)
VIDEO_STRATEGY_ROBUST=NO
 (échec Discovery, échec coût STRESS, échec réplication USATECH Discovery/V1)
VIDEO_STRATEGY_TRANSFER_TO_FX=NOT_PROMISING
 (gross 5 min < coûts ; inversion de signe GBPUSD V2)

## 7. Ce que la vidéo a de réel (et ce qui n'est pas démontré)

RÉEL : (a) le respect d'une cadence 1 trade/jour élimine l'overtrading —
discipline, pas edge statistique ; (b) un micro-drift post-retest de quelques
minutes/pips existe (visible 3/3 marchés FX et 3/3 splits US) mais est
d'ordre de grandeur inférieur aux coûts de détail ; (c) le mécanisme
« accumulation overnight → cassure → retest » est cohérent avec la
microstructure (Osler, Admati-Pfleiderer — literature_review.md).
NON DÉMONTRÉ : le WR ~70 %, les RR 1:5-1:14 « tous les jours », et
l'amélioration par EMA8/pyramide (la pyramide était d'ailleurs interdite en
première validation par la mission — condition P000_BASE_EDGE_POSITIVE=NO).

## 8. Limites de notre test

Proxy CFD au lieu d'actions individuelles (univers réel de la vidéo) ;
VWAP=TWAP fallback ; trim 50 %/BE interprétés ; intraday bar-level. Ces
limites pénalisent la FIDÉLITÉ mais les conclusions de robustesse (instable
dans le temps, non répliqué) ne dépendent pas de ces choix.
