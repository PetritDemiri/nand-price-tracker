"""Threshold alerts.

Each rule stores the price it was last measured against, so a drifting price
fires once per threshold crossed rather than once per poll.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List

from .db import Database


@dataclass
class AlertHit:
    alert_id: int
    product_id: int
    name: str
    direction: str
    change_pct: float
    price: float

    def title(self) -> str:
        return "Price drop" if self.change_pct < 0 else "Price rise"

    def body(self, money) -> str:
        arrow = "down" if self.change_pct < 0 else "up"
        return f"{self.name} is {arrow} {abs(self.change_pct):.1f}% at {money(self.price)}"


def evaluate(db: Database) -> List[AlertHit]:
    latest = db.latest_map()
    hits: List[AlertHit] = []
    now = datetime.now(timezone.utc).isoformat()
    for rule in db.alerts(enabled_only=True):
        pid = int(rule["product_id"])
        entry = latest.get(pid)
        if not entry:
            continue
        price = entry[1]
        reference = rule["reference"] or price
        if not reference:
            continue
        change = (price - reference) / reference * 100.0
        threshold = float(rule["threshold"])
        direction = rule["direction"]
        fired = (
            (direction in ("down", "both") and change <= -threshold)
            or (direction in ("up", "both") and change >= threshold)
        )
        if fired:
            hits.append(AlertHit(
                alert_id=int(rule["id"]), product_id=pid, name=rule["name"],
                direction=direction, change_pct=change, price=price,
            ))
            db.touch_alert(int(rule["id"]), price, now)
    return hits
