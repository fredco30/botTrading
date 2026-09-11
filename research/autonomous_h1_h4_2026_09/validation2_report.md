# VALIDATION_2 — candidat gelé sur 2023-01-01 → 2026-04-08

Testé UNE FOIS, sans aucune modification. C'est la dernière porte interne
avant l'OOS.

## C2 — F5 vol-compression breakout H1 (L 40, ratio 0.85, horizon 12h)

| | N | MEAN pips | après LOW | après NORMAL | après STRESS | WIN |
|---|---:|---:|---:|---:|---:|---:|
| Agrégat | 285 | +1.59 | +0.59 | **−0.41** | −1.91 | 52.6 % |
| EURUSD | 80 | +3.10 | +2.10 | +1.10 | −0.40 | 53.8 % |
| GBPUSD | 81 | −1.51 | −2.51 | −3.51 | −5.01 | 50.6 % |
| USDJPY | 124 | +2.64 | +1.64 | +0.64 | −0.86 | 53.2 % |

Moyenne hors top-1 % des gains : **+0.01 pip** — l'intégralité de
l'espérance brute tient dans quelques trades.

## Verdict

```
C2 : REJECT — AFTER_NORMAL = −0.41 pip (< 0), MEAN_EX99 ≈ 0, GBPUSD négatif.
```

Le candidat ne survit pas à VALIDATION_2. Il ne se dégage **aucun
candidat robuste** de la mission H1/H4 multi-paires.

Portrait-robot de l'échec (cohérent avec la mission M15 précédente) :
les effets détectés en DISCOVERY (2010-2018) étaient soit des artefacts
de période (mean-reversion, effondrée dès 2019-2022), soit des effets
réels mais d'amplitude inférieure aux coûts (vol-compression breakout :
+1.6 pip brut → −0.4 pip net en 2023-2026).
