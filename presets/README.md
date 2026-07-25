# Presets MT4 — EMA_Pullback_pyramid v1.20

Fichiers `.set` à charger directement dans le Strategy Tester. Zéro paramètre
à saisir à la main.

## Procédure

1. **MetaEditor** (F4) → ouvrir `EMA_Pullback_pyramid.mq4` → **F7** (compiler).
   Vérifier `0 errors`.
2. **MT4** → **Ctrl+R** (Strategy Tester).
3. Expert Advisor : `EMA_Pullback_pyramid`
4. Symbole : la paire testée. Période : **M15**. Modèle : **Every tick**.
5. **Propriétés du test** → onglet **Paramètres** → bouton **Charger** →
   choisir le `.set` correspondant à la paire.
6. **Toujours cliquer « Remise à zéro » avant chaque run.** Le tester MT4 met
   les inputs en cache après une recompilation et rejoue silencieusement les
   anciennes valeurs — c'est déjà noté dans `CLAUDE.md`.
7. Dépôt initial **10 000**, levier au réglage habituel.
8. Lancer, puis onglet **Résultats** → clic droit → **Enregistrer sous** →
   fichier `.htm`.

## Ce que chaque fichier fixe réellement

`ApplyPreset()` écrase la plupart des valeurs runtime à partir de l'enum
`Preset`. Les seules lignes qui comptent vraiment sont donc :

| Ligne | EURUSD | GBPUSD | USDJPY |
|-------|--------|--------|--------|
| `Preset` | 0 | 1 | 2 |
| `PyramidMode` | 3 (MODE_PAIR) | 3 | 3 |
| `MagicNumber` | 20260410 | 20260411 | 20260412 |

Le reste est écrit à ses valeurs par défaut pour que le fichier soit
auto-documenté et immunisé contre un input resté en cache.

**Les magic numbers sont volontairement différents.** `CountOpenTrades()` filtre
par magic : avec le même numéro sur trois graphiques, chaque EA compterait les
positions des deux autres et bloquerait ses propres entrées.

## Attendus (moteur Python, à confirmer en tester)

| Paire | Période | Trades | Net | PF | DD |
|-------|---------|--------|-----|----|----|
| EURUSD | 2023.03 → 2025.10 | 105 | +$25 293 | 2.54 | 8.7 % |
| GBPUSD | 2021.01 → 2026.04 | 81 | +$9 481 | 1.90 | 9.1 % |
| USDJPY | 2023.02 → 2025.09 | 97 | +$18 189 | 2.24 | 11.2 % |

Le moteur est calibré à 0.006 % du net MT4 sur EURUSD et 0.024 % sur GBPUSD,
mais sur des runs **sans pyramide multi-paires**. Un écart est possible ici.

### Si l'écart dépasse ~5 %

Exporte le rapport en liste de trades (`.txt` tabulé, comme les
`resultats_*.txt` existants) et compare :

```bash
python3 calibrate_pullback_pyramid.py --pair GBPUSD \
    --report ton_rapport.txt --show 20
```

Le script dit exactement quels trades divergent et pourquoi : entrée, SL, lot,
sortie, et les trades qu'un côté a pris et pas l'autre.

## Avant le live

- Ces chiffres sortent du moteur Python, pas encore du tester MT4.
- USDJPY repose sur **2.6 ans** seulement (trou de 207 jours dans le CSV après
  2025.09) et concentre 74 % du profit sur L2. GBPUSD est le résultat le plus
  solide : 5.3 ans propres, 6 années positives sur 6.
- Demo d'abord, `RiskPercent = 0.5` au démarrage.
