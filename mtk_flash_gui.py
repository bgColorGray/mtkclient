#!/usr/bin/env python3
# MTK Firmware Flasher (c) B.Kerler 2018-2026
# Licensed under GPLv3 License
"""Entry point for the focused firmware-flashing window.

Run it with an optional package path:
    python mtk_flash_gui.py [/path/to/download_agent/flash.xml]
"""
import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from mtkclient.gui.flash.flash_window import FlashWindow
from mtkclient.gui.translations import load_translations


def is_dark(app: QApplication) -> bool:
    try:
        return app.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except AttributeError:
        palette = app.palette()
        return palette.window().color().lightness() < 128


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("MTK Firmware Flasher")
    load_translations(app)
    window = FlashWindow(dark=is_dark(app))
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        window.load_package(sys.argv[1])
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
