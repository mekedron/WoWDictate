# Dictate: design

Dictate lets a player write to WoW chat by voice: hold a key, optionally flick
the mouse toward a channel, speak, release. The text is recognized locally and
either sent at once, put into the chat input line, or shown in a small window
to confirm or edit.

## Parts

| Part | Where | Role |
|---|---|---|
| `Dictate/` | WoW addon (Lua) | channel menu, recording indicator, routing, confirmation window, sending |
| `companion/` | `wow-dictate`, Python; systemd user service (Linux), Startup shortcut (Windows), LaunchAgent (macOS) | push-to-talk detection, microphone, speech recognition, pasting the result into the game |

An addon has no access to the microphone, files, network or other programs, so
recognition has to run outside the game. Both parts react to the **same
physical key**: the companion listens to input without blocking it, so the
game still receives the key and runs the addon's key binding.

```
hold key ──► addon: radial menu + "Recording: Raid"      companion: start recording
release  ──► addon: remember channel, "Recognizing..."    companion: stop, recognize (0.6-2 s)
         ──► addon: focuses its hidden input box               companion: clipboard + Ctrl+V
         ◄── addon: hidden box receives ##WD#t#text#WD## ─┘
             route: menu choice > voice prefix > default channel
             deliver: popup | chat input line | send now
```

The wire format and the receive mechanism are in [protocol.md](protocol.md).

## Addon

### Key bindings (Key Bindings > AddOns > Dictate)

All "hold" bindings use `runOnUp`, so the addon sees both press and release.

| Binding | Use |
|---|---|
| Channel menu (hold) | radial menu around the cursor; bound to the middle mouse button on first login if that button is free |
| Default channel (hold) | no menu, goes to the default channel (voice prefixes apply) |
| Reply to whisper (hold) | goes to the last whisper sender (also Battle.net whispers) |
| Send / Cancel the confirmation window | for playing with the window not holding the keyboard |

Holds shorter than 0.25 s are taps and do nothing (the companion ignores holds
under 300 ms, `min_hold_ms`).

### Radial menu

Opens centered on the cursor while the key is held. Channels sit on a ring,
clockwise from the top in a fixed order (Raid, Party, Instance, Raid Warning,
Say, Yell, Reply, Whisper target, Officer, Guild, then joined public channels
if enabled), so the same channel is always in the same direction. Only channels
usable right now are shown: Party only in a group, Raid Warning only as raid
leader or assistant, Reply only after a whisper, Whisper target only for a
friendly player target.

- Cursor near the center: the default channel (or Cancel, option).
- Cursor toward a pill: that channel; the HUD shows it live.
- Cursor far outside the ring: Cancel (shown in red).

### Routing

