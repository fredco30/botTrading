# Recherche autonome H1/H4 multi-paires — septembre 2026

Mission : chercher méthodiquement un edge Forex exploitable sur H1/H4,
trois paires majeures, après coûts synthétiques, avec validation gelée en
deux étapes. Aucun accès à l'OOS 2026-04-09 → 2026-07-24.

## Verdict final

```
NO_ROBUST_H1_H4_MULTIPAIR_EDGE_FOUND
```

Deux candidats ont passé la sélection DISCOVERY et la gate VALIDATION_1,
mais **aucun** n'a survécu à VALIDATION_2 (testée une seule fois, sans
retouche). Détail dans les fichiers ci-dessous.

## Contenu

| Fichier | Rôle |
|---|---|
| `data_manifest.md` / `data_manifest.json` | Provenance et qualité des données |
| `family_screen.csv` / `.json` | Écran DISCOVERY complet (126 configs × 3 paires × 4 horizons = 484 lignes) |
| `discovery_report.md` | Lecture de l'écran DISCOVERY |
| `validation1_report.md` | Candidats gelés sur 2019-2022 |
| `validation2_report.md` | Candidats gelés sur 2023-01-01 → 2026-04-08 |
| `rejected_hypotheses.md` | Ce qui a été rejeté et pourquoi |
| `h1h4_lib.py` | Agrégation causale, indicateurs, familles F1-F8, event study |
| `run_screen.py`, `pipeline.py` | Reproduction complète des écrans et validations |
| `test_h1h4_research.py` | 7 tests synthétiques (agrégation, cutoff OOS, causalité, crossing unique, signes) |

## Points clés

1. **Bug de lookahead corrigé avant toute validation** : la première version
   du screen datait les événements à la barre dont la CLÔTURE génère le
   signal, et mesurait le rendement depuis l'open de cette même barre —
   capturant le corps de la bougie de signal (+50 pips / 87 % win
   fantômes sur les breakouts H4). Correction : exécution causale
   décalée d'une barre (`to_executable_side`), testée. Tous les chiffres
   du rapport sont post-correction.
2. 126 configurations screenées (F1-F8, H1+H4, 3 paires) sur DISCOVERY
   uniquement. Les critères §13 (≥2/3 paires positives après
   NORMAL_COST, robuste aux outliers, ≥4/9 années) laissent **2
   candidats** sur 484 lignes.
3. VALIDATION_1 (2019-2022), rerun corrigé : la mean-reversion H1 reste
   effondrée (−3.88 pips après NORMAL, 0/3 paires) ; la vol-compression
   breakout reste positive en agrégat (+1.01) mais portée par USDJPY seul
   (1/3 paires) → gate FAIL.
4. VALIDATION_2 (2023 → 2026-04-08) : **non exécutée** — aucun candidat
   n'a passé la gate V1 corrigée. (Le run initial, invalidé par un bug de
   double décalage d'exécution, avait fait entrer C2 en V2 avec −0.41.)
   Décompte corrigé : 42 configurations de stratégie uniques,
   126 évaluations config×paire.
5. Pyramide : **non testée** — la condition `BASE_EDGE_POSITIVE` (candidat
   survivant aux trois phases) n'a jamais été remplie.
6. Un bug de double décalage d'exécution (V1/V2) a été détecté en revue,
   corrigé et verrouillé par des tests de parité
   (`TestExecutionShiftParity`) : RAW signal à l'index k → exécution à
   k+1, jamais k+2 ; les chemins DISCOVERY et VALIDATION produisent des
   événements et des rendements identiques sur le même signal.

## Reproduction

```
python data_prep.py       # nécessite le snapshot EURUSD hors repo (voir manifest)
python run_screen.py      # écran DISCOVERY -> family_screen.csv/json
python pipeline.py        # sélection + VALIDATION_1 + VALIDATION_2
```

Les datasets agrégés sont mis en cache hors Git
(`C:\Users\Fred\.zcode\tmp\autonomous\h1h4\*.parquet`).
