"""One category in detail: filter the table, select rows, overlay the charts."""

from __future__ import annotations

import csv
from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog,
                               QFrame,
                               QHBoxLayout, QHeaderView, QInputDialog, QLabel,
                               QLineEdit, QMessageBox, QPushButton, QSplitter,
                               QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget, QFileDialog)

from .. import analytics
from ..analytics import ProductStat
from ..catalog import CATEGORIES
from ..paths import exports_dir
from .add_product import AddProductDialog
from .charts import SERIES_COLOURS, PriceChart
from .theme import change_colour
from .widgets import format_change, num_font

STAR_ON = "\u2605"
STAR_OFF = "\u2606"

COLUMNS = ["", "Product", "Capacity", "Now", "Since Sep 2025", "7 days", "Peak"]


class CategoryView(QWidget):
    """Used for the four categories and, with category=None, for the watchlist."""

    watch_changed = Signal()
    alert_created = Signal(str)

    def __init__(self, db, settings, category: Optional[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.db = db
        self.settings = settings
        self.category = category
        self._stats: List[ProductStat] = []
        self._visible: List[ProductStat] = []
        self._custom_ids: set[int] = set()
        self._fitted_ids: set[int] = set()
        self._loading = True   # suppress filter callbacks until the table exists

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 12)
        root.setSpacing(12)
        root.addLayout(self._build_header())
        root.addWidget(self._build_filters())

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_table())
        splitter.addWidget(self._build_chart_panel())
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 6)
        splitter.setSizes([520, 700])
        root.addWidget(splitter, 1)
        self._loading = False

    # -- construction -----------------------------------------------------
    def _build_header(self) -> QHBoxLayout:
        meta = CATEGORIES.get(self.category or "", {})
        row = QHBoxLayout()
        column = QVBoxLayout()
        column.setSpacing(2)
        self.title = QLabel(meta.get("label", "Watchlist"))
        self.title.setObjectName("Heading")
        self.subtitle = QLabel(meta.get("blurb", "Products you follow"))
        self.subtitle.setObjectName("SubHeading")
        column.addWidget(self.title)
        column.addWidget(self.subtitle)
        row.addLayout(column)
        row.addStretch(1)

        self.summary = QLabel()
        self.summary.setObjectName("SubHeading")
        self.summary.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row.addWidget(self.summary)
        return row

    def _build_filters(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("Panel")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(9)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter by name")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(170)
        self.search.textChanged.connect(self._apply_filters)

        self.brand = QComboBox()
        self.capacity = QComboBox()
        self.form = QComboBox()
        for combo, label in ((self.brand, "All brands"),
                             (self.capacity, "Any capacity"),
                             (self.form, "Any form factor")):
            combo.addItem(label, None)
            combo.setMinimumWidth(128)
            combo.currentIndexChanged.connect(self._apply_filters)

        self.watch_only = QCheckBox("Watchlist only")
        self.watch_only.toggled.connect(self._apply_filters)

        layout.addWidget(self.search)
        layout.addWidget(self.brand)
        layout.addWidget(self.capacity)
        layout.addWidget(self.form)
        layout.addWidget(self.watch_only)
        layout.addStretch(1)

        reset = QPushButton("Clear filters")
        reset.setObjectName("Ghost")
        reset.clicked.connect(self._clear_filters)
        layout.addWidget(reset)

        self.add_btn = QPushButton("Add product")
        self.add_btn.setObjectName("Primary")
        self.add_btn.clicked.connect(self._add_product)
        layout.addWidget(self.add_btn)

        self.remove_btn = QPushButton("Remove")
        self.remove_btn.setObjectName("Ghost")
        self.remove_btn.setToolTip("Removes a product you added yourself")
        self.remove_btn.setEnabled(False)
        self.remove_btn.clicked.connect(self._remove_product)
        layout.addWidget(self.remove_btn)
        if self.category is None:
            self.watch_only.setChecked(True)
            self.watch_only.setVisible(False)
        return bar

    def _build_table(self) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setSortingEnabled(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.itemSelectionChanged.connect(self._on_selection)
        self.table.cellClicked.connect(self._on_cell_clicked)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 30)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        for col in range(2, len(COLUMNS)):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        layout.addWidget(self.table, 1)

        hint = QLabel("Select several rows to overlay them. The star follows a product "
                      "on the dashboard. A \u25c9 means that product's numbers were "
                      "measured from real quotes rather than modelled.")
        hint.setObjectName("CardFoot")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        return wrapper

    def _build_chart_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("Panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.mode = QComboBox()
        self.mode.addItem("Price", "price")
        self.mode.addItem("Change since start of view", "percent")
        self.mode.setCurrentIndex(0 if self.settings.default_chart_mode == "price" else 1)
        self.mode.currentIndexChanged.connect(
            lambda: self.chart.set_mode(self.mode.currentData()))
        controls.addWidget(self.mode)

        self.log_toggle = QCheckBox("Log scale")
        self.log_toggle.setChecked(self.settings.log_scale)
        controls.addWidget(self.log_toggle)
        controls.addStretch(1)

        for label, days in (("3M", 90), ("6M", 180), ("All", None)):
            btn = QPushButton(label)
            btn.setObjectName("Ghost")
            btn.setFixedWidth(42)
            btn.clicked.connect(lambda _=False, d=days: self.chart.zoom_to_days(d))
            controls.addWidget(btn)
        layout.addLayout(controls)

        self.chart = PriceChart(self.settings.theme)
        self.chart.set_money_formatter(self.settings.money)
        self.chart.set_mode(self.mode.currentData())
        self.log_toggle.toggled.connect(self.chart.set_log)
        layout.addWidget(self.chart, 1)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.alert_btn = QPushButton("Alert me when this moves")
        self.alert_btn.clicked.connect(self._create_alert)
        csv_btn = QPushButton("Export data")
        csv_btn.setObjectName("Ghost")
        csv_btn.clicked.connect(self._export_csv)
        png_btn = QPushButton("Save chart")
        png_btn.setObjectName("Ghost")
        png_btn.clicked.connect(self._export_png)
        actions.addWidget(self.alert_btn)
        actions.addStretch(1)
        actions.addWidget(csv_btn)
        actions.addWidget(png_btn)
        layout.addLayout(actions)

        self.empty_note = QLabel("Pick a product on the left to draw its history.")
        self.empty_note.setObjectName("CardFoot")
        layout.addWidget(self.empty_note)
        return panel

    # -- data -------------------------------------------------------------
    def refresh(self, keep_selection: bool = True) -> None:
        selected = self._selected_ids() if keep_selection else []
        self._stats = analytics.product_stats(
            self.db, category=self.category, watched_only=(self.category is None)
        )
        rows = self.db.products(category=self.category)
        self._custom_ids = {int(r["id"]) for r in rows if r["custom"]}
        self._fitted_ids = {int(r["id"]) for r in rows if r["fitted"]}
        self._refill_filter_options()
        self._apply_filters(restore=selected)
        self._update_summary()

    def _refill_filter_options(self) -> None:
        self._loading = True
        for combo, key in ((self.brand, "brand"), (self.capacity, "capacity_gb"),
                           (self.form, "form_factor")):
            current = combo.currentData()
            placeholder = combo.itemText(0)
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(placeholder, None)
            values = sorted({getattr(s, key) for s in self._stats if getattr(s, key)},
                            key=lambda v: (isinstance(v, str), v))
            for value in values:
                label = f"{value // 1000} TB" if key == "capacity_gb" and value >= 1000 else \
                    (f"{value} GB" if key == "capacity_gb" else str(value))
                combo.addItem(label, value)
            index = combo.findData(current)
            combo.setCurrentIndex(index if index >= 0 else 0)
            combo.blockSignals(False)
        self._loading = False

    def _apply_filters(self, *_args, restore: Optional[List[int]] = None) -> None:
        if self._loading:
            return
        text = self.search.text().strip().lower()
        brand = self.brand.currentData()
        capacity = self.capacity.currentData()
        form = self.form.currentData()
        watch_only = self.watch_only.isChecked()

        self._visible = [
            s for s in self._stats
            if (not text or text in s.name.lower() or text in s.interface.lower())
            and (brand is None or s.brand == brand)
            and (capacity is None or s.capacity_gb == capacity)
            and (form is None or s.form_factor == form)
            and (not watch_only or s.watched)
        ]
        self._fill_table(restore or self._selected_ids())

    def _fill_table(self, reselect: List[int]) -> None:
        self.table.setSortingEnabled(False)
        self.table.blockSignals(True)
        self.table.setRowCount(len(self._visible))
        money = self.settings.money
        for r, s in enumerate(self._visible):
            star = QTableWidgetItem(STAR_ON if s.watched else STAR_OFF)
            star.setTextAlignment(Qt.AlignCenter)
            star.setForeground(QBrush(QColor("#E8C547" if s.watched else "#6B7787")))
            star.setToolTip("Follow this product on the dashboard")
            star.setData(Qt.UserRole, s.id)

            measured = s.id in self._fitted_ids
            name = QTableWidgetItem(("\u25c9 " if measured else "") + s.name)
            name.setData(Qt.UserRole, s.id)
            name.setToolTip(
                f"{s.brand} \u00b7 {s.interface or s.form_factor}\n"
                f"Baseline {money(s.baseline)} on 1 Sep 2025\n"
                + ("Fitted to prices your sources actually reported"
                   if measured else "Modelled from the category curve"))

            cap = QTableWidgetItem(
                f"{s.capacity_gb // 1000} TB" if s.capacity_gb and s.capacity_gb >= 1000
                else (f"{s.capacity_gb} GB" if s.capacity_gb else "\u2014")
            )
            cap.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

            now = _numeric_item(money(s.current), s.current or 0)
            surge = _numeric_item(format_change(s.since_surge), s.since_surge or 0)
            surge.setForeground(QBrush(QColor(change_colour(self.settings.theme, s.since_surge))))
            week = _numeric_item(format_change(s.week), s.week or 0)
            week.setForeground(QBrush(QColor(change_colour(self.settings.theme, s.week))))
            peak = _numeric_item(money(s.peak), s.peak or 0)

            for col, item in enumerate([star, name, cap, now, surge, week, peak]):
                self.table.setItem(r, col, item)

        self.table.blockSignals(False)
        self.table.setSortingEnabled(True)

        if reselect:
            self._select_ids(reselect)
        elif self._visible:
            self.table.selectRow(0)
        else:
            self.chart.clear()

    def _update_summary(self) -> None:
        priced = [s for s in self._stats if s.current]
        if not priced:
            self.summary.setText("No prices recorded yet")
            return
        avg = sum(s.current for s in priced) / len(priced)
        surge = [s.since_surge for s in priced if s.since_surge is not None]
        mean = sum(surge) / len(surge) if surge else None
        cheapest = min(priced, key=lambda s: s.current)
        self.summary.setText(
            f"{len(priced)} products \u00b7 average {self.settings.money(avg, 0)} \u00b7 "
            f"{format_change(mean, 0)} since the baseline\n"
            f"cheapest right now: {cheapest.name} at {self.settings.money(cheapest.current)}"
        )

    # -- selection --------------------------------------------------------
    def _selected_ids(self) -> List[int]:
        ids: List[int] = []
        for index in self.table.selectionModel().selectedRows() if self.table.selectionModel() else []:
            item = self.table.item(index.row(), 1)
            if item:
                ids.append(int(item.data(Qt.UserRole)))
        return ids

    def _select_ids(self, ids: List[int]) -> None:
        wanted = set(ids)
        self.table.blockSignals(True)
        self.table.clearSelection()
        found = False
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 1)
            if item and int(item.data(Qt.UserRole)) in wanted:
                self.table.selectRow(r)
                found = True
        self.table.blockSignals(False)
        if not found and self.table.rowCount():
            self.table.selectRow(0)
        self._on_selection()

    def select_product(self, product_id: int) -> None:
        self._select_ids([product_id])

    def _on_selection(self) -> None:
        ids = self._selected_ids()
        self._sync_remove_button(ids)
        if not ids:
            self.chart.clear()
            self.empty_note.setText("Pick a product on the left to draw its history.")
            self.alert_btn.setEnabled(False)
            return
        self.alert_btn.setEnabled(len(ids) == 1)
        by_id = {s.id: s for s in self._stats}
        series = []
        for i, pid in enumerate(ids[:10]):
            stat = by_id.get(pid)
            history = self.db.history(pid)
            if stat and history:
                series.append((stat.name, history, SERIES_COLOURS[i % len(SERIES_COLOURS)]))
        self.chart.set_series(series)
        self.chart.zoom_to_baseline()
        if len(ids) > 10:
            self.empty_note.setText("Showing the first 10 selected products.")
        else:
            oldest = min((s[1][0][0] for s in series), default=None)
            self.empty_note.setText(
                f"History from {oldest.strftime('%d %B %Y')} to now"
                if oldest else "No history recorded yet."
            )

    def _on_cell_clicked(self, row: int, column: int) -> None:
        if column != 0:
            return
        item = self.table.item(row, 0)
        if not item:
            return
        pid = int(item.data(Qt.UserRole))
        stat = next((s for s in self._stats if s.id == pid), None)
        if not stat:
            return
        self.db.set_watched(pid, not stat.watched)
        stat.watched = not stat.watched
        item.setText(STAR_ON if stat.watched else STAR_OFF)
        item.setForeground(QBrush(QColor("#E8C547" if stat.watched else "#6B7787")))
        self.watch_changed.emit()

    def _clear_filters(self) -> None:
        self.search.clear()
        for combo in (self.brand, self.capacity, self.form):
            combo.setCurrentIndex(0)
        if self.category is not None:
            self.watch_only.setChecked(False)

    # -- actions ----------------------------------------------------------
    def _sync_remove_button(self, ids: List[int]) -> None:
        custom = [pid for pid in ids if pid in self._custom_ids]
        self.remove_btn.setEnabled(len(ids) == 1 and len(custom) == 1)

    def _add_product(self) -> None:
        dialog = AddProductDialog(self.db, self.settings, self.category, self)
        if dialog.exec() != QDialog.Accepted or dialog.created_id is None:
            return
        row = self.db.product(dialog.created_id)
        self.refresh(keep_selection=False)
        if row and row["category"] == self.category:
            self.select_product(dialog.created_id)
        self.watch_changed.emit()
        name = row["name"] if row else "the product"
        where = CATEGORIES.get(row["category"], {}).get("label", "") if row else ""
        self.alert_created.emit(
            f"Added {name}" + (f" to {where}" if where and row and
                               row["category"] != self.category else "")
        )

    def _remove_product(self) -> None:
        ids = [pid for pid in self._selected_ids() if pid in self._custom_ids]
        if len(ids) != 1:
            return
        stat = next((s for s in self._stats if s.id == ids[0]), None)
        if not stat:
            return
        answer = QMessageBox.question(
            self, "Remove this product?",
            f"{stat.name} and its whole price history will be deleted.\n\n"
            "Products that shipped with the app cannot be removed, only ones you added.")
        if answer != QMessageBox.Yes:
            return
        self.db.delete_product(stat.id)
        self.refresh(keep_selection=False)
        self.watch_changed.emit()
        self.alert_created.emit(f"Removed {stat.name}")

    def _create_alert(self) -> None:
        ids = self._selected_ids()
        if len(ids) != 1:
            return
        stat = next((s for s in self._stats if s.id == ids[0]), None)
        if not stat or not stat.current:
            return
        value, ok = QInputDialog.getDouble(
            self, "Alert me when this moves",
            f"{stat.name}\nNotify when the price moves this far from "
            f"{self.settings.money(stat.current)}:",
            5.0, 0.5, 90.0, 1,
        )
        if not ok:
            return
        self.db.add_alert(stat.id, "both", float(value), stat.current)
        self.alert_created.emit(
            f"Watching {stat.name} for a {value:.1f}% move from "
            f"{self.settings.money(stat.current)}"
        )

    def _export_csv(self) -> None:
        ids = self._selected_ids() or [s.id for s in self._visible]
        if not ids:
            return
        default = exports_dir() / f"nandtrack-{self.category or 'watchlist'}.csv"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export price history", str(default), "CSV files (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(["sku", "product", "timestamp_utc", f"price_{self.settings.currency}"])
                writer.writerows(self.db.export_rows(ids))
        except OSError as exc:
            QMessageBox.warning(self, "Export failed", f"That file could not be written.\n\n{exc}")
            return
        self.alert_created.emit(f"Saved {len(ids)} product(s) to {path}")

    def _export_png(self) -> None:
        default = exports_dir() / f"nandtrack-{self.category or 'watchlist'}.png"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save chart", str(default), "PNG image (*.png)")
        if not path:
            return
        if self.chart.save_png(path):
            self.alert_created.emit(f"Chart saved to {path}")
        else:
            QMessageBox.warning(self, "Save failed", "The chart image could not be written.")

    # -- theming ----------------------------------------------------------
    def apply_theme(self, theme: str) -> None:
        self.chart.apply_theme(theme)
        self.refresh()


class _NumericItem(QTableWidgetItem):
    """Sorts on the underlying number, not the formatted string."""

    def __lt__(self, other) -> bool:  # noqa: D105
        try:
            return float(self.data(Qt.UserRole + 1)) < float(other.data(Qt.UserRole + 1))
        except (TypeError, ValueError):
            return super().__lt__(other)


def _numeric_item(text: str, value: float) -> QTableWidgetItem:
    item = _NumericItem(text)
    item.setData(Qt.UserRole + 1, float(value))
    item.setFont(num_font(10))
    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    return item
