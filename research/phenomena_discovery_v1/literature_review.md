# LITERATURE REVIEW — phenomena-discovery-v1

Méthode : sources académiques / institutions (BIS, Fed, ECB, banques centrales),
en évitant le contenu SEO / « holy grail ». Chaque entrée est codée selon le
format demandé. REPRODUCIBLE = l'effet est classiquement reproductible avec
des données publiques OHLC/taux (pas nécessairement rentable net de coûts).

---

SOURCES="Admati & Pfleiderer, 'A Theory of Intraday Patterns: Volume and Price Variability', Review of Financial Studies 1(1)"
YEAR=1988
PHENOMENON=U intraday de volume/volatilité ; regroupement endogène des flux de liquidité à l'ouverture
MECHANISM=Les traders de liquidité non discrétionnaires se concentrent à l'ouverture ; les traders discrétionnaires s'alignent sur ces fenêtres (auto-renforcement) → volatilité/volume élevés au open, prix plus prévisible en direction de flux à court horizon
MARKETS=Actions (transposable FX aux opens de sessions)
TIMEFRAME=Intraday (minutes/heures)
REPRODUCIBLE=YES (pattern documenté, pas un edge net)
URL=https://academic.oup.com/rfs/article-abstract/1/1/3/1601212
COMMENTS=Fondement du choix des fenêtres session-open dans le catalogue (famille B)

SOURCES="Osler, 'Support for Resistance: Technical Analysis and Intraday Exchange Rates', FRBNY Economic Policy Review 6(2)"
YEAR=2000
PHENOMENON=Niveaux support/résistance effectifs en FX intraday
MECHANISM=Clustering d'ordres clients (stops/TP) autour de niveaux techniques → exécution en cascade, interruption des tendances à ces niveaux
MARKETS=FX
TIMEFRAME=Intraday
REPRODUCIBLE=YES
URL=https://www.newyorkfed.org/research/epr/00v06n2/0007osle.html
COMMENTS=Directement lié à P000_TRANSFER (breakout/retest de range de session) et aux hypothèses de niveaux (famille I)

SOURCES="Osler, 'Currency Orders and Exchange-Rate Dynamics: Explaining the Success of Technical Analysis', FRBNY Staff Report 125"
YEAR=2001 (publié 2003 J. Finance)
PHENOMENON=Asymétrie stops (taux de change) : take-profits sur nombres ronds, stop-loss au-delà → accélération directionnelle après franchissement
MECHANISM=Les stops stop-loss déclenchent des ordres dans le sens du mouvement ; les TP limitent le mouvement dans l'autre sens → drift post-breakout
MARKETS=FX
TIMEFRAME=Intraday à quelques jours
REPRODUCIBLE=YES
URL=https://fraser.stlouisfed.org/files/docs/publications/frbnysr/frbny_sr125.pdf
COMMENTS=Mécanisme causal du « breakout continuation » ; justifie WHY du test breakout→drift

SOURCES="Andersen, Bollerslev, Diebold & Vega, 'Micro Effects of Macro Announcements: Real-Time Price Discovery in Foreign Exchange', American Economic Review 93(1)"
YEAR=2003
PHENOMENON=Réaction quasi-instantanée du FX aux surprises macro (CPI, NFP, paie)
MECHANISM=Price discovery : l'information macro est intégrée en secondes/minutes ; sur-réaction partielle et drift post-annonce selon le signe de la surprise
MARKETS=FX majeures
TIMEFRAME=Minutes à heures
REPRODUCIBLE=YES (direction de base sans consensus : événement + réponse de prix)
URL=https://www.aeaweb.org/articles?id=10.1257/000282803321455151
COMMENTS=Famille G ; attention révisions — utiliser EVENT_TIME + réponse, pas de chiffres révisés

