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

### Le levier est le facteur qui limite `max_concurrent`

Le notionnel d'une position vaut `risque / (distance au stop en %)`. Le stop
étant à 3 ATR, soit 2-4 % du prix en crypto, le notionnel est un multiple du
risque — il **double si `risk_pct` double**.

| notionnel / equity | à 0.5 % de risque | **à 1 % (réglage actuel)** |
|---|---|---|
| médiane | 0.15× | **0.29×** |
| p95 | 0.33× | 0.66× |
| p99 | 0.43× | 0.86× |

Exposition totale selon le nombre de positions ouvertes, à 1 % de risque :

| positions | exposition |
|---|---|
| 3 | 0.88× |
| **4 (réglage actuel)** | **1.17×** |
| 8 | 2.34× — **au-dessus de `max_leverage = 2.0`** |

C'est ce qui interdit de monter `max_concurrent` à 8 pour exploiter le
multi-vitesse : le plafond de levier rognerait les positions en silence et le
bot ne traderait plus la stratégie mesurée. Sous 4 positions on reste dans le
plafond ESMA de 2:1, sans risque de liquidation.

## Calibrage du risque : viser le drawdown FLOTTANT

⚠️ **Les DD des backtests de ce dépôt sont des DD sur equity *clôturée*.**
`portfolio.simulate()` ne crédite le capital qu'à la fermeture d'un trade, donc
une position ouverte qui part contre nous n'apparaît nulle part tant qu'elle
n'est pas sortie. C'est la métrique standard des rapports MT4, et elle est
structurellement optimiste sur du suivi de tendance — où l'on tient des
positions des semaines et où le trailing à 6 ATR est *conçu* pour rendre du
profit ouvert avant de sortir.

Le bot, lui, lit l'equity **mark-to-market** du broker (`state.check_drawdown`).
Ce sont deux définitions différentes du même mot. Mesuré sur 2021-2026 :

| Configuration | DD clôturé | DD flottant |
|---|---|---|
| 0.5 %, max 3 | 13.4 % | **16.0 %** |
| 0.5 %, max 4 | 14.3 % | **16.7 %** |
| 1.0 %, max 3 | 25.5 % | **29.6 %** |
| 3 vitesses, 0.5 %, max 6 | 24.7 % | **29.4 %** |

**Majorer d'environ 20 % un DD clôturé pour obtenir ce que le compte affichera.**
Et c'est une borne basse : le flottant est calculé sur les clôtures H1, pas sur
les mèches, donc les creux intra-barre réels sont plus profonds.

Le réglage actuel (1 % / max 4) est calibré pour **30 % de DD flottant**, seuil
retenu comme tenable. `max_drawdown_pct` est à 45 % en conséquence : un
disjoncteur placé à 30 % couperait en fonctionnement normal, au creux, juste
avant la reprise de tendance qui paie — et `halted` est définitif.

Résultat de ce réglage sur 2021-2026, **la pire fenêtre de 5 ans du jeu de
données** : ×13.0 (1 000 € → 13 024 €), CAGR 68.6 %.

## Petit compte : ce qui change et ce qui ne change pas

Le système est proportionnel — ×13.02 au départ de 1 000 € comme de 10 000 €,
même DD. Vérifié, pas supposé :

- **Minimum d'ordre : aucun problème.** Notionnel médian de 292 € sur un compte
  de 1 000 €, le plus petit à 47 €. 0 % des trades sous le minimum de 10 €. Ça
  tient encore à 250 € de capital.
- **Levier : voir plus haut.** C'est la seule contrainte qui mord vraiment.
- **Coûts fixes : le vrai handicap.** Un VPS n'est pas un pourcentage, donc il
  ponctionne le petit compte au moment où il compose le plus fort.

| VPS | Capital final sur 5 ans | Perte |
|---|---|---|
| 0 €/mois | 13 623 € | — |
| 3 €/mois | 12 772 € | −6.2 % |
| 5 €/mois | 12 205 € | **−10.4 %** |
| 10 €/mois | 10 786 € | **−20.8 %** |

5 €/mois ne coûte pas 300 € sur 5 ans mais **1 400 €** : chaque euro prélevé en
année 1 est un euro qui ne compose plus pendant quatre ans. Sur un compte de
10 000 € le même VPS coûte 1 % du résultat au lieu de 10 %.

