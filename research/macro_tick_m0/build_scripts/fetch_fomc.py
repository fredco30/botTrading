#!/usr/bin/env python3
"""MACRO_TICK_M0: official FOMC decision calendar 2010-2018.

Provenance rules (mission-critical):
  * Meeting dates come from the Fed's historical FOMC pages; a candidate page
    is kept ONLY if its <title> is an FOMC statement page.
  * The EXACT release time is taken only from an official page line
    ("For release at H:MM a.m./p.m. EST/EDT") printed on the statement page
    itself, or on the same-moment implementation-note page
    (monetaryYYYYMMDDb/c.htm) when that page's title identifies it as an
    implementation note (they existed for press-conference meetings from
    March 2013; every meeting from January 2016).
  * Pages with no such line are recorded with release_time_official=None
    (DATE_ONLY). A separate non-official conventional time (12:30 ET for
    2010-2012, 14:00 ET for 2013+) is stored in conventional_time_hhmm for
    tick-alignment validation only. The convention is NEVER presented as an
    official timestamp. (Verified via era Wayback captures: pre-2016 Fed
    statement pages carried no intraday time line.)
  * Target-range values are extracted from the statement text only; nothing
    is guessed.

Output: ../data_raw/fomc_statements.json
"""
import json
import os
import re
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.normpath(os.path.join(HERE, "..", "data_raw"))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0"}

RELEASE_RE = re.compile(
    r"For\s+release\s+at\s+(\d{1,2}):(\d{2})\s*([ap])\.?m\.?\s*(E[SD]T)", re.I)
MONETARY_A_RE = re.compile(r"monetary(\d{8})a\.htm")
FOMC_DATE_RE = re.compile(r"FOMC(\d{8})")
NUM = r"(?:\d+(?:[-\u2011]\d+)?/\d+|\d+)"
RANGE_RE = re.compile(NUM + r"\s+to\s+" + NUM + r"\s+percent")


def fetch(url, tries=4):
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode("utf-8", errors="ignore")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if k == tries - 1:
                raise
        except Exception:
            if k == tries - 1:
                raise
        time.sleep(2 * (k + 1))
    return None


def title_of(html):
    m = re.search(r"<title>([^<]*)</title>", html or "")
    return m.group(1).strip() if m else None


def parse_release_line(html):
    m = RELEASE_RE.search(html)
    if not m:
        return None, None, None
    hh, mm, ap, tz = int(m.group(1)), m.group(2), m.group(3).lower(), m.group(4).upper()
    if ap == "p" and hh != 12:
        hh += 12
    if ap == "a" and hh == 12:
        hh = 0
    return f"{hh:02d}:{mm}", tz, re.sub(r"\s+", " ", m.group(0)).strip()


def norm_num(tok):
    tok = tok.replace("\u2011", "-")
    if "/" in tok:
        whole_s, frac_s = tok.split("/")
        if "-" in whole_s:
            whole, num = whole_s.split("-")
            return float(whole) + float(num) / float(frac_s)
        return float(whole_s) / float(frac_s)
    return float(tok)


def extract_ranges(html):
    text = re.sub(r"<[^>]+>", " ", html)
    text = text.replace("\u2011", "-")
    text = re.sub(r"\s+", " ", text)
    out = []
    for sent in re.split(r"(?<=\.)\s+", text):
        if "federal funds rate" not in sent.lower():
            continue
        for m in RANGE_RE.finditer(sent):
            a, b = m.group(0).split(" to ")
            lo, hi = norm_num(a.strip()), norm_num(b.replace(" percent", "").strip())
            out.append({"low": lo, "high": hi, "sentence": sent.strip()[:300]})
    return out


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    cand = {}
    scheduled = {}
    for year in range(2010, 2019):
        url = f"https://www.federalreserve.gov/monetarypolicy/fomchistorical{year}.htm"
        html = fetch(url)
        dates = set(m.group(1) for m in MONETARY_A_RE.finditer(html))
        dates |= set(m.group(1) for m in FOMC_DATE_RE.finditer(html))
        dates = sorted(d for d in dates
                       if "20100101" <= d <= "20181231")
        cand[year] = dates
        # scheduled meeting decision days = dates with meeting materials
        # (agenda/materials/minutes files) on the year page; unscheduled
        # statements (e.g. 2010-05-09 swap lines) have none.
        mat = set(m.group(1) for m in re.finditer(
            r"FOMC(\d{8})(?:Agenda|material|minutes|gbpt|bbgb|SEP)", html))
        scheduled[year] = mat
        print(year, "candidates:", len(dates), "scheduled:", len(mat))
        time.sleep(1.0)

    records = []
    for year in range(2010, 2019):
        for yyyymmdd in cand[year]:
            iso = f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:]}"
            base = ("https://www.federalreserve.gov/newsevents/pressreleases/"
                    f"monetary{yyyymmdd}")
            a_html = fetch(base + "a.htm")
            title = title_of(a_html)
            if a_html is None or not title or "FOMC statement" not in title:
                continue  # not a monetary policy statement page
            kind = ("scheduled" if yyyymmdd in scheduled[year]
                    else "unscheduled_intermeeting")
            hhmm, tz, raw = parse_release_line(a_html)
            src = "statement_page"
            # Sibling-package pages (projections/goals/implementation note)
            # only corroborate the statement time in the 2:00 p.m. era
            # (2013+). In 2011-2012 the statements were released at 12:30
            # p.m. while sibling pages were released separately at ~14:00,
            # so their time lines do NOT describe the statement.
            if hhmm is None and iso >= "2013-01-01":
                for suf in ("b", "c"):
                    b_html = fetch(base + f"{suf}.htm")
                    b_title = title_of(b_html or "")
                    if b_html is None:
                        continue
                    low = b_title.lower()
                    if ("implementation note" in low
                            or "economic projections" in low
                            or "longer-run goals" in low):
                        hhmm_b, tz_b, raw_b = parse_release_line(b_html)
                        if hhmm_b is not None:
                            hhmm, tz, raw = hhmm_b, tz_b, raw_b
                            src = f"same_release_package_page_{suf}"
                            break
            conventional = "12:30" if iso < "2013-01-01" else "14:00"
            records.append({
                "date": iso,
                "kind": kind,
                "statement_url": base + "a.htm",
                "title": title,
                "release_time_hhmm_official": hhmm,
                "release_tz_label": tz,
                "release_line_raw": raw,
                "release_time_source": src if hhmm else None,
                "conventional_time_hhmm_non_official":
                    None if hhmm else conventional,
                "target_ranges_in_text": extract_ranges(a_html)[:3],
            })
            print(iso, hhmm, tz, src if hhmm else "DATE_ONLY",
                  [(r["low"], r["high"]) for r in records[-1]["target_ranges_in_text"]][:1])
            time.sleep(1.0)

    with open(os.path.join(OUT_DIR, "fomc_statements.json"), "w", encoding="utf-8") as f:
        json.dump(records, f, indent=1, ensure_ascii=False)
    n = len(records)
    n_t = sum(1 for r in records if r["release_time_hhmm_official"])
    print(f"kept {n} FOMC statement events; official time on {n_t}")


if __name__ == "__main__":
    main()
