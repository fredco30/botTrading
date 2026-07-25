# Bot v2 — Portefeuille Donchian Breakout

Repart de zéro. Objectif fixé : **10 000 → 100 000 en 5 ans** (×10, soit 58 % de CAGR).

**Verdict d'emblée : l'objectif n'est pas atteint de façon fiable.** Médiane à
2.6× sur 5 ans à un risque tenable. Le détail, les chiffres et la route pour
s'en approcher sont ci-dessous.

---

## Pourquoi ce système et pas l'EMA Pullback

Le post-mortem de l'EMA Pullback sur historique complet a donné trois leçons,
et chacune est une contrainte de conception ici :

| Leçon | Conséquence dans le design |
|---|---|
| Signal PF 0.89-1.19 selon l'époque | On change d'archétype : breakout, pas pullback |
| Les filtres calés sur 3 ans n'apportent rien sur 16 | **Zéro filtre** horaire, journalier ou ATR |
| Un jeu de params par paire = un fit | **Un seul jeu pour les 4 instruments** |
| Un walk-forward sur 2 moitiés du même régime ne protège pas | Jugé sur **45 fenêtres glissantes de 5 ans** |

Comparaison directe, mêmes données, mêmes coûts :

| Instrument | EMA Pullback (PF) | **Breakout (PF)** | Période |
|---|---|---|---|
| EURUSD | 1.27 | **1.68** | 27 ans |
| GBPUSD | 1.14 | **1.38** | 16.5 ans |
| USDJPY | 1.73 | **1.98** | 6.5 ans |
| XAUUSD | 1.03 | **2.26** | 16.5 ans |

Le breakout bat le pullback **sur les quatre**, avec un seul jeu de paramètres
au lieu de quatre presets sur-ajustés.

## Le système

Quatre paramètres. C'est tout.

| Paramètre | Valeur | Rôle |
|---|---|---|
| Canal d'entrée | **2880 barres H1** (~120 j) | Cassure du plus haut/bas |
| Canal de sortie | **960 barres H1** (~40 j) | Sortie sur cassure opposée |
| Stop | **3 × ATR(14)** | Stop initial |
| Trailing | **5 × ATR(14)** | Chandelier depuis l'extrême |

- Exécution en **ordre stop** au niveau du canal (c'est ce qu'est une cassure),
  pas à l'open de la bougie suivante
- **Spread + slippage** facturés à chaque entrée et sortie
- **Swap overnight** facturé, avec le triple du jeudi
- Long et short
- Sizing : risque % de l'équity courante, distance de stop = 3 ATR

Le **trailing stop est structurel** : le désactiver fait passer GBPUSD de
PF 1.38 à **0.65**.

## Résultats — 842 trades, 4 instruments

**Espérance +0.332 R par trade. 44 % de gagnants seulement.** Médiane à −0.29 R,
meilleur trade **+22 R**. Toute la rentabilité est dans la queue droite : on
perd petit souvent et on gagne énorme rarement. C'est l'inverse du profil de
l'EMA Pullback, et c'est ce qui rend le système supportable en DD.

### 45 fenêtres glissantes de 5 ans

| Risque | ×  médian | × min | × max | DD médian | DD pire | ≥ ×10 | fenêtres perdantes |
|---|---|---|---|---|---|---|---|
| 1 % | 1.68 | 1.09 | 2.9 | 8 % | 16 % | 0 % | **0 %** |
| **2 %** | **2.59** | **1.18** | 7.6 | **15 %** | 29 % | 0 % | **0 %** |
| 3 % | 3.74 | 1.26 | 18.5 | 22 % | 41 % | 16 % | **0 %** |
| 4 % | 5.11 | 1.33 | 41.5 | 29 % | 51 % | 31 % | **0 %** |

**Aucune fenêtre de 5 ans perdante, à aucun niveau de risque.** Sur 27 ans et
trois régimes de marché. C'est le premier système du projet dont on puisse dire
ça — et c'est plus important que n'importe quel PF.

## Validation hors-échantillon du **processus**, pas d'une config

Tout ce qui précède partage un défaut : les paramètres ont été choisis en
regardant les mêmes données qui servent à les juger. `walkforward_trend.py`
répond à la vraie question :

> Si, à une date passée, j'avais choisi les paramètres avec **uniquement**
> l'historique disponible à ce moment-là, puis tradé 5 ans sans y toucher —
> qu'est-ce qui se serait passé ?

16 ancrages annuels de 2006 à 2021, paramètres re-choisis à chaque fois sur
l'historique seul, testés sur 5 ans de données qui n'existaient pas encore.

