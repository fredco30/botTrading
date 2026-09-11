# DISCOVERY report — écran F1-F8 sur 2010-01-01 → 2018-12-31

Périmètre : 126 configurations (7 familles × grilles courtes × H1/H4 × 3
paires ; F4 sur H1 uniquement). 484 lignes de résultats (config × paire ×
horizon) dans `family_screen.csv`.

Horizons : H1 = 4/12/24/48 barres (4h/12h/24h/48h) ; H4 = 3/6/12/24 barres
(12h/24h/48h/96h). Toutes les moyennes citées sont **après NORMAL_COST
(2.0 pips aller-retour, SYNTHETIC)**.

## Lecture par famille

| Famille | Mécanisme | Résultat DISCOVERY |
|---|---|---|
| F1 time-series momentum (24-192h / 6-48 H4) | continuation | ≈ 0 en agrégat multi-paires (±0.1 pip) ; léger +0.9/+0.8 EURUSD/GBPUSD H4 L48, USDJPY négatif |
| F2 Donchian breakout (20-80) | breakout | Négatif à positif faible selon paire ; rien ne survit à NORMAL de façon robuste après correction du lookahead |
| F3 trend+pullback (20/100, 50/200) | pullback continuation | Négatif ou nul |
| F4 trend H4 + entrée H1 | multi-TF | Négatif ou nul |
| F5 vol compression → breakout (ATR12/48 ≤ 0.75-0.85) | compression | GBPUSD/USDJPY légèrement positifs à 12h ; EURUSD négatif |
| F6 mean reversion (|z| ≥ 1.5-2.5, SMA 20/50) | retour à la moyenne | Positif sur plusieurs configs (12h-96h), surtout EURUSD H4 (z=2.0, sma=50 : +9.8 pips) — mais **1 paire seule** |
| F7 trend strength (|close−EMA100|/ATR ≥ 1.0-1.5) | force de tendance | EURUSD/USDJPY H4 positifs faibles, GBPUSD négatif |
| F8 breakout + expansion (F2 ∧ ATR12/48 ≥ 0.9) | breakout en expansion | ≈ F2, pas d'amélioration nette |

## Candidats retenus (critères §13)

Sur 484 lignes, seules **2 configurations** satisfont tous les critères :
≥ 2/3 paires positives après NORMAL, moyenne hors top-1 % positive sur
≥ 2 paires, ≥ 4/9 années positives après coûts, N total ≥ 500 :

1. **C1 — F6 mean reversion H1** (SMA 20, z 1.5, horizon 48 barres = 48 heures)
   agrégat +1.30 pip/trade après NORMAL, N = 12 365
   (EURUSD +2.5, GBPUSD +2.8, USDJPY −1.3), 5-6/9 années positives.
2. **C2 — F5 vol-compression breakout H1** (L 40, ratio 0.85, horizon 12 = 12h)
   agrégat +1.09 pip/trade après NORMAL, N = 594
   (EURUSD −0.8, GBPUSD +0.2, USDJPY +2.9), 4-7/9 années.

Remarque d'honnêteté : le candidat EURUSD-only F6 H4 (+9.8 pips) est
exclu par la règle multi-paires — c'est précisément le type de résultat
que la discipline doit filtrer. L'ampleur des deux candidats retenus est
faible (+1.1 à +1.3 pips) : ils vont en VALIDATION_1 gelés, sans espoir
pré-établi.
