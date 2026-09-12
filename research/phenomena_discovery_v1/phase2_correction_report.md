# PHASE 2 FINAL CORRECTION REPORT (audit v3)

Corrections appliquées uniquement aux familles affectées ; les écrans propres
n'ont pas été relancés. Aucun accès V1/V2 dans cette mission (gate.py
verrouillé, gate_audit.log sans autorisation réelle ; les tests unitaires
redirigent vers un log temporaire).

## 1. P034 — forward range (BUG CONFIRMÉ, corrigé)

- BUG : `high.shift(-144) - low.shift(-144)` mesurait le range d'UNE seule
  bougie située 12 h plus tard.
- FIX : `future_rolling_range()` = max(high[i+1:i+145]) − min(low[i+1:i+145]) ;
  la fenêtre future entière doit rester dans Discovery (événements de queue
  exclus) ; seuils gelés 0.60/0.70 inchangés ; test synthétique (expansion
  connue retrouvée sur les 144 barres, NaN sur la queue).
- ANCIEN RÉSULTAT : INVALIDATED_BY_FORWARD_RANGE_IMPLEMENTATION_BUG
  (l'ancien « ratio 1.24-1.29 » mesurait une seule bougie : baseline 4.2 pips
  au lieu de 62.5).
- NOUVEAU (Discovery) : EURUSD baseline 62.5 pips → après compression 70.5/70.0
  (ratio 1.13/1.12, N=1799/2166) ; USDJPY 50.5 → 47.6/48.1 (ratio 0.94/0.95).
- **P034_SECOND_ORDER_CANDIDATE=NO** (expansion non robuste : positive faible
  EURUSD, négative USDJPY).

## 2. P032 — DST + prix d'entrée (BUGS CONFIRMÉS, corrigés)

- DST : le champ tz parsé (EST/EDT) est maintenant honoré via offsets fixes
  (pytz rejette les noms EDT). Tests : 2016-01-27 14:00 EST → 19:00 UTC ;
  2016-03-16 14:00 EDT → 18:00 UTC.
- Entrée : premier OPEN de barre dont le timestamp >= release_ts (l'ancien
  code partait du CLOSE de la barre de réaction ≈ 14:05 et mangeait le move).
- Période réelle : heures exactes uniquement à partir de 2016 → **N=24,
  période 2016-2018** (jamais « 2015-2018 »).
- NOUVEAU (Discovery) : |réaction initiale| = 29-33 pips/30 min (EURUSD/USDJPY/
  GBPUSD) ; continuation 30m→2h signée : +8.6 / +3.4 / +11.1 pips ; N=24 →
  INCONCLUSIVE (sous-puissant), étude event-time uniquement.

## 3. P004 — machine d'états reclaim (BUG CONFIRMÉ, corrigé)

- FIX : états explicites NONE → BROKEN → FAILED → RECLAIMED par côté ;
  reclaim = APRES un failed, close repasse le niveau (PDH reclaim = LONG,
  PDL reclaim = SHORT) ; tests synthétiques BREAK→FAILED→RECLAIM (timestamps
  + sides) pour PDH et PDL.
- ANCIENNES stats reclaim : INVALIDATED_BY_STATE_MACHINE_BUG.
- NOUVEAU (Discovery) : toujours miroir-incohérent entre paires → REJECT.

## 4. P025 — définitions de signaux (BUGS CONFIRMÉS, corrigés)

- Δdifferential : événement UNIQUEMENT si le différentiel change réellement
  après le lag causal (delta ≠ 0) ; plus de jours-signal à 0.
- carry+momentum : événement UNIQUEMENT si sign(carry) == sign(momentum),
  direction = côté carry ; sinon PAS d'événement.
- ANCIEN VERDICT : INVALIDATED_BY_SIGNAL_DEFINITION_BUG jusqu'au rerun.
- NOUVEAU (Discovery) : toujours ≈ 0 sur 3 paires (meilleur : USDJPY level
  +19 pips/20d, P=.29) → REJECT confirmé.

