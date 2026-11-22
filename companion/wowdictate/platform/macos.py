"""macOS: Quartz event taps and CGEvent typing (pynput), NSPasteboard, Quartz window list.

The program that runs the companion (Terminal, or Python for the LaunchAgent)
needs Accessibility, Input Monitoring and Microphone permission in System
Settings > Privacy & Security.
"""

from __future__ import annotations

import asyncio
import logging

from ..keys import Combo
from .pynput_common import PynputInput, PynputKeyboard

log = logging.getLogger(__name__)

# macOS virtual key codes (ANSI layout positions; independent of the input language).
VK_BY_NAME: dict[str, int] = {
    "A": 0x00, "S": 0x01, "D": 0x02, "F": 0x03, "H": 0x04, "G": 0x05, "Z": 0x06, "X": 0x07,
    "C": 0x08, "V": 0x09, "B": 0x0B, "Q": 0x0C, "W": 0x0D, "E": 0x0E, "R": 0x0F, "Y": 0x10,
    "T": 0x11, "1": 0x12, "2": 0x13, "3": 0x14, "4": 0x15, "6": 0x16, "5": 0x17, "=": 0x18,
    "9": 0x19, "7": 0x1A, "-": 0x1B, "8": 0x1C, "0": 0x1D, "]": 0x1E, "O": 0x1F, "U": 0x20,
    "[": 0x21, "I": 0x22, "P": 0x23, "ENTER": 0x24, "L": 0x25, "J": 0x26, "'": 0x27, "K": 0x28,
    ";": 0x29, "\\": 0x2A, ",": 0x2B, "/": 0x2C, "N": 0x2D, "M": 0x2E, ".": 0x2F, "TAB": 0x30,
    "SPACE": 0x31, "`": 0x32, "BACKSPACE": 0x33, "ESCAPE": 0x35, "CAPSLOCK": 0x39,
    "NUMPADDECIMAL": 0x41, "NUMPADMULTIPLY": 0x43, "NUMPADPLUS": 0x45, "NUMPADDIVIDE": 0x4B,
    "NUMPADMINUS": 0x4E, "NUMPAD0": 0x52, "NUMPAD1": 0x53, "NUMPAD2": 0x54, "NUMPAD3": 0x55,
    "NUMPAD4": 0x56, "NUMPAD5": 0x57, "NUMPAD6": 0x58, "NUMPAD7": 0x59, "NUMPAD8": 0x5B,
    "NUMPAD9": 0x5C, "F5": 0x60, "F6": 0x61, "F7": 0x62, "F3": 0x63, "F8": 0x64, "F9": 0x65,
    "F11": 0x67, "F13": 0x69, "F16": 0x6A, "F14": 0x6B, "F10": 0x6D, "F12": 0x6F, "F15": 0x71,
    "HOME": 0x73, "PAGEUP": 0x74, "DELETE": 0x75, "F4": 0x76, "END": 0x77, "F2": 0x78,
    "PAGEDOWN": 0x79, "F1": 0x7A, "LEFT": 0x7B, "RIGHT": 0x7C, "DOWN": 0x7D, "UP": 0x7E,
    "F17": 0x40, "F18": 0x4F, "F19": 0x50, "F20": 0x5A,
}
NAME_BY_VK = {vk: name for name, vk in VK_BY_NAME.items()}
MODIFIER_BY_VK = {
    0x37: "META", 0x36: "META",  # Command
    0x38: "SHIFT", 0x3C: "SHIFT",
    0x3A: "ALT", 0x3D: "ALT",  # Option
    0x3B: "CTRL", 0x3E: "CTRL",
}
MOUSE_NAMES = {"left": "BUTTON1", "right": "BUTTON2", "middle": "BUTTON3"}


class MacClipboard:
    """Text clipboard through NSPasteboard."""

    def __init__(self):
        from AppKit import NSPasteboard, NSPasteboardTypeString

        self.board = NSPasteboard.generalPasteboard()
        self.text_type = NSPasteboardTypeString

    def _get(self):
        return self.board.stringForType_(self.text_type)

    def _set(self, text: str) -> None:
        self.board.clearContents()
        self.board.setString_forType_(text, self.text_type)

    async def save(self):
        return await asyncio.to_thread(self._get)

    async def set(self, text: str) -> None:
        await asyncio.to_thread(self._set, text)

    async def restore(self, saved) -> None:
        if saved is not None:
            await self.set(str(saved))


class Platform:
    name = "macos"
    paste = Combo(frozenset({"META"}), "V")

    def __init__(self):
        self.clipboard = MacClipboard()
        self.input = PynputInput(NAME_BY_VK, MODIFIER_BY_VK, MOUSE_NAMES)

    def active_window(self) -> str | None:
        """Owner of the front-most normal window. Works without an AppKit run loop,
        unlike NSWorkspace.frontmostApplication in a background process."""
        from Quartz import (
            CGWindowListCopyWindowInfo,
            kCGNullWindowID,
            kCGWindowListExcludeDesktopElements,
            kCGWindowListOptionOnScreenOnly,
        )

        windows = CGWindowListCopyWindowInfo(
            kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements, kCGNullWindowID
        )
        for window in windows or []:
            if window.get("kCGWindowLayer", 1) == 0:
                return str(window.get("kCGWindowOwnerName", "")) or None
        return None

    async def start(self, matcher, loop) -> None:
        self.input.start(matcher, loop)
        log.info("listening to keyboard and mouse event taps")

    async def stop(self) -> None:
        self.input.stop()

    def keyboard(self, combos: list[Combo]):
        from pynput.keyboard import Key

        return PynputKeyboard(VK_BY_NAME, {"CTRL": Key.ctrl, "ALT": Key.alt, "SHIFT": Key.shift, "META": Key.cmd})