1. The channel picked in the menu, or the whisper sender for the Reply binding.
2. Otherwise a **voice prefix**: the first words name a channel ("Рейд, пулим
   через десять", "guild: who is up for ZG"). The prefix is removed and the
   next letter capitalized. A prefix needs a following space or punctuation and
   only matches channels available right now.
3. Otherwise the default channel: group (instance > raid > party) else Say,
   or the last used channel, or a fixed one.

### Delivery modes

| Mode | Behaviour |
|---|---|
| Confirmation window (default) | Window with the channel (click / Tab to change), editable text, byte counter and part count, Send / Cancel. Takes the keyboard by default (Enter sends, Esc cancels); optional auto-send countdown. |
| Chat input line | Opens the normal chat input with `/p text` etc.; the player presses Enter. Long texts use the window instead. |
| Send right away | Sends at once and flashes "Sent: Raid". |

Messages over 255 bytes (about 127 Cyrillic letters) are split at spaces into
several messages.

Say, Yell and numbered channels need a hardware event outside instances, and
`C_ChatInfo.InChatMessagingLockdown()` marks periods when chat is restricted
for addons. In those cases "Send right away" falls back to the chat input line,
and the countdown does not run, so the player's own Enter or click sends.

### Text rendering

Like Talent Compass, all text uses copies of Blizzard fonts set to
`Fonts\FRIZQT___CYR.TTF`, which covers Latin and Cyrillic. Avoid glyphs the
font lacks (arrows, bullets, middle dot).

## Companion

`wow-dictate run`. The core (`main.py`, `keys.py`, `audio.py`, `speech.py`,
`deliver.py`) is the same everywhere; `platform/` holds one module per
operating system:

| Job | Linux (`linux.py`) | Windows (`windows.py`) | macOS (`macos.py`) |
|---|---|---|---|
| Hear the trigger key | `evdev`, every keyboard and mouse with a trigger key, rescanned for hot-plug | low-level hooks (pynput) | event taps (pynput) |
| Press keys | `uinput` virtual keyboard (write-only access is enough) | `SendInput` (pynput) | `CGEvent` (pynput) |
| Clipboard | `xclip` when an X server exists (Wine/Proton reads it), else `wl-copy` | Win32 API | `NSPasteboard` |
| Active window | KWin script over D-Bus, else X11 `_NET_ACTIVE_WINDOW` | `GetForegroundWindow` | Quartz window list (front-most layer-0 window owner) |
| Paste key | Ctrl+V | Ctrl+V | Command+V |
| Runs as | systemd user service | Startup shortcut (`uvw`, no console) | LaunchAgent |

- **Key names** are WoW binding names on every platform (`BUTTON3`,
  `CTRL-SHIFT-F12`). Platform modules map their native codes to them: evdev
  codes, Windows virtual keys, macOS virtual key codes. Virtual key codes do
  not depend on the input language, so a Russian layout changes nothing.
  `keys.HotkeyMatcher` matches modifiers exactly, as WoW does.
- **Keyboard options on Linux**: options that move modifiers
  (`ctrl:swap_lwin_lctl`, `ctrl:nocaps`, `altwin:swap_alt_win`, ...) are read
  from `XKB_DEFAULT_OPTIONS`, KDE `kxkbrc`, GNOME `gsettings` and
  `setxkbmap -query`. They decide which physical key counts as Ctrl when
  matching triggers and which key the virtual keyboard presses for Ctrl (right
  Ctrl and Shift by default, left Alt because right Alt is often AltGr).
- **Focus gate**: dictation only runs while the active window caption (the
  application name on macOS) is `World of Warcraft`; unknown counts as the game.
- **Audio**: `sounddevice`, 16 kHz mono. The microphone stays open and keeps
  300 ms before the press, so the first syllable survives. Recordings below an
  RMS threshold are reported as `empty` without running the model; the last
  recording is kept as `last.wav` in the cache folder.
- **Recognition**: `onnx-asr` on CPU, model loaded and warmed up at start.
- **Text clean-up**: whitespace, a space before glued dashes, user
  replacements (`[text.replace]`), final period dropped.
- **Delivery**: see [protocol.md](protocol.md).
- **Translation**: a trigger with `translate = "en"` runs NVIDIA Canary in
  translation mode: speak Russian, send English.
- **Files**: config, cache and log follow each system's conventions
  (`platformdirs`); `wow-dictate doctor` prints them.

### Speech models

Measured on i7-12700H, CPU only, int8, with WoW running; median of 3 warm
runs on a 6 s and a 15 s Russian clip.

| Config name | Model | Languages | 6 s | 15 s | Notes |
|---|---|---|---|---|---|
| `parakeet-v3` | NVIDIA Parakeet TDT 0.6B v3 | 25 European incl. ru, en; auto-detect | 0.8 s | 1.2 s | default; punctuation |
| `canary-v2` | NVIDIA Canary 1B v2 | same 25; language set in config | 1.9 s | 3.6 s | X to English translation |
| `gigaam-v3` | Sber GigaAM v3 e2e RNNT | Russian | 0.8 s | 1.0 s | best Russian, punctuation, "ё" |
| `gigaam-multi` | Sber GigaAM multilingual CTC | several | 0.6 s | 0.7 s | no punctuation or capitals |
| `whisper-turbo` | Whisper large-v3-turbo (ONNX) | 99 | 5.4 s | 7.3 s | too slow on this CPU |

The GPU (RTX 3050 Ti, 4 GB) is left to the game: WoW at 5120x1440 already uses
most of its memory. `wow-dictate bench` records a few phrases from the
microphone and runs every model on them, to compare accuracy on the player's
own voice and mixed Russian/English game slang.

## Extension points

The companion is the place for everything that needs the outside world; the
addon stays a thin UI. New features add a message `kind` (unknown kinds are
ignored by older addons) and, if needed, a trigger option.

- **AI assistant channel**: a trigger (or a menu sector) whose speech goes to
  an LLM with web search and WoW sources instead of chat; the answer comes back
  as a new kind (`a`) and is shown in an addon window with conversation
  history. Answers arrive at any time, which the receive-key mechanism already
  supports (the companion can push at will).
- **Addon to companion direction** (typed questions, current zone or target
  as context): not possible directly. Candidates: the chat log file written
  with `/chatlog` (`Logs/WoWChatLog.txt`) for messages the addon posts to a
  private channel, or SavedVariables, which are only written on reload or
  logout.

## To verify in game

- Windows and macOS: hooks see the middle mouse button while WoW has focus,
  and the pasted text reaches the addon.
- Linux: the paste reaches the addon with the right-Ctrl virtual keyboard.
- `C_ChatInfo.SendChatMessage` from the receive box (inside the paste key
  event) for Party/Raid/Guild in "Send right away" mode, and behaviour during
  encounters (`InChatMessagingLockdown`).
- Chat input line mode: `/p text` set through `ChatFrameUtil.OpenChat` is sent
  to the right channel on Enter.
