#!/usr/bin/env python3
"""P032R FOMC post-reaction continuation — V1 lib (règle figée, voir
P032R_FROZEN_SPEC.md committé AVANT toute lecture des prix V1).

Unité statistique = événement FOMC (les 3 jambes restent ensemble).
Tous les prix = OPEN de barres 5 min Dukascopy (ts = bar OPEN, UTC).
"""
import json
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))

V1_START = pd.Timestamp("2019-01-01", tz="UTC")
V1_END = pd.Timestamp("2023-01-01", tz="UTC")  # EXCLUS

PAIRS = ["EURUSD", "USDJPY", "GBPUSD"]
PIP = {"EURUSD": 1e-4, "USDJPY": 1e-2, "GBPUSD": 1e-4}
COST_NORMAL_PIPS = 2.0
COST_STRESS_PIPS = 4.0

TZ_OFFSET = {"EST": -5, "EDT": -4}

# Réunions FOMC PROGRAMMÉES 2019-2022 (8/an) — pages officielles
# federalreserve.gov/monetarypolicy/fomchistorical{2019,2020}.htm et
# snapshot officiel fomccalendars.htm (2021, 2022).
# Format: (année_réunion, date du communiqué "monetaryYYYYMMDDa").
SCHEDULED_STATEMENTS = [
    ("2019", "2019-01-30"), ("2019", "2019-03-20"), ("2019", "2019-05-01"),
    ("2019", "2019-06-19"), ("2019", "2019-07-31"), ("2019", "2019-09-18"),
    ("2019", "2019-10-30"), ("2019", "2019-12-11"),
    ("2020", "2020-01-29"), ("2020", "2020-03-15"),  # réunion programmée mars 17-18 tenue en visio le 15
    ("2020", "2020-04-29"), ("2020", "2020-06-10"), ("2020", "2020-07-29"),
    ("2020", "2020-09-16"), ("2020", "2020-11-05"), ("2020", "2020-12-16"),
    ("2021", "2021-01-27"), ("2021", "2021-03-17"), ("2021", "2021-04-28"),
    ("2021", "2021-06-16"), ("2021", "2021-07-28"), ("2021", "2021-09-22"),
    ("2021", "2021-11-03"), ("2021", "2021-12-15"),
    ("2022", "2022-01-26"), ("2022", "2022-03-16"), ("2022", "2022-05-04"),
    ("2022", "2022-06-15"), ("2022", "2022-07-27"), ("2022", "2022-09-21"),
    ("2022", "2022-11-02"), ("2022", "2022-12-14"),
]


def load_events():
    """Timestamps de release UTC depuis la source officielle
    (heures exactes 'For release at' parsées des communiqués)."""
    with open(os.path.join(ROOT, "data_raw", "official",
                           "fomc_decisions.json")) as f:
        by_date = {e["date"]: e for e in json.load(f)}
    events = []
    for year, d in SCHEDULED_STATEMENTS:
        e = by_date[d]
        off = TZ_OFFSET[e["tz"]]
        ts = pd.Timestamp(f"{e['date']} {e['release_time']}", tz="UTC") \
            - pd.Timedelta(hours=off)
        events.append({"EVENT_DATE": d, "YEAR": year, "RELEASE_TS": ts})
    return events


def load_bars(pair):
    df = pd.read_parquet(os.path.join(ROOT, "data_raw", "parquet",
                                      f"{pair}_5m.parquet"))
    return df.sort_index()


def first_open_at_or_after(bars, ts):
    """OPEN de la première barre 5 min dont l'OPEN ts >= ts."""
    idx = bars.index.searchsorted(ts, side="left")
    if idx >= len(bars.index):
        return None, None
    t = bars.index[idx]
    return t, float(bars["open"].iloc[idx])


def measure_event_pair(bars, release_ts, pair, v1_start=V1_START,
                       v1_end=V1_END):
    """T0/T30/T120 causaux + INITIAL_MOVE + CONT_30_120 (pips).
    Retourne None si T0/T30/T120 introuvables ou hors V1
    (entrée ET sortie doivent être dans V1)."""
    t0, p0 = first_open_at_or_after(bars, release_ts)
    if t0 is None or t0 < v1_start:
        return None
    t30, p30 = first_open_at_or_after(bars, t0 + pd.Timedelta(minutes=30))
    if t30 is None:
        return None
    t120, p120 = first_open_at_or_after(bars, t0 + pd.Timedelta(minutes=120))
    if t120 is None:
        return None
    if not (v1_start <= t0 < v1_end and v1_start <= t120 < v1_end):
        return None
    pip = PIP[pair]
    return {"T0": t0, "P0": p0, "T30": t30, "P30": p30,
            "T120": t120, "P120": p120,
            "INITIAL_MOVE_PIPS": (p30 - p0) / pip,
            "CONT_30_120_PIPS": (p120 - p30) / pip}


