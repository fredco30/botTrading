# RESEARCH_ENGINE_SPEC — CANONICAL_RESEARCH_ENGINE V1

Branche : `research/causal-engine-v1` (base `main` @ `59befeb1949736c7067fc99a0ad53609cc169796`)
Code : `research_engine.py` — Tests : `test_research_engine.py`
Moteurs legacy `bt_engine.py` / `bt_fast.py` : **PRESERVÉS, non modifiés** (traçabilité).
Ce moteur n'est PAS une réplique de l'EA MT4 historique (voir §7).

Statuts des hypothèses : **ASSUMPTION** = approximation assumée et localisée.
**SYNTHETIC** = donnée non historique, construite par convention.

---

## 1. TIMELINE DE DÉCISION (preuve d'indexation)

Convention : chaque barre M15 est identifiée par son **heure d'ouverture** `dt`.
Une barre de `dt = 09:15` couvre `[09:15:00, 09:30:00)` et devient **entièrement
connue à 09:30:00** (sa clôture est le dernier tick avant 09:30:00).

Exemple traçé (M15) :

```
bar 09:00  | connu entièrement à 09:15:00
bar 09:15  | connu entièrement à 09:30:00
bar 09:30  | S'OUVRE à 09:30:00  (sa close n'est connue qu'à 09:45:00)
bar 09:45  | s'ouvre à 09:45:00
```

Un signal n'utilisant que les barres clôturées `i-2` (09:00) et `i-1` (09:15) :

```
SIGNAL_AVAILABLE_AT = 09:30:00 = open time de la barre i
```

Détermination explicite du prix d'entrée causal :

