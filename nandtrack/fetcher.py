"""Background polling.

A QObject worker lives on its own QThread so the UI never blocks on a socket.
It polls every source in turn, writes whatever came back, and reports which
products moved. Polling continues while the window is minimised or in the tray.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot

from .db import Database
from .sources import build_sources


@dataclass
class Movement:
    product_id: int
    name: str
    category: str
    previous: float
    current: float

    @property
    def change_pct(self) -> float:
        if not self.previous:
            return 0.0
        return (self.current - self.previous) / self.previous * 100.0


class FetchWorker(QObject):
    """Runs on the worker thread. Never touch widgets from in here."""

    finished_cycle = Signal(list, str, str)   # movements, source label, error or ""
    started_cycle = Signal()

    def __init__(self, db_path: str, interval_seconds: int, use_live: bool,
                 settings=None) -> None:
        super().__init__()
        self._db_path = db_path
        self._interval = max(60, interval_seconds)
        self._use_live = use_live
        self._settings = settings
        self._timer: Optional[QTimer] = None
        self._db: Optional[Database] = None
        self._busy = False

    # -- lifecycle --------------------------------------------------------
    @Slot()
    def start(self) -> None:
        self._db = Database(self._db_path)
        self._timer = QTimer()
        self._timer.setInterval(self._interval * 1000)
        self._timer.timeout.connect(self.poll)
        self._timer.start()
        QTimer.singleShot(1200, self.poll)        # one cycle shortly after launch

    @Slot()
    def stop(self) -> None:
        if self._timer:
            self._timer.stop()
        if self._db:
            self._db.close()

    @Slot(int)
    def set_interval(self, seconds: int) -> None:
        self._interval = max(60, seconds)
        if self._timer:
            self._timer.setInterval(self._interval * 1000)

    @Slot(bool)
    def set_live(self, use_live: bool) -> None:
        self._use_live = use_live

    # -- work -------------------------------------------------------------
    @Slot()
    def _maybe_refresh_index(self) -> str:
        """Pull the market index when it has gone stale, and reshape the tail."""
        settings = self._settings
        if self._db is None or settings is None:
            return ""
        if getattr(settings, "index_provider", "off") == "off":
            return ""
        from . import marketdata
        from .market import ANCHORS  # noqa: F401  (import guard for frozen builds)

        last = self._db.get_meta("index_refreshed")
        if last:
            try:
                age = datetime.now(timezone.utc) - datetime.fromisoformat(last)
                if age < timedelta(hours=max(1, int(getattr(settings, "index_refresh_hours", 12)))):
                    return ""
            except ValueError:
                pass

        written, problem = marketdata.refresh(self._db, settings)
        if not written:
            return ""
        report = marketdata.load_into_curve(self._db)
        if not report:
            return ""

        # Only redraw the modelled tail when the feed genuinely moved it.
        signature = "|".join(f"{k}:{v}" for k, v in sorted(report.items()))
        if signature != (self._db.get_meta("index_signature") or ""):
            from .seed import refresh_tail
            refresh_tail(self._db, marketdata.LAST_REPORTED)
            self._db.set_meta("index_signature", signature)
        return self._db.get_meta("index_feed") or "index"

    def _maybe_calibrate(self) -> int:
        settings = self._settings
        if self._db is None or not getattr(settings, "auto_calibrate", True):
            return 0
        from . import calibrate
        try:
            return len(calibrate.calibrate_all(self._db))
        except Exception:                                  # noqa: BLE001
            return 0

    @Slot()
    def poll(self) -> None:
        if self._busy or self._db is None:
            return
        self._busy = True
        self.started_cycle.emit()
        error = ""
        labels: List[str] = []
        movements: List[Movement] = []
        try:
            rows = self._db.products()
            products = [
                {"id": int(r["id"]), "sku": r["sku"], "category": r["category"],
                 "baseline": float(r["baseline"]), "surge_scale": float(r["surge_scale"]),
                 "name": r["name"]}
                for r in rows
            ]
            previous: Dict[int, float] = {
                pid: price for pid, (_, price) in self._db.latest_map().items()
            }
            quotes = []
            for source in build_sources(self._use_live):
                try:
                    batch = source.fetch(products)
                except Exception as exc:                       # noqa: BLE001
                    error = f"{source.name}: {exc}"
                    continue
                if batch:
                    quotes.extend(batch)
                    labels.append(source.describe())
                if getattr(source, "error", None):
                    error = str(source.error)

            self._db.insert_prices(quotes)

            by_name = {p["id"]: p for p in products}
            best: Dict[int, float] = {}
            for pid, _ts, price, _src in quotes:
                best[pid] = min(price, best.get(pid, price))
            for pid, price in best.items():
                before = previous.get(pid)
                if before and abs(price - before) / before >= 0.0005:
                    info = by_name.get(pid, {})
                    movements.append(Movement(
                        product_id=pid,
                        name=info.get("name", ""),
                        category=info.get("category", ""),
                        previous=before,
                        current=price,
                    ))
            self._db.set_meta("last_poll", datetime.now(timezone.utc).isoformat())

            index_note = self._maybe_refresh_index()
            if index_note:
                labels.append(index_note)
            fits = self._maybe_calibrate()
            if fits:
                labels.append(f"{fits} re-fitted")
        except Exception as exc:                               # noqa: BLE001
            error = str(exc)
        finally:
            self._busy = False
        self.finished_cycle.emit(movements, " + ".join(dict.fromkeys(labels)), error)


class FetchController(QObject):
    """UI-thread handle for the worker: owns the thread, forwards signals.

    Every instruction to the worker goes out as a signal. Qt queues those onto
    the worker's own thread, which matters because a QTimer may only be started
    or stopped from the thread that owns it.
    """

    cycle_finished = Signal(list, str, str)
    cycle_started = Signal()

    _poll_requested = Signal()
    _stop_requested = Signal()
    _interval_requested = Signal(int)
    _live_requested = Signal(bool)

    def __init__(self, db_path: str, interval_seconds: int, use_live: bool,
                 settings=None, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.thread = QThread()
        self.thread.setObjectName("nandtrack-fetch")
        self.worker = FetchWorker(db_path, interval_seconds, use_live, settings)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.start)
        self.worker.finished_cycle.connect(self.cycle_finished)
        self.worker.started_cycle.connect(self.cycle_started)

        self._poll_requested.connect(self.worker.poll)
        self._stop_requested.connect(self.worker.stop)
        self._interval_requested.connect(self.worker.set_interval)
        self._live_requested.connect(self.worker.set_live)

    def start(self) -> None:
        self.thread.start()

    def poll_now(self) -> None:
        self._poll_requested.emit()

    def apply_settings(self, interval_seconds: int, use_live: bool) -> None:
        self._interval_requested.emit(int(interval_seconds))
        self._live_requested.emit(bool(use_live))

    def shutdown(self) -> None:
        if not self.thread.isRunning():
            return
        self._stop_requested.emit()
        self.thread.quit()
        if not self.thread.wait(3000):
            self.thread.terminate()
            self.thread.wait(1000)
