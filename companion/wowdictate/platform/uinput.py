"""Minimal uinput virtual keyboard that only needs write access to /dev/uinput.

python-evdev's UInput opens the device read-write; distributions (and the
udev rules here) often grant the input group write-only access, which is all
the legacy uinput setup needs.
"""

from __future__ import annotations

import fcntl
import os
import struct

UI_SET_EVBIT = 0x40045564
UI_SET_KEYBIT = 0x40045565
UI_DEV_CREATE = 0x5501
UI_DEV_DESTROY = 0x5502
EV_SYN, EV_KEY, SYN_REPORT = 0x00, 0x01, 0
BUS_USB = 0x03


class VirtualKeyboard:
    def __init__(self, keys: list[int], name: str, path: str = "/dev/uinput"):
        self.fd = os.open(path, os.O_WRONLY | os.O_NONBLOCK)
        try:
            fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_KEY)
            for key in keys:
                fcntl.ioctl(self.fd, UI_SET_KEYBIT, key)
            # struct uinput_user_dev: name[80], input_id, ff_effects_max, abs arrays
            user_dev = struct.pack("80sHHHHI", name.encode()[:79], BUS_USB, 0x1209, 0x5744, 1, 0)
            user_dev += b"\0" * (4 * 64 * 4)
            os.write(self.fd, user_dev)
            fcntl.ioctl(self.fd, UI_DEV_CREATE)
        except OSError:
            os.close(self.fd)
            raise

    def _event(self, type_: int, code: int, value: int) -> None:
        os.write(self.fd, struct.pack("llHHi", 0, 0, type_, code, value))

    def key(self, code: int, down: bool) -> None:
        self._event(EV_KEY, code, 1 if down else 0)
        self._event(EV_SYN, SYN_REPORT, 0)

    def close(self) -> None:
        try:
            fcntl.ioctl(self.fd, UI_DEV_DESTROY)
        finally:
            os.close(self.fd)
