"""Linux: evdev for keys, uinput for typing, xclip/wl-clipboard, KWin or X11 for focus.

Works on Wayland and X11. Needs read access to /dev/input/event* and write
access to /dev/uinput (the `input` group on most distributions).
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import time

import evdev
from evdev import ecodes

from ..keys import Combo
from .uinput import VirtualKeyboard

log = logging.getLogger(__name__)

OWN_DEVICE_PREFIX = "wow-dictate"
RESCAN_SECONDS = 3
MODIFIER_LEAD = 0.06  # Wine applies modifiers late; see docs/protocol.md
KEY_HOLD = 0.03

# --- key names ------------------------------------------------------------

_SPECIAL = {
    "BUTTON1": ecodes.BTN_LEFT, "BUTTON2": ecodes.BTN_RIGHT, "BUTTON3": ecodes.BTN_MIDDLE,
    "BUTTON4": ecodes.BTN_SIDE, "BUTTON5": ecodes.BTN_EXTRA,
    "SPACE": ecodes.KEY_SPACE, "TAB": ecodes.KEY_TAB, "ENTER": ecodes.KEY_ENTER,
    "ESCAPE": ecodes.KEY_ESC, "BACKSPACE": ecodes.KEY_BACKSPACE, "CAPSLOCK": ecodes.KEY_CAPSLOCK,
    "INSERT": ecodes.KEY_INSERT, "DELETE": ecodes.KEY_DELETE, "HOME": ecodes.KEY_HOME,
    "END": ecodes.KEY_END, "PAGEUP": ecodes.KEY_PAGEUP, "PAGEDOWN": ecodes.KEY_PAGEDOWN,
    "UP": ecodes.KEY_UP, "DOWN": ecodes.KEY_DOWN, "LEFT": ecodes.KEY_LEFT, "RIGHT": ecodes.KEY_RIGHT,
    "PAUSE": ecodes.KEY_PAUSE, "SCROLLLOCK": ecodes.KEY_SCROLLLOCK, "PRINTSCREEN": ecodes.KEY_SYSRQ,
    "NUMPADPLUS": ecodes.KEY_KPPLUS, "NUMPADMINUS": ecodes.KEY_KPMINUS,
    "NUMPADMULTIPLY": ecodes.KEY_KPASTERISK, "NUMPADDIVIDE": ecodes.KEY_KPSLASH,
    "NUMPADDECIMAL": ecodes.KEY_KPDOT,
    "`": ecodes.KEY_GRAVE, "-": ecodes.KEY_MINUS, "=": ecodes.KEY_EQUAL,
    "[": ecodes.KEY_LEFTBRACE, "]": ecodes.KEY_RIGHTBRACE, ";": ecodes.KEY_SEMICOLON,
    "'": ecodes.KEY_APOSTROPHE, ",": ecodes.KEY_COMMA, ".": ecodes.KEY_DOT,
    "/": ecodes.KEY_SLASH, "\\": ecodes.KEY_BACKSLASH,
}
CODE_BY_NAME: dict[str, int] = dict(_SPECIAL)
CODE_BY_NAME.update({chr(c): ecodes.ecodes[f"KEY_{chr(c)}"] for c in range(ord("A"), ord("Z") + 1)})
CODE_BY_NAME.update({str(d): ecodes.ecodes[f"KEY_{d}"] for d in range(10)})
CODE_BY_NAME.update({f"F{n}": ecodes.ecodes[f"KEY_F{n}"] for n in range(1, 25)})
CODE_BY_NAME.update({f"NUMPAD{d}": ecodes.ecodes[f"KEY_KP{d}"] for d in range(10)})
NAME_BY_CODE = {code: name for name, code in CODE_BY_NAME.items()}

# Which physical keys act as which modifier. xkb options can move them: with
# ctrl:swap_lwin_lctl the key labelled Ctrl is Super and Win is Ctrl.
DEFAULT_MODIFIERS = {
    "CTRL": {ecodes.KEY_LEFTCTRL, ecodes.KEY_RIGHTCTRL},
    "ALT": {ecodes.KEY_LEFTALT, ecodes.KEY_RIGHTALT},
    "SHIFT": {ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT},
    "META": {ecodes.KEY_LEFTMETA, ecodes.KEY_RIGHTMETA},
}
XKB_OPTIONS = {
    # option: [(modifier, physical key)] moves
    "ctrl:swap_lwin_lctl": [("CTRL", ecodes.KEY_LEFTMETA), ("META", ecodes.KEY_LEFTCTRL)],
    "ctrl:swap_rwin_rctl": [("CTRL", ecodes.KEY_RIGHTMETA), ("META", ecodes.KEY_RIGHTCTRL)],
    "ctrl:swap_lalt_lctl": [("CTRL", ecodes.KEY_LEFTALT), ("ALT", ecodes.KEY_LEFTCTRL)],
    "ctrl:swap_ralt_rctl": [("CTRL", ecodes.KEY_RIGHTALT), ("ALT", ecodes.KEY_RIGHTCTRL)],
    "ctrl:swap_lalt_lctl_lwin": [("CTRL", ecodes.KEY_LEFTALT), ("ALT", ecodes.KEY_LEFTMETA),
                                 ("META", ecodes.KEY_LEFTCTRL)],
    "ctrl:nocaps": [("CTRL", ecodes.KEY_CAPSLOCK)],
    "ctrl:swapcaps": [("CTRL", ecodes.KEY_CAPSLOCK), (None, ecodes.KEY_LEFTCTRL)],
    "altwin:swap_alt_win": [("ALT", ecodes.KEY_LEFTMETA), ("ALT", ecodes.KEY_RIGHTMETA),
                            ("META", ecodes.KEY_LEFTALT), ("META", ecodes.KEY_RIGHTALT)],
    "altwin:swap_lalt_lwin": [("ALT", ecodes.KEY_LEFTMETA), ("META", ecodes.KEY_LEFTALT)],
    "altwin:ctrl_win": [("CTRL", ecodes.KEY_LEFTMETA), ("CTRL", ecodes.KEY_RIGHTMETA)],
    "altwin:ctrl_alt_win": [("CTRL", ecodes.KEY_LEFTALT), ("CTRL", ecodes.KEY_RIGHTALT)],
}
# Right Alt is AltGr in many layouts, so Alt is typed with the left key.
PREFERRED_PRESS = {
    "CTRL": [ecodes.KEY_RIGHTCTRL, ecodes.KEY_LEFTCTRL, ecodes.KEY_LEFTMETA, ecodes.KEY_CAPSLOCK],
    "SHIFT": [ecodes.KEY_RIGHTSHIFT, ecodes.KEY_LEFTSHIFT],
    "ALT": [ecodes.KEY_LEFTALT, ecodes.KEY_LEFTCTRL, ecodes.KEY_LEFTMETA, ecodes.KEY_RIGHTALT],
    "META": [ecodes.KEY_LEFTMETA, ecodes.KEY_RIGHTMETA, ecodes.KEY_LEFTCTRL],
}


def _run_quiet(*args: str) -> str:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=2).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def xkb_options() -> list[str]:
    """xkb options from KDE, GNOME, X11 or XKB_DEFAULT_OPTIONS (Wayland compositors)."""
    found: list[str] = []
    found += os.environ.get("XKB_DEFAULT_OPTIONS", "").split(",")
    config = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    try:
        with open(os.path.join(config, "kxkbrc"), encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.startswith("Options="):
                    found += line[len("Options="):].strip().split(",")
    except OSError:
        pass
    if shutil.which("gsettings"):
        gnome = _run_quiet("gsettings", "get", "org.gnome.desktop.input-sources", "xkb-options")
        found += [o.strip(" '") for o in gnome.strip().strip("@as").strip(" []").split(",")]
    if os.environ.get("DISPLAY") and shutil.which("setxkbmap"):
        for line in _run_quiet("setxkbmap", "-query").splitlines():
            if line.startswith("options:"):
                found += line.split(":", 1)[1].strip().split(",")
    return sorted({o.strip() for o in found if o.strip()})


def modifier_map(options: list[str]) -> tuple[dict[int, str], dict[str, int]]:
    """Physical key -> modifier name, and modifier name -> key to press."""
    by_key = {code: name for name, codes in DEFAULT_MODIFIERS.items() for code in codes}
    by_key.pop(ecodes.KEY_CAPSLOCK, None)
    for option in options:
        for name, code in XKB_OPTIONS.get(option, []):
            if name is None:
                by_key.pop(code, None)
            else:
                by_key[code] = name
    press = {}
    for name, candidates in PREFERRED_PRESS.items():
        press[name] = next((c for c in candidates if by_key.get(c) == name), candidates[0])
    return by_key, press


# --- clipboard ------------------------------------------------------------

MAX_CLIPBOARD_BYTES = 32 * 1024 * 1024


async def _run(*args: str, data: bytes | None = None, capture: bool = True) -> tuple[int, bytes]:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.PIPE if data is not None else asyncio.subprocess.DEVNULL,
        # xclip -i and wl-copy fork a child that keeps serving: never wait on its stdout.
        stdout=asyncio.subprocess.PIPE if capture else asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    out, _ = await proc.communicate(data)
    return proc.returncode or 0, out or b""


class XClipboard:
    """X11 CLIPBOARD via xclip. Used whenever an X server is reachable: the game
    runs under Wine/Proton on X11 or XWayland and reads this clipboard directly.
    (wl-copy on KWin maps a small focus-grabbing surface, which takes focus away
    from the game.)"""

    TEXT_TYPES = ("UTF8_STRING", "text/plain;charset=utf-8", "STRING", "TEXT")

    async def save(self):
        code, targets = await _run("xclip", "-o", "-selection", "clipboard", "-t", "TARGETS")
        if code != 0 or not targets.strip():
            return None
        names = targets.decode(errors="replace").split()
        preferred = next((t for t in self.TEXT_TYPES if t in names), None) or next(
            (t for t in names if "/" in t), None
        )
        if preferred is None:
            return None
        code, data = await _run("xclip", "-o", "-selection", "clipboard", "-t", preferred)
        if code != 0 or len(data) > MAX_CLIPBOARD_BYTES:
            return None
        return preferred, data

    async def set(self, text: str, mime: str = "UTF8_STRING", data: bytes | None = None) -> None:
        await _run("xclip", "-selection", "clipboard", "-t", mime, "-i",
                   data=data if data is not None else text.encode(), capture=False)

    async def restore(self, saved) -> None:
        if saved is not None:
            await self.set("", saved[0], saved[1])


class WaylandClipboard:
    """wl-clipboard, for games running as native Wayland clients."""

    async def save(self):
        code, types = await _run("wl-paste", "--list-types")
        if code != 0 or not types.strip():
            return None
        mime_types = types.decode(errors="replace").split()
        preferred = next((t for t in mime_types if t.startswith("text/plain")), mime_types[0])
        code, data = await _run("wl-paste", "--no-newline", "--type", preferred)
        if code != 0 or len(data) > MAX_CLIPBOARD_BYTES:
            return None
        return preferred, data

    async def set(self, text: str, mime: str = "text/plain;charset=utf-8", data: bytes | None = None) -> None:
        await _run("wl-copy", "--type", mime, data=data if data is not None else text.encode(), capture=False)

    async def restore(self, saved) -> None:
        if saved is not None:
            await self.set("", saved[0], saved[1])


# --- keyboard -------------------------------------------------------------


class Keyboard:
    def __init__(self, combos: list[Combo], press: dict[str, int]):
        self.press = press
        keys = {press[m] for c in combos for m in c.modifiers} | {CODE_BY_NAME[c.key] for c in combos}
        self.device = VirtualKeyboard(sorted(keys), f"{OWN_DEVICE_PREFIX}-keyboard")
        time.sleep(0.3)  # let the compositor pick up the new device

    def tap(self, combo: Combo) -> None:
        mods = [self.press[m] for m in ("CTRL", "ALT", "SHIFT", "META") if m in combo.modifiers]
        for code in mods:
            self.device.key(code, True)
        if mods:
            time.sleep(MODIFIER_LEAD)
        key = CODE_BY_NAME[combo.key]
        self.device.key(key, True)
        time.sleep(KEY_HOLD)
        self.device.key(key, False)
        if mods:
            time.sleep(MODIFIER_LEAD)
        for code in reversed(mods):
            self.device.key(code, False)

    def close(self) -> None:
        self.device.close()


# --- platform -------------------------------------------------------------


class Platform:
    name = "linux"
    paste = Combo(frozenset({"CTRL"}), "V")

    def __init__(self):
        self.options = xkb_options()
        self.modifier_by_key, self.press = modifier_map(self.options)
        if os.environ.get("DISPLAY") and shutil.which("xclip"):
            self.clipboard = XClipboard()
        elif shutil.which("wl-copy"):
            self.clipboard = WaylandClipboard()
        else:
            raise RuntimeError("install xclip (X11/XWayland) or wl-clipboard (Wayland)")
        self.kwin = None
        self.tasks: dict[str, asyncio.Task] = {}
        log.info("xkb options: %s", ",".join(self.options) or "none")

    # focus
    async def _start_focus(self) -> None:
        from .kwin import KWinFocus

        kwin = KWinFocus()
        if await kwin.start():
            self.kwin = kwin
        elif os.environ.get("DISPLAY") and shutil.which("xprop"):
            log.info("tracking the active window through X11 (_NET_ACTIVE_WINDOW)")
        else:
            log.warning("cannot see the active window; dictation works in every window")

    def active_window(self) -> str | None:
        if self.kwin is not None:
            return self.kwin.caption
        if os.environ.get("DISPLAY") and shutil.which("xprop"):
            out = _run_quiet("xprop", "-root", "_NET_ACTIVE_WINDOW")
            window = out.strip().split()[-1] if out.strip() else ""
            if window.startswith("0x") and int(window, 16):
                name = _run_quiet("xprop", "-id", window, "_NET_WM_NAME")
                if "=" in name:
                    return name.split("=", 1)[1].strip().strip('"')
        return None

    # hotkeys
    def _wanted(self, device: evdev.InputDevice, codes: set[int]) -> bool:
        if device.name.startswith(OWN_DEVICE_PREFIX):
            return False
        return bool(set(device.capabilities().get(ecodes.EV_KEY, [])) & codes)

    async def _read(self, device: evdev.InputDevice, matcher) -> None:
        try:
            async for event in device.async_read_loop():
                if event.type != ecodes.EV_KEY or event.value == 2:
                    continue
                name = self.modifier_by_key.get(event.code) or NAME_BY_CODE.get(event.code)
                matcher.feed(name, event.value == 1, (device.path, event.code))
        except OSError:
            log.info("input device gone: %s", device.name)
        finally:
            self.tasks.pop(device.path, None)

    async def _scan(self, matcher) -> None:
        codes = {CODE_BY_NAME[c.key] for c in matcher.combos}
        while True:
            for path in evdev.list_devices():
                if path in self.tasks:
                    continue
                try:
                    device = evdev.InputDevice(path)
                except OSError:
                    continue
                if self._wanted(device, codes):
                    log.info("watching %s (%s)", device.name, path)
                    self.tasks[path] = asyncio.create_task(self._read(device, matcher))
                else:
                    device.close()
            await asyncio.sleep(RESCAN_SECONDS)

    async def start(self, matcher, loop) -> None:  # noqa: ARG002
        await self._start_focus()
        self.scanner = asyncio.create_task(self._scan(matcher))

    async def stop(self) -> None:
        self.scanner.cancel()
        for task in list(self.tasks.values()):
            task.cancel()
        if self.kwin is not None:
            await self.kwin.stop()

    def keyboard(self, combos: list[Combo]) -> Keyboard:
        return Keyboard(combos, self.press)
