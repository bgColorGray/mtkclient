#!/usr/bin/python3
# -*- coding: utf-8 -*-
# (c) B.Kerler 2018-2026 GPLv3 License
"""Device-free tests for the V6 Firmware Upgrade host logic.

These cover the pure pieces of the FLASH-UPDATE host responder: the
packet checksum, the CMD:FLASH-UPDATE XML, and the file-system-operation
answers. The actual USB transfer loop is exercised only against hardware.
"""
import os

import pytest

from mtkclient.Library.DA.xmlflash.xml_lib import DAXML, FileSysOp
from mtkclient.Library.DA.xmlflash.xml_cmd import XMLCmd


class _Mtk:
    class _Cfg:
        gui = None
    config = _Cfg()


def _bare_daxml(recorder):
    """A DAXML with __init__ bypassed; only transport/logging stubbed."""
    obj = object.__new__(DAXML)
    obj.xsend = recorder
    obj.error = lambda *a, **k: None
    obj.info = lambda *a, **k: None
    return obj


def test_chk16_matches_libflash_algorithm():
    # 4 aligned bytes: little-endian dword sum
    assert DAXML.chk16(bytes([1, 0, 0, 0])) == 1
    assert DAXML.chk16(bytes([0, 1, 0, 0])) == 0x100
    # dword 0xFFFFFFFF -> truncated to 16 bits
    assert DAXML.chk16(b"\xff\xff\xff\xff") == 0xFFFF
    # tail bytes added as bytes after the aligned region
    assert DAXML.chk16(bytes([0, 0, 0, 0, 2, 3])) == 5
    assert DAXML.chk16(b"") == 0


def test_cmd_flash_update_builds_v2_command_with_flash_list():
    cmd = XMLCmd(_Mtk())
    xml = cmd.cmd_flash_update(
        scatter_file="/pkg/scatter.xml",
        backup_folder="/pkg/backup",
        flash_list=[("boot_a", "/pkg/boot.img"), ("lk_a", "/pkg/lk.img")],
    )
    assert "<command>CMD:FLASH-UPDATE</command>" in xml
    assert "<version>2.0</version>" in xml
    assert "<source_file>/pkg/scatter.xml</source_file>" in xml
    assert "<backup_folder>/pkg/backup</backup_folder>" in xml
    assert '<pt name="boot_a">/pkg/boot.img</pt>' in xml
    assert '<pt name="lk_a">/pkg/lk.img</pt>' in xml


def test_serve_filesys_file_size_existing(tmp_path):
    sent = []
    obj = _bare_daxml(lambda data, **k: sent.append(data) or True)
    target = tmp_path / "img.bin"
    target.write_bytes(b"\x00" * 1234)
    assert obj.serve_filesys(FileSysOp("FILE-SIZE", str(target))) is True
    assert sent == [f"OK@{hex(1234)}\0"]


def test_serve_filesys_file_size_missing_sends_plain_ok(tmp_path):
    sent = []
    obj = _bare_daxml(lambda data, **k: sent.append(data) or True)
    assert obj.serve_filesys(FileSysOp("FILE-SIZE", str(tmp_path / "nope"))) is True
    assert sent == ["OK\0"]


def test_serve_filesys_exists(tmp_path):
    sent = []
    obj = _bare_daxml(lambda data, **k: sent.append(data) or True)
    present = tmp_path / "there"
    present.write_bytes(b"x")
    obj.serve_filesys(FileSysOp("EXISTS", str(present)))
    obj.serve_filesys(FileSysOp("EXISTS", str(tmp_path / "absent")))
    assert sent == ["OK@EXISTS\0", "OK@NOT-EXISTS\0"]


def test_serve_filesys_mkdir_creates_dir(tmp_path):
    sent = []
    obj = _bare_daxml(lambda data, **k: sent.append(data) or True)
    newdir = tmp_path / "a" / "b"
    assert obj.serve_filesys(FileSysOp("MKDIR", str(newdir))) is True
    assert newdir.is_dir()
    assert sent == ["OK\0"]


def test_serve_filesys_remove_file(tmp_path):
    sent = []
    obj = _bare_daxml(lambda data, **k: sent.append(data) or True)
    victim = tmp_path / "gone.bin"
    victim.write_bytes(b"x")
    assert obj.serve_filesys(FileSysOp("REMOVE", str(victim))) is True
    assert not victim.exists()
    assert sent == ["OK\0"]


def test_serve_filesys_unknown_key_errors(tmp_path):
    sent = []
    obj = _bare_daxml(lambda data, **k: sent.append(data) or True)
    assert obj.serve_filesys(FileSysOp("FRobnicate", str(tmp_path))) is False
    assert sent == ["ERR!UNSUPPORTED"]
