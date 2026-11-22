# Companion to addon protocol

A WoW addon cannot open sockets, read files or run programs while the game is
running. The only way for an outside program to hand text to an addon at
runtime is the keyboard. The companion therefore delivers every message like
this:

1. Put the message on the clipboard. On Linux this is the X11 clipboard via
   `xclip` whenever an X server exists, because Wine reads it directly;
   `wl-copy` on KWin maps a small surface to get keyboard focus, which takes
   focus away from the game. Windows and macOS use the system clipboard API.
2. Make sure the addon's hidden, invisible `EditBox` (`DictateReceiveBox`) has
   the keyboard:
   - after a dictation the addon focuses it itself when the dictation key is
     released, and keeps it for up to 10 s or until a message arrives (Esc
     gives the keyboard back);
   - for messages the companion sends on its own (future pushes such as AI
     answers) it first presses the **receive key** (default `CTRL-SHIFT-F12`),
     which the addon binds with `SetOverrideBindingClick` to a hidden button
     that focuses the box for 2 s.
3. Press the paste key (Ctrl+V; Command+V on macOS) on a virtual keyboard
   (Linux: `uinput` device `wow-dictate-keyboard`; Windows: `SendInput`;
   macOS: `CGEvent`). The message lands in the focused input line.
4. Restore the previous clipboard contents.

## Message format

```
##WD#<kind>#<payload>#WD##
```

- `kind` is a short word without `#`.
- `payload` may contain `#`; the message ends at the first `#WD##` after the start.
- `|` is replaced by `/` (WoW escape character), line breaks by spaces.

| Kind | Payload | Addon reaction |
|---|---|---|
| `t` | recognized text | routes it to a channel and sends / shows it (see design) |
| `s` | `empty` | "Nothing heard" |
| `s` | `loading` | the companion is still loading the model |
| `s` | `error:<name>` | recognition failed |

Unknown kinds are ignored, so new kinds can be added without breaking older
addon versions.

## Where the paste can land

- **Hidden receive box** (nothing else had the keyboard): the addon parses the
  message and clears the box.
- **An input line that already had the keyboard** (a chat edit box or the
  Dictate confirmation window): key bindings do not fire while typing, so the
  paste goes into that line. The addon hooks `OnTextChanged` of all chat edit
  boxes and its own window and replaces the message with its payload in place,
  so dictating while typing inserts the words at the cursor.
- **Another program**: prevented by the companion, which only reacts while the
  active window is `World of Warcraft` (see the platform table in design.md).

## Timing

| Setting (companion `[game]`) | Default | Why |
|---|---|---|
| `clipboard_delay_ms` | 80 | XWayland needs a moment to see the new clipboard owner |
| `focus_delay_ms` | 60 | the receive binding must run before `Ctrl+V` arrives |

On Linux, modifiers are pressed 60 ms before the key and released 60 ms after
it (30 ms on Windows and macOS), so slow modifier handling (Wine) never sees a
bare key.

On Linux the virtual keyboard presses the key that the current xkb options
make Ctrl (right Ctrl unless an option moves it). With `ctrl:swap_lwin_lctl`
the left Ctrl key code means Super, and Super+V opens the Plasma clipboard
history instead of pasting.

Before pressing keys the companion waits until no physical Ctrl/Alt/Shift is
held, so a trigger such as `SHIFT-BUTTON3` does not turn into `Shift+Ctrl+V`.