| Candidat | Statut | Raison |
|---|---|---|
| **`open[i]`** | **RETENU** | premier prix observable à/après `SIGNAL_AVAILABLE_AT` (09:30:00) |
| `close[i]` | REJETÉ | connu seulement à 09:45:00 — remplir à `close[i]` simule une exécution 15 min après la décision à un prix non observable au moment de la décision (biais de l'ancien moteur `bt_engine.py`) |
| `open[i+1]` | REJETÉ | légal mais retardé d'une barre M15 complète sans justification |

```
DECISION_TS   = open time de la barre i
ENTRY_TS      = DECISION_TS (même instant)
ENTRY_PRICE   = open[i], côté exécution (Ask pour un long, Bid pour un short)
ENTRY_USES_FUTURE_DATA = NO (garanti par construction, cf. §8 et tests A/B)
```

## 2. DONNÉES AUTORISÉES POUR LE SIGNAL

- **M15** : uniquement les barres `[0 .. i-1]`, entièrement clôturées. La vue
  stratégique (`CausalContext.m15`) est **bornée causalement** : tout accès
  `t >= i` lève `CausalityError`. `close[i]`, `high[i]`, `low[i]` sont inaccessibles.
- **H1** : uniquement des buckets **clôturés**. Un bucket H1 d'heure `[h, h+1)`
  est publié avec `close_dt = h+1:00` et n'est visible qu'à partir de cet instant
  (`close_dt <= open_time(barre i)`). Aucune H1 en formation n'est jamais exposée.

```
LEGACY_MT4_USED_FORMING_H1    = YES   (iMA/iATR/iClose H1 shift 0 dans les EAs historiques)
RESEARCH_ENGINE_USES_CLOSED_H1 = YES  (par construction, testée)
```

## 3. CONVENTION BID / ASK

- Les CSV du dépôt sont des OHLC **Bid** (export MT4). Le moteur les traite comme tels.
- `Ask = Bid + spread`, spread supposé constant intra-barre.
- LONG : entrée sur **Ask** ; SL/TP évalués sur **Bid** ; sortie au Bid.
- SHORT : entrée sur **Bid** ; SL/TP évalués sur **Ask** ; sortie au Ask.
- Les niveaux `sl_price` / `tp_price` d'un ordre sont exprimés **côté sortie**
  (niveaux Bid pour un long, niveaux Ask pour un short) — convention documentée.

## 4. SPREAD — SYNTHETIC

- `CostModel.spread_mode = "fixed"` (seul mode V1), `spread_pips` paramétrique.
- **Aucune série de spread historique n'existe dans le dépôt** : le spread est
  **SYNTHETIC**. Le moteur n'affirme JAMAIS qu'un spread fixe est « réaliste ».
- `SPREAD_HISTORICAL_AVAILABLE = NO`. Une future série réelle pourra remplacer
  le mode fixe sans changer l'API.

## 5. COMMISSION — paramétrique

- `CostModel.commission_per_lot_per_side` (devise du compte), facturée **par
  fill** (entrée + sortie). Aucun tarif broker codé en dur ($7 etc. interdits).

## 6. SLIPPAGE — paramétrique, déterministe

- `CostModel.adverse_slippage_pips` : glissement **toujours défavorable**,
  déterministe (aucun aléa en V1), appliqué :
  - à l'entrée au market (les deux sens) ;
  - aux sorties stop (SL/BE) y compris sur gap ;
  - à la clôture forcée fin de dataset ;
  - **pas** aux sorties TP (ordre limite : rempli au niveau ou mieux, jamais pire).

## 7. GAPS

Règle causale documentée — un stop traversé par un gap **n'est pas** rempli au
prix du stop :

- LONG, stop sur Bid : si `open_bid < SL`, rempli au **premier prix exécutable**
  `open_bid`, moins le slippage (`exec = open_bid - slippage`) → pire que le stop.
- SHORT, stop sur Ask : si `open_ask > SL`, rempli à `open_ask`, plus le
  slippage (`exec = open_ask + slippage`) → pire que le stop.
- TP traversé par un gap : sémantique limite standard, rempli à l'open
  (**meilleur** que le TP). Convention documentée, favorable au trader, sans
  slippage.

Tests dédiés LONG et SHORT (tests H, I).

## 8. ORDRE INTRA-BAR — `INTRABAR_POLICY=CONSERVATIVE` (défaut V1)

Avec OHLC seul, le chemin `OPEN→HIGH→LOW→CLOSE` vs `OPEN→LOW→HIGH→CLOSE` est
inconnu. Le moteur n'invente **jamais** silencieusement un chemin favorable.

Cas ambigus identifiés et résolus :

| Cas | Résolution CONSERVATIVE |
|---|---|
| SL **et** TP touchés dans la même barre | sortie au **SL** (pire issue compatible) |
| Trigger BE **et** ancien SL touchés dans la même barre | sortie à l'**ancien SL** (perte pleine) ; le BE ne sauve pas dans sa barre d'armement |
| Trigger BE **et** nouveau stop BE touchés dans la même barre (ancien SL intact) | **aucune sortie inventée** : la position survit, le BE est armé pour la barre suivante |
| Armement BE quelconque | effectif **à partir de la barre suivante** |

`AMBIGUOUS_BARS` compte le nombre de **BARRES DISTINCTES** ayant produit au
moins une ambiguïté (une même barre peut générer plusieurs événements de
types différents : elle compte pour une seule barre). La liste déterministe
des timestamps de ces barres est exposée dans `ambiguous_bar_ts` (ordre
chronologique). `ambiguity_event_counts` compte, lui, les **ÉVÉNEMENTS**
par type. `AMBIGUOUS_TRADES` compte les **TRADES DISTINCTS** ayant subi au
moins une ambiguïté. **LIMITATION assumée** : bar-level ≠ tick-level.
La validation LTF/tick est une extension prévue (le champ `intrabar_policy`
est réservé pour `LTF_VALIDATION`), pas une équivalence acquise.

## 9. BREAKEVEN

- Optionnel (`BreakevenConfig` : `trigger_r`, `offset_pips`).
- Déclencheur mesuré **côté sortie** (Bid haut pour un long atteignant
  `entry_exec + trigger_r × risk_dist`) ; nouveau stop = `entry_exec ± offset`.
- Soumis à la politique intra-bar du §8 (jamais armé-et-touché dans la même barre).

## 10. CLÔTURE FIN DE DATASET

Une position encore ouverte à la dernière barre est **fermée de force** au
prix de clôture de la dernière barre, côté sortie (Bid long / Ask short),
avec slippage défavorable, `exit_reason = END_OF_DATA`, comptée dans
`forced_closes` et dans la décomposition PnL.

## 11. PIPS / TICKS / PnL

- Aucun `PIP=0.0001` ni `PIP_VALUE_PER_LOT=$10` codé en dur : tout passe par
  `InstrumentSpec` (§12).
- `pip_value_per_lot = (pip_size / tick_size) × tick_value`.
- **ASSUMPTION** : `quote_currency == account_currency` (pas de conversion de
  change modélisée en V1 ; champ présent pour brancher une conversion plus tard).
- Décomposition exacte, par trade et en cumul :

```
NET_PNL = GROSS_PNL - SPREAD_COST - SLIPPAGE_COST - COMMISSION_COST
```

avec, par fill : `ref = prix côté (mid)` ; `GROSS` = PnL mid-à-mid ;
`SPREAD_COST = spread_pips × pip_value × lots` (aller-retour complet) ;
`SLIPPAGE_COST = slippage réellement appliqué` ; `COMMISSION = 2 × par-side`.
`NET` est calculé par cette identité et **vérifié** contre le PnL brut
d'exécution (`dir × (exit_exec − entry_exec)`, tolérance 1e-6, test O).
Rounding : les PnL ne sont pas arrondis ; les lots sont arrondis **au floor**
au `lot_step` (floor ne peut que réduire ou maintenir le risque) puis, selon
le mode (cf. §13) : `fixed_lot` → clamp aux contraintes broker
(ASSUMPTION, choix explicite de l'utilisateur) ; `fixed_risk_percent` →
**rejet** si le lot minimal broker dépasse le risque planifié (aucun clamp
vers `min_lot`).

## 12. INSTRUMENT SPEC

`InstrumentSpec` : `symbol, pip_size, tick_size, tick_value, lot_size,
min_lot, lot_step, max_lot, quote_currency, account_currency`.
V1 active : **EURUSD uniquement** (`get_instrument("EURUSD")`). GBPUSD,
USDJPY, XAUUSD sont représentables (champs génériques) mais **non
fournis et non backtestés** dans cette mission.

## 13. MONEY MANAGEMENT

- `SizingConfig.mode = "fixed_lot"` ou `"fixed_risk_percent"`.
- **Risque planifié all-in (V1C)** : en `fixed_risk_percent`, la taille est
  calculée sur la **PERTE NETTE PLANIFIÉE SUR STOP NON GAPÉ**
  (`PLANNED_NON_GAP_STOP_LOSS_NET`), qui inclut TOUS les coûts
  déterministes connus du moteur :
  - distance de prix entre `entry_exec` et le stop **ajusté du slippage de
    sortie** (LONG : `sl − slippage` ; SHORT : `sl + slippage`) — le spread
    et le slippage d'entrée sont déjà dans `entry_exec`, **sans double
    comptage** ;
  - **plus** `2 × commission_per_lot_per_side` (entrée + sortie).

  ```
  RISK_TARGET_MONEY = balance × risk_percent / 100
  lots = floor(RISK_TARGET_MONEY / PLANNED_LOSS_PER_LOT, au lot_step)
  Garantie : PLANNED_NON_GAP_STOP_LOSS_NET <= RISK_TARGET_MONEY
             (tolérance flottante 1e-9 relative, testée)
  ```
- **Règle min-lot (V1B/V1C)** : si le lot minimal du broker ferait dépasser
  `RISK_TARGET_MONEY`, le trade est **REJETÉ proprement** et compté dans
  `orders_rejected_min_lot_risk`. Le moteur ne transforme jamais
  silencieusement un risque de 1 % en 2 % ou 5 %. Un clamp à `max_lot` est
  autorisé (il réduit le risque par rapport à la cible).
- **Les gaps restent NON BORNÉS** : le sizing garantit le risque planifié
  hors gap uniquement.
  ```
  FIXED_RISK_PLANNED_NON_GAP_CAN_EXCEED_TARGET = NO
  GAP_LOSS_CAN_EXCEED_TARGET = YES
  ```
  Un gap à travers le stop peut produire `REALIZED_LOSS >
  RISK_TARGET_MONEY` : c'est un comportement réaliste, pas un bug. Aucun
  re-dimensionnement rétrospectif n'a lieu ; `gap_exit` identifie ces trades.
  Auditabilité : chaque trade expose `risk_target_money` (None en
  `fixed_lot`, renseigné en `fixed_risk_percent`) et
  `planned_stop_loss_net` (calculé dans LES DEUX modes) pour contrôle
  a posteriori de `planned_stop_loss_net <= risk_target_money`.
- En `fixed_lot`, la taille est un choix explicite de l'utilisateur : elle
  reste clampée aux contraintes broker (comportement legacy documenté).
- **Aucune martingale / pyramid / reverse** dans le moteur V1.
- Une seule position à la fois ; les ordres émis pendant une position ouverte
  sont ignorés et comptés (`orders_ignored`).
- Compounding : le solde est mis à jour à chaque clôture (`balance += net`).

## 14. DÉTERMINISME

Aucun aléa, aucun dictionnaire ordonné par insertion exploité, aucun temps
système, aucune parallélisation : même input + même config ⇒ sortie
**bit-for-bit identique** (test N, égalité structurelle exacte).

## 15. PARITÉ MT4 — HORS PÉRIMÈTRE

Pas d'objectif de parité avec l'EA MT4 historique dans cette mission :
l'EA utilisait des H1 en formation, le moteur scientifique n'utilise que du
clôturé. Une mission future créera un EA MQL4 de référence conforme à CETTE
spécification (CANONICAL_RESEARCH_ENGINE), pas l'inverse.

## 16. PROTECTION OOS

La fenêtre `2026-04-09 → 2026-07-24` est **protégée par procédure** (aucun run
stratégique autorisé dessus, aucun calcul de PF/expectancy/DD/profit, aucun
regard sur les trades qu'y produirait une stratégie). La protection est
disciplinaire, pas embarquée dans la librairie : les missions futures
autoriseront explicitement son usage. Cette mission n'y a pas accédé.
Smoke test technique autorisé : tranche contaminée 2023 uniquement
(`ENGINE_RUNS=YES/NO`, aucune conclusion de rentabilité).

## 17. DATA_HISTORY_START / ENTRY_START (API `run`)

```
run(bars, strategy, entry_start_dt=None, end_dt=None)
```

- **DATA_HISTORY_START** = `dt de bars[0]` (implicite : l'historique de
  données est exactement la liste `bars` fournie). Le moteur parcourt
  **toutes** les barres depuis le début : les vues M15/H1 et les indicateurs
  côté stratégie se warm-up sur l'historique antérieur complet. Une EMA50 H1
  évaluée en 2023 utilise l'historique H1 antérieur — elle ne redémarre pas
  artificiellement à `entry_start_dt`.
- **ENTRY_START** = `entry_start_dt` : **aucun nouvel ordre** n'est accepté
  avant cet instant ; les ordres retournés par la stratégie avant
  `ENTRY_START` sont écartés et comptés dans `orders_ignored_warmup`.
- **Garantie d'identité causale** : à tout timestamp T, les features obtenues
  avec `entry_start_dt = T` sont **identiques** à celles du run complet sur
  le même historique (test de régression dédié). `entry_start_dt` ne filtre
  que l'ACCEPTATION des ordres, jamais la construction des vues.
- `end_dt` : fin d'évaluation ; position ouverte forcée à la clôture de la
  dernière barre traitée.
- Note V1B : le paramètre `start_dt` de la V1 (qui découpait la fenêtre et
  détruisait l'historique de warm-up) est **supprimé** — c'était un défaut,
  pas une sémantique à conserver.

## 18. HYPOTHÈSES MARQUÉES (résumé)

| Marqueur | Objet |
|---|---|
| ASSUMPTION | `quote_currency == account_currency` (pas de conversion FX) |
| ASSUMPTION | `fixed_lot` : taille clampée aux contraintes broker (choix explicite utilisateur) ; `fixed_risk_percent` : trade REJETÉ si lot < min_lot (jamais au-dessus du risque PLANIFIÉ HORS GAP, cf. §13 ; `GAP_LOSS_CAN_EXCEED_TARGET=YES`) |
| ASSUMPTION | spread constant intra-barre |
| ASSUMPTION | niveaux d'ordre comparés à OHLC Bid/Ask dérivé, sans microstructure |
| SYNTHETIC | spread (aucun historique de spread dans le dépôt) |
| SYNTHETIC | tous les datasets des tests unitaires (en mémoire) |