def build_table(events, bars_by_pair):
    """Une ligne = une réunion. Si une jambe manque, l'événement est
    exclu en entier (les 3 jambes restent ensemble)."""
    rows = []
    for ev in events:
        row = {"EVENT_DATE": ev["EVENT_DATE"], "YEAR": ev["YEAR"],
               "RELEASE_TS": ev["RELEASE_TS"]}
        ok = True
        for pair in PAIRS:
            r = measure_event_pair(bars_by_pair[pair], ev["RELEASE_TS"], pair)
            if r is None:
                ok = False
                break
            row[f"{pair}_INITIAL_30M"] = r["INITIAL_MOVE_PIPS"]
            row[f"{pair}_CONT_30_120_GROSS"] = r["CONT_30_120_PIPS"]
        if not ok:
            continue
        rows.append(row)
    df = pd.DataFrame(rows)
    for pair in PAIRS:
        direction = np.sign(df[f"{pair}_INITIAL_30M"])
        gross = df[f"{pair}_CONT_30_120_GROSS"]
        df[f"{pair}_NET_NORMAL"] = direction * gross - COST_NORMAL_PIPS
        df[f"{pair}_NET_STRESS"] = direction * gross - COST_STRESS_PIPS
    df["POOLED_GROSS"] = df[[f"{p}_CONT_30_120_GROSS" for p in PAIRS]].mean(axis=1)
    df["POOLED_NET_NORMAL"] = df[[f"{p}_NET_NORMAL" for p in PAIRS]].mean(axis=1)
    df["POOLED_NET_STRESS"] = df[[f"{p}_NET_STRESS" for p in PAIRS]].mean(axis=1)
    return df


def paired_bootstrap_ci(net_by_event, n=2000, seed=42):
    """Bootstrap PAIRED par événement: on rééchantillonne des événements
    entiers (les 3 jambes voyagent ensemble via POOLED par ligne)."""
    rng = np.random.default_rng(seed)
    x = np.asarray(net_by_event, dtype=float)
    means = rng.choice(x, size=(n, x.size), replace=True).mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def classify(table):
    pooled = float(table["POOLED_NET_NORMAL"].mean())
    pair_means = {p: float(table[f"{p}_NET_NORMAL"].mean()) for p in PAIRS}
    pos_pairs = sum(1 for v in pair_means.values() if v > 0)
    by_year = table.groupby("YEAR")["POOLED_NET_NORMAL"].mean()
    pos_years = int((by_year > 0).sum())
    remove_best = float(
        table["POOLED_NET_NORMAL"].sort_values(ascending=False)
        .iloc[1:].mean())
    lo, hi = paired_bootstrap_ci(table["POOLED_NET_NORMAL"].values)
    gate1 = pooled >= 5.0 and pos_pairs >= 2 and remove_best > 0
    if gate1 and pos_years >= 3 and lo > 0:
        cls = "P032R_V1_STRONG"
    elif gate1:
        cls = "P032R_V1_SUPPORTIVE"
    else:
        cls = "P032R_V1_REJECT"
    return {"N_EVENTS": len(table), "pair_means_net_normal": pair_means,
            "POOLED_GROSS": float(table["POOLED_GROSS"].mean()),
            "POOLED_NET_NORMAL": pooled,
            "POOLED_NET_STRESS": float(table["POOLED_NET_STRESS"].mean()),
            "MEDIAN_NET_NORMAL": float(table["POOLED_NET_NORMAL"].median()),
            "WIN_RATE_NET_NORMAL": float((table["POOLED_NET_NORMAL"] > 0).mean()),
            "BY_YEAR_NET_NORMAL": {k: float(v) for k, v in by_year.items()},
            "POS_YEARS": f"{pos_years}/{by_year.size}",
            "REMOVE_BEST_EVENT_NET_NORMAL": remove_best,
            "CI95_NET_NORMAL": [lo, hi], "CLASSIFICATION": cls}