| | Choix ancré (honnête) | Config fixe (avec recul) |
|---|---|---|
| × médian | **3.56** | 3.39 |
| × pire fenêtre | **1.93** | 1.49 |
| Fenêtres perdantes | **0 / 16** | 0 / 16 |

**Écart +5 % en faveur du choix ancré.** Le rétrospectif ne trichait pas — il
était même légèrement conservateur. C'est la première fois dans ce projet qu'un
système passe un test hors-échantillon du processus de sélection lui-même.

Le choix est **stable** : `1440 / 3 ATR / trail 6` retenu **15 fois sur 16**.
Ce n'est pas une grille qui saute d'un optimum à l'autre.

### Le budget de DD ne se transmet pas hors-échantillon

Imposer « DD in-sample ≤ 25 % » au moment du choix laisse quand même passer
**39 % de DD out-of-sample**. Une contrainte de DD calée sur le passé ne borne
pas l'avenir. Le seul levier fiable sur le DD est le **% de risque**, qui est
un cadran linéaire.

### Cadran risque / rendement sur les 16 fenêtres OOS

Config `1440 / 3 / 6`, celle que le processus choisit tout seul :

| Risque | × médian | × min | × max | DD médian | DD pire | ≥ ×10 | perdantes |
|---|---|---|---|---|---|---|---|
| 0.75 % | 1.74 | 1.23 | 2.20 | 9.6 % | 16.9 % | 0 % | 0/16 |
| 1.00 % | 2.05 | 1.32 | 2.82 | 12.6 % | 21.9 % | 0 % | 0/16 |
| **1.25 %** | **2.40** | **1.40** | 3.58 | **15.5 %** | **26.6 %** | 0 % | **0/16** |
| 1.50 % | 2.80 | 1.49 | 4.51 | 18.3 % | 31.1 % | 0 % | 0/16 |
| 2.00 % | 3.71 | 1.68 | 7.00 | 23.7 % | 39.3 % | 0 % | 0/16 |
| 2.50 % | 4.80 | 1.87 | 10.58 | 28.7 % | 46.7 % | 6 % | 0/16 |
| 3.00 % | 6.06 | 2.07 | 15.57 | 33.4 % | 53.2 % | 12 % | 0/16 |

**Point de fonctionnement retenu : 1.25 % de risque par trade.** C'est le
dernier palier qui respecte le plafond de DD de 25-30 % documenté comme
psychologiquement tenable. Il donne **×2.4 médian sur 5 ans** (~19 % de CAGR),
la pire des 16 fenêtres à **×1.40**, et **aucune fenêtre perdante sur 20 ans**.

## Réponse à l'objectif ×10

**Non atteint de façon fiable.**

Sur les 16 fenêtres réellement hors-échantillon :

- À **1.25 %** (DD pire 26.6 %, tenable) : médiane **2.4×**, jamais ×10
- À **2.5 %** : ×10 dans **6 %** des fenêtres, DD pire **46.7 %**
- À **3 %** : ×10 dans **12 %** des fenêtres, DD pire **53.2 %**

Traduit : à un risque tradeable, ce système fait ×2 à ×3 sur 5 ans. Le ×10 est
atteignable seulement en pariant sur un bon régime **et** en acceptant un DD
que tu as toi-même documenté comme intenable.

## La route vers le ×10, quantifiée

Le facteur dominant n'est ni le réglage ni le risque — c'est le **nombre
d'instruments**. Les données le disent sans ambiguïté :

| Fenêtre | Instruments actifs | Multiple sur 5 ans (2 %) |
|---|---|---|
| 1999-2010 | 1 (EURUSD seul) | **1.2 - 1.5×** |
| 2010-2020 | 3 | 2.6 - 5.1× |
| 2020-2026 | 4 | **6.5 - 7.6×** |

Passer de 1 à 4 instruments multiplie le résultat par ~5 **au même niveau de
risque**, parce que des paris décorrélés permettent plus de risque par pari
pour un même DD de portefeuille.

**Étape suivante concrète : exporter 8 à 12 instruments de plus.** Indices
(US30, NAS100, GER40), matières premières (WTI, argent), et les paires FX
majeures manquantes (AUDUSD, USDCAD, USDCHF, EURJPY, GBPJPY). Le moteur les
avale sans modification — il suffit d'ajouter une ligne dans
`engine/instruments.py` et le CSV M15.

Avec 12 instruments au lieu de 4, le même système à 2-3 % de risque devrait
placer la médiane dans la zone ×5 à ×8 sur 5 ans, avec un DD comparable. Le ×10
devient alors un objectif haut plausible plutôt qu'un coup de dés.

