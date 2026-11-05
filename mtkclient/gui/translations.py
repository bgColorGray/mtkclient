#!/usr/bin/python3
# -*- coding: utf-8 -*-
# (c) B.Kerler 2018-2026 GPLv3 License
"""Locale detection and translation loading, free of side effects.

Kept out of mtk_gui so importing it cannot pull in that module's top-level
work (it builds a Main instance on import, which reaches the device layer).
"""
import os
import subprocess
import sys

from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator

I18N_SUBDIR = os.path.join("mtkclient", "gui", "i18n")


def macos_preferred_languages() -> list:
    """macOS UI languages, since Qt only sees LANG/LC_* from a terminal."""
    if sys.platform != "darwin":
        return []
    try:
        out = subprocess.run(["defaults", "read", "-g", "AppleLanguages"],
                             capture_output=True, text=True, timeout=2).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [item.strip().strip('",') for item in out.strip("()\n").split("\n")
            if item.strip()]


def translation_candidates() -> list:
    """Locale codes to try, best first. MTK_LANG overrides everything."""
    names = ([os.environ.get("MTK_LANG", "")]
             + list(QLocale.system().uiLanguages())
             + macos_preferred_languages())
    candidates = []
    for name in filter(None, names):
        locale = QLocale(name)
        if locale.language() == QLocale.Language.C:
            continue
        code = "nl_NL" if locale.name() == "en_NL" else locale.name()
        if code not in candidates:
            candidates.append(code)
    return candidates


def i18n_base_dir() -> str:
    """Directory that contains mtkclient/gui/i18n, frozen app included."""
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled and os.path.isdir(os.path.join(bundled, I18N_SUBDIR)):
        return bundled
    return os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))


def load_translations(application) -> None:
    """Install the app and Qt base translations for the detected locale."""
    directory = i18n_base_dir()
    candidates = translation_candidates()
    translator = QTranslator(application)
    for code in candidates:
        if translator.load(os.path.join(I18N_SUBDIR, code), directory):
            application.installTranslator(translator)
            break

    locale = QLocale(candidates[0]) if candidates else QLocale.system()
    base_translator = QTranslator(application)
    translations_path = QLibraryInfo.path(QLibraryInfo.TranslationsPath)
    if base_translator.load(locale, "qtbase", "_", translations_path):
        application.installTranslator(base_translator)
