"""Windows: low-level keyboard/mouse hooks and SendInput (pynput), Win32 clipboard.

The companion must run at the same privilege level as the game: Windows does
not let a normal process press keys in a window of a process started "as
administrator".
"""

from __future__ import annotations

import asyncio
import ctypes
import logging
from ctypes import wintypes

from ..keys import Combo
from .pynput_common import PynputInput, PynputKeyboard

log = logging.getLogger(__name__)

VK_BY_NAME: dict[str, int] = {
    "SPACE": 0x20, "TAB": 0x09, "ENTER": 0x0D, "ESCAPE": 0x1B, "BACKSPACE": 0x08, "CAPSLOCK": 0x14,
    "INSERT": 0x2D, "DELETE": 0x2E, "HOME": 0x24, "END": 0x23, "PAGEUP": 0x21, "PAGEDOWN": 0x22,
    "LEFT": 0x25, "UP": 0x26, "RIGHT": 0x27, "DOWN": 0x28, "PAUSE": 0x13, "SCROLLLOCK": 0x91,
    "PRINTSCREEN": 0x2C,
    "NUMPADMULTIPLY": 0x6A, "NUMPADPLUS": 0x6B, "NUMPADMINUS": 0x6D, "NUMPADDECIMAL": 0x6E,
    "NUMPADDIVIDE": 0x6F,
    "`": 0xC0, "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD, ";": 0xBA, "'": 0xDE, ",": 0xBC,
    ".": 0xBE, "/": 0xBF, "\\": 0xDC,
}
VK_BY_NAME.update({chr(c): c for c in range(ord("A"), ord("Z") + 1)})
VK_BY_NAME.update({str(d): 0x30 + d for d in range(10)})
VK_BY_NAME.update({f"F{n}": 0x6F + n for n in range(1, 25)})
VK_BY_NAME.update({f"NUMPAD{d}": 0x60 + d for d in range(10)})
NAME_BY_VK = {vk: name for name, vk in VK_BY_NAME.items()}

MODIFIER_BY_VK = {
    0x10: "SHIFT", 0xA0: "SHIFT", 0xA1: "SHIFT",
    0x11: "CTRL", 0xA2: "CTRL", 0xA3: "CTRL",
    0x12: "ALT", 0xA4: "ALT", 0xA5: "ALT",
    0x5B: "META", 0x5C: "META",
}
MOUSE_NAMES = {"left": "BUTTON1", "right": "BUTTON2", "middle": "BUTTON3", "x1": "BUTTON4", "x2": "BUTTON5"}

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002


class Win32Clipboard:
    """Unicode text clipboard through the Win32 API (other formats are not kept)."""

    def __init__(self):
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        u, k = self.user32, self.kernel32
        u.OpenClipboard.argtypes = [wintypes.HWND]
        u.GetClipboardData.restype = wintypes.HANDLE
        u.GetClipboardData.argtypes = [wintypes.UINT]
        u.SetClipboardData.restype = wintypes.HANDLE
        u.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
        k.GlobalAlloc.restype = wintypes.HGLOBAL
        k.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
        k.GlobalLock.restype = ctypes.c_void_p
        k.GlobalLock.argtypes = [wintypes.HGLOBAL]
        k.GlobalUnlock.argtypes = [wintypes.HGLOBAL]

    def _open(self) -> bool:
        for _ in range(20):
            if self.user32.OpenClipboard(None):
                return True
            import time

            time.sleep(0.01)
        return False

    def _get(self) -> str | None:
        if not self._open():
            return None
        try:
            handle = self.user32.GetClipboardData(CF_UNICODETEXT)
            if not handle:
                return None
            pointer = self.kernel32.GlobalLock(handle)
            try:
                return ctypes.wstring_at(pointer)
            finally:
                self.kernel32.GlobalUnlock(handle)
        finally:
            self.user32.CloseClipboard()

    def _set(self, text: str) -> None:
        data = text.encode("utf-16-le") + b"\0\0"
        if not self._open():
            raise OSError("clipboard is busy")
        try:
            self.user32.EmptyClipboard()
            handle = self.kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
            pointer = self.kernel32.GlobalLock(handle)
            ctypes.memmove(pointer, data, len(data))
            self.kernel32.GlobalUnlock(handle)
            self.user32.SetClipboardData(CF_UNICODETEXT, handle)
        finally:
            self.user32.CloseClipboard()

    async def save(self):
        return await asyncio.to_thread(self._get)

    async def set(self, text: str) -> None:
        await asyncio.to_thread(self._set, text)

    async def restore(self, saved) -> None:
        if saved is not None:
            await self.set(saved)


class Platform:
    name = "windows"
    paste = Combo(frozenset({"CTRL"}), "V")

    def __init__(self):
        self.clipboard = Win32Clipboard()
        self.input = PynputInput(NAME_BY_VK, MODIFIER_BY_VK, MOUSE_NAMES)
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self.user32 = user32

    def active_window(self) -> str | None:
        hwnd = self.user32.GetForegroundWindow()
        if not hwnd:
            return None
        length = self.user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(length + 1)
        self.user32.GetWindowTextW(hwnd, buffer, length + 1)
        return buffer.value

    async def start(self, matcher, loop) -> None:
        self.input.start(matcher, loop)
        log.info("listening to keyboard and mouse hooks")

    async def stop(self) -> None:
        self.input.stop()

    def keyboard(self, combos: list[Combo]):
        from pynput.keyboard import Key

        return PynputKeyboard(VK_BY_NAME, {"CTRL": Key.ctrl, "ALT": Key.alt, "SHIFT": Key.shift, "META": Key.cmd})
