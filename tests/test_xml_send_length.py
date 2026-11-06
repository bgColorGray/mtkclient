#!/usr/bin/python3
# -*- coding: utf-8 -*-
# (c) B.Kerler 2018-2026 GPLv3 License
"""The XML DA frame header must carry the payload's length in bytes.

xsend() used len(str) — a character count — while sending the UTF-8
bytes. A package under /Volumes/Zip/刷机包/ made FLASH-UPDATE 186 bytes
longer than its header said, the DA read a truncated command, and the
flash hung right after "Starting Firmware Upgrade".
"""
from struct import unpack
from types import SimpleNamespace

from mtkclient.Library.DA.xmlflash.xml_lib import DAXML

MAGIC = 0xFEEEEEEF


def _sender():
    writes = []
    obj = object.__new__(DAXML)
    obj.cmd = SimpleNamespace(MAGIC=MAGIC)
    obj.usbwrite = lambda data: writes.append(bytes(data)) or True
    return obj, writes


def _check(writes):
    header, payload = writes
    magic, _datatype, length = unpack("<III", header)
    assert magic == MAGIC
    assert length == len(payload)
    return payload


def test_ascii_string_length_includes_terminator():
    obj, writes = _sender()
    obj.xsend("OK")
    assert _check(writes) == b"OK\x00"


def test_non_ascii_string_length_is_in_bytes():
    obj, writes = _sender()
    text = "<source_file>/Volumes/Zip/刷机包/scatter.xml</source_file>"
    obj.xsend(text)
    payload = _check(writes)
    assert payload == text.encode("utf-8") + b"\x00"
    assert len(payload) > len(text) + 1


def test_bytes_and_ints_are_unchanged():
    obj, writes = _sender()
    obj.xsend(b"\x01\x02\x03")
    assert _check(writes) == b"\x01\x02\x03"

    obj, writes = _sender()
    obj.xsend(0x1234)
    assert _check(writes) == (0x1234).to_bytes(4, "little")

    obj, writes = _sender()
    obj.xsend(0x1234, is64bit=True)
    assert _check(writes) == (0x1234).to_bytes(8, "little")
