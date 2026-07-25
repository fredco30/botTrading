# Bot live — Donchian breakout multi-paires sur ccxt

Portage du système validé dans `TREND_PORTFOLIO.md`. **Les paramètres sont ceux
que le walk-forward ancré a choisis tout seul** (`1440 / 3 ATR / trail 6`,
13 fois sur 16 ancrages) — ne pas les « améliorer » sans repasser par
`walkforward_trend.py`.

## Pourquoi des perps et pas du spot

Mesuré, pas supposé :

| Mode | Trades | Espérance | × total | × 2022+ |
|---|---|---|---|---|
| Spot long seul (26 bps) | 756 | +0.485 R | 5.07 | 1.42 |
| **Perp long+short** (10 bps + 3 bps/j) | 1178 | **+0.557 R** | **13.85** | **2.72** |

Le spot interdit la vente à découvert et coûte **la moitié du résultat**.
L'espérance *par trade* est presque identique — on perd 40 % des occasions, pas
de la qualité.

Le financement des perps est quasi indolore : la détention moyenne est de
**1.9 jour**, donc 3 ou 6 bps/jour ne changent presque rien (13.85 vs 12.84).

### Le levier n'est pas un problème

| | notionnel / equity |
|---|---|
| médiane | **0.13×** |
| p99 | 0.40× |
| maximum | 0.56× |

**100 % des trades passent sous le plafond ESMA de 2:1**, et 3 positions
simultanées n'utilisent que 0.7× le capital. Le risque vient du stop à 0.5 %,
pas du levier. Aucun risque de liquidation dans ces conditions.

## Démarrage

```bash
pip install ccxt numpy numba
python3 run_bot.py --once          # un cycle, en paper
python3 run_bot.py                 # boucle, en paper
```

Le mode paper utilise les **vraies bougies** de la place et simule uniquement
l'exécution : les écarts observés viennent donc de l'exécution, pas des données.

### Passer en live

```bash
export BITVAVO_API_KEY=...
export BITVAVO_API_SECRET=...
python3 run_bot.py --live
```

Il faut **les deux** : le drapeau `--live` et les clés dans l'environnement.
Une confirmation tapée à la main (`LIVE`) est demandée en plus. Les clés ne sont
jamais lues depuis le fichier de config, qui peut finir dans un dépôt git.

## Architecture

| Fichier | Rôle |
|---|---|
| `live/config.py` | Configuration ; force `allow_short=False` en spot |
| `live/broker.py` | ccxt en live, simulation en paper, **même interface** |
| `live/signal.py` | Décision — importe les indicateurs de `engine.trend` |
| `live/state.py` | Persistance atomique des positions et du drawdown |
| `live/bot.py` | Boucle : bougies → décision → ordre |
| `run_bot.py` | CLI |

`live/signal.py` **importe** `donchian` et `wilder_atr` depuis `engine.trend`
au lieu de les réimplémenter. Une réimplémentation, même fidèle au départ,
diverge dès qu'un seul des deux côtés bouge — et l'écart ne se voit qu'en
production.

## Garde-fous

- **Paper par défaut.** Le live exige drapeau + clés + confirmation tapée.
- **Arrêt sur drawdown** à 30 % : plus aucune ouverture, mais les positions
  existantes restent gérées (les abandonner serait pire).
- **Plafond de positions simultanées** à 3 : les 8 cryptos bougent ensemble,
  8 positions ouvertes ne sont pas 8 paris.
- **Bougie en cours écartée.** `broker.ohlcv()` retire la dernière barre, encore
  ouverte. Décider sur une barre incomplète est la première cause d'écart entre
  un backtest et un bot.
- **Une paire en erreur n'interrompt pas les autres.** Une position ouverte non
  surveillée est bien pire qu'un signal manqué.
- **Écriture d'état atomique** (fichier temporaire + renommage) : une coupure ne
  laisse pas un JSON tronqué.

## Écarts assumés avec le backtest

1. **Entrée en retard.** Le backtest entre au niveau du canal via un ordre stop.
   Le bot détecte le franchissement sur la barre close puis entre au marché : le
   prix a déjà bougé dans l'heure. Toujours en retard, jamais en avance — c'est
   un coût réel, pas une illusion favorable. Un ordre stop laissé sur le marché
   supprimerait cet écart au prix d'ordres orphelins si le bot tombe.
2. **Sortie sur stop en retard**, pour la même raison.
3. **Pas de swap ni de financement modélisés côté bot** — ils sont prélevés par
   la place et apparaissent dans l'equity.

## Ce qui n'a PAS été testé

**Le bot n'a jamais parlé à une vraie place.** L'environnement de développement
bloque les API d'exchange, donc tout a été validé hors ligne, sur un marché
synthétique : cassure détectée, stop suivi de 114 à 172, sortie sur stop,
retournement short. La logique est vérifiée, l'intégration ccxt ne l'est pas.

**À faire avant tout live :**
1. `python3 run_bot.py --once -v` et vérifier que les bougies arrivent
2. Laisser tourner **plusieurs semaines en paper**
3. Comparer les trades obtenus à ceux du backtest sur la même période
4. Passer en live à **risque réduit** (0.1-0.2 %) avant 0.5 %

## Choix de la place

`bitvavo` est la valeur par défaut (Pays-Bas, MiCA). Les perps n'y sont pas
forcément disponibles — vérifier, et sinon basculer sur une place qui en propose
et qui reste accessible depuis l'UE. Le changement se fait par une seule ligne
de config : `exchange` et `market_type`.

Si aucune place UE ne propose de perps accessibles, `"market_type": "spot"`
fonctionne — `allow_short` est alors désactivé automatiquement — mais attends-toi
à la moitié du résultat.
