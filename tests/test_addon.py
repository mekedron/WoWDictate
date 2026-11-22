"""Offline checks of the Dictate addon logic against a mocked WoW API.

Run: uv run --with lupa python tests/test_addon.py   (from the repository root)
"""

import pathlib
import sys

import lupa

try:
    from lupa import lua51 as lua_module
except ImportError:
    lua_module = lupa

ROOT = pathlib.Path(__file__).resolve().parent.parent / "Dictate"
TOC = [l.strip().replace("\\", "/") for l in (ROOT / "Dictate.toc").read_text().splitlines()
       if l.strip().endswith(".lua")]
FORBIDDEN_GLYPHS = "\u2192\u2190\u2022\u00b7\u00d7"  # arrows, bullet, middle dot, multiplication sign

MOCK = r"""
local noop = function() end
local function object()
  local o = {}
  return setmetatable(o, { __index = function(t, k)
    if k == "GetStringWidth" then return function() return 50 end end
    if k == "GetText" then return function(self) return rawget(self, "_text") or "" end end
    if k == "SetText" then return function(self, v) rawset(self, "_text", v) end end
    if k == "HookScript" or k == "SetScript" then
      return function(self, name, fn) local s = rawget(self, "scripts") or {}; rawset(self, "scripts", s); s[name] = fn end
    end
    if k == "GetEffectiveScale" then return function() return 1 end end
    if type(k) == "string" and k:sub(1, 6) == "Create" then return function() return object() end end
    return noop
  end })
end
CreateFrame = function() return object() end
CreateFont = function() return object() end
UIParent = object()
GameFontNormal = object(); GameFontNormal.GetFont = function() return "x", 12, "" end
GameFontHighlight = GameFontNormal
DEFAULT_CHAT_FRAME = { AddMessage = function(_, m) print("CHAT", m) end }
GetLocale = function() return "ruRU" end
ChatTypeInfo = setmetatable({}, { __index = function() return { r = 1, g = 0.5, b = 0 } end })
SOUNDKIT = {}
PlaySound = noop
GetTime = function() return NOW end
NOW = 100
time = os.time
date = os.date
C_Timer = { NewTimer = function() return { Cancel = noop } end, After = noop }
IsInGroup = function() return GROUP end
IsInRaid = function() return RAID end
IsInGuild = function() return true end
IsInInstance = function() return false end
UnitIsGroupLeader = function() return false end
UnitIsGroupAssistant = function() return false end
UnitExists = function() return false end
LE_PARTY_CATEGORY_HOME = 1
LE_PARTY_CATEGORY_INSTANCE = 2
C_GuildInfo = { IsGuildOfficer = function() return false end }
GetChannelList = function() return 1, "General", false, 2, "Trade", false end
Ambiguate = function(n) return n end
SENT = {}
C_ChatInfo = {
  SendChatMessage = function(text, chatType, lang, target) table.insert(SENT, chatType .. "|" .. tostring(target) .. "|" .. text) end,
  InChatMessagingLockdown = function() return false end,
}
OPENED = nil
ChatFrameUtil = {
  GetLastTellTarget = function() return LAST_TELL end,
  SetLastToldTarget = noop,
  OpenChat = function(t) OPENED = t end,
}
InCombatLockdown = function() return false end
CopyTable = function(t) local c = {} for k, v in pairs(t) do c[k] = type(v) == "table" and CopyTable(v) or v end return c end
strtrim = function(s) return (s:gsub("^%s+", ""):gsub("%s+$", "")) end
Settings = nil
SlashCmdList = {}
NUM_CHAT_WINDOWS = 1
"""


