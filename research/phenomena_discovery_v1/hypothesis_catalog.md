# HYPOTHESIS CATALOG — phenomena-discovery-v1

P000 est réservé à la vidéo (voir video_strategy_spec.md). Ce catalogue
enregistre les hypothèses P001+ du premier cycle (maximum 40).
Chaque hypothèse commence par WHY_SHOULD_THIS_EDGE_EXIST? — phénomène,
mécanisme, acteurs, persistance, information observable, horizon, disparition,
coûts.

Classes :
A = mécanisme très plausible (flux forcés / microstructure documentée)
B = plausible (empirique solide, mécanisme indirect)
C = empirique/spéculatif (pattern observé, mécanisme faible)

---

## P001 — ASIA_RANGE_BREAKOUT_FIRST (famille B) — CLASSE A
WHY: Le range asiatique [23:00,07:00 UTC] accumule des stops des positions overnight et des ordres optionnels ; l'ouverture London (flux européens + hedging corporate) pousse hors du range. Les stops des vendeurs au-dessus du high (acheteurs forcés) et des acheteurs sous le low accélèrent la cassure (Osler 2001). Persistance : les ordres restent des contraintes réelles ; disparition si les acteurs anticipent la cassure (front-running) ou si la liquidité électronique absorbe les stops. Information observable : close 5m hors range. Horizon : heures. Coûts : spread FX NORMAL 2 pips — le signal doit faire > 2 pips d'espérance.
NOTE=Économiquement comparable à P000 (pre-market → RTH). C'est le cœur de P000_TRANSFER côté « signal premier breakout » (sans retest).

## P002 — ASIA_RANGE_RETEST_CONTINUATION (famille B) — CLASSE A
WHY: Après la première cassure du range asiatique, le retest du niveau = absorption : les vendeurs du breakout vendent, les ordres résiduels du range se déclenchent ; si le niveau tient, le drift reprend (retest réussi = confirmation de flux). Mécanisme identique à P000 adapté FX.
NOTE=C'est P000_TRANSFER (retest). Séparé de P001 pour ne jamais mélanger signal simple et signal avec retest.

## P003 — FALSE_BREAKOUT_ASIA (famille B/I) — CLASSE A
WHY: La première cassure du range asiatique échoue souvent : les stops capturés, le flux s'arrête ; le retour dans le range = signal mean-reversion (les breakout traders sont piégés et doivent couvrir). Acteurs : breakout traders + stops. Persistance : repose sur la psychologie de cassure naïve — plus fragile si arbitrée. Horizon : 1-3 h.
NOTE=Anti-corollaire de P001 ; testable sur les mêmes événements (retour dans le range sous X minutes).

## P004 — PREVIOUS_DAY_HL_FX (famille I) — CLASSE B
WHY: PDH/PDL (previous day high/low) sont des niveaux saillants où se concentrent stops et options ; réaction mesurable (rejet ou cassure). Mécanisme saillance/ancrage + clustering d'ordres. Horizon : heures.
NOTE=Test : retour directionnel après échec de franchissement en séance Europe/US.

## P005 — LONDON_OPEN_FIRST_HOUR_DIRECTION (famille B) — CLASSE B
WHY: La première heure London concentre le volume (BIS) ; le sens du premier déplacement post-open se prolonge statistiquement plus qu'il ne s'inverse (momentum intraday de session) quand il sort du range asiatique. Horizon : 1-4 h.
NOTE=Variante sans niveau précis : direction du premier 30-min post 07:00 UTC.

## P006 — NY_OPEN_OVERLAP_CONTINUATION (famille B) — CLASSE B
WHY: Le chevauchement London/NY (13:00-16:00 UTC max de volume FX) prolonge le move européen si le flux directionnel se poursuit (hedging multi-marchés). Horizon : heures.
NOTE=Sous-hypothèse : continuation du sens du jour (open NY vs open EU).

## P007 — ROUND_NUMBERS_FX (famille I) — CLASSE A
WHY: Concentration d'ordres aux nombres ronds (Osler 2001/2003) : réaction de rejet mesurable à ±50 pips (approche) et accélération au franchissement. Acteurs : stops, ordres entry à niveaux ronds. Horizon : minutes-heures. Disparition : partielle (documentée jusqu'en 2019+).
NOTE=Test : espérance conditionnelle autour des multiples de 0.0100/0.0050.

