"""Numbers the dashboard needs, computed off the SQLite store."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from .catalog import CATEGORIES, CATEGORY_ORDER
from .db import Database
from .market import BASELINE_DATE

BASELINE_TS = f"{BASELINE_DATE.isoformat()}T00:00:00+00:00"


def pct(new: Optional[float], old: Optional[float]) -> Optional[float]:
    if not new or not old:
        return None
    return (new - old) / old * 100.0


@dataclass
class ProductStat:
    id: int
    sku: str
    name: str
    category: str
    brand: str
    capacity_gb: Optional[int]
    form_factor: str
    interface: str
    watched: bool
    baseline: float
    current: Optional[float]
    updated: Optional[datetime]
    since_surge: Optional[float]     # % vs first recorded price
    week: Optional[float]            # % vs 7 days ago
    month: Optional[float]           # % vs 30 days ago
    peak: Optional[float]
    trough: Optional[float]

    @property
    def per_gb(self) -> Optional[float]:
        if self.current and self.capacity_gb:
            return self.current / self.capacity_gb
        return None


@dataclass
class CategoryStat:
    key: str
    label: str
    colour: str
    blurb: str
    count: int
    average: Optional[float]
    lowest: Optional[float]
    lowest_name: str
    since_surge: Optional[float]
    week: Optional[float]
    index_series: List[Tuple[str, float]]


def _ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def product_stats(db: Database, category: Optional[str] = None,
                  watched_only: bool = False) -> List[ProductStat]:
    rows = db.products(category=category, watched_only=watched_only)
    latest = db.latest_map()
    base = db.baseline_map(BASELINE_TS)
    week_ref = db.baseline_map(_ago(7))
    month_ref = db.baseline_map(_ago(30))

    ranges = {
        int(r["pid"]): (float(r["lo"]), float(r["hi"]))
        for r in db.conn.execute(
            "SELECT product_id pid, MIN(price) lo, MAX(price) hi FROM prices GROUP BY product_id"
        )
    }

    stats: List[ProductStat] = []
    for row in rows:
        pid = int(row["id"])
        ts, price = latest.get(pid, (None, None))
        lo, hi = ranges.get(pid, (None, None))
        stats.append(ProductStat(
            id=pid,
            sku=row["sku"],
            name=row["name"],
            category=row["category"],
            brand=row["brand"],
            capacity_gb=row["capacity_gb"],
            form_factor=row["form_factor"] or "",
            interface=row["interface"] or "",
            watched=bool(row["watched"]),
            baseline=float(row["baseline"]),
            current=price,
            updated=ts,
            since_surge=pct(price, base.get(pid, row["baseline"])),
            week=pct(price, week_ref.get(pid)),
            month=pct(price, month_ref.get(pid)),
            peak=hi,
            trough=lo,
        ))
    return stats


def category_stats(db: Database) -> List[CategoryStat]:
    out: List[CategoryStat] = []
    for key in CATEGORY_ORDER:
        meta = CATEGORIES[key]
        stats = [s for s in product_stats(db, category=key) if s.current]
        if stats:
            cheapest = min(stats, key=lambda s: s.current or 0)
            surge = [s.since_surge for s in stats if s.since_surge is not None]
            week = [s.week for s in stats if s.week is not None]
            out.append(CategoryStat(
                key=key, label=meta["label"], colour=meta["colour"], blurb=meta["blurb"],
                count=len(stats),
                average=sum(s.current for s in stats) / len(stats),
                lowest=cheapest.current,
                lowest_name=cheapest.name,
                since_surge=sum(surge) / len(surge) if surge else None,
                week=sum(week) / len(week) if week else None,
                index_series=db.category_index(key),
            ))
        else:
            out.append(CategoryStat(
                key=key, label=meta["label"], colour=meta["colour"], blurb=meta["blurb"],
                count=0, average=None, lowest=None, lowest_name="",
                since_surge=None, week=None, index_series=[],
            ))
    return out


def movers(db: Database, days: int = 7, limit: int = 8) -> List[Tuple[ProductStat, float]]:
    """Products whose price moved most over the window, biggest change first."""
    ref = db.baseline_map(_ago(days))
    latest = db.latest_map()
    scored: List[Tuple[ProductStat, float]] = []
    for stat in product_stats(db):
        old = ref.get(stat.id)
        new = latest.get(stat.id, (None, None))[1]
        change = pct(new, old)
        if change is not None and abs(change) >= 0.05:
            scored.append((stat, change))
    scored.sort(key=lambda item: abs(item[1]), reverse=True)
    return scored[:limit]


def portfolio_summary(db: Database) -> Dict[str, Optional[float]]:
    """What a mid-range build's memory and storage bill has done since the baseline."""
    stats = {s.sku: s for s in product_stats(db)}
    basket = ["ram-ddr5-32-6000c30", "nvme-sn850x-2tb", "gpu-rtx5070"]
    then = sum(stats[s].baseline for s in basket if s in stats)
    now = sum(stats[s].current or 0 for s in basket if s in stats)
    return {"then": then or None, "now": now or None, "change": pct(now, then)}
