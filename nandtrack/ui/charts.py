"""The chart surface.

pyqtgraph rather than QtCharts: it draws a year of daily points for a dozen
overlaid SKUs without dropping frames, and pan/zoom come for free. Wheel zooms,
drag pans, right-drag scales one axis, and the crosshair reads out the exact
date and price of the nearest sample.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence, Tuple

import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ..market import BASELINE_DATE
from .theme import palette

pg.setConfigOption("antialias", True)
pg.setConfigOption("foreground", "#8996A8")

SERIES_COLOURS = [
    "#F2994A", "#3ECFB0", "#6C8CFF", "#B47DE8", "#E85D75",
    "#4EA8FF", "#E8C547", "#59C36A", "#FF8FA3", "#7FD3E8",
]


def epoch(dt: datetime) -> float:
    return dt.replace(tzinfo=dt.tzinfo or timezone.utc).timestamp()


class PriceChart(QWidget):
    """Overlay chart with price / percent-change modes and a crosshair readout."""

    hovered = Signal(str)

    def __init__(self, theme: str = "dark", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._mode = "price"          # price | percent
        self._log = False
        self._series: Dict[str, Tuple[List[float], List[float], str]] = {}
        self._curves: Dict[str, pg.PlotDataItem] = {}
        self._money = lambda v, d=2: f"{v:,.2f}"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        axis = pg.DateAxisItem(orientation="bottom")
        self.plot = pg.PlotWidget(axisItems={"bottom": axis})
        self.plot.setMenuEnabled(False)
        self.plot.showGrid(x=True, y=True, alpha=0.18)
        self.plot.setMouseEnabled(x=True, y=True)
        self.plot.getPlotItem().setClipToView(True)
        self.plot.getPlotItem().setDownsampling(auto=True, mode="peak")
        layout.addWidget(self.plot)

        self.legend = self.plot.addLegend(offset=(12, 10), labelTextSize="9pt")

        self.vline = pg.InfiniteLine(angle=90, movable=False,
                                     pen=pg.mkPen("#6C8CFF", width=1, style=Qt.DashLine))
        self.vline.setZValue(20)
        self.vline.hide()
        self.plot.addItem(self.vline, ignoreBounds=True)

        self.readout = pg.TextItem(anchor=(0, 1))
        self.readout.setZValue(30)
        self.readout.hide()
        self.plot.addItem(self.readout, ignoreBounds=True)

        self.surge_line = pg.InfiniteLine(
            pos=epoch(datetime(2025, 10, 15, tzinfo=timezone.utc)),
            angle=90, movable=False,
            pen=pg.mkPen("#E85D75", width=1, style=Qt.DotLine),
            label="shortage begins", labelOpts={"position": 0.04, "color": "#E85D75",
                                                "movable": False, "fill": (0, 0, 0, 0)},
        )
        self.plot.addItem(self.surge_line, ignoreBounds=True)

        self.plot.scene().sigMouseMoved.connect(self._on_move)
        self.apply_theme(theme)

    # -- configuration ----------------------------------------------------
    def set_money_formatter(self, fn) -> None:
        self._money = fn

    def apply_theme(self, theme: str) -> None:
        self._theme = theme
        c = palette(theme)
        self.plot.setBackground(QColor(c["panel"]))
        for side in ("left", "bottom"):
            ax = self.plot.getAxis(side)
            ax.setPen(pg.mkPen(c["line"]))
            ax.setTextPen(pg.mkPen(c["ink_dim"]))
        self.readout.setColor(QColor(c["ink"]))
        self.readout.fill = pg.mkBrush(QColor(c["panel_hi"]))
        self.readout.border = pg.mkPen(QColor(c["line"]))
        font = QFont("Cascadia Mono")
        font.setPointSize(9)
        self.readout.setFont(font)
        self._relabel_axis()

    def set_mode(self, mode: str) -> None:
        self._mode = mode
        self._rebuild()

    def set_log(self, enabled: bool) -> None:
        self._log = enabled
        self.plot.getPlotItem().vb.enableAutoRange()
        self.plot.setLogMode(x=False, y=enabled and self._mode == "price")
        self._rebuild()
        self.plot.getPlotItem().vb.enableAutoRange()

    def _relabel_axis(self) -> None:
        c = palette(self._theme)
        label = "change since baseline (%)" if self._mode == "percent" else "cheapest price"
        self.plot.setLabel("left", label, color=c["ink_dim"], size="9pt")

    # -- data -------------------------------------------------------------
    def set_series(self, series: Sequence[Tuple[str, List[Tuple[datetime, float]], Optional[str]]]) -> None:
        """series: (label, [(datetime, price), ...], colour or None)."""
        self._series.clear()
        for i, (label, points, colour) in enumerate(series):
            if not points:
                continue
            xs = [epoch(dt) for dt, _ in points]
            ys = [price for _, price in points]
            self._series[label] = (xs, ys, colour or SERIES_COLOURS[i % len(SERIES_COLOURS)])
        self._rebuild()

    def clear(self) -> None:
        self._series.clear()
        self._rebuild()

    def _rebuild(self) -> None:
        for curve in self._curves.values():
            self.plot.removeItem(curve)
        self._curves.clear()
        try:
            self.legend.clear()
        except Exception:                       # pyqtgraph version differences
            pass

        for label, (xs, ys, colour) in self._series.items():
            values = ys
            if self._mode == "percent" and ys and ys[0]:
                values = [(y - ys[0]) / ys[0] * 100.0 for y in ys]
            curve = self.plot.plot(
                xs, values, name=label,
                pen=pg.mkPen(colour, width=1.8),
                autoDownsample=True,
            )
            self._curves[label] = curve

        if self._mode == "percent":
            zero = pg.InfiniteLine(pos=0, angle=0, movable=False,
                                   pen=pg.mkPen(palette(self._theme)["line"], width=1))
            self.plot.addItem(zero, ignoreBounds=True)
            self._curves["__zero__"] = zero
        self.plot.setLogMode(x=False, y=self._log and self._mode == "price")
        self._relabel_axis()
        if self._series:
            self.plot.enableAutoRange()

    def reset_view(self) -> None:
        self.plot.enableAutoRange()

    def zoom_to_days(self, days: Optional[int]) -> None:
        if not self._series:
            return
        if days is None:
            self.plot.enableAutoRange()
            return
        now = datetime.now(timezone.utc).timestamp()
        self.plot.setXRange(now - days * 86400, now, padding=0.02)
        self.plot.enableAutoRange(axis="y")

    def zoom_to_baseline(self) -> None:
        start = datetime(BASELINE_DATE.year, BASELINE_DATE.month, BASELINE_DATE.day,
                         tzinfo=timezone.utc).timestamp()
        self.plot.setXRange(start, datetime.now(timezone.utc).timestamp(), padding=0.02)
        self.plot.enableAutoRange(axis="y")

    # -- crosshair --------------------------------------------------------
    def _on_move(self, pos) -> None:
        if not self._series or not self.plot.sceneBoundingRect().contains(pos):
            self.vline.hide()
            self.readout.hide()
            return
        view = self.plot.getPlotItem().vb
        point = view.mapSceneToView(pos)
        x = point.x()
        self.vline.setPos(x)
        self.vline.show()

        lines: List[str] = []
        stamp = ""
        for label, (xs, ys, _colour) in self._series.items():
            idx = min(range(len(xs)), key=lambda i: abs(xs[i] - x))
            value = ys[idx]
            if self._mode == "percent" and ys[0]:
                shown = f"{(value - ys[0]) / ys[0] * 100.0:+.1f}%"
            else:
                shown = self._money(value)
            name = label if len(label) <= 34 else label[:33] + "\u2026"
            lines.append(f"{name}  {shown}")
            stamp = datetime.fromtimestamp(xs[idx], tz=timezone.utc).strftime("%d %b %Y, %H:%M")
        text = stamp + "\n" + "\n".join(lines[:10])
        if len(lines) > 10:
            text += f"\n+{len(lines) - 10} more"
        self.readout.setText(text)

        # Flip the box away from whichever edge the cursor is near, otherwise it
        # runs off the plot and gets clipped at the right-hand side.
        (x_min, x_max), (y_min, y_max) = view.viewRange()
        anchor_x = 0.0 if x < (x_min + x_max) / 2.0 else 1.0
        anchor_y = 0.0 if point.y() > (y_min + y_max) / 2.0 else 1.0
        self.readout.setAnchor((anchor_x, anchor_y))

        self.readout.setPos(x, point.y())
        self.readout.show()
        self.hovered.emit(stamp)

    # -- export -----------------------------------------------------------
    def save_png(self, path: str) -> bool:
        try:
            return bool(self.plot.grab().save(path, "PNG"))
        except Exception:                       # noqa: BLE001
            return False