## P008 — VOL_SHOCK_CONTINUATION (famille C) — CLASSE C
WHY: Choc normalisé (ret/ATR > 3) → sous-réaction partielle puis continuation OU reversal selon le régime. Mécanisme ambivalent : hédonique de flux vs rebond de liquidité. C = mécanisme non tranché a priori.
NOTE=Test des deux sens ; classification SECOND_ORDER si seule la vol future bouge.

## P009 — VOL_SHOCK_SECOND_ORDER (famille L) — CLASSE A
WHY: Après un choc, la volatilité future augmente de façon quasi certaine (clustering, Engle 1982) — utile pour le sizing/vol targeting même sans direction. SECOND_ORDER_OPPORTUNITY.
NOTE=Test : variance forward conditionnelle vs inconditionnelle à horizon 1-24 h.

## P010 — LEAD_LAG_EURGBP_GBPUSD (famille D) — CLASSE B
WHY: EURUSD intègre l'information euro-zone, GBPUSD l'info UK ; EURGBP (cross) et l'ordre des opens (London avant NY) créent des retards d'intégration mesurables. Mécanisme : différences de flux par devise. Horizon : minutes.
NOTE=Test Granger-style simple : corr(ret GBPUSD_t, ret EURUSD_{t-k}) sur Discovery 5 min. Risque : microstructure commune → co-intégration mécanique.

## P011 — WEEKEND_GAP_FX (famille B/I) — CLASSE B
WHY: Le gap du dimanche 21:00/22:00 UTC corrige l'information du week-end ; les brokers élargissent le spread → le premier mouvement après gap est souvent un retour partiel (liquidité restaurée). Horizon : 1-6 h. CLASSE B.
NOTE=Test : retour directionnel opposé au gap à 1-6 h.

## P012 — FRIDAY_AFTERNOON_DRAIN (famille B) — CLASSE C
WHY: Vendredi après-midi UTC, la liquidité se retire avant le week-end ; les moves s'amortissent, le range se contracte. Pas d'edge directionnel clair → C. Testable comme Second-order (vol basse vendredi PM).

## P013 — MONTH_END_REBALANCING_FX (famille H) — CLASSE B
WHY: Rééquilibrages de portefeuilles en fin de mois : flux prévisibles en direction du différentiel de performance actions/obligations et des devises ; pression vers le fix de fin de mois. Acteurs : asset managers forcés. Horizon : dernier jour ouvré ±1. Nécessite : calendrier fin de mois + flux estimés (pas de consensus individuel requis si on teste la moyenne inconditionnelle). CLASSE B (retour moyen documenté dans la littérature asset-flows).
NOTE=Version simple testable : drift du dernier jour ouvré du mois à 16:00 London fix — retour moyen vs jours normaux.

## P014 — ASIA_FADE_LONDON (famille B) — CLASSE B
WHY: Le trend asiatique s'inverse souvent à London open (les acteurs asiatiques dénouent, London repréte le prix). Test : si le range asiatique est directionnel (close hors du milieu), fade à l'open London. CLASSE B.

## P015 — FIRST_BAR_OF_SESSION_REVERSAL_US (famille B) — CLASSE B
WHY: Sur l'index US, la première barre 5-min après l'open (09:30) sur-réagit (flux retail/ordre marché accumulés overnight) ; retour partiel vers VWAP dans les 30-60 min. Littérature overnight/intraday (Lou et al. 2019). Horizon : 30-60 min. CLASSE B.

## P016 — VWAP_MEAN_REVERSION_RTH_US (famille B) — CLASSE B
WHY: Le VWAP de séance est la référence d'exécution institutionnelle : les écarts extrêmes attirent des flux d'exécution (ordres conditionnels) qui ramènent le prix. Acteurs : desks d'exécution. Horizon : 30-120 min. CLASSE B.
NOTE=Test : |z = (prix − VWAP)/ATR| élevé → retour vers VWAP.

## P017 — PM_RANGE_SIZE_CONDITIONAL_BREAKOUT (famille I, dérivée) — CLASSE C
WHY: Un range pre-market étroit → cassure plus follow-through (compression) ; large → faux breakout. Testé UNIQUEMENT comme conditionnement de P000 (jamais seul) si P000 montre un edge brut. CLASSE C.

