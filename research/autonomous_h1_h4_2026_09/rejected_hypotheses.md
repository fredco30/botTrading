# Hypothèses rejetées — mission H1/H4 multi-paires

Toutes les conclusions portent sur la fenêtre protégée
[2010-01-01, 2026-04-09) avec validation gelée en deux étapes.

| # | Hypothèse | Mechanisme | Raison du rejet |
|---|---|---|---|
| F1 | Time-series momentum (24-192h H1, 6-48 H4) | continuation de tendance | ≈ 0 pip après NORMAL en agrégat ; USDJPY systématiquement négatif |
| F2 | Donchian breakout (20/40/80) | breakout | Négatif ou non robuste ; l'écran initial « +50 pips / 87 % » était un bug de lookahead (signal-bar body), corrigé |
| F3 | Trend EMA + pullback ATR-normalisé (20/100, 50/200) | pullback continuation | Négatif ou nul sur les 3 paires |
| F4 | Trend H4 + entrée H1 (multi-TF) | multi-TF | Négatif ou nul |
| F5 | Compression de volatilité → breakout (ATR12/48 ≤ 0.85) | compression → expansion | Survit à DISCOVERY et VALIDATION_1 (+0.67) mais **échoue VALIDATION_2** (−0.41 après NORMAL, EX99 ≈ 0, GBPUSD négatif) → REJECT final |
| F6 | Mean reversion z-score (SMA 20/50, z 1.5-2.5) | retour à la moyenne | Meilleur candidat DISCOVERY (EURUSD H4 +9.8) mais 1 paire seule → exclu ; la variante multi-paires H1 s'effondre en VALIDATION_1 (−3.67) → REJECT |
| F7 | Trend strength (|close−EMA100|/ATR ≥ 1.0-1.5) | force de tendance | 3/9 années positives minimum → ne passe pas la sélection |
| F8 | Breakout en expansion de volatilité | breakout + régime | ≈ F2, aucun gain net du filtre → couvert par le rejet de F2 |

Nouvelles familles inventées (max 3 autorisé) : **aucune lancée** — les
familles prescrites couvrent déjà les mécanismes MR / trend / breakout à
plusieurs seuils et horizons, et leurs effets DISCOVERY se sont tous
effondrés ou dilués sous les coûts en validation. Inventer une variante
supplémentaire des mêmes mécanismes n'aurait été que du data mining.

## Leçons méthodologiques

1. **Le lookahead du breakout** (mesurer depuis l'open de la bougie de
   signal) gonflait artificiellement tous les breakouts de ~40-50 pips.
   Corrigé avant validation, testé (`to_executable_side`).
2. Le découpage DISCOVERY/VALIDATION a rempli son office : les deux
   « meilleurs » effets DISCOVERY ont été tués proprement (l'un en V1,
   l'autre en V2) sans contamination des fenêtres.
3. L'effet mean-reversion existe (déjà vu en M15 : +0.2 pip) mais reste
   à chaque échelle d'un ordre de grandeur sous les coûts réalistes.
