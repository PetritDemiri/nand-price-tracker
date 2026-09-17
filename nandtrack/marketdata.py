"""Where the curve stops being a guess.

The shipped anchors in market.py run to mid-September 2026 because that is as far
as published contract-price reporting went when they were written. Everything
after that was a straight-line guess. This module replaces the guess with a
fetched series.

Two feeds ship:

FredFeed   The US Federal Reserve's FRED service. Free, a free API key, an
           official producer price index, explicitly open for programmatic use.
           Monthly and lagged a couple of weeks, so it will not tick, but it
           keeps running forever without anyone maintaining it.

CsvFeed    Any URL that returns two columns of date,value. Point it at an export
           from a market-intelligence service you subscribe to, a sheet you
           maintain by hand, or anything else you are allowed to read.

The hard part is not fetching. A broad semiconductor price index does not move
4.4x when a DDR5 kit does - it moves a fraction of that. So rather than
substituting the fetched series for the curve, the app measures how the two
moved together over the period where both are known, and uses that relationship
to carry the curve forward. That ratio is `elasticity`, and it is fitted, not
guessed - see fit_elasticity below.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .catalog import CATEGORY_ORDER
from .market import ANCHORS, BASELINE_DATE, category_index

# The last anchor that reflects something somebody actually published. Anything
# after this in ANCHORS is a tail put there so the curve keeps running, and it
# is what a live feed is allowed to overwrite.
LAST_REPORTED = date(2026, 9, 15)

FRED_ENDPOINT = "https://api.stlouisfed.org/fred/series/observations"

# Producer price indices. One broad semiconductor series is the defensible
# default; the settings page lets you put a different id against each category,
# and the Test button reports exactly what FRED says about an id that is wrong.
DEFAULT_FRED_SERIES: Dict[str, str] = {
    "ram": "PCU334413334413",
    "gpu": "PCU334413334413",
    "sata_ssd": "PCU334413334413",
    "nvme_ssd": "PCU334413334413",
}


# --------------------------------------------------------------------------
# feeds
# --------------------------------------------------------------------------
class IndexFeed:
    name = "feed"

    def available(self) -> Tuple[bool, str]:
        return True, ""

    def fetch(self, category: str) -> List[Tuple[str, float]]:
        """[(ISO day, raw index value)] oldest first. Units do not matter."""
        raise NotImplementedError

    def describe(self) -> str:
        return self.name


class FredFeed(IndexFeed):
    name = "fred"

    def __init__(self, api_key: str, series: Optional[Dict[str, str]] = None,
                 timeout: float = 15.0) -> None:
        self.api_key = (api_key or "").strip()
        self.series = dict(DEFAULT_FRED_SERIES)
        self.series.update(series or {})
        self.timeout = timeout
        self.error: Optional[str] = None

    def available(self) -> Tuple[bool, str]:
        if not self.api_key:
            return False, "no FRED API key yet - get a free one at fred.stlouisfed.org"
        try:
            import requests  # noqa: F401
        except ImportError:
            return False, "the requests package is not installed"
        return True, ""

    def fetch(self, category: str) -> List[Tuple[str, float]]:
        import requests

        series_id = self.series.get(category) or DEFAULT_FRED_SERIES["ram"]
        params = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json",
            "observation_start": (BASELINE_DATE - timedelta(days=400)).isoformat(),
        }
        response = requests.get(FRED_ENDPOINT, params=params, timeout=self.timeout)
        if response.status_code >= 400:
            # FRED puts a readable reason in the body, including for a bad id
            detail = ""
            try:
                detail = response.json().get("error_message", "")
            except ValueError:
                detail = response.text[:180]
            raise RuntimeError(f"FRED said: {detail or response.status_code}")
        return parse_fred(response.text)

    def describe(self) -> str:
        return "FRED producer price index"


class CsvFeed(IndexFeed):
    name = "csv"

    def __init__(self, urls: Dict[str, str], timeout: float = 15.0) -> None:
        self.urls = {k: v for k, v in (urls or {}).items() if v}
        self.timeout = timeout

    def available(self) -> Tuple[bool, str]:
        if not self.urls:
            return False, "no CSV address set"
        try:
            import requests  # noqa: F401
        except ImportError:
            return False, "the requests package is not installed"
        return True, ""

    def fetch(self, category: str) -> List[Tuple[str, float]]:
        import requests

        url = self.urls.get(category) or self.urls.get("all")
        if not url:
            return []
        response = requests.get(url, timeout=self.timeout)
        response.raise_for_status()
        return parse_csv(response.text)

    def describe(self) -> str:
        return "CSV feed"


# --------------------------------------------------------------------------
# parsing - kept out of the feed classes so they can be tested without a socket
# --------------------------------------------------------------------------
def parse_fred(body: str) -> List[Tuple[str, float]]:
    payload = json.loads(body)
    out: List[Tuple[str, float]] = []
    for row in payload.get("observations", []):
        raw = row.get("value", ".")
        if raw in (".", "", None):
            continue                      # FRED marks a missing month with a dot
        try:
            out.append((row["date"], float(raw)))
        except (KeyError, ValueError):
            continue
    return out


def parse_csv(body: str) -> List[Tuple[str, float]]:
    out: List[Tuple[str, float]] = []
    reader = csv.reader(io.StringIO(body))
    for row in reader:
        if len(row) < 2:
            continue
        day, value = row[0].strip(), row[1].strip()
        try:
            datetime.strptime(day[:10], "%Y-%m-%d")
            out.append((day[:10], float(value)))
        except ValueError:
            continue                      # header rows and blanks fall out here
    return out


# --------------------------------------------------------------------------
# turning a raw series into a curve extension
# --------------------------------------------------------------------------
def forward_fill(points: Sequence[Tuple[str, float]], start: date,
                 end: date) -> Dict[date, float]:
    """Monthly observations become a daily lookup by carrying each value forward."""
    if not points:
        return {}
    parsed = sorted((date.fromisoformat(d), v) for d, v in points)
    filled: Dict[date, float] = {}
    idx = 0
    current = parsed[0][1]
    day = start
    while day <= end:
        while idx < len(parsed) and parsed[idx][0] <= day:
            current = parsed[idx][1]
            idx += 1
        filled[day] = current
        day += timedelta(days=1)
    return filled


def fit_elasticity(category: str, series: Sequence[Tuple[str, float]],
                   pivot: date = LAST_REPORTED) -> Optional[float]:
    """How far the category moved for each point the outside index moved.

    Measured over the window where both are known, by least squares through the
    origin: a flat external series or one that barely moved gives no signal and
    returns None rather than a wild number.
    """
    if not series:
        return None
    filled = forward_fill(series, BASELINE_DATE, pivot)
    if len(filled) < 60:
        return None
    base_ext = filled.get(BASELINE_DATE)
    if not base_ext:
        return None

    num = den = 0.0
    day = BASELINE_DATE
    while day <= pivot:
        ext = filled.get(day)
        if ext:
            x = ext / base_ext - 1.0
            y = category_index(category, day, dynamic=False) - 1.0
            num += x * y
            den += x * x
        day += timedelta(days=7)
    if den < 1e-9:
        return None
    slope = num / den
    if not (0.05 < slope < 400.0):
        return None
    return slope


def build_extension(category: str, series: Sequence[Tuple[str, float]],
                    until: Optional[date] = None) -> List[Tuple[date, float]]:
    """Daily curve values after the pivot, driven by the fetched series."""
    until = until or (datetime.now(timezone.utc).date() + timedelta(days=30))
    if until <= LAST_REPORTED:
        return []
    elasticity = fit_elasticity(category, series)
    if elasticity is None:
        return []
    filled = forward_fill(series, BASELINE_DATE, until)
    anchor_ext = filled.get(LAST_REPORTED)
    if not anchor_ext:
        return []
    anchor_idx = category_index(category, LAST_REPORTED, dynamic=False)

    out: List[Tuple[date, float]] = []
    day = LAST_REPORTED
    while day <= until:
        ext = filled.get(day)
        if ext:
            move = ext / anchor_ext - 1.0
            value = anchor_idx * (1.0 + elasticity * move)
            out.append((day, max(value, 0.05)))
        day += timedelta(days=1)
    return out


# --------------------------------------------------------------------------
# orchestration
# --------------------------------------------------------------------------
def build_feed(settings) -> Optional[IndexFeed]:
    provider = getattr(settings, "index_provider", "off")
    if provider == "fred":
        return FredFeed(getattr(settings, "fred_api_key", ""),
                        getattr(settings, "fred_series", None))
    if provider == "csv":
        return CsvFeed(getattr(settings, "index_csv_urls", None) or {})
    return None


def refresh(db, settings) -> Tuple[int, str]:
    """Pull every category's series and cache it. Returns (rows, message)."""
    feed = build_feed(settings)
    if feed is None:
        return 0, "market index is switched off"
    ok, why = feed.available()
    if not ok:
        return 0, why

    written = 0
    problems: List[str] = []
    for category in CATEGORY_ORDER:
        try:
            points = feed.fetch(category)
        except Exception as exc:                        # noqa: BLE001
            problems.append(str(exc))
            continue
        if points:
            written += db.store_index(category, feed.name, points)
    if written:
        db.set_meta("index_refreshed", datetime.now(timezone.utc).isoformat())
        db.set_meta("index_feed", feed.name)
    if problems:
        return written, problems[0]
    return written, "" if written else "the feed returned nothing"


def load_into_curve(db) -> Dict[str, str]:
    """Apply whatever is cached to market.py, and report what happened."""
    from . import market

    report: Dict[str, str] = {}
    feeds = db.index_feeds()
    if not feeds:
        market.set_extension({})
        return report
    feed = db.get_meta("index_feed") or feeds[0]

    extension: Dict[str, List[Tuple[date, float]]] = {}
    for category in CATEGORY_ORDER:
        series = db.index_series(category, feed)
        if not series:
            continue
        elasticity = fit_elasticity(category, series)
        points = build_extension(category, series)
        if points:
            extension[category] = points
            report[category] = (f"{len(points)} days from {feed}, "
                                f"moving {elasticity:.1f}x the index")
    market.set_extension(extension)
    return report
