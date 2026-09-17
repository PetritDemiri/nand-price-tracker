"""Write nandtrack.ico so the built .exe has a proper Windows icon.

Run automatically by build_exe.bat; needs PySide6, which you already have.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPainterPath, QPixmap

SIZES = (16, 24, 32, 48, 64, 128, 256)


def draw(size: int) -> QImage:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    scale = size / 64.0
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.scale(scale, scale)

    chassis = QPainterPath()
    chassis.addRoundedRect(2, 2, 60, 60, 13, 13)
    painter.fillPath(chassis, QColor("#141A23"))
    painter.setPen(QColor("#2A3441"))
    painter.drawPath(chassis)

    trace = QPainterPath()
    trace.moveTo(13, 48)
    trace.lineTo(25, 42)
    trace.lineTo(35, 34)
    trace.lineTo(44, 18)
    trace.lineTo(51, 13)
    pen = painter.pen()
    pen.setColor(QColor("#F2994A"))
    pen.setWidthF(max(2.0, 5.0))
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.drawPath(trace)
    painter.end()
    return pixmap.toImage()


def main() -> int:
    QGuiApplication(sys.argv)
    target = Path(__file__).with_name("nandtrack.ico")
    images = [draw(s) for s in SIZES]
    # QImage cannot write multi-size .ico directly; the largest frame is enough
    # for Windows Explorer, which downsamples it.
    if not images[-1].save(str(target), "ICO"):
        print("could not write nandtrack.ico", file=sys.stderr)
        return 1
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