SOURCES="Menkhoff, Sarno, Schmeling & Schrimpf, 'Currency Momentum Strategies', Journal of Financial Economics 106(3)"
YEAR=2012
PHENOMENON=Momentum cross-sectionnel des devises (1-12 mois)
MECHANISM=Under-réaction des acteurs (frictions, ordres central-bank/hedging), prime de risque associée aux stratégies momentum
MARKETS=FX (cross-section de paires)
TIMEFRAME=Mensuel
REPRODUCIBLE=YES
URL=https://www.sciencedirect.com/science/article/abs/pii/S0304405X12001578
COMMENTS=Hors périmètre intraday ; cité pour cadrage (les familles testées ici sont intraday, le momentum mensuel n'est pas retesté)

SOURCES="Lustig, Roussanov & Verdelhan, 'Common Risk Factors in Currency Markets', Review of Financial Studies 24(11)"
YEAR=2011
PHENOMENON=Carry : différentiel de taux → prime à l'ensemble long haut-rendement / court bas-rendement
MECHANISM=Prime de risque du facteur « dollar » et « carry » ; crash risk des stratégies carry
MARKETS=FX
TIMEFRAME=Mensuel
REPRODUCIBLE=YES
URL=https://academic.oup.com/rfs/article-abstract/24/11/3731/1588607
COMMENTS=Famille F ; nécessite séries de taux FRED/ECB — hypothèse enregistrée, non testée ce cycle (données de consensus/dates de publication à fiabiliser)

SOURCES="Lou, Polk & Skouras, 'A Tug of War: Overnight Versus Intraday Expected Returns', Journal of Financial Economics 134(1)"
YEAR=2019
PHENOMENON=La prime d'actions se concentre la nuit (overnight) vs intraday ; saisonnalité de séance
MECHANISM=Composition des détenteurs (retail vs institutionnels), contraintes d'exécution, marché fermé la nuit → espérances différentes overnight vs intraday
MARKETS=Actions US (pertinent pour P000)
TIMEFRAME=Overnight/intraday
REPRODUCIBLE=YES
URL=https://www.sciencedirect.com/science/article/abs/pii/S0304405X19301350
COMMENTS=Appuie la plausibilité d'effets liés à la frontière pre-market/regular session

SOURCES="Biais of Dukascopy feed — aucun papier ; documentation feed public"
YEAR=n/a
PHENOMENON=n/a
MECHANISM=n/a
MARKETS=n/a
TIMEFRAME=n/a
REPRODUCIBLE=NO
URL=https://github.com/dukascopy-node/dukascopy-node
COMMENTS=Référence technique du format bi5 utilisé pour les données 5 min (pas un phénomène)

SOURCES="BIS Triennial Central Bank Survey — FX turnover"
YEAR=2022
PHENOMENON=Structure du marché FX : dominance des dealers, part des algorithmes, pics de volume aux opens London/NY et aux fixings
MECHANISM=Concentration des flux aux fenêtres d'exécution benchmark (WM/R 4pm London) et aux sessions
MARKETS=FX
TIMEFRAME=Structurel
REPRODUCIBLE=NO (statistiques agrégées)
URL=https://www.bis.org/statistics/rpfx22_fx.htm
COMMENTS=Justifie familles B (session transitions) et H (fixing flows) ; couvre la microstructure institutionnelle

SOURCES="Andersen & Bollerslev, 'Intraday Periodicity and Persistent Volatility in Foreign Exchange Markets', Journal of International Money and Finance / 'DM-dollar volatility' work with Das"
YEAR=1997-2000
PHENOMENON=Seasonalité intraday forte et stable de la volatilité FX (pics London open, NY open, chevauchement)
MECHANISM=Arrivée d'information + concentration de flux aux opens ; volatilité prévisible (second-order opportunity : sizing/vol targeting)
MARKETS=FX
TIMEFRAME=Minutes (agrégé heures)
REPRODUCIBLE=YES
URL=https://www.sciencedirect.com/science/article/abs/pii/S0261560697000186
COMMENTS=Fondement des hypothèses SECOND_ORDER (famille L) et session transitions

SOURCES="Engle (1982) 'Autoregressive Conditional Heteroscedasticity'; Bollerslev (1986) 'Generalized ARCH'"
YEAR=1982/1986
PHENOMENON=Volatility clustering
MECHANISM=Persistance de la variance conditionnelle — la volatilité future est partiellement prévisible sans direction
MARKETS=Tous
TIMEFRAME=Quotidien/intraday
REPRODUCIBLE=YES
URL=https://www.jstor.org/stable/1912773
COMMENTS=Base des opportunités SECOND_ORDER (X → vol future), classées sans edge directionnel

SOURCES="George & Hwang, 'The 52-Week High and Momentum Investing', Journal of Finance 59(5)"
YEAR=2004
PHENOMENON=Ancrage au plus haut 52 semaines
MECHANISM=Biais d'ancrage des investisseurs autour de niveaux saillants → sous-réaction près du niveau
MARKETS=Actions
TIMEFRAME=Quotidien
REPRODUCIBLE=YES
URL=https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.2004.00695.x
COMMENTS=Analogie avec les niveaux PMH/PML saillants de P000 (niveaux saillants → comportement ordonné)

SOURCES="Mancini, Ranaldo & Wrampelmeyer, 'Liquidity in the Foreign Exchange Market: Measurement, Commonality, and Risk Premiums', Journal of Finance 68(5)"
YEAR=2013
PHENOMENON=Liquidité FX : mesure, facteur commun, prime
MECHANISM=Variation de liquidité systématique → réponses de prix différenciées par paire (lead-lag possible)
MARKETS=FX
TIMEFRAME=Quotidien/intraday
REPRODUCIBLE=PARTIEL (données tick EBS nécessaires pour la réplication exacte)
URL=https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.12053
COMMENTS=Cadre pour la famille D (lead-lag cross-pair)

SOURCES="Albuquerque? — remplacé par : 'The London 4pm Fix' — littérature réglementaire (FCA, 2014) et BIS sur le fixing WM/R"
YEAR=2014
PHENOMENON=Flux benchmark au fix 16:00 London
MECHANISM=Ordres inélastiques exécutés au fix → pression de prix pré-exécution et retour post-fix documenté lors des enquêtes
MARKETS=FX
TIMEFRAME=Minutes autour du fix
REPRODUCIBLE=PARTIEL (sans volumes institutionnels, seule la saisonnalité horaire est testable)
URL=https://www.fca.org.uk/publications/final-notices/final-notices-issued-2014
COMMENTS=Famille H ; hypothèse enregistrée, test limité à la saisonnalité de retour autour de 16:00 London sur données 5 min

SOURCES="Barber & Odean, 'Trading Is Hazardous to Your Wealth', Journal of Finance 55(2)"
YEAR=2000
PHENOMENON=Overtrading et pertes des investisseurs particuliers
MECHANISM=Biais comportementaux ; asymétrie d'information/exécution → espérance brute négative des traders actifs (anti-edge structurel côté retail)
MARKETS=Actions (étendu FX retail par la suite)
TIMEFRAME=Variable
REPRODUCIBLE=PARTIEL
URL=https://onlinelibrary.wiley.com/doi/abs/10.1111/0022-1082.00226
COMMENTS=Justifie la famille A (anti-edge) : chercher des signaux « wrong-way » où le comportement moyen est systématiquement perdant AVANT coûts

SOURCES="Foster & Viswanathan, 'A Theory of the Interday Variations in Trading Volume', Journal of Finance 48(3)"
YEAR=1993
PHENOMENON=Variation inter-journalière de volume/volatilité, information asymétrique en début de semaine/journée
MECHANISM=Séquence d'arrivée d'information et adverse selection en open → patterns prévisibles de volatilité, pas de direction
MARKETS=Actions
TIMEFRAME=Intraday
REPRODUCIBLE=YES
URL=https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.1993.tb04717.x
COMMENTS=Complète Admati-Pfleiderer pour la saisonnalité d'open

SOURCES="Committee documentation ECB/Euro FX reference rates"
YEAR=n/a
PHENOMENON=n/a
MECHANISM=n/a
MARKETS=FX
TIMEFRAME=Quotidien 16:00 CET
REPRODUCIBLE=YES
URL=https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html
COMMENTS=Source de données officielle pour différentiels de taux (famille F) — enregistrée pour un cycle ultérieur

---

## SYNTHÈSE ORIENTÉE CATALOGUE

1. Les effets les mieux établis et CAUSALEMENT documentés sont des effets de
   VOLUME/VOLATILITÉ localisés dans le temps (opens, fixing) — pas des edges
   directionnels nets. Conséquence : prioriser les événements de flux
   (stops, fixings, opens) où le mécanisme d'exécution forcée crée une
   direction, et classer le reste en SECOND_ORDER.
2. P000 (breakout pre-market + retest) est cohérent avec la microstructure :
   accumulation overnight → cassure avec stops → retest = test d'absorption.
   Le mécanisme est plausible sur actions US ; la transposition FX (range
   asiatique → London) est économiquement comparable (famille B).
3. Les mécanismes de stops (Osler) prédisent une asymétrie : continuation
   après cassure confirmée, mais échecs plus fréquents au 2e test d'un même
   niveau — hypothèse FALSIFIED_BREAKOUT du catalogue.
