"""Dashboard: where every category stands, and what moved this week."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QHeaderView,
                               QLabel, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from .. import analytics
from ..catalog import CATEGORIES, CATEGORY_ORDER
from .charts import PriceChart, epoch
from .theme import change_colour, palette
from .widgets import CategoryCard, StatBlock, format_change, num_font


class Dashboard(QWidget):
    open_category = Signal(str)
    open_product = Signal(int)

    def __init__(self, db, settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.db = db
        self.settings = settings
        self._cards: Dict[str, CategoryCard] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 12)
        root.setSpacing(14)

        root.addLayout(self._build_header())
        root.addLayout(self._build_cards())

        middle = QHBoxLayout()
        middle.setSpacing(14)
        middle.addWidget(self._build_index_panel(), 3)
        middle.addWidget(self._build_movers_panel(), 2)
        root.addLayout(middle, 1)

    # -- construction -----------------------------------------------------
    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(14)

        left = QVBoxLayout()
        left.setSpacing(2)
        title = QLabel("Where prices stand today")
        title.setObjectName("Heading")
        self.subtitle = QLabel()
        self.subtitle.setObjectName("SubHeading")
        left.addWidget(title)
        left.addWidget(self.subtitle)
        row.addLayout(left)
        row.addStretch(1)

        self.basket = StatBlock("A mid-range build's memory bill")
        self.basket.setMinimumWidth(270)
        row.addWidget(self.basket)
        return row

    def _build_cards(self) -> QGridLayout:
        grid = QGridLayout()
        grid.setSpacing(12)
        for i, key in enumerate(CATEGORY_ORDER):
            card = CategoryCard(key, self.settings.theme)
            card.clicked.connect(self.open_category)
            self._cards[key] = card
            grid.addWidget(card, 0, i)
            grid.setColumnStretch(i, 1)
        return grid

    def _build_index_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("Panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        head = QHBoxLayout()
        title = QLabel("Every category against its September 2025 price")
        title.setObjectName("Heading")
        title.setStyleSheet("font-size:15px;")
        head.addWidget(title)
        head.addStretch(1)
        for label, days in (("3M", 90), ("6M", 180), ("1Y", 365), ("All", None)):
            btn = QPushButton(label)
            btn.setObjectName("Ghost")
            btn.setFixedWidth(46)
            btn.clicked.connect(lambda _=False, d=days: self.chart.zoom_to_days(d))
            head.addWidget(btn)
        layout.addLayout(head)

        self.chart = PriceChart(self.settings.theme)
        self.chart.set_mode("price")
        layout.addWidget(self.chart, 1)

        self.legend_note = QLabel(
            "100 = the cheapest price for that product on 1 September 2025. "
            "Each line is the average across the products tracked in that category."
        )
        self.legend_note.setObjectName("CardFoot")
        self.legend_note.setWordWrap(True)
        layout.addWidget(self.legend_note)
        return panel

    def _build_movers_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("Panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        title = QLabel("Moved most this week")
        title.setObjectName("Heading")
        title.setStyleSheet("font-size:15px;")
        layout.addWidget(title)

        self.movers = QTableWidget(0, 3)
        self.movers.setHorizontalHeaderLabels(["Product", "Now", "7 days"])
        self.movers.verticalHeader().setVisible(False)
        self.movers.setAlternatingRowColors(True)
        self.movers.setSelectionBehavior(QTableWidget.SelectRows)
        self.movers.setEditTriggers(QTableWidget.NoEditTriggers)
        self.movers.setShowGrid(False)
        header = self.movers.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.movers.cellDoubleClicked.connect(self._on_mover_activated)
        layout.addWidget(self.movers, 1)

        self.watch_note = QLabel()
        self.watch_note.setObjectName("CardFoot")
        self.watch_note.setWordWrap(True)
        layout.addWidget(self.watch_note)
        return panel

    # -- data -------------------------------------------------------------
    def refresh(self) -> None:
        money = self.settings.money
        cats = analytics.category_stats(self.db)
        for stat in cats:
            self._cards[stat.key].update_stat(stat, money)

        series = []
        for stat in cats:
            points = [
                (datetime.fromisoformat(day + "T12:00:00+00:00"), value * 100.0)
                for day, value in stat.index_series
            ]
            if points:
                series.append((stat.label, points, stat.colour))
        self.chart.set_money_formatter(lambda v, d=1: f"{v:,.0f}")
        self.chart.set_series(series)
        self.chart.zoom_to_baseline()

        self._fill_movers()

        summary = analytics.portfolio_summary(self.db)
        if summary["now"] and summary["then"]:
            colour = change_colour(self.settings.theme, summary["change"])
            self.basket.set(
                self.settings.money(summary["now"], 0),
                f"was {self.settings.money(summary['then'], 0)} \u00b7 "
                f"{format_change(summary['change'], 0)} \u00b7 32GB DDR5 + 2TB NVMe + RTX 5070",
                colour,
            )

        last = self.db.last_ts()
        worst = max((c.since_surge or 0) for c in cats) if cats else 0
        leader = next((c.label for c in cats if (c.since_surge or 0) == worst), "")
        self.subtitle.setText(
            f"{leader} has moved furthest since the shortage began \u2014 "
            f"{format_change(worst, 0)} across {sum(c.count for c in cats)} tracked products"
            + (f" \u00b7 latest sample {last.astimezone().strftime('%d %b %H:%M')}" if last else "")
        )

    def _fill_movers(self) -> None:
        rows = analytics.movers(self.db, days=7, limit=10)
        self.movers.setRowCount(len(rows))
        for r, (stat, change) in enumerate(rows):
            name = QTableWidgetItem(stat.name)
            name.setData(Qt.UserRole, stat.id)
            name.setToolTip(f"{stat.brand} \u00b7 {stat.interface}\nDouble-click to open the chart")
            dot = QColor(CATEGORIES[stat.category]["colour"])
            name.setForeground(QBrush(dot.lighter(120)))

            price = QTableWidgetItem(self.settings.money(stat.current))
            price.setFont(num_font(10))
            price.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

            pct = QTableWidgetItem(format_change(change))
            pct.setFont(num_font(10, QFont.DemiBold))
            pct.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            pct.setForeground(QBrush(QColor(change_colour(self.settings.theme, change))))

            self.movers.setItem(r, 0, name)
            self.movers.setItem(r, 1, price)
            self.movers.setItem(r, 2, pct)

        watched = analytics.product_stats(self.db, watched_only=True)
        if watched:
            names = ", ".join(w.name.split("(")[0].strip() for w in watched[:3])
            self.watch_note.setText(f"On your watchlist: {names}"
                                    + (f" and {len(watched) - 3} more" if len(watched) > 3 else ""))
        else:
            self.watch_note.setText("Nothing on your watchlist yet. Star a product in any "
                                    "category view to follow it here.")

    def _on_mover_activated(self, row: int, _column: int) -> None:
        item = self.movers.item(row, 0)
        if item:
            self.open_product.emit(int(item.data(Qt.UserRole)))

    # -- theming ----------------------------------------------------------
    def apply_theme(self, theme: str) -> None:
        for card in self._cards.values():
            card.set_theme(theme)
        self.chart.apply_theme(theme)
        self.refresh()
