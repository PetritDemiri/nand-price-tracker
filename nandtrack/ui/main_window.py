"""The application shell."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (QApplication, QButtonGroup, QFrame, QHBoxLayout,
                               QLabel, QMainWindow, QMenu, QPushButton,
                               QStackedWidget, QSystemTrayIcon, QVBoxLayout,
                               QWidget)

from .. import APP_NAME, APP_TAGLINE, VERSION, alerts
from ..catalog import CATEGORIES, CATEGORY_ORDER
from ..config import Settings
from ..db import Database
from ..fetcher import FetchController
from .category import CategoryView
from .dashboard import Dashboard
from .settings_view import SettingsView
from .theme import palette, stylesheet


def app_icon(theme: str = "dark") -> QIcon:
    """A drawn icon, so the one-file build carries no external assets."""
    size = 64
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    body = QPainterPath()
    body.addRoundedRect(4, 4, size - 8, size - 8, 14, 14)
    painter.fillPath(body, QColor("#161C25"))
    painter.setPen(QColor("#2A3441"))
    painter.drawPath(body)
    # a rising trace
    trace = QPainterPath()
    trace.moveTo(14, 46)
    trace.lineTo(26, 41)
    trace.lineTo(36, 34)
    trace.lineTo(44, 20)
    trace.lineTo(50, 15)
    pen = painter.pen()
    pen.setColor(QColor("#F2994A"))
    pen.setWidth(5)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.drawPath(trace)
    painter.end()
    return QIcon(pixmap)


class MainWindow(QMainWindow):
    themed = Signal(str)

    def __init__(self, db: Database, settings: Settings) -> None:
        super().__init__()
        self.db = db
        self.settings = settings
        self._views: Dict[str, QWidget] = {}
        self._buttons: Dict[str, QPushButton] = {}
        self._last_poll: Optional[datetime] = db.last_ts()
        self._quitting = False

        self.setWindowTitle(f"{APP_NAME} \u2014 {APP_TAGLINE}")
        self.setWindowIcon(app_icon())
        self.resize(1360, 860)
        self.setMinimumSize(1040, 640)

        self._build_ui()
        self._build_tray()
        self.apply_theme(settings.theme, refresh=False)
        self.refresh_all()
        self._start_fetching()

        self._clock = QTimer(self)
        self._clock.timeout.connect(self._update_status)
        self._clock.start(20_000)

    # -- construction -----------------------------------------------------
    def _build_ui(self) -> None:
        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._build_nav())

        self.stack = QStackedWidget()
        body.addWidget(self.stack, 1)
        outer.addLayout(body, 1)
        outer.addWidget(self._build_status())

        self.dashboard = Dashboard(self.db, self.settings)
        self.dashboard.open_category.connect(self.show_view)
        self.dashboard.open_product.connect(self._open_product)
        self._register("dashboard", self.dashboard)

        for key in CATEGORY_ORDER:
            view = CategoryView(self.db, self.settings, key)
            view.watch_changed.connect(self._on_watch_changed)
            view.alert_created.connect(self.flash)
            self._register(key, view)

        watchlist = CategoryView(self.db, self.settings, None)
        watchlist.watch_changed.connect(self._on_watch_changed)
        watchlist.alert_created.connect(self.flash)
        self._register("watchlist", watchlist)

        self.settings_view = SettingsView(self.db, self.settings)
        self.settings_view.changed.connect(self._on_settings_changed)
        self.settings_view.theme_changed.connect(self.apply_theme)
        self.settings_view.notice.connect(self.flash)
        self._register("settings", self.settings_view)

        self.setCentralWidget(central)
        self.show_view(self.settings.last_view or "dashboard")

    def _build_nav(self) -> QWidget:
        rail = QFrame()
        rail.setObjectName("NavRail")
        rail.setFixedWidth(224)
        layout = QVBoxLayout(rail)
        layout.setContentsMargins(0, 18, 0, 12)
        layout.setSpacing(0)

        brand = QVBoxLayout()
        brand.setContentsMargins(17, 0, 14, 14)
        brand.setSpacing(1)
        mark = QLabel(APP_NAME)
        mark.setObjectName("WordMark")
        sub = QLabel("prices since September 2025")
        sub.setObjectName("WordMarkSub")
        sub.setWordWrap(True)
        brand.addWidget(mark)
        brand.addWidget(sub)
        layout.addLayout(brand)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        layout.addWidget(self._nav_button("dashboard", "Dashboard"))
        layout.addWidget(self._nav_label("Categories"))
        for key in CATEGORY_ORDER:
            layout.addWidget(self._nav_button(key, CATEGORIES[key]["label"],
                                              CATEGORIES[key]["colour"]))
        layout.addWidget(self._nav_label("Yours"))
        layout.addWidget(self._nav_button("watchlist", "Watchlist"))
        layout.addStretch(1)
        layout.addWidget(self._nav_button("settings", "Settings"))

        version = QLabel(f"version {VERSION}")
        version.setObjectName("CardFoot")
        version.setContentsMargins(17, 8, 0, 0)
        layout.addWidget(version)
        return rail

    def _nav_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("NavGroup")
        return label

    def _nav_button(self, key: str, text: str, colour: Optional[str] = None) -> QPushButton:
        button = QPushButton(text)
        button.setCheckable(True)
        button.setCursor(Qt.PointingHandCursor)
        if colour:
            dot = QPixmap(10, 10)
            dot.fill(Qt.transparent)
            painter = QPainter(dot)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setBrush(QColor(colour))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(1, 1, 8, 8)
            painter.end()
            button.setIcon(QIcon(dot))
            button.setIconSize(QSize(10, 10))
        button.clicked.connect(lambda: self.show_view(key))
        self._group.addButton(button)
        self._buttons[key] = button
        return button

    def _build_status(self) -> QWidget:
        strip = QFrame()
        strip.setObjectName("StatusStrip")
        strip.setFixedHeight(34)
        layout = QHBoxLayout(strip)
        layout.setContentsMargins(16, 0, 14, 0)
        layout.setSpacing(8)

        self.status_dot = QLabel("\u25cf")
        self.status_dot.setObjectName("StatusDot")
        self.status_text = QLabel()
        self.status_text.setObjectName("StatusText")
        layout.addWidget(self.status_dot)
        layout.addWidget(self.status_text)
        layout.addStretch(1)

        self.flash_text = QLabel()
        self.flash_text.setObjectName("StatusText")
        layout.addWidget(self.flash_text)

        refresh = QPushButton("Check now")
        refresh.setObjectName("Ghost")
        refresh.clicked.connect(self._manual_poll)
        layout.addWidget(refresh)
        return strip

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip(APP_NAME)
        menu = QMenu()
        show = QAction("Open NANDTrack", self)
        show.triggered.connect(self._restore_window)
        check = QAction("Check prices now", self)
        check.triggered.connect(self._manual_poll)
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self._really_quit)
        menu.addAction(show)
        menu.addAction(check)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: self._restore_window()
            if reason == QSystemTrayIcon.Trigger else None)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

    def _register(self, key: str, widget: QWidget) -> None:
        self._views[key] = widget
        self.stack.addWidget(widget)

    # -- navigation -------------------------------------------------------
    def show_view(self, key: str) -> None:
        widget = self._views.get(key)
        if widget is None:
            return
        self.stack.setCurrentWidget(widget)
        button = self._buttons.get(key)
        if button:
            button.setChecked(True)
        if hasattr(widget, "refresh"):
            widget.refresh()
        self.settings.last_view = key
        self.settings.save()

    def _open_product(self, product_id: int) -> None:
        row = self.db.product(product_id)
        if not row:
            return
        self.show_view(row["category"])
        view = self._views.get(row["category"])
        if isinstance(view, CategoryView):
            view.select_product(product_id)

    # -- polling ----------------------------------------------------------
    def _start_fetching(self) -> None:
        self.fetcher = FetchController(
            self.db.path, self.settings.poll_seconds, self.settings.use_live_sources, self)
        self.fetcher.cycle_started.connect(lambda: self._set_status("checking"))
        self.fetcher.cycle_finished.connect(self._on_cycle)
        self.fetcher.start()

    def _manual_poll(self) -> None:
        self._set_status("checking")
        self.fetcher.poll_now()

    def _on_cycle(self, movements: List, source_label: str, error: str) -> None:
        self._last_poll = datetime.now(timezone.utc)
        self._source_label = source_label
        self._set_status("error" if error else "ok", error)
        if movements:
            self.refresh_all()
            biggest = max(movements, key=lambda m: abs(m.change_pct))
            self.flash(f"{len(movements)} price(s) moved \u00b7 biggest: "
                       f"{biggest.name} {biggest.change_pct:+.1f}%")
        self._check_alerts()

    def _check_alerts(self) -> None:
        for hit in alerts.evaluate(self.db):
            message = hit.body(self.settings.money)
            self.flash(message)
            if self.settings.notifications and QSystemTrayIcon.supportsMessages():
                self.tray.showMessage(hit.title(), message, app_icon(), 8000)
        if isinstance(self._views.get("settings"), SettingsView):
            self._views["settings"].refresh_alerts()

    # -- status -----------------------------------------------------------
    def _set_status(self, state: str, detail: str = "") -> None:
        c = palette(self.settings.theme)
        colour = {"ok": c["fall"], "checking": c["focus"], "error": c["rise"]}.get(state, c["flat"])
        self.status_dot.setStyleSheet(f"color:{colour};")
        self._status_state = state
        self._status_detail = detail
        self._update_status()

    def _update_status(self) -> None:
        state = getattr(self, "_status_state", "ok")
        detail = getattr(self, "_status_detail", "")
        source = getattr(self, "_source_label", "") or "modelled curve"
        if state == "checking":
            self.status_text.setText("Checking prices\u2026")
            return
        if self._last_poll:
            ago = (datetime.now(timezone.utc) - self._last_poll).total_seconds()
            when = "just now" if ago < 90 else (
                f"{int(ago // 60)} min ago" if ago < 5400 else
                self._last_poll.astimezone().strftime("%d %b %H:%M"))
        else:
            when = "not yet"
        text = f"Last updated {when} \u00b7 {source} \u00b7 next check in " \
               f"{self.settings.poll_minutes} min"
        if state == "error" and detail:
            text = f"Last updated {when} \u00b7 {detail}"
        self.status_text.setText(text)

    def flash(self, message: str) -> None:
        self.flash_text.setText(message)
        QTimer.singleShot(9000, lambda: self.flash_text.setText(""))

    # -- refresh ----------------------------------------------------------
    def refresh_all(self) -> None:
        current = self.stack.currentWidget()
        if hasattr(current, "refresh"):
            current.refresh()
        elif hasattr(current, "refresh_alerts"):
            current.refresh_alerts()

    def _on_watch_changed(self) -> None:
        self.dashboard.refresh()
        watchlist = self._views.get("watchlist")
        if isinstance(watchlist, CategoryView) and watchlist is not self.stack.currentWidget():
            watchlist.refresh()

    def _on_settings_changed(self) -> None:
        self.fetcher.apply_settings(self.settings.poll_seconds, self.settings.use_live_sources)
        self._update_status()

    # -- theming ----------------------------------------------------------
    def apply_theme(self, theme: str, refresh: bool = True) -> None:
        self.settings.theme = theme
        self.settings.save()
        app = QApplication.instance()
        if app:
            app.setStyleSheet(stylesheet(theme))
        if refresh:
            for view in self._views.values():
                if hasattr(view, "apply_theme"):
                    view.apply_theme(theme)
        self._set_status(getattr(self, "_status_state", "ok"),
                         getattr(self, "_status_detail", ""))
        self.themed.emit(theme)

    # -- window lifecycle -------------------------------------------------
    def _restore_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _really_quit(self) -> None:
        self._quitting = True
        self.close()
        app = QApplication.instance()
        if app:
            app.quit()

    def closeEvent(self, event) -> None:  # noqa: N802
        if (not self._quitting and self.settings.minimise_to_tray
                and QSystemTrayIcon.isSystemTrayAvailable() and self.tray.isVisible()):
            event.ignore()
            self.hide()
            if QSystemTrayIcon.supportsMessages():
                self.tray.showMessage(
                    APP_NAME,
                    "Still watching prices in the background. Right-click here to quit.",
                    app_icon(), 4000)
            return
        try:
            self.fetcher.shutdown()
        except Exception:                     # noqa: BLE001
            pass
        self.settings.save()
        self.db.close()
        event.accept()
