# Hypothèses rejetées — mission H1/H4 multi-paires

Toutes les conclusions portent sur la fenêtre protégée
[2010-01-01, 2026-04-09) avec validation gelée en deux étapes.

| # | Hypothèse | Mechanisme | Raison du rejet |
|---|---|---|---|
| F1 | Time-series momentum (24-192h H1, 6-48 H4) | continuation de tendance | ≈ 0 pip après NORMAL en agrégat ; USDJPY systématiquement négatif |
| F2 | Donchian breakout (20/40/80) | breakout | Négatif ou non robuste ; l'écran initial « +50 pips / 87 % » était un bug de lookahead (signal-bar body), corrigé |
| F3 | Trend EMA + pullback ATR-normalisé (20/100, 50/200) | pullback continuation | Négatif ou nul sur les 3 paires |
| F4 | Trend H4 + entrée H1 (multi-TF) | multi-TF | Négatif ou nul |
| F5 | Compression de volatilité → breakout (ATR12/48 ≤ 0.85) | compression → expansion | Après rerun corrigé (single shift) : positif en agrégat VAL1 (+1.01) mais **porté par USDJPY seul (1/3 paires) → GATE FAIL en VALIDATION_1** → REJECT (le run initial, invalidé par un double shift, l'avait fait entrer en V2 avec −0.41) |
| F6 | Mean reversion z-score (SMA 20/50, z 1.5-2.5) | retour à la moyenne | Meilleur candidat DISCOVERY (EURUSD H4 +9.8) mais 1 paire seule → exclu ; la variante multi-paires H1 s'effondre en VALIDATION_1 rerun corrigé (−3.88, 0/3 paires) → REJECT |
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

## Correction du double décalage d'exécution (revue post-mission)

La revue indépendante a détecté que VALIDATION_1/2 appliquaient DEUX
décalages d'exécution (dans `evaluate_window` puis dans `event_returns`)
alors que DISCOVERY n'en appliquait qu'un — les deux chemins ne mesuraient
pas la même stratégie. Corrigé par une convention unique (RAW signal dans
les générateurs ; `event_returns()` = seul point de conversion), verrouillée
par les tests `TestExecutionShiftParity` (k → k+1, jamais k+2 ; parité
DISCOVERY/VALIDATION sur événements et rendements). Le DISCOVERY (un seul
shift) reste la référence inchangée ; les résultats V1/V2 précédents sont
INVALIDATED_BY_DOUBLE_EXECUTION_SHIFT et remplacés par le rerun :
- C1 F6 mean-reversion H1 : V1 = −3.88 pips après NORMAL, 0/3 paires → REJECT.
- C2 F5 vol-compression breakout H1 : V1 = +1.01 pips après NORMAL mais
  1/3 paires porteuses → GATE FAIL → REJECT. VALIDATION_2 non exécutée.