## Crypto — 8 instruments, 8.9 ans, et le résultat change tout

Données Binance spot M15 via `fetch_crypto.py`. Le portefeuille passe de 4 à
**12 instruments**.

| Instrument | Trades | PF | DD | Buy & hold |
|---|---|---|---|---|
| BTCUSD | 142 | 1.47 | 10.4 % | 4 261 → 64 370 |
| ETHUSD | 140 | 1.62 | 11.3 % | 298 → 1 873 |
| BNBUSD | 117 | **2.14** | 7.1 % | 1.7 → 569 |
| SOLUSD | 95 | 1.57 | 9.8 % | 3.2 → 74 |
| XRPUSD | 47 | **4.40** | 3.8 % | 0.93 → 1.10 |
| ADAUSD | 104 | 2.07 | 7.0 % | 0.267 → **0.165** |
| LTCUSD | 111 | 1.40 | 14.1 % | 288 → **46** |
| LINKUSD | 93 | 1.28 | 10.1 % | 0.52 → 8.4 |

**Les 8 sont rentables, y compris LTC et ADA qui ont perdu 84 % et 38 % en
buy & hold.** Le système gagne sur des actifs qui ont baissé — c'est le shorting
et le suivi de tendance qui travaillent, pas l'exposition longue au marché.

### L'edge n'est pas qu'un artefact du bull run

| Période | Trades | × (1 % risque) | Espérance |
|---|---|---|---|
| 2017-2019 (avant) | 156 | ×2.90 | +0.710 R |
| 2020-2021 (le bull run) | 249 | ×3.91 | +0.561 R |
| **2022-2026 (après, bear 2022 inclus)** | **444** | **×3.45** | **+0.267 R** |

Positif dans les trois régimes. Mais l'espérance **décroît nettement**
(0.71 → 0.56 → 0.27) et les fenêtres glissantes passent de ×13 à **×3.93** pour
la plus récente. C'est de l'érosion d'edge : le marché crypto devient plus
efficient. **Toute projection doit partir du régime récent, pas de la moyenne.**

### ⚠️ Le lieu d'exécution compte plus que la stratégie

| Scénario de coûts | Espérance | × sur 2022-2026 |
|---|---|---|
| Binance spot (10 bps/côté) | +0.435 R | **3.45** |
| Binance + slippage réaliste | +0.380 R | 2.73 |
| CFD serré (25 bps, 2 bps/j) | +0.344 R | 2.37 |
| **CFD type IC Markets (40 bps, 4 bps/j)** | +0.275 R | **1.72** |
| CFD large (60 bps, 6 bps/j) | +0.183 R | **1.14** |

Le même système, la même période : **×3.45 sur Binance spot, ×1.14 en CFD
large.** Le choix du broker détruit ou préserve les deux tiers du résultat.
C'est la leçon du swap de l'EMA Pullback, portée à une échelle où elle décide
de tout.

## Estimation prospective honnête — 12 instruments, régime récent seul

2022.01 → 2026.07 (4.5 ans, hors bull run), 708 trades :

| Risque | × réel 4.5 ans | CAGR | DD | Extrapolé 5 ans |
|---|---|---|---|---|
| 0.50 % | 3.07 | 28 % | 16 % | 3.44 |
| **0.75 %** | **5.14** | 43 % | **23 %** | **6.06** |
| **1.00 %** | **8.39** | 60 % | **29 %** | **10.37** |
| 1.50 % | 20.71 | 95 % | 41 % | 28.04 |

**À 1 % de risque, l'objectif ×10 est atteint** — sur le régime le plus
défavorable disponible, coûts Binance spot inclus, avec 29 % de DD.

Ce qui reste à vérifier avant d'y croire :
- 4.5 ans seulement, et une seule trajectoire (pas 16 fenêtres indépendantes)
- coûts Binance spot : en CFD, diviser le résultat par ~2
- l'érosion d'edge crypto est réelle et pourrait continuer
- biais du survivant : les 8 paires sont toutes encore cotées en 2026

## Walk-forward ancré sur les 12 instruments

Même test que sur le FX : paramètres re-choisis à chaque ancrage avec
**l'historique seul**, puis tradés 5 ans sans y toucher. 16 ancrages, 2006-2021.

| | Choix ancré | Config fixe (avec recul) |
|---|---|---|
| × médian (1 % risque) | **8.00** | 5.38 |
| × pire fenêtre | **1.43** | 1.20 |
| Fenêtres perdantes | **0 / 16** | 0 / 16 |

