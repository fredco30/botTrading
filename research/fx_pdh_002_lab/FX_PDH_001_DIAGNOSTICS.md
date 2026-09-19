# FX_PDH_001 — DIAGNOSTICS (Phase 0, diagnostic ONLY)

Population: the 639 frozen STRICT V1 trades (2020-2025, NORMAL costs). Nothing here filters or changes the strategy; lifecycle variables are NEVER entry filters.

## Feature medians by outcome group (net R)

|                                 |    ALL |   TOP10% |   TOP25% |    MID |   LOSERS<=0 |   REST90% |
|:--------------------------------|-------:|---------:|---------:|-------:|------------:|----------:|
| atr14_pips                      | 17.228 |   15.761 |   16.283 | 16.03  |      17.236 |    17.314 |
| atr_pctile                      |  0.665 |    0.629 |    0.683 |  0.683 |       0.657 |     0.67  |
| prior_day_range_pips            | 84.4   |   72.6   |   80.1   | 78.1   |      84.35  |    85.7   |
| dayopen_below_pdh_pips          | 21.5   |   18.05  |   20.7   | 20.7   |      21.15  |    22.1   |
| travelled_dayopen_to_close_pips | 23.7   |   21.5   |   22.7   | 21.9   |      22.9   |    23.7   |
| close_above_pdh_pips            |  0.4   |    1.1   |    0.2   |  0     |       0.15  |     0.3   |
| high_above_pdh_pips             |  7.3   |    7.15  |    7.1   |  6.5   |       7     |     7.6   |
| gap_vs_prevclose_pips           |  0     |    0     |    0     |  0     |       0     |     0     |
| sig_range_atr                   |  1.53  |    1.413 |    1.558 |  1.558 |       1.52  |     1.532 |
| sig_body_ratio                  |  0.571 |    0.56  |    0.569 |  0.589 |       0.588 |     0.578 |
| sig_close_loc                   |  0.734 |    0.712 |    0.727 |  0.736 |       0.742 |     0.741 |
| bars_into_day                   |  6     |    5.5   |    6     |  6     |       5.5   |     6     |
| ema20_dist_pips                 | 28.327 |   26.13  |   26.82  | 26.159 |      28.181 |    28.69  |
| ret_1d_pips                     | 35.6   |   97.9   |   40.4   | 23.8   |      20.3   |    29.9   |
| ret_3d_pips                     | 46.6   |  104.5   |   50.1   | 29.9   |      29.2   |    39.8   |
| ret_5d_pips                     | 54.6   |  137.95  |   57.6   | 31.9   |      33.15  |    48.9   |
| consec_higher_high_days         |  0     |    0     |    0     |  0     |       0     |     0     |
| her24                           |  0.243 |    0.234 |    0.244 |  0.246 |       0.243 |     0.243 |
| mfe_r                           |  0.985 |    9.354 |    1.639 |  0.582 |       0.513 |     0.811 |
| mae_r                           | -1.157 |   -0.462 |   -1.08  | -1.267 |      -1.314 |    -1.202 |
| time_to_05r_bars                |  0     |    0     |    0     |  0     |       0     |     0     |
| time_to_1r_bars                 |  1     |    1     |    1     |  1     |       1     |     1     |
| time_to_2r_bars                 |  4     |    4     |    4     |  5     |       4     |     4     |
| duration_bars                   |  5     |   37.5   |    9     |  3     |       2     |     4     |

Groups: TOP10%/TOP25% = upper net-R quantiles; MID = interquartile; LOSERS = net R <= 0; REST90% = complement of TOP10%.

## Spearman correlation (pre-entry feature vs net R)

|                                 |      0 |
|:--------------------------------|-------:|
| ret_1d_pips                     |  0.406 |
| ret_3d_pips                     |  0.185 |
| ret_5d_pips                     |  0.133 |
| atr_pctile                      |  0.038 |
| bars_into_day                   |  0.038 |
| sig_range_atr                   |  0.037 |
| gap_vs_prevclose_pips           |  0.021 |
| high_above_pdh_pips             |  0.019 |
| close_above_pdh_pips            |  0.009 |
| travelled_dayopen_to_close_pips | -0.007 |
| dayopen_below_pdh_pips          | -0.01  |
| her24                           | -0.01  |
| consec_higher_high_days         | -0.035 |
| sig_body_ratio                  | -0.046 |
| sig_close_loc                   | -0.054 |
| ema20_dist_pips                 | -0.066 |
| atr14_pips                      | -0.077 |
| prior_day_range_pips            | -0.085 |

## Sessions (signal bar CLOSE hour, UTC)

