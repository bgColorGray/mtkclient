#!/usr/bin/python3
# -*- coding: utf-8 -*-
# (c) B.Kerler 2018-2026 GPLv3 License
"""Background worker that flashes a V6 package, for the flashing GUI.

Keeps every blocking step off the UI thread: waiting for the phone, loading
the DA, and running the native Firmware Upgrade. Progress and state reach the
window as Qt signals only.
"""
import logging
import os
import time

from PySide6.QtCore import QObject, QThread, Signal

from mtkclient.Library.DA.flashpackage import (MODE_FIRMWARE_UPGRADE,
                                               parse_flash_xml)
from mtkclient.Library.DA.mtk_da_handler import DaHandler
from mtkclient.Library.DA.xmlflash.xml_lib import DAXML
from mtkclient.Library.Partitions.gpt import GptSettings
from mtkclient.Library.mtk_class import Mtk
from mtkclient.config.mtk_config import MtkConfig

# Pause between connection attempts while waiting for the phone to appear.
RETRY_DELAY = 2
# Phases reported to the window.
PHASE_WAITING = "waiting"
PHASE_CONNECTED = "connected"
PHASE_FLASHING = "flashing"
PHASE_DONE = "done"
PHASE_FAILED = "failed"


class FlashWorker(QObject):
    """Runs one flashing job; lives on its own QThread."""

    log = Signal(str)
    phase = Signal(str, str)            # phase, human-readable detail
    device = Signal(str)                # chip / storage description
    file_started = Signal(str, int)     # image name, size in bytes
    file_progress = Signal(int)         # bytes done within current image
    overall = Signal(int, int)          # bytes done, total bytes
    finished = Signal(bool, str)        # success, message

    def __init__(self, flash_xml: str, selected: list, storage: str = None,
                 backup: str = None, mode: str = MODE_FIRMWARE_UPGRADE,
                 parent=None):
        super().__init__(parent)
        self.flash_xml = flash_xml
        self.selected = list(selected)
        self.storage = storage
        self.backup = backup
        self.mode = mode
        self._stop = False
        self._total = 0
        self._done_before_current = 0
        self._current_size = 0

    def request_stop(self) -> None:
        """Ask the job to stop; honoured between connection attempts."""
        self._stop = True

    # ── progress plumbing ────────────────────────────────────────────

    def _on_file(self, name: str, size: int) -> None:
        self._done_before_current += self._current_size
        self._current_size = size
        self.file_started.emit(name, size)
        self.overall.emit(self._done_before_current, self._total)

    def _on_bytes(self, pos) -> None:
        try:
            pos = int(pos)
        except (TypeError, ValueError):
            return
        self.file_progress.emit(pos)
        self.overall.emit(self._done_before_current + pos, self._total)

    def _emit_log(self, text) -> None:
        self.log.emit(str(text).rstrip())

    # ── the job ──────────────────────────────────────────────────────

    def run(self) -> None:
        try:
            self._run()
        except Exception as err:  # keep the UI alive on any unexpected error
            self.log.emit(f"Unexpected error: {err}")
            self.phase.emit(PHASE_FAILED, str(err))
            self.finished.emit(False, str(err))

    def _run(self) -> None:
        try:
            package = parse_flash_xml(self.flash_xml)
        except (ValueError, FileNotFoundError) as err:
            self.finished.emit(False, f"Could not read the package: {err}")
            return

        attempt = 0
        while not self._stop:
            attempt += 1
            self.phase.emit(PHASE_WAITING,
                            f"Waiting for the phone (attempt {attempt})")
            ok, retry, msg = self._attempt(package)
            if ok:
                self.phase.emit(PHASE_DONE, msg)
                self.finished.emit(True, msg)
                return
            if not retry:
                self.phase.emit(PHASE_FAILED, msg)
                self.finished.emit(False, msg)
                return
            self.log.emit(f"{msg} — waiting for the next connection.")
            for _ in range(RETRY_DELAY * 10):
                if self._stop:
                    break
                time.sleep(0.1)
        self.finished.emit(False, "Stopped.")

    def _attempt(self, package):
        """One connect-and-flash attempt.

        Returns (ok, may_retry, message). may_retry is False once the DA has
        accepted the upgrade, since the device may already be modified.
        """
        config = MtkConfig(loglevel=logging.INFO, gui=self.log,
                           guiprogress=None, update_status_text=None)
        config.gpt_settings = GptSettings(gpt_num_part_entries='0',
                                          gpt_part_entry_size='0',
                                          gpt_part_entry_start_lba='0')
        config.reconnect = True
        config.uartloglevel = 2
        config.logchannel = "UART"
        # The bundled DA loaders rarely cover the package's SoC; the package
        # ships the matching one.
        if package.da_loader and os.path.isfile(package.da_loader):
            config.loader = package.da_loader

        mtk = Mtk(config=config, loglevel=logging.INFO)
        handler = DaHandler(mtk, logging.INFO)
        handler.close = lambda *a, **k: None   # never sys.exit from the GUI

        mtk = handler.connect(mtk)
        if mtk is None:
            return False, True, "No phone detected"
        mtk = handler.configure_da(mtk)
        if mtk is None:
            return False, True, "Could not load the download agent"

        da = mtk.daloader.da
        if not isinstance(da, DAXML):
            return False, False, "This device does not use a V6 (XML) DA"

        detected = getattr(da.daconfig.storage, "storagetype", None)
        if detected not in ("EMMC", "UFS"):
            detected = None
        storage = self.storage or detected
        if storage is None:
            return False, True, "Could not detect the storage type (EMMC/UFS)"
        if detected and storage != detected:
            return (False, False,
                    f"Device storage is {detected} but the {storage} layout "
                    "was selected; refusing to flash")
        if storage not in package.storage_names():
            return False, False, f"The package has no {storage} layout"

        self.device.emit(f"{mtk.config.chipconfig.name} · {storage}")
        self.phase.emit(PHASE_CONNECTED, f"Connected · {storage}")

        parts = [p for p in package.download_list(storage)
                 if not self.selected or p.name in self.selected]
        if not parts:
            return False, False, "No partitions selected"
        missing = [p.name for p in parts if not os.path.isfile(p.filename)]
        if missing:
            return False, False, f"Missing image files: {', '.join(missing)}"

        self._total = sum(os.path.getsize(p.filename) for p in parts)
        self._done_before_current = 0
        self._current_size = 0
        self.overall.emit(0, self._total)

        backup = self.backup or os.path.join(package.root, "mtk_fwbackup")
        da.fw_on_file = self._on_file
        config.guiprogress = _SignalShim(self._on_bytes)
        self.phase.emit(PHASE_FLASHING, f"Flashing {len(parts)} partitions")

        trimmed = _SubsetPackage(package, storage, parts)
        ok = da.fwflash(trimmed, storage, backup, display=True, mode=self.mode)
        if ok:
            return True, False, "Flashing completed"
        if da.fw_accepted:
            return False, False, "Flashing failed after it had started"
        return False, True, "The device did not accept the flash command"


class _SignalShim:
    """Adapter so mtkclient's progress helper can call a plain function.

    mtkclient calls ``guiprogress.emit(pos)``; this gives that attribute to a
    callable without routing byte-level updates through a real Qt signal.
    """

    def __init__(self, fn):
        self.emit = fn


class _SubsetPackage:
    """A FlashPackage view limited to the partitions the user ticked."""

    def __init__(self, package, storage, parts):
        self._package = package
        self._storage = storage
        self._parts = tuple(parts)
        self.root = package.root
        self.project = package.project
        self.scatter_path = package.scatter_path
        self.da_loader = package.da_loader
        self.build_version = package.build_version

    def storage_names(self):
        return self._package.storage_names()

    def partitions(self, storage: str):
        return self._package.partitions(storage)

    def download_list(self, storage: str):
        if storage == self._storage:
            return self._parts
        return self._package.download_list(storage)

    def missing_images(self, storage: str):
        return self._package.missing_images(storage)


def start_worker(worker: FlashWorker) -> QThread:
    """Move worker onto a new thread, start it, and return the thread."""
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)
    thread.start()
    return thread
