# EMA_BASE_EVENT_STUDY_SPEC — pré-enregistrement AVANT résultats

Statut : **SPÉCIFICATION UNIQUEMENT — rien n'est exécuté dans la Mission 2.**
Signal concerné : `EMA_BASE_CORE_V1` (`ema_base_signal.py`), branche
`research/ema-base-core-v1`. Cette spécification est figée avant toute
observation de la performance du signal avec le moteur canonique.
Toute modification après la première exécution devra être documentée comme
déviation post-hoc et invaliderait la propreté statistique de l'étude.

---

## 1. QUESTION SCIENTIFIQUE

Le signal EMA Pullback (tendances H1 EMA50 + pullback EMA20 M15 + rejet +
RSI), débarrassé de tout money management, pyramid, reverse et de tous les
filtres post-hoc, contient-il une information prédictive statistiquement
mesurable sur les rendements futurs signés ?

## 2. DONNÉES

- Instrument : EURUSD, M15, OHLC Bid (CSV MT4).
- Fenêtre autorisée : historique **contaminé** uniquement, du début des
  données (2010-01-04) jusqu'au **2026-04-08 23:45 inclus**.
- **INTERDIT : la fenêtre 2026-04-09 → 2026-07-24 (OOS protégée).**
- Reconstruction via le moteur canonique `ResearchEngine` avec
  `entry_start_dt` fixé après le warm-up complet (§4) ; l'historique complet
  alimente les vues M15/H1 (aucun redémarrage artificiel des indicateurs).

## 3. DÉFINITION DES ÉVÉNEMENTS

- Événement = décision du composant `EMA_BASE_CORE_V1` retournant `LONG`
  ou `SHORT` à l'ouverture de la barre M15 i (timestamp `decision_ts`).
- `entry_price` = `open[i]` **Bid** (référence brute ; le signal ne connaît
  ni spread ni Ask — convention documentée).
- Aucun filtrage supplémentaire : pas de session, pas d'horaire, pas d'ATR,
  aucun filtre post-hoc (liste `EXCLUDED_POSTHOC_FILTERS`).
- Diagnostics du signal enregistrés pour audit, jamais pour filtrer.

## 4. WARM-UP

Premier événement admissible : première barre de décision i telle que
i ≥ 21 barres M15 clôturées ET ≥ 55 buckets H1 clôturés
(`h1_trend_ema_period 50 + h1_trend_bars 5`), conformément à
`EmaBaseCoreV1.warmup_requirements()`.

## 5. MESURES — rendements signés

Pour chaque événement et chaque horizon h ∈ {1, 2, 4, 8, 16} barres M15
(15 min, 30 min, 1 h, 2 h, 4 h) :

```
future_price(h) = open[i + h]        (Bid, convention open-to-open)
LONG :  future_return(h) = future_price(h) − entry_price
SHORT:  future_return(h) = entry_price − future_price(h)
```

- `RAW_SIGNED_RETURN_PIPS` = future_return × 10 000 (pip = 0.0001).
- `COST_ADJUSTED_SIGNED_RETURN_PIPS` = RAW − `TOTAL_SYNTHETIC_COST_PIPS`
  avec `TOTAL_SYNTHETIC_COST_PIPS = spread_pips + 2 × adverse_slippage_pips
  + commission_en_pips` — **SYNTHETIC** : aucune preuve broker n'étant
  disponible dans le dépôt, les valeurs seront pré-enregistrées et figées
  dans la mission d'expérience AVANT exécution (aucun choix dans Mission 2).
  Les événements dont l'horizon h déborde de la fenêtre sont exclu de
  l'horizon h (et uniquement de celui-ci).

## 6. STATISTIQUES PAR HORIZON (obligatoires)

Pour chaque horizon et chaque coût (raw / cost-adjusted) :

| Statistique | Définition |
|---|---|
| N_SIGNALS | nombre d'événements mesurés |
| MEAN_SIGNED_RETURN_PIPS | moyenne arithmétique |
| MEDIAN_SIGNED_RETURN_PIPS | médiane |
| WIN_RATE_DIRECTIONAL | part des rendements strictement > 0 |
| STD | écart-type échantillonnal (ddof=1) |
| STANDARD_ERROR | STD / sqrt(N) |
| CI 95 % | mean ± 1.96 × STANDARD_ERROR (approximation normale, pré-enregistrée) |
| SIGN | POSITIVE si mean > 0 et CI > 0 ; NEGATIVE si mean < 0 et CI < 0 ; sinon UNDETERMINED |

Seuil de conclusion pré-enregistré : un horizon est **INTERPRÉTABLE**
seulement si N_SIGNALS ≥ 100. En dessous : reporté, non interprété.

## 7. STABILITÉ PAR ANNÉE

Mêmes statistiques par année calendaire, **uniquement pour mesurer la
stabilité temporelle** du signe et de l'ampleur. Interdiction explicite
d'utiliser ces coupes pour sélectionner des années, filtrer, ou ajuster
quoi que ce soit.

## 8. SIGNAUX CHEVAUCHANTS

- **Étude primaire** : chaque événement est mesuré indépendamment même si
  les fenêtres [i, i+h] se chevauchent ; le rapport doit inclure
  `N_OVERLAPPING_EVENTS` (nombre d'événements dont la fenêtre maximale
  h=16 recouvre celle d'au moins un autre événement).
- **Robustesse secondaire (NON exécutée dans la mission primaire)** :
  `NON_OVERLAPPING_EVENTS` — parcours chronologique, on conserve un
  événement seulement si sa barre de décision est postérieure de
  **strictement plus de 16 barres M15** à celle du dernier événement
  conservé. Les mêmes statistiques sont recalculées sur ce sous-ensemble
  afin de vérifier que la significativité n'est pas gonflée par
  l'autocorrélation des fenêtres chevauchantes.

## 9. GARDE-FOUS DE L'EXPÉRIENCE

- Aucune modification du signal, des paramètres (gelés), ou du moteur après
  la première exécution.
- Aucune métrique de type PF/DD/profit de stratégie : l'event study mesure
  un pouvoir prédictif brut, pas une rentabilité.
- Aucun pyramid/reverse/BE/SL/TP dans la mesure.
- GBPUSD/USDJPY/XAUUSD : non testés (réservés à une éventuelle étude
  cross-pair ultérieure, pré-enregistrée séparément).
- Le résultat — positif, négatif ou indéterminé — sera rapporté tel quel.
