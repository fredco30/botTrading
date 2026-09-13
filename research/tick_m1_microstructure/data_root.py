#!/usr/bin/env python3
"""TICK-M1 data root resolution.

Machine-specific paths must NOT be hardcoded in repo code. Resolution order:
  1. explicit --data-root CLI argument (highest)
  2. env BOTTRADING_TICK_DATA_ROOT
  3. repo-relative default: <repo>/data_raw/tick_m1  (small-scale / CI use)

Layout under the root:
  raw/EURUSD/YYYYMMDD/HHh_ticks.bi5      (hourly Dukascopy files, as in TICK-M0)
  raw/EURUSD/YYYYMMDD/HHh_ticks.bi5.missing  (404 marker for resume)
  parquet/EURUSD/year=YYYY/month=MM/ticks.parquet
"""
import os


def resolve_data_root(cli_value=None):
    if cli_value:
        return os.path.abspath(cli_value)
    env = os.environ.get("BOTTRADING_TICK_DATA_ROOT")
    if env:
        return os.path.abspath(env)
    repo = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    return os.path.join(repo, "data_raw", "tick_m1")


def raw_dir(root, symbol):
    return os.path.join(root, "raw", symbol.upper())


def parquet_dir(root, symbol):
    return os.path.join(root, "parquet", symbol.upper())


def hour_path(raw_sym_dir, y, m, d, h):
    """raw_sym_dir = raw_dir(root, symbol); kept symbol-free by construction."""
    return os.path.join(raw_sym_dir, f"{y:04d}{m:02d}{d:02d}", f"{h:02d}h_ticks.bi5")
