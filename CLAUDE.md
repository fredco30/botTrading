# Bot Trading MT4 — Projet Multi-EA

## Contexte projet
Bots de trading automatique MT4. Expert Advisors :
1. **EMA_Pullback_pyramid** — EMA Pullback + Anti-Martingale Pyramid sur wins (**CHAMPION** : PF 1.89 / DD 26% sur 6 ans, +$34k / mode SAFE)
2. **EMA_Pullback_EA** — EMA Pullback baseline sans pyramide (PF 2.12, +$7k sur 3 ans)
3. **regime_pyramid_EA** — Pyramid + filtres régime ADX/BBW/EMA slope (signal générique, exploration abandonnee)
4. **martingale_anti_filtered** — Pyramid seul sans filtres régime (exploration)
5. **SMC_Scalper_EA** — Smart Money Concepts M15+M5 (en dev)

## Personnalite attendue
- Tu vas droit au but, concis, rapide, zero blabla
- Reponses structurees en listes a puces, directement actionnables
- Pas de generalites ni de bullshit
- Si une demande est risquee, tu le dis et tu proposes une alternative
- A chaque reponse, propose au moins une amelioration/optimisation
- Comporte-toi comme un trader experimente qui affine son edge en permanence

---

## EMA Pullback Pyramid EA (CHAMPION ⭐)

Extension de `EMA_Pullback_EA` avec **anti-martingale pyramid** sur les wins consécutifs.
Le signal reste 100% identique (EMA50 H1 trend + EMA20 M15 pullback + rejection).

### Concept pyramide
- **L0 (base)** : 1er trade apres un reset. Lot = base_lot × L0_LotMult
- **L1 (apres 1 win)** : Lot = base_lot × L1_LotMult
- **L2 (apres 2 wins)** : Lot = base_lot × L2_LotMult (cap)
- **LOSS** → streak reset à 0 → prochain trade = L0
- **WIN** → streak++ jusqu'à cap (MaxStreakLevel = 2)

### Pourquoi ça marche
Le signal EMA Pullback cluster les wins. Après un L0 gagnant, le L1 suivant a
un WR **~76.9%** et PF **4.22** (mesuré sur 3 ans). Amplifier les L1 amplifie
directement le profit sans toucher aux losses (qui resetent le streak).

### 3 Modes (input `PyramidMode`)

**MODE_SAFE** (défaut, recommandé pour LIVE)
- `L0=1.0 / L1=4.0 / L2=2.5`
- Backtest EURUSD M15 2020-2026 :
  - Net : **+$34,575 (+346%)**
  - PF : **1.89**
  - DD max : **26.3%**
  - 253 trades | WR 48.2%
  - Return/DD ratio : **1,316**
- 6 années positives sur 7 (seul 2021 négatif : -$1,135)

**MODE_AGGRESSIVE** (experimental, NE PAS utiliser pour démarrage neuf)
- `L0=2.0 / L1=7.0 / L2=4.0`
- Backtest EURUSD M15 2020-2026 :
  - Net : **+$109,621 (+1,096%)**
  - PF : 1.91
  - DD max : **47.3%**
  - Return/DD ratio : **2,317** (meilleur mathématiquement)
- **ATTENTION** : 14 mois de DD 42% au début (2021-02 → 2022-04), puis 9 mois de DD 41% (2022-08 → 2023-05). Impossible à tenir psychologiquement en live neuf.

**MODE_CUSTOM** (pour optimisation fine)
- Utilise les inputs `L0_LotMult`, `L1_LotMult`, `L2_LotMult` directement

### Décomposition par niveau (6 ans, mode SAFE)
| Niveau | N | WR% | Net | PF |
|--------|---|-----|-----|-----|
| L0 | 132 | 48.5% | +$5,654 | 1.57 |
| **L1** ⭐ | 63 | **50.8%** | **+$25,276** | **2.79** |
| L2 | 58 | 44.8% | +$3,644 | 1.25 |

**L1 génère 73% du profit total.** C'est le profit engine. Ne pas le déprécier.

