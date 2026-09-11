# VALIDATION_1 — candidats gelés sur 2019-01-01 → 2022-12-31

> ⚠️ **INVALIDATED_BY_DOUBLE_EXECUTION_SHIFT** : la première version de ce
> rapport (commit d460acb) mesurait la validation avec un double décalage
> d'exécution (shift dans `evaluate_window` + shift dans `event_returns`),
> incohérent avec DISCOVERY (un seul shift). Ces chiffres sont invalidés et
> remplacés ci-dessous par le rerun corrigé (mêmes candidats gelés, mêmes
> règles, aucun retuning). L'historique Git conserve la version invalide.

Convention corrigée : les générateurs produisent le signal brut sur la
barre dont la clôture le rend connu ; `event_returns()` applique LE
seul décalage d'exécution (close[i] → open[i+1]). Garanti par les tests
de parité DISCOVERY/VALIDATION (`TestExecutionShiftParity`).

Censure de borne ajoutée (revue final) : un événement n'est conservé que
si sa décision ET le règlement de son horizon (`ts[i+horizon]`) sont
strictement dans la fenêtre — aucun horizon V1 ne consomme plus un prix
de 2023. Chiffres du rerun à censure : C1 N=5 411 (9 événements censurés),
C2 N=308 (inchangé).

## C1 — F6 mean reversion H1 (SMA 20, z 1.5, horizon 48 barres = 48 heures)

| | N | MEAN pips | après LOW | après NORMAL | après STRESS | WIN | EX99 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Agrégat | 5 411 | −1.77 | −2.77 | **−3.77** | −5.27 | 49.4 % | −5.29 |
| EURUSD | 1 852 | −2.15 | −3.15 | −4.15 | −5.65 | 48.5 % | −4.49 |
| GBPUSD | 1 843 | −3.18 | −4.18 | −5.18 | −6.68 | 49.1 % | −6.91 |
| USDJPY | 1 716 | +0.14 | −0.86 | −1.86 | −3.36 | 50.7 % | −4.21 |

**GATE : FAIL** (`AFTER_NORMAL > 0` violé : −3.77 ; `PAIRS_POS = 0/3`).
L'effet DISCOVERY (+1.30) s'inverse complètement — inchangé dans sa
substance par rapport au run invalide : l'effet de mean-reversion
2010-2018 était un artifact de période.

## C2 — F5 vol-compression breakout H1 (L 40, ratio 0.85, horizon 12h)

| | N | MEAN pips | après LOW | après NORMAL | après STRESS | WIN | EX99 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Agrégat | 308 | +3.01 | +2.01 | **+1.01** | −0.49 | 53.3 % | +1.03 |
| EURUSD | 86 | +1.51 | +0.51 | −0.49 | −1.99 | 47.7 % | +0.36 |
| GBPUSD | 110 | −1.06 | −2.06 | −3.06 | −4.56 | 53.6 % | −3.66 |
| USDJPY | 112 | +8.16 | +7.16 | +6.16 | +4.66 | 57.1 % | +5.25 |

**GATE : FAIL** — `PAIRS_POS = 1/3` (critère existant : ≥ 2/3 paires ne
contredisent pas). L'agrégat reste positif après NORMAL (+1.01), mais
porté par USDJPY seul ; EURUSD et GBPUSD sont négatifs. N = 308 (limite).

## Portes de passage

```
C1 : GATE FAIL → n'entre pas en VALIDATION_2
C2 : GATE FAIL → n'entre pas en VALIDATION_2
Aucun candidat n'atteint VALIDATION_2 après correction du double-shift.
```
