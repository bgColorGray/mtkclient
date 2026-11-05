#!/usr/bin/python3
# -*- coding: utf-8 -*-
# (c) B.Kerler 2018-2026 GPLv3 License
"""Guards against the flashing app reaching the device just by starting.

mtk_gui builds a Main instance at import time, which initialises the device
layer. The flasher once imported load_translations from there, so launching
the app immediately began a preloader handshake. Keep that import out.
"""
import subprocess
import sys


def _run(code: str):
    return subprocess.run([sys.executable, "-c", code],
                          capture_output=True, text=True, timeout=120)


def test_importing_the_flasher_does_not_import_mtk_gui():
    done = _run(
        "import sys; import mtk_flash_gui; "
        "print('mtk_gui' in sys.modules)")
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "False", (
        "mtk_flash_gui must not import mtk_gui: that module constructs Main() "
        "at import time and starts talking to the device.")


def test_translations_module_has_no_device_imports():
    done = _run(
        "import sys; import mtkclient.gui.translations; "
        "print(any(m.startswith('mtkclient.Library.DA') for m in sys.modules))")
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "False"


def test_translation_candidates_skip_the_c_locale():
    done = _run(
        "from mtkclient.gui.translations import translation_candidates;"
        "print(all(c not in ('C', 'POSIX') for c in translation_candidates()))")
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "True"
