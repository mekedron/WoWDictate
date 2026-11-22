"""Platform-neutral key names, written like WoW key bindings.

Keys are named the way WoW names them in bindings: "A".."Z", "0".."9",
"F1".."F24", "NUMPAD0".., "BUTTON1".."BUTTON5", "SPACE", "`", ... Modifiers are
"CTRL", "ALT", "SHIFT" and, on macOS, "META" (Command). Platform modules
translate their native key codes to and from these names.
"""

from __future__ import annotations

from dataclasses import dataclass

MODIFIER_NAMES = ("CTRL", "ALT", "SHIFT", "META")

NAMED_KEYS = {
    "SPACE", "TAB", "ENTER", "ESCAPE", "BACKSPACE", "CAPSLOCK",
    "INSERT", "DELETE", "HOME", "END", "PAGEUP", "PAGEDOWN",
    "UP", "DOWN", "LEFT", "RIGHT", "PAUSE", "SCROLLLOCK", "PRINTSCREEN",
    "NUMPADPLUS", "NUMPADMINUS", "NUMPADMULTIPLY", "NUMPADDIVIDE", "NUMPADDECIMAL",
    "`", "-", "=", "[", "]", ";", "'", ",", ".", "/", "\\",
}
KEY_NAMES = (
    NAMED_KEYS
    | {chr(c) for c in range(ord("A"), ord("Z") + 1)}
    | {str(d) for d in range(10)}
    | {f"F{n}" for n in range(1, 25)}
    | {f"NUMPAD{d}" for d in range(10)}
    | {f"BUTTON{n}" for n in range(1, 6)}
)


@dataclass(frozen=True)
class Combo:
    modifiers: frozenset[str]
    key: str

    @property
    def text(self) -> str:
        order = [m for m in ("ALT", "CTRL", "SHIFT", "META") if m in self.modifiers]
        return "-".join([*order, self.key])


def parse(binding: str) -> Combo:
    """Parse "CTRL-SHIFT-F12", "BUTTON3", "ALT--" (Alt + minus)."""
    text = binding.strip().upper()
    if not text:
        raise ValueError("empty key")
    if text.endswith("--") or text == "-":
        mods, key = [p for p in text[:-1].split("-") if p], "-"
    else:
        *mods, key = text.split("-")
    aliases = {"CMD": "META", "COMMAND": "META", "OPTION": "ALT", "CONTROL": "CTRL", "ESC": "ESCAPE",
               "RETURN": "ENTER", "MIDDLEBUTTON": "BUTTON3"}
    mods = [aliases.get(m, m) for m in mods]
    key = aliases.get(key, key)
    for mod in mods:
        if mod not in MODIFIER_NAMES:
            raise ValueError(f"unknown modifier {mod!r} in {binding!r}")
    if key not in KEY_NAMES:
        raise ValueError(f"unknown key {key!r} in {binding!r}")
    return Combo(frozenset(mods), key)


class HotkeyMatcher:
    """Turns a stream of (key name, down/up) from any platform into trigger presses.

    Modifiers must match exactly, as in WoW: "BUTTON3" does not fire while Shift
    is held, "SHIFT-BUTTON3" does.
    """

    def __init__(self, combos, on_press, on_release):
        self.combos = combos
        self.on_press = on_press
        self.on_release = on_release
        self.held: dict[str, set] = {m: set() for m in MODIFIER_NAMES}
        self.active: dict[str, int] = {}

    def modifiers_down(self) -> bool:
        return any(self.held.values())

    def feed(self, name: str | None, down: bool, source=None) -> None:
        """name: key name or modifier name; source: anything identifying the physical
        key, so that left and right Ctrl are tracked separately."""
        if name is None:
            return
        if name in self.held:
            (self.held[name].add if down else self.held[name].discard)(source if source is not None else name)
            return
        if down:
            if name in self.active:
                return  # autorepeat
            mods = frozenset(m for m, keys in self.held.items() if keys)
            for index, combo in enumerate(self.combos):
                if combo.key == name and combo.modifiers == mods:
                    self.active[name] = index
                    self.on_press(index)
                    return
        elif name in self.active:
            self.on_release(self.active.pop(name))
