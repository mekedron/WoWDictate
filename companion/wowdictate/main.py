"""wow-dictate: push-to-talk speech recognition for the Dictate WoW addon."""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import statistics
import sys
import time

from . import config as config_mod
from . import keys
from .audio import SAMPLE_RATE, Microphone, rms
from .speech import MODELS, Recognizer
from .text import build_replacer, clean

log = logging.getLogger("wowdictate")

LAST_WAV = config_mod.CACHE_DIR / "last.wav"


def save_wav(audio) -> None:
    """Keep the last recording for troubleshooting (overwritten every time)."""
    import wave

    import numpy as np

    LAST_WAV.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(LAST_WAV), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())


def make_deliverer(platform_, cfg, modifiers_down):
    from .deliver import Deliverer

    receive = keys.parse(cfg.receive_key) if cfg.receive_key else None
    return Deliverer(
        platform_, receive, cfg.clipboard_delay_ms, cfg.focus_delay_ms, cfg.restore_clipboard, modifiers_down
    )


class Companion:
    def __init__(self, cfg: config_mod.Config):
        from . import platform

        self.cfg = cfg
        self.platform = platform.current()
        self.combos = [keys.parse(t.key) for t in cfg.triggers]
        self.recognizer = Recognizer(cfg.model, cfg.language, cfg.threads)
        self.ready = False
        self.mic = Microphone(cfg.device, cfg.preroll_ms, cfg.max_seconds)
        self.matcher = keys.HotkeyMatcher(self.combos, self.on_press, self.on_release)
        self.deliver = make_deliverer(self.platform, cfg, self.matcher.modifiers_down)
        self.replacer = build_replacer(cfg.replace)
        self.recording: tuple[int, float] | None = None  # trigger index, start time

    def on_press(self, index: int) -> None:
        from . import platform

        if self.recording is not None:
            return
        caption = self.platform.active_window()
        if not platform.is_game(caption, self.cfg.windows):
            log.info("ignored %s: active window is %r, not the game", self.combos[index].text, caption)
            return
        self.recording = (index, time.monotonic())
        self.mic.start()
        log.info("recording (%s)", self.combos[index].text)

    def on_release(self, index: int) -> None:
        if self.recording is None or self.recording[0] != index:
            return
        _, started = self.recording
        self.recording = None
        audio = self.mic.stop()
        held_ms = (time.monotonic() - started) * 1000
        if held_ms < self.cfg.min_hold_ms:
            log.info("ignored a short press (%.0f ms < min_hold_ms)", held_ms)
            return
        asyncio.ensure_future(self.process(audio, self.cfg.triggers[index].translate))

    async def process(self, audio, translate: str | None) -> None:
        from .deliver import encode

        if not self.ready:
            await self.deliver.send(encode("s", "loading"))
            return
        save_wav(audio)
        level = rms(audio)
        log.info(
            "recorded %.1f s, level %.4f (silence below %.4f), saved to %s",
            audio.size / SAMPLE_RATE, level, self.cfg.silence_rms, LAST_WAV,
        )
        if level < self.cfg.silence_rms:
            await self.deliver.send(encode("s", "empty"))
            return
        start = time.perf_counter()
        try:
            raw = await asyncio.to_thread(self.recognizer.transcribe, audio, translate)
        except Exception as exc:  # noqa: BLE001
            log.exception("recognition failed")
            await self.deliver.send(encode("s", f"error:{type(exc).__name__}"))
            return
        text = clean(raw, self.cfg.strip_final_period, self.replacer)
        log.info(
            "%.1f s audio -> %.0f ms: %s",
            audio.size / SAMPLE_RATE,
            (time.perf_counter() - start) * 1000,
            text,
        )
        await self.deliver.send(encode("t", text) if text else encode("s", "empty"))

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        await self.platform.start(self.matcher, loop)
        translator = any(t.translate for t in self.cfg.triggers)
        log.info("platform %s, triggers: %s", self.platform.name, ", ".join(c.text for c in self.combos))
        await asyncio.to_thread(self.recognizer.preload, translator)
        self.ready = True
        log.info("ready (%s)", self.cfg.model)
        stop = asyncio.Event()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stop.set)
            except (NotImplementedError, RuntimeError):  # Windows: Ctrl+C raises KeyboardInterrupt
                pass
        try:
            await stop.wait()
        finally:
            await self.platform.stop()
            self.mic.close()
            self.deliver.close()


def cmd_devices(_args) -> None:
    import sounddevice as sd

    print(sd.query_devices())


