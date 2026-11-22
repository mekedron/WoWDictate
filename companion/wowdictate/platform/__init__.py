"""Operating system specific parts of the companion.

Every platform module provides a `Platform` class with:

- `paste`: the key combo that pastes in the game (Ctrl+V, Cmd+V on macOS)
- `async start(matcher, loop)`: start feeding key and mouse button events
  (WoW key names) into a `keys.HotkeyMatcher`; must not block the game's input
- `async stop()`
- `keyboard(combos) -> Keyboard`: a keyboard that can press the given combos
  (`tap(combo)`, `close()`)
- `clipboard`: `async save()`, `async set(text)`, `async restore(saved)`
- `active_window() -> str | None`: caption or application name of the active
  window, None when unknown
"""

from __future__ import annotations

import sys


def current():
    if sys.platform.startswith("linux"):
        from .linux import Platform
    elif sys.platform == "win32":
        from .windows import Platform
    elif sys.platform == "darwin":
        from .macos import Platform
    else:
        raise RuntimeError(f"unsupported platform {sys.platform}")
    return Platform()


def is_game(caption: str | None, windows: list[str]) -> bool:
    """True when the caption is one of the game windows, or unknown."""
    if caption is None:
        return True
    caption = caption.strip().lower()
    return any(caption == w.lower() or caption.startswith(w.lower()) for w in windows)
