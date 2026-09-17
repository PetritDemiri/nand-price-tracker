"""User settings, stored as JSON next to the database."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict

from .paths import config_path

CURRENCIES = {
    "EUR": "\u20ac",
    "USD": "$",
    "GBP": "\u00a3",
    "CHF": "CHF ",
    "PLN": "z\u0142 ",
}


@dataclass
class Settings:
    theme: str = "dark"                  # dark | light
    poll_minutes: int = 10               # 1..180
    currency: str = "EUR"
    notifications: bool = True
    notify_threshold_pct: float = 2.0    # move since last notification
    minimise_to_tray: bool = True
    poll_when_minimised: bool = True
    use_live_sources: bool = False       # requires sources.json
    default_chart_mode: str = "price"    # price | percent
    log_scale: bool = False
    last_view: str = "dashboard"
    window_geometry: str = ""            # base64 QByteArray
    extra: Dict[str, Any] = field(default_factory=dict)

    # -- persistence ------------------------------------------------------
    @classmethod
    def load(cls) -> "Settings":
        path = config_path()
        if not path.exists():
            return cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in raw.items() if k in known})

    def save(self) -> None:
        try:
            config_path().write_text(
                json.dumps(asdict(self), indent=2), encoding="utf-8"
            )
        except OSError:
            pass  # a read-only profile must not take the app down

    # -- helpers ----------------------------------------------------------
    @property
    def symbol(self) -> str:
        return CURRENCIES.get(self.currency, "\u20ac")

    def money(self, value: float | None, decimals: int = 2) -> str:
        if value is None:
            return "\u2014"
        return f"{self.symbol}{value:,.{decimals}f}"

    @property
    def poll_seconds(self) -> int:
        return max(60, int(self.poll_minutes) * 60)
