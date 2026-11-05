#!/usr/bin/python3
# -*- coding: utf-8 -*-
# (c) B.Kerler 2018-2026 GPLv3 License
"""Unit tests for the V6 firmware-package parser (flash.xml + scatter)."""
import os

import pytest

from mtkclient.Library.DA.flashpackage import (
    FlashPackage,
    PackagePartition,
    parse_flash_xml,
    parse_scatter,
    _parse_int,
)

SCATTER_XML = """<?xml version="1.0" encoding="utf-8"?>
<root>
  <general name="MTK_PLATFORM_CFG">
    <config_version name="V2.2.0"><platform>MT6989</platform></config_version>
  </general>
  <storage_type name="EMMC">
    <general name="MTK_STORAGE_CFG">
      <storage name="EMMC"><block_size>0x20000</block_size></storage>
    </general>
    <partition_index name="SYS0">
      <partition_name>preloader_a</partition_name>
      <file_name>preloader_demo.bin</file_name>
      <is_download>true</is_download>
      <linear_start_addr>0x0</linear_start_addr>
      <physical_start_addr>0x0</physical_start_addr>
      <partition_size>0x100000</partition_size>
      <region>EMMC_BOOT1</region>
      <operation_type>BOOTLOADERS</operation_type>
      <is_upgradable>true</is_upgradable>
      <empty_boot_needed>false</empty_boot_needed>
    </partition_index>
    <partition_index name="SYS1">
      <partition_name>pgpt</partition_name>
      <file_name>NONE</file_name>
      <is_download>false</is_download>
      <linear_start_addr>0x0</linear_start_addr>
      <partition_size>0x8000</partition_size>
      <region>EMMC_USER</region>
      <operation_type>INVISIBLE</operation_type>
      <is_upgradable>false</is_upgradable>
    </partition_index>
    <partition_index name="SYS2">
      <partition_name>boot_a</partition_name>
      <file_name>boot.img</file_name>
      <is_download>true</is_download>
      <linear_start_addr>0x2d900000</linear_start_addr>
      <partition_size>0x4000000</partition_size>
      <region>EMMC_USER</region>
      <operation_type>UPDATE</operation_type>
      <is_upgradable>true</is_upgradable>
    </partition_index>
    <partition_index name="SYS3">
      <partition_name>nvram</partition_name>
      <file_name>NONE</file_name>
      <is_download>false</is_download>
      <linear_start_addr>0x3a500000</linear_start_addr>
      <partition_size>0x4000000</partition_size>
      <region>EMMC_USER</region>
      <operation_type>BINREGION</operation_type>
      <is_upgradable>false</is_upgradable>
    </partition_index>
  </storage_type>
  <storage_type name="UFS">
    <partition_index name="SYS0">
      <partition_name>preloader_a</partition_name>
      <file_name>preloader_demo.bin</file_name>
      <is_download>true</is_download>
      <linear_start_addr>0x0</linear_start_addr>
      <partition_size>0x100000</partition_size>
      <region>UFS_LU0</region>
      <operation_type>BOOTLOADERS</operation_type>
      <is_upgradable>true</is_upgradable>
    </partition_index>
  </storage_type>
</root>
"""

FLASH_XML = """<?xml version="1.0" encoding="UTF-8" ?>
<flash-mode>
    <project>demo_project</project>
    <dagent>DA_BR.bin</dagent>
    <scatter>../demo_scatter.xml</scatter>
    <build_version>alps-mp-u0.mp1-V1</build_version>
    <build_time>2026-10-27 18:14:05</build_time>
    <version>1.0</version>
    <contact>Tester</contact>
    <phone_tracking_en>Y</phone_tracking_en>
</flash-mode>
"""


def _write(path, text):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


@pytest.fixture
def package(tmp_path):
    """A minimal on-disk V6 package; only some image files actually exist."""
    agent = tmp_path / "download_agent"
    agent.mkdir()
    _write(str(agent / "flash.xml"), FLASH_XML)
    (agent / "DA_BR.bin").write_bytes(b"MTK_DOWNLOAD_AGENT")
    _write(str(tmp_path / "demo_scatter.xml"), SCATTER_XML)
    # boot.img exists, preloader_demo.bin intentionally missing
    (tmp_path / "boot.img").write_bytes(b"\x00" * 16)
    return tmp_path


def test_parse_int_handles_hex_decimal_and_blank():
    assert _parse_int("0x100000") == 0x100000
    assert _parse_int("4096") == 4096
    assert _parse_int("") == 0
    assert _parse_int("  0X20  ") == 0x20


def test_parse_scatter_groups_partitions_by_storage(package):
    storages = parse_scatter(str(package / "demo_scatter.xml"), str(package))
    assert set(storages) == {"EMMC", "UFS"}
    assert len(storages["EMMC"]) == 4
    assert len(storages["UFS"]) == 1


def test_partition_fields_are_parsed(package):
    storages = parse_scatter(str(package / "demo_scatter.xml"), str(package))
    boot = next(p for p in storages["EMMC"] if p.name == "boot_a")
    assert isinstance(boot, PackagePartition)
    assert boot.is_download is True
    assert boot.is_upgradable is True
    assert boot.operation_type == "UPDATE"
    assert boot.linear_start_addr == 0x2d900000
    assert boot.partition_size == 0x4000000
    assert boot.filename == os.path.join(str(package), "boot.img")
    assert boot.is_protected is False


def test_none_file_name_yields_no_image(package):
    storages = parse_scatter(str(package / "demo_scatter.xml"), str(package))
    pgpt = next(p for p in storages["EMMC"] if p.name == "pgpt")
    assert pgpt.filename is None
    assert pgpt.has_image is False
    assert pgpt.is_protected is True  # INVISIBLE


def test_parse_flash_xml_resolves_scatter_and_da(package):
    pkg = parse_flash_xml(str(package / "download_agent" / "flash.xml"))
    assert isinstance(pkg, FlashPackage)
    assert pkg.project == "demo_project"
    assert pkg.build_version == "alps-mp-u0.mp1-V1"
    assert pkg.root == str(package)
    assert pkg.da_loader == os.path.join(str(package), "download_agent", "DA_BR.bin")
    assert pkg.scatter_path == os.path.join(str(package), "demo_scatter.xml")
    assert set(pkg.storage_names()) == {"EMMC", "UFS"}


def test_download_list_skips_protected_and_missing_files(package):
    pkg = parse_flash_xml(str(package / "download_agent" / "flash.xml"))
    names = [p.name for p in pkg.download_list("EMMC")]
    # boot.img exists -> included; preloader image missing -> excluded;
    # pgpt/nvram are is_download=false -> excluded.
    assert names == ["boot_a"]


def test_missing_images_reports_absent_downloadables(package):
    pkg = parse_flash_xml(str(package / "download_agent" / "flash.xml"))
    missing = [p.name for p in pkg.missing_images("EMMC")]
    assert missing == ["preloader_a"]


def test_partitions_unknown_storage_raises(package):
    pkg = parse_flash_xml(str(package / "download_agent" / "flash.xml"))
    with pytest.raises(ValueError):
        pkg.partitions("NAND")


def test_missing_flash_xml_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        parse_flash_xml(str(tmp_path / "nope.xml"))


@pytest.mark.skipif(
    not os.environ.get("MTK_TEST_PACKAGE"),
    reason="set MTK_TEST_PACKAGE to a real flash.xml path to run",
)
def test_real_package_parses():
    pkg = parse_flash_xml(os.environ["MTK_TEST_PACKAGE"])
    assert pkg.storage_names()
    for storage in pkg.storage_names():
        assert pkg.partitions(storage)
