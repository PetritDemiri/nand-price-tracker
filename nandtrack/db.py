"""SQLite storage. One connection per thread, WAL mode, no ORM."""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from typing import Iterable, List, Optional, Sequence, Tuple

from .paths import db_path

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS products (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sku         TEXT UNIQUE NOT NULL,
    name        TEXT NOT NULL,
    category    TEXT NOT NULL,
    brand       TEXT NOT NULL,
    capacity_gb INTEGER,
    form_factor TEXT,
    interface   TEXT,
    baseline    REAL NOT NULL,          -- street price on the baseline date
    surge_scale REAL NOT NULL DEFAULT 1.0,
    watched     INTEGER NOT NULL DEFAULT 0,
    active      INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS prices (
    product_id INTEGER NOT NULL,
    ts         TEXT NOT NULL,           -- ISO-8601, UTC
    price      REAL NOT NULL,
    source     TEXT NOT NULL,
    PRIMARY KEY (product_id, ts, source),
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_prices_pid_ts ON prices(product_id, ts);

CREATE TABLE IF NOT EXISTS alerts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id  INTEGER NOT NULL,
    direction   TEXT NOT NULL,          -- up | down | both
    threshold   REAL NOT NULL,          -- percent
    reference   REAL,                   -- price the threshold is measured from
    enabled     INTEGER NOT NULL DEFAULT 1,
    last_fired  TEXT,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def parse_iso(text: str) -> datetime:
    dt = datetime.fromisoformat(text)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class Database:
    """Thread-affine connections; every worker thread gets its own handle."""

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = str(path or db_path())
        self._local = threading.local()
        self._write_lock = threading.Lock()
        self._init_schema()

    # -- plumbing ---------------------------------------------------------
    @property
    def conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, timeout=15.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return conn

    def _init_schema(self) -> None:
        with self._write_lock:
            self.conn.executescript(SCHEMA)
            self.conn.commit()

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    # -- meta -------------------------------------------------------------
    def get_meta(self, key: str, default: Optional[str] = None) -> Optional[str]:
        row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set_meta(self, key: str, value: str) -> None:
        with self._write_lock:
            self.conn.execute(
                "INSERT INTO meta(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, str(value)),
            )
            self.conn.commit()

    # -- products ---------------------------------------------------------
    def upsert_product(self, p: dict) -> int:
        with self._write_lock:
            cur = self.conn.execute(
                """INSERT INTO products
                   (sku,name,category,brand,capacity_gb,form_factor,interface,baseline,surge_scale)
                   VALUES(:sku,:name,:category,:brand,:capacity_gb,:form_factor,:interface,
                          :baseline,:surge_scale)
                   ON CONFLICT(sku) DO UPDATE SET
                       name=excluded.name, category=excluded.category, brand=excluded.brand,
                       capacity_gb=excluded.capacity_gb, form_factor=excluded.form_factor,
                       interface=excluded.interface, baseline=excluded.baseline,
                       surge_scale=excluded.surge_scale""",
                p,
            )
            self.conn.commit()
        if cur.lastrowid:
            row = self.conn.execute(
                "SELECT id FROM products WHERE sku=?", (p["sku"],)
            ).fetchone()
            return int(row["id"])
        return 0

    def products(self, category: Optional[str] = None, watched_only: bool = False) -> List[sqlite3.Row]:
        sql = "SELECT * FROM products WHERE active=1"
        args: list = []
        if category:
            sql += " AND category=?"
            args.append(category)
        if watched_only:
            sql += " AND watched=1"
        sql += " ORDER BY category, brand, capacity_gb, name"
        return list(self.conn.execute(sql, args))

    def product(self, product_id: int) -> Optional[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()

    def set_watched(self, product_id: int, watched: bool) -> None:
        with self._write_lock:
            self.conn.execute(
                "UPDATE products SET watched=? WHERE id=?", (1 if watched else 0, product_id)
            )
            self.conn.commit()

    def product_count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) c FROM products").fetchone()["c"])

    # -- prices -----------------------------------------------------------
    def insert_prices(self, rows: Iterable[Tuple[int, str, float, str]]) -> int:
        rows = list(rows)
        if not rows:
            return 0
        with self._write_lock:
            cur = self.conn.executemany(
                "INSERT OR IGNORE INTO prices(product_id, ts, price, source) VALUES(?,?,?,?)",
                rows,
            )
            self.conn.commit()
        return cur.rowcount or 0

    def price_count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) c FROM prices").fetchone()["c"])

    def history(self, product_id: int, since: Optional[str] = None) -> List[Tuple[datetime, float]]:
        """Cheapest price per timestamp, oldest first."""
        sql = ("SELECT ts, MIN(price) p FROM prices WHERE product_id=? "
               + ("AND ts>=? " if since else "")
               + "GROUP BY ts ORDER BY ts")
        args = [product_id] + ([since] if since else [])
        return [(parse_iso(r["ts"]), float(r["p"])) for r in self.conn.execute(sql, args)]

    def latest(self, product_id: int) -> Optional[Tuple[datetime, float]]:
        row = self.conn.execute(
            "SELECT ts, MIN(price) p FROM prices WHERE product_id=? "
            "AND ts=(SELECT MAX(ts) FROM prices WHERE product_id=?)",
            (product_id, product_id),
        ).fetchone()
        if not row or row["p"] is None:
            return None
        return parse_iso(row["ts"]), float(row["p"])

    def latest_map(self) -> dict:
        """product_id -> (timestamp, lowest price) for every product, one query."""
        sql = """
            SELECT p.product_id AS pid, p.ts AS ts, MIN(p.price) AS price
            FROM prices p
            JOIN (SELECT product_id, MAX(ts) AS mts FROM prices GROUP BY product_id) m
              ON m.product_id = p.product_id AND m.mts = p.ts
            GROUP BY p.product_id
        """
        return {
            int(r["pid"]): (parse_iso(r["ts"]), float(r["price"]))
            for r in self.conn.execute(sql)
        }

    def price_on_or_after(self, product_id: int, ts: str) -> Optional[float]:
        row = self.conn.execute(
            "SELECT MIN(price) p FROM prices WHERE product_id=? AND ts>=? "
            "AND ts=(SELECT MIN(ts) FROM prices WHERE product_id=? AND ts>=?)",
            (product_id, ts, product_id, ts),
        ).fetchone()
        return float(row["p"]) if row and row["p"] is not None else None

    def baseline_map(self, ts: str) -> dict:
        """product_id -> first recorded price at/after `ts`."""
        sql = """
            SELECT p.product_id AS pid, MIN(p.price) AS price
            FROM prices p
            JOIN (SELECT product_id, MIN(ts) AS mts FROM prices WHERE ts>=? GROUP BY product_id) m
              ON m.product_id = p.product_id AND m.mts = p.ts
            GROUP BY p.product_id
        """
        return {int(r["pid"]): float(r["price"]) for r in self.conn.execute(sql, (ts,))}

    def last_ts(self) -> Optional[datetime]:
        row = self.conn.execute("SELECT MAX(ts) m FROM prices").fetchone()
        return parse_iso(row["m"]) if row and row["m"] else None

    def daily_series(self, product_id: int) -> List[Tuple[str, float]]:
        """One point per calendar day (the day's low) - used for sparklines."""
        return [
            (r["d"], float(r["p"]))
            for r in self.conn.execute(
                "SELECT substr(ts,1,10) d, MIN(price) p FROM prices "
                "WHERE product_id=? GROUP BY d ORDER BY d",
                (product_id,),
            )
        ]

    def category_index(self, category: str) -> List[Tuple[str, float]]:
        """Daily average of each product's price relative to its own baseline."""
        sql = """
            SELECT substr(pr.ts,1,10) AS d,
                   AVG(pr.price / p.baseline) AS idx
            FROM prices pr
            JOIN products p ON p.id = pr.product_id
            WHERE p.category = ? AND p.active = 1 AND p.baseline > 0
            GROUP BY d ORDER BY d
        """
        return [(r["d"], float(r["idx"])) for r in self.conn.execute(sql, (category,))]

    # -- alerts -----------------------------------------------------------
    def alerts(self, enabled_only: bool = True) -> List[sqlite3.Row]:
        sql = "SELECT a.*, p.name, p.sku, p.category FROM alerts a JOIN products p ON p.id=a.product_id"
        if enabled_only:
            sql += " WHERE a.enabled=1"
        return list(self.conn.execute(sql))

    def add_alert(self, product_id: int, direction: str, threshold: float,
                  reference: Optional[float]) -> int:
        with self._write_lock:
            cur = self.conn.execute(
                "INSERT INTO alerts(product_id,direction,threshold,reference) VALUES(?,?,?,?)",
                (product_id, direction, threshold, reference),
            )
            self.conn.commit()
        return int(cur.lastrowid)

    def delete_alert(self, alert_id: int) -> None:
        with self._write_lock:
            self.conn.execute("DELETE FROM alerts WHERE id=?", (alert_id,))
            self.conn.commit()

    def touch_alert(self, alert_id: int, reference: float, when: str) -> None:
        with self._write_lock:
            self.conn.execute(
                "UPDATE alerts SET reference=?, last_fired=? WHERE id=?",
                (reference, when, alert_id),
            )
            self.conn.commit()

    # -- export -----------------------------------------------------------
    def export_rows(self, product_ids: Sequence[int]) -> List[Tuple[str, str, str, float]]:
        if not product_ids:
            return []
        marks = ",".join("?" * len(product_ids))
        sql = (f"SELECT p.sku, p.name, pr.ts, MIN(pr.price) price FROM prices pr "
               f"JOIN products p ON p.id=pr.product_id WHERE pr.product_id IN ({marks}) "
               f"GROUP BY pr.product_id, pr.ts ORDER BY p.sku, pr.ts")
        return [
            (r["sku"], r["name"], r["ts"], float(r["price"]))
            for r in self.conn.execute(sql, list(product_ids))
        ]
