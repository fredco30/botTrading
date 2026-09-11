# DATA MANIFEST — phenomena-discovery-v1

Politique : datasets bruts HORS GIT (`data_raw/` gitignored) ; les parquets
dérivés vivent aussi hors git. Reproductibilité : chaque source est re-
téléchargeable sans clé via les scripts `dukascopy_download.py` /
`build_5m.py` de ce répertoire. **Fenêtre protégée 2026-04-09 → 2026-07-24
incluse : filtrée AVANT toute inspection/analyse** (`p000_lib.load_5m` et
`h1h4_lib.filter_window` l'imposent défensivement). OOS_ACCESSED=NO.

---

## DS1 — USA500IDXUSD 5m (proxy marché original P000)

- DATASET_ID=USA500IDXUSD_5M
- SOURCE=Dukascopy public datafeed (index CFD, sans clé) — https://datafeed.dukascopy.com/datafeed/USA500IDXUSD/...
- URL_SCRIPT=research/phenomena_discovery_v1/dukascopy_download.py
- SYMBOL=USA500.IDX/USD (S&P 500 index CFD, cotes BID)
- FREQUENCY=5 min (agrégé depuis 1 min Dukascopy, build_5m.py)
- TIMEZONE=UTC (converti en America/New_York pour les sessions, DST géré)
- BID_OR_MID=BID
- FIRST_TS=2011-09-19 00:00:00 UTC
- LAST_TS=2026-04-08 23:55:00 UTC
- ROWS_5M=1 090 080
- ACCESS_DATE=2026-09-11
- SHA256(parquet)=181ac27d02f18061...
- KNOWN_LIMITATIONS=proxy CFD (cotes dealer composite), PAS le consolidated tape des actions ; volume = ticks feed (utilisé pour VWAP, fallback TWAP documenté) ; 2010-09-2011 absente
- REVISION_RISK=LOW (feed historique figé)
- CAUSALITY_NOTES=barre 5m = début de bucket, connue à fin de bucket ; niveaux pre-market [04:00,09:30) ET utilisables seulement dès 09:30 ET

## DS2 — USATECHIDXUSD 5m (réplication cross-marché P000)

- DATASET_ID=USATECHIDXUSD_5M — même source/limites que DS1
- FIRST_TS=2011-09-19 UTC, LAST_TS=2026-04-08 23:55 UTC, ROWS_5M=1 089 792
- SHA256(parquet)=82eb9c588c5b49da...

## DS3..DS5 — EURUSD / GBPUSD / USDJPY 5m (P000_TRANSFER + screens FX)

- DATASET_ID=EURUSD_5M / GBPUSD_5M / USDJPY_5M
- SOURCE=Dukascopy public datafeed (spot FX BID, sans clé)
- FREQUENCY=5 min (agrégé depuis 1 min) ; USDJPY échelle de prix détectée 1/1000 (quotes 3 décimales), EUR/GBP 1/100000 (5 décimales) — détection automatique validée par plage de prix
- TIMEZONE=UTC
- FIRST_TS=2010-01-01 00:00:00 UTC (les 3)
- LAST_TS=2026-04-08 23:55:00 UTC (les 3)
- ROWS_5M=1 218 528 / 1 220 544 / 1 215 936
- SHA256=4ea2e1abebefdb45... / bda776cf08595ef1... / ece2140c8e5d9d9d...
- KNOWN_LIMITATIONS=pas de séance dimanche (le feed démarre lundi 00:00 UTC) → P011 (weekend gap) non testable ; volume = tick count proxy
- REVISION_RISK=LOW
- CAUSALITY_NOTES=identiques ; ranges "Asie" [23:00,07:00) UTC construits uniquement depuis barres < 07:00 du jour + [23:00,24:00) de la veille

## DS6 — M15 du dépôt (screens anti-edge P028/P029)

- DATASET_ID=REPO_M15
- SOURCE=GBPUSD15.csv, USDJPY15.csv (worktree, exports MT4) + EURUSD15_full.csv (export complet extrait du snapshot git 3cd12c3 — le worktree EURUSD15.csv n'est qu'un cut 2020+)
- TIMEZONE=heure serveur MT4 (offset inconnu, IDENTIQUE entre paires) — screens utilisés SANS logique de session (croisements EMA/Donchian only)
- FREQUENCY=15 min
- PÉRIODE UTILISÉE=2010-01-01 → 2018-12-31 (Discovery), filtrée défensivement < 2026-04-09
- SHA256(EURUSD15_full.csv)=8c2dd952d2a8f8d2... (identique au manifest de la mission H1/H4 — même fichier)
- KNOWN_LIMITATIONS=timezone serveur inconnue ; pas de volume fiable
- REVISION_RISK=NONE (fichier figé dans git)

## Étalonnage des coûts (SYNTHETIC)

- Mesure d'échantillon BID/ASK Dukascopy USA500 (research/phenomena_discovery_v1/measure_spread.py) :
  écarts médians minute-close ~0.005–0.01 index point (quotes CFD fines).
- Les scénarios de coûts RESTENT paramétriques et conservateurs :
  US (points d'indice aller-retour) LOW=0.5 / NORMAL=1.0 / STRESS=2.5 — NORMAL ≈
  spread ETF classe SPY + commission + slippage ; STRESS = friction pénalisante.
  FX (pips aller-retour) LOW=1.0 / NORMAL=2.0 / STRESS=3.5 (conventions du dépôt).
- Aucun coût n'est présenté comme « réaliste » : SYNTHETIC par convention.

## Conformité OOS

- Toutes les données chargées passent par un filtre strict `ts < 2026-04-09`.
- Aucun run, statistique ou visuel n'a été produit sur [2026-04-09, 2026-07-24].
- OOS_ACCESSED=NO
