# PHENOMENA DISCOVERY V1 — recherche autonome d'edges de marché

Branche : `research/phenomena-discovery-v1` (base `main` @ `005dceed`).
Pipeline scientifique : PHENOMENON → SIGNAL → VALIDATION → STRATEGY.
Priorité absolue : **P000** = stratégie de la vidéo fournie par l'utilisateur,
reconstruite EXTERNALLY_PREREGISTERED puis testée sans optimisation.

## Verdict en une ligne

**FINAL_VERDICT = NO_ROBUST_PHENOMENON_FOUND_IN_V1_SEARCH_SPACE** — la
stratégie de la vidéo n'a pas d'edge net robuste sur son marché (proxy S&P
500) ni en transposition FX ; aucun des 16 phénomènes testés en Discovery ne
franchit le gate ; 1 candidat anti-edge (Donchian M15 gross-négatif 3/3) mais
son inversion n'est pas net-positive ni stable → 0 survivant.

## Contenu

| Fichier | Rôle |
|---|---|
| `video_strategy_spec.md` | Règles P000 reconstruites du transcript + ambiguïtés |
| `video_strategy_results.json` | Résultats bruts P000A/P000B/P000C (raw + stratégie, 3 splits) |
| `video_strategy_report.md` | Analyse et verdicts P000 |
| `p000_replication_usatech.json` | Réplication cross-marché P000A (Nasdaq 100 CFD) |
| `literature_review.md` | Sources académiques/institutionnelles codées |
| `hypothesis_catalog.md` | P001-P040 : mécanismes, classes, budget |
| `hypothesis_ledger.csv` | Registre complet (aucun échec ne disparaît) |
| `data_manifest.md` | Sources, couverture, hash, limites, conformité OOS |
| `methodology.md` | Causalité, fenêtres, mesures, gates, protocole anti-edge |
| `phenomena_screen.json/.csv` | Screens Discovery 2010-2018 (16 familles) |
| `anti_edge_report.md` + `anti_edge_results.json` | Protocole anti-edge |
| `rejected_hypotheses.md` | Rejets motivés (Discovery uniquement) |
| `second_order_opportunities.md` | Effets de volatilité sans direction |
| `video_source/` | Transcript + description + métadonnées de la vidéo |
| `dukascopy_probe.py` / `dukascopy_download.py` / `build_5m.py` | Acquisition données (sans clé, reproductible) |
| `measure_spread.py` | Étalonnage empirique du spread CFD |
| `p000_lib.py` | Librairie causale P000 (détection, event study, simulateur) |
| `run_p000.py` / `phenomena_screen.py` | Exécution des analyses |
| `test_p000_lib.py` | 18 tests synthétiques (timing, DST, causalité, retest, splits, anti-edge) |

## Données (hors git — `data_raw/`)

Dukascopy public datafeed, 5 min BID, 2010-01-01 → 2026-04-08 (fenêtre OOS
2026-04-09 → 2026-07-24 interdite et filtrée défensivement) :
EURUSD, GBPUSD, USDJPY, USA500IDXUSD, USATECHIDXUSD. Tout est re-téléchargeable
sans clé : `python dukascopy_download.py && python build_5m.py`.

## Comment relancer

```bash
python research/phenomena_discovery_v1/dukascopy_download.py   # ~1.7 h
python research/phenomena_discovery_v1/build_5m.py             # ~5 min
python research/phenomena_discovery_v1/run_p000.py             # ~10 min
python research/phenomena_discovery_v1/phenomena_screen.py     # ~8 min
python -m unittest discover -s research/phenomena_discovery_v1 -p "test_*.py"
```

## Prochaine expérience recommandée

Mission « microstructure execution layer » : exploiter SO3/SO4
(second_order_opportunities.md) comme couche de TIMING/EXÉCUTION pour les
futures STRATEGY_V0 — la seule signature robuste multi-marché trouvée ce
cycle (reversion micro-flux ≤ 15 min) est 10-20× sous les coûts en standalone
mais peut réduire la friction d'entrée d'autres signaux.
