# MACRO_TICK_M0 — Causal Macro Event Database (EURUSD research)

**Branch:** `research/macro-tick-m0` · **Parent:** `def3a943` (MTF-M1 PR #30) · **DO NOT MERGE**

Discovery range: **2010-01-01 (inclusive) → 2019-01-01 (exclusive)**. No 2019+ data was
queried, fetched, or stored. This mission builds a **data/provenance artifact only**:
no strategy, no entries/exits, no returns, no PnL, no optimization — the event/tick
alignment below is **timestamp validation only**.

## 1. What was built

One row per official macro release (289 events):

| Family | Events | Coverage |
|---|---|---|
| NFP (Employment Situation) | 108 | every official release 2010-2018 |
| CPI (headline CPI-U + core) | 108 | every official release 2010-2018 |
| FOMC statements | 73 | 72 scheduled + 1 unscheduled (2010-05-09 swap lines) |

Dataset: `data/macro_events_2010_2018_aligned.csv` (289 rows, git-safe).
Timestamp + value fields only; tick columns are lag measurements (§8), never returns.

## 2. Sources and provenance

### BLS release dates (primary, official)
Archived news-release indexes (`bls.gov/bls/news-release/empsit.htm`, `.../cpi.htm`)
give every actual release date with its archive URL. 108 + 108 events; captures the
shutdown-delayed releases (Employment Situation for September 2013 released
**2013-10-22**, CPI September 2013 released **2013-10-30**).
Manifest: `source_manifests/bls_empsit_archive_index.json`, `bls_cpi_archive_index.json`.

### BLS release times (per-entry, official)
Yearly schedule pages `bls.gov/schedule/{YEAR}/home.htm` list per-entry times
("08:30 AM"; page header: "All times on calendar are Eastern Time"). Every one of the
216 BLS events matched a per-entry scheduled time — including the updated 2013 page
entries for the delayed October releases. No family-default fallback time was needed.
Manifest: `bls_schedule_entries_2010_2018.json` (raw page probes: `bls_schedule_pages_probe.json`).

### ALFRED vintages (first-release values)
Values known at release time come from ALFRED realtime vintages, **not** today's
revised series:

* `PAYEMS` (total nonfarm payrolls, thousands, SA) — first print of the reference
  month = vintage at the release date; previous month's value as known immediately
  before the release = vintage at the previous release date; first revision = vintage
  at the next release date (with its availability date).
* `CPIAUCSL` (headline index, SA) and `CPILFESL` (core index, SA) — same scheme.

ALFRED endpoint used (discovered 2026-09-13; the plain `fredgraph.csv`/API routes are
bot-gated, so the CSVs were fetched in-browser from the ALFRED origin):
`https://alfred.stlouisfed.org/graph/alfredgraph.csv?id=<SERIES>&vintage_date=<YYYY-MM-DD>&cosd=2008-01-01&coed=2019-01-01`
Every returned column header was validated to equal the requested vintage date
(327/327 across the three series). Raw stores: `data_raw/alfred_vintages/` (gitignored),
compact extracts in the dataset.

**Vintage → event causality mapping (mission §7):** ALFRED vintage (realtime_start)
dates for these series equal the BLS release dates; a value in vintage *D* was first
public on date *D* at the official release time. Daily vintage granularity cannot
prove an intraday instant, so every vintage-sourced value carries
`value_time_precision = DATE_ONLY` while the event timestamp itself is exact.
`value_available_time_utc` is set to the release instant; the builder hard-fails any
value availability predating its release (tested).

### FOMC (Federal Reserve, official)
Meeting dates + statement pages from `federalreserve.gov/monetarypolicy/fomchistorical{Y}.htm`.

* **2016-2018 (24 meetings):** exact release times from the statement page itself
  ("For release at 2:00 p.m. EST/EDT").
* **2013-03 → 2015-12 (11 meetings):** the statement pages of that era carry no
  intraday time; the official **same-release-package** page (SEP projections /
  longer-run goals / implementation note) carries "For release at 2:00 p.m.".
  Grade: `OFFICIAL_SAME_RELEASE_PACKAGE_PAGE`.
* **2010-2012 + 2013-01/05/07/10/11 + 2015-06 (37 events):** official pages show the
  release **date only**. Verified also against era Internet Archive captures
  (2011-01-29 capture of the Jan 2011 statement: "For immediate release"; 2013, 2014,
  2015 captures: date-only). This is the explicit documented blocker: the Fed's CMS
  printed no intraday time on statement pages before 2016. These rows carry
  `timestamp_grade = DATE_ONLY_OFFICIAL_TIME_UNAVAILABLE` and a **separate non-official
  conventional time** (12:30 ET 2010-2012, 14:00 ET 2013+) in
  `timestamp_provenance`, used only for tick-alignment validation — never presented
  as official.
* **Unscheduled:** 2010-05-09 joint central-bank swap-line statement
  ("FOMC statement:" title, no meeting materials on the year page) — classified
  `unscheduled_intermeeting`, exact official time **21:15 EDT**. It is kept out of the
  scheduled chain, not silently merged.
* **Rate decisions:** target ranges parsed from statement text only (with Fed-page
  non-breaking-hyphen normalization). 71/72 scheduled meetings have a resolved
  `rate_change_bp` (2010-01-27 is `DATA_UNAVAILABLE` for the *change* because the
  predecessor meeting is outside the discovery window; its level is known).
  Independent cross-check: all 9 in-window hikes match ALFRED `DFEDTARU` effective
  dates within 2 days, 0 mismatches.
  Manifest: `source_manifests/fomc_statements.json`, `dfedtaru_current.csv`.

## 3. Timezone handling (mission §6)

All conversions use `zoneinfo` `America/New_York` (real DST rules, no hard-coded
offsets). Page labels EST/EDT are additionally validated against zoneinfo per date.
Examples from the dataset: 08:30 ET → 13:30Z in January, 12:30Z in June; FOMC
14:00 ET → 19:00Z in summer, 18:00Z after the fall transition. Covered by tests
(EST date, EDT date, spring-forward week, fall-back week, label mismatches).

## 4. Event/tick alignment (mission §8 — timestamps only)

Existing EURUSD tick store (`E:\ResearchData\botTrading\ticks`, monthly parquet,
UTC timestamps; **no tick data copied into git**). For each event: last tick strictly
before the release instant, first tick at or after it, and both lags in ms.

| Metric | Value |
|---|---|
| Events | 289 |
| Aligned (first executable tick ≤ 5 s) | **283 (97.9%)** |
| First tick beyond 5 s | 3 |
| Events inside tick-source data gaps | 3 |
| Median / max aligned post-tick lag | 206 ms / 4,898 ms |

Documented exceptions:
* **Tick-source gap (2018-06):** the source parquet for June 2018 contains only
  2018-06-04 → 2018-06-08, so `MACRO-NFP-201805`, `MACRO-CPI-201805`,
  `MACRO-FOMC-20180613` cannot be aligned. Coverage audit:
  `data/tick_store_month_coverage.csv`.
* **Sparse-feed moments (2010-2012 era):** `MACRO-NFP-201002` (+7.3 s),
  `MACRO-CPI-201003` (+6.0 s), `MACRO-FOMC-20121024` (+7.4 s) — no tick within 5 s
  at release (thin data moments, not missing files; neighbors exist seconds away).

## 5. Pass gate (mission §13)

| Gate | Requirement | Result | Verdict |
|---|---|---|---|
| NFP timestamps | ≥ 95% exact | 100% (108/108) | PASS |
| NFP first-release vintages | ≥ 90% | 100% (108/108) | PASS |
| CPI timestamps | ≥ 95% exact | 100% (108/108) | PASS |
| CPI first-release vintages | ≥ 90% | 100% (108/108 headline, 108/108 core) | PASS |
| FOMC timestamps | ≥ 95% exact **or explicit documented blocker** | 48.6% exact-or-package (36/74 incl. unscheduled); blocker documented (§2) | PASS with documented blocker |
| FOMC rate decisions | — (best effort, no guessing) | 98.6% resolved, cross-checked vs DFEDTARU | PASS |
| Tick alignment | ≥ 95% without unresolved gaps | 97.9% (6 exceptions, all documented) | PASS |

**`MACRO_TICK_M0_PASS`** (FOMC timestamps: documented-blocker clause; values complete).

## 6. Consensus forecast feasibility (mission §10)

**`CONSENSUS_DATA_STATUS = NOT_AVAILABLE_FREE_RELIABLY`** — no consensus values were
ingested. Nothing was fabricated; no today's expectations were applied retrospectively.

| Source | Coverage 2010-2018 | Forecast | Actual | Timestamp | Free/Paid | Terms / practical access | Trust |
|---|---|---|---|---|---|---|---|
| ForexFactory calendar archive | full, event-level | yes (editorial consensus) | yes | yes (epoch dateline) | free pages | scraping/data-reuse restricted by site terms; needs per-page crawl | LOW-MED (undocumented methodology, values unversioned/silently revisable) |
| Investing.com economic calendar | full, event-level | yes | yes | page-level only | free pages | anti-scraping; editorial | LOW-MED |
| Reuters polls (news archive) | NFP/CPI/FOMC previews, uneven | poll median in article text | in article text | article-level | free news | unstructured, incomplete enumeration, editorial corrections | MED for values, LOW for completeness |
| TradingEconomics | partial free, full paid API | yes (paid archive) | yes | paid tier | paid tier | API license | MED |
| Econoday / Action Economics / Bloomberg / LSEG | full | yes, timestamped | yes | exact | **paid license** | commercial licensing | HIGH (professional standard) |
| Philly Fed SPF / Blue Chip | quarterly / monthly | not event-level | n/a | n/a | SPF free | wrong granularity for release-day consensus | HIGH (but unusable here) |

Best free candidate: ForexFactory. Spot-check 2016-01-08: its record shows
`actual 292K / forecast 203K / previous 211K / revision 252K`, dateline
`1452259800` = 2016-01-08T13:30:00Z — exactly the official release instant, and the
actual matches our ALFRED first print. Rejected anyway for the database: forecasts
have no documented survey provenance and are silently revisable (no vintage trail),
and machine extraction conflicts with the site's terms — exactly the "do not scrape
dubious / do not fabricate" bar in the mission. Upgrading consensus later requires a
licensed feed (Econoday/Bloomberg/LSEG tier); the dataset's `event_id` +
`release_timestamp_utc` are designed to join against such a feed without changes.

## 7. Data quality register (mission §9)

* Duplicates: none (dedupe raises by design; 289 unique ids).
* Timezone ambiguity: none (EST/EDT labels validated vs zoneinfo; 0 mismatches).
* Missing source pages: 2 non-meeting Fed candidate pages rejected by title check
  (one 404, one non-FOMC statement); no missing BLS archive pages.
* ALFRED vintage mismatch: 0 of 327 vintages (column-name validated).
* Events during tick-data gaps: 3 (June 2018 source gap, listed above).
* FOMC DATE_ONLY: 37 events (documented blocker, §2).

## 8. Reproduction

```
python -m pytest research/macro_tick_m0/test_macro_tick_m0.py   # 22 synthetic tests
python research/macro_tick_m0/build_scripts/fetch_fomc.py       # refetches Fed pages (network)
python research/macro_tick_m0/build_scripts/build_events.py     # needs data_raw/alfred_vintages + manifests
python research/macro_tick_m0/build_scripts/align_ticks.py      # needs E:\ResearchData\botTrading\ticks
python research/macro_tick_m0/build_scripts/audit_tick_coverage.py
python research/macro_tick_m0/build_scripts/make_report.py
```

BLS manifests and ALFRED vintage stores were fetched through a real-browser session
on 2026-09-13 (BLS rejects plain HTTP clients; the committed manifests are the fetch
evidence; URLs and parameters are documented in §2). Governance: only code, small
CSV/JSON datasets, tests, reports and source manifests are committed; no tick data;
2019+ never accessed; protected OOS untouched; **no strategy research performed**.
