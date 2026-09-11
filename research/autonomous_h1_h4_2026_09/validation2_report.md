# VALIDATION_2 — 2023-01-01 → 2026-04-09 (exclusif)

> ⚠️ **INVALIDATED_BY_DOUBLE_EXECUTION_SHIFT** : la première version de ce
> rapport testait C2 sur VALIDATION_2 avec le double décalage d'exécution
> (−0.41 pips après NORMAL). Ces chiffres sont invalidés.

## État après correction

Après le rerun corrigé (un seul décalage d'exécution, convention unifiée,
testée par `TestExecutionShiftParity`) :

- **C1 — F6 mean reversion H1** : GATE VALIDATION_1 FAIL (−3.88 pips après
  NORMAL, 0/3 paires) → n'entre pas en VALIDATION_2.
- **C2 — F5 vol-compression breakout H1** : GATE VALIDATION_1 FAIL
  (`PAIRS_POS = 1/3`, le seul porteur étant USDJPY) → n'entre pas en
  VALIDATION_2.

```
VALIDATION_2 : NON EXÉCUTÉE — aucun candidat gelé n'a passé la gate V1 corrigée.
```

Conformément à la mission (§6 : « uniquement pour les candidats qui
passent le gate V1 corrigé » ; §11 CAS B), la mission s'arrête au
verdict :

```
NO_ROBUST_H1_H4_MULTIPAIR_EDGE_FOUND
```
