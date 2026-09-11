# SECOND-ORDER OPPORTUNITIES — phenomena-discovery-v1

Phénomènes qui prédisent la VOLATILITÉ (ou une autre caractéristique) sans
prédire la direction — utilisables pour le sizing, le vol-targeting, les
stratégies de volatilité/relative-value ultérieures.

## SO1 — Vol-shock → variance forward accrue (P009)

- Événement : |retour 5 m| > 3×ATR(96 barres) en session [07:00-19:00 UTC].
- Mesure (Discovery) : vol réalisée forward 1 h (somme |ret 5 m|, pips)
  événement vs baseline — EURUSD 47.2 vs 27.1 (RATIO 1.74) ; GBPUSD 55.5 vs
  31.3 (1.77) ; USDJPY 40.7 vs 22.2 (1.83). (phenomena_screen.json,
  P008_VOL_SHOCK_*/SECOND_ORDER.)
- USAGE : réduire la taille dans les stratégies mean-reversion immédiatement
  après un choc (les stops sont plus larges), l'augmenter pour les stratégies
  de momentum court. NE PRÉDIT PAS la direction (continuation ≈ 0, cf. P008).

## SO2 — Profil de volatilité par jour de semaine (P035)

- Mesure : vol 1 h moyenne par jour (Discovery, pips) — EURUSD :
  lundi 29.9 / mardi 32.2 / mercredi 33.5 / jeudi 34.8 / vendredi 31.9 ;
  GBPUSD : 34.0 / 36.8 / 38.6 / 39.1 / 36.5 ; USDJPY : 23.4 / 26.2 / 27.4 /
  28.0 / 26.0 — PIC JEUDI constant, lundi le plus bas (phenomena_screen.json
  P035_VOL_BY_DOW_*).
- USAGE : facteur de normalisation pour tout seuil en pips (évite le biais
  de saisonnalité de volatilité dans les règles fixes).

## SO3 — Micro-reversion 5 min comme mécanique d'exécution (P021/P008/P007)

- Trois familles indépendantes (runs 4×, chocs 3-ATR, round-numbers)
  montrent le même signe : reversion de micro-flux à ≤ 15 min, espérance
  brute +0.15 à +0.6 pip, 3/3 paires, P≈0.
- USAGE : timing d'EXÉCUTION (entrer en retrait après un spike, éviter de
  marteler un niveau rond) plutôt que signal autonome (10-20× sous les coûts
  en standalone). Candidat naturel pour un module d'amélioration d'exécution
  des futures STRATEGY_V0 (compatible avec la règle anti-money-management :
  c'est du timing, pas du lissage de perte).

## SO4 — Micro-momentum post-retest (issu de P000)

- Après un fill P000A/P000C (confirmation + retest + reprise), le drift des
  5 premières minutes est positif 3/3 marchés, 3/3 splits (+0.2 à +1.3 pip),
  puis s'évanouit.
- USAGE : valuation d'exécution (confirmer la qualité d'un fill) ; NE JUSTIFIE
  PAS de tenir la position (rien à 30-120 min de stable).


## SO5 — Compression de range → expansion de volatilité (P034, Phase 2)

- Événement : range 12 h < 0.60 (ou 0.70) × médiane mobile 30 j du range 12 h.
- Mesure (Discovery) : range forward 12 h médian vs baseline — EURUSD
  5.2 vs 4.2 pips (ratio 1.24 ; 1.29 au seuil 0.70, N=1800-2166) ; USDJPY
  3.7 vs 3.3 (1.09-1.12, N=1334-1795). phase2_results.json P034_*.
- USAGE : sizing de breakout et vol-targeting ; ne prédit PAS la direction
  (direction moyenne ≈ 0). Candidat volatilité pour une mission dédiée.