## 5. P026 — alignement DGS2 (BUG CONFIRMÉ, corrigé)

- FIX : premier jour de marché >= t+1 jour calendaire (l'ancien `> t+1`
  sautait le jour éligible, lundi → mercredi) ; `d2_change` stocké dans
  l'événement à la construction (plus de re-lookup −1/−2 jours) ; tests
  lundi → mardi et vendredi → lundi.
- NOUVEAU (Discovery) : choc ≥3bp h5d +8.9 pips (N=586, P=.051 — limite) ;
  h1d ≈ 0 → INCONCLUSIVE.

## 6. P020 — convention (documentée, corrigée sans retuning)

Une barre « 16:00 » couvre [16:00, 16:05) : sa CLOSE est le prix de 16:05.
Les bornes 13:00/16:00/18:00 utilisent désormais l'OPEN de la barre au label
exact (= dernier prix exécutable à/avant la borne). Recalculé : conclusions
inchangées (fade post-fix sous les coûts : EURUSD +0.79, GBPUSD +1.21 pips).

## 7. P013 — gate checks reproductibles

`run_phase2_gate_checks.py` (versionné) reproduit exactement les valeurs
publiées (DIFF −2.16/2.47/8.79/6.77 ; p 0.654/0.615/0.066/0.138) :
ME, NORMAL, DIFF, CI bootstrap (2000, seed 42), BOOT_P, BY_YEAR_DIFF.

## 8. P013R — réplication JPY cross PRÉ-ENREGISTRÉE

Enregistrée au ledger (DERIVED_PREREGISTERED, parent P013) AVANT tout calcul.
Règle figée : dernier jour FX ouvré du mois, LONG XJPY, close → close du jour
de marché suivant, coût NORMAL 2 pips, Discovery 2010-2018, bootstrap 2000
seed 42. Testée exactement sur USDJPY / EURJPY / GBPJPY (p013r_replication.json) :

| Paire | N | GROSS (pips) | NET NORMAL | IC95 (gross) | BOOT_P | Années + |
|---|---|---|---|---|---|---|
| USDJPY | 107 | +9.78 | +7.78 | [−0.68, +20.62] | 0.066 | 7/9 |
| EURJPY | 107 | **+15.06** | **+13.06** | **[+0.86, +28.93]** | **0.041** | 7/9 |
| GBPJPY | 107 | +2.06 | +0.06 | [−18.74, +23.34] | 0.851 | 3/9 |
| **POOLED équi-pondéré** | — | **+8.97** | **+6.97** | [−0.19, +18.28] | **0.053** | 3/3 paires + |

Lecture : réplication PARTIELLE — la jambe EURJPY franchit le seuil de 5 %
avec un IC excluant zéro et une amplitude nette > coûts ; la pooled est à
0.053 ; GBPJPY est plat. Statut : **DISCOVERY_CANDIDATE=YES (limite)** —
et conformément à la consigne, **V1 n'est PAS ouverte** : elle est préservée
pour la revue humaine.

## 9. Verdict

