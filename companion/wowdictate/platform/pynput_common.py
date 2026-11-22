"""Key and mouse listening and typing through pynput (Windows and macOS).

Keys are identified by virtual key code, not by the character they produce, so
the keyboard layout (Russian, English, ...) does not matter.
"""

from __future__ import annotations

import asyncio
import logging
import time

from ..keys import Combo

log = logging.getLogger(__name__)

MODIFIER_LEAD = 0.03
KEY_HOLD = 0.02


class PynputInput:
    """Listens to keyboard and mouse without blocking them for other programs."""

    def __init__(self, name_by_vk: dict[int, str], modifier_by_vk: dict[int, str], mouse_names: dict[str, str]):
        self.name_by_vk = name_by_vk
        self.modifier_by_vk = modifier_by_vk
        self.mouse_names = mouse_names
        self.listeners = []

    @staticmethod
    def _vk(key) -> int | None:
        vk = getattr(key, "vk", None)
        if vk is None and hasattr(key, "value"):
            vk = getattr(key.value, "vk", None)
        return vk

    def start(self, matcher, loop: asyncio.AbstractEventLoop) -> None:
        from pynput import keyboard, mouse

        def on_key(key, down: bool) -> None:
            vk = self._vk(key)
            if vk is None:
                return
            name = self.modifier_by_vk.get(vk) or self.name_by_vk.get(vk)
            loop.call_soon_threadsafe(matcher.feed, name, down, vk)

        def on_click(_x, _y, button, pressed) -> None:
            name = self.mouse_names.get(getattr(button, "name", ""))
            loop.call_soon_threadsafe(matcher.feed, name, pressed, button)

        kb = keyboard.Listener(on_press=lambda k: on_key(k, True), on_release=lambda k: on_key(k, False))
        ms = mouse.Listener(on_click=on_click)
        kb.start()
        ms.start()
        self.listeners = [kb, ms]

    def stop(self) -> None:
        for listener in self.listeners:
            listener.stop()


class PynputKeyboard:
    def __init__(self, vk_by_name: dict[str, int], modifier_keys: dict[str, object]):
        from pynput.keyboard import Controller

        self.controller = Controller()
        self.vk_by_name = vk_by_name
        self.modifier_keys = modifier_keys

    def tap(self, combo: Combo) -> None:
        from pynput.keyboard import KeyCode

        mods = [self.modifier_keys[m] for m in ("CTRL", "ALT", "SHIFT", "META") if m in combo.modifiers]
        for key in mods:
            self.controller.press(key)
        if mods:
            time.sleep(MODIFIER_LEAD)
        key = KeyCode.from_vk(self.vk_by_name[combo.key])
        self.controller.press(key)
        time.sleep(KEY_HOLD)
        self.controller.release(key)
        if mods:
            time.sleep(MODIFIER_LEAD)
        for key in reversed(mods):
            self.controller.release(key)

    def close(self) -> None:
        pass
