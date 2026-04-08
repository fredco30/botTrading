# Bug Report — EMA_Pullback_EA donne 8-20 trades au lieu de 124

## Contexte
Le 08/04/2026 au soir, l'EMA Pullback EA donnait PF 2.12, DD 6.3%, 124 trades sur EURUSD 3 ans avec le preset EURUSD optimise.
Apres le travail sur le module Range (branche feature/range-module), le bot ne donne plus que 8-20 trades meme en revenant sur la branche main.

## Symptomes
- 8 trades avec tous les filtres ON (preset EURUSD)
- 15 trades avec ATR + EMA50 distance OFF
- 20 trades avec TOUS les filtres OFF (ATR, EMA50, Friday, 13h, combos, Thursday)
- 46 trades avec tous filtres OFF + MinSL=10, MaxSL=30 (brut)
- Le brut devrait donner ~700 trades
- Le SMC_Scalper_EA fonctionne normalement sur le meme MT4

## Ce qui a ete teste
1. Recompilation complete (F4 > F7, 0 errors)
2. Suppression du .ex4 + recompilation
3. Renommage du fichier en V5.mq4
4. Retour sur branche main (git checkout main)
5. Copie manuelle du .mq4 de main vers MQL4/Experts/
6. Remise a zero des parametres dans le Strategy Tester
7. Verification du .set exporte (params corrects)
8. Retelechargement des donnees M15 + H1
9. Suppression + retelechargement des donnees historiques

## Ce qui a ete elimine
- Le code : le OnTick sur main est IDENTIQUE a celui qui donnait PF 2.12
- Les inputs : le .set exporte montre les bonnes valeurs
- Le cache MT4 : le SMC Scalper fonctionne normalement
- Les donnees manquantes : 682k barres M15, 175k barres H1 (complet)

## Piste principale
Les donnees M15 commencent en 1971 (MT4 telecharge tout l'historique).
Ca a TOUJOURS ete le cas et ca marchait avant.
Le retelechargement des donnees pendant la session a peut-etre change
quelque chose dans la facon dont MT4 indexe ou lit les donnees.

## Diagnostic a faire demain
1. Verifier l'onglet "Experts" dans le Strategy Tester pour les messages de debug
2. Ajouter des Print() dans OnTick pour tracer quels filtres bloquent
3. Comparer les resultats du brut V1 (historique trade 3ans.txt, 709 trades)
   avec le brut actuel (46 trades) — les dates des trades manquants indiqueront
   quelles periodes sont affectees
4. Tester sur un autre compte demo / autre terminal MT4
5. Verifier si le "Nombre de barres dans le graphique" dans les options MT4
   a ete modifie (Outils > Options > Graphiques > Max barres dans l'historique)

## Piste #2 : Max barres dans l'historique
MT4 a un parametre "Nombre max de barres dans l'historique" et
"Nombre max de barres dans le graphique" dans Outils > Options > Graphiques.
Si cette valeur est trop basse (ex: 65000), le Strategy Tester ne charge pas
assez de donnees et le bot ne peut pas calculer l'EMA correctement sur
toute la periode.
VERIFIER CE PARAMETRE DEMAIN — c'est probablement la cause.

## Fichiers de reference
- Code main (qui marchait) : branche main
- Resultats de reference : historique trade 3ansV2.txt (527 trades, V2)
- Parametres de reference : EMA.set
