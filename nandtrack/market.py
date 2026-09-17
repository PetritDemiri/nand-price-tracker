"""The price curves behind the backfilled history.

NANDTrack ships with a modelled reconstruction of the memory shortage rather
than scraped retailer archives, because no free public API serves a year of
per-SKU retail history. The curves below are anchored to published figures so
the shape and the magnitude are right even though an individual day is not a
receipt:

  * NAND contract prices rose 33-38% in Q4 2025, 85-90% in Q1 2026 and a further
    70-75% in Q2 2026 (TrendForce), cumulatively about 4.2-4.5x over three
    quarters, decelerating to +10-15% in Q3 2026.
  * Conventional DRAM contract prices rose about 90-95% QoQ in Q1 2026 and
    58-63% in Q2 2026, then +13-18% in Q3 2026 (TrendForce).
  * Retail checkpoints: a 32GB DDR5-6000 CL30 kit went from roughly EUR 70-90 in
    late 2025 to about EUR 127 by December and EUR 282-309 by Q1/April 2026; a
    1TB entry Gen4 NVMe drive went from about EUR 50 to EUR 140-250 over the
    same window; DDR4 32GB kits landed at EUR 150-210.
  * GPUs were insulated until fixed memory contracts expired, then took three
    2026 hikes (January +10-15%, a May round aimed at the flagship, and a
    July/August round of +20-30%). RTX 5090 street pricing went from a ~2,000
    launch price to 4,300 in June 2026 and past 5,000 by September; RTX 5080
    from 1,199 to about 1,595; RX 9070 XT from 599 to about 1,037.

Everything written by this module is tagged with the source name "modelled" in
the database, and the UI labels it as such. Live points fetched later carry the
name of the retailer they came from, so the two never get confused.
"""

from __future__ import annotations

import hashlib
import math
from datetime import date, datetime, time, timedelta, timezone
from typing import Dict, List, Sequence, Tuple

BASELINE_DATE = date(2025, 9, 1)

# (date, index) with the baseline day at 1.00. Linear interpolation in log space
# between anchors keeps month-to-month growth smooth instead of stair-stepped.
ANCHORS: Dict[str, List[Tuple[date, float]]] = {
    "ram": [
        (date(2025, 9, 1), 1.00),
        (date(2025, 10, 1), 1.04),
        (date(2025, 10, 20), 1.12),
        (date(2025, 11, 15), 1.26),
        (date(2025, 12, 10), 1.45),
        (date(2026, 1, 15), 1.95),
        (date(2026, 2, 15), 2.35),
        (date(2026, 3, 15), 2.85),
        (date(2026, 4, 10), 3.35),
        (date(2026, 5, 15), 3.90),
        (date(2026, 6, 20), 4.25),
        (date(2026, 8, 1), 4.55),
        (date(2026, 9, 15), 4.70),
        (date(2027, 6, 30), 5.10),   # tail so the curve keeps running
    ],
    "nvme_ssd": [
        (date(2025, 9, 1), 1.00),
        (date(2025, 10, 1), 1.03),
        (date(2025, 11, 10), 1.22),
        (date(2025, 12, 15), 1.55),
        (date(2026, 1, 20), 1.90),
        (date(2026, 2, 20), 2.40),
        (date(2026, 3, 20), 2.85),
        (date(2026, 4, 15), 3.20),
        (date(2026, 5, 20), 3.65),
        (date(2026, 6, 30), 4.00),
        (date(2026, 8, 1), 4.25),
        (date(2026, 9, 15), 4.40),
        (date(2027, 6, 30), 4.85),
    ],
    "sata_ssd": [
        (date(2025, 9, 1), 1.00),
        (date(2025, 10, 5), 1.02),
        (date(2025, 11, 15), 1.18),
        (date(2025, 12, 20), 1.48),
        (date(2026, 1, 25), 1.82),
        (date(2026, 2, 25), 2.25),
        (date(2026, 3, 25), 2.70),
        (date(2026, 4, 20), 3.05),
        (date(2026, 5, 25), 3.45),
        (date(2026, 7, 5), 3.80),
        (date(2026, 8, 10), 4.00),
        (date(2026, 9, 15), 4.10),
        (date(2027, 6, 30), 4.45),
    ],
    "gpu": [
        (date(2025, 9, 1), 1.00),
        (date(2025, 11, 1), 1.01),
        (date(2025, 12, 20), 1.03),   # fixed memory contracts still holding
        (date(2026, 1, 31), 1.15),    # first hike
        (date(2026, 3, 1), 1.21),
        (date(2026, 4, 15), 1.26),
        (date(2026, 5, 20), 1.34),    # flagship-focused round
        (date(2026, 6, 20), 1.46),
        (date(2026, 8, 5), 1.68),     # third hike, +20-30% across the stack
        (date(2026, 9, 15), 1.80),
        (date(2027, 6, 30), 2.05),
    ],
}

