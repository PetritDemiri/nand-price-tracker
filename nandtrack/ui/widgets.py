"""Small custom widgets: sparkline, category card, change pill."""

from __future__ import annotations

from typing import List, Optional, Sequence

from PySide6.QtCore import QPointF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QSizePolicy,
                               QVBoxLayout, QWidget)

from .theme import NUM_FONT, change_colour, palette


def num_font(size: int = 13, weight: int = QFont.Normal) -> QFont:
    font = QFont()
    for family in ("Cascadia Mono", "Consolas", "DejaVu Sans Mono", "Courier New"):
        font.setFamily(family)
        break
    font.setPointSize(size)
    font.setWeight(QFont.Weight(weight) if isinstance(weight, int) else weight)
    font.setStyleHint(QFont.Monospace)
    return font


def format_change(value: Optional[float], decimals: int = 1) -> str:
    if value is None:
        return "\u2014"
    sign = "+" if value > 0 else ("\u2212" if value < 0 else "")
    return f"{sign}{abs(value):.{decimals}f}%"


class Sparkline(QWidget):
    """A bare trend line - no axes, no labels, just the shape of the move."""

    def __init__(self, theme: str = "dark", colour: Optional[str] = None,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._values: List[float] = []
        self._theme = theme
        self._colour = colour
        self.setMinimumHeight(38)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def sizeHint(self) -> QSize:
        return QSize(160, 42)

    def set_values(self, values: Sequence[float]) -> None:
        # thin long series so painting stays cheap on a 400-point year
        values = list(values)
        if len(values) > 220:
            step = len(values) / 220.0
            values = [values[int(i * step)] for i in range(220)]
        self._values = values
        self.update()

    def set_theme(self, theme: str) -> None:
        self._theme = theme
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        if len(self._values) < 2:
            return
        c = palette(self._theme)
        colour = QColor(self._colour or c["rise"])
        w, h = self.width(), self.height()
        pad = 3.0
        lo, hi = min(self._values), max(self._values)
        span = (hi - lo) or 1.0
        n = len(self._values)
        points = [
            QPointF(pad + (w - 2 * pad) * i / (n - 1),
                    h - pad - (h - 2 * pad) * (v - lo) / span)
            for i, v in enumerate(self._values)
        ]

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        fill = QPainterPath(QPointF(points[0].x(), h))
        for p in points:
            fill.lineTo(p)
        fill.lineTo(points[-1].x(), h)
        fill.closeSubpath()
        wash = QColor(colour)
        wash.setAlpha(34)
        painter.fillPath(fill, wash)

        line = QPainterPath(points[0])
        for p in points[1:]:
            line.lineTo(p)
        painter.setPen(QPen(colour, 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawPath(line)

        painter.setPen(Qt.NoPen)
        painter.setBrush(colour)
        painter.drawEllipse(points[-1], 2.6, 2.6)
        painter.end()


class ChangePill(QLabel):
    """Coloured percentage badge."""

    def __init__(self, theme: str = "dark", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self.setFont(num_font(10))
        self.setAlignment(Qt.AlignCenter)
        self.set_value(None)

    def set_theme(self, theme: str) -> None:
        self._theme = theme
        self.set_value(self._value)

    def set_value(self, value: Optional[float], suffix: str = "") -> None:
        self._value = value
        colour = change_colour(self._theme, value)
        self.setText(format_change(value) + suffix)
        tint = QColor(colour)
        tint.setAlpha(38)
        self.setStyleSheet(
            f"color:{colour}; background: rgba({tint.red()},{tint.green()},{tint.blue()},0.16);"
            f" border:1px solid {colour}; border-radius:5px; padding:2px 7px;"
        )


class CategoryCard(QFrame):
    """Headline numbers for one tracked category. Clicking opens that category."""

    clicked = Signal(str)

    def __init__(self, key: str, theme: str = "dark", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.key = key
        self._theme = theme
        self._colour = "#F2994A"
        self.setObjectName("Card")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumWidth(228)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.bar = QFrame()
        self.bar.setFixedWidth(3)
        outer.addWidget(self.bar)

        body = QVBoxLayout()
        body.setContentsMargins(14, 12, 14, 12)
        body.setSpacing(4)
        outer.addLayout(body)

        self.title = QLabel()
        self.title.setObjectName("CardTitle")
        self.value = QLabel("\u2014")
        self.value.setObjectName("CardValue")

        row = QHBoxLayout()
        row.setSpacing(6)
        self.pill = ChangePill(theme)
        self.since = QLabel("since 1 Sep 2025")
        self.since.setObjectName("CardFoot")
        row.addWidget(self.pill)
        row.addWidget(self.since)
        row.addStretch(1)

        self.spark = Sparkline(theme)
        self.foot = QLabel()
        self.foot.setObjectName("CardFoot")
        self.foot.setWordWrap(True)

        body.addWidget(self.title)
        body.addWidget(self.value)
        body.addLayout(row)
        body.addWidget(self.spark)
        body.addWidget(self.foot)

    def set_theme(self, theme: str) -> None:
        self._theme = theme
        self.pill.set_theme(theme)
        self.spark.set_theme(theme)

    def update_stat(self, stat, money) -> None:
        self._colour = stat.colour
        self.bar.setStyleSheet(
            f"background:{stat.colour}; border-top-left-radius:8px; border-bottom-left-radius:8px;"
        )
        self.title.setText(stat.label)
        self.value.setText(money(stat.average, 0) if stat.average else "\u2014")
        self.pill.set_value(stat.since_surge)
        self.spark.set_values([v for _, v in stat.index_series])
        self.spark._colour = stat.colour
        cheapest = money(stat.lowest, 0) if stat.lowest else "\u2014"
        week = format_change(stat.week)
        self.foot.setText(
            f"{stat.count} tracked \u00b7 cheapest {cheapest} \u00b7 {week} this week"
        )
        self.value.setToolTip("Average of the cheapest current price for each tracked product")

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.key)
        super().mouseReleaseEvent(event)


class StatBlock(QFrame):
    """A single labelled number, used across the dashboard header."""

    def __init__(self, title: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 11, 14, 11)
        layout.setSpacing(2)
        self.title = QLabel(title)
        self.title.setObjectName("CardTitle")
        self.value = QLabel("\u2014")
        self.value.setObjectName("CardValue")
        self.foot = QLabel("")
        self.foot.setObjectName("CardFoot")
        layout.addWidget(self.title)
        layout.addWidget(self.value)
        layout.addWidget(self.foot)

    def set(self, value: str, foot: str = "", colour: Optional[str] = None) -> None:
        self.value.setText(value)
        self.foot.setText(foot)
        self.value.setStyleSheet(f"color:{colour};" if colour else "")
