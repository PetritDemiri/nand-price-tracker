"""Settings: polling, appearance, notifications, data sources, active alerts."""

from __future__ import annotations

import json
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QFrame,
                               QGroupBox, QHBoxLayout, QLabel, QMessageBox,
                               QPushButton, QScrollArea, QSpinBox,
                               QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget, QHeaderView)

from ..config import CURRENCIES
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
        s.save()
        self._refresh_source_status()
        self.changed.emit()

    def apply_theme(self, theme: str) -> None:
        self._loading = True
        self.theme.setCurrentIndex(0 if theme == "dark" else 1)
        self._loading = False
        self.refresh_alerts()
