# P000 — VIDEO STRATEGY SPEC (`video_strategy_spec.md`)

Source primaire : https://youtu.be/tLEcVa1FxzM
Méthode : transcript officiel YouTube (sous-titres `en-orig`, 18:14) + description
officielle, archivés dans `video_source/` (`transcript_plain.txt`, `video.description`,
`video.info.json`). La vidéo/source originale fait foi sur la liste de départ connue.

VIDEO_TITLE=This ONLY One-Trade-Per-Day Strategy Works Everyday For Me (Simple & Profitable)
VIDEO_CHANNEL=PBInvesting (New Age Trading) — upload 2026-07-26, durée 18:14
VIDEO_MARKET=Actions US (illustré sur des graphiques d'actions avec zone pre/post-market TradingView ; mention d'options « calls/puts » pour les exemples). L'auteur promeut aussi du futures (sponsor Tradovate) mais AUCUN exemple de la stratégie n'est montré sur futures.
VIDEO_INSTRUMENT=Actions/ETF US liquides (type SPY / mega-caps). Aucun ticker nommé verbalement ; les graphiques montrent des actions US à 3 chiffres (dollars, centimes).
VIDEO_TIMEZONE=America/New_York (ET) — les heures de séance US et le shading pre/post-market TradingView sont en ET.
VIDEO_SESSION=Pre-market 04:00–09:30 ET (zone rouge), séance régulière 09:30–16:00 ET. « I waited, I traded the exact setup … every single morning … only trading the first hour » — la fenêtre d'exécution visée est l'ouverture US (première heure).
VIDEO_TIMEFRAME=5 minutes (« the stock closes above the pre-market high here on the 5-minute time frame » ; résumé final : « you wait for it to get a 5-minute close either over or under, then you trade the retest »). Le graphique 1-minute n'est utilisé QUE pour la pédagogie (« I don't trade in the 1-minute, guys. This is to show you like candle by candle when I would enter »).
VIDEO_ENTRY=Retest de niveau. Séquence : (1) marquer le plus haut et le plus bas du pre-market (PMH/PML) ; (2) biais = long UNIQUEMENT si prix au-dessus de PMH, short UNIQUEMENT si prix en dessous de PML, AUCUN trade entre les deux (« chop day ») ; (3) confirmation = clôture 5 min AU-DESSUS de PMH (ou en dessous de PML) ; (4) attendre le RETEST : « the retest is when the stock comes back and taps that level » ; (5) « I'm not entering exactly when it taps … I'm entering once it taps and then starts to go up a little bit. I want to see a little bit of momentum to come in » → entrée dans le sens de la cassure après le tap quand le prix repart.
VIDEO_CONFIRMATION=Clôture 5 minutes à l'extérieur de la zone pre-market (au-dessus de PMH pour les longs, en dessous de PML pour les shorts).
VIDEO_RETEST=Retour du prix au niveau cassé (PMH/PML) après la confirmation ; l'entrée ne se fait PAS au toucher, mais après que le prix « repart un peu » dans le sens du trade.
VIDEO_STOP=« I personally like to put my stop loss if it closes under it » → invalidation quand une clôture 5 min retombe SOUS le niveau retesté (pour un long ; symétrique pour un short). Interprétation littérale : STOP BASÉ SUR CLÔTURE au niveau retesté (pas sur mèche).
VIDEO_PARTIALS=« I like to trim at new high of day then as it goes up » → prises partielles (« trims ») au NEW HIGH OF DAY (plus haut du jour), puis au fil de la montée ; après le premier trim, « I'm moving my stop loss to in the profits » (stop passé en profit).
VIDEO_TRAILING=EMA 8 (5 min) pour le reliquat (« runner ») : « As long as the stock doesn't get under the 8 EMA, you could stay in the trade » → sortie du reliquat quand le prix repasse sous l'EMA 8. Précision temporelle : l'EMA 8 ne sert qu'APRÈS le premier trim (« you only do that after the first trim »).
VIDEO_EXIT=Stop sur clôture sous le niveau (avant trim) ; après le premier trim : stop en profit + sortie du reliquat sous EMA 8 ; trims successifs aux nouveaux extrêmes du jour.
VIDEO_VWAP_ROLE=VWAP ajouté en overlay (bandes désactivées). Variantes explicites montrées : si le prix part « way above » PMH (ou « way below » PML) SANS retest du niveau, ET que VWAP est au-dessus de PMH (en dessous de PML), on trade alors le RETEST DE VWAP (tap VWAP puis départ dans le sens du trade). « When it's lined up with this pre-market low or pre-market high, that is a really, really, really good setup. » Quatre setups au total : PMH retest (long), PML retest (short), VWAP retest long (VWAP > PMH), VWAP retest short (VWAP < PML).
VIDEO_EMA8_ROLE=Trailing stop du reliquat uniquement, après le premier trim ; aucune fonction d'entrée ou de filtre.
AMBIGUITIES=voir ci-dessous.

