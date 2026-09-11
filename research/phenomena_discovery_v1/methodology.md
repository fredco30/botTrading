# METHODOLOGY — phenomena-discovery-v1

Pipeline scientifique : PHENOMENON → SIGNAL → VALIDATION → STRATEGY
( jamais INDICATORS → OPTIMIZATION → backtest joli ).

## 1. Priorité P000

P000 = hypothèse EXTERNE (vidéo PBInvesting) reconstruite à partir du
transcript officiel (video_source/) — EXTERNALLY_PREREGISTERED : toutes les
règles sont fixées AVANT tout contact avec les données (video_strategy_spec.md).
Aucune optimisation : 0 paramètre ajusté sur les données. Les ambiguïtés sont
documentées (AMBIGUOUS_RULE=…) avec l'interprétation la plus littérale.

## 2. Causalité (héritée du CANONICAL_RESEARCH_ENGINE, adaptée 5 min)

- Chaque barre 5 m est identifiée par son instants d'OUVERTURE `ts` ; elle
  n'est entièrement connue qu'à `ts+5min`. Toute décision (confirmation,
  tap, stop sur clôture, EMA8, VWAP) n'utilise que de l'information disponible
  à l'instant de décision.
- Niveaux pre-market/Asie : calculés sur la fenêtre fermée ; utilisables
  uniquement à partir de la première barre de session.
- Trim « new extreme of day » : extrême COURANT du jour AVANT la barre
  (cummax/cummin décalés) ; rempli en limite au niveau (jamais mieux).
- Entrée = ordre stop au bout extrême de la bougie de tap ; si gap, rempli à
  l'open (pire). Sorties sur clôture = exécutées à cette clôture (observée).
- BE gap-aware : rempli au pire de (open, plancher).
- Cas ambigus même barre : issue la pire compatible (stop de niveau avant
  trim ; BE avant EMA8 — ordre séquentiel des prix).
- Forward returns : base = prix d'exécution réel (fill) ; jamais de
  traversée de frontière de fenêtre (filtrés par construction).
- Screens (P001+) : événement marqué à la bougie dont la CLOSE déclenche ;
  exécution à l'OPEN de la bougie SUIVANTE (convention identique au moteur).

## 3. Fenêtres et protection OOS

- INTERDICTION ABSOLUE [2026-04-09, 2026-07-24] : filtrage défensif dans le
  code (load_5m / filter_window). OOS_ACCESSED=NO.
- DISCOVERY 2010-01-01 → 2018-12-31 ; V1 2019-01-01 → 2022-12-31 ;
  V2 2023-01-01 → 2026-04-08.
- WHY_SPLIT_CHANGED (P000 original) : USA500/USATECH Dukascopy démarrent
  2011-09-19 → Discovery = 2012-01-01 → 2018-12-31 (7 ans, 337 événements
  P000A). FX inchangé (2010+).

## 4. Mesures

N, MEAN, MEDIAN, WIN_RATE, STD, LONG/SHORT, BY_YEAR, BY_HOUR_ET,
MEAN_BEST1_REMOVED, MEAN_BEST5_REMOVED, MEAN_TOP1PCT_REMOVED, intervalle
bootstrap moving-block (20 événements, 2000 rééchantillonnages, seed 42) et
p-value bilatérale. Pas de t-test IID (événements potentiellement
autocorrélés) — bootstrap par blocs.

## 5. Coûts (SYNTHETIC, paramétriques)

FX : LOW 1.0 / NORMAL 2.0 / STRESS 3.5 pips aller-retour (conventions dépôt).
US : LOW 0.5 / NORMAL 1.0 / STRESS 2.5 points d'indice A-R (≈ ETF classe SPY :
spread+commission+slippage). Slippage/execution degradés = scénario STRESS.
Aucun coût n'est déclaré réaliste.

## 6. Gate Discovery → V1 → V2

Un phénomène mérite V1 si (conjonction) : effet brut clair, amplitude >
coûts NORMAL, médiane cohérente, robustesse best-1/best-5, stabilité
temporelle intra-Discovery (BY_YEAR), mécanisme plausible, N acceptable.
Décision de freeze AVANT ouverture de V1 ; AUCUN retuning après ; V2 ouvert
seulement si V1 solide ; aucune modification après V2.

## 7. Anti-edge (famille A)

Pour chaque signal : GROSS_DIRECTIONAL_EXPECTANCY. Si < 0 stable sur
Discovery (3/3 marchés idéalement) → ANTI_EDGE_CANDIDATE=YES ; création de
INVERTED_SIGNAL = −ORIGINAL sans rien changer d'autre ; décision d'inversion
UNIQUEMENT sur Discovery ; puis freeze → V1 → V2. Ne jamais inverser sur la
foi d'une perte nette seule.

## 8. Budget paramètres

Hypothèses du cycle : configurations NATURALLES uniquement (seuils fixes
documentés à l'avance : 3 ATR, 100 pips, 4 closes, Donchian 48, EMA 5/20...).
Zéro grille. Maximum respecté (< 10 par hypothèse, plupart = 1).

## 9. Limitations connues

- P000 original testé sur PROXY index CFD (pas d'historique actions
  individuelles pre-market libre sans clé) — documenté DATA_BLOCKED pour
  l'univers actions précis de la vidéo.
- VWAP volume-pondéré seulement si volume > 0 (CFD), sinon TWAP (ASSUMPTION).
- Timezone MT4 inconnue pour les M15 du dépôt (screens sans session).
- Bar-level, pas tick-level (INTRABAR_POLICY=CONSERVATIVE par convention).
- FX Dukascopy : pas de séance dimanche.
