# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the standalone firmware flashing app (macOS .app).

Bundles libusb explicitly: pyusb looks it up through ctypes.util.find_library,
which searches the system paths, so a machine without Homebrew would fail at
the first USB access if the dylib were not inside the bundle.
"""
import ctypes.util
import os
import shutil

# PyInstaller resolves relative paths against the spec's own directory, so
# anchor everything to the repository root instead.
ROOT = os.path.dirname(os.path.abspath(SPECPATH))  # noqa: F821
APP_NAME = "MTK Firmware Flasher"


def at_root(*parts):
    return os.path.join(ROOT, *parts)


def _libusb_candidates():
    """Every libusb copy worth bundling, so the app runs without Homebrew."""
    found = []
    located = ctypes.util.find_library("usb-1.0")
    if located and os.path.exists(located):
        found.append(located)
    for path in ("/opt/homebrew/lib/libusb-1.0.0.dylib",
                 "/usr/local/lib/libusb-1.0.0.dylib"):
        if os.path.exists(path) and path not in found:
            found.append(path)
    # pyusb's own backend search also accepts a bundled copy named libusb-1.0.dylib
    return [(p, ".") for p in found]


binaries = _libusb_candidates()
if not binaries:
    raise SystemExit("libusb not found; install it with: brew install libusb")

datas = [
    (at_root("mtkclient/Loader"), "mtkclient/Loader"),
    (at_root("mtkclient/payloads"), "mtkclient/payloads"),
    (at_root("mtkclient/gui/i18n"), "mtkclient/gui/i18n"),
    (at_root("mtkclient/gui/images"), "mtkclient/gui/images"),
]
datas = [(src, dst) for src, dst in datas if os.path.exists(src)]

a = Analysis(
    [at_root("mtk_flash_gui.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=["usb.backend.libusb1", "usb.backend.libusb0",
                   "mtkclient.Library.DA.xmlflash.xml_lib",
                   "mtkclient.Library.DA.flashpackage"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[at_root("packaging/rthook_libusb.py")],
    excludes=["tkinter", "matplotlib", "PyQt5", "PyQt6"],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="mtkflash",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="mtkflash",
)

app = BUNDLE(
    coll,
    name=f"{APP_NAME}.app",
    icon=at_root("packaging/mtkflash.icns"),
    bundle_identifier="org.mtkclient.flashgui",
    info_plist={
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleShortVersionString": os.environ.get("MTKFLASH_VERSION", "1.0.0"),
        "CFBundleVersion": os.environ.get("MTKFLASH_VERSION", "1.0.0"),
        "NSHighResolutionCapable": True,
        # Shown if macOS ever prompts for removable-volume access.
        "NSRemovableVolumesUsageDescription":
            "Needed to talk to a MediaTek device over USB.",
        "LSMinimumSystemVersion": "11.0",
    },
)
_ = shutil