## Règles ambiguës (AMBIGUOUS_RULE=…, interdiction d'inventer en silence)

AMBIGUOUS_RULE=PM_WINDOW — borne exacte de la zone pre-market.
La vidéo montre le shading pre/post-market TradingView mais ne prononce pas
les heures. Interprétation retenue : 04:00–09:30 ET (défaut TradingView pour
les actions US ; le plus littéral et standard). Testée comme hypothèse
localement sensible si besoin documenté (pas d'optimisation).

AMBIGUOUS_RULE=RETEST_TRIGGER — déclencheur exact de l'entrée après le tap.
« Taps then starts to go up a little bit / a little bit of momentum » n'est pas
mécaniquement défini (il montre l'entrée bougie par bougie en 1 min mais ne
donne pas de règle chiffrée). Interprétation la plus littérale et la plus
simple : après la confirmation, au PREMIER retour au niveau (mèche 5 min qui
touche le niveau), pose d'un stop-entry au bout extrême de la bougie de tap
(haut de la bougie de tap pour un long, bas pour un short) ; l'entrée a lieu
si le prix repart et franchit ce niveau. Si le prix retombe clôturer sous le
niveau avant d'avoir relancé, le setup du jour est invalidé.

AMBIGUOUS_RULE=STOP_WICK_VS_CLOSE — « put my stop loss if it closes under it ».
Littéral : invalidation sur CLÔTURE 5 min sous le niveau (pas sur mèche).
C'est l'interprétation retenue. Une mèche sous le niveau ne sort pas seule.

AMBIGUOUS_RULE=TRIM_SIZE — la taille des trims n'est jamais chiffrée
(« taking trims », « sold most of our position » au new high of day).
Interprétation simple : 50 % au premier new high of day (NHD), stop passé à
breakeven ; le reliquat suit EMA 8. (La vidéo suggère « most » au premier
NHD ; 50 % est le choix le plus conservateur qui reste fidèle au mécanisme.)

AMBIGUOUS_RULE=VWAP_ANCHOR — ancrage du VWAP non précisé. TradingView
(défaut, bande unique) ancre au début de la séance régulière : 09:30 ET.
Retenu : VWAP ancré 09:30 ET, reconstruit en volume-pondéré si volumes
disponibles, sinon TWAP documenté (données CFD sans volume fiable).

AMBIGUOUS_RULE=ONE_TRADE_PER_DAY — « one trade per day » est un principe
disciplinaire (anti-overtrading) ; mécaniquement : maximum 1 position à la
fois, et maximum 1 entrée par jour par marché (retest de niveau OU VWAP,
pas les deux). Un seul sens par jour (celui du biais de cassure).

AMBIGUOUS_RULE=ENTRY_TIME_WINDOW — « first hour every morning » suggère une
fenêtre d'exécution matinale mais aucun cutoff exact n'est donné. Interprétation
littérale minimale : la séquence confirmation→retest doit commencer en séance
régulière le jour même ; pas de cutoff horaire artificiel dans P000_VIDEO_CORE_V1
(la vidéo montre des entrées le matin mais ne limite pas explicitement).
Sensibilité documentée a posteriori, sans optimisation.

## ORIGINAL_MARKET

ORIGINAL_MARKET=Actions US (séance régulière + pre-market 04:00–09:30 ET).
P000_ORIGINAL est donc testé sur son marché naturel — pas sur le Forex.
Données publiques sans clé profondes pour actions US individuelles incluant le
pre-market : INDISPONIBLES (yfinance : 60 jours seulement ; les autres sources
fiables exigent un compte). Substitution documentée : index CFD S&P 500
(Dukascopy USA500IDXUSD, cotation ~24h incluant 04:00–09:30 ET) = proxy
économique direct du marché actions US large (SPY/QQQ-class). Limitations
inscrites dans data_manifest.md. Toute transposition FX est séparée sous
P000_TRANSFER (Asia range → London breakout/retest).

## Classifications

P000A=P000_VIDEO_CORE_V1 — règles exactes vidéo (level retest, long+short).
P000B=P000_VWAP_V1 — variante VWAP retest (réellement présente dans la vidéo).
P000C=P000_TRANSFER — transposition session FX (Asia range → London), testée
séparément, jamais mélangée aux résultats P000_ORIGINAL.

EXTERNALLY_PREREGISTERED : oui, dans la mesure où toutes les règles ci-dessus
sont fixées par la vidéo indépendamment des données ; Discovery sert à
caractériser le phénomène, pas à choisir des paramètres.
