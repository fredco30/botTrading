# Hypothèses exploratoires testées (Phase 2B) — EXPLORATORY, pas une validation

Écran multi-familles sur la même fenêtre contaminée stricte
[2010-01-04, 2026-04-09) — 402 911 barres M15 EURUSD. Toutes les familles
sont causales (décision à open[i], données clôturées uniquement).
Avertissement multiple-testing : 8 familles × 5 horizons × 2 sens ≈ 80
lectures ; seul un effet consistant et d'amplitude exploitable aurait dû
retenir l'attention.

## Coûts de référence (SYNTHETIC, non surmontables par les effets observés)

| Scénario | Spread | Slippage/side | Commission | ≈ Aller-retour |
|---|---|---|---|---|
| LOW_COST | 0.3 pip | 0.2 pip | 2 $/lot/side | ≈ 1.1 pips |
| NORMAL_COST | 0.8 pip | 0.5 pip | 3.5 $/lot/side | ≈ 2.5 pips |
| STRESS_COST | 1.5 pip | 1.0 pip | 7 $/lot/side | ≈ 5.0 pips |

## Résultats par famille

| Famille | Définition (causale) | N | Verdict |
|---|---|---:|---|
| EMA_BASE_CORE_V1 (Phase 1) | signal figé complet | 19 106 | **NO_EDGE** : −0.10 à −0.47 pips à tous les horizons, win 46-47 % |
| H1 trend+pullback | ablation : sans rejet/ratio/RSI | 194 455 | Néant : ±0.05 pip, win 49.6 % |
| H2 trend+pullback+couleur | sans ratio/RSI | 53 262 | Négatif partout (−0.07 à −0.15) |
| H3 signal complet sans RSI | sans RSI | 19 512 | Identique au signal complet → le RSI ne détruit pas l'edge, il n'y en a pas |
| H4 trend+rejection | sans pullback | 135 750 | Négatif partout (−0.13 à −0.35) |
| H5 pullback+rejection sans tendance | direction = polarité seule | 114 232 | Négatif partout (−0.08 à −0.21) |
| H6 RSI mean-reversion | LONG RSI<30, SHORT RSI>70 | 36 035 | **Positif mais microstructure** : +0.16 à +0.23 pips, win 54 % à 15m, 12/17 années positives, t≈4.5 — mais 5-10× sous LOW_COST ; pic à 12h (+0.71) puis −0.49 à 24h (non monotope) |
| H7 breakout Donchian 24h H1 | clôture H1 hors canal 24h | 36 879 | Négatif partout, s'aggrave aux longs horizons (−1.6 pip à 12h) |

## Lecture

1. Aucune sous-partie du signal EMA ne porte plus d'information que le
   signal complet : les ablations H1-H5 sont toutes ≤ 0. Le « pouvoir
   prédictif » recherché n'existe pas à cette échelle de temps sur EURUSD.
2. H6 (mean reversion RSI) est le seul effet statistiquement réel — c'est
   un phénomène de microstructure bien connu — mais son amplitude
   (+0.2 pip) est indéfiniment plus petite que n'importe quel scénario de
   coûts. Une stratégie qui le traderait perdrait ~0.9-2.3 pips par trade
   même en LOW_COST.
3. H7 confirme qu'un breakout intraday simple n'a pas de dérive positive
   sur cette fenêtre.
4. Horizons étendus (jusqu'à 24h) : rien ne change la conclusion ; les
   effets positifs résiduels ne sont pas monotoypes et restent sous les
   coûts.

## Décision

- **EMA_BASE_REJECTED** (Phase 1).
- Phase 2A (construction d'une stratégie) **non déclenchée** : aucun
  signal n'a démontré une espérance brute supérieure aux coûts.
- SMC **non reconstruit** : conformément à la mission, la reconstruction
  propre d'un système à ~25 degrés de liberté sans aucun signal préalable
  convaincant n'est pas un usage raisonnable de la mission.
- Auto-correction documentée : `EmaBaseVariant.evaluate` lisait
  `_ema50_hist` sans garde quand `require_trend=False` (IndexError sur
  warm-up H1 incomplet) — corrigé en ne calculant les features H1 que si
  `require_trend=True`. Aucune règle stratégique changée.
