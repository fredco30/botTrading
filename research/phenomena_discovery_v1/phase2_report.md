# PHASE 2 REPORT — phenomena-discovery-v1 (audit fix + causal phenomena)

Périmètre : 10 familles causales au-delà des patterns OHLC simples, Discovery
uniquement (2010-01-01 → 2018-12-31), accès V1/V2 verrouillé par `gate.py`
(aucune autorisation délivrée : aucun candidat n'a franchi le gate Discovery).
Données ajoutées : EURGBP/EURJPY/GBPJPY/XAUUSD 5-min Dukascopy ; DGS2 /
DFEDTARU / ECBDFR / BOERUKM (FRED, officiels) ; taux BoJ (dates de décision
officielles, ASSUMPTION proxy) ; calendrier FOMC officiel avec heures de
publication parsées depuis chaque communiqué (« For release at … », 131
décisions 2011-2026, 91 avec heure exacte ; pré-2015 = « For immediate
release » sans heure → exclus des fenêtres intraday).
Résultats bruts : phase2_results.json ; checks de gate : phase2_gate_checks.json.

## 1. Corrections d'audit appliquées avant tout recalcul

| Fix | Contenu |
|---|---|
| A — pip USDJPY | /0.0001 → P.PIP[sym] (USDJPY = 0.01) dans P028/P029 + test 10 pips ≡ 10 pips |
| B — fenêtre | execution_ts ∈ Discovery ET future_ts < DISCOVERY_END strict + test frontière |
| C — entry_ts | = barre d'exécution réelle (l'ancien code enregistrait la barre du prix futur) + test |
| D — contamination | P029_V1_V2_ACCESSED_PREMATURELY=YES ; P029_V1_V2_CONTAMINATED=YES ; résultats marqués INVALID_FOR_FRESH_VALIDATION ; V1/V2 NON relancées |
| E — classification | P000_ORIGINAL (actions US, DATA_BLOCKED) ≠ P000_PROXY_SP500_CFD (testé, NO_ROBUST_EDGE_FOUND) |
| F — trim guard | trim jamais pire que le fill (long : trim ≥ fill ; short : trim ≤ fill) + running_day_extremes re-shifté PAR jour (la 1ère barre du jour n'hérite plus de la veille) + tests |

Effet des fixes sur les résultats existants : P029 USDJPY −76.6 pips (erreur
×100) → −0.77 pip (cohérent 3/3, toujours gross-négatif → inversion toujours
sous les coûts → REJECT confirmé) ; sims P000 stratégie marginalement
modifiées (gross Discovery P000A 0.039→0.047 pt) — RAW bit-identique, verdicts
inchangés.

## 2. Résultats par famille (Discovery, gross)

| Famille | Résultat principal | Verdict |
|---|---|---|
| P010 cross-pair lead/lag | EURGBP-shock → GBPUSD +0.31/+0.38 pips (5/15m, P≤.001, best5 stable) ; EURUSD→USDJPY +0.14→+0.39 pips (P≤.02) | REJECT (traces < coûts) |
| P010 résidu triangulaire | « réversion » de +2σ en 5 min sur triangle EUR/GBP = bruit d'asynchronie de feed — ARTEFACT, pas un arbitrage | REJECT (artefact documenté) |
| P026 US 2Y → USDJPY | choc ≥3bp : +3.9 pips j+1 (P=.29), +8.2 pips j+5 (P=.20) — direction conforme au mécanisme, non significatif | INCONCLUSIVE (sous-puissant) |
| P025 carry (Fed/ECB/BoE/BoJ) | tout ≈ 0 ; USDJPY level +19 pips/20d (P=.29) seul positif | REJECT |
| P027 gold ↔ JPY | gold-shock → USDJPY −0.35 pip @60m (P=.03, direction risk-off) ; USDJPY-shock → gold −0.03..−0.10 (P≤.02) | REJECT (traces) |
| P020 London fix 16:00 | post-fix fade : EURUSD +0.83 (WR 51.8%) / GBPUSD +1.23 (WR 55.1%) ; amplification month-end réelle mais instable par année | REJECT (sous les coûts) |
| P013 month-end | MEILLEUR signe du cycle : USDJPY long au close du dernier jour ouvré → j+1 : +6.77 pips, 7/9 ans positifs, MAIS p=0.138, IC95 [−2.1, +16.2] ; GBPUSD on-day +8.79 p=0.066 avec 2015/2018 négatifs | NO_CANDIDATE (gate non franchi) |
| P032 post-FOMC | N=24 (2015-2018, heures publiées) ; réaction initiale |Δ|≈10-14 pips/30min ; continuation 30m→2h +3.3/+1.9 pips | INCONCLUSIVE (sous-puissant) |
| P004 PDH/PDL (8 types d'événements) | signes miroir-incohérents entre paires (USDJPY break_PDH +1.94 P=.002 vs EURUSD −0.07) | REJECT (pas de cohérence cross-marché) |
| P006 NY overlap | continuation London→NY +0.9 à +1.9 pips, WR 50-51.4% | REJECT (sous les coûts) |
| P034 compression → vol | expansion forward 12h : ratio 1.24-1.29 (EURUSD, N=1800-2166), 1.09-1.12 (USDJPY) vs baseline | **SECOND_ORDER_CANDIDATE** (pas de direction) |

## 3. Gate Discovery — pourquoi aucun candidat

Le gate exige : effet brut clair (p<0.05 idéalement avec IC ne croisant pas 0),
amplitude > coûts NORMAL, stabilité temporelle, robustesse outliers,
mécanisme plausible. Le meilleur prétendant (P013 USDJPY month-end) échoue
sur la significativité (p=0.138) et l'amplitude nette (6.8 pips bruts ≈ 4.8
nets à NORMAL, sans significativité). Conformément au protocole (et à la leçon
P029) : **aucune fenêtre V1 n'a été ouverte** — la décision est journalisée
dans phase2_gate_checks.json et gate_audit.log reste sans autorisation.

## 4. Verdicts

NEW_DISCOVERY_CANDIDATES=0
NEW_V1_CANDIDATES=0
NEW_V2_CANDIDATES=0
FINAL_VERDICT=NO_ROBUST_PHENOMENON_FOUND_AFTER_PHASE2

## 5. Ce qui reste exploitable

- P034 (compression → expansion de volatilité, ratio 1.1-1.3×) : sizing/
  vol-targeting — candidat second-order pour une mission volatilité.
- P013 month-end USDJPY : si une mission future veut le creuser, il faudra
  d'abord PLUS d'historique ou un test multi-marchés JPY-cross (EURJPY/GBPJPY
  disponibles dès maintenant) AVANT tout V1 — hypothèse non consommée (V1/V2
  verrouillées, jamais regardées).
- Traces de microstructure (lag EURGBP→GBPUSD, fade du fix, gold-JPY) :
  utiles pour une couche d'exécution, pas comme signaux autonomes.
