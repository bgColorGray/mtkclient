"""Runtime hook: let pyusb find the libusb copy bundled inside the .app.

ctypes.util.find_library only searches system locations, which are empty on a
Mac without Homebrew. Point pyusb at the dylib shipped next to the executable
before any backend lookup happens.
"""
import os
import sys

if getattr(sys, "frozen", False):
    _base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    for _name in ("libusb-1.0.0.dylib", "libusb-1.0.dylib"):
        _path = os.path.join(_base, _name)
        if os.path.exists(_path):
            # Both are honoured by pyusb's libusb1 backend lookup.
            os.environ.setdefault("LIBUSB_LIBRARY", _path)
            os.environ["DYLD_LIBRARY_PATH"] = (
                _base + os.pathsep + os.environ.get("DYLD_LIBRARY_PATH", ""))
            try:
                import usb.backend.libusb1 as _b
                _b.get_backend(find_library=lambda _x: _path)
            except Exception:
                pass
            break
