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