Paramètres retenus : `1440 / 3 ATR / trail 6` **13 fois sur 16**. Le processus
converge, il ne saute pas d'un optimum à l'autre.

### ⚠️ Pourquoi le × médian de 8.00 ne doit pas être pris au pied de la lettre

Les fenêtres récentes affichent ×444, ×324, ×88. Ces chiffres ne sont **pas
atteignables**. À 1 % de risque depuis 10 000 €, ×444 implique des positions
444 fois plus grosses en fin de course — sur des altcoins, tu deviens le marché.
Le simulateur suppose une liquidité infinie et un slippage constant ; ni l'un ni
l'autre ne tient à cette échelle.

Il faut aussi voir d'où vient la médiane : les ancrages 2006-2013 (FX seul,
la crypto n'existait pas) donnent ×1.43 à ×4.17. Tout ce qui dépasse vient des
ancrages 2014+, tous dominés par la même envolée crypto 2016-2021 et tous
chevauchants.

### Point de fonctionnement réaliste

Avec un plafond de **3 positions crypto simultanées** — les 8 pièces bougent
ensemble, 8 positions crypto ouvertes ne sont pas 8 paris :

| Risque | × médian (16 fen.) | × min | DD médian | DD pire | × médian ère crypto |
|---|---|---|---|---|---|
| 1.00 % | 6.16 | 1.31 | 17 % | 41 % | 59.75 |
| 0.75 % | 4.02 | 1.23 | 13 % | 32 % | 24.52 |
| **0.50 % (cap 3 crypto)** | **2.47** | **1.15** | **9 %** | **19 %** | **8.14** |
| 0.35 % (cap 3) | 1.90 | 1.10 | 6 % | 14 % | 4.48 |

**Retenu : 0.50 % de risque, maximum 3 positions crypto simultanées.**
Aucune fenêtre perdante sur 20 ans, DD pire **19 %**, et ×8.14 médian sur les
fenêtres où les 12 instruments coexistent.

C'est deux fois moins de risque par trade que le portefeuille FX seul (1.25 %),
parce que 12 instruments déploient bien plus de capital simultanément.

## Ce qui a été testé et ne marche PAS

**La pyramide, pour la troisième fois.** Ajouter des unités dans une tendance
qui court — l'usage théoriquement correct de l'anti-martingale, sur un profil
de gains à queue longue :

| Unités max | Espérance | × médian 5 ans | DD médian |
|---|---|---|---|
| **1** | **+0.332 R** | **2.59** | 15 % |
| 3 | +0.156 R | 1.42 | 22 % |
| 5 | +0.031 R | 0.98 | 32 % |
| 8 | −0.115 R | 0.66 | 48 % |

Les unités ajoutées se font sortir par le trailing stop quand la tendance
respire, et leur perte annule le gain de l'unité initiale.

**Bilan du projet sur la pyramide : 3 architectures, 3 échecs.** Scalp EMA
Pullback, régime filtré, suivi de tendance. Elle n'a jamais résisté à un
historique complet. C'est une conclusion, pas un accident.

## Réserves honnêtes

1. **XAUUSD n'est pas calibré.** Aucun rapport MT4 or dans le repo : le spread
   est estimé à 0.20 et le swap deviné. L'or pèse lourd dans le résultat
   (PF 2.26). Un run MT4 sur l'or permettrait de recaler ça exactement, comme
   pour les trois autres.
2. **USDJPY ne couvre que 6.5 ans** — dans le régime favorable. Son PF 1.98 est
   le moins fiable des quatre.
3. **Pas encore de code MQL4.** Tout est en Python. Le portage vers l'EA est un
   chantier à part.
4. **Corrélation EUR/GBP** bornée par `corr_groups` mais pas neutralisée. Deux
   positions simultanées restent proches d'un pari double.
5. **Slippage supposé constant.** Sur une vraie cassure en news, il est pire.

## Fichiers

| Fichier | Rôle |
|---|---|
| `engine/trend.py` | Cœur numba : Donchian + ATR + trailing + pyramiding |
| `engine/instruments.py` | Spécifications par instrument, chargement H1 |
| `engine/portfolio.py` | Équity partagée, compounding, fenêtres glissantes |
| `research_trend_portfolio.py` | Reproduit les chiffres in-sample |
| `walkforward_trend.py` | Walk-forward ancré sur le **choix des paramètres** |

```bash
python3 research_trend_portfolio.py               # run in-sample
python3 walkforward_trend.py                      # validation OOS du processus
python3 walkforward_trend.py --max-dd 25          # avec budget de DD
```
