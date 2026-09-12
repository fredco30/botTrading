# REJECTED HYPOTHESES — phenomena-discovery-v1

Aucun échec ne disparaît. Rejets en Discovery uniquement (aucun V1 ouvert
sans gate franchie). Détails chiffrés : phenomena_screen.json,
video_strategy_results.json, anti_edge_results.json.

| ID | Nom | Critère de rejet | Chiffres Discovery (gross) |
|---|---|---|---|
| P000A | Video level-retest (USA500 proxy) | pas d'effet brut exploitable + instabilité temporelle | h30m ≈ 0 (P=.92), h60m −0.36 (P=.11) ; V1/V2 positifs non répliqués (USATECH Disc. P=.70) |
| P000B | Video VWAP retest | instabilité temporelle | Disc. + (P≤.006) mais V2 négatif (h120m −0.77) |
| P000C | Transfer FX (3 paires) | gross < coûts NORMAL, signe inversé GBPUSD V2 | h30m ≈ 0-1 pip ; strat net NORMAL < 0 3/3 |
| P001 | Asia range breakout continuation | aucun effet (1/3 paires +0.28, 2/3 ≈0) | EUR +0.28 (P=.34), GBP −0.07, JPY +0.16 |
| P003 | False breakout fade | sous les coûts, incohérent 3/3 | EUR +0.41 (P=.20), GBP +0.70 (P=.04), JPY −0.38 |
| P004 | PDH/PDL levels | non testé ce cycle (priorité) | REGISTERED_NOT_TESTED |
| P005 | London first-hour continuation | incohérent (anti sur EUR, rien GBP/JPY) | −0.97 (P=.04) / −0.63 / +0.15 |
| P007 | Round numbers | trace Osler non tradable, incohérente JPY | −0.27 / −0.37 / −0.02 |
| P008 | Vol-shock continuation | inversion du signe attendu (fade) mais < coûts | −0.12 / −0.58 / −0.31 |
| P011 | Weekend gap fade | DATA_BLOCKED : pas de séance dimanche dans le feed Dukascopy | N=0 |
| P014 | Asia fade London | 1/3 paires seulement | EUR +0.65, GBP +1.78 (P=.00), JPY −0.51 |
| P016 | VWAP mean reversion US | signe inversé (drift continue) et ≈0 | −0.098 pt (P=.02) |
| P018 | Opening gap fill US | aucun effet | −0.037 pt (P=.23), N=14052 |
| P021 | Runs 5m continuation | fade réel mais 10-20× sous les coûts | continuation −0.16/−0.31/−0.18 (3/3, P=.00) |
| P028 | Anti EMA5/20 cross | gross négatif incohérent 3/3 | −0.02 / −0.55 / −23.9 |
| P029 | Anti Donchian 48 M15 | candidat anti-edge mais inversion NON net-positive et instable (voir anti_edge_report.md) | inverted : +1.2/+2.0/+52.5 gross ; net ≤ 0 à NORMAL ; JPY instable 5/9 ans |

## Règles respectées

- Aucun rejet après avoir vu V1 (tous les rejets = Discovery).
- Aucune suppression de résultat : tout est dans les JSON/CSV versionnés.
- Aucun money management pour « sauver » un signal.
- Aucune inversion décidée après ouverture d'une fenêtre de validation.

## Ce qui reste ouvert (cycle suivant)

P004, P006, P009-suite (sizing), P010, P012, P013, P015, P019, P020, P022-P024,
P026, P027, P030-P031, P033-P035, P037, P039-P040 — enregistrés, non testés
(budget du premier cycle). La trace la plus prometteuse pour un cycle dérivé
est la FAMILLE de reversion microstructurelle (P021/P008/P007) en tant que
filtre/timing, pas comme stratégie autonome.