### Lecons apprises sur la pyramide
- Le signal de base doit être RENTABLE (PF > 1.5) pour que la pyramide marche. Sur un signal à PF 0.88 (comme `regime_pyramid_EA`), la pyramide amplifie mais l'edge reste marginal.
- Amplifier L1 (profit engine) est beaucoup plus efficace que L2 (weak link, PF 1.25)
- Garder L2 modéré (≤ 3.0) car son WR chute après 2 wins consécutifs
- Ne JAMAIS pousser le pyramid au point où une seule perte L2 dépasse 5% du capital
- Max DD psychologique tradeable : **25-30%**. Au-delà, 99% des traders abandonnent en live.
- 47% DD en backtest = **intradable** en live pour démarrage neuf
- Risk réduit (`RiskPercent = 0.5`) divise les dollars perdus par 2 mais le DD% reste identique

### Bug fix critique (filtre fantôme PB)
Le filtre `IsPullbackHealthy()` était silencieusement actif sur EURUSD (r_PB_MaxRatio=0.70 jamais override). Causait 8-20 trades au lieu de 124. Corrigé en câblant vraiment le bool `UsePullbackSizeFilter` dans la fonction.
Fichiers concernés : `EMA_Pullback_EA.mq4` et `EMA_Pullback_pyramid.mq4`.

---

## EMA Pullback EA (baseline sans pyramide)

### Architecture
- **H1** : Trend direction via EMA 50 (price above + EMA rising = bullish)
- **M15** : Entree sur pullback vers EMA 20 + rejet confirme
- Mode optionnel **H4+M30** (swing, non optimise)

### Logique d'entree
1. H1 EMA50 donne la direction (slope + price position)
2. M15 : bar 2 touche/croise EMA20 (pullback)
3. M15 : bar 1 cloture au-dessus EMA20 avec body > 60% du range
4. Bar 1 body > bar 2 body (rejection plus forte que le pullback)
5. Filtre RSI : pas de buy au-dessus de 70, pas de sell en dessous de 30
6. RR minimum 2.5:1 sinon pas de trade

### Filtres de contexte (ce qui marche)
- **ATR band** (H1 ATR 14) : min et max configurables par paire
- **EMA50 distance** : rejette les entrees trop loin de l'EMA50
- **Jours bloques** : vendredi (toutes paires), lundi (GBPUSD, USDJPY)
- **Heures bloquees** : specifiques par paire
- **Combos heure x jour** : specifiques EURUSD
- **MinSL / MaxSL** : filtre les setups avec SL trop serre ou trop large

### Filtres d'entree testes et REJETES
- **Pullback size ratio** (taille bougies pullback vs trend) : tue les trades sur toutes les paires
- **Structure filter** (swing H/L intact) : trop agressif, elimine les bons trades
- **Conclusion** : l'entree EMA20 + body ratio + RSI est deja bien calibree, ne pas y toucher

### ⚠️ BUG FIX critique (filtre fantôme PB)
Le bool `UsePullbackSizeFilter` n'était pas câblé dans `IsPullbackHealthy()`. Le filtre
était silencieusement actif sur le preset EURUSD (r_PB_MaxRatio = 0.70 par défaut, jamais
override). Symptôme : **8-20 trades au lieu de 124** sur le backtest EURUSD.
Fix : `if(!UsePullbackSizeFilter) return true;` ajouté en début de fonction.
Concerne : `EMA_Pullback_EA.mq4` et `EMA_Pullback_pyramid.mq4`.

### Trade Management
- Lot size dynamique base sur % du capital
- SL sous/au-dessus du swing low/high + 2 pips buffer
- Breakeven a 1.5R (valide par analyse — 1R trop serr)
- Max 2 trades/jour
- Risk reduit le jeudi sur EURUSD (50%)

### Presets optimises (resultats spread reel)

