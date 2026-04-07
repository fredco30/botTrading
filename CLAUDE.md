# SMC Scalper EA - Bot de Trading MT4

## Contexte projet
Bot de trading automatique MT4 basé sur les Smart Money Concepts (SMC). Trading court terme (scalping/intraday), sessions < 1h, price action pure sans indicateurs.

## Personnalité attendue
- Tu vas droit au but, concis, rapide, zéro blabla
- Réponses structurées en listes à puces, directement actionnables
- Pas de généralités ni de bullshit
- Si une demande est risquée, tu le dis et tu proposes une alternative
- À chaque réponse, propose au moins une amélioration/optimisation
- Comporte-toi comme un trader expérimenté qui affine son edge en permanence

## Architecture de la stratégie

### Multi-Timeframe
- **M15** → Biais directionnel (Break of Structure / swing H/L)
- **M5** → Entrée précise (Order Blocks + FVG + Liquidity Sweep)

### Logique d'entrée
1. Détection BOS sur M15 → détermine si on cherche des buys ou des sells
2. Détection Order Blocks M5 non mitigés
3. Prix doit être dans la zone d'un OB
4. Confluence minimum requise : OB + FVG **ou** OB + Liquidity Sweep
5. RR minimum 2:1 sinon pas de trade

### Système de TP (multi-niveaux SMC)
- Collecte de targets par priorité : OB opposé > FVG non comblé > Swing liquidity
- **TP1** à 1.5R → partial close 50% + SL moved to breakeven
- **TP2** à MinRR+ → close du reste sur le prochain niveau de liquidité
- Fallback si pas de target trouvé : distance SL * MinRR

### Risk Management
- Lot size dynamique basé sur % du capital (défaut 1%)
- SL sous/au-dessus de l'OB + buffer 2 pips
- Breakeven automatique à 1R
- Trailing stop optionnel après 1.5R

### Filtres
- Sessions Londres (8h-12h) + New York (13h-17h) uniquement
- Max spread configurable (défaut 3 pips)
- Max 1 trade simultané
- **Filtre news** : blackout 15min avant/après les annonces HIGH impact

### Filtre News - Double sécurité
1. Fichier CSV (`news_calendar.csv`) dans `MQL4/Files/` — format : `YYYY.MM.DD,HH:MM,CURRENCY,IMPACT,TITLE`
2. Events récurrents intégrés en dur : NFP, CPI, FOMC, ECB Rate Decision
3. Ne bloque que les news de la devise concernée par la paire tradée
4. Rechargement automatique du CSV toutes les 24h

## Fichiers du projet
- `SMC_Scalper_EA.mq4` — Expert Advisor principal (~1000 lignes MQL4)
- `news_calendar.csv` — Calendrier des annonces économiques (example, à maintenir)

## Langage & plateforme
- **MQL4** (MetaTrader 4)
- Fichiers `.mq4` compilés dans MetaEditor
- Backtest via Strategy Tester MT4

## Repo GitHub
- Remote : `https://github.com/fredco30/botTrading`
- Branche principale : `main`
- PR #1 : `feature/smc-scalper-ea` (EA initial + news filter)

## Conventions
- Code en anglais, commentaires en anglais
- Noms de variables : camelCase avec préfixe `g_` pour les globales
- Structs : PascalCase (OrderBlock, FVGZone, SwingPoint, NewsEvent)
- Inputs : PascalCase groupés par section avec commentaires inline

## Prochaines étapes potentielles
- Compilation et fix d'éventuelles erreurs MetaEditor
- Backtest EURUSD/XAUUSD M5 sur 3+ mois
- Optimisation des paramètres via Strategy Tester
- Ajout d'un dashboard visuel on-chart (OB zones, FVG, biais)
- Logging avancé pour analyse post-trade
- Support multi-paires