FINAL_VERDICT=NO_VALIDATED_PHENOMENON_AFTER_PHASE2
(un candidat Discovery limite existe — P013R — mais aucune validation V1/V2
n'a été lancée : phénomène non validé, décision réservée à la revue humaine.)

OOS_ACCESSED=NO ; TESTS=96 verts ; CI=PASS ; PR #19 mise à jour, non mergée.


## 10. P013R — AUDIT DE DÉPENDANCE (avant toute décision V1)

Faiblesse corrigée : l'ancien bootstrap pooled resamplait les 3 paires
INDÉPENDAMMENT alors que les événements partagent les mêmes month-ends, la
devise JPY et des rendements corrélés (ρ = 0.60 USDJPY/EURJPY, 0.62
USDJPY/GBPJPY, 0.72 EURJPY/GBPJPY) → incertitude artificiellement réduite.
ANCIEN POOLED BOOTSTRAP : SUPERSEDED_BY_PAIRED_BOOTSTRAP (valeurs historiques
conservées dans p013r_replication.json, plus aucune valeur de preuve).

Table événementielle commune (p013r_dependence_audit.json) : N=107 month-ends
où les 3 paires ont une observation causalement valide (calendrier de chaque
paire respecté — un bug d'alignement inter-calendriers a été détecté et
corrigé lors de la construction).

Résultats (règle INCHANGÉE, Discovery 2010-2018) :

| Métrique | Valeur |
|---|---|
| PAIRED_POOLED_GROSS | +8.97 pips |
| PAIRED_POOLED_NET_NORMAL | +6.97 pips |
| PAIRED_POOLED_NET_STRESS (4 pips) | +4.97 pips |
| PAIRED_CI95_GROSS / NET | [−4.64, +22.13] / [−6.64, +20.13] |
| PAIRED_P_GROSS / P_NET | 0.169 / 0.307 |
| YEAR_BLOCK_CI95_GROSS / NET | [−5.26, +24.29] / [−7.26, +22.29] (audit v5 : bug de déduplication des années tirées corrigé — la multiplicité des blocs compte désormais ; ancien CI [−4.23, +20.61] / [−6.23, +18.61] invalidé) |
| MEDIAN_GROSS / NET | +12.43 / +10.43 |
| WIN_RATE_GROSS / NET | 0.598 / 0.570 |
| REMOVE_BEST_EVENT_NET | +5.22 |
| REMOVE_BEST_3_EVENTS_NET | +2.04 |
| POSITIVE_YEARS_GROSS / NET | 7/9 / 5/9 |

La correction de dépendance fait exactement ce qui était suspecté : elle
élargit l'incertitude (p gross 0.053 → 0.169 ; l'IC95 net croise zéro).
Critères de classement : 5/6 remplis (seul le CI apparié excluant zéro
échoue) → **P013R_DISCOVERY_CLASSIFICATION = P013R_DISCOVERY_WEAK**
(effet positif, net de coûts NORMAL et STRESS, robuste au retrait des 3
meilleurs événements, mais fragile statistiquement : IC croisant zéro,
5/9 années nettes positives).

V1_ACCESSED=NO ; V2_ACCESSED=NO ; OOS_ACCESSED=NO. Décision d'ouverture V1
réservée à la revue humaine sur la base de cette classification WEAK.


## 11. P013R — YEAR-BLOCK BOOTSTRAP FINAL FIX (audit v5)

BUG CONFIRMÉ : `year_block_bootstrap_means` construisait un masque booléen
(`mask |= years == y`) qui DÉDUPLIQUAIT les années tirées en double — la
multiplicité des blocs était perdue. CORRECTION : les blocs tirés sont
CONCATÉNÉS dans l'ordre du tirage (une année tirée k fois contribue k fois)
; n_boot=2000, seed=42 inchangés ; test synthétique obligatoire ajouté
(tirage YEAR_C, YEAR_C, YEAR_A → (100+100−100)/3 = +33.3, et l'ancienne
logique booléenne donnait bien 0 — le test échoue avec l'ancien code).

RECALCUL (uniquement les stats year-block) :
YEAR_BLOCK_GROSS_MEAN +8.85 / NET_MEAN +6.85 ;
CI95_GROSS [−5.26, +24.29] ; CI95_NET [−7.26, +22.29] (CI légèrement plus
large, cohérent avec la multiplicité restaurée).
TOUTES les métriques appariées et de robustesse : bit-identiques (aucun
nouveau bug révélé). CLASSIFICATION : P013R_DISCOVERY_WEAK inchangée
(fondée sur les critères figés, le CI apparié restant le critère limitant).