| Paire | PF | DD | Profit/3ans | Trades | Trades/mois |
|-------|----|----|-------------|--------|-------------|
| **EURUSD** | **2.12** | **6.3%** | +7 075$ | 124 | 3.4 |
| **GBPUSD** | **1.67** | **6.1%** | +2 271$ | 62 | 1.7 |
| **USDJPY** | **1.43** | **8.4%** | +2 464$ | 89 | 2.5 |
| **Portfolio** | **~1.7** | **~10%** | **+11 810$** | **275** | **7.6** |

### Parametres par preset

**EURUSD :**
- SL : 15-25 pips | ATR : 9-19 pips | EMA50 dist : < 30 pips
- Block : Vendredi + 13h + combos toxiques (14h/Mar, 11h/Lun, 14h/Jeu, 16h/Lun)
- Thursday risk : 50%

**GBPUSD :**
- SL : 20-25 pips | ATR : 9-25 pips | EMA50 dist : < 50 pips
- Block : Vendredi + Lundi + 10h + 15h
- London : commence a 09h (08h toxique)

**USDJPY :**
- SL : 17-25 pips | ATR : OFF | EMA50 dist : < 75 pips
- Block : Vendredi + Lundi + 09h + 11h + 16h
- Note : pips JPY = *100 (pas *10000)

**XAUUSD (non backteste, estimations) :**
- SL : 50-120 pips | ATR : 20-80 pips | EMA50 dist : < 150 pips
- Block : Vendredi | NY etendu jusqu'a 18h

### Lecons apprises
- Les filtres de CONTEXTE (quand trader) marchent. Les filtres d'ENTREE (comment entrer) ne marchent pas.
- Chaque paire a besoin de ses propres parametres — ne jamais copier-coller
- Le MinSL est le filtre le plus impactant par paire (EURUSD=15, GBPUSD=20, USDJPY=17)
- Le backtest MT4 garde les params en cache — toujours faire "Remise a zero" apres recompilation
- Spread reel vs spread 2 fait une difference significative sur les resultats

---

## Exploration martingale/pyramid (leçons apprises)

### Parcours de découverte
1. **martingale_invert_EA** (reverse martingale) → **-42%** sur 3 ans
   - 2 bugs identifiés : délai 1 barre sur trigger REV + conversion ticks/pips 10× sur 5-digit
   - Concept "flip direction après SL" structurellement cassé sur EURUSD H1 (WR REV 8.3%)
   - Prouvé mathématiquement par simulation Python sur 839 INITs : aucune config de SL ne rend le reverse profitable

2. **martingale_classic_filtered** (same-direction martingale) → **-26%** sur 3 ans
   - Mg1 WR 37.9%, tue les gains INIT
   - Le pyramide classique sur un signal faible ne marche pas

3. **martingale_anti_filtered** (anti-martingale sans filtres régime)
   - 3 ans : +$22k / DD 31% / PF 1.17
   - **6 ans : +$14k / DD 47% / PF 1.09** → fragile, 2020-2022 saigne

4. **regime_pyramid_EA** (anti-mart + filtres ADX/BBW/EMA slope + H×J + ATR)
   - Config agressive (L0=0.05, L1=3.0, L2=4.0) : **+$43k / DD 39% / PF 1.25** sur 6 ans
   - Solution pour un signal faible : filtrer activement le régime de marché
   - Signal L0 perdant (PF 0.88) donc L0 réduit au minimum (juste "ticket d'entrée")

5. **EMA_Pullback_pyramid** (signal fort + pyramid) → **GAGNANT**
   - Mode SAFE : +$34k / DD 26% / PF 1.89 sur 6 ans
   - Mode AGGRESSIVE : +$109k / DD 47% / PF 1.91 sur 6 ans
   - L1 PF 2.79 (vs 1.53 sur regime_pyramid) → signal de qualité × pyramid = combo tueur

