# EMA_BASE_CORE_V1 — Event Study (Phase 1, mission autonome)

Exécuté conformément à `EMA_BASE_EVENT_STUDY_SPEC.md` (Mission 2), sans
aucune modification du signal figé.

- Données : EURUSD M15, fenêtre stricte **[2010-01-04 00:00, 2026-04-09 00:00)** — 402 911 barres.
  La fenêtre OOS 2026-04-09→2026-07-24 n'a pas été lue (le snapshot utilisé
  s'arrête au 2026-04-08 et un filtre de défense est appliqué au chargement).
- Signal : `EMA_BASE_CORE_V1` exactement tel que mergé (paramètres gelés).
- Événements : 19 106 (9 390 LONG / 9 716 SHORT), premier signal 2010-01-06.
  Chevauchement : 10 319 événements à moins de 16 barres du précédent.
- Mesure : rendement directionnel open-to-open en pips (Bid), LONG comme SHORT.

## Résultats par horizon

| Horizon | Side | N | MEAN pips | MEDIAN pips | WIN % | STD |
|---|---|---:|---:|---:|---:|---:|
| 15m | ALL | 19106 | **−0.095** | −0.30 | 46.00 | 6.93 |
| 15m | LONG | 9390 | −0.095 | −0.30 | 46.01 | 7.08 |
| 15m | SHORT | 9716 | −0.095 | −0.30 | 45.99 | 6.78 |
| 30m | ALL | 19106 | **−0.134** | −0.40 | 46.32 | 9.76 |
| 30m | LONG | 9390 | −0.116 | −0.40 | 46.43 | 9.95 |
| 30m | SHORT | 9716 | −0.151 | −0.40 | 46.21 | 9.57 |
| 1h | ALL | 19106 | **−0.264** | −0.60 | 46.27 | 13.81 |
| 1h | LONG | 9390 | −0.430 | −0.60 | 45.81 | 14.22 |
| 1h | SHORT | 9716 | −0.104 | −0.50 | 46.71 | 13.40 |
| 2h | ALL | 19106 | **−0.267** | −0.70 | 47.04 | 19.19 |
| 2h | LONG | 9390 | −0.380 | −0.70 | 46.96 | 19.76 |
| 2h | SHORT | 9716 | −0.157 | −0.80 | 47.11 | 18.62 |
| 4h | ALL | 19106 | **−0.474** | −0.90 | 47.24 | 26.69 |
| 4h | LONG | 9390 | −0.917 | −1.00 | 47.12 | 27.11 |
| 4h | SHORT | 9716 | −0.046 | −0.90 | 47.35 | 26.26 |

Moyennes par année (pips, tous horizons confondus dans le JSON) : aucune
année ne montre un effet stable et marqué ; le signe oscille selon les
années et les horizons sans structure (ex. 4h : +1.57 en 2015, −3.30 en
2011, +1.49 en 2020, −1.02 en 2024).

## Interprétation (screen, pas un test définitif)

- Avec N = 19 106, l'erreur standard de la moyenne à 4h est ≈ 0.19 pip :
  la moyenne −0.47 pip est à ~2.5 SE **sous zéro** — le signal ne montre
  aucune dérive positive, plutôt une légère dérive défavorable typique du
  bruit + microstructure.
- Aucune histoire cohérente entre horizons (15m ≈ 0, puis dégradation).
- LONG et SHORT sont tous deux négatifs ou nuls ; pas de compensation
  exploitable.
- Tout coût de transaction (≥ ~0.7 pip aller-retour même en LOW_COST)
  rendrait l'espérance nette clairement négative.

## Verdict Phase 1

```
EMA_BASE_CLASSIFICATION = NO_EDGE
EMA_BASE_REJECTED       = YES
```

Le noyau de signal historique, isolé de tout money management et de tous
ses filtres post-hoc, ne contient **pas** d'information prédictive
exploitable sur EURUSD 2010→2026. Ce résultat est **compatible avec
l'hypothèse** que les résultats historiques « champions » du dépôt
s'expliquaient largement par le money management (pyramid sur grappes de
wins) et la sélection post-hoc de filtres — mais cette causalité exacte
n'est pas démontrée par la présente étude.

Conformément à la mission : passage en Phase 2B (ablations + familles
exploratoires), sans tentative de sauvetage d'EMA_BASE.
