#!/usr/bin/env python3
"""Runner P032R V1 — exécute UNE FOIS la règle figée (P032R_FROZEN_SPEC.md),
écrit la table, les stats et la classification. Aucune variante."""
import json
import os

import pandas as pd

import lib_v1 as L

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    events = L.load_events()
    print(f"N scheduled FOMC events 2019-2022: {len(events)}")
    bars_by_pair = {p: L.load_bars(p) for p in L.PAIRS}
    table = L.build_table(events, bars_by_pair)
    stats = L.classify(table)

    table.to_csv(os.path.join(HERE, "v1_table.csv"), index=False)
    with open(os.path.join(HERE, "v1_results.json"), "w") as f:
        json.dump(stats, f, indent=2)
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
