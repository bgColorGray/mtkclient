#!/usr/bin/env python3
"""Draw the app icon: a chip outline with a download arrow, rendered to PNG.

Original artwork, drawn with Qt so the build needs no image assets.
"""
import sys
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication

BG_TOP, BG_BOTTOM = QColor("#1e6fd9"), QColor("#0a47a1")
FG = QColor("#ffffff")


def draw(size: int) -> QImage:
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    u = size / 1024.0

    # Rounded square background with a vertical gradient.
    from PySide6.QtGui import QLinearGradient
    grad = QLinearGradient(0, 0, 0, size)
    grad.setColorAt(0, BG_TOP)
    grad.setColorAt(1, BG_BOTTOM)
    body = QPainterPath()
    body.addRoundedRect(QRectF(0, 0, size, size), 225 * u, 225 * u)
    p.fillPath(body, grad)

    # Chip outline.
    pen = QPen(FG, 46 * u, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    chip = QRectF(286 * u, 286 * u, 452 * u, 452 * u)
    p.drawRoundedRect(chip, 54 * u, 54 * u)

    # Chip legs on all four sides.
    p.setPen(QPen(FG, 40 * u, Qt.SolidLine, Qt.RoundCap))
    for frac in (0.3, 0.5, 0.7):
        x = chip.left() + chip.width() * frac
        y = chip.top() + chip.height() * frac
        p.drawLine(x, 212 * u, x, 286 * u)
        p.drawLine(x, 738 * u, x, 812 * u)
        p.drawLine(212 * u, y, 286 * u, y)
        p.drawLine(738 * u, y, 812 * u, y)

    # Download arrow inside the chip: writing into the device.
    p.setPen(QPen(FG, 52 * u, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    cx = size / 2
    p.drawLine(cx, 388 * u, cx, 600 * u)
    head = QPainterPath()
    head.moveTo(430 * u, 548 * u)
    head.lineTo(cx, 632 * u)
    head.lineTo(594 * u, 548 * u)
    p.drawPath(head)
    p.end()
    return img


def main() -> int:
    app = QApplication(sys.argv)
    _ = app
    out = sys.argv[1] if len(sys.argv) > 1 else "packaging/icon.iconset"
    import os
    os.makedirs(out, exist_ok=True)
    for size in (16, 32, 64, 128, 256, 512, 1024):
        draw(size).save(f"{out}/icon_{size}x{size}.png")
        if size <= 512:
            draw(size * 2).save(f"{out}/icon_{size}x{size}@2x.png")
    print(f"icons written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
