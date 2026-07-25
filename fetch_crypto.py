#!/usr/bin/env python3
"""Telecharge l'historique crypto depuis Binance au format CSV MT4.

A lancer sur TA machine : l'environnement distant ou tourne le moteur bloque
api.binance.com par politique reseau.

Sortie : BTCUSD15.csv, ETHUSD15.csv, ... au format exact des exports MT4
    2017.08.17,04:00,4261.48,4313.62,4261.32,4308.83,47

Aucune dependance : urllib de la bibliotheque standard suffit.

    python fetch_crypto.py
    python fetch_crypto.py --symbols BTCUSDT,ETHUSDT --interval 15m
    python fetch_crypto.py --start 2017-01-01

Ensuite :
    git add *15.csv && git commit -m "data: crypto" && git push
"""

import argparse
import json
import os
import time
import urllib.request
from datetime import datetime, timezone

BASE = "https://api.binance.com/api/v3/klines"

# Paires par defaut. USDT plutot que USD : c'est la ou est la liquidite et la
# profondeur d'historique sur Binance.
DEFAULT = "BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,XRPUSDT,ADAUSDT,LTCUSDT,LINKUSDT"

MS = {"15m": 900_000, "1h": 3_600_000, "4h": 14_400_000}


def fetch_klines(symbol, interval, start_ms, end_ms, pause=0.25):
    """Pagine l'API Binance (1000 bougies max par appel)."""
    out = []
    cur = start_ms
    step = MS[interval] * 1000
    while cur < end_ms:
        url = (f"{BASE}?symbol={symbol}&interval={interval}"
               f"&startTime={cur}&limit=1000")
        for attempt in range(5):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
                with urllib.request.urlopen(req, timeout=30) as r:
                    batch = json.load(r)
                break
            except Exception as exc:
                if attempt == 4:
                    raise
                # 429 = rate limit : Binance veut qu'on ralentisse, pas qu'on insiste
                wait = 2 ** attempt
                print(f"\n  {type(exc).__name__} -> nouvelle tentative dans {wait}s")
                time.sleep(wait)

        if not batch:
            cur += step
            continue
        out.extend(batch)
        last = batch[-1][0]
        if last <= cur:
            break
        cur = last + MS[interval]
        print(f"\r  {symbol} {interval}: {len(out):>7} bougies "
              f"jusqu'a {datetime.fromtimestamp(last/1000, timezone.utc):%Y-%m-%d}",
              end="", flush=True)
        time.sleep(pause)
    print()
    return out


def to_mt4_csv(klines, path):
    """Ecrit au format d'export MT4, en UTC.

    Attention : MT4 chez IC Markets tourne en heure serveur (GMT+2/+3), pas en
    UTC. Le systeme v2 n'a aucun filtre horaire, donc ce decalage ne change
    rien ici - mais il compterait pour toute strategie a filtres de session.
    """
    seen = set()
    rows = []
    for k in klines:
        ts = int(k[0]) // 1000
        if ts in seen:
            continue
        seen.add(ts)
        dt = datetime.fromtimestamp(ts, timezone.utc)
        rows.append(f"{dt:%Y.%m.%d},{dt:%H:%M},{float(k[1]):.8g},{float(k[2]):.8g},"
                    f"{float(k[3]):.8g},{float(k[4]):.8g},{int(float(k[5]))}")
    rows.sort()
    with open(path, "w", newline="\r\n") as fh:
        fh.write("\n".join(rows) + "\n")
    return len(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbols", default=DEFAULT)
    ap.add_argument("--interval", default="15m", choices=sorted(MS))
    ap.add_argument("--start", default="2017-01-01")
    ap.add_argument("--out", default=".")
    args = ap.parse_args()

    start_ms = int(datetime.strptime(args.start, "%Y-%m-%d")
                   .replace(tzinfo=timezone.utc).timestamp() * 1000)
    end_ms = int(time.time() * 1000)

    for sym in args.symbols.split(","):
        sym = sym.strip().upper()
        if not sym:
            continue
        # BTCUSDT -> BTCUSD15.csv, pour coller au nommage des exports MT4
        name = sym[:-1] if sym.endswith("USDT") else sym
        path = os.path.join(args.out, f"{name}15.csv")
        print(f"{sym} -> {path}")
        try:
            kl = fetch_klines(sym, args.interval, start_ms, end_ms)
        except Exception as exc:
            print(f"  ECHEC : {exc}")
            continue
        if not kl:
            print("  aucune donnee")
            continue
        n = to_mt4_csv(kl, path)
        first = datetime.fromtimestamp(kl[0][0] / 1000, timezone.utc)
        last = datetime.fromtimestamp(kl[-1][0] / 1000, timezone.utc)
        print(f"  {n} bougies   {first:%Y-%m-%d} -> {last:%Y-%m-%d}   "
              f"{(last - first).days / 365.25:.1f} ans")

    print("\nEnsuite :  git add *15.csv && git commit -m 'data: crypto' && git push")


if __name__ == "__main__":
    main()
