"""Active window tracking on KDE Plasma (Wayland and X11) through a KWin script.

The script calls back into our D-Bus service whenever the active window changes.
start() returns False when KWin is not reachable (other desktops).
"""

import logging
import tempfile
from pathlib import Path

from dbus_fast import BusType
from dbus_fast.aio import MessageBus
from dbus_fast.service import ServiceInterface, method

log = logging.getLogger(__name__)

BUS_NAME = "dev.wowdictate"
OBJECT_PATH = "/dev/wowdictate"
INTERFACE = "dev.wowdictate.Focus"
SCRIPT_NAME = "wow-dictate-focus"

KWIN_SCRIPT = f"""
function report(w) {{
    callDBus("{BUS_NAME}", "{OBJECT_PATH}", "{INTERFACE}", "Activated",
             w ? String(w.caption) : "", w ? String(w.resourceClass) : "");
}}
workspace.windowActivated.connect(report);
workspace.windowList().forEach(function (w) {{
    w.captionChanged.connect(function () {{ if (w === workspace.activeWindow) report(w); }});
}});
workspace.windowAdded.connect(function (w) {{
    w.captionChanged.connect(function () {{ if (w === workspace.activeWindow) report(w); }});
}});
report(workspace.activeWindow);
"""


class _FocusInterface(ServiceInterface):
    def __init__(self, watcher: "KWinFocus"):
        super().__init__(INTERFACE)
        self.watcher = watcher

    @method()
    def Activated(self, caption: "s", window_class: "s"):  # noqa: N802, F821
        self.watcher.caption = caption
        self.watcher.window_class = window_class
        log.debug("active window: %r (%s)", caption, window_class)


class KWinFocus:
    def __init__(self):
        self.caption: str | None = None
        self.window_class: str | None = None
        self.available = False
        self.bus: MessageBus | None = None

    async def start(self) -> bool:
        try:
            self.bus = await MessageBus(bus_type=BusType.SESSION).connect()
            self.bus.export(OBJECT_PATH, _FocusInterface(self))
            await self.bus.request_name(BUS_NAME)
            scripting = await self._kwin("/Scripting", "org.kde.kwin.Scripting")
            await scripting.call_unload_script(SCRIPT_NAME)
            path = Path(tempfile.gettempdir()) / f"{SCRIPT_NAME}.js"
            path.write_text(KWIN_SCRIPT, encoding="utf-8")
            script_id = await scripting.call_load_script(str(path), SCRIPT_NAME)
            script = await self._kwin(f"/Scripting/Script{script_id}", "org.kde.kwin.Script")
            await script.call_run()
            self.available = True
            log.info("tracking the active window through KWin")
        except Exception as exc:  # noqa: BLE001 - any failure means "no focus info"
            log.debug("KWin not available: %s", exc)
            if self.bus is not None:
                self.bus.disconnect()
                self.bus = None
        return self.available

    async def _kwin(self, path: str, interface: str):
        introspection = await self.bus.introspect("org.kde.KWin", path)
        proxy = self.bus.get_proxy_object("org.kde.KWin", path, introspection)
        return proxy.get_interface(interface)

    async def stop(self) -> None:
        if self.bus is None:
            return
        try:
            if self.available:
                scripting = await self._kwin("/Scripting", "org.kde.kwin.Scripting")
                await scripting.call_unload_script(SCRIPT_NAME)
        except Exception:  # noqa: BLE001
            pass
        self.bus.disconnect()