def main():
    lua = lua_module.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(MOCK)
    ns = lua.table()
    for name in TOC:
        chunk = lua.execute(f"return function(...) {(ROOT / name).read_text()} \nend")
        chunk("Dictate", ns)
    # ADDON_LOADED
    lua.execute("DictateDB = nil")
    g = lua.globals()
    ns.db = None
    # emulate event handler: find the registered OnEvent is hard with mocks; init directly
    lua.execute("""
      local ns = ...
    """)
    init = lua.eval("""function(ns)
      DictateDB = {}
      for k, v in pairs(ns.defaults) do DictateDB[k] = type(v) == "table" and CopyTable(v) or v end
      ns.db = DictateDB
      ns.lang = "ruRU"
    end""")
    init(ns)
    failures = 0

    def check(label, got, want):
        nonlocal failures
        ok = got == want
        failures += not ok
        print(("OK  " if ok else "FAIL"), label, "|", repr(got), "" if ok else f"!= {want!r}")

    # Locales: every locale has exactly the English keys, no glyphs the font lacks.
    en_keys = set(ns.locales.enUS.strings.keys())
    for code in ns.localeOrder.values():
        keys = set(ns.locales[code].strings.keys())
        check(f"locale {code} missing keys", sorted(en_keys - keys), [])
        check(f"locale {code} unknown keys", sorted(keys - en_keys), [])
        texts = []
        for value in ns.locales[code].strings.values():
            texts += list(value.values()) if lupa.lua_type(value) == "table" else [value]
        check(f"locale {code} glyphs", [t for t in texts if any(g in t for g in FORBIDDEN_GLYPHS)], [])
    check("game locale picked", (ns.DetectLanguage("auto"), ns.DetectLanguage("en"), ns.DetectLanguage("deDE")),
          ("ruRU", "enUS", "enUS"))
    check("binding name localized", g.BINDING_NAME_DICTATE_RADIAL, "Диктовка: меню каналов (удерживать)")

    kind, payload, before, after = ns.ExtractMessage("abc##WD#t#Привет, мир#WD##xyz")
    check("extract kind", kind, "t")
    check("extract payload", payload, "Привет, мир")
    check("extract around", (before, after), ("abc", "xyz"))
    check("extract hash in text", ns.ExtractMessage("##WD#t#пул #1 через 5#WD##")[1], "пул #1 через 5")
    check("extract incomplete", ns.ExtractMessage("##WD#t#half"), None)

    ch = ns.Channels
    check("lower", ch.Lower("РЕЙД, Ёлка ABC"), "рейд, ёлка abc")
    check("upperfirst", ch.UpperFirst("пулим"), "Пулим")
    check("upperfirst ё", ch.UpperFirst("ёлка"), "Ёлка")

    long = ("слово " * 60).strip()
    parts = list(ch.Split(long).values())
    check("split count", len(parts), 3)
    check("split sizes", all(len(p.encode()) <= 255 for p in parts), True)
    check("split rejoin", " ".join(parts), long)
    check("split utf8 valid", all(p.encode().decode("utf-8") == p for p in parts), True)

    g.GROUP, g.RAID = True, True
    t, rest = ch.ParsePrefix("Рейд, пулим через десять секунд")
    check("prefix raid", (t and t.chatType, rest), ("RAID", "Пулим через десять секунд"))
    t, rest = ch.ParsePrefix("В гильдию: кто идёт в рейд?")
    check("prefix guild", (t and t.chatType, rest), ("GUILD", "Кто идёт в рейд?"))
    check("no prefix inside word", ch.ParsePrefix("Гильдийный банк открыт"), None)
    t, rest = ch.ParsePrefix("party - need heal")
    check("prefix party en", (t and t.chatType, rest), ("PARTY", "Need heal"))
    g.GROUP, g.RAID = False, False
    check("prefix unavailable channel", ch.ParsePrefix("Рейд, пулим"), None)

    # Full flow in auto mode: quick key -> text with prefix -> sent to guild.
    ns.db.mode = "auto"
    ns.HandleText("Гильдия, всем привет")
    check("auto send", list(g.SENT.values()), ["GUILD|nil|Всем привет"])
    # Restricted SAY outside instance falls back to the chat box.
    ns.HandleText("Привет всем")
    check("say falls back to chatbox", g.OPENED, "/s Привет всем")
    # Reply binding flow
    g.LAST_TELL = "Thrall"
    g.NOW = 100
    g.Dictate_Binding("REPLY", "down")
    g.NOW = 101
    g.Dictate_Binding("REPLY", "up")
    ns.HandleText("скоро буду")
    check("reply", list(g.SENT.values())[-1], "WHISPER|Thrall|скоро буду")
    # Tap shorter than the minimum hold does nothing
    g.Dictate_Binding("QUICK", "down")
    g.Dictate_Binding("QUICK", "up")
    check("tap clears pending", ns.pending, None)
    print("\n%d failure(s)" % failures)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
