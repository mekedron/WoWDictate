# Dictate

Voice-to-chat for World of Warcraft on Windows, Linux and macOS. Hold the
middle mouse button, flick the cursor toward a channel, say your message,
release. The speech is recognized locally on the CPU (NVIDIA Parakeet by
default, Russian and English in any mix) and lands in a small window where
Enter sends it, or goes out right away, or into the normal chat line, as you
prefer.

Two parts:

- `Dictate/`: the WoW addon (channel menu, indicator, confirmation window, settings).
- `companion/`: `wow-dictate`, a small background program that listens to the
  same key, records the microphone, recognizes the speech and pastes the text
  into the game. An addon cannot use the microphone or talk to other programs,
  so this part runs outside the game.

## Install

### Windows

In PowerShell, in the downloaded repository folder:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

This copies the addon into `World of Warcraft\_forever_\Interface\AddOns`
(found through the registry; otherwise pass `-WowDir "D:\...\_forever_"`),
installs [uv](https://docs.astral.sh/uv/) if needed, sets up the companion and
adds a "WoW Dictate" shortcut to the Start menu and to Startup. Do not run the
game as administrator: Windows would not let the companion paste into it.

### Linux

```bash
./install.sh
```

Copies the addon (the WoW folder is looked up in common Wine, Lutris, Bottles
and Steam prefixes; otherwise `WOW_DIR=".../_forever_" ./install.sh`) and runs
the companion as the systemd user service `wow-dictate`.

Needs your user in the `input` group (`sudo usermod -aG input $USER`, then log
in again), write access to `/dev/uinput`, `xclip`, PipeWire or PulseAudio.
Works on X11 and Wayland; the active window is detected through KWin on KDE
Plasma and through X11 elsewhere. Keyboard options that move Ctrl, Alt or Win
(`ctrl:swap_lwin_lctl` and friends) are read from KDE, GNOME or X11 settings.

### macOS

```bash
./install.sh
```

Copies the addon into `/Applications/World of Warcraft/_forever_` and runs the
companion as the LaunchAgent `dev.wowdictate`. Allow it in System Settings >
Privacy & Security under Accessibility, Input Monitoring and Microphone. On a
Mac the paste key is Command+V.

### All systems

- `wow-dictate doctor` shows what the companion detects: platform, config and
  log paths, keys, active window. Run it as
  `uv run --project companion wow-dictate doctor`.
- Other clients: `FLAVOR=_retail_` (Linux, macOS) or `-Flavor _retail_`
  (Windows); the addon's `.toc` targets WoW Forever.
- The first start downloads the speech model (about 700 MB).

## Use

| Key (default) | What it does |
|---|---|
| Middle mouse button, hold | channel menu; speak while holding, release to finish |
| Key Bindings > Dictate | default-channel and reply-to-whisper keys, send/cancel for the window |

- Start a message with a channel word to pick a channel without the menu:
  "Рейд, пулим через десять", "Гильдия: кто на ZG?", "party - need heal".
- Dictating while the chat line or the Dictate window is open inserts the text
  at the cursor.
- `/dictate` opens the settings, `/dictate help` lists commands,
  `/dictate test <text>` tries the routing without speaking,
  `/dictate debug` shows what the addon receives.

Every key you bind to a "hold" action in WoW must also be a `[[trigger]]` in
the companion config, written the same way (`BUTTON3`, `CTRL-T`,
`SHIFT-BUTTON4`). `wow-dictate config` prints where the config file is.

### Choosing a speech model

`[speech] model` in the config: `parakeet-v3` (default, fastest multilingual),
`gigaam-v3` (best Russian), `canary-v2` (most accurate multilingual, slower,
can translate), `gigaam-multi`, `whisper-turbo`. Compare them on your own voice:

```bash
uv run --project companion wow-dictate bench --phrases 3 --seconds 5
```

### Speak Russian, send English

```toml
[[trigger]]
key = "SHIFT-BUTTON3"
translate = "en"
```

Bind Shift + middle mouse button to the channel menu in WoW as well.

## Languages

The addon follows the game language (English and Russian so far; other
clients get English). `/dictate` > Language picks another one.

Adding a language takes one file:

1. Copy `Dictate/Locales/enUS.lua` to `Dictate/Locales/<locale>.lua`, using the
   WoW client locale code (`deDE`, `frFR`, `esES`, `ptBR`, `itIT`, ...), and
   change the first two arguments of `ns.RegisterLocale`: the code and the
   language name in that language.
2. Translate the strings; keep `%s` / `%d` placeholders. Strings you leave out
   fall back to English.
3. Add the file to `Dictate/Dictate.toc` after `Locales\ruRU.lua`.
4. Run `uv run --with lupa python tests/test_addon.py`: it reports missing or
   unknown keys and characters the addon font cannot show.

The voice channel words ("рейд", "guild", ...) are in `Dictate/Channels.lua`
(`PREFIXES`). Speech recognition languages depend on the model, not on the
addon language.

## Troubleshooting

| Symptom | Check |
|---|---|
| "No answer from the companion" | the companion runs (`wow-dictate doctor`, log file); `/dictate debug` shows `receive box got: ...` |
| `receive box got: v` | the paste arrived without Ctrl: report your keyboard options (`wow-dictate doctor`) |
| Nothing is recorded | the companion log says "ignored ... active window is ..."; add that caption to `[game] windows` |
| "Nothing heard" | microphone choice (`wow-dictate devices`, `[audio] device`); the last recording is kept as `last.wav` in the cache folder |

## How it works

See [docs/design.md](docs/design.md) and [docs/protocol.md](docs/protocol.md).

## Tests

```bash
uv run --with lupa python tests/test_addon.py              # addon logic against a mocked WoW API
uv run --project companion python tests/test_companion.py  # key names, matching, key tables
```

## License

MIT
