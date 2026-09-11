#!/usr/bin/env python3
"""Build the official FOMC decision calendar (2010-2026) with the EXACT
release timestamps parsed from each statement press release page
("For release at H:MM a.m./p.m. EST/EDT").

Sources (official, no key):
  * https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm  (2021+)
  * https://www.federalreserve.gov/monetarypolicy/fomchistorical{Y}.htm (2010-2020)

Output: data_raw/official/fomc_decisions.json
  [{date: 'YYYY-MM-DD', release_time: 'HH:MM', tz: 'EST|EDT', source_url}]
The parsed release time is authoritative (no schedule guessing).
Pages with a missing time line are flagged release_time=null (dropped from
intraday windows by the consumer; still usable for next-day studies).
"""
import json
import os
import re
import time
import urllib.request

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "..", "..", "data_raw", "official")
UA = {"User-Agent": "Mozilla/5.0 (research)"}


def fetch(url, tries=3):
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=45) as r:
                return r.read().decode("utf-8", errors="ignore")
        except Exception:
            if k == tries - 1:
                raise
            time.sleep(2)


def statement_urls_from_calendars(html):
    """2021+ page: statement press-release links monetaryYYYYMMDDa.htm."""
    urls = set(re.findall(
        r'href="(/newsevents/pressreleases/monetary(\d{8})a?)\.htm"', html))
    return sorted(urls)


def statement_urls_from_historical(html):
    """2010-2020 pages: statement links in the 'Meeting, statement' blocks."""
    urls = set(re.findall(
        r'href="(/newsevents/pressreleases/monetary(\d{8})a)\.htm"', html))
    return sorted(urls)


RELEASE_RE = re.compile(
    r"For\s+release\s+at\s+(\d{1,2}):(\d{2})\s*([ap]\.m\.)\s*(E[SD]T)", re.I)


def parse_release_time(html):
    m = RELEASE_RE.search(html)
    if not m:
        return None, None
    hh, mm, ampm, tz = m.group(1), m.group(2), m.group(3).lower(), m.group(4)
    hh = int(hh)
    if ampm == "p.m." and hh != 12:
        hh += 12
    if ampm == "a.m." and hh == 12:
        hh = 0
    return f"{hh:02d}:{mm}", tz


def main():
    events = {}
    pages = ["https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"]
    pages += [f"https://www.federalreserve.gov/monetarypolicy/fomchistorical{y}.htm"
              for y in range(2010, 2021)]
    for page in pages:
        html = fetch(page)
        for path, yyyymmdd in statement_urls_from_calendars(html) + \
                statement_urls_from_historical(html):
            date = f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:]}"
            if date in events:
                continue
            events[date] = {"url": "https://www.federalreserve.gov" + path + ".htm"}
        print(page.rsplit("/", 1)[-1], "->", len(events), "statements so far")

    out = []
    for date in sorted(events):
        url = events[date]["url"]
        try:
            html = fetch(url)
            t, tz = parse_release_time(html)
        except Exception as e:
            t, tz = None, None
            print("FAIL", url, str(e)[:60])
        out.append({"date": date, "release_time": t, "tz": tz, "url": url})
        time.sleep(0.4)
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "fomc_decisions.json"), "w") as f:
        json.dump(out, f, indent=1)
    ok = sum(1 for e in out if e["release_time"])
    print(f"WROTE {len(out)} FOMC decisions ({ok} with exact release time)")
    years = sorted({e["date"][:4] for e in out})
    print("years:", years[0], "->", years[-1])


if __name__ == "__main__":
    main()
