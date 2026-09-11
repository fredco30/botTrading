# Data manifest — recherche H1/H4 multi-paires

Pipeline commun : CSV M15 (export MT4, OHLC Bid) -> filtre strict
`2010-01-01 <= ts < 2026-04-09` AVANT toute analyse -> agrégation
calendaire H1/H4 (open=premier, high=max, low=min, close=dernier).
Les buckets partiels de clôture hebdomadaire sont conservés tels quels
(barres de marché réelles, rien de fabriqué). Timezone = heure serveur MT4
(offset inconnu mais IDENTIQUE pour les 3 paires — même terminal),

## EURUSD H1

- SOURCE=C:\Users\Fred\.zcode\tmp\autonomous\eurusd15_snapshot.csv (git snapshot 3cd12c3:EURUSD15.csv)
- SYMBOL=EURUSD
- TIMEZONE=MT4 server time (unknown offset, consistent across pairs)
- BID_OR_MID=BID (MT4 export)
- FIRST_TS=2010-01-04 00:00:00
- LAST_TS=2026-04-08 02:00:00
- ROWS=100853
- SHA256(source)=8c2dd952d2a8f8d2...

## EURUSD H4

- SOURCE=C:\Users\Fred\.zcode\tmp\autonomous\eurusd15_snapshot.csv (git snapshot 3cd12c3:EURUSD15.csv)
- SYMBOL=EURUSD
- TIMEZONE=MT4 server time (unknown offset, consistent across pairs)
- BID_OR_MID=BID (MT4 export)
- FIRST_TS=2010-01-04 00:00:00
- LAST_TS=2026-04-08 00:00:00
- ROWS=25282
- SHA256(source)=8c2dd952d2a8f8d2...

## GBPUSD H1

- SOURCE=C:\Users\Fred\.zcode\tmp\audit-bottrading\botTrading\GBPUSD15.csv
- SYMBOL=GBPUSD
- TIMEZONE=MT4 server time (unknown offset, consistent across pairs)
- BID_OR_MID=BID (MT4 export)
- FIRST_TS=2010-01-04 00:00:00
- LAST_TS=2026-04-08 23:00:00
- ROWS=100923
- SHA256(source)=30009aff684656ee...

## GBPUSD H4

- SOURCE=C:\Users\Fred\.zcode\tmp\audit-bottrading\botTrading\GBPUSD15.csv
- SYMBOL=GBPUSD
- TIMEZONE=MT4 server time (unknown offset, consistent across pairs)
- BID_OR_MID=BID (MT4 export)
- FIRST_TS=2010-01-04 00:00:00
- LAST_TS=2026-04-08 20:00:00
- ROWS=25299
- SHA256(source)=30009aff684656ee...

## USDJPY H1

- SOURCE=C:\Users\Fred\.zcode\tmp\audit-bottrading\botTrading\USDJPY15.csv
- SYMBOL=USDJPY
- TIMEZONE=MT4 server time (unknown offset, consistent across pairs)
- BID_OR_MID=BID (MT4 export)
- FIRST_TS=2010-01-04 00:00:00
- LAST_TS=2026-04-08 23:00:00
- ROWS=100929
- SHA256(source)=30c0d7436a448344...

## USDJPY H4

- SOURCE=C:\Users\Fred\.zcode\tmp\audit-bottrading\botTrading\USDJPY15.csv
- SYMBOL=USDJPY
- TIMEZONE=MT4 server time (unknown offset, consistent across pairs)
- BID_OR_MID=BID (MT4 export)
- FIRST_TS=2010-01-04 00:00:00
- LAST_TS=2026-04-08 20:00:00
- ROWS=25300
- SHA256(source)=30c0d7436a448344...