### Principes validés
- **Qualité du signal > sophistication du filtrage** : EMA Pullback (signal selectif) + pyramid simple > signal générique + 5 filtres
- **Le L1 (après 1 win) est TOUJOURS le profit engine** sur tous les systèmes testés
- **Le L2 (après 2 wins) est toujours le maillon faible** (WR chute, PF proche de 1)
- **Les simulations Python sur trades existants sont UNREALIABLES** pour le pyramid (l'ordre des trades change avec les filtres, ce qui casse le streak). Toujours valider en MT4 backtest.
- **Over-fit walk-forward** : toujours tester sur 2 périodes séparées (2020-2022 vs 2023-2026). Un filtre qui marche sur 1 période seule est probablement over-fit.
- **Le bug TP ×10 sur 5-digit** : `tickVal = $1` sur 5-digit (vs $10 sur 4-digit), toujours convertir via `MarketInfo(MODE_TICKSIZE)` pas `g_pt`

### Configs qui ne marchent pas (enseignements)
- Reverse martingale direction-opposee sur H1 : marché continue à 60% après SL, pas de mean-reversion exploitable
- 7 cellules H×J "walk-forward robustes" : catastrophique en live (la simulation Python ne modélisait pas l'effet pyramid sur les trades supplémentaires)
- Filtre ATR rolling : s'adapte au chaos et perd son efficacité. Préférer un seuil FIXE en pips.

---

## SMC Scalper EA (en dev)

### Architecture
- **M15** : Biais directionnel (BOS / swing H/L)
- **M5** : Entree (Order Blocks + FVG + Liquidity Sweep)

### Logique
1. Detection BOS sur M15 -> buys ou sells
2. Detection Order Blocks M5 non mitiges
3. Prix doit etre dans la zone d'un OB
4. Confluence : OB + FVG ou OB + Liquidity Sweep
5. RR minimum 2:1

### TP multi-niveaux
- OB oppose > FVG non comble > Swing liquidity
- TP1 a 1.5R : partial close 50% + SL to BE
- TP2 a MinRR+ : close reste sur prochaine liquidite

### Filtres
- Sessions Londres (8-12) + New York (13-17)
- Filtre news CSV + events recurrents (NFP, CPI, FOMC, ECB)
- Presets : EURUSD, XAUUSD, NAS100, US30

---

## Fichiers du projet

### Code EAs
- `EMA_Pullback_pyramid.mq4` — ⭐ **EA CHAMPION** : EMA Pullback + pyramide (SAFE/AGGRESSIVE/CUSTOM)
- `EMA_Pullback_EA.mq4` — baseline EMA Pullback (~830 lignes)
- `regime_pyramid_EA.mq4` — pyramid + filtres régime (signal générique, abandonné)
- `martingale_anti_filtered.mq4` — anti-mart sans filtres régime (exploration)
- `martingale_classic_filtered.mq4` — martingale classique (exploration)
- `martingale_invert_EA.mq4` / `_v2` / `_v3` — reverse martingale (exploration, buggé)
- `SMC_Scalper_EA.mq4` — EA SMC (~1200 lignes, en dev)
- `news_calendar.csv` — Calendrier news pour SMC EA

### Analyses Python EMA Pullback
- `analysis.py` — Analyse v1 EURUSD (723 trades)
- `analysis_v2.py` — Analyse v2 EURUSD (527 trades)
- `analysis_1an.py` — Diagnostic 2025-2026
- `analysis_gbpusd.py` — Analyse GBPUSD (732 trades)
- `analysis_usdjpy.py` — Analyse USDJPY (349 trades)
- `analyze_emapullback_pyramid.py` — Analyse pyramide 3 ans
- `analyze_emapullback_6ans.py` — Analyse pyramide 6 ans
- `analyze_pullback_final.py` — Analyse mode AGGRESSIVE 3 ans
- `analyze_pullback_6ans_final.py` — Analyse mode AGGRESSIVE 6 ans + DD episodes

### Analyses Python martingale/regime_pyramid
- `analysis_martingale*.py` — Analyses reverse martingale
- `analysis_6ans.py` — Walk-forward H×J calibration
- `analyze_regime_v1.py` / `analyze_regime_v2_3ans.py` — regime_pyramid analyses
- `analyze_antifiltered_3ans.py` — anti-mart sans filtres régime
- `simul_*.py` — Simulations (cooldown, ATR fixed, rev SL, etc.)

### Donnees marche (_cut = 5 dernieres annees)
- `EURUSD15_cut.csv`, `EURUSD60_cut.csv`
- `GBPUSD15_cut.csv`, `GBPUSD60_cut.csv`
- `USDJPY15_cut.csv`, `USDJPY60_cut.csv`

### Historiques de trades EMA Pullback (baseline)
- `historique trade 3ans.txt` — EURUSD v1 (709 trades)
- `historique trade 3ansV2.txt` — EURUSD v2 (527 trades)
- `historique trade 1an.txt` — EURUSD 2025-2026 (80 trades)
- `historique trade gbpusd 3ans.txt` — GBPUSD brut (732 trades)
- `historique trade gbpusd 3ansV4.txt` — GBPUSD optimise (78 trades)
- `historique trade usdjpy 3ans.txt` — USDJPY brut (349 trades)
- `historique trade usdjpy 3ansV2.txt` — USDJPY optimise (89 trades)

### Historiques de trades Pyramid (resultats_*.txt)
**EMA Pullback Pyramid :**
- `resultats_martingale_EMAPullback3ans.txt` — mode SAFE 3 ans
- `resultats_martingale_EMAPullback6ans.txt` — mode SAFE 6 ans (+$34k, DD 26%)
- `resultats_martingale_EMAPullback3ansFinal.txt` — mode AGGRESSIVE 3 ans (+$87k, DD 24%)
- `resultats_martingale_EMAPullback6ansFinal.txt` — mode AGGRESSIVE 6 ans (+$109k, DD 47%)

**Regime Pyramid (exploration) :**
- `resultats_regime_pyramid-3ans_v1.txt` — config modérée 3 ans
- `resultats_regime_pyramid_v1.txt` — config modérée 6 ans

**Martingale explorations :**
- `resultats_martingale.txt` à `resultats_martingale4.txt` — reverse martingale tests
- `resultats_anti-martingale*.txt` — anti-martingale explorations
- `resultats6ans_anti-martingale_*.txt` — 6 ans avec filtres divers
- `resultats_martingale_antifiltred*.txt` — anti-mart sans filtres régime

### Docs
- `guide.html` — Tuto complet debutant MT4
- `CLAUDE.md` — Ce fichier

## Langage et plateforme
- **MQL4** (MetaTrader 4)
- Compilation dans MetaEditor (F4 > F7)
- Backtest via Strategy Tester (Ctrl+R)
- **Broker** : IC Markets (Raw Spread, compte demo)

## Repo GitHub
- Remote : `https://github.com/fredco30/botTrading`
- Branche principale : `main`

## Conventions
- Code en anglais, commentaires en anglais
- Variables : camelCase, prefix `g_` pour globales, `r_` pour runtime (preset override)
- Structs/Enums : PascalCase
- Inputs : PascalCase groupes par section
- Chaque preset a ses propres valeurs runtime, initialisees dans `ApplyPreset()`

## Prochaines etapes

### Court terme — validation EMA_Pullback_pyramid
- **Demo live EURUSD** avec `PyramidMode = MODE_SAFE` pendant 4-8 semaines
- Risk reduit a 0.5% initial puis 1% si la courbe tient
- Monitoring quotidien : si DD demo depasse 12% -> stop et debug
- Comparer trades reels vs backtest sur la meme periode

### Moyen terme — extension pyramid
- Test `EMA_Pullback_pyramid` sur GBPUSD (preset deja existant)
- Test sur USDJPY (preset deja existant)
- Si les 3 paires fonctionnent -> portfolio pyramid multi-paires
- Evaluation mode AGGRESSIVE SEULEMENT apres 3-6 mois de SAFE en live

### Long terme
- Optimisation USDCHF / XAUUSD (quand broker disponible)
- Mode H4+M30 avec pyramide (moins de trades, plus selectif)
- Test `EMA_Pullback_pyramid` sur autres TF (M5 pour plus de trades, H4 pour swing)
- Compilation et test du SMC Scalper EA
- Dashboard visuel on-chart (OB zones, FVG, biais)
- Dashboard pyramide : afficher le streak actuel et le prochain lot multiplier
