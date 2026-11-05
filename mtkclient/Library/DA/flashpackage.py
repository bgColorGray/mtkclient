#!/usr/bin/python3
# -*- coding: utf-8 -*-
# (c) B.Kerler 2018-2026 GPLv3 License
"""Parser for SP Flash Tool V6 firmware packages (flash.xml + scatter).

A V6 download package is a directory containing image files, a scatter
file describing the partition layout, and a ``download_agent/flash.xml``
that points at the scatter and the download agent (DA) to use. This module
turns that on-disk layout into immutable value objects the flasher can use,
without talking to any device.
"""
import os
from dataclasses import dataclass
from typing import Optional
from xml.etree import ElementTree as ET

# operation_type values that must never be written during a firmware upgrade.
PROTECTED_OPERATIONS = ("PROTECTED", "RESERVED", "INVISIBLE", "BINREGION")
# Marker used by scatter files for "no image for this partition".
NO_FILE = "NONE"


def _parse_int(value: str) -> int:
    """Parse a scatter numeric field, which may be hex (0x...) or decimal."""
    text = (value or "").strip()
    if text == "":
        return 0
    return int(text, 16) if text.lower().startswith("0x") else int(text, 10)


@dataclass(frozen=True)
class PackagePartition:
    """One partition entry from a scatter file, with its resolved image path."""
    name: str
    filename: Optional[str]
    is_download: bool
    is_upgradable: bool
    region: str
    operation_type: str
    linear_start_addr: int
    physical_start_addr: int
    partition_size: int
    empty_boot_needed: bool

    @property
    def is_protected(self) -> bool:
        return self.operation_type in PROTECTED_OPERATIONS

    @property
    def has_image(self) -> bool:
        return self.filename is not None


@dataclass(frozen=True)
class FlashPackage:
    """A parsed V6 firmware package, keyed by storage type (EMMC / UFS)."""
    root: str
    project: str
    da_loader: str
    scatter_path: str
    build_version: str
    build_time: str
    storages: dict  # storage name -> tuple[PackagePartition, ...]

    def storage_names(self) -> tuple:
        return tuple(self.storages.keys())

    def partitions(self, storage: str) -> tuple:
        if storage not in self.storages:
            raise ValueError(f"Unknown storage type {storage!r}; "
                             f"have {self.storage_names()}")
        return self.storages[storage]

    def download_list(self, storage: str) -> tuple:
        """Partitions to flash: download-enabled, with an image that exists."""
        result = []
        for part in self.partitions(storage):
            if not part.is_download or not part.has_image:
                continue
            if not os.path.isfile(part.filename):
                continue
            result.append(part)
        return tuple(result)

    def missing_images(self, storage: str) -> tuple:
        """Download-enabled partitions whose image file is absent on disk."""
        result = []
        for part in self.partitions(storage):
            if part.is_download and part.has_image and not os.path.isfile(part.filename):
                result.append(part)
        return tuple(result)


def _parse_partition(node: ET.Element, root: str) -> PackagePartition:
    def text(tag: str) -> str:
        child = node.find(tag)
        return child.text.strip() if child is not None and child.text else ""

    raw_file = text("file_name")
    filename = None
    if raw_file and raw_file != NO_FILE:
        filename = os.path.normpath(os.path.join(root, raw_file))

    return PackagePartition(
        name=text("partition_name"),
        filename=filename,
        is_download=text("is_download").lower() == "true",
        is_upgradable=text("is_upgradable").lower() == "true",
        region=text("region"),
        operation_type=text("operation_type"),
        linear_start_addr=_parse_int(text("linear_start_addr")),
        physical_start_addr=_parse_int(text("physical_start_addr")),
        partition_size=_parse_int(text("partition_size")),
        empty_boot_needed=text("empty_boot_needed").lower() == "true",
    )


def parse_scatter(scatter_path: str, root: str) -> dict:
    """Parse a V6 XML scatter file into {storage_name: (PackagePartition, ...)}.

    Image paths are resolved relative to ``root`` (the package directory).
    """
    if not os.path.isfile(scatter_path):
        raise FileNotFoundError(f"Scatter file not found: {scatter_path}")
    tree = ET.parse(scatter_path)
    storages = {}
    for storage_node in tree.getroot().findall("storage_type"):
        name = storage_node.get("name", "")
        parts = tuple(_parse_partition(p, root)
                      for p in storage_node.findall("partition_index"))
        if parts:
            storages[name] = parts
    if not storages:
        raise ValueError(f"No storage_type/partition_index found in {scatter_path}; "
                         "this does not look like a V6 XML scatter file.")
    return storages


def parse_flash_xml(flash_xml_path: str) -> FlashPackage:
    """Parse ``download_agent/flash.xml`` and its referenced scatter file.

    The package root is the directory that holds the image files, i.e. the
    parent of the ``download_agent`` directory that contains flash.xml.
    """
    if not os.path.isfile(flash_xml_path):
        raise FileNotFoundError(f"flash.xml not found: {flash_xml_path}")
    agent_dir = os.path.dirname(os.path.abspath(flash_xml_path))

    tree = ET.parse(flash_xml_path)
    node = tree.getroot()
    if node.tag != "flash-mode":
        raise ValueError(f"Unexpected root element {node.tag!r} in {flash_xml_path}; "
                         "expected <flash-mode>.")

    def text(tag: str) -> str:
        child = node.find(tag)
        return child.text.strip() if child is not None and child.text else ""

    scatter_rel = text("scatter")
    if not scatter_rel:
        raise ValueError(f"No <scatter> element in {flash_xml_path}")
    scatter_path = os.path.normpath(os.path.join(agent_dir, scatter_rel))
    root = os.path.dirname(scatter_path)

    da_rel = text("dagent")
    da_loader = os.path.normpath(os.path.join(agent_dir, da_rel)) if da_rel else ""

    storages = parse_scatter(scatter_path, root)
    return FlashPackage(
        root=root,
        project=text("project"),
        da_loader=da_loader,
        scatter_path=scatter_path,
        build_version=text("build_version"),
        build_time=text("build_time"),
        storages=storages,
    )
