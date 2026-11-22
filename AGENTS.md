# AGENTS.md

Guidance for agents working on Dictate (voice-to-chat for WoW: Forever on Windows, Linux and macOS).

## Layout

| Path | Purpose |
|---|---|
| `Dictate/` | the addon; runtime files are `Dictate.toc`, `Bindings.xml`, `*.lua` |
| `Dictate/Locales/` | `Locales.lua` (registry, `ns.L`, fallback to enUS, binding names), one file per WoW locale (`enUS.lua` is the reference) |
| `Dictate/Core.lua` | saved variables, fonts, protocol parsing, dictation state, key bindings, receive box, delivery, slash commands |
| `Dictate/Channels.lua` | channel availability, default channel, voice prefixes, splitting, sending |
| `Dictate/UI.lua` | HUD and confirmation window |
| `Dictate/Radial.lua` | radial channel menu |
| `Dictate/Options.lua` | Settings panel (vertical layout) |
| `companion/wowdictate/` | `wow-dictate` companion (Python, uv): core modules |
| `companion/wowdictate/platform/` | one module per OS (`linux.py`, `windows.py`, `macos.py`, shared `pynput_common.py`, KWin focus `kwin.py`, write-only `uinput.py`) |
| `install.sh`, `install.ps1` | installers: Linux + macOS, Windows |
| `tests/test_addon.py` | addon logic against a mocked WoW API (`uv run --with lupa python tests/test_addon.py`) |
| `tests/test_companion.py` | key names, matching, per-OS key tables, xkb modifier moves (`uv run --project companion python tests/test_companion.py`) |
| `companion/tools/bench_models.py` | model latency on WAV files |
| `docs/` | design and protocol |

## Target client

- WoW Forever, `## Interface: 16001`, mainline-based UI (`C_ChatInfo.SendChatMessage`,
  `ChatFrameUtil`, Settings API). Blizzard UI source: branch `forever` of
  https://github.com/Gethe/wow-ui-source.
- The user's install: `~/Battle.net/Games/World of Warcraft/_forever_` under Proton
  (`./install.sh addon`); the user tests with `/reload`.

## Rules

- All addon text goes through `ns.CreateText` / `ns.Font` (Cyrillic Friz Quadrata).
  No arrows, bullets, middle dots or multiplication signs in UI strings.
- In-game texts: add every new key to `Locales/enUS.lua` and `Locales/ruRU.lua`;
  `tests/test_addon.py` checks that locales have the same keys. Docs are English.
- Companion code outside `platform/` must not use OS-specific APIs; key names are WoW
  binding names everywhere. Windows and macOS modules cannot be run here: keep their
  key tables covered by `tests/test_companion.py`.
- Protocol changes: add a new message kind, never change existing ones; update `docs/protocol.md`.
- Never run the companion's delivery against the game while the user is playing
  without asking: it presses keys in the active WoW window.
- Commits: the user is the only author, no attribution trailers.
