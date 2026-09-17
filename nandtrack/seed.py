"""First-run setup: load the catalogue and backfill history to today."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
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


def rebuild_modelled(db: Database, product_id: int) -> int:
    """Redraw one product's modelled history after its parameters changed.

    Observed prices are never touched - only the generated points are replaced,
    so a re-fit cannot quietly rewrite something a retailer actually reported.
    """
    row = db.product(product_id)
    if not row:
        return 0
    with db._write_lock:
        db.conn.execute("DELETE FROM prices WHERE product_id=? AND source=?",
                        (product_id, MODELLED))
        db.conn.commit()
    product = {"sku": row["sku"], "category": row["category"],
               "baseline": row["baseline"], "surge_scale": row["surge_scale"]}
    today = datetime.now(timezone.utc).date()
    points = daily_points(product, BASELINE_DATE, today)
    return db.insert_prices([(product_id, ts, price, MODELLED) for ts, price in points])


def refresh_tail(db: Database, pivot: date) -> int:
    """Rewrite every modelled point from `pivot` on, against the current curve.

    Called when a live index feed changes the shape of the future: the anchors
    before the pivot are published history and stay put, the tail is redrawn.
    """
    stamp = datetime.combine(pivot, time(0, 0), tzinfo=timezone.utc).isoformat()
    db.drop_modelled_after(stamp)
    today = datetime.now(timezone.utc).date()
    written = 0
    for row in db.products():
        product = {"sku": row["sku"], "category": row["category"],
                   "baseline": row["baseline"], "surge_scale": row["surge_scale"]}
        points = daily_points(product, pivot, today)
        written += db.insert_prices(
            [(int(row["id"]), ts, price, MODELLED) for ts, price in points])
    return written


def is_seeded(db: Database) -> bool:
    return db.product_count() > 0 and db.price_count() > 0