def cmd_bench(args) -> None:
    """Record a few phrases from the microphone and run every model on them."""
    import numpy as np
    import sounddevice as sd

    clips = []
    for i in range(args.phrases):
        input(f"[{i + 1}/{args.phrases}] Enter, then speak for {args.seconds} s...")
        clip = sd.rec(int(args.seconds * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype="float32")
        sd.wait()
        clips.append(np.ascontiguousarray(clip[:, 0]))
    names = args.models.split(",") if args.models else list(MODELS)
    for name in names:
        recognizer = Recognizer(name, args.language)
        start = time.perf_counter()
        recognizer.preload()
        print(f"\n== {name} (loaded in {time.perf_counter() - start:.1f} s)")
        for clip in clips:
            times, text = [], ""
            for _ in range(3):
                t = time.perf_counter()
                text = recognizer.transcribe(clip)
                times.append(time.perf_counter() - t)
            print(f"  {statistics.median(times) * 1000:5.0f} ms | {text}")
        del recognizer


def _countdown(seconds: int) -> None:
    for left in range(seconds, 0, -1):
        print(f"switch to WoW, starting in {left}...", flush=True)
        time.sleep(1)


def cmd_send(args) -> None:
    """Deliver a test message to the game without speaking (receive key + paste)."""
    from . import platform
    from .deliver import encode

    cfg = config_mod.load()
    deliverer = make_deliverer(platform.current(), cfg, lambda: False)
    _countdown(args.delay)
    asyncio.run(deliverer.send(encode("t", args.text), receive_key=True))
    deliverer.close()
    print("sent")


def cmd_probe(args) -> None:
    """Press the receive key and the paste key separately, to see what each does in the game."""
    from . import platform
    from .deliver import encode

    cfg = config_mod.load()
    plat = platform.current()
    receive = keys.parse(cfg.receive_key)
    keyboard = plat.keyboard([receive, plat.paste])
    asyncio.run(plat.clipboard.set(encode("t", "probe / проверка")))
    _countdown(args.delay)
    print(f"[{time.strftime('%X')}] pressing {receive.text}", flush=True)
    keyboard.tap(receive)
    time.sleep(3)
    print(f"[{time.strftime('%X')}] pressing {plat.paste.text}", flush=True)
    keyboard.tap(plat.paste)
    time.sleep(0.5)
    keyboard.close()
    print("done")


def cmd_doctor(_args) -> None:
    """Print what the companion sees on this system."""
    from . import platform

    cfg = config_mod.load()
    plat = platform.current()
    print("platform:", plat.name)
    print("config:", config_mod.CONFIG_PATH)
    print("log:", config_mod.LOG_PATH)
    print("triggers:", ", ".join(keys.parse(t.key).text for t in cfg.triggers))
    print("paste key:", plat.paste.text)
    if hasattr(plat, "options"):
        print("xkb options:", ",".join(plat.options) or "none")
        print("modifier keys pressed:", {m: c for m, c in plat.press.items()})
    print("clipboard:", type(plat.clipboard).__name__)
    print("active window:", repr(plat.active_window()))


def cmd_config(_args) -> None:
    print(config_mod.ensure_config_file())


def main() -> None:
    parser = argparse.ArgumentParser(prog="wow-dictate", description=__doc__)
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("run", help="run the companion (default)")
    sub.add_parser("devices", help="list audio devices")
    sub.add_parser("config", help="create the config file if needed and print its path")
    sub.add_parser("doctor", help="show what the companion detects on this system")
    probe = sub.add_parser("probe", help="press the receive key, then Ctrl+V 3 s later, in the game")
    probe.add_argument("--delay", type=int, default=5)
    send = sub.add_parser("send", help="type a test message into the game after a delay")
    send.add_argument("text", nargs="?", default="Dictate test / проверка")
    send.add_argument("--delay", type=int, default=5)
    bench = sub.add_parser("bench", help="compare speech models on your own voice")
    bench.add_argument("--phrases", type=int, default=3)
    bench.add_argument("--seconds", type=float, default=5)
    bench.add_argument("--models", default="")
    bench.add_argument("--language", default="ru")
    args = parser.parse_args()
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if args.cmd in (None, "run"):
        from logging.handlers import RotatingFileHandler

        config_mod.LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(RotatingFileHandler(config_mod.LOG_PATH, maxBytes=1_000_000, backupCount=2, encoding="utf-8"))
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
    )
    logging.getLogger("dbus_fast").setLevel(logging.WARNING)
    if args.cmd == "devices":
        cmd_devices(args)
    elif args.cmd == "bench":
        cmd_bench(args)
    elif args.cmd == "probe":
        cmd_probe(args)
    elif args.cmd == "send":
        cmd_send(args)
    elif args.cmd == "doctor":
        cmd_doctor(args)
    elif args.cmd == "config":
        cmd_config(args)
    else:
        try:
            asyncio.run(Companion(config_mod.load()).run())
        except KeyboardInterrupt:
            sys.exit(0)


if __name__ == "__main__":
    main()
