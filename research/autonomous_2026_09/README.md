# Recherche autonome Forex — nuit du 2026-09-10/11

Mission : trouver ou éliminer honnêtement une piste Forex prometteuse,
en utilisant le moteur causal canonique et le signal figé
EMA_BASE_CORE_V1, sans jamais toucher à l'OOS 2026-04-09 → 2026-07-24.

## Verdict final

```
NO_ROBUST_FOREX_EDGE_FOUND
```

## Contenu

| Fichier | Rôle |
|---|---|
| `ema_base_event_study.md` | Rapport Phase 1 : event study du signal figé (19 106 signaux) → NO_EDGE |
| `ema_event_study.json` | Données brutes Phase 1 (par horizon / sens / année) |
| `hypotheses.md` | Phase 2B : 7 familles exploratoires (ablations + RSI-MR + Donchian), verdicts |
| `phase2b_screen.json` | Données brutes du screening |
| `extended_horizons.py/.json` | Vérification multi-jours (jusqu'à 24h) |
| `event_study.py`, `variants.py`, `phase2b_screen.py` | Code d'expérimentation (causal, déterministe) |

## Résumé exécutif

1. **Phase 1** — le signal EMA Pullback isolé (figé, sans money management
   ni filtres post-hoc) ne contient aucune dérive positive : −0.10 à
   −0.47 pip de moyenne open-to-open sur 19 106 signaux, win rate 46-47 %.
   → `EMA_BASE_REJECTED`.
2. **Phase 2B** — 7 familles exploratoires (ablations du signal, RSI mean
   reversion, breakout Donchian 24h). Toutes nulles ou négatives, sauf la
   mean reversion RSI (+0.2 pip, significative mais microstructure) :
   5-10× sous même le scénario de coûts le plus favorable.
3. **Phase 2A non déclenchée** : aucune stratégie de trading construite —
   aucun signal ne survit aux coûts, donc rien à robustifier.
4. **SMC non reconstruit** : aucun signal préalable convaincant ne
   justifiait l'investissement.
5. **OOS intacte** : aucun accès, même indirect (dataset restauré depuis
   le snapshot git qui précède l'extension 2026-04-09+, + filtre strict
   au chargement).

Reproduction : `python event_study.py <eurusd_m15.csv> out.json`
(le CSV est filtré strictement à [2010-01-04, 2026-04-09) avant analyse ;
le fichier de données n'est volontairement pas committé).
