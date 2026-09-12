# ANTI-EDGE REPORT — phenomena-discovery-v1 (audit fix v2)

Protocole (methodology.md §7) : GROSS_DIRECTIONAL_EXPECTANCY d'abord ; un
signal dont l'espérance BRUTE est négative et stable sur Discovery devient
ANTI_EDGE_CANDIDATE ; on crée INVERTED_SIGNAL = −ORIGINAL sans rien changer ;
la décision d'inversion se prend UNIQUEMENT sur Discovery ; puis freeze →
V1 → V2.

## Corrections d'audit appliquées à ce rapport

1. **Pip-size** : les écrans utilisaient /0.0001 pour toutes les paires —
   FAUX pour USDJPY (pip = 0.01). L'ancien « −76.6 pips USDJPY P029 » était
   une erreur d'échelle ×100. Corrigé via P.PIP[sym] + test synthétique
   (10 pips EURUSD ≡ 10 pips USDJPY).
2. **Fenêtre stricte** : execution_ts ∈ [DISCOVERY_LO, DISCOVERY_HI) ET
   future_ts < DISCOVERY_HI strictement (aucun prix 2019 ne peut alimenter un
   candidat Discovery) + test de frontière.
3. **entry_ts** = barre d'exécution réelle (l'ancien code enregistrait la
   barre du prix futur) + test dédié.
4. **Contamination** : les V1/V2 de P029 calculées au cycle 1 l'ont été AVANT
   toute décision de gate, avec pip faux et fuite de fenêtre :
   **P029_V1_V2_ACCESSED_PREMATURELY=YES — P029_V1_V2_CONTAMINATED=YES —
   INVALID_FOR_FRESH_VALIDATION** (conservées dans l'historique git, plus
   aucune valeur de preuve ; V1/V2 ne seront PAS relancées).

## Signaux testés en gross (Discovery recalculé, 2010-2018, pips corrects)

| Signal | EURUSD | GBPUSD | USDJPY | Verdict |
|---|---|---|---|---|
| P028 EMA5/20 cross M15 (h60m) | −0.02 (P=.89) | −0.55 (P=.00) | −0.24 (P=.00) | gross < 0 sur 2/3, ≈0 sur 1/3 ; amplitude < 1 pip → sous les coûts, non candidat |
| P029 Donchian 48 M15 breakout (h120m / h240m) | −0.77 (P=.01) / −1.18 (P=.01) | −0.50 (P=.12) / −1.37 (P=.00) | −0.77 (P=.00) / −0.90 (P=.00) | gross < 0 cohérent 3/3 → CANDIDAT |
| P021 runs 4×5m continuation (h5m) | −0.18 (P=.00) | −0.31 (P=.00) | −0.16 (P=.00) | trace fade 3/3 mais < coûts |
| P008 vol-shock 3ATR continuation (h5m) | −0.12 (P=.60) | −0.58 (P=.00) | −0.31 (P=.15) | trace fade, < coûts |
| P005 London first-hour continuation (h60m) | −0.97 (P=.04) | −0.63 (P=.23) | +0.15 (P=.78) | incohérent 3/3 → non candidat |
| P007 round-number continuation (h15m) | −0.27 (P=.02) | −0.37 (P=.00) | −0.02 (P=.82) | incohérent 3/3 → non candidat |

## P029 — évaluation de l'inversion (Discovery recalculée uniquement)

INVERTED gross (pips/event) : EURUSD +0.77 (2h) / +1.18 (4h) ;
GBPUSD +0.50 / +1.37 ; USDJPY +0.77 / +0.90.

NET à NORMAL (2 pips aller-retour) : **négatif partout**
(−1.2 / −0.8 ; −1.5 / −0.6 ; −1.2 / −1.1). NET à LOW (1 pip) : ≈ 0 ou
légèrement positif sur 2 horizons seulement — aucun profil net-positif
robuste multi-marchés/multi-horizons.

## VERDICTS

ANTI_EDGES_TESTED=6 familles (P005, P007, P008, P021, P028, P029)
ANTI_EDGE_CANDIDATES=1 (P029, gross < 0 cohérent 3/3 en pips corrigés)
ANTI_EDGE_SURVIVORS=0

Justification : l'inversion P029 ne couvre pas les coûts NORMAL sur aucun
marché/horizon (edge brut 0.5-1.4 pips vs 2 pips de friction), et le
protocole interdit de conserver un candidat dont l'espérance nette est
négative en Discovery. Gate Discovery non franchi → pas de V1 (et V1/V2
historiques de toute façon INVALID_FOR_FRESH_VALIDATION).

## Observations de microstructure (mémoire, non candidates)

- Fade des runs 5-min et des chocs 3-ATR : +0.15 à +0.6 pip brut 3/3 paires,
  P≈0 — signe robuste, amplitude 10-20× sous les coûts (voir
  second_order_opportunities.md SO3).
- Continuation après round-number cross légèrement négative EUR/GBP — trace
  Osler, non tradable.