## P018 — OPENING_GAP_FILL_US (famille I) — CLASSE B
WHY: Gaps d'open US (open 09:30 vs close 16:00 veille) partiellement comblés en séance. Mécanisme : retour des market makers / rééquilibrage. Horizon : jour. CLASSE B (pattern classique).

## P019 — LUNCH_HOUR_DRIFT_US (famille B) — CLASSE C
WHY: Le creux de volume 12:00-13:30 ET ralentit le prix ; breakout du range de lunch → continuation faible. CLASSE C.

## P020 — FIX_16_LONDON_PRE_DRIFT (famille H) — CLASSE B
WHY: Autour du fix WM/R 16:00 London, les flux benchmark créent une pression mesurable pré-fix sur les grandes paires. Sans données de flux, seule la saisonnalité moyenne est testable (faible signal attendu). CLASSE B.

## P021 — SERIAL_DEPENDENCE_FX_5M (famille K) — CLASSE B
WHY: Autocorrélation conditionnelle des rendements 5-min FX (runs) : après N bougies consécutives même sens, la probabilité de continuation vs reversal est mesurable et stable. Mécanisme : fragmentations de gros ordres (slice execution) → runs mécaniques. Horizon : minutes. CLASSE B.

## P022 — US_SESSION_RANGE_EXTENSION_AFTER_PM_BREAK (famille I, dérivée) — CLASSE C
WHY: Si la cassure PMH/PML survient < 30 min après l'open, la journée est souvent tendance (liquidity flush). Dérivée de P000, conditionnement uniquement. CLASSE C.

## P023 — TUESDAY_MOMENTUM_FX (famille B/K) — CLASSE C
WHY: Saisonnalité jour-de-semaine du momentum (lundi range → mardi direction). CLASSE C — faible mécanisme, testé une fois, seuil de rejet strict.

## P024 — ASIA_HIGH_LOW_AS_MAGNET (famille I) — CLASSE B
WHY: Les extrêmes du range asiatique restent des aimants pendant la séance Europe (ordre resting non déclenchés) : probabilité de visite du niveau opposé avant tendance. CLASSE B.

## P025 — CARRY_MOMENTUM_MONTHLY_FX (famille F) — CLASSE A (mécanisme) / NON TESTÉ CE CYCLE
WHY: Prime de risque carry + momentum documentée (Lustig et al. 2011 ; Menkhoff et al. 2012). Nécessite séries de taux mensuelles avec dates de publication correctes (FRED). ENREGISTRÉ, NON TESTÉ (données à fiabiliser dans une mission dédiée — risque de revised-data leakage).

## P026 — US2Y_SHOCK_USDJPY_DAILY (famille E) — CLASSE A (mécanisme) / NON TESTÉ CE CYCLE
WHY: Le différentiel de taux court US-JP pilote USDJPY (carry + repatriation) : un choc de taux US 2Y se transmet en jours. Nécessite DGS2 (FRED) + alignement des dates. ENREGISTRÉ, NON TESTÉ (alignement de publication à fiabiliser).

## P027 — GOLD_RISK_OFF_XAUUSD (famille E) — CLASSE B / NON TESTÉ CE CYCLE
WHY: XAUUSD 5-min est dans le dépôt (XAUUSD15.csv) — corrélation risk-off avec JPY/CHF. Test lead-lag possible sur M15. ENREGISTRÉ (données présentes), priorité inférieure ce cycle.

## P028 — WRONG_WAY_MA_CROSS_M15 (famille A, anti-edge) — CLASSE B
WHY: Les signaux naïfs suivis par le retail (croisements EMA court/long en M15 FX) perdent en moyenne NET de coûts ; l'espérance BRUTE est souvent déjà négative à courte horizon (retour à la moyenne après signal). Si ORIGINAL_GROSS_EXPECTANCY < 0 stable → candidat INVERSION (anti-edge, protocole dédié). CLASSE B.

## P029 — WRONG_WAY_BREAKOUT_M15 (famille A, anti-edge) — CLASSE B
WHY: Breakouts Donchian M15 sur FX majeures échouent plus souvent qu'ils réussissent à court horizon (les stops alimentent le mouvement puis s'épuisent) ; espérance brute directionnelle à horizon fixe potentiellement négative → anti-edge candidat. Protocole : inversion uniquement sur Discovery, jamais après V1.