# Short-lived retail events: (start, days, depth). Depth is multiplicative.
PROMOS: Dict[str, List[Tuple[date, int, float]]] = {
    "ram": [(date(2026, 3, 5), 9, 0.93), (date(2026, 7, 12), 6, 0.96)],
    "nvme_ssd": [(date(2025, 11, 28), 5, 0.94), (date(2026, 3, 8), 7, 0.95)],
    "sata_ssd": [(date(2025, 11, 28), 5, 0.93), (date(2026, 6, 1), 5, 0.96)],
    "gpu": [(date(2026, 2, 10), 8, 0.97)],
}


def _interp(anchors: Sequence[Tuple[date, float]], day: date) -> float:
    if day <= anchors[0][0]:
        return anchors[0][1]
    if day >= anchors[-1][0]:
        return anchors[-1][1]
    for (d0, v0), (d1, v1) in zip(anchors, anchors[1:]):
        if d0 <= day <= d1:
            span = (d1 - d0).days or 1
            t = (day - d0).days / span
            # geometric interpolation - price series compound, they don't add
            return v0 * (v1 / v0) ** t
    return anchors[-1][1]


def category_index(category: str, day: date) -> float:
    """Category-wide multiplier against the 1 Sep 2025 baseline."""
    return _interp(ANCHORS.get(category, ANCHORS["nvme_ssd"]), day)


def _promo_factor(category: str, day: date) -> float:
    factor = 1.0
    for start, days, depth in PROMOS.get(category, []):
        if start <= day < start + timedelta(days=days):
            factor *= depth
    return factor


def _seeded(sku: str, day: date, salt: str = "") -> float:
    """Deterministic pseudo-random in [0,1) - same SKU and day, same value."""
    h = hashlib.sha256(f"{sku}|{day.isoformat()}|{salt}".encode()).digest()
    return int.from_bytes(h[:6], "big") / float(1 << 48)


def _noise(sku: str, day: date) -> float:
    """Slow-moving retailer-specific wobble, roughly +-2.5%."""
    a = _seeded(sku, day, "a")
    b = _seeded(sku, day - timedelta(days=1), "a")
    c = _seeded(sku, day - timedelta(days=2), "a")
    smooth = (0.5 * a + 0.3 * b + 0.2 * c) - 0.5   # in [-0.5, 0.5]
    return 1.0 + smooth * 0.05


def _retail_round(value: float) -> float:
    """Retailers price to .99 / .95, and round harder as numbers get bigger."""
    if value < 100:
        return math.floor(value) + 0.99
    if value < 1000:
        return round(value / 5.0) * 5.0 - 0.01
    return round(value / 10.0) * 10.0 - 0.01


def price_for(product: dict, day: date) -> float:
    """Modelled cheapest street price for one SKU on one day."""
    idx = category_index(product["category"], day)
    scaled = 1.0 + (idx - 1.0) * float(product.get("surge_scale", 1.0))
    raw = float(product["baseline"]) * scaled
    raw *= _promo_factor(product["category"], day)
    raw *= _noise(product["sku"], day)
    return _retail_round(max(raw, 1.0))


def intraday_price(product: dict, when: datetime) -> float:
    """A live-looking quote: the day's modelled price plus a small tick."""
    day = when.date()
    base = price_for(product, day)
    slot = when.hour * 6 + when.minute // 10
    wobble = (_seeded(product["sku"], day, f"h{slot}") - 0.5) * 0.012
    return _retail_round(base * (1.0 + wobble))


def daily_points(product: dict, start: date, end: date) -> List[Tuple[str, float]]:
    """(ISO timestamp, price) for every day in [start, end], stamped at 12:00 UTC."""
    out: List[Tuple[str, float]] = []
    day = start
    while day <= end:
        ts = datetime.combine(day, time(12, 0), tzinfo=timezone.utc).isoformat()
        out.append((ts, price_for(product, day)))
        day += timedelta(days=1)
    return out