| session   |   n |   mean_r |   median_r |
|:----------|----:|---------:|-----------:|
| Asia      | 327 |    0.461 |         -1 |
| Late      |   3 |    0.694 |         -1 |
| London    | 129 |    0.344 |         -1 |
| NYpm      |  48 |    0.258 |         -1 |
| Overlap   | 132 |    0.187 |         -1 |

## Runners (top net-R decile) by year

|   year |   runners |   median_r |   mean_r |
|-------:|----------:|-----------:|---------:|
|   2020 |         7 |      5.546 |    7.852 |
|   2021 |        13 |      5.222 |    6.51  |
|   2022 |        17 |      6.81  |    8.154 |
|   2023 |         9 |      6.063 |    6.262 |
|   2024 |         9 |      5.644 |    6.712 |
|   2025 |         9 |      7.969 |    8.403 |

## All trades by year

|   year |   n |   mean_r |
|-------:|----:|---------:|
|   2020 |  96 |    0     |
|   2021 | 102 |    0.602 |
|   2022 | 102 |    1.137 |
|   2023 | 117 |    0.222 |
|   2024 | 119 |    0.051 |
|   2025 | 103 |    0.242 |

## Top decile, 2022 vs other years (medians)

|                         |   top10_2022 |   top10_other |   all_2022 |   all_other |
|:------------------------|-------------:|--------------:|-----------:|------------:|
| atr14_pips              |       19.099 |        15.226 |     19.726 |      16.595 |
| atr_pctile              |        0.824 |         0.565 |      0.879 |       0.623 |
| her24                   |        0.285 |         0.209 |      0.257 |       0.237 |
| consec_higher_high_days |        2     |         0     |      0     |       0     |
| close_above_pdh_pips    |        2.3   |         0.8   |      3.35  |       0.1   |
| sig_close_loc           |        0.748 |         0.699 |      0.769 |       0.724 |
| ret_5d_pips             |      236.8   |       105.7   |     80.4   |      50.3   |
| ema20_dist_pips         |       32.542 |        23.108 |     35.263 |      27.088 |
| mfe_r                   |       10.793 |         9.27  |      1.455 |       0.968 |
| time_to_2r_bars         |        4     |         4     |      4     |       4     |

## Exit reason x outcome

| reason   |   n |   mean_r |   median_mfe |
|:---------|----:|---------:|-------------:|
| stop     | 619 |    0.116 |        0.935 |
| time     |  20 |    8.117 |        7.838 |

## FINDINGS (descriptive; nothing here filters 001)

1. RUNNERS ARE MADE BY MULTI-DAY CONTEXT, NOT BAR SHAPE.
   The top net-R decile (64 trades) shows prior-1d return median +97.9 pips
   vs +29.9 for the rest (Spearman rho +0.41, the only strong pre-entry
   correlate); prior 3d/5d medians are ~2x the rest. Signal-bar features
   (close location, body, range/ATR, ATR level, distance above PDH) barely
   separate (|rho| <= 0.08).
2. CONTRACTION -> EXPANSION. Runners' prior-day range is NARROWER
   (median 72.6 vs 85.7 pips, rho -0.085): the break fires after a quieter
   prior day.
3. 2022 IS A REGIME, NOT A DIFFERENT MECHANISM. 2022 runners sit at the
   0.82 ATR percentile vs 0.56 in other years, follow +237-pip 5d moves, and
   start from 2 consecutive higher-high days (vs 0 elsewhere). High-vol
   trending regime amplified the SAME mechanism.
4. RUNNERS EXIST EVERY YEAR (7-17, median 5.2-8.0R). 2024/2025 weakness is
   NOT a missing-runner problem (9 runners each): the drag is the ~90%
   ordinary trades (2024 mean R of all trades = +0.05).
5. ASIA-HOUR BREAKS SCORE BEST (mean +0.46R, n=327) vs Overlap +0.19R;
   medians are -1R everywhere (most trades are stop-outs in all sessions).
6. LIFECYCLE (understanding only): 64% of trades touch +0.5R, 49% touch
   +1R, 35% touch +2R. Touching +1R weakly predicts continuation (57% end
   positive). Winners' median MAE is -0.48R vs -1.31R for losers: genuine
   runs go almost nowhere adverse first. Time exits are rare (20) but huge
   (+8.1R mean); the 3-ATR trail is what turns runners into ~9R MFE trades.
7. LAB IMPLICATION. The edge is trend-run capture, not entry timing:
   Phase B (pyramiding) and Phase D (exit) attack the mechanism directly;
   Phase C (entry) fights the weak part of the trade population. The strong
   prior-1d-momentum observation above is NOT preregistered as a filter and
   is NOT used here (protocol section 26: would need a separate authorized
   hypothesis).