## P030 — OVERNIGHT_TREND_CONTINUATION_US_INDEX (famille B) — CLASSE B
WHY: Le move pre-market (23:00/04:00 → 09:30) se prolonge-t-il en séance ? Mécanisme flux institutionnels EU→US + information overnight. CLASSE B. Test : sign(open vs PM range milieu) → drift RTH.

## P031 — LUNCH_BREAK_LONDON_11_UTC (famille B) — CLASSE C
WHY: Creux de liquidité vers 11:00-11:30 UTC (pause London) ; micro-retour à la moyenne du range de matinée. CLASSE C.

## P032 — POST_FOMC_DRIFT (famille G) — CLASSE A (mécanisme) / DATA_BLOCKED
WHY: Le drift post-FOMC est documenté (sous-réaction à l'info de taux). Nécessite historique des dates/heures FOMC + heure de communiqué (14:00/19:00 ET selon période) — calendar public disponible mais l'alignement précis des timestamps Dukascopy ET l'historique des heures exigent une mission dédiée. DATA_BLOCKED ce cycle (documenté ci-dessous).

## P033 — SPIKE_REVERSAL_NEWS_5M (famille C/G) — CLASSE C
WHY: Spikes de volatilité extrêmes 5-min (news) reviennent partiellement dans les 30 min après le pic. Sans calendrier de news, test inconditionnel sur extrêmes normalisés. CLASSE C (risque de confondre news positives/négatives).

## P034 — RANGE_CONTRACTION_EXPANSION_H1 (famille L) — CLASSE B
WHY: Compression du range H1 (NR7-like) → expansion suivante ; direction non prédite (SECOND_ORDER pour breakout sizing). CLASSE B.

## P035 — DAY_OF_WEEK_VOL_PATTERN_FX (famille L, second-order) — CLASSE B
WHY: Profil de volatilité par jour de semaine stable (lundi bas, mercredi haut — usage sizing). SECOND_ORDER. CLASSE B.

## P036 — FIRST_MOVE_FALSE_BREAK_ALIAS (famille B, dérivée P000) — CLASSE B
WHY: Si P000A échoue à l'entrée (invalidation avant entry), le jour suivant le sens opposé est-il meilleur ? Dérivée : nécessite les événements P000. Conditionnée à l'analyse P000 (pas de test indépendant ce cycle si P000 négatif).

## P037 — EURJPY_CROSS_LEAD (famille D) — CLASSE C
WHY: EURJPY/GBPJPY (paires à carry) intègrent le risk-on/off avant USDJPY. Données 5-min Dukascopy disponibles mais hors périmètre téléchargé ce cycle → enregistré, NON TESTÉ (à activer si famille D prometteuse sur EURUSD/GBPUSD/USDJPY).

## P038 — OPEN_DRIVE_US_INDEX_VS_VWAP (famille B, dérivée P000B) — CLASSE B
WHY: L'open-drive au-dessus du PMH avec VWAP aligné (le setup VWAP de la vidéo) : le retest de VWAP = meilleure entrée que le retest de niveau ? Testé via P000B directement.

## P039 — HALT_LIKE_CLUSTERS_US_INDEX (famille C) — CLASSE C
WHY: Séquences de volatilité extrême sur l'index CFD (quasi-halts) → reprise directionnelle après stabilisation. CLASSE C, événements rares, absence d'edge attendu — enregistré pour complétude.

## P040 — SESSION_CLOSE_REVERSAL_US_1550 (famille B) — CLASSE B
WHY: Les 10 dernières minutes de séance US (15:50-16:00) voient des flux MOC déséquilibrés ; retour d'une partie du move de fin de journée à l'open suivant (overnight). Horizon : overnight — dépasse le cadre intraday du cycle, enregistré pour un cycle futures avec données overnight.

---

## RÉSUMÉ

HYPOTHESES_REGISTERED=40 (P000 vidéo + P001..P039 numérotées + P040 = 41 fiches, dont P000 hors cycle « autres »)
CLASSE_A=13
CLASSE_B=17
CLASSE_C=11
TESTABLE_CE_CYCLE_AVEC_DONNEES_PRESENTES=P001,P002,P003,P004,P005,P007,P008,P009,P011,P014,P016,P018,P021,P024,P028,P029,P034,P035 (et P000)
DATA_BLOCKED=P032 (FOMC timestamps), P025/P026 (dates de publication), P037 (crosses non téléchargés)
