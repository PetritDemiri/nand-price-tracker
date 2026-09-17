"""Where live prices come from.

Two sources ship with the app:

ModelledSource   Always available. Continues the shipped curve to the current
                 minute so the dashboard visibly ticks without any network.

HttpSource       Reads sources.json from the data directory and scrapes real
                 retailer pages you nominate. Nothing is hard-coded to a
                 particular shop, because the cheapest place to buy a 2TB SN850X
                 in Pristina is not the cheapest one in Portland - and most
                 large retailers forbid scraping in their terms of use, so this
                 has to be your call, not the app's.

sources.json looks like:

    {
      "retailer": "gjirafa50",
      "timeout": 12,
      "currency": "EUR",
      "products": {
        "nvme-sn850x-2tb": {
          "url": "https://example.com/wd-black-sn850x-2tb",
          "selector": "span.price",
          "regex": "([0-9][0-9.,]*)"
        }
      }
    }

Write a class with the same three methods to add your own - an affiliate API, a
price-comparison feed, a CSV your colleague maintains.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from .market import intraday_price
from .paths import sources_path

PriceQuote = Tuple[int, str, float, str]   # product_id, iso ts, price, source

_NUMBER = re.compile(r"(\d[\d\s.,]*)")


def _to_float(text: str) -> Optional[float]:
    """Parse 1.299,00 / 1,299.00 / 1299 into a float."""
    match = _NUMBER.search(text.replace("\xa0", " "))
    if not match:
        return None
    raw = match.group(1).strip().replace(" ", "")
    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".") if raw.rfind(",") > raw.rfind(".") \
            else raw.replace(",", "")
    elif "," in raw:
        head, _, tail = raw.rpartition(",")
        raw = f"{head.replace(',', '')}.{tail}" if len(tail) in (1, 2) else raw.replace(",", "")
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if 0 < value < 100000 else None


class PriceSource:
    name = "source"

    def available(self) -> bool:
        return True

    def fetch(self, products: List[dict]) -> List[PriceQuote]:
        raise NotImplementedError

    def describe(self) -> str:
        return self.name


class ModelledSource(PriceSource):
    """Offline ticker that follows the shipped surge curve."""

    name = "modelled"

    def fetch(self, products: List[dict]) -> List[PriceQuote]:
        now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        stamp = now.isoformat()
        quotes: List[PriceQuote] = []
        for p in products:
            quotes.append((p["id"], stamp, intraday_price(p, now), self.name))
        return quotes

    def describe(self) -> str:
        return "Modelled curve (offline)"


class HttpSource(PriceSource):
    """Scrapes retailer pages listed in sources.json."""

    name = "retailer"

    def __init__(self) -> None:
        self.config: Dict = {}
        self.error: Optional[str] = None
        self.reload()

    def reload(self) -> None:
        path = sources_path()
        if not path.exists():
            self.config = {}
            self.error = "sources.json not found"
            return
        try:
            self.config = json.loads(path.read_text(encoding="utf-8"))
            self.name = self.config.get("retailer", "retailer")
            self.error = None
        except (OSError, ValueError) as exc:
            self.config = {}
            self.error = f"sources.json is not valid JSON: {exc}"

    def available(self) -> bool:
        if not self.config.get("products"):
            return False
        try:
            import requests  # noqa: F401
        except ImportError:
            self.error = "the requests package is not installed"
            return False
        return True

    def _extract(self, html: str, rule: dict) -> Optional[float]:
        chunk = html
        selector = rule.get("selector")
        if selector:
            try:
                from bs4 import BeautifulSoup
                node = BeautifulSoup(html, "html.parser").select_one(selector)
                if node is None:
                    return None
                chunk = node.get_text(" ", strip=True)
            except ImportError:
                self.error = "install beautifulsoup4 to use CSS selectors"
                return None
        pattern = rule.get("regex")
        if pattern:
            match = re.search(pattern, chunk, re.S)
            if not match:
                return None
            chunk = match.group(match.lastindex or 0)
        return _to_float(chunk)

    def fetch(self, products: List[dict]) -> List[PriceQuote]:
        import requests

        rules = self.config.get("products", {})
        timeout = float(self.config.get("timeout", 12))
        headers = {"User-Agent": self.config.get(
            "user_agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) NANDTrack/1.0",
        )}
        stamp = datetime.now(timezone.utc).replace(second=0, microsecond=0).isoformat()
        quotes: List[PriceQuote] = []
        failures = 0
        for p in products:
            rule = rules.get(p["sku"])
            if not rule or not rule.get("url"):
                continue
            try:
                response = requests.get(rule["url"], headers=headers, timeout=timeout)
                response.raise_for_status()
                price = self._extract(response.text, rule)
            except Exception:                      # network, DNS, TLS, 403, ...
                failures += 1
                continue
            if price is not None:
                quotes.append((p["id"], stamp, price, self.name))
            else:
                failures += 1
        self.error = f"{failures} page(s) could not be read" if failures else None
        return quotes

    def describe(self) -> str:
        return f"{self.name} (live)"


def build_sources(use_live: bool) -> List[PriceSource]:
    sources: List[PriceSource] = [ModelledSource()]
    if use_live:
        http = HttpSource()
        if http.available():
            sources.insert(0, http)
    return sources
