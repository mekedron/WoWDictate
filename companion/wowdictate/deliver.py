"""Hands text to the addon: clipboard + (receive key) + paste key on a virtual keyboard.

Wire format of one message (see docs/protocol.md):  ##WD#<kind>#<payload>#WD##
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable

from .keys import Combo

log = logging.getLogger(__name__)


def encode(kind: str, payload: str = "") -> str:
    # "|" starts WoW escape sequences and line breaks end chat messages.
    clean = payload.replace("|", "/").replace("\r", " ").replace("\n", " ")
    return f"##WD#{kind}#{clean}#WD##"


class Deliverer:
    def __init__(
        self,
        platform,
        receive: Combo | None,
        clipboard_delay_ms: int,
        focus_delay_ms: int,
        restore_clipboard: bool,
        modifiers_down: Callable[[], bool],
    ):
        self.platform = platform
        self.receive = receive
        self.clipboard_delay = clipboard_delay_ms / 1000
        self.focus_delay = focus_delay_ms / 1000
        self.restore_clipboard = restore_clipboard
        self.modifiers_down = modifiers_down
        combos = [platform.paste] + ([receive] if receive else [])
        self.keyboard = platform.keyboard(combos)
        self.lock = asyncio.Lock()

    async def _wait_for_modifiers(self, limit: float = 1.5) -> None:
        deadline = time.monotonic() + limit
        while self.modifiers_down() and time.monotonic() < deadline:
            await asyncio.sleep(0.02)

    async def send(self, message: str, receive_key: bool = False) -> None:
        """Paste a message. The addon focuses its input box when a dictation key is
        released; receive_key=True presses the receive key first (unprompted pushes)."""
        clipboard = self.platform.clipboard
        async with self.lock:
            saved = await clipboard.save() if self.restore_clipboard else None
            await clipboard.set(message)
            await asyncio.sleep(self.clipboard_delay)
            await self._wait_for_modifiers()
            if receive_key and self.receive:
                await asyncio.to_thread(self.keyboard.tap, self.receive)
                await asyncio.sleep(self.focus_delay)
            await asyncio.to_thread(self.keyboard.tap, self.platform.paste)
            log.info("pasted %d chars%s", len(message), " after the receive key" if receive_key else "")
            if self.restore_clipboard:
                await asyncio.sleep(0.4)
                await clipboard.restore(saved)

    def close(self) -> None:
        self.keyboard.close()
