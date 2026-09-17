"""Settings: polling, appearance, notifications, data sources, active alerts."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFormLayout, QFrame,
                               QGroupBox, QHBoxLayout, QLabel, QMessageBox,
                               QLineEdit, QPushButton, QScrollArea, QSpinBox,
                               QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget, QHeaderView)

from .. import calibrate, marketdata
from ..config import CURRENCIES
from ..marketdata import DEFAULT_FRED_SERIES
from ..paths import data_dir, sources_path
from ..sources import HttpSource

SOURCES_TEMPLATE = {
    "retailer": "my-retailer",
    "timeout": 12,
    "currency": "EUR",
    "products": {
        "nvme-sn850x-2tb": {
            "url": "https://example.com/wd-black-sn850x-2tb",
            "selector": "span.price",
            "regex": "([0-9][0-9.,]*)",
        }
    },
}


class SettingsView(QWidget):
    changed = Signal()
    theme_changed = Signal(str)
    notice = Signal(str)

    def __init__(self, db, settings, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.db = db
        self.settings = settings
        self._loading = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 12)
        outer.setSpacing(12)

        title = QLabel("Settings")
        title.setObjectName("Heading")
        outer.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(14)
        layout.addWidget(self._updates_group())
        layout.addWidget(self._appearance_group())
        layout.addWidget(self._notifications_group())
        layout.addWidget(self._data_group())
        layout.addWidget(self._index_group())
        layout.addWidget(self._alerts_group())
        layout.addStretch(1)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

    # -- groups -----------------------------------------------------------
    def _updates_group(self) -> QGroupBox:
        box = QGroupBox("Updates")
        form = QFormLayout(box)
        form.setSpacing(9)

        self.interval = QSpinBox()
        self.interval.setRange(1, 180)
        self.interval.setSuffix(" minutes")
        self.interval.setValue(self.settings.poll_minutes)
        self.interval.valueChanged.connect(self._save)
        form.addRow("Check for new prices every", self.interval)

        self.background = QCheckBox("Keep checking while the window is minimised")
        self.background.setChecked(self.settings.poll_when_minimised)
        self.background.toggled.connect(self._save)
        form.addRow("", self.background)

        self.tray = QCheckBox("Close to the notification area instead of quitting")
        self.tray.setChecked(self.settings.minimise_to_tray)
        self.tray.toggled.connect(self._save)
        form.addRow("", self.tray)
        return box

    def _appearance_group(self) -> QGroupBox:
        box = QGroupBox("Appearance")
        form = QFormLayout(box)
        form.setSpacing(9)

        self.theme = QComboBox()
        self.theme.addItem("Dark", "dark")
        self.theme.addItem("Light", "light")
        self.theme.setCurrentIndex(0 if self.settings.theme == "dark" else 1)
        self.theme.currentIndexChanged.connect(self._on_theme)
        form.addRow("Theme", self.theme)

        self.currency = QComboBox()
        for code in CURRENCIES:
            self.currency.addItem(code, code)
        index = self.currency.findData(self.settings.currency)
        self.currency.setCurrentIndex(max(index, 0))
        self.currency.currentIndexChanged.connect(self._save)
        form.addRow("Currency symbol", self.currency)

        note = QLabel("The symbol is cosmetic. Prices are stored in whatever currency "
                      "your sources quote.")
        note.setObjectName("CardFoot")
        note.setWordWrap(True)
        form.addRow("", note)

        self.chart_mode = QComboBox()
        self.chart_mode.addItem("Price", "price")
        self.chart_mode.addItem("Change since start of view", "percent")
        self.chart_mode.setCurrentIndex(0 if self.settings.default_chart_mode == "price" else 1)
        self.chart_mode.currentIndexChanged.connect(self._save)
        form.addRow("Charts open in", self.chart_mode)
        return box

    def _notifications_group(self) -> QGroupBox:
        box = QGroupBox("Notifications")
        form = QFormLayout(box)
        form.setSpacing(9)

        self.notify = QCheckBox("Show a desktop notification when an alert fires")
        self.notify.setChecked(self.settings.notifications)
        self.notify.toggled.connect(self._save)
        form.addRow("", self.notify)

        self.threshold = QSpinBox()
        self.threshold.setRange(1, 50)
        self.threshold.setSuffix(" %")
        self.threshold.setValue(int(self.settings.notify_threshold_pct))
        self.threshold.valueChanged.connect(self._save)
        form.addRow("Default alert threshold", self.threshold)
        return box

    def _data_group(self) -> QGroupBox:
        box = QGroupBox("Price sources")
        layout = QVBoxLayout(box)
        layout.setSpacing(9)

        explain = QLabel(
            "Out of the box the app runs on a modelled reconstruction of the "
            "memory shortage, so the charts work offline and the numbers match "
            "published contract-price data. Point it at real shops by writing a "
            "sources.json file; live prices then take priority and are labelled "
            "with the retailer's name."
        )
        explain.setObjectName("CardFoot")
        explain.setWordWrap(True)
        layout.addWidget(explain)

        self.live = QCheckBox("Use sources.json for live prices")
        self.live.setChecked(self.settings.use_live_sources)
        self.live.toggled.connect(self._save)
        layout.addWidget(self.live)

        self.source_status = QLabel()
        self.source_status.setObjectName("CardFoot")
        self.source_status.setWordWrap(True)
        layout.addWidget(self.source_status)

        row = QHBoxLayout()
        create = QPushButton("Create a starter sources.json")
        create.clicked.connect(self._create_sources)
        open_folder = QPushButton("Open data folder")
        open_folder.setObjectName("Ghost")
        open_folder.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(data_dir()))))
        row.addWidget(create)
        row.addWidget(open_folder)
        row.addStretch(1)
        layout.addLayout(row)

        self._refresh_source_status()
        return box

    def _index_group(self) -> QGroupBox:
        box = QGroupBox("Market index")
        layout = QVBoxLayout(box)
        layout.setSpacing(9)

        explain = QLabel(
            "The shipped curve runs on published contract pricing up to September "
            "2026; past that it was a straight-line guess. Point it at a live index "
            "and the app measures how far this category moved for each point the "
            "index moved, then carries the curve forward on that relationship. "
            "History before the handover date never changes."
        )
        explain.setObjectName("CardFoot")
        explain.setWordWrap(True)
        layout.addWidget(explain)

        form = QFormLayout()
        form.setSpacing(9)

        self.index_provider = QComboBox()
        self.index_provider.addItem("Off \u2014 use the shipped curve", "off")
        self.index_provider.addItem("FRED producer price index", "fred")
        self.index_provider.addItem("A CSV address I supply", "csv")
        index = self.index_provider.findData(self.settings.index_provider)
        self.index_provider.setCurrentIndex(max(index, 0))
        self.index_provider.currentIndexChanged.connect(self._on_provider)
        form.addRow("Source", self.index_provider)

        self.fred_key = QLineEdit(self.settings.fred_api_key)
        self.fred_key.setPlaceholderText("free from fred.stlouisfed.org")
        self.fred_key.setEchoMode(QLineEdit.PasswordEchoOnEdit)
        self.fred_key.editingFinished.connect(self._save)
        form.addRow("FRED key", self.fred_key)

        self.fred_series = QLineEdit(
            self.settings.fred_series.get("all", DEFAULT_FRED_SERIES["ram"]))
        self.fred_series.setPlaceholderText(DEFAULT_FRED_SERIES["ram"])
        self.fred_series.editingFinished.connect(self._save)
        form.addRow("FRED series id", self.fred_series)

        self.csv_url = QLineEdit(self.settings.index_csv_urls.get("all", ""))
        self.csv_url.setPlaceholderText("https://example.com/memory-index.csv")
        self.csv_url.editingFinished.connect(self._save)
        form.addRow("CSV address", self.csv_url)

        self.index_hours = QSpinBox()
        self.index_hours.setRange(1, 168)
        self.index_hours.setSuffix(" hours")
        self.index_hours.setValue(self.settings.index_refresh_hours)
        self.index_hours.valueChanged.connect(self._save)
        form.addRow("Refresh every", self.index_hours)
        layout.addLayout(form)

        row = QHBoxLayout()
        self.index_test = QPushButton("Fetch it now")
        self.index_test.clicked.connect(self._test_index)
        row.addWidget(self.index_test)
        row.addStretch(1)
        layout.addLayout(row)

        self.index_status = QLabel()
        self.index_status.setObjectName("CardFoot")
        self.index_status.setWordWrap(True)
        layout.addWidget(self.index_status)

        divider = QLabel("Learning from real prices")
        divider.setObjectName("SubHeading")
        layout.addWidget(divider)

        self.auto_calibrate = QCheckBox(
            "Re-fit each product against the prices your sources report")
        self.auto_calibrate.setChecked(self.settings.auto_calibrate)
        self.auto_calibrate.toggled.connect(self._save)
        layout.addWidget(self.auto_calibrate)

        calib_note = QLabel(
            "Once a product has a few days of real quotes behind it, the price you "
            "typed in when you added it is replaced by one measured from the data. "
            "Separating the starting price from the trend needs the curve to have "
            "moved a few percent while the app was watching, so on a flat month it "
            "will correct the price and say it could not do the rest."
        )
        calib_note.setObjectName("CardFoot")
        calib_note.setWordWrap(True)
        layout.addWidget(calib_note)

        row2 = QHBoxLayout()
        self.calibrate_now = QPushButton("Re-fit now")
        self.calibrate_now.setObjectName("Ghost")
        self.calibrate_now.clicked.connect(self._run_calibration)
        row2.addWidget(self.calibrate_now)
        row2.addStretch(1)
        layout.addLayout(row2)

        self.calibrate_status = QLabel()
        self.calibrate_status.setObjectName("CardFoot")
        self.calibrate_status.setWordWrap(True)
        layout.addWidget(self.calibrate_status)

        self._on_provider()
        self._refresh_index_status()
        return box

    def _on_provider(self) -> None:
        provider = self.index_provider.currentData()
        for widget in (self.fred_key, self.fred_series):
            widget.setEnabled(provider == "fred")
        self.csv_url.setEnabled(provider == "csv")
        self.index_test.setEnabled(provider != "off")
        self._save()
        self._refresh_index_status()

    def _refresh_index_status(self) -> None:
        when = self.db.get_meta("index_refreshed")
        feed = self.db.get_meta("index_feed")
        if self.index_provider.currentData() == "off":
            self.index_status.setText(
                "Running on the shipped curve. Everything after 15 September 2026 "
                "is extrapolated.")
        elif when and feed:
            try:
                stamp = datetime.fromisoformat(when).astimezone().strftime("%d %b %H:%M")
            except ValueError:
                stamp = when
            self.index_status.setText(f"Last fetched {stamp} from {feed}.")
        else:
            self.index_status.setText("Not fetched yet.")

        ready, any_data = calibrate.candidates(self.db)
        last = self.db.get_meta("last_calibration")
        if any_data:
            tail = ""
            if last:
                try:
                    tail = (" \u00b7 last re-fitted "
                            + datetime.fromisoformat(last).astimezone().strftime("%d %b %H:%M"))
                except ValueError:
                    tail = ""
            self.calibrate_status.setText(
                f"{ready} of {any_data} product(s) with real quotes have enough "
                f"data to fit{tail}.")
        else:
            self.calibrate_status.setText(
                "No real quotes yet \u2014 set up a retailer in Price sources first.")

    def _test_index(self) -> None:
        self._save()
        self.index_test.setEnabled(False)
        self.index_status.setText("Fetching\u2026")
        QApplication.processEvents()
        try:
            written, problem = marketdata.refresh(self.db, self.settings)
        except Exception as exc:                            # noqa: BLE001
            written, problem = 0, str(exc)
        if written:
            report = marketdata.load_into_curve(self.db)
            detail = "; ".join(f"{k}: {v}" for k, v in report.items())
            self.index_status.setText(
                f"Fetched {written} point(s). {detail or 'not enough overlap to fit yet'}")
            self.notice.emit("Market index updated")
        else:
            self.index_status.setText(problem or "Nothing came back.")
        self.index_test.setEnabled(True)

    def _run_calibration(self) -> None:
        self.calibrate_now.setEnabled(False)
        QApplication.processEvents()
        try:
            fits = calibrate.calibrate_all(self.db)
        except Exception as exc:                            # noqa: BLE001
            QMessageBox.warning(self, "Could not re-fit", str(exc))
            fits = []
        self.calibrate_now.setEnabled(True)
        self._refresh_index_status()
        if fits:
            best = fits[0]
            self.notice.emit(f"Re-fitted {len(fits)} product(s) \u2014 {best.note()}")
            self.changed.emit()
        else:
            self.notice.emit("Nothing has enough real price data to re-fit yet")

    def _alerts_group(self) -> QGroupBox:
        box = QGroupBox("Active alerts")
        layout = QVBoxLayout(box)
        layout.setSpacing(9)

        self.alerts_table = QTableWidget(0, 4)
        self.alerts_table.setHorizontalHeaderLabels(
            ["Product", "Triggers at", "Measured from", ""])
        self.alerts_table.verticalHeader().setVisible(False)
        self.alerts_table.setShowGrid(False)
        self.alerts_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.alerts_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.alerts_table.setMaximumHeight(190)
        header = self.alerts_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for col in (1, 2, 3):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.alerts_table.cellClicked.connect(self._maybe_delete_alert)
        layout.addWidget(self.alerts_table)

        self.alerts_note = QLabel()
        self.alerts_note.setObjectName("CardFoot")
        layout.addWidget(self.alerts_note)
        self.refresh_alerts()
        return box

    # -- behaviour --------------------------------------------------------
    def refresh_alerts(self) -> None:
        rules = self.db.alerts(enabled_only=False)
        self.alerts_table.setRowCount(len(rules))
        for r, rule in enumerate(rules):
            self.alerts_table.setItem(r, 0, QTableWidgetItem(rule["name"]))
            self.alerts_table.setItem(
                r, 1, QTableWidgetItem(f"\u00b1{float(rule['threshold']):.1f}%"))
            self.alerts_table.setItem(
                r, 2, QTableWidgetItem(self.settings.money(rule["reference"])))
            remove = QTableWidgetItem("Remove")
            remove.setData(Qt.UserRole, int(rule["id"]))
            remove.setForeground(Qt.red)
            self.alerts_table.setItem(r, 3, remove)
        self.alerts_note.setText(
            "Set an alert from any category view: select one product, then "
            "\u201cAlert me when this moves\u201d."
            if not rules else f"{len(rules)} alert(s) armed."
        )

    def _maybe_delete_alert(self, row: int, column: int) -> None:
        if column != 3:
            return
        item = self.alerts_table.item(row, column)
        if not item:
            return
        self.db.delete_alert(int(item.data(Qt.UserRole)))
        self.refresh_alerts()
        self.notice.emit("Alert removed")

    def _refresh_source_status(self) -> None:
        source = HttpSource()
        if source.available():
            count = len(source.config.get("products", {}))
            self.source_status.setText(
                f"sources.json found: {count} product(s) mapped to {source.name}.")
        else:
            self.source_status.setText(
                f"No live sources yet \u2014 {source.error or 'sources.json is empty'}.")

    def _create_sources(self) -> None:
        path = sources_path()
        if path.exists():
            answer = QMessageBox.question(
                self, "Replace sources.json?",
                "A sources.json already exists. Replace it with the starter template?")
            if answer != QMessageBox.Yes:
                return
        try:
            path.write_text(json.dumps(SOURCES_TEMPLATE, indent=2), encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, "Could not write the file", str(exc))
            return
        self._refresh_source_status()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        self.notice.emit(f"Starter template written to {path}")

    def _on_theme(self) -> None:
        self._save()
        self.theme_changed.emit(self.theme.currentData())

    def _save(self) -> None:
        if self._loading:
            return
        s = self.settings
        s.poll_minutes = self.interval.value()
        s.poll_when_minimised = self.background.isChecked()
        s.minimise_to_tray = self.tray.isChecked()
        s.theme = self.theme.currentData()
        s.currency = self.currency.currentData()
        s.default_chart_mode = self.chart_mode.currentData()
        s.notifications = self.notify.isChecked()
        s.notify_threshold_pct = float(self.threshold.value())
        s.use_live_sources = self.live.isChecked()
        if hasattr(self, "index_provider"):
            s.index_provider = self.index_provider.currentData()
            s.fred_api_key = self.fred_key.text().strip()
            series = self.fred_series.text().strip()
            s.fred_series = {"all": series} if series else {}
            if series:
                s.fred_series.update({c: series for c in DEFAULT_FRED_SERIES})
            url = self.csv_url.text().strip()
            s.index_csv_urls = {"all": url} if url else {}
            s.index_refresh_hours = self.index_hours.value()
            s.auto_calibrate = self.auto_calibrate.isChecked()
        s.save()
        self._refresh_source_status()
        self.changed.emit()

    def apply_theme(self, theme: str) -> None:
        self._loading = True
        self.theme.setCurrentIndex(0 if theme == "dark" else 1)
        self._loading = False
        self.refresh_alerts()
