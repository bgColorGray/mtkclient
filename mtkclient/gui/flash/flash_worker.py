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
import sys
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


def user_data_dir() -> str:
    """Writable per-user directory for mtkclient's runtime files.

    An app launched from Finder starts with "/" as its working directory,
    and mtkclient defaults to writing hwparam.json and .state there, which
    fails on the read-only system volume.
    """
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    elif os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        base = (os.environ.get("XDG_DATA_HOME")
                or os.path.expanduser("~/.local/share"))
    path = os.path.join(base, "mtkclient")
    os.makedirs(path, exist_ok=True)
    return path


class FlashWorker(QObject):
    """Runs one flashing job; lives on its own QThread."""

    # Byte counts travel as `object`: a Signal(int) is a 32-bit C int, so a
    # 9 GB userdata image wrapped around and showed as 989 MB.
    log = Signal(str)
    phase = Signal(str, str)            # phase, human-readable detail
    device = Signal(str)                # chip / storage description
    file_started = Signal(str, object)  # image name, size in bytes
    file_progress = Signal(object)      # bytes done within current image
    overall = Signal(object, object)    # bytes done, total bytes
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
            self.log.emit(self.tr("Unexpected error: {err}").format(err=err))
            self.phase.emit(PHASE_FAILED, str(err))
            self.finished.emit(False, str(err))

    def _run(self) -> None:
        try:
            package = parse_flash_xml(self.flash_xml)
        except (ValueError, FileNotFoundError) as err:
            self.finished.emit(False, self.tr("Could not read the package: {err}").format(err=err))
            return

        attempt = 0
        while not self._stop:
            attempt += 1
            self.phase.emit(PHASE_WAITING,
                            self.tr("Waiting for the phone (attempt {n})").format(n=attempt))
            ok, retry, msg = self._attempt(package)
            if ok:
                self.phase.emit(PHASE_DONE, msg)
                self.finished.emit(True, msg)
                return
            if not retry:
                self.phase.emit(PHASE_FAILED, msg)
                self.finished.emit(False, msg)
                return
            self.log.emit(self.tr("{msg} — waiting for the next connection.").format(msg=msg))
            for _ in range(RETRY_DELAY * 10):
                if self._stop:
                    break
                time.sleep(0.1)
        self.finished.emit(False, self.tr("Stopped."))

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
        data_dir = user_data_dir()
        config.hwparam_path = data_dir
        # The bundled DA loaders rarely cover the package's SoC; the package
        # ships the matching one.
        if package.da_loader and os.path.isfile(package.da_loader):
            config.loader = package.da_loader

        mtk = Mtk(config=config, loglevel=logging.INFO)
        handler = DaHandler(mtk, logging.INFO)
        handler.close = lambda *a, **k: None   # never sys.exit from the GUI

        # connect() turns a missing directory into "." and hands it to the
        # preloader, which overwrites hwparam_path with it — so setting the
        # config alone is not enough; the directory has to be passed here.
        mtk = handler.connect(mtk, directory=data_dir)
        if mtk is None:
            return False, True, self.tr("No phone detected")
        mtk = handler.configure_da(mtk)
        if mtk is None:
            return False, True, self.tr("Could not load the download agent")

        da = mtk.daloader.da
        if not isinstance(da, DAXML):
            return False, False, self.tr("This device does not use a V6 (XML) DA")

        detected = getattr(da.daconfig.storage, "storagetype", None)
        if detected not in ("EMMC", "UFS"):
            detected = None
        storage = self.storage or detected
        if storage is None:
            return False, True, "Could not detect the storage type (EMMC/UFS)"
        if detected and storage != detected:
            return (False, False,
                    self.tr("Device storage is {detected} but the {storage} layout "
                            "was selected; refusing to flash").format(
                        detected=detected, storage=storage))
        if storage not in package.storage_names():
            return False, False, self.tr("The package has no {storage} layout").format(storage=storage)

        self.device.emit(f"{mtk.config.chipconfig.name} · {storage}")
        self.phase.emit(PHASE_CONNECTED, self.tr("Connected · {storage}").format(storage=storage))

        parts = [p for p in package.download_list(storage)
                 if not self.selected or p.name in self.selected]
        if not parts:
            return False, False, self.tr("No partitions selected")
        missing = [p.name for p in parts if not os.path.isfile(p.filename)]
        if missing:
            return False, False, self.tr("Missing image files: {names}").format(names=", ".join(missing))

        self._total = sum(os.path.getsize(p.filename) for p in parts)
        self._done_before_current = 0
        self._current_size = 0
        self.overall.emit(0, self._total)

        backup = self.backup or os.path.join(package.root, "mtk_fwbackup")
        da.fw_on_file = self._on_file
        config.guiprogress = _SignalShim(self._on_bytes)
        self.phase.emit(PHASE_FLASHING,
                        self.tr("Flashing {count} partitions").format(count=len(parts)))

        trimmed = _SubsetPackage(package, storage, parts)
        ok = da.fwflash(trimmed, storage, backup, display=True, mode=self.mode)
        if ok:
            return True, False, self.tr("Flashing completed")
        if da.fw_accepted:
            return False, False, self.tr("Flashing failed after it had started")
        return False, True, self.tr("The device did not accept the flash command")


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
    """Move worker onto a new thread, start it, and return the thread.

    The caller must keep the returned thread referenced until its own
    finished signal fires: dropping a running QThread makes Qt abort with
    "Destroyed while thread is still running".
    """
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    thread.start()
    return thread