**Sur un petit compte, ne pas payer d'hébergement.** Le bot tient dans 82 Mo et
moins de 5 ms de calcul par cycle : un Oracle Cloud Free Tier (ARM, gratuit) ou
un Raspberry Pi déjà en place suffisent. C'est la plus grosse optimisation
disponible à cette taille — elle vaut plus que tout ce qui a été gratté sur les
paramètres.

## Démarrage

```bash
pip install ccxt numpy numba
python3 run_bot.py --dry-run-api   # vraie place, LECTURE SEULE
python3 run_bot.py --once          # un cycle, en paper
python3 run_bot.py                 # boucle, en paper
python3 dashboard.py               # suivi sur http://127.0.0.1:8000
```

### `--dry-run-api` : tester la plomberie sans qu'un ordre puisse partir

Le paper trading simule l'exécution, donc il ne teste pas la moitié dangereuse
de l'intégration : le nom exact des marchés, l'authentification, la pagination
des bougies, la précision des tailles. Ce mode fait tous ces appels **pour de
vrai**, en lecture seule.

Le blocage est dans `DryRunBroker`, la couche par laquelle tout ordre doit
passer — pas dans `bot.py`. Une garde dans la logique de décision se contourne
par un chemin oublié ; une garde dans le broker est la seule porte.

Il vérifie, dans l'ordre :

| Vérification | Ce qu'elle attrape |
|---|---|
| marchés | la place répond, `load_markets` aboutit |
| **symboles** | `BTC/USDT:USDT` existe-t-il vraiment — l'échec le plus probable, une place sans perpétuels ne le connaît pas. Propose les noms voisins. |
| timeframe | `1h` supporté |
| bougies | assez de barres, espacement de 3600 s, dernière barre fraîche |
| rythme | un cycle tient-il bien sous `poll_seconds` |
| solde / positions | les clés ouvrent-elles la lecture du compte |
| dimensionnement | la taille calculée passe-t-elle les minimums de la place |
| levier | `max_concurrent` positions dépassent-elles `max_leverage` |

**Les clés API ne sont pas nécessaires.** Sans elles, tout est testé sauf le
solde et les positions, et le dimensionnement est simulé sur `initial_equity`.

Si tout passe, un vrai cycle de décision tourne sur les bougies réelles et
affiche les ordres qui *auraient* été envoyés. `tests/test_dryrun.py` verrouille
la propriété critique : un faux exchange lève une exception si une écriture est
tentée, et un témoin vérifie que le broker normal, lui, l'atteint bien — sans ce
témoin, le test ne prouverait que l'absence de chemin, pas son blocage.

### Le tableau de bord

`dashboard.py` lit `live_state.json` et `live_bot.log`, rien d'autre : aucun
appel à la place, aucune écriture. Un tableau de bord qui peut passer des ordres
est une surface d'attaque pour zéro bénéfice.

Bibliothèque standard uniquement — pas de Flask, pas de npm. Il affiche
l'equity flottante, le drawdown avec sa distance au disjoncteur, les positions
ouvertes avec leur P&L latent et leur distance au stop, l'historique, et la fin
du journal avec les erreurs en évidence.

**Détection de bot mort.** C'est la fonction la plus importante de la page. Si
le processus s'arrête, le fichier d'état reste parfaitement valide et le
tableau de bord afficherait une situation rassurante — panne silencieuse, le
pire mode de défaillance. `State.save()` écrit donc un `updated_ts` epoch (pas
seulement le texte, qui casse au changement d'heure et suppose le même fuseau)
et la page compare :

| Retard | Affichage |
|---|---|
| > 1.5 cycle | avertissement — un cycle manqué, probablement du réseau |
| **> 3 cycles** | **bandeau rouge : le bot ne répond plus**, avec le nombre de positions laissées sans surveillance et les commandes `systemctl` / `journalctl` |

Le titre de l'onglet passe à `⛔ ARRÊTÉ — …`, pour que l'alerte soit visible
sans mettre la page au premier plan. Les bandeaux s'empilent : un bot mort
*avec* des positions ouvertes et un drawdown déclenché doit montrer les trois.

**Il n'a aucune authentification** et n'écoute donc que sur `127.0.0.1`. Depuis
un VPS, passer par un tunnel plutôt que par `--host` :

```bash
ssh -L 8000:localhost:8000 user@vps
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
4. Passer en live à **risque réduit** (0.2 %) avant le 1 % calibré

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
