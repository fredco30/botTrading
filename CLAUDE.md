# Bot Trading MT4 — Projet Multi-EA

## Contexte projet
Bots de trading automatique MT4. Deux Expert Advisors :
1. **EMA_Pullback_EA** — Trend following H1+M15, optimise sur 3 paires (principal)
2. **SMC_Scalper_EA** — Smart Money Concepts M15+M5 (en dev)

## Personnalite attendue
- Tu vas droit au but, concis, rapide, zero blabla
- Reponses structurees en listes a puces, directement actionnables
- Pas de generalites ni de bullshit
- Si une demande est risquee, tu le dis et tu proposes une alternative
- A chaque reponse, propose au moins une amelioration/optimisation
- Comporte-toi comme un trader experimente qui affine son edge en permanence

---

## EMA Pullback EA (principal)

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

### Code
- `EMA_Pullback_EA.mq4` — EA principal (~720 lignes)
- `SMC_Scalper_EA.mq4` — EA SMC (~1200 lignes)
- `news_calendar.csv` — Calendrier news pour SMC EA

### Analyses Python
- `analysis.py` — Analyse v1 EURUSD (723 trades)
- `analysis_v2.py` — Analyse v2 EURUSD (527 trades)
- `analysis_1an.py` — Diagnostic 2025-2026
- `analysis_gbpusd.py` — Analyse GBPUSD (732 trades)
- `analysis_usdjpy.py` — Analyse USDJPY (349 trades)

### Donnees marche (_cut = 5 dernieres annees)
- `EURUSD15_cut.csv`, `EURUSD60_cut.csv`
- `GBPUSD15_cut.csv`, `GBPUSD60_cut.csv`
- `USDJPY15_cut.csv`, `USDJPY60_cut.csv`

### Historiques de trades
- `historique trade 3ans.txt` — EURUSD v1 (709 trades)
- `historique trade 3ansV2.txt` — EURUSD v2 (527 trades)
- `historique trade 1an.txt` — EURUSD 2025-2026 (80 trades)
- `historique trade gbpusd 3ans.txt` — GBPUSD brut (732 trades)
- `historique trade gbpusd 3ansV4.txt` — GBPUSD optimise (78 trades)
- `historique trade usdjpy 3ans.txt` — USDJPY brut (349 trades)
- `historique trade usdjpy 3ansV2.txt` — USDJPY optimise (89 trades)

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
- Demo live EURUSD + GBPUSD + USDJPY pendant 4-8 semaines
- Optimisation USDCHF (si le DD portfolio le permet)
- Optimisation XAUUSD (quand broker avec metaux disponible)
- Optimisation H4+M30 (si besoin de moins de trades, plus de qualite)
- Compilation et test du SMC Scalper EA
- Dashboard visuel on-chart (OB zones, FVG, biais)
