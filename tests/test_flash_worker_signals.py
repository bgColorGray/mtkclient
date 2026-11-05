#!/usr/bin/python3
# -*- coding: utf-8 -*-
# (c) B.Kerler 2018-2026 GPLv3 License
"""Byte counts must survive the worker's Qt signals unchanged.

A Signal(int) carries a 32-bit C int: the 9 GB userdata image wrapped
around and the window showed "userdata.img · 989.3 MB".
"""
from PySide6.QtCore import QCoreApplication

from mtkclient.gui.flash.flash_worker import FlashWorker

USERDATA_SIZE = 9_627_273_272      # the real userdata.img, > 2**33
TOTAL_SIZE = 15_400_000_000


def _worker():
    QCoreApplication.instance() or QCoreApplication([])
    return FlashWorker(flash_xml="unused", selected=[])


def test_file_size_above_4gb_is_not_truncated():
    worker = _worker()
    got = []
    worker.file_started.connect(lambda name, size: got.append((name, size)))
    worker._on_file("userdata.img", USERDATA_SIZE)
    assert got == [("userdata.img", USERDATA_SIZE)]


def test_progress_and_overall_above_4gb_are_not_truncated():
    worker = _worker()
    worker._total = TOTAL_SIZE
    worker._done_before_current = 5_506_368_960     # super.img already sent
    progress, overall = [], []
    worker.file_progress.connect(progress.append)
    worker.overall.connect(lambda done, total: overall.append((done, total)))
    worker._on_bytes(USERDATA_SIZE - 1)
    assert progress == [USERDATA_SIZE - 1]
    assert overall == [(5_506_368_960 + USERDATA_SIZE - 1, TOTAL_SIZE)]
