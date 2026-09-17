"""Start-up: build the database on first run, then show the window."""

from __future__ import annotations

import sys
import traceback

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMessageBox, QSplashScreen

from . import APP_NAME, ORG_NAME, VERSION
from .config import Settings
from .db import Database
from .seed import backfill, is_seeded
from .ui.main_window import MainWindow, app_icon
from .ui.theme import palette, stylesheet


def _splash(theme: str) -> QSplashScreen:
    c = palette(theme)
    pixmap = QPixmap(460, 190)
    pixmap.fill(QColor(c["panel"]))
    painter = QPainter(pixmap)
    painter.setPen(QColor(c["line"]))
    painter.drawRect(0, 0, 459, 189)
    painter.setPen(QColor(c["ink"]))
    title = QFont()
    title.setPointSize(19)
    title.setWeight(QFont.Bold)
    painter.setFont(title)
    painter.drawText(28, 70, APP_NAME)
    painter.setPen(QColor(c["ink_dim"]))
    body = QFont()
    body.setPointSize(10)
    painter.setFont(body)
    painter.drawText(28, 96, "PC hardware prices through the memory shortage")
    painter.setPen(QColor(c["rise"]))
    painter.drawLine(28, 116, 432, 116)
    painter.end()
    splash = QSplashScreen(pixmap)
    splash.setWindowFlag(Qt.WindowStaysOnTopHint, True)
    return splash


def main() -> int:
    QApplication.setApplicationName(APP_NAME)
    QApplication.setApplicationVersion(VERSION)
    QApplication.setOrganizationName(ORG_NAME)
    if hasattr(Qt, "AA_EnableHighDpiScaling"):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setWindowIcon(app_icon())
    app.setQuitOnLastWindowClosed(False)      # the tray keeps it alive

    settings = Settings.load()
    app.setStyleSheet(stylesheet(settings.theme))

    try:
        db = Database()
    except Exception as exc:                  # noqa: BLE001
        QMessageBox.critical(None, APP_NAME,
                             f"The price database could not be opened.\n\n{exc}")
        return 1

    splash = None
    if not is_seeded(db):
        splash = _splash(settings.theme)
        splash.show()
        splash.showMessage("Building price history\u2026", Qt.AlignBottom | Qt.AlignLeft,
                           QColor(palette(settings.theme)["ink_dim"]))
        app.processEvents()

        def report(done: int, total: int) -> None:
            splash.showMessage(f"Building price history\u2026  {done}/{total}",
                               Qt.AlignBottom | Qt.AlignLeft,
                               QColor(palette(settings.theme)["ink_dim"]))
            app.processEvents()

        try:
            backfill(db, report)
        except Exception as exc:              # noqa: BLE001
            splash.close()
            QMessageBox.critical(None, APP_NAME,
                                 f"The history could not be built.\n\n{exc}")
            return 1
    else:
        # top up whatever days passed since the app was last open
        try:
            backfill(db)
        except Exception:                     # noqa: BLE001
            traceback.print_exc()

    window = MainWindow(db, settings)
    app.aboutToQuit.connect(window.fetcher.shutdown)   # never leave the thread running
    window.show()
    if splash is not None:
        splash.finish(window)

    QTimer.singleShot(0, window.raise_)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
