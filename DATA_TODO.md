# Données à exporter — liste de courses

Le moteur v2 tourne sur 4 instruments. Le facteur qui limite le résultat n'est
ni le réglage ni le risque, c'est le **nombre de paris décorrélés**. Mesuré :
1 instrument → ×1.2-1.5 sur 5 ans, 4 instruments → ×6.5-7.6 au même risque.

⚠️ **Le critère est la décorrélation, pas le nombre.** EURUSD, GBPUSD et USDJPY
sont trois façons de parier sur le dollar. Ajouter AUDUSD n'apporte qu'une
fraction de ce qu'apporte un indice actions ou le pétrole, qui répondent à des
moteurs entièrement différents.

## Priorité 1 — moteurs totalement différents

Ce sont ceux qui changent vraiment le portefeuille.

| Symbole MT4 (variantes) | Moteur économique | Pourquoi |
|---|---|---|
| `US30` / `DJ30` / `US30Cash` | actions US | Aucun lien avec le FX. Tendances longues et propres. |
| `NAS100` / `USTEC` / `NAS100Cash` | tech US | Le plus tendanciel de tous les indices. |
| `USOIL` / `WTI` / `XTIUSD` | énergie | Décorrélé du dollar ET des actions. Grosses tendances. |
| `XAGUSD` | argent | Corrélé à l'or mais 2-3× plus volatil — pas un doublon. |
| `GER40` / `DE40` / `GER30` | actions Europe | Complète US30/NAS100. |

**Si tu n'en fais que trois : `US30`, `NAS100`, `USOIL`.**

## Priorité 2 — FX avec d'autres moteurs

| Symbole | Moteur |
|---|---|
| `AUDUSD` | matières premières / Chine |
| `USDCAD` | pétrole (inverse d'USOIL) |
| `USDCHF` | valeur refuge |

## Priorité 3 — croisées sans dollar

`EURJPY`, `GBPJPY`, `EURGBP`. Elles retirent complètement le facteur dollar,
mais l'apport est plus faible que la priorité 1.

## Procédure (identique à ce que tu as déjà fait)

Une seule fois :
1. **Outils > Options > Graphiques** → « Max. de barres dans l'historique » = `999999999`
2. **Redémarrer MT4**

Pour chaque symbole :
3. **F2** (Centre d'historique) → le symbole → **M15** → **Télécharger**
4. Ouvrir un graphique **M15** de ce symbole → **Home** maintenu jusqu'au début
5. **Fichier > Enregistrer sous** → `SYMBOLE15.csv` dans le dossier du projet

**Le H1 n'est pas nécessaire** — le moteur le reconstruit par agrégation du M15,
vérifié identique au point près sur 175 992 bougies.

## Contrôle avant de pousser

```powershell
Get-ChildItem *15.csv | ForEach-Object {
    "{0,-16} {1,8} lignes   {2}" -f $_.Name, (Get-Content $_ | Measure-Object -Line).Lines, (Get-Content $_ -First 1)
}
```

- **Bon** : ≥ 150 000 lignes, première ligne datant de 2010 ou avant
- **Mauvais** : ~65 000 lignes → l'étape 2 (redémarrage) a été sautée

**Minimum utile : 10 ans.** En dessous, l'instrument ne peut pas être testé hors
du régime actuel — l'erreur qui a coûté trois presets sur l'EMA Pullback.
Beaucoup de CFD indices sur MT4 ne remontent qu'à 2015-2018 ; exporte-les quand
même, mais je les traiterai comme des données de second rang.

## Push

```powershell
cd C:\Users\projets\botTrading
git add *15.csv
git status --short      # verifier une ligne A par fichier AVANT de committer
git commit -m "data: instruments supplementaires M15"
git push
```

Ne mets **jamais** un fichier inexistant dans un `git add` : git annule la
commande entière sans rien signaler. C'est arrivé deux fois.

## Crypto — le seul bloc que tu peux récupérer sans MT4

Les dépôts de départ (Freqtrade, Hummingbot, CCXT) étaient tous crypto, et ce
n'est pas un hasard : **la crypto est le terrain naturel du suivi de tendance.**
Elle tend violemment, tourne 24/7 (aucun gap de week-end), et les données sont
publiques et gratuites.

`fetch_crypto.py` télécharge tout depuis Binance et écrit directement le format
MT4 que le moteur lit. À lancer **sur ta machine** (l'environnement distant
bloque `api.binance.com`) :

```powershell
cd C:\Users\projets\botTrading
python fetch_crypto.py
git add *15.csv
git status --short
git commit -m "data: crypto M15 depuis Binance"
git push
```

Par défaut : BTC, ETH, BNB, SOL, XRP, ADA, LTC, LINK en M15 depuis 2017.
Comptez 10-20 minutes de téléchargement (l'API est paginée à 1000 bougies).

### Trois réserves, à lire avant de s'enthousiasmer

1. **~8 ans d'historique seulement.** C'est sous le seuil de 15 ans que ce
   projet s'est imposé après avoir perdu trois presets. Et ces 8 ans
   contiennent deux bull runs historiques (2017, 2020-21) qui n'ont aucune
   raison de se reproduire.

2. **Biais du survivant.** BTC et ETH sont les gagnants *connus aujourd'hui*.
   En 2017 le portefeuille « évident » contenait aussi BCH, EOS, XEM. Tester
   uniquement les survivants surestime mécaniquement le résultat. Atténuation
   partielle : inclure quelques pièces mortes ou décevantes (XRP, ADA, LTC
   sont dans la liste par défaut pour ça).

3. **⚠️ Le piège le plus grave : les données Binance ne sont PAS ton exécution.**
   Binance = spot, spread quasi nul, pas de financement overnight sur le spot.
   IC Markets = CFD crypto, avec un spread BTCUSD couramment à **$20-50** et un
   financement overnight lourd. C'est exactement la leçon du swap découverte
   aujourd'hui, en dix fois pire. Un backtest sur données Binance exécuté chez
   IC Markets peut perdre de l'argent là où le backtest en gagne.

   **Avant toute conclusion crypto : dis-moi le spread réel et le financement
   overnight de ton broker sur BTCUSD et ETHUSD.** Je les intègre dans
   `engine/instruments.py` comme pour les autres. Sans ça, je marquerai la
   crypto comme non calibrée, au même titre que l'or.

## À part : calibrer XAUUSD

L'or affiche le meilleur PF des quatre (2.26) mais son spread et son swap sont
**devinés** — aucun rapport MT4 or n'existe dans le dépôt. C'est la réserve la
plus lourde du système.

Pour la lever : lancer **n'importe quel** backtest MT4 sur **XAUUSD M15** avec
`EMA_Pullback_pyramid` (la config n'a aucune importance, même mauvaise), puis
exporter la liste de trades en `.txt` tabulé. J'en extrais le spread, le swap et
le tick value exactement comme pour les trois autres paires.

## Ce dont je n'ai PAS besoin

- Le H1, le M5, le M1 — inutiles
- Les volumes — non utilisés par le système
- Les données de news — le système n'a aucun filtre calendaire, volontairement
- Des données tick — l'exécution est modélisée en ordre stop sur bougie H1
