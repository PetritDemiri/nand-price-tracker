"""Where NANDTrack keeps its data.

On Windows this resolves to %APPDATA%\\NANDTrack, so a one-file .exe can live
anywhere (Desktop, a USB stick) and still keep its history between runs.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def data_dir() -> Path:
    """Per-user writable directory for the database, config and exports."""
    override = os.environ.get("NANDTRACK_HOME")
    if override:
        base = Path(override)
    elif sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "NANDTrack"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "NANDTrack"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "nandtrack"
    base.mkdir(parents=True, exist_ok=True)
    return base


def db_path() -> Path:
    return data_dir() / "prices.db"


def config_path() -> Path:
    return data_dir() / "settings.json"


def sources_path() -> Path:
    """Optional user-supplied live scraper definitions."""
    return data_dir() / "sources.json"


def exports_dir() -> Path:
    d = data_dir() / "exports"
    d.mkdir(parents=True, exist_ok=True)
    return d


def resource(*parts: str) -> Path:
    """Resolve a bundled read-only resource, PyInstaller-aware."""
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return root.joinpath(*parts)
