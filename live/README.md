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

## Le portage trade-t-il bien la stratégie validée ?

Oui, et c'est mesuré. `tests/test_integration_replay.py` rejoue les **vraies
bougies H1** du CSV à travers `Bot.step()`, cycle par cycle, et compare les
trades obtenus à ceux du noyau numba sur exactement les mêmes barres. Deux
chemins de code entièrement différents, un seul jeu de bougies.

| Symbole | Appariés | Absorbés | Découpages |
|---|---|---|---|
| BTCUSD | 54/55 | 1 | 1 |
| ETHUSD | 50/52 | 2 | 0 |
| BNBUSD | 45/48 | 3 | 3 |
| SOLUSD | 47/51 | 4 | 1 |
| XRPUSD | 35/37 | 2 | 2 |
| ADAUSD | 36/36 | 0 | 1 |
| LTCUSD | 42/46 | 4 | 1 |
| LINKUSD | 42/42 | 0 | 0 |

**367 trades, 0 signal raté, 0 signal inventé, sens identique partout.**

Les écarts restants sont classés, pas masqués. *Absorbé* : le backtest a coupé
en deux ce que le bot a traversé d'une traite — son stop, calculé sur un prix
d'entrée légèrement différent, ne l'a pas sorti. *Découpage* : l'inverse. Dans
les deux cas l'exposition est la même, seul le découpage en tickets diffère.
Seuls un signal raté ou inventé font échouer le test.

### Le coût d'exécution n'est pas mesurable sur cet échantillon

Le bot est structurellement en retard sur le backtest (détection à la clôture
puis ordre au marché, contre un ordre stop posé au niveau du canal). On
attendrait donc un P&L systématiquement inférieur. Ce n'est **pas** ce qu'on
observe :

| | BTC | ETH | BNB | SOL | XRP | ADA | LTC | LINK |
|---|---|---|---|---|---|---|---|---|
| écart P&L | +49% | +111% | +60% | +325% | −19% | −33% | signe inversé | −32% |

Agrégé : backtest 6 875 $, bot 9 059 $, soit **+32 % en faveur du bot**.

Personne ne doit lire ça comme un avantage. C'est la démonstration que
**40 à 55 trades par symbole ne suffisent pas à mesurer un coût d'exécution** :
en suivi de tendance le P&L est porté par trois ou quatre trades de queue, et de
quel côté d'un stop ils tombent est un tirage au sort qui écrase largement les
quelques points de base d'écart d'entrée. Le coût réel du retard est positif,
mais il est enfoui sous le bruit — ne pas le budgéter à zéro pour autant.

## Ce qui n'a PAS été testé

**Le bot n'a jamais parlé à une vraie place.** L'environnement de développement
bloque les API d'exchange, donc l'intégration ccxt elle-même n'est pas vérifiée :
tout a été validé hors ligne, sur marché synthétique d'abord (cassure détectée,
stop suivi de 114 à 172, sortie sur stop, retournement short) puis sur bougies
réelles via le rejeu ci-dessus. La **stratégie** est vérifiée, la **plomberie
réseau** ne l'est pas.

**À faire avant tout live :**
1. `python3 run_bot.py --once -v` et vérifier que les bougies arrivent
2. Laisser tourner **plusieurs semaines en paper**
3. Comparer les trades obtenus à ceux du backtest sur la même période
4. Passer en live à **risque réduit** (0.1-0.2 %) avant 0.5 %

## Empreinte VPS

Mesuré, pas estimé :

| Étape | RSS |
|---|---|
| python seul | 8 Mo |
| + modules du bot | 27 Mo |
| + ccxt | 79 Mo |
| **+ calcul des 8 paires** | **82 Mo** |

**~82 Mo en fonctionnement.** Un VPS à **512 Mo suffit largement**, 1 Go est
confortable. Le CPU est négligeable : un cycle complet sur 8 paires coûte moins
de 5 ms de calcul, le reste est de l'attente réseau.

Les données ne pèsent rien : 1 459 barres H1 × 6 colonnes = **68 Ko par paire**,
et elles sont traitées une paire à la fois.

### D'où viennent les 82 Mo

`ccxt` en représente 52 à lui seul — il importe plus de cent classes d'échange
au chargement. C'est incompressible sans bricoler ses internes, ce qui ne vaut
pas le risque.

**Numba a été sorti du chemin live** : il coûtait 68 Mo (21 à l'import, 47 de
plus à la compilation JIT) pour un gain nul. Le bot calcule 1 459 barres toutes
les cinq minutes, ce qui prend **0.6 ms en numpy pur**. Le backtest, lui, garde
numba — il rejoue 170 000 barres des centaines de fois.

Concrètement : `engine/channels.py` contient les indicateurs en numpy pur,
`engine/__init__.py` importe ses sous-modules paresseusement (PEP 562) pour que
`from engine.channels import ...` ne tire pas tout le paquet, et
`tests/test_channels.py` verrouille l'équivalence — **bit-identique**, écart
0.00e+00 sur 5 jeux de test jusqu'à 170 000 barres.

Sans ce verrou, le bot pourrait un jour ne plus trader la stratégie validée sans
que rien ne le signale.

## Choix de la place

`bitvavo` est la valeur par défaut (Pays-Bas, MiCA). Les perps n'y sont pas
forcément disponibles — vérifier, et sinon basculer sur une place qui en propose
et qui reste accessible depuis l'UE. Le changement se fait par une seule ligne
de config : `exchange` et `market_type`.

Si aucune place UE ne propose de perps accessibles, `"market_type": "spot"`
fonctionne — `allow_short` est alors désactivé automatiquement — mais attends-toi
à la moitié du résultat.
