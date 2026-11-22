"""Platform-neutral checks of the companion (key names, matching, key tables).

Run: uv run --project companion python tests/test_companion.py
"""

import sys

from wowdictate import keys
from wowdictate.deliver import encode
from wowdictate.platform import is_game

failures = 0


def check(label, got, want):
    global failures
    ok = got == want
    failures += not ok
    print("OK  " if ok else "FAIL", label, "|", repr(got), "" if ok else f"!= {want!r}")


check("parse simple", keys.parse("button3"), keys.Combo(frozenset(), "BUTTON3"))
check("parse combo text", keys.parse("shift-ctrl-f12").text, "CTRL-SHIFT-F12")
check("parse minus", keys.parse("ALT--"), keys.Combo(frozenset({"ALT"}), "-"))
check("parse mac alias", keys.parse("CMD-V"), keys.Combo(frozenset({"META"}), "V"))
for bad in ("HYPER-V", "F99", ""):
    try:
        keys.parse(bad)
        check(f"reject {bad!r}", "accepted", "error")
    except ValueError:
        check(f"reject {bad!r}", "error", "error")

events = []
m = keys.HotkeyMatcher([keys.parse("BUTTON3"), keys.parse("SHIFT-BUTTON3")],
                       lambda i: events.append(("press", i)), lambda i: events.append(("release", i)))
m.feed("BUTTON3", True, "mouse")
m.feed("BUTTON3", True, "mouse")  # repeat
m.feed("BUTTON3", False, "mouse")
m.feed("SHIFT", True, "lshift")
m.feed("BUTTON3", True, "mouse")
m.feed("SHIFT", False, "lshift")  # released before the button: still the same trigger
m.feed("BUTTON3", False, "mouse")
m.feed("CTRL", True, "lctrl")
m.feed("BUTTON3", True, "mouse")  # CTRL-BUTTON3 is not a trigger
m.feed("BUTTON3", False, "mouse")
check("matcher", events, [("press", 0), ("release", 0), ("press", 1), ("release", 1)])
check("modifiers down", m.modifiers_down(), True)

check("encode", encode("t", "a|b\nc"), "##WD#t#a/b c#WD##")
check("is_game", (is_game("World of Warcraft", ["World of Warcraft"]), is_game("Konsole", ["World of Warcraft"]),
                  is_game(None, ["World of Warcraft"])), (True, False, True))

# Key tables: every WoW key name must be typeable / recognizable on each platform.
from wowdictate.platform import macos, windows  # noqa: E402  (tables only, no OS calls at import)

missing_win = sorted(keys.KEY_NAMES - set(windows.VK_BY_NAME) - {f"BUTTON{n}" for n in range(1, 6)})
check("windows table complete", missing_win, [])
check("windows vk unique", len(set(windows.VK_BY_NAME.values())), len(windows.VK_BY_NAME))
missing_mac = sorted(keys.KEY_NAMES - set(macos.VK_BY_NAME) - {f"BUTTON{n}" for n in range(1, 6)})
check("mac table gaps (no such keys on Macs)", all(k.startswith("F") or k in
      {"INSERT", "PAUSE", "SCROLLLOCK", "PRINTSCREEN"} for k in missing_mac), True)
check("mac vk unique", len(set(macos.VK_BY_NAME.values())), len(macos.VK_BY_NAME))

if sys.platform.startswith("linux"):
    from evdev import ecodes as e

    from wowdictate.platform import linux

    by_key, press = linux.modifier_map([])
    check("linux default ctrl", (by_key[e.KEY_LEFTCTRL], press["CTRL"]), ("CTRL", e.KEY_RIGHTCTRL))
    by_key, press = linux.modifier_map(["ctrl:swap_lwin_lctl"])
    check("swap_lwin_lctl", (by_key[e.KEY_LEFTCTRL], by_key[e.KEY_LEFTMETA], press["CTRL"]),
          ("META", "CTRL", e.KEY_RIGHTCTRL))
    by_key, press = linux.modifier_map(["ctrl:swap_lalt_lctl"])
    check("swap_lalt_lctl", (by_key[e.KEY_LEFTALT], by_key[e.KEY_LEFTCTRL], press["ALT"]),
          ("CTRL", "ALT", e.KEY_LEFTCTRL))
    check("linux table complete", sorted(keys.KEY_NAMES - set(linux.CODE_BY_NAME)), [])

print(f"\n{failures} failure(s)")
sys.exit(1 if failures else 0)
