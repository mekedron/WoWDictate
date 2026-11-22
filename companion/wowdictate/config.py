"""Configuration: ~/.config/wow-dictate/config.toml merged over built-in defaults."""

from __future__ import annotations

import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import platformdirs

# Linux: ~/.config/wow-dictate, Windows: %APPDATA%\wow-dictate,
# macOS: ~/Library/Application Support/wow-dictate
CONFIG_DIR = Path(platformdirs.user_config_dir("wow-dictate", appauthor=False, roaming=True))
CONFIG_PATH = CONFIG_DIR / "config.toml"
CACHE_DIR = Path(platformdirs.user_cache_dir("wow-dictate", appauthor=False))
LOG_PATH = Path(platformdirs.user_log_dir("wow-dictate", appauthor=False)) / "wow-dictate.log"

DEFAULT_CONFIG = """\
# Dictate companion settings. Restart the companion after editing:
#   Linux:   systemctl --user restart wow-dictate
#   Windows: run the "WoW Dictate" shortcut in the Start menu again
#   macOS:   launchctl kickstart -k gui/$(id -u)/dev.wowdictate

# Push-to-talk keys, written like WoW key bindings ("BUTTON3", "T", "CTRL-T",
# "SHIFT-BUTTON4"; on macOS "META" is Command). Use the same keys you bound to the Dictate actions in WoW
# (Esc > Options > Keybindings > AddOns > Dictate), so the game opens the
# channel menu while the companion records.
#   translate = "en"  speaks any supported language, sends English (Canary model).
[[trigger]]
key = "BUTTON3"

# [[trigger]]
# key = "SHIFT-BUTTON3"
# translate = "en"

[speech]
# parakeet-v3   NVIDIA Parakeet TDT 0.6B v3: Russian + English + 23 European
#               languages, detects the language by itself, punctuation. Default.
# canary-v2     NVIDIA Canary 1B v2: same languages, more accurate on hard audio,
#               about 2x slower, needs `language`; also used for translation.
# gigaam-v3     Sber GigaAM v3 e2e: best Russian, punctuation, Russian only.
# gigaam-multi  Sber GigaAM multilingual CTC: fastest, no punctuation.
# whisper-turbo OpenAI Whisper large-v3-turbo: slow on CPU (5 s and more).
model = "parakeet-v3"
# Source language for models that need it (canary-v2): "ru", "en", ...
language = "ru"
# onnxruntime threads, 0 = automatic.
threads = 0

[audio]
# "default" or a part of the input device name (see `wow-dictate devices`).
device = "default"
# Keep the microphone open and prepend this much audio recorded before the key
# press, so the first syllable is not cut off. 0 opens the microphone per press.
preroll_ms = 300
# Presses shorter than this are ignored (a tap is not a dictation).
min_hold_ms = 300
# Recordings stop after this many seconds even if the key is still held.
max_seconds = 30
# Below this RMS level the recording counts as silence.
silence_rms = 0.004

[text]
# Drop the final period of a message, as people do in chat.
strip_final_period = true
# Exact replacements applied after recognition, case-insensitive whole words.
[text.replace]
# "пати" = "пати"
# "хилл" = "хил"

[game]
# Window captions (application name on macOS) that count as the game.
# Dictation only runs while one of them is the active window.
windows = ["World of Warcraft"]
# Key the addon binds to "receive text" (used for messages the companion sends
# on its own). Must match /dictate receivekey. Empty disables it.
receive_key = "CTRL-SHIFT-F12"
# Delay after setting the clipboard and after the receive key, in milliseconds.
clipboard_delay_ms = 80
focus_delay_ms = 60
# Put the previous clipboard contents back after pasting.
restore_clipboard = true
"""


@dataclass
class Trigger:
    key: str
    translate: str | None = None


@dataclass
class Config:
    triggers: list[Trigger] = field(default_factory=lambda: [Trigger("BUTTON3")])
    model: str = "parakeet-v3"
    language: str = "ru"
    threads: int = 0
    device: str = "default"
    preroll_ms: int = 300
    min_hold_ms: int = 300
    max_seconds: float = 30
    silence_rms: float = 0.004
    strip_final_period: bool = True
    replace: dict[str, str] = field(default_factory=dict)
    windows: list[str] = field(default_factory=lambda: ["World of Warcraft"])
    receive_key: str = "CTRL-SHIFT-F12"
    clipboard_delay_ms: int = 80
    focus_delay_ms: int = 60
    restore_clipboard: bool = True


def ensure_config_file() -> Path:
    if not CONFIG_PATH.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        text = DEFAULT_CONFIG
        if sys.platform == "darwin":
            # Many Mac mice have no side buttons, and F-keys are media keys.
            text = text.replace('receive_key = "CTRL-SHIFT-F12"', 'receive_key = "CTRL-SHIFT-F19"')
        CONFIG_PATH.write_text(text, encoding="utf-8")
    return CONFIG_PATH


def load(path: Path | None = None) -> Config:
    path = path or ensure_config_file()
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    cfg = Config()
    if "trigger" in data:
        cfg.triggers = [Trigger(t["key"], t.get("translate")) for t in data["trigger"]]
    speech = data.get("speech", {})
    cfg.model = speech.get("model", cfg.model)
    cfg.language = speech.get("language", cfg.language)
    cfg.threads = int(speech.get("threads", cfg.threads))
    audio = data.get("audio", {})
    cfg.device = audio.get("device", cfg.device)
    cfg.preroll_ms = int(audio.get("preroll_ms", cfg.preroll_ms))
    cfg.min_hold_ms = int(audio.get("min_hold_ms", cfg.min_hold_ms))
    cfg.max_seconds = float(audio.get("max_seconds", cfg.max_seconds))
    cfg.silence_rms = float(audio.get("silence_rms", cfg.silence_rms))
    text = data.get("text", {})
    cfg.strip_final_period = bool(text.get("strip_final_period", cfg.strip_final_period))
    cfg.replace = dict(text.get("replace", {}))
    game = data.get("game", {})
    cfg.windows = list(game.get("windows", cfg.windows))
    cfg.receive_key = game.get("receive_key", cfg.receive_key)
    cfg.clipboard_delay_ms = int(game.get("clipboard_delay_ms", cfg.clipboard_delay_ms))
    cfg.focus_delay_ms = int(game.get("focus_delay_ms", cfg.focus_delay_ms))
    cfg.restore_clipboard = bool(game.get("restore_clipboard", cfg.restore_clipboard))
    return cfg
