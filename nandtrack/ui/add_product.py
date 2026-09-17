"""Add a product without touching the code.

You give it a name and what the part costs today; it works the September 2025
baseline backwards off the category curve, writes the product, and backfills a
year of history so the new line starts where every other line starts. If you
also paste a shop URL it registers the scraping rule, so the part picks up live
prices on the next poll.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFormLayout, QGroupBox, QLabel,
                               QLineEdit, QSpinBox, QVBoxLayout, QWidget)

from ..catalog import CATEGORIES, CATEGORY_ORDER
from ..db import Database
from ..market import BASELINE_DATE, implied_baseline
from ..sources import write_rule

# How hard a part rides its category's curve, in plain words.
TREND_CHOICES = [
    ("Moves with the rest of the category", 1.0),
    ("Moves less than the rest \u2014 older or budget parts", 0.65),
    ("Moves more than the rest \u2014 high capacity or halo parts", 1.45),
]


def slugify(*parts: str) -> str:
    text = " ".join(p for p in parts if p)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text[:60] or "product"


class AddProductDialog(QDialog):
    """Returns a product id through `created_id` once accepted."""

    def __init__(self, db: Database, settings, category: Optional[str] = None,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.db = db
        self.settings = settings
        self.created_id: Optional[int] = None

        self.setWindowTitle("Add a product")
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(9)

        self.name = QLineEdit()
        self.name.setPlaceholderText("Samsung 9100 PRO 2TB")
        self.name.textChanged.connect(self._on_name_changed)
        form.addRow("Name", self.name)

        self.category = QComboBox()
        for key in CATEGORY_ORDER:
            self.category.addItem(CATEGORIES[key]["label"], key)
        if category:
            index = self.category.findData(category)
            self.category.setCurrentIndex(max(index, 0))
        self.category.currentIndexChanged.connect(self._update_preview)
        form.addRow("Category", self.category)

        self.brand = QLineEdit()
        self.brand.setPlaceholderText("Samsung")
        self.brand.textChanged.connect(self._on_name_changed)
        form.addRow("Brand", self.brand)

        self.capacity = QSpinBox()
        self.capacity.setRange(0, 131072)
        self.capacity.setSuffix(" GB")
        self.capacity.setSpecialValueText("not applicable")
        self.capacity.setSingleStep(256)
        form.addRow("Capacity", self.capacity)

        self.form_factor = QComboBox()
        self.form_factor.setEditable(True)
        self.form_factor.addItems(
            ["", "M.2 2280", '2.5"', "DIMM", "SO-DIMM", "Dual-slot", "Triple-slot"])
        form.addRow("Form factor", self.form_factor)

        self.interface = QLineEdit()
        self.interface.setPlaceholderText("PCIe 5.0 x4")
        form.addRow("Specification", self.interface)

        self.price = QDoubleSpinBox()
        self.price.setRange(0.01, 99999.0)
        self.price.setDecimals(2)
        self.price.setValue(199.0)
        self.price.setPrefix(self.settings.symbol)
        self.price.valueChanged.connect(self._update_preview)
        form.addRow("Price", self.price)

        self.price_when = QComboBox()
        self.price_when.addItem("is what it costs today", "today")
        self.price_when.addItem("is what it cost on 1 September 2025", "baseline")
        self.price_when.currentIndexChanged.connect(self._update_preview)
        form.addRow("That price", self.price_when)

        self.trend = QComboBox()
        for label, scale in TREND_CHOICES:
            self.trend.addItem(label, scale)
        self.trend.currentIndexChanged.connect(self._update_preview)
        form.addRow("History", self.trend)

        self.sku = QLineEdit()
        self.sku.setPlaceholderText("generated from the name")
        form.addRow("Short id", self.sku)

        layout.addLayout(form)

        self.live_group = QGroupBox("Live price (optional)")
        self.live_group.setCheckable(True)
        self.live_group.setChecked(False)
        live_form = QFormLayout(self.live_group)
        self.url = QLineEdit()
        self.url.setPlaceholderText("https://shop.example/samsung-9100-pro-2tb")
        self.selector = QLineEdit()
        self.selector.setPlaceholderText("span.price")
        live_form.addRow("Product page", self.url)
        live_form.addRow("Price element", self.selector)
        live_hint = QLabel("Saved into sources.json. Turn on live sources in Settings "
                           "for it to be read.")
        live_hint.setObjectName("CardFoot")
        live_hint.setWordWrap(True)
        live_form.addRow("", live_hint)
        layout.addWidget(self.live_group)

        self.watch = QCheckBox("Follow this one on the dashboard")
        self.watch.setChecked(True)
        layout.addWidget(self.watch)

        self.preview = QLabel()
        self.preview.setObjectName("CardFoot")
        self.preview.setWordWrap(True)
        layout.addWidget(self.preview)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Add product")
        buttons.button(QDialogButtonBox.Ok).setObjectName("Primary")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        self._ok = buttons.button(QDialogButtonBox.Ok)
        layout.addWidget(buttons)

        self._update_preview()

    # -- helpers ----------------------------------------------------------
    def _suggested_sku(self) -> str:
        brand = self.brand.text().strip()
        name = self.name.text().strip()
        # "Samsung" + "Samsung 9100 PRO" should not become samsung-samsung-9100-pro
        if brand and name.lower().startswith(brand.lower()):
            brand = ""
        return slugify(brand, name)

    def _on_name_changed(self) -> None:
        if not self.sku.isModified():
            self.sku.setText(self._suggested_sku())
        self._update_preview()

    def _values(self) -> dict:
        category = self.category.currentData()
        scale = float(self.trend.currentData())
        price = float(self.price.value())
        if self.price_when.currentData() == "today":
            baseline = implied_baseline(category, price, scale)
        else:
            baseline = price
        return {
            "sku": self.sku.text().strip() or self._suggested_sku(),
            "name": self.name.text().strip(),
            "category": category,
            "brand": self.brand.text().strip() or "Unbranded",
            "capacity_gb": self.capacity.value() or None,
            "form_factor": self.form_factor.currentText().strip(),
            "interface": self.interface.text().strip(),
            "baseline": round(baseline, 2),
            "surge_scale": scale,
            "custom": 1,
        }

    def _update_preview(self) -> None:
        values = self._values()
        days = (datetime.now(timezone.utc).date() - BASELINE_DATE).days
        money = self.settings.money
        problem = ""
        if not values["name"]:
            problem = "Give it a name first."
        elif self.db.sku_exists(values["sku"]):
            problem = f"The short id \u201c{values['sku']}\u201d is already taken. Change it."
        self._ok.setEnabled(not problem)
        if problem:
            self.preview.setText(problem)
            return
        change = (self.price.value() / values["baseline"] - 1.0) * 100.0 \
            if self.price_when.currentData() == "today" else 0.0
        tail = (f" \u2014 a rise of {change:+.0f}% over the period"
                if self.price_when.currentData() == "today" else "")
        self.preview.setText(
            f"Starts from {money(values['baseline'])} on 1 September 2025{tail}. "
            f"About {days} days of history will be filled in so it lines up with "
            f"everything else."
        )

    def _accept(self) -> None:
        values = self._values()
        if not values["name"] or self.db.sku_exists(values["sku"]):
            return
        from ..seed import backfill          # imported late to avoid a cycle

        self.db.upsert_product(values)
        row = self.db.conn.execute(
            "SELECT id FROM products WHERE sku=?", (values["sku"],)).fetchone()
        if not row:
            self.reject()
            return
        self.created_id = int(row["id"])
        backfill(self.db)
        if self.watch.isChecked():
            self.db.set_watched(self.created_id, True)
        if self.live_group.isChecked() and self.url.text().strip():
            try:
                write_rule(values["sku"], self.url.text().strip(),
                           self.selector.text().strip())
            except OSError:
                pass
        self.accept()
