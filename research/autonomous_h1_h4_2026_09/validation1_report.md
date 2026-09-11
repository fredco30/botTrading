# VALIDATION_1 — candidats gelés sur 2019-01-01 → 2022-12-31

Aucun paramètre modifié après DISCOVERY. Événements générés une seule fois
sur l'historique complet (features strictement passées), puis filtrés par
date de décision dans la fenêtre — les indicateurs ne redémarrent pas
artificiellement.

## C1 — F6 mean reversion H1 (SMA 20, z 1.5, horizon 12h)

| | N | MEAN pips | après LOW | après NORMAL | après STRESS | WIN |
|---|---:|---:|---:|---:|---:|---:|
| Agrégat | 5 419 | −1.67 | −2.67 | **−3.67** | −5.17 | 49.3 % |
| EURUSD | 1 856 | −2.28 | −3.28 | −4.28 | −5.78 | 48.0 % |
| GBPUSD | 1 843 | −2.85 | −3.85 | −4.85 | −6.35 | 49.3 % |
| USDJPY | 1 720 | +0.27 | −0.73 | −1.73 | −3.23 | 50.9 % |

**GATE : FAIL** — l'effet DISCOVERY (+1.30) s'inverse complètement
(0/3 paires positives, mean hors outliers −5.16). L'effet de
mean-reversion 2010-2018 était un artifact de période.

## C2 — F5 vol-compression breakout H1 (L 40, ratio 0.85, horizon 12h)

| | N | MEAN pips | après LOW | après NORMAL | après STRESS | WIN |
|---|---:|---:|---:|---:|---:|---:|
| Agrégat | 308 | +2.67 | +1.67 | **+0.67** | −0.83 | 50.7 % |
| EURUSD | 86 | +3.72 | +2.72 | +1.72 | +0.22 | 45.4 % |
| GBPUSD | 110 | −0.45 | −1.45 | −2.45 | −3.95 | 49.1 % |
| USDJPY | 112 | +4.94 | +3.94 | +2.94 | +1.44 | 56.3 % |

**GATE : PASS (de justesse)** — agrégat positif après NORMAL (+0.67),
2/3 paires ne contredisent pas (GBPUSD légèrement négatif), pas
d'effondrement complet, N = 308 (limite basse), mécanisme économiquement
plausible (compression de volatilité → breakout directionnel).

→ Un seul candidat passe vers VALIDATION_2 (≤ 3 autorisés).
