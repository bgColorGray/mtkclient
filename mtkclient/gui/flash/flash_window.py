#!/usr/bin/python3
# -*- coding: utf-8 -*-
# (c) B.Kerler 2018-2026 GPLv3 License
"""A focused window for flashing an SP Flash Tool V6 package.

One job, one screen: choose the package, review what will be written, press
Flash. Everything else mtkclient can do lives in the main GUI.
"""
import os

from PySide6.QtCore import Qt, QTime
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFrame,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QMainWindow, QMessageBox, QPlainTextEdit,
                               QProgressBar, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from mtkclient.Library.DA.flashpackage import (MODE_DOWNLOAD_ONLY,
                                               MODE_FIRMWARE_UPGRADE,
                                               MODE_FORMAT_ALL,
                                               parse_flash_xml)
from mtkclient.gui.flash import __version__, flash_style
from mtkclient.gui.flash.flash_worker import (FlashWorker, PHASE_FLASHING,
                                              start_worker)

COL_PART, COL_FILE, COL_ADDR, COL_SIZE = range(4)
MAX_LOG_LINES = 2000


def human_size(num: int) -> str:
    value = float(num)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def _card(*widgets) -> QFrame:
    frame = QFrame()
    frame.setObjectName("Card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(9)
    for widget in widgets:
        if isinstance(widget, QWidget):
            layout.addWidget(widget)
        else:
            layout.addLayout(widget)
    return frame


def _section(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("SectionLabel")
    return label


class FlashWindow(QMainWindow):
    def __init__(self, dark: bool = False):
        super().__init__()
        self.package = None
        self.worker = None
        self.thread = None
        self.current_total = 0
        self.setWindowTitle(f"{self.tr('MTK Firmware Flasher')}  {__version__}")
        self.resize(900, 760)
        self._palette = flash_style.DARK if dark else flash_style.LIGHT
        self.setStyleSheet(flash_style.stylesheet(dark))
        self._build()
        # currentIndexChanged doesn't fire for the index the combo starts on.
        self._mode_changed()
        self._set_phase("waiting", self.tr("No package loaded"))
        self._set_running(False)

    # ── layout ───────────────────────────────────────────────────────

    def _build(self) -> None:
        root = QWidget()
        root.setObjectName("Root")
        outer = QVBoxLayout(root)
        outer.setContentsMargins(20, 18, 20, 18)
        outer.setSpacing(14)
        outer.addLayout(self._build_header())
        outer.addWidget(_card(_section(self.tr("Firmware package")),
                              self._build_package_row(),
                              self._build_package_info()))
        outer.addWidget(self._build_partitions_card(), 1)
        outer.addWidget(_card(_section(self.tr("Mode")), self._build_mode_row(),
                              self._build_options()))
        outer.addWidget(_card(self._build_actions(), self._build_progress()))
        outer.addWidget(self._build_log())
        self.setCentralWidget(root)

    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        title = QLabel(self.tr("Firmware Flasher"))
        title.setObjectName("Title")
        self.status_pill = QLabel()
        self.status_pill.setObjectName("StatusPill")
        self.device_label = QLabel()
        self.device_label.setObjectName("Hint")
        row.addWidget(title)
        row.addSpacing(12)
        row.addWidget(self.device_label)
        row.addStretch(1)
        row.addWidget(self.status_pill)
        return row

    def _build_package_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText(
            self.tr("Select the package's download_agent/flash.xml"))
        self.path_edit.setReadOnly(True)
        browse = QPushButton(self.tr("Choose..."))
        browse.clicked.connect(self.choose_package)
        row.addWidget(self.path_edit, 1)
        row.addWidget(browse)
        return row

    def _build_package_info(self) -> QLabel:
        self.pkg_info = QLabel(self.tr("No package loaded."))
        self.pkg_info.setObjectName("Hint")
        return self.pkg_info

    def _build_partitions_card(self) -> QFrame:
        head = QHBoxLayout()
        self.select_all = QCheckBox(self.tr("Select all"))
        self.select_all.setChecked(True)
        self.select_all.stateChanged.connect(self._toggle_all)
        self.part_summary = QLabel()
        self.part_summary.setObjectName("Hint")
        head.addWidget(_section(self.tr("Partitions to write")))
        head.addStretch(1)
        head.addWidget(self.part_summary)
        head.addSpacing(12)
        head.addWidget(self.select_all)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([
            self.tr("Partition"), self.tr("Image file"),
            self.tr("Start address"), self.tr("Size")])
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(False)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        # The partition list is the main thing to review before flashing, so
        # give it real room instead of the small default size hint.
        self.table.setMinimumHeight(260)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(COL_PART, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_FILE, QHeaderView.Stretch)
        header.setSectionResizeMode(COL_ADDR, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_SIZE, QHeaderView.ResizeToContents)
        self.table.itemChanged.connect(lambda _item: self._update_summary())
        return _card(head, self.table)

    def _build_mode_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self.mode_box = QComboBox()
        self.mode_box.addItem(self.tr("Firmware Upgrade"), MODE_FIRMWARE_UPGRADE)
        self.mode_box.addItem(self.tr("Download Only"), MODE_DOWNLOAD_ONLY)
        self.mode_box.addItem(self.tr("Format All + Download"), MODE_FORMAT_ALL)
        self.mode_box.currentIndexChanged.connect(self._mode_changed)
        self.mode_hint = QLabel()
        self.mode_hint.setObjectName("Hint")
        self.mode_hint.setWordWrap(True)
        row.addWidget(QLabel(self.tr("Mode")))
        row.addWidget(self.mode_box)
        row.addSpacing(14)
        row.addWidget(self.mode_hint, 1)
        return row

    def _mode_hint_text(self, mode: str) -> str:
        """One line explaining what the chosen mode does to the phone."""
        if mode == MODE_FIRMWARE_UPGRADE:
            return self.tr("The download agent backs up the protected "
                           "partitions (nvram, protect) and restores them "
                           "afterwards.")
        if mode == MODE_DOWNLOAD_ONLY:
            return self.tr("Writes only the ticked partitions. Everything "
                           "else, including user data, is left untouched.")
        if mode == MODE_FORMAT_ALL:
            return self.tr("Erases the entire flash first. Nothing is kept — "
                           "user data, IMEI and calibration data are all lost.")
        return ""

    def _mode_changed(self) -> None:
        mode = self.mode_box.currentData()
        self.mode_hint.setText(self._mode_hint_text(mode))
        # Use the theme's own danger colour; the pill red is tuned for a
        # coloured background and reads too dark on the dark window.
        warn = mode == MODE_FORMAT_ALL
        self.mode_hint.setStyleSheet(
            f"color: {self._palette['danger']}; font-weight: 600;" if warn else "")

    def _build_options(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self.storage_box = QComboBox()
        self.storage_box.addItem(self.tr("Auto-detect"), None)
        self.storage_box.addItem("EMMC", "EMMC")
        self.storage_box.addItem("UFS", "UFS")
        self.backup_edit = QLineEdit()
        self.backup_edit.setPlaceholderText(
            self.tr("Default: mtk_fwbackup next to the package"))
        pick = QPushButton(self.tr("Choose..."))
        pick.clicked.connect(self._choose_backup)
        row.addWidget(QLabel(self.tr("Storage")))
        row.addWidget(self.storage_box)
        row.addSpacing(18)
        row.addWidget(QLabel(self.tr("Backup folder")))
        row.addWidget(self.backup_edit, 1)
        row.addWidget(pick)
        return row

    def _build_actions(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self.flash_btn = QPushButton(self.tr("Start flashing"))
        self.flash_btn.setObjectName("Primary")
        self.flash_btn.clicked.connect(self.start_flash)
        self.stop_btn = QPushButton(self.tr("Stop"))
        self.stop_btn.setObjectName("Danger")
        self.stop_btn.clicked.connect(self.stop_flash)
        self.hint = QLabel()
        self.hint.setObjectName("Hint")
        row.addWidget(self.flash_btn)
        row.addWidget(self.stop_btn)
        row.addSpacing(14)
        row.addWidget(self.hint, 1)
        return row

    def _build_progress(self) -> QVBoxLayout:
        box = QVBoxLayout()
        box.setSpacing(6)
        self.file_label = QLabel()
        self.file_label.setObjectName("Hint")
        self.file_bar = QProgressBar()
        self.file_bar.setRange(0, 1000)
        self.overall_label = QLabel()
        self.overall_label.setObjectName("Hint")
        self.overall_bar = QProgressBar()
        self.overall_bar.setObjectName("OverallBar")
        self.overall_bar.setRange(0, 1000)
        box.addWidget(self.file_label)
        box.addWidget(self.file_bar)
        box.addWidget(self.overall_label)
        box.addWidget(self.overall_bar)
        return box

    def _build_log(self) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        row = QHBoxLayout()
        self.log_toggle = QPushButton(self.tr("Show log"))
        self.log_toggle.clicked.connect(self._toggle_log)
        row.addWidget(self.log_toggle)
        row.addStretch(1)
        self.log_box = QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMaximumBlockCount(MAX_LOG_LINES)
        self.log_box.setFixedHeight(150)
        self.log_box.setVisible(False)
        layout.addLayout(row)
        layout.addWidget(self.log_box)
        return wrapper

    # ── package loading ──────────────────────────────────────────────

    def choose_package(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("Select flash.xml"), "", "flash.xml (flash.xml);;XML (*.xml)")
        if path:
            self.load_package(path)

    def load_package(self, path: str) -> None:
        try:
            package = parse_flash_xml(path)
        except (ValueError, FileNotFoundError) as err:
            QMessageBox.warning(self, self.tr("Cannot read package"), str(err))
            return
        self.package = package
        self.path_edit.setText(path)
        storages = " / ".join(package.storage_names())
        layouts = self.tr("layouts")
        self.pkg_info.setText(
            f"{package.project} · {package.build_version} · "
            f"{layouts}: {storages} · {package.build_time}")
        self._fill_table()
        self._set_phase("waiting", self.tr("Ready — connect the phone"))

    def _layout_name(self) -> str:
        chosen = self.storage_box.currentData()
        if chosen:
            return chosen
        names = self.package.storage_names()
        return "UFS" if "UFS" in names else names[0]

    def _fill_table(self) -> None:
        parts = self.package.download_list(self._layout_name())
        self.table.blockSignals(True)
        self.table.setRowCount(len(parts))
        for row, part in enumerate(parts):
            item = QTableWidgetItem(part.name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            item.setData(Qt.UserRole, part.name)
            self.table.setItem(row, COL_PART, item)
            self.table.setItem(row, COL_FILE,
                               QTableWidgetItem(os.path.basename(part.filename)))
            addr = QTableWidgetItem(f"0x{part.linear_start_addr:X}")
            addr.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, COL_ADDR, addr)
            size = QTableWidgetItem(human_size(os.path.getsize(part.filename)))
            size.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, COL_SIZE, size)
        self.table.blockSignals(False)
        self._update_summary()

    def _toggle_all(self, state) -> None:
        checked = Qt.Checked if state else Qt.Unchecked
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            self.table.item(row, COL_PART).setCheckState(checked)
        self.table.blockSignals(False)
        self._update_summary()

    def selected_partitions(self) -> list:
        names = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, COL_PART)
            if item is not None and item.checkState() == Qt.Checked:
                names.append(item.data(Qt.UserRole))
        return names

    def _update_summary(self) -> None:
        if self.package is None:
            return
        chosen = set(self.selected_partitions())
        parts = [p for p in self.package.download_list(self._layout_name())
                 if p.name in chosen]
        total = sum(os.path.getsize(p.filename) for p in parts)
        self.part_summary.setText(
            self.tr("{count} partitions · {size}").format(
                count=len(parts), size=human_size(total)))
        self.flash_btn.setEnabled(bool(parts) and self.worker is None)

    def _choose_backup(self) -> None:
        path = QFileDialog.getExistingDirectory(self, self.tr("Select backup folder"))
        if path:
            self.backup_edit.setText(path)

    # ── flashing ─────────────────────────────────────────────────────

    def start_flash(self) -> None:
        if self.package is None or self.worker is not None:
            return
        names = self.selected_partitions()
        if not names:
            return
        mode = self.mode_box.currentData()
        question = self.tr("Mode: {mode}\n{detail}\n\n"
                           "{count} partitions will be written. Continue?").format(
            mode=self.mode_box.currentText(),
            detail=self._mode_hint_text(mode),
            count=len(names))
        if mode == MODE_FORMAT_ALL:
            question = self.tr("THE WHOLE FLASH WILL BE ERASED FIRST.\n\n") + question
        answer = QMessageBox.warning(
            self, self.tr("Confirm flashing"), question,
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel)
        if answer != QMessageBox.Yes:
            return

        self.log_box.clear()
        self.worker = FlashWorker(flash_xml=self.path_edit.text(),
                                  selected=names,
                                  storage=self.storage_box.currentData(),
                                  backup=self.backup_edit.text() or None,
                                  mode=mode)
        self.worker.log.connect(self.append_log)
        self.worker.phase.connect(self._set_phase)
        self.worker.device.connect(self.device_label.setText)
        self.worker.file_started.connect(self._on_file_started)
        self.worker.file_progress.connect(self._on_file_progress)
        self.worker.overall.connect(self._on_overall)
        self.worker.finished.connect(self._on_finished)
        self._set_running(True)
        self.hint.setText(self.tr("Power the phone off, hold both volume keys "
                                  "and plug in the USB cable."))
        self.thread = start_worker(self.worker)

    def stop_flash(self) -> None:
        if self.worker is not None:
            self.worker.request_stop()
            self.hint.setText(self.tr("Stopping after the current step..."))

    def _set_running(self, running: bool) -> None:
        self.flash_btn.setEnabled(not running and self.package is not None
                                  and bool(self.selected_partitions()))
        self.stop_btn.setEnabled(running)
        self.path_edit.setEnabled(not running)
        self.table.setEnabled(not running)
        self.storage_box.setEnabled(not running)
        self.backup_edit.setEnabled(not running)
        self.select_all.setEnabled(not running)
        self.mode_box.setEnabled(not running)

    def _set_phase(self, phase: str, detail: str) -> None:
        bg, fg = flash_style.PILL_COLORS.get(phase, ("#8e8e93", "#ffffff"))
        self.status_pill.setText(detail or phase)
        self.status_pill.setStyleSheet(
            f"background-color: {bg}; color: {fg};")
        if phase == PHASE_FLASHING:
            self.hint.setText(self.tr("Do not unplug the cable."))

    def _on_file_started(self, name: str, size: int) -> None:
        self.current_total = max(size, 1)
        self.file_bar.setValue(0)
        self.file_label.setText(f"{name} · {human_size(size)}")

    def _on_file_progress(self, done: int) -> None:
        self.file_bar.setValue(min(1000, int(1000 * done / self.current_total)))

    def _on_overall(self, done: int, total: int) -> None:
        if total <= 0:
            return
        self.overall_bar.setValue(min(1000, int(1000 * done / total)))
        pct = 100.0 * min(done, total) / total
        self.overall_label.setText(
            self.tr("Overall {pct:.1f}% — {done} of {total}").format(
                pct=pct, done=human_size(done), total=human_size(total)))

    def _on_finished(self, ok: bool, message: str) -> None:
        self.worker = None
        self.thread = None
        self._set_running(False)
        self.hint.setText(message)
        if ok:
            self.overall_bar.setValue(1000)
            QMessageBox.information(self, self.tr("Done"), message)
        else:
            QMessageBox.warning(self, self.tr("Flashing stopped"), message)

    # ── log ──────────────────────────────────────────────────────────

    def append_log(self, text: str) -> None:
        stamp = QTime.currentTime().toString("HH:mm:ss")
        self.log_box.appendPlainText(f"{stamp}  {text}")

    def _toggle_log(self) -> None:
        shown = not self.log_box.isVisible()
        self.log_box.setVisible(shown)
        self.log_toggle.setText(self.tr("Hide log") if shown else self.tr("Show log"))

    def closeEvent(self, event) -> None:
        if self.worker is not None:
            answer = QMessageBox.warning(
                self, self.tr("Flashing in progress"),
                self.tr("Closing now may leave the phone in an unusable state. "
                        "Close anyway?"),
                QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel)
            if answer != QMessageBox.Yes:
                event.ignore()
                return
            self.worker.request_stop()
        event.accept()
