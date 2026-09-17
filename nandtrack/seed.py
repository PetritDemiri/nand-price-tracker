"""First-run setup: load the catalogue and backfill history to today."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Callable, Optional

from .catalog import CATALOG, DEFAULT_WATCHLIST
from .db import Database
from .market import BASELINE_DATE, daily_points

MODELLED = "modelled"


def ensure_catalog(db: Database) -> None:
    for product in CATALOG:
        db.upsert_product(product)
    watch = set(DEFAULT_WATCHLIST)
    for row in db.products():
        if row["sku"] in watch and not row["watched"]:
            db.set_watched(int(row["id"]), True)


def backfill(db: Database, progress: Optional[Callable[[int, int], None]] = None) -> int:
    """Fill every gap between the baseline date and today. Safe to re-run."""
    ensure_catalog(db)
    today = datetime.now(timezone.utc).date()
    rows = db.products()
    written = 0
    for i, row in enumerate(rows, start=1):
        pid = int(row["id"])
        product = {
            "sku": row["sku"], "category": row["category"],
            "baseline": row["baseline"], "surge_scale": row["surge_scale"],
        }
        last = db.conn.execute(
            "SELECT MAX(ts) m FROM prices WHERE product_id=? AND source=?", (pid, MODELLED)
        ).fetchone()["m"]
        start = BASELINE_DATE
        if last:
            start = date.fromisoformat(last[:10]) + timedelta(days=1)
        if start <= today:
            points = daily_points(product, start, today)
            written += db.insert_prices(
                [(pid, ts, price, MODELLED) for ts, price in points]
            )
        if progress:
            progress(i, len(rows))
    db.set_meta("last_backfill", datetime.now(timezone.utc).isoformat())
    return written


def is_seeded(db: Database) -> bool:
    return db.product_count() > 0 and db.price_count() > 0
