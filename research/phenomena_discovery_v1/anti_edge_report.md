# ANTI-EDGE REPORT — phenomena-discovery-v1

Protocole (methodology.md §7) : GROSS_DIRECTIONAL_EXPECTANCY d'abord ; un
signal dont l'espérance BRUTE est négative et stable sur Discovery devient
ANTI_EDGE_CANDIDATE ; on crée INVERTED_SIGNAL = −ORIGINAL sans rien changer ;
la décision d'inversion se prend UNIQUEMENT sur Discovery ; puis freeze →
V1 → V2. Résultats détaillés : anti_edge_results.json, phenomena_screen.json.

## Signaux testés en gross (Discovery, 2010-2018)

| Signal | EURUSD | GBPUSD | USDJPY | Verdict |
|---|---|---|---|---|
| P028 EMA5/20 cross M15 (h60m) | −0.02 (P=.89) | −0.55 (P=.00) | −23.9 (P=.00) | incohérent 3/3 → non candidat |
| P029 Donchian 48 M15 breakout (h120m) | −0.77 (P=.01) | −0.50 (P=.12) | −76.6 (P=.00) | gross négatif 3/3 → CANDIDAT |
| P021 runs 4×5m continuation (h5m) | −0.18 (P=.00) | −0.31 (P=.00) | −0.16 (P=.00) | trace fade 3/3 mais ≈0.2 pip < coûts |
| P008 vol-shock 3ATR continuation (h5m) | −0.12 (P=.60) | −0.58 (P=.00) | −0.31 (P=.15) | trace fade, < coûts |
| P005 London first-hour continuation (h60m) | −0.97 (P=.04) | −0.63 (P=.23) | +0.15 (P=.78) | incohérent 3/3 → non candidat |
| P007 round-number continuation (h15m) | −0.27 (P=.02) | −0.37 (P=.00) | −0.02 (P=.82) | incohérent 3/3 → non candidat |

## P029 — evaluation du signal inversé (fade des breakouts Donchian 48 M15)

INVERTED gross (pips/event) :

| Split | EURUSD | GBPUSD | USDJPY |
|---|---|---|---|
| DISCOVERY | +1.2 (7/9 ans >0) | +2.0 (6/9) | +52.5 (5/9 ans, −260 à +503 !) |
| V1 | +2.0 (4/4) | +0.8 (3/4) | −66.1 (0/4) |
| V2 | +0.5 (2/4) | +1.2 (3/4) | −201.0 (2/4) |

NET à NORMAL (2 pips A-R) : EURUSD −0.8 / 0.0 / −1.5 ; GBPUSD 0.0 / −1.2 /
−0.8 ; USDJPY n/a (instable).

## VERDICTS

ANTI_EDGES_TESTED=6 familles de signaux (P005, P007, P008, P021, P028, P029)
ANTI_EDGE_CANDIDATES=1 (P029 : espérance brute négative 3/3 marchés)
ANTI_EDGE_SURVIVORS=0

Justification : l'inversion P029 n'est PAS net-positive à NORMAL (≤ +2 pips
brut ≈ coûts), et la composante USDJPY du Discovery est un artefact de régime
2010-2011 (mean-reversion post-crise) qui INVERSE en 2013-2014 (−260 pips)
et en V1/V2 — exactement le blow-up de régime attendu d'un fade de breakout.
Conformément au protocole : pas de V1 ouverte sur ce candidat gelé, faute de
gate Discovery franchie (stabilité temporelle + coûts).

## Observations de microstructure (pas des candidats, documentées pour mémoire)

- Fade des runs 5-min et des chocs 3-ATR : +0.15 à +0.6 pip d'espérance brute
  3/3 paires — signe robuste, amplitude 10-20× sous les coûts NORMAL. Cohérent
  avec la littérature (reversion mécanique de micro-flux). Classé observation.
- Continuation après round-number cross : légèrement négative (rejet) sur
  EUR/GBP — trace Osler, non tradable.
